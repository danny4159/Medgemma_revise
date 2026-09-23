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

GPT 리뷰는 계획의 review_mode가 full일 때만 한다. skip이어도 Claude의 SELF_CHECK가
PASS가 아니거나 권한 거부가 있으면 리뷰한다. 리뷰를 건너뛴 반복은 다음 계획 단계에서
GPT가 Claude 보고서를 직접 읽고 확인한다.

자동화 정도 (--autonomy):
    manual : 매 반복 계획을 사람이 확인
    smart  : (기본) 계획이 ask_human이거나 규칙 위반일 때만 확인, 나머지는 1순위 대안으로 진행
    full   : 계획 확인 없이 진행 (--auto와 같음)
    어떤 모드든 리뷰가 NEEDS_HUMAN이면 사람에게 묻는다.

접근법 관리: 계획은 대안 순위(alternatives)와 이번 approach를 내고, 리뷰는 approach를
success / improve / abandon으로 판정한다. 같은 approach는 --max-attempts번까지만 시도하고
(마지막 시도는 GPT 리뷰 강제), 넘으면 다음 대안으로 넘어가거나 사람에게 묻는다.

코드 버전 관리: Claude는 별도 git worktree(<프로젝트>_research)에서 작업한다.
접근법마다 research/<approach_id> 브랜치를 쓰고, 직전 접근법이 success면 그 위에서,
아니면 그 접근법이 시작한 지점으로 돌아가 새 브랜치를 만든다. 커밋은 GPT 리뷰가
commit_worthy로 판단한 경우에만 한다. 버리는 접근법의 미커밋 작업은 git stash로 보관한다.
main 폴더(오케스트레이터, agent/ 기록, 데이터, 결과)는 브랜치와 상관없이 그대로다.

논문 추천: GPT 리뷰는 실제 결과로 가능성이 분명해진 방향에 한해 드물게 논문 1편을 추천한다.
링크가 열리고 중복이 아니면 agent/PAPERS.md에 쌓고 Telegram으로 알린다.

산출물은 agent/runs/iter_NNN/ 에 저장된다. 중간에 끊겨도 다시 실행하면
완료되지 않은 단계부터 이어서 진행한다.

사용 예:
    python orchestrator.py                     # smart: 애매할 때만 확인
    python orchestrator.py --autonomy manual   # 매 반복 계획을 확인
    python orchestrator.py --auto --max-iters 5
    python orchestrator.py --reset --goal "새 연구 목표"
    python orchestrator.py --gpus 1            # Claude가 GPU 1만 보이게
    python orchestrator.py --gpt-tier normal --claude-tier light   # 등급 강제
