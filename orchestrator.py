"""GPT(Codex) ↔ Claude Code 자동 연구 루프.

반복(iteration) 한 번:
    GPT 계획 (codex, read-only) → [사람 확인] → Claude 구현/실험 → GPT 리뷰 (codex, read-only, JSON)

리뷰의 verdict로 다음 행동을 정한다.
    CONTINUE    → 다음 반복
    DONE        → 종료
    NEEDS_HUMAN → 사람 입력을 받고 다음 반복 (또는 종료)

단계별 모델/사고 수준은 agent/tiers.json의 등급으로 정한다.
    GPT 계획  : 직전 리뷰의 next_plan_tier (deep / normal / light), 첫 반복은 deep
    Claude    : 계획의 claude_tier (creative / heavy / light)
    GPT 리뷰  : Claude 등급을 따라감 (creative→deep, heavy→normal, light→light)

산출물은 agent/runs/iter_NNN/ 에 저장된다. 중간에 끊겨도 다시 실행하면
완료되지 않은 단계부터 이어서 진행한다.

사용 예:
    python orchestrator.py                     # 매 반복 계획을 확인하며 진행
    python orchestrator.py --auto --max-iters 3
    python orchestrator.py --reset --goal "새 연구 목표"
    python orchestrator.py --gpus 1            # Claude가 GPU 1만 보이게
    python orchestrator.py --gpt-tier normal --claude-tier light   # 등급 강제
"""

from pathlib import Path
import argparse
import datetime
import json
import os
import shutil
import subprocess
import sys
import threading

PROJECT_DIR = Path(__file__).resolve().parent
AGENT_DIR = PROJECT_DIR / "agent"
PROMPT_DIR = AGENT_DIR / "prompts"
RUNS_DIR = AGENT_DIR / "runs"
ARCHIVE_DIR = AGENT_DIR / "archive"

GOAL_FILE = AGENT_DIR / "GOAL.md"
INDEX_FILE = AGENT_DIR / "INDEX.md"
LOG_FILE = AGENT_DIR / "RESEARCH_LOG.md"
TIERS_FILE = AGENT_DIR / "tiers.json"
# runs/ 도입 전 수동 실행의 마지막 리뷰. 첫 반복 계획의 참고 자료로 쓴다.
LEGACY_REVIEW_FILE = AGENT_DIR / "GPT_REVIEW.md"

CONDA_ENV = Path("/home/test/.conda/envs/medgemma")
HF_HOME = PROJECT_DIR / "hf_cache"

# Claude 작업 전후 변경 파일을 비교할 때 건너뛸 경로
SNAPSHOT_SKIP_DIRS = {".git", "hf_cache", "eval_samples", "__pycache__"}
SNAPSHOT_SKIP_PATHS = {"agent/runs", "agent/archive"}


class AgentError(Exception):
    pass


# --------------------------------------------------
# 공통 유틸
# --------------------------------------------------

def now():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def banner(text):
    print("\n==========================================")
    print(text)
    print("==========================================\n", flush=True)


def read(path, default=""):
    return path.read_text(encoding="utf-8") if path.exists() else default


def save(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def log(title, text):
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(f"\n\n## {title} — {now()}\n\n{text}\n")


def ask(prompt):
    """사람 입력. stdin이 없으면(nohup 등) None."""
    try:
        return input(prompt).strip()
    except EOFError:
        return None


def agent_env(gpus):
    env = os.environ.copy()
    env["PATH"] = f"{CONDA_ENV / 'bin'}{os.pathsep}{env.get('PATH', '')}"
    env["CONDA_PREFIX"] = str(CONDA_ENV)
    env["CONDA_DEFAULT_ENV"] = "medgemma"
    env["PYTHONNOUSERSITE"] = "1"
    env["HF_HOME"] = str(HF_HOME)
    if gpus is not None:
        env["CUDA_VISIBLE_DEVICES"] = gpus
    # API 키가 있으면 Claude Code가 구독 대신 API 과금으로 동작한다.
    env.pop("ANTHROPIC_API_KEY", None)
    return env


def run_streaming(cmd, log_path, timeout, env, on_line):
    """명령을 실행하며 출력을 on_line으로 넘기고 log_path에 그대로 저장한다."""
    timed_out = threading.Event()

    with log_path.open("w", encoding="utf-8") as log_f:
        proc = subprocess.Popen(
            cmd,
            cwd=PROJECT_DIR,
            env=env,
            text=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=1,
        )

        def kill():
            timed_out.set()
            proc.kill()

        timer = threading.Timer(timeout, kill)
        timer.start()
        try:
            for line in proc.stdout:
                log_f.write(line)
                log_f.flush()
                on_line(line)
            proc.wait()
        except KeyboardInterrupt:
            proc.kill()
            proc.wait()
            raise
        finally:
            timer.cancel()

    if timed_out.is_set():
        raise AgentError(f"{cmd[0]} 시간 초과 ({timeout}s). 로그: {log_path}")
    if proc.returncode != 0:
        raise AgentError(f"{cmd[0]} 종료 코드 {proc.returncode}. 로그: {log_path}")


# --------------------------------------------------
# 에이전트 호출
# --------------------------------------------------

GPT_TIERS = ["deep", "normal", "light"]
CLAUDE_TIERS = ["creative", "heavy", "light"]
# Claude 작업 등급 → 그 결과를 검토할 GPT 리뷰 등급
REVIEW_TIER_FOR_CLAUDE = {"creative": "deep", "heavy": "normal", "light": "light"}


def tier_spec(agent, tier):
    return json.loads(read(TIERS_FILE))[agent][tier]


def run_codex(args, prompt, out_file, log_path, tier, schema=None):
    spec = tier_spec("gpt", tier)
    print(f"GPT 등급: {tier} ({spec['model']}, effort={spec['effort']})\n", flush=True)
    cmd = [
        "codex", "exec",
        "-s", "read-only",
        "-m", spec["model"],
        "-c", f'model_reasoning_effort="{spec["effort"]}"',
        "-o", str(out_file),
    ]
    if schema:
        cmd += ["--output-schema", str(schema)]
    cmd.append(prompt)

    out_file.unlink(missing_ok=True)
    run_streaming(
        cmd, log_path, args.gpt_timeout, agent_env(args.gpus),
        on_line=lambda line: print(f"  [gpt] {line}", end="", flush=True),
    )

    text = read(out_file).strip()
    if not text:
        raise AgentError(f"Codex 출력이 비어 있음. 로그: {log_path}")
    return text


def summarize_tool_input(name, tool_input):
    if name == "Bash":
        return tool_input.get("command", "")
    for key in ("file_path", "path", "pattern", "url"):
        if key in tool_input:
            return str(tool_input[key])
    return json.dumps(tool_input, ensure_ascii=False)


def run_claude(args, prompt, log_path, tier):
    """Claude를 stream-json으로 실행해 진행 상황을 보여주고 최종 result 이벤트를 반환한다."""
    spec = tier_spec("claude", tier)
    print(f"Claude 등급: {tier} ({spec['model']}, effort={spec['effort']})\n", flush=True)
    cmd = [
        "claude", "-p",
        "--permission-mode", "acceptEdits",
        "--output-format", "stream-json", "--verbose",
        "--model", spec["model"],
        "--effort", spec["effort"],
        "--append-system-prompt-file", str(PROMPT_DIR / "claude_engineer.md"),
        # 연구 에이전트 전용 권한. .claude/settings.json에 두면 대화형 세션까지 막힌다.
        "--settings", str(AGENT_DIR / "claude_settings.json"),
        prompt,
    ]

    result = {}

    def on_line(line):
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            print(f"  [claude] {line}", end="", flush=True)
            return

        if event.get("type") == "assistant":
            for block in event.get("message", {}).get("content", []):
                if block.get("type") == "text" and block.get("text", "").strip():
                    text = block["text"].strip().replace("\n", " ")
                    print(f"  [claude] {text[:300]}", flush=True)
                elif block.get("type") == "tool_use":
                    detail = summarize_tool_input(block.get("name"), block.get("input", {}))
                    print(f"  [claude:{block.get('name')}] {detail[:300]}", flush=True)
        elif event.get("type") == "result":
            result.update(event)

    run_streaming(cmd, log_path, args.claude_timeout, agent_env(args.gpus), on_line)

    if not result:
        raise AgentError(f"Claude result 이벤트 없음. 로그: {log_path}")
    return result


# --------------------------------------------------
# 파일 변경 추적 (gitignore와 무관하게 Claude가 바꾼 파일을 잡는다)
# --------------------------------------------------

def snapshot():
    files = {}
    for root, dirs, names in os.walk(PROJECT_DIR):
        rel_root = Path(root).relative_to(PROJECT_DIR)
        dirs[:] = [
            d for d in dirs
            if d not in SNAPSHOT_SKIP_DIRS
            and (rel_root / d).as_posix() not in SNAPSHOT_SKIP_PATHS
        ]
        for name in names:
            path = Path(root) / name
            try:
                st = path.stat()
            except OSError:
                continue
            files[(rel_root / name).as_posix()] = [st.st_mtime_ns, st.st_size]
    return files


def diff_snapshots(before, after):
    lines = []
    for path in sorted(set(before) | set(after)):
        if path not in before:
            lines.append(f"A {path}")
        elif path not in after:
            lines.append(f"D {path}")
        elif before[path] != after[path]:
            lines.append(f"M {path}")
    return "\n".join(lines)


def git(*git_args):
    result = subprocess.run(
        ["git", *git_args], cwd=PROJECT_DIR, text=True, capture_output=True
    )
    return result.returncode, result.stdout


# --------------------------------------------------
# 반복 상태
# --------------------------------------------------

def iter_dir(n):
    return RUNS_DIR / f"iter_{n:03d}"


def existing_iterations():
    if not RUNS_DIR.exists():
        return []
    return sorted(
        int(p.name.split("_")[1])
        for p in RUNS_DIR.glob("iter_*")
        if p.is_dir() and p.name.split("_")[1].isdigit()
    )


def load_review(n):
    path = iter_dir(n) / "review.json"
    return json.loads(read(path)) if path.exists() else None


def tiers_used(n):
    return json.loads(read(iter_dir(n) / "tiers_used.json", "{}"))


def record_tier(n, step, tier):
    used = tiers_used(n)
    used[step] = tier
    save(iter_dir(n) / "tiers_used.json", json.dumps(used, indent=2))


def plan_tier(args, n):
    if args.gpt_tier:
        return args.gpt_tier
    prev = load_review(n - 1) if n > 1 else None
    return prev.get("next_plan_tier", "deep") if prev else "deep"


def claude_tier(args, n):
    if args.claude_tier:
        return args.claude_tier
    d = iter_dir(n)
    override = read(d / "claude_tier_override.txt").strip()
    return override or json.loads(read(d / "plan.json"))["claude_tier"]


def review_tier(args, n):
    if args.gpt_tier:
        return args.gpt_tier
    return REVIEW_TIER_FOR_CLAUDE[tiers_used(n).get("claude", "heavy")]


def current_iteration():
    """완료되지 않은 반복이 있으면 그 번호, 없으면 다음 번호."""
    iters = existing_iterations()
    if not iters:
        return 1
    last = iters[-1]
    return last if load_review(last) is None else last + 1


def rebuild_index():
    lines = ["# Research Index", ""]
    for n in existing_iterations():
        review = load_review(n)
        if review is None:
            lines.append(f"- iter_{n:03d} [진행 중]")
            continue
        used = tiers_used(n)
        tiers = "/".join(used.get(k, "?") for k in ("plan", "claude", "review"))
        line = f"- iter_{n:03d} [{review['verdict']}] ({tiers}) {review['one_line_summary']}"
        if review.get("next_task"):
            line += f" → 다음: {review['next_task']}"
        lines.append(line)
    save(INDEX_FILE, "\n".join(lines) + "\n")


# --------------------------------------------------
# 단계
# --------------------------------------------------

def step_plan(args, goal, n):
    d = iter_dir(n)
    banner(f"[iter_{n:03d} · 1/3] GPT가 연구 계획을 작성합니다.")

    prev = load_review(n - 1) if n > 1 else None
    if prev:
        prev_text = (
            f"파일: agent/runs/iter_{n - 1:03d}/review.md (필요하면 직접 열어 읽어라)\n"
            f"verdict: {prev['verdict']}\n"
            f"next_task: {prev['next_task']}\n"
            f"reason: {prev['reason']}"
        )
    elif LEGACY_REVIEW_FILE.exists():
        prev_text = "파일: agent/GPT_REVIEW.md (자동 루프 도입 전 마지막 수동 리뷰. 먼저 읽어라)"
    else:
        prev_text = "없음 (첫 반복)"

    prompt = f"""{read(PROMPT_DIR / "gpt_plan.md")}

=== 이번 반복 ===
iter_{n:03d}

=== 연구 목표 ===
{goal}

=== 지금까지의 반복 요약 (agent/INDEX.md) ===
{read(INDEX_FILE, "없음")}

=== 직전 리뷰 ===
{prev_text}

=== 사람의 추가 지시 ===
{read(d / "human_to_gpt.md", "없음")}
"""
    tier = plan_tier(args, n)
    raw = run_codex(
        args, prompt, d / "plan.json", d / "plan_codex.log", tier,
        schema=PROMPT_DIR / "plan_schema.json",
    )
    try:
        plan = json.loads(raw)
    except json.JSONDecodeError as e:
        raise AgentError(f"계획 JSON 파싱 실패: {e}. 파일: {d / 'plan.json'}")
    record_tier(n, "plan", tier)
    # plan.md가 있으면 계획 단계는 완료로 본다 (마지막에 저장)
    save(d / "plan.md", plan["plan_markdown"])
    log(f"iter_{n:03d} GPT PLAN [claude: {plan['claude_tier']}]", plan["plan_markdown"])
    print("\n" + plan["plan_markdown"])
    print(f"\nClaude 등급 제안: {plan['claude_tier']} — {plan['tier_reason']}")


def step_checkpoint(args, n):
    """계획을 Claude에 넘기기 전 사람 확인. False면 종료."""
    d = iter_dir(n)
    if args.auto:
        return True

    while True:
        tier = claude_tier(args, n)
        banner("사용자 확인")
        print(f"계획: {d / 'plan.md'}")
        print(f"Claude 등급: {tier} {tier_spec('claude', tier)}\n")
        print("ENTER : 그대로 Claude에게 전달")
        print("f     : 추가 지시 입력")
        print(f"t     : Claude 등급 바꾸기 ({' / '.join(CLAUDE_TIERS)})")
        print("a     : 이후 확인 없이 자동 진행")
        print("q     : 종료 (다시 실행하면 여기서 이어짐)")

        choice = ask("> ")
        if choice is None:
            return False
        choice = choice.lower()
        if choice == "q":
            return False
        if choice == "t":
            if args.claude_tier:
                print("--claude-tier로 고정되어 있어 바꿀 수 없습니다.")
            else:
                picked = (ask(f"등급 입력 ({' / '.join(CLAUDE_TIERS)}): ") or "").lower()
                if picked in CLAUDE_TIERS:
                    save(d / "claude_tier_override.txt", picked)
                else:
                    print("알 수 없는 등급입니다.")
            continue
        if choice == "a":
            args.auto = True
        elif choice == "f":
            feedback = ask("Claude에게 줄 추가 지시:\n> ") or ""
            if feedback:
                save(d / "human_to_claude.md", feedback)
                log(f"iter_{n:03d} USER FEEDBACK", feedback)
        return True


def step_claude(args, goal, n):
    d = iter_dir(n)
    banner(f"[iter_{n:03d} · 2/3] Claude가 구현/실험합니다.")

    # 중단 후 재실행해도 첫 시도 이전 상태와 비교하도록 스냅샷은 한 번만 찍는다.
    snap_file = d / "snapshot_before.json"
    if not snap_file.exists():
        save(snap_file, json.dumps(snapshot()))
    _, head = git("rev-parse", "HEAD")
    save(d / "base_commit.txt", head.strip())

    prompt = f"""이번 반복: iter_{n:03d}

=== 연구 목표 ===
{goal}

=== GPT 계획 ===
agent/runs/iter_{n:03d}/plan.md 를 먼저 읽고 그 계획을 구현/실행하라.

=== 사용자 추가 지시 ===
{read(d / "human_to_claude.md", "없음")}
"""
    tier = claude_tier(args, n)
    record_tier(n, "claude", tier)
    result = run_claude(args, prompt, d / "claude_stream.jsonl", tier)

    report = result.get("result", "").strip()
    denials = result.get("permission_denials") or []
    if denials:
        report += "\n\n# [orchestrator] 권한 거부된 도구 호출\n"
        for item in denials:
            detail = summarize_tool_input(item.get("tool_name"), item.get("tool_input", {}))
            report += f"- {item.get('tool_name')}: {detail}\n"

    changed = diff_snapshots(json.loads(read(snap_file)), snapshot())
    save(d / "changed_files.txt", changed + "\n")
    _, patch = git("diff", "--", ".", ":!agent")
    save(d / "changes.patch", patch)
    save(d / "claude_meta.json", json.dumps({
        key: result.get(key)
        for key in ("session_id", "is_error", "num_turns", "duration_ms", "total_cost_usd")
    }, indent=2))
    save(d / "claude_report.md", report)
    log(f"iter_{n:03d} CLAUDE REPORT", report)
    print("\n" + report)

    if result.get("is_error"):
        raise AgentError(f"Claude가 오류로 종료됨. 로그: {d / 'claude_stream.jsonl'}")


def step_review(args, goal, n):
    d = iter_dir(n)
    banner(f"[iter_{n:03d} · 3/3] GPT가 결과를 리뷰합니다.")

    changed = read(d / "changed_files.txt").strip().splitlines()
    changed_text = "\n".join(changed[:200]) or "없음"
    if len(changed) > 200:
        changed_text += f"\n... 외 {len(changed) - 200}개 (전체: agent/runs/iter_{n:03d}/changed_files.txt)"

    prompt = f"""{read(PROMPT_DIR / "gpt_review.md")}

=== 이번 반복 ===
iter_{n:03d}

=== 연구 목표 ===
{goal}

=== 검토 자료 (직접 열어 확인하라) ===
- 계획: agent/runs/iter_{n:03d}/plan.md
- Claude 보고서: agent/runs/iter_{n:03d}/claude_report.md
- Claude 도구 호출 전체 기록: agent/runs/iter_{n:03d}/claude_stream.jsonl
- git 추적 파일 diff: agent/runs/iter_{n:03d}/changes.patch

=== 이번 반복에서 바뀐 파일 (A 추가 / M 수정 / D 삭제) ===
{changed_text}
"""
    tier = review_tier(args, n)
    raw = run_codex(
        args, prompt, d / "review.raw.json", d / "review_codex.log", tier,
        schema=PROMPT_DIR / "review_schema.json",
    )
    record_tier(n, "review", tier)
    try:
        review = json.loads(raw)
    except json.JSONDecodeError as e:
        raise AgentError(f"리뷰 JSON 파싱 실패: {e}. 파일: {d / 'review.raw.json'}")

    save(d / "review.md", review["review_markdown"])
    # review.json이 있으면 이 반복은 완료로 본다 (마지막에 저장)
    save(d / "review.json", json.dumps(review, ensure_ascii=False, indent=2))
    log(f"iter_{n:03d} GPT REVIEW [{review['verdict']}]", review["review_markdown"])
    rebuild_index()

    print("\n" + review["review_markdown"])
    print(f"\nverdict  : {review['verdict']}")
    print(f"summary  : {review['one_line_summary']}")
    print(f"next_task: {review['next_task']}")
    print(f"다음 계획 등급: {review['next_plan_tier']}")
    return review


def step_commit(n, review):
    git("add", "-A")
    code, _ = git("diff", "--cached", "--quiet")
    if code == 0:
        print("커밋할 변경 없음.")
        return
    message = f"research iter_{n:03d} [{review['verdict']}]: {review['one_line_summary']}"
    code, out = git("commit", "-m", message)
    print(out if code == 0 else f"[WARN] git commit 실패 (종료 코드 {code})")


def handle_needs_human(review, n):
    """NEEDS_HUMAN 처리. False면 종료."""
    banner("사람의 결정이 필요합니다")
    print(review["reason"])
    print("\nENTER : GPT 제안(next_task)대로 계속")
    print("f     : 다음 계획에 반영할 지시 입력 후 계속")
    print("q     : 종료")

    choice = ask("> ")
    if choice is None or choice.lower() == "q":
        return False
    if choice.lower() == "f":
        note = ask("다음 계획에 반영할 지시:\n> ") or ""
        if note:
            save(iter_dir(n + 1) / "human_to_gpt.md", note)
            log(f"iter_{n + 1:03d} HUMAN NOTE", note)
    return True


# --------------------------------------------------
# main
# --------------------------------------------------

def parse_args():
    p = argparse.ArgumentParser(description="GPT(Codex) ↔ Claude Code 자동 연구 루프")
    p.add_argument("--max-iters", type=int, default=3, help="이번 실행에서 진행할 최대 반복 수")
    p.add_argument("--auto", action="store_true", help="계획 확인 없이 진행 (NEEDS_HUMAN이면 멈춤)")
    p.add_argument("--goal", help="연구 목표 지정 (기존 반복이 있으면 --reset 필요)")
    p.add_argument("--reset", action="store_true", help="기존 runs/와 GOAL을 archive로 옮기고 새로 시작")
    p.add_argument("--gpus", help="Claude 실험에 보일 GPU (CUDA_VISIBLE_DEVICES), 예: 1 또는 0,1")
    p.add_argument("--commit", action="store_true", help="반복마다 git commit (main/master에서는 거부)")
    p.add_argument("--gpt-tier", choices=GPT_TIERS, help="GPT 계획/리뷰 등급 고정 (agent/tiers.json)")
    p.add_argument("--claude-tier", choices=CLAUDE_TIERS, help="Claude 등급 고정 (agent/tiers.json)")
    p.add_argument("--gpt-timeout", type=int, default=30 * 60, help="GPT 단계 제한 시간(초)")
    p.add_argument("--claude-timeout", type=int, default=3 * 60 * 60, help="Claude 단계 제한 시간(초)")
    return p.parse_args()


def reset():
    if not RUNS_DIR.exists() and not GOAL_FILE.exists():
        return
    dest = ARCHIVE_DIR / f"runs_{datetime.datetime.now():%Y%m%d_%H%M%S}"
    dest.mkdir(parents=True)
    if RUNS_DIR.exists():
        shutil.move(str(RUNS_DIR), str(dest / "runs"))
    for path in (GOAL_FILE, INDEX_FILE):
        if path.exists():
            shutil.move(str(path), str(dest / path.name))
    print(f"이전 연구를 {dest} 로 옮겼습니다.")


def load_goal(args):
    if args.goal:
        if existing_iterations() and not args.reset:
            sys.exit("기존 반복이 있습니다. 목표를 바꾸려면 --reset을 함께 쓰세요.")
        save(GOAL_FILE, args.goal)
    if not GOAL_FILE.exists():
        goal = ask("\n=== 연구 목표 입력 ===\n이번 연구에서 무엇을 할지 입력하세요:\n> ")
        if not goal:
            sys.exit("연구 목표가 비어 있습니다.")
        save(GOAL_FILE, goal)
    return read(GOAL_FILE).strip()


def main():
    args = parse_args()

    if args.commit:
        _, branch = git("rev-parse", "--abbrev-ref", "HEAD")
        if branch.strip() in ("main", "master"):
            sys.exit(f"--commit은 {branch.strip()} 브랜치에서 쓸 수 없습니다. 연구용 브랜치를 만드세요.")
    if not (CONDA_ENV / "bin" / "python").exists():
        sys.exit(f"conda env를 찾을 수 없습니다: {CONDA_ENV}")

    if args.reset:
        reset()
    goal = load_goal(args)
    RUNS_DIR.mkdir(parents=True, exist_ok=True)

    banner("RESEARCH GOAL")
    print(goal)

    n = current_iteration()
    if n > 1 and load_review(n - 1) and load_review(n - 1)["verdict"] == "DONE":
        print("\n직전 반복에서 DONE 판정이 났습니다. 이어가려면 목표를 바꾸거나(--reset --goal) 계속하세요.")
        if args.auto or (ask("계속할까요? [y/N] ") or "").lower() != "y":
            return

    for _ in range(args.max_iters):
        n = current_iteration()
        d = iter_dir(n)
        d.mkdir(parents=True, exist_ok=True)

        if not (d / "plan.md").exists():
            step_plan(args, goal, n)
        if not (d / "claude_report.md").exists():
            if not step_checkpoint(args, n):
                print("종료합니다.")
                return
            step_claude(args, goal, n)
        review = step_review(args, goal, n)

        if args.commit:
            step_commit(n, review)

        if review["verdict"] == "DONE":
            banner("연구 목표 완료 (DONE)")
            break
        if review["verdict"] == "NEEDS_HUMAN" and not handle_needs_human(review, n):
            print("종료합니다. 다시 실행하면 다음 반복부터 진행합니다.")
            return

    banner("루프 종료")
    print(f"요약: {INDEX_FILE}")
    print(f"기록: {RUNS_DIR}")


if __name__ == "__main__":
    try:
        main()
    except AgentError as e:
        print(f"\n[ERROR] {e}")
        print("다시 실행하면 완료되지 않은 단계부터 이어서 진행합니다.")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n중단됨. 다시 실행하면 완료되지 않은 단계부터 이어서 진행합니다.")
        sys.exit(130)