"""

from pathlib import Path
import argparse
import datetime
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import urllib.request

from notifier import Human

PROJECT_DIR = Path(__file__).resolve().parent
AGENT_DIR = PROJECT_DIR / "agent"
PROMPT_DIR = AGENT_DIR / "prompts"
RUNS_DIR = AGENT_DIR / "runs"
ARCHIVE_DIR = AGENT_DIR / "archive"

GOAL_FILE = AGENT_DIR / "GOAL.md"
INDEX_FILE = AGENT_DIR / "INDEX.md"
PAPERS_FILE = AGENT_DIR / "PAPERS.md"
LOG_FILE = AGENT_DIR / "RESEARCH_LOG.md"
TIERS_FILE = AGENT_DIR / "tiers.json"
# runs/ 도입 전 수동 실행의 마지막 리뷰. 첫 반복 계획의 참고 자료로 쓴다.
LEGACY_REVIEW_FILE = AGENT_DIR / "GPT_REVIEW.md"
# Telegram 봇 설정 (TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID). git에 올리지 않는다.
NOTIFY_ENV_FILE = AGENT_DIR / ".notify.env"

# Claude가 코드를 고치는 git worktree. 브랜치를 바꿔도 main 폴더(기록·데이터)는 그대로다.
RESEARCH_DIR = PROJECT_DIR.parent / f"{PROJECT_DIR.name}_research"
BASE_BRANCH = "research/base"
# worktree에서 main 폴더를 가리키는 링크 (데이터·결과는 브랜치와 무관하게 공유)
SHARED_LINKS = ("eval_samples", "hf_cache", "eval_results")
# 커밋에서 제외할 파일 크기
MAX_COMMIT_FILE_BYTES = 5 * 1024 * 1024

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


HUMAN = None  # main()에서 만든다


def ask(prompt, telegram_text=None):
    """사람 입력. telegram_text가 있으면 Telegram 답장도 받는다. 받을 방법이 없으면 None."""
    return HUMAN.ask(prompt, telegram_text)


def notify(text):
    if HUMAN is not None:
        HUMAN.notify(text)


def split_reply(reply):
    """'f 추가 지시' → ('f', '추가 지시'). ENTER/ok는 ('', '')."""
    cmd, _, rest = reply.strip().partition(" ")
    cmd = cmd.lower()
    if cmd in ("ok", "go", "ㅇㅋ", "계속"):
        cmd = ""
    return cmd, rest.strip()


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


def run_streaming(cmd, log_path, timeout, env, on_line, cwd=PROJECT_DIR):
    """명령을 실행하며 출력을 on_line으로 넘기고 log_path에 그대로 저장한다."""
    timed_out = threading.Event()

    with log_path.open("w", encoding="utf-8") as log_f:
        proc = subprocess.Popen(
            cmd,
            cwd=cwd,
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
# 같은 접근법 최대 시도 횟수 (--max-attempts로 덮어씀)
MAX_ATTEMPTS = 3
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
        # 선행 연구 확인과 논문 추천을 위한 웹 검색
        "-c", 'web_search="live"',
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
        # 작업 디렉터리는 worktree. main 폴더는 결과 저장(eval_results)과 계획 읽기용
        "--add-dir", str(PROJECT_DIR),
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

    run_streaming(cmd, log_path, args.claude_timeout, agent_env(args.gpus), on_line, cwd=RESEARCH_DIR)

    if not result:
        raise AgentError(f"Claude result 이벤트 없음. 로그: {log_path}")
    return result


# --------------------------------------------------
# 파일 변경 추적 (gitignore와 무관하게 Claude가 바꾼 파일을 잡는다)
# --------------------------------------------------

def snapshot():
    """Claude가 건드릴 수 있는 곳의 파일 상태: worktree(코드) + main의 eval_results(결과)."""
    files = {}
    for base, label in ((RESEARCH_DIR, ""), (PROJECT_DIR / "eval_results", "eval_results")):
        for root, dirs, names in os.walk(base):
            rel_root = Path(label) / Path(root).relative_to(base)
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


def git(*git_args, cwd=None):
    """(종료 코드, 출력). 실패하면 출력 대신 에러 메시지."""
    result = subprocess.run(["git", *git_args], cwd=cwd or PROJECT_DIR, text=True, capture_output=True)
    return result.returncode, result.stdout if result.returncode == 0 else result.stderr.strip()


def wgit(*git_args):
    """연구 worktree에서 git 실행."""
    return git(*git_args, cwd=RESEARCH_DIR)


def current_branch():
    return wgit("rev-parse", "--abbrev-ref", "HEAD")[1].strip()


def ensure_worktree():
    """연구 코드용 worktree(research/base)를 준비한다. 이미 있으면 그대로 둔다.

    main은 scripts/, docs/를 추적하지 않으므로, research/base에서만 추적하도록 바꾸고
    현재 main 폴더의 scripts/, docs/를 기준 커밋으로 남긴다.
    """
    if (RESEARCH_DIR / ".git").exists():
        return
    exists = git("show-ref", "--verify", "--quiet", f"refs/heads/{BASE_BRANCH}")[0] == 0
    add = ["worktree", "add", str(RESEARCH_DIR), BASE_BRANCH] if exists else \
          ["worktree", "add", "-b", BASE_BRANCH, str(RESEARCH_DIR), "HEAD"]
    code, out = git(*add)
    if code:
        raise AgentError(f"worktree 생성 실패: {out}")
    print(f"연구 worktree 생성: {RESEARCH_DIR} ({BASE_BRANCH})")

    gitignore = RESEARCH_DIR / ".gitignore"
    lines = [line for line in read(gitignore).splitlines() if line.strip() not in ("scripts/", "docs/")]
    lines += ["", "# main 폴더의 데이터·결과를 가리키는 링크 (브랜치와 무관하게 공유)"]
    lines += [f"/{name}" for name in SHARED_LINKS]
    save(gitignore, "\n".join(lines) + "\n")

    for name in ("scripts", "docs"):
        if (PROJECT_DIR / name).exists() and not (RESEARCH_DIR / name).exists():
            shutil.copytree(PROJECT_DIR / name, RESEARCH_DIR / name,
                            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    for name in SHARED_LINKS:
        link = RESEARCH_DIR / name
        if not link.exists() and not link.is_symlink():
            link.symlink_to(PROJECT_DIR / name)

    wgit("add", "-A")
    if wgit("diff", "--cached", "--quiet")[0] != 0:
        code, out = wgit("commit", "-m", "Research baseline: track existing scripts and docs")
        if code:
            raise AgentError(f"기준 커밋 실패: {out}")


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


def parse_trailer(report, key):
    """보고서 끝의 'KEY: 값' 줄을 읽는다. 여러 개면 마지막 것."""
    matches = re.findall(rf"^\s*{key}:\s*(.+?)\s*$", report, re.MULTILINE)
    return matches[-1] if matches else ""


def review_decision(args, n):
    """(GPT 리뷰 여부, 이유). 계획이 skip이어도 Claude 결과에 문제 신호가 있으면 리뷰한다."""
    d = iter_dir(n)
    if args.always_review:
        return True, "--always-review 지정"
    entry = approach_ledger(upto=n).get(approach_key(load_plan(n)))
    if entry and entry["attempts"] >= MAX_ATTEMPTS:
        return True, f"'{entry['name']}' {entry['attempts']}번째 시도라 계속/포기 판단 필요"
    override = read(d / "review_mode_override.txt").strip()
    mode = override or json.loads(read(d / "plan.json")).get("review_mode", "full")
    if mode == "full":
        return True, "사람이 full 지정" if override else "계획에서 full 지정"
    if parse_trailer(read(d / "claude_report.md"), "SELF_CHECK").upper() != "PASS":
        return True, "skip이었지만 Claude 자체 검증이 PASS가 아님"
    if json.loads(read(d / "claude_meta.json", "{}")).get("permission_denials"):
        return True, "skip이었지만 권한 거부된 명령이 있음"
    return False, ("사람이 skip 지정" if override else "계획에서 skip 지정") + ", Claude 자체 검증 PASS"


def load_plan(n):
    path = iter_dir(n) / "plan.json"
    return json.loads(read(path)) if path.exists() else None


def load_json(path):
    return json.loads(read(path)) if path.exists() else None


def approach_key(plan):
    """접근법 id (git 브랜치 이름에 쓸 수 있는 형태)."""
    raw = (plan or {}).get("approach_id") or (plan or {}).get("approach") or ""
    key = re.sub(r"[^a-z0-9-]+", "-", raw.lower()).strip("-")[:40]
    return key or "unnamed"


def approach_branch(key):
    return f"research/{key}"


def approach_ledger(upto=None):
    """접근법별 시도 기록. 반복 파일에서 매번 다시 계산한다.

    {approach_id: {"name", "attempts", "iters", "status", "branch", "base", "commits"}}
    """
    ledger = {}
    for n in existing_iterations():
        if upto is not None and n > upto:
            break
        plan = load_plan(n)
        if not plan:
            continue
        key = approach_key(plan)
        entry = ledger.setdefault(key, {
            "name": plan.get("approach", key), "attempts": 0, "iters": [], "status": "진행 중",
            "branch": approach_branch(key), "base": None, "commits": [],
        })
        git_info = load_json(iter_dir(n) / "git.json") or {}
        if git_info.get("created") and entry["base"] is None:
            entry["base"] = git_info.get("base")
        commit = load_json(iter_dir(n) / "commit.json")
        if commit:
            entry["commits"].append(commit["sha"])
        entry["attempts"] += 1
        entry["iters"].append(n)
        review = load_review(n)
        if review:
            entry["status"] = review.get("approach_status") or "미검토"
    return ledger


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
        approach = (load_plan(n) or {}).get("approach", "?")
        status = review.get("approach_status") or ("미검토" if review.get("skipped") else "?")
        commit = load_json(iter_dir(n) / "commit.json")
        committed = f" 💾{commit['sha']}" if commit else ""
        line = (
            f"- iter_{n:03d} [{review['verdict']}] ({tiers}) "
            f"<{approach}: {status}>{committed} {review['one_line_summary']}"
        )
        if review.get("next_task"):
            line += f" → 다음: {review['next_task']}"
        lines.append(line)

    ledger = approach_ledger()
    if ledger:
        lines += ["", f"## 접근법 기록 (같은 접근법 최대 {MAX_ATTEMPTS}회)", ""]
        for entry in ledger.values():
            iters = ", ".join(f"iter_{i:03d}" for i in entry["iters"])
            commits = ", ".join(entry["commits"]) or "없음"
            lines.append(
                f"- {entry['name']} [{entry['branch']}]: {entry['attempts']}회 ({iters}), "
                f"최근 판정: {entry['status']}, 커밋: {commits}"
            )
        lines += ["", f"현재 연구 브랜치: {current_branch()} (코드 위치: {RESEARCH_DIR})"]
        last_plan = load_plan(existing_iterations()[-1]) or {}
        if last_plan.get("alternatives"):
            lines += ["", "### 최근 계획의 대안 순위", ""]
            lines += [f"{i}. {alt}" for i, alt in enumerate(last_plan["alternatives"], 1)]
    save(INDEX_FILE, "\n".join(lines) + "\n")


# --------------------------------------------------
# 단계
# --------------------------------------------------

def step_plan(args, goal, n):
    d = iter_dir(n)
    banner(f"[iter_{n:03d} · 1/3] GPT가 연구 계획을 작성합니다.")

    prev = load_review(n - 1) if n > 1 else None
    if prev and prev.get("skipped"):
        prev_text = (
            f"직전 반복(iter_{n - 1:03d})은 GPT 리뷰를 생략했다 ({prev['reason']}).\n"
            f"먼저 agent/runs/iter_{n - 1:03d}/claude_report.md 와 changed_files.txt 를 직접 읽고\n"
            f"결과가 믿을 만한지 확인한 뒤 계획하라.\n"
            f"Claude 요약: {prev['one_line_summary']}"
        )
    elif prev:
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

=== 코드 위치 ===
연구 코드는 {RESEARCH_DIR} (git worktree, 현재 브랜치 {current_branch()})에 있다.
main 폴더의 scripts/는 옛 사본이니 보지 마라. 데이터·결과는 main 폴더의 eval_samples/, eval_results/.

=== 직전 결과 ===
{prev_text}

=== 사람의 추가 지시 ===
{read(d / "human_to_gpt.md", "없음")}

=== 규칙 ===
같은 접근법 최대 시도 횟수: {MAX_ATTEMPTS}
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
    log(f"iter_{n:03d} GPT PLAN [{plan['approach']} / {plan['decision']}]", plan["plan_markdown"])
    print("\n" + plan["plan_markdown"])
    print("\n대안 순위:")
    for i, alt in enumerate(plan["alternatives"], 1):
        print(f"  {i}. {alt}")
    print(f"결정: {plan['decision']} — {plan['decision_reason']}")
    print(f"\nClaude 등급 제안: {plan['claude_tier']} — {plan['tier_reason']}")
    print(f"GPT 리뷰: {plan['review_mode']} — {plan['review_reason']}")


def plan_concerns(n, plan):
    """계획이 스스로 묻겠다고 했거나 접근법 규칙을 어긴 경우의 이유 목록."""
    concerns = []
    if plan.get("decision") == "ask_human":
        concerns.append(plan.get("decision_reason", ""))
    before = approach_ledger(upto=n - 1).get(approach_key(plan))
    if before and before["status"] == "abandon":
        concerns.append(f"이미 포기(abandon) 판정된 접근법 '{before['name']}'을 다시 고름")
    elif before and before["attempts"] >= MAX_ATTEMPTS and before["status"] != "success":
        concerns.append(f"'{before['name']}'을 이미 {before['attempts']}번 시도함 (최대 {MAX_ATTEMPTS})")
    return concerns


def step_checkpoint(args, n):
    """계획을 Claude에 넘기기 전 확인. 'go' / 'replan' / 'quit'."""
    d = iter_dir(n)
    plan = load_plan(n)
    concerns = plan_concerns(n, plan)
    approach = plan.get("approach", "?")
    attempt = approach_ledger(upto=n).get(approach_key(plan), {}).get("attempts", 1)

    if args.autonomy == "full" or (args.autonomy == "smart" and not concerns):
        print(f"\n자동 진행 ({args.autonomy}): {approach} {attempt}번째 시도")
        notify(
            f"▶ iter_{n:03d} 자동 진행: {approach} ({attempt}번째 시도)\n"
            f"근거: {plan.get('decision_reason', '')}\n"
            f"Claude {claude_tier(args, n)} / 리뷰 {plan.get('review_mode', 'full')}"
        )
        return "go"

    alternatives = plan.get("alternatives", [])
    alt_text = "\n".join(f"{i}. {alt}" for i, alt in enumerate(alternatives, 1))
    while True:
        tier = claude_tier(args, n)
        review_mode = read(d / "review_mode_override.txt").strip() or plan["review_mode"]
        banner("사용자 확인")
        print(f"계획: {d / 'plan.md'}")
        if concerns:
            print("확인이 필요한 이유:")
            for c in concerns:
                print(f"  - {c}")
        print(f"\n대안 순위 (1번이 현재 계획):\n{alt_text}\n")
        print(f"Claude 등급: {tier} {tier_spec('claude', tier)}")
        print(f"GPT 리뷰  : {review_mode}\n")
        print("ENTER / ok / 1 : 현재 계획(1순위)대로 Claude에게 전달")
        print("2, 3, ...      : 해당 대안으로 계획 다시 세우기")
        print("f [지시]       : 추가 지시 후 전달")
        print(f"t [등급]       : Claude 등급 바꾸기 ({' / '.join(CLAUDE_TIERS)})")
        print("r full|skip    : Claude 작업 후 GPT 리뷰 여부 바꾸기")
        print("a              : 이후 확인 없이 자동 진행")
        print("q              : 종료 (다시 실행하면 여기서 이어짐)")

        reasons = "\n".join(f"• {c}" for c in concerns) or "(수동 확인 모드)"
        telegram_text = (
            f"🙋 iter_{n:03d} 계획 확인 필요\n\n"
            f"{reasons}\n\n"
            f"대안 순위 (1번이 현재 계획):\n{alt_text}\n\n"
            f"Claude {tier} / 리뷰 {review_mode}\n\n"
            f"{plan['plan_markdown'][:1200]}\n\n"
            "답장:\n"
            "ok 또는 1 → 1순위로 진행\n"
            "2, 3… → 그 대안으로 계획 다시\n"
            "f 지시내용 → 추가 지시 후 진행\n"
            f"t {'|'.join(CLAUDE_TIERS)} → Claude 등급 변경\n"
            "r full|skip → GPT 리뷰 여부 변경\n"
            "a → 이후 자동 진행\n"
            "q → 종료"
        )
        reply = ask("> ", telegram_text)
        if reply is None:
            return "quit"
        cmd, rest = split_reply(reply)

        if cmd == "q":
            return "quit"
        if cmd.isdigit() and 1 <= int(cmd) <= max(len(alternatives), 1):
            k = int(cmd)
            if k == 1:
                return "go"
            choice = alternatives[k - 1]
            note = f"사용자가 대안 {k}번을 선택했다: {choice}\n이 대안을 approach로 계획을 다시 세워라."
            if rest:
                note += f"\n추가 지시: {rest}"
            earlier = read(d / "human_to_gpt.md").strip()
            save(d / "human_to_gpt.md", f"{earlier}\n\n{note}".strip())
            log(f"iter_{n:03d} USER CHOSE ALTERNATIVE", note)
            # 기존 계획은 기록으로 남기고 다시 계획한다
            for name in ("plan.json", "plan.md"):
                if (d / name).exists():
                    (d / name).rename(d / f"rejected_{now().replace(' ', '_').replace(':', '')}_{name}")
            return "replan"
        if cmd == "t":
            if args.claude_tier:
                print("--claude-tier로 고정되어 있어 바꿀 수 없습니다.")
                continue
            picked = (rest or ask(f"등급 입력 ({' / '.join(CLAUDE_TIERS)}): ") or "").lower()
            if picked in CLAUDE_TIERS:
                save(d / "claude_tier_override.txt", picked)
            else:
                print("알 수 없는 등급입니다.")
            continue
        if cmd == "r":
            picked = (rest or ask("리뷰 여부 입력 (full / skip): ") or "").lower()
            if picked in ("full", "skip"):
                save(d / "review_mode_override.txt", picked)
            else:
                print("full 또는 skip만 가능합니다.")
            continue
        if cmd == "a":
            args.autonomy = "full"
            return "go"
        if cmd == "f":
            feedback = rest or ask("Claude에게 줄 추가 지시:\n> ") or ""
            if feedback:
                save(d / "human_to_claude.md", feedback)
                log(f"iter_{n:03d} USER FEEDBACK", feedback)
            return "go"
        if cmd == "":
            return "go"
        print(f"알 수 없는 입력입니다: {reply}")
        notify(f"알 수 없는 입력입니다: {reply}")


def base_for_new_branch(cur):
    """새 접근법 브랜치의 출발점.

    직전 접근법이 success면 그 위에서 이어가고, 아니면 그 접근법이 시작했던 지점으로 돌아간다.
    """
    if cur == BASE_BRANCH or not cur.startswith("research/"):
        return cur
    entry = approach_ledger().get(cur[len("research/"):])
    if entry and entry["status"] == "success":
        return cur
    return (entry or {}).get("base") or BASE_BRANCH


def ensure_branch(n):
    """이번 반복 접근법의 브랜치로 worktree를 맞춘다. 결과는 git.json에 기록."""
    d = iter_dir(n)
    info = load_json(d / "git.json")
    if info:
        # 재실행: 이미 준비된 브랜치에 있는지만 확인
        if current_branch() != info["branch"]:
            code, out = wgit("checkout", info["branch"])
            if code:
                raise AgentError(f"브랜치 {info['branch']} 복귀 실패: {out}")
        return info

    target = approach_branch(approach_key(load_plan(n)))
    cur = current_branch()
    info = {"branch": target, "from_branch": cur}
    if cur != target:
        if wgit("status", "--porcelain")[1].strip():
            message = f"iter_{n:03d}: {cur}의 미커밋 작업 (접근법 전환 전 보관)"
            code, out = wgit("stash", "push", "-u", "-m", message)
            if code:
                raise AgentError(f"git stash 실패: {out}")
            info["stashed"] = message
            print(f"미커밋 작업을 stash로 보관: {message}")
        if wgit("show-ref", "--verify", "--quiet", f"refs/heads/{target}")[0] == 0:
            code, out = wgit("checkout", target)
        else:
            base_ref = base_for_new_branch(cur)
            info["base_ref"] = base_ref
            info["base"] = wgit("rev-parse", "--short", base_ref)[1].strip()
            info["created"] = True
            code, out = wgit("checkout", "-b", target, base_ref)
        if code:
            raise AgentError(f"브랜치 전환 실패 ({target}): {out}")
    info["head_before"] = wgit("rev-parse", "--short", "HEAD")[1].strip()
    save(d / "git.json", json.dumps(info, ensure_ascii=False, indent=2))

    if info.get("created"):
        print(f"새 브랜치 {target} ← {info['base_ref']} ({info['base']})")
    elif cur != target:
        print(f"브랜치 전환: {cur} → {target}")
    else:
        print(f"브랜치 유지: {target}")
    return info


def step_claude(args, goal, n):
    d = iter_dir(n)
    banner(f"[iter_{n:03d} · 2/3] Claude가 구현/실험합니다.")

    branch = ensure_branch(n)["branch"]
    # 중단 후 재실행해도 첫 시도 이전 상태와 비교하도록 스냅샷은 한 번만 찍는다.
    snap_file = d / "snapshot_before.json"
    if not snap_file.exists():
        save(snap_file, json.dumps(snapshot()))

    prompt = f"""이번 반복: iter_{n:03d}

=== 연구 목표 ===
{goal}

=== GPT 계획 ===
{d / "plan.md"} 를 먼저 읽고 그 계획을 구현/실행하라.

=== 작업 위치 ===
현재 디렉터리는 연구용 git worktree다 (브랜치 {branch}). 코드는 여기서만 만들고 고친다.
eval_samples/, eval_results/, hf_cache/는 main 폴더({PROJECT_DIR})로 연결된 링크다.
기존 스크립트 안의 main 절대경로(데이터·결과)는 그대로 써도 된다.
git 커밋과 브랜치 관리는 orchestrator가 한다.

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
    save(d / "changes.patch", wgit("diff", "HEAD")[1])
    save(d / "claude_meta.json", json.dumps({
        key: result.get(key)
        for key in ("session_id", "is_error", "num_turns", "duration_ms", "total_cost_usd")
    } | {"permission_denials": len(denials)}, indent=2))
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

=== 이번 접근법 ===
{(load_plan(n) or {}).get("approach", "?")} — {approach_ledger(upto=n).get(approach_key(load_plan(n)), {}).get("attempts", 1)}번째 시도 (최대 {MAX_ATTEMPTS})
브랜치: {current_branch()} (코드 위치: {RESEARCH_DIR})

=== 지금까지의 반복 요약과 접근법 기록 (agent/INDEX.md) ===
{read(INDEX_FILE, "없음")}

=== 이미 추천한 논문 (agent/PAPERS.md) ===
{read(PAPERS_FILE, "없음")}

=== 검토 자료 (직접 열어 확인하라) ===
- 계획: agent/runs/iter_{n:03d}/plan.md
- Claude 보고서: agent/runs/iter_{n:03d}/claude_report.md
- Claude 도구 호출 전체 기록: agent/runs/iter_{n:03d}/claude_stream.jsonl
- 코드 변경 diff (마지막 커밋 대비): agent/runs/iter_{n:03d}/changes.patch
- 코드 자체는 {RESEARCH_DIR} 에 있다. main 폴더의 scripts/는 옛 사본이니 보지 마라.

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


def url_opens(url):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status < 400
    except Exception:
        return False


def handle_paper(n, review):
    """리뷰의 논문 추천을 검증해 PAPERS.md에 추가하고 알린다."""
    paper = review.get("paper_recommendation") or {}
    if not paper.get("recommend"):
        return
    d = iter_dir(n)
    url = paper.get("url", "").strip()

    problem = None
    if review.get("approach_status") == "abandon":
        problem = "접근법이 abandon인데 추천함"
    elif not paper.get("title") or not url:
        problem = "제목이나 링크가 없음"
    elif url in read(PAPERS_FILE):
        problem = "이미 추천한 논문"
    elif not url_opens(url):
        problem = "링크가 열리지 않음"
    if problem:
        save(d / "paper_rejected.json", json.dumps({"reason": problem, **paper}, ensure_ascii=False, indent=2))
        print(f"\n논문 추천 무시: {problem} — {paper.get('title', '')}")
        return

    if not PAPERS_FILE.exists():
        save(PAPERS_FILE, "# 읽어볼 논문\n\n읽은 논문은 [ ]를 [x]로 바꿔 두세요.\n")
    entry = (
        f"\n## [ ] {paper['title']} ({paper['authors_year']})\n"
        f"- 링크: {url}\n"
        f"- 추천: iter_{n:03d}, {now()[:10]}\n"
        f"- 지금 하고 있는 것: {paper['current_work']}\n"
        f"- 추천 이유: {paper['why']}\n"
        f"- 읽어볼 부분: {paper['what_to_read']}\n"
    )
    with PAPERS_FILE.open("a", encoding="utf-8") as f:
        f.write(entry)
    log(f"iter_{n:03d} PAPER RECOMMENDATION", entry)
    print(f"\n📚 논문 추천: {paper['title']}")
    notify(
        f"📚 읽어볼 논문 (iter_{n:03d})\n\n"
        f"{paper['title']} ({paper['authors_year']})\n{url}\n\n"
        f"지금 하고 있는 것:\n{paper['current_work']}\n\n"
        f"추천 이유:\n{paper['why']}\n\n"
        f"읽어볼 부분:\n{paper['what_to_read']}"
    )


def step_skip_review(n, reason):
    """GPT 리뷰 없이 반복을 마친다. 확인은 다음 계획 단계의 GPT가 맡는다."""
    d = iter_dir(n)
    banner(f"[iter_{n:03d} · 3/3] GPT 리뷰 생략 — {reason}")

    summary = parse_trailer(read(d / "claude_report.md"), "SUMMARY") or "Claude 작업 완료 (요약 없음)"
    review = {
        "verdict": "CONTINUE",
        "one_line_summary": summary,
        "next_task": "",
        "next_plan_tier": tiers_used(n).get("plan", "normal"),
        "reason": reason,
        "review_markdown": (
            f"# GPT 리뷰 생략\n\n{reason}.\n"
            "다음 반복의 계획 단계에서 GPT가 Claude 보고서를 직접 확인한다.\n"
        ),
        "skipped": True,
    }
    record_tier(n, "review", "skip")
    save(d / "review.md", review["review_markdown"])
    save(d / "review.json", json.dumps(review, ensure_ascii=False, indent=2))
    log(f"iter_{n:03d} GPT REVIEW SKIPPED", reason)
    rebuild_index()
    print(f"summary: {summary}")
    return review


def step_commit(n, review):
    """GPT 리뷰가 commit_worthy로 판단했을 때만 연구 브랜치에 커밋한다."""
    if review.get("skipped") or not review.get("commit_worthy") or review.get("approach_status") == "abandon":
        return
    d = iter_dir(n)
    wgit("add", "-A")
    skipped_large = []
    for path in wgit("diff", "--cached", "--name-only")[1].splitlines():
        full = RESEARCH_DIR / path
        if full.is_file() and full.stat().st_size > MAX_COMMIT_FILE_BYTES:
            wgit("reset", "-q", "--", path)
            skipped_large.append(path)
    if wgit("diff", "--cached", "--quiet")[0] == 0:
        print("커밋할 코드 변경 없음.")
        return

    plan = load_plan(n)
    title = review.get("commit_message") or review["one_line_summary"]
    message = (
        f"[{approach_key(plan)}] {title}\n\n"
        f"iter_{n:03d}, 접근법: {plan.get('approach', '')}\n"
        f"GPT 리뷰({tiers_used(n).get('review', '?')}) 검증: {review.get('approach_status', '')}"
    )
    code, out = wgit("commit", "-m", message)
    if code:
        print(f"[WARN] git commit 실패: {out}")
        notify(f"⚠ iter_{n:03d} git commit 실패: {out[:300]}")
        return

    sha = wgit("rev-parse", "--short", "HEAD")[1].strip()
    branch = current_branch()
    save(d / "commit.json", json.dumps(
        {"sha": sha, "branch": branch, "message": title, "skipped_large_files": skipped_large},
        ensure_ascii=False, indent=2,
    ))
    rebuild_index()
    log(f"iter_{n:03d} GIT COMMIT", f"{sha} ({branch}) {title}")
    print(f"\n💾 커밋 {sha} ({branch}): {title}")
    if skipped_large:
        print(f"   5MB 넘는 파일은 제외: {', '.join(skipped_large)}")
    notify(f"💾 커밋 {sha} ({branch})\n{title}")


def handle_needs_human(review, n):
    """NEEDS_HUMAN 처리. False면 종료."""
    banner("사람의 결정이 필요합니다")
    print(review["reason"])
    print("\nENTER / ok   : GPT 제안(next_task)대로 계속")
    print("f [지시]     : 다음 계획에 반영할 지시 입력 후 계속")
    print("q            : 종료")

    telegram_text = (
        f"🙋 iter_{n:03d} 결정이 필요합니다\n\n"
        f"{review['reason']}\n\n"
        f"이번 결과: {review['one_line_summary']}\n"
        f"GPT 제안: {review['next_task']}\n\n"
        "답장:\n"
        "ok → GPT 제안대로 계속\n"
        "f 지시내용 → 지시 반영해서 계속\n"
        "q → 종료"
    )
    while True:
        reply = ask("> ", telegram_text)
        if reply is None:
            return False
        cmd, rest = split_reply(reply)
        if cmd == "q":
            return False
        if cmd == "f":
            note = rest or ask("다음 계획에 반영할 지시:\n> ") or ""
            if note:
                save(iter_dir(n + 1) / "human_to_gpt.md", note)
                log(f"iter_{n + 1:03d} HUMAN NOTE", note)
            return True
        if cmd == "":
            return True
        print(f"알 수 없는 입력입니다: {reply}")
        notify(f"알 수 없는 입력입니다: {reply}")


# --------------------------------------------------
# main
# --------------------------------------------------

def parse_args():
    p = argparse.ArgumentParser(description="GPT(Codex) ↔ Claude Code 자동 연구 루프")
    p.add_argument("--max-iters", type=int, default=3, help="이번 실행에서 진행할 최대 반복 수")
    p.add_argument("--autonomy", choices=["manual", "smart", "full"], default="smart",
                   help="계획 확인: manual=매번, smart=애매할 때만(기본), full=안 함")
    p.add_argument("--auto", action="store_true", help="--autonomy full과 같음")
    p.add_argument("--max-attempts", type=int, default=MAX_ATTEMPTS, help="같은 접근법 최대 시도 횟수")
    p.add_argument("--goal", help="연구 목표 지정 (기존 반복이 있으면 --reset 필요)")
    p.add_argument("--reset", action="store_true", help="기존 runs/와 GOAL을 archive로 옮기고 새로 시작")
    p.add_argument("--gpus", help="Claude 실험에 보일 GPU (CUDA_VISIBLE_DEVICES), 예: 1 또는 0,1")
    p.add_argument("--gpt-tier", choices=GPT_TIERS, help="GPT 계획/리뷰 등급 고정 (agent/tiers.json)")
    p.add_argument("--claude-tier", choices=CLAUDE_TIERS, help="Claude 등급 고정 (agent/tiers.json)")
    p.add_argument("--gpt-timeout", type=int, default=30 * 60, help="GPT 단계 제한 시간(초)")
    p.add_argument("--claude-timeout", type=int, default=3 * 60 * 60, help="Claude 단계 제한 시간(초)")
    p.add_argument("--always-review", action="store_true", help="계획과 상관없이 매 반복 GPT 리뷰")
    p.add_argument("--no-telegram", action="store_true", help="Telegram 알림/답장 끄기")
    args = p.parse_args()
    if args.auto:
        args.autonomy = "full"
    return args


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
    global HUMAN, MAX_ATTEMPTS
    args = parse_args()
    MAX_ATTEMPTS = args.max_attempts
    HUMAN = Human(None if args.no_telegram else NOTIFY_ENV_FILE)
    if HUMAN.telegram:
        print("Telegram 알림 사용 중 (끄려면 --no-telegram)")

    if not (CONDA_ENV / "bin" / "python").exists():
        sys.exit(f"conda env를 찾을 수 없습니다: {CONDA_ENV}")
    ensure_worktree()

    if args.reset:
        reset()
    goal = load_goal(args)
    RUNS_DIR.mkdir(parents=True, exist_ok=True)

    banner("RESEARCH GOAL")
    print(goal)

    n = current_iteration()
    if n > 1 and load_review(n - 1) and load_review(n - 1)["verdict"] == "DONE":
        print("\n직전 반복에서 DONE 판정이 났습니다. 이어가려면 목표를 바꾸거나(--reset --goal) 계속하세요.")
        if args.autonomy == "full" or (ask("계속할까요? [y/N] ") or "").lower() != "y":
            return

    first_line = goal.splitlines()[0][:200] if goal else ""
    notify(f"▶ 연구 루프 시작 (iter_{current_iteration():03d}부터, 최대 {args.max_iters}회)\n목표: {first_line}")

    completed = 0
    finished = False
    while completed < args.max_iters:
        n = current_iteration()
        d = iter_dir(n)
        d.mkdir(parents=True, exist_ok=True)

        if not (d / "plan.md").exists():
            step_plan(args, goal, n)
        if not (d / "claude_report.md").exists():
            action = step_checkpoint(args, n)
            if action == "quit":
                print("종료합니다.")
                return
            if action == "replan":
                continue
            step_claude(args, goal, n)
        needs_review, reason = review_decision(args, n)
        if needs_review:
            print(f"\nGPT 리뷰 진행: {reason}")
            review = step_review(args, goal, n)
            handle_paper(n, review)
        else:
            review = step_skip_review(n, reason)
        completed += 1

        step_commit(n, review)

        if review["verdict"] == "DONE":
            banner("연구 목표 완료 (DONE)")
            notify(f"🎉 iter_{n:03d} 연구 목표 완료 (DONE)\n{review['one_line_summary']}")
            finished = True
            break
        if review["verdict"] == "CONTINUE":
            if review.get("skipped"):
                notify(f"✅ iter_{n:03d} 완료 (GPT 리뷰 생략)\n{review['one_line_summary']}")
            else:
                notify(
                    f"✅ iter_{n:03d} 완료 [{review.get('approach_status', '')}]\n"
                    f"{review['one_line_summary']}\n"
                    f"접근법: {review.get('approach_note', '')}\n"
                    f"다음: {review['next_task']}"
                )
        if review["verdict"] == "NEEDS_HUMAN" and not handle_needs_human(review, n):
            print("종료합니다. 다시 실행하면 다음 반복부터 진행합니다.")
            return

    if not finished:
        notify(f"⏸ 최대 반복 수({args.max_iters})에 도달해 멈췄습니다. 다시 실행하면 이어서 진행합니다.")

    banner("루프 종료")
    print(f"요약: {INDEX_FILE}")
    print(f"기록: {RUNS_DIR}")


if __name__ == "__main__":
    try:
        main()
    except AgentError as e:
        print(f"\n[ERROR] {e}")
        notify(f"❌ 오류로 멈췄습니다\n{e}\n다시 실행하면 이어서 진행합니다.")
        print("다시 실행하면 완료되지 않은 단계부터 이어서 진행합니다.")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n중단됨. 다시 실행하면 완료되지 않은 단계부터 이어서 진행합니다.")
        sys.exit(130)
