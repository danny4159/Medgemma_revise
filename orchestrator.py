"""GPT(Codex) ↔ Claude Code 자동 연구 루프.

반복(iteration) 한 번:
    GPT 계획 (codex, read-only) → [사람 확인] → Claude 구현/실험 → GPT 리뷰 (codex, read-only, JSON)

GPT 계획은 여러 사고 라운드로 이어질 수 있다. 방향이 아직 불분명하면 GPT가 조사·검색하고
스스로 다음 질문을 남긴 뒤(think_more) 다시 사고하고, 무엇을 시도할지 판단이 서면(implement)
Claude로 넘어간다. 라운드별 노트는 runs/iter_NNN/think/, 최대 --max-think-rounds번.

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

코드 버전 관리: Claude는 research/ 폴더(자체 git 저장소)에서 작업한다.
접근법마다 approach/<approach_id> 브랜치를 쓰고, 직전 접근법이 success면 그 위에서,
아니면 그 접근법이 시작한 지점으로 돌아가 새 브랜치를 만든다. 커밋은 GPT 리뷰가
commit_worthy로 판단한 경우에만 한다. 버리는 접근법의 미커밋 작업은 git stash로 보관한다.
브랜치는 research/ 안에서만 바뀌므로 오케스트레이터, agent/ 기록, legacy/는 그대로다.

논문 추천: GPT 리뷰는 실제 결과로 가능성이 분명해진 방향에 한해 드물게 논문 1편을 추천한다.
링크가 열리고 중복이 아니면 agent/PAPERS.md에 쌓고 Telegram으로 알린다.

산출물은 agent/runs/iter_NNN/ 에 저장된다. 상태는 모두 파일에 있으므로, 중간에 끊기거나
orchestrator.py를 고친 뒤 다시 실행해도 완료되지 않은 단계부터 이어서 진행한다.
    - 반복 완료 표시는 done.json. 리뷰 뒤 처리(논문·커밋·마일스톤)도 각각 한 번만 한다.
    - Claude가 작업 중에 끊기면 같은 세션을 --resume으로 이어서 마무리한다.
    - 에이전트 호출이 실패하면(네트워크 등) 1분·5분·15분 뒤 다시 시도한다.
    - 예전 반복 파일에 없는 필드는 기본값으로 채워 읽는다.
연구 목표 변경: --goal "새 목표"는 기록을 지우지 않고 새 챕터를 연다. 반복 번호는 이어지고,
새 목표의 첫 계획(deep)은 이전 기록에서 가져올 것을 정리한 뒤 새 목표 기준으로 다시 사고한다.
접근법 시도 횟수는 목표별로 센다. 목표 이력은 agent/GOALS.json. --reset은 완전히 새로 시작할 때만.

정지: 터미널 Ctrl+C, `touch agent/STOP`(현재 단계 후), Telegram `stop` / `stop now` / `status`.

사용 예:
    python orchestrator.py                     # smart: 애매할 때만 확인
    python orchestrator.py --autonomy manual   # 매 반복 계획을 확인
    python orchestrator.py --auto --max-iters 5
    python orchestrator.py --goal "새 연구 목표"     # 이전 기록을 이어받아 목표 변경
    python orchestrator.py --reset --goal "..."     # 기록을 archive로 옮기고 완전히 새로 시작
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
# 목표 변경 이력: [{"goal", "start_iter", "time"}]. GOAL.md는 현재 목표 사본
GOALS_FILE = AGENT_DIR / "GOALS.json"
INDEX_FILE = AGENT_DIR / "INDEX.md"
PAPERS_FILE = AGENT_DIR / "PAPERS.md"
# 사람이 읽는 기록: JOURNEY(마일스톤 흐름) → DECISIONS(반복별 결정) → runs/(원본)
JOURNEY_FILE = AGENT_DIR / "JOURNEY.md"
DECISIONS_FILE = AGENT_DIR / "DECISIONS.md"
# 이 파일이 생기면 현재 단계를 마친 뒤 멈춘다 (Telegram stop도 이 파일을 만든다)
STOP_FILE = AGENT_DIR / "STOP"
# 에이전트 호출 실패 시 재시도 간격(초)
RETRY_DELAYS = (60, 300, 900)
LOG_FILE = AGENT_DIR / "RESEARCH_LOG.md"
TIERS_FILE = AGENT_DIR / "tiers.json"
# runs/ 도입 전 수동 실행의 마지막 리뷰. 첫 반복 계획의 참고 자료로 쓴다.
LEGACY_REVIEW_FILE = AGENT_DIR / "GPT_REVIEW.md"
# Telegram 봇 설정 (TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID). git에 올리지 않는다.
NOTIFY_ENV_FILE = AGENT_DIR / ".notify.env"

# Claude가 코드를 고치는 곳. 자체 git 저장소라 브랜치를 바꿔도 이 폴더 밖은 그대로다.
RESEARCH_DIR = PROJECT_DIR / "research"
BASE_BRANCH = "base"
BRANCH_PREFIX = "approach/"
# 이전 수동 연구 기록 (읽기 전용 참고 자료, 입력 데이터 포함)
LEGACY_DIR = PROJECT_DIR / "legacy"
# 커밋에서 제외할 파일 크기
MAX_COMMIT_FILE_BYTES = 5 * 1024 * 1024

CONDA_ENV = Path("/home/test/.conda/envs/medgemma")
HF_HOME = PROJECT_DIR / "hf_cache"

# Claude 작업 전후 변경 파일을 비교할 때 건너뛸 경로
SNAPSHOT_SKIP_DIRS = {".git", "hf_cache", "eval_samples", "__pycache__"}
SNAPSHOT_SKIP_PATHS = {"agent/runs", "agent/archive"}


class AgentError(Exception):
    pass


class RetryableError(AgentError):
    """네트워크 끊김 등 다시 시도해 볼 만한 실패. output은 마지막 출력 몇 줄."""

    def __init__(self, message, output=""):
        super().__init__(message)
        self.output = output


class StopRequested(Exception):
    pass


# 지금 무엇을 하고 있는지 (Telegram status, 중단 기록용)
STATE = {"n": None, "stage": "시작 전", "since": None, "proc": None, "stop_now": False}


def set_stage(n, stage):
    STATE.update(n=n, stage=stage, since=datetime.datetime.now())


def check_stop():
    if STOP_FILE.exists():
        STOP_FILE.unlink(missing_ok=True)
        raise StopRequested("정지 요청")


def sleep_with_stop(seconds):
    end = datetime.datetime.now() + datetime.timedelta(seconds=seconds)
    while datetime.datetime.now() < end:
        check_stop()
        threading.Event().wait(5)


def with_retries(what, fn):
    """fn()이 RetryableError로 실패하면 RETRY_DELAYS 간격으로 다시 시도한다."""
    last = None
    for attempt, delay in enumerate((0, *RETRY_DELAYS)):
        if delay:
            minutes = delay // 60
            print(f"\n[재시도] {what} 실패 → {minutes}분 뒤 다시 시도 ({attempt}/{len(RETRY_DELAYS)})")
            notify(f"🔁 {what} 실패, {minutes}분 뒤 다시 시도 ({attempt}/{len(RETRY_DELAYS)})\n{str(last)[:300]}")
            sleep_with_stop(delay)
        try:
            return fn()
        except RetryableError as e:
            last = e
    raise AgentError(f"{what}: {len(RETRY_DELAYS)}번 다시 시도했지만 실패. 마지막 오류: {last}")


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


def record_event(n, stage, **data):
    """반복의 결정/단계 기록 (DECISIONS.md를 만드는 원본). runs/iter_NNN/events.jsonl"""
    path = RUNS_DIR / f"iter_{n:03d}" / "events.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"time": now(), "stage": stage, **data}, ensure_ascii=False) + "\n")


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
    tail = []

    with log_path.open("a", encoding="utf-8") as log_f:
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
        STATE["proc"] = proc

        def kill():
            timed_out.set()
            proc.kill()

        timer = threading.Timer(timeout, kill)
        timer.start()
        try:
            for line in proc.stdout:
                log_f.write(line)
                log_f.flush()
                tail = (tail + [line])[-20:]
                on_line(line)
            proc.wait()
        except KeyboardInterrupt:
            proc.kill()
            proc.wait()
            raise
        finally:
            timer.cancel()
            STATE["proc"] = None

    if STATE["stop_now"]:
        raise StopRequested("즉시 정지 요청")
    if timed_out.is_set():
        raise AgentError(f"{cmd[0]} 시간 초과 ({timeout}s). 로그: {log_path}")
    if proc.returncode != 0:
        raise RetryableError(f"{cmd[0]} 종료 코드 {proc.returncode}. 로그: {log_path}", "".join(tail))


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
        raise RetryableError(f"Codex 출력이 비어 있음. 로그: {log_path}")
    return text


def summarize_tool_input(name, tool_input):
    if name == "Bash":
        return tool_input.get("command", "")
    for key in ("file_path", "path", "pattern", "url"):
        if key in tool_input:
            return str(tool_input[key])
    return json.dumps(tool_input, ensure_ascii=False)


def run_claude(args, prompt, log_path, tier, session_file=None, resume_id=None):
    """Claude를 stream-json으로 실행해 진행 상황을 보여주고 최종 result 이벤트를 반환한다.

    세션 id는 시작하자마자 session_file에 저장해 두고, 끊기면 resume_id로 같은 세션을 잇는다.
    """
    spec = tier_spec("claude", tier)
    print(f"Claude 등급: {tier} ({spec['model']}, effort={spec['effort']})\n", flush=True)
    cmd = [
        "claude", "-p",
        "--permission-mode", "acceptEdits",
        "--output-format", "stream-json", "--verbose",
        "--model", spec["model"],
        "--effort", spec["effort"],
        # 작업 디렉터리는 research/. 프로젝트 폴더는 계획과 legacy/ 데이터를 읽는 용도.
        # --add-dir는 값을 여러 개 받으므로 프롬프트 바로 앞에 두면 프롬프트까지 경로로 읽는다.
        "--add-dir", str(PROJECT_DIR),
        "--append-system-prompt-file", str(PROMPT_DIR / "claude_engineer.md"),
        # 연구 에이전트 전용 권한. .claude/settings.json에 두면 대화형 세션까지 막힌다.
        "--settings", str(AGENT_DIR / "claude_settings.json"),
    ]
    if resume_id:
        cmd += ["--resume", resume_id]
    cmd.append(prompt)

    result = {}

    def on_line(line):
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            print(f"  [claude] {line}", end="", flush=True)
            return

        if session_file and event.get("session_id") and not read(session_file).strip():
            save(session_file, event["session_id"])
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
        raise RetryableError(f"Claude result 이벤트 없음. 로그: {log_path}")
    return result


# --------------------------------------------------
# 파일 변경 추적 (gitignore와 무관하게 Claude가 바꾼 파일을 잡는다)
# --------------------------------------------------

def snapshot():
    """Claude가 건드릴 수 있는 research/의 파일 상태 (경로는 프로젝트 기준)."""
    files = {}
    for base in (RESEARCH_DIR,):
        for root, dirs, names in os.walk(base):
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


def git(*git_args, cwd=None):
    """(종료 코드, 출력). 실패하면 출력 대신 에러 메시지."""
    result = subprocess.run(["git", *git_args], cwd=cwd or PROJECT_DIR, text=True, capture_output=True)
    return result.returncode, result.stdout if result.returncode == 0 else result.stderr.strip()


def wgit(*git_args):
    """research/ 저장소에서 git 실행."""
    return git(*git_args, cwd=RESEARCH_DIR)


def current_branch():
    return wgit("rev-parse", "--abbrev-ref", "HEAD")[1].strip()


def ensure_research_repo():
    """research/를 자체 git 저장소로 준비한다. 이미 있으면 그대로 둔다."""
    if (RESEARCH_DIR / ".git").exists():
        return
    RESEARCH_DIR.mkdir(exist_ok=True)
    code, out = wgit("init", "-q", "-b", BASE_BRANCH)
    if code:
        raise AgentError(f"research 저장소 생성 실패: {out}")
    # 커밋 작성자는 바깥 저장소 설정을 따른다
    for key in ("user.name", "user.email"):
        value = git("config", key)[1].strip()
        if value:
            wgit("config", key, value)
    save(RESEARCH_DIR / ".gitignore", "results/\n__pycache__/\n*.pyc\n")
    save(RESEARCH_DIR / "README.md", (
        "# research\n\n"
        "오케스트레이터가 진행하는 연구 코드. 접근법마다 `approach/<id>` 브랜치를 쓴다.\n"
        "- `results/`: 실험 결과 (git 제외, 브랜치와 상관없이 유지)\n"
        "- 입력 데이터와 이전 수동 분석 기록은 `../legacy/`\n"
    ))
    wgit("add", "-A")
    code, out = wgit("commit", "-q", "-m", "Initialize research repository")
    if code:
        raise AgentError(f"research 저장소 첫 커밋 실패: {out}")
    print(f"연구 저장소 생성: {RESEARCH_DIR} ({BASE_BRANCH})")


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


# orchestrator를 고쳐 필드가 늘어나도 예전 반복 파일을 그대로 읽을 수 있게 기본값을 채운다
PLAN_DEFAULTS = {
    "plan_summary": "", "approach": "?", "approach_id": "", "alternatives": [],
    "decision": "proceed", "decision_reason": "", "claude_tier": "heavy", "tier_reason": "",
    "review_mode": "full", "review_reason": "", "plan_markdown": "",
}
REVIEW_DEFAULTS = {
    "verdict": "CONTINUE", "approach_status": "", "approach_note": "", "commit_worthy": False,
    "commit_message": "", "one_line_summary": "", "next_task": "", "next_plan_tier": "normal",
    "reason": "", "review_markdown": "", "paper_recommendation": {}, "milestone": {},
}


def load_review(n):
    path = iter_dir(n) / "review.json"
    return {**REVIEW_DEFAULTS, **json.loads(read(path))} if path.exists() else None


def tiers_used(n):
    return json.loads(read(iter_dir(n) / "tiers_used.json", "{}"))


def record_tier(n, step, tier):
    used = tiers_used(n)
    used[step] = tier
    save(iter_dir(n) / "tiers_used.json", json.dumps(used, indent=2))


def plan_tier(args, n):
    if args.gpt_tier:
        return args.gpt_tier
    if goal_start(n) == n:
        return "deep"  # 새 목표의 첫 계획은 이전 기록을 다시 읽고 깊게 사고한다
    prev = load_review(n - 1) if n > 1 else None
    return prev.get("next_plan_tier", "deep") if prev else "deep"


def claude_tier(args, n):
    if args.claude_tier:
        return args.claude_tier
    d = iter_dir(n)
    override = read(d / "claude_tier_override.txt").strip()
    return override or load_plan(n)["claude_tier"]


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
    mode = override or load_plan(n)["review_mode"]
    if mode == "full":
        return True, "사람이 full 지정" if override else "계획에서 full 지정"
    if parse_trailer(read(d / "claude_report.md"), "SELF_CHECK").upper() != "PASS":
        return True, "skip이었지만 Claude 자체 검증이 PASS가 아님"
    if json.loads(read(d / "claude_meta.json", "{}")).get("permission_denials"):
        return True, "skip이었지만 권한 거부된 명령이 있음"
    return False, ("사람이 skip 지정" if override else "계획에서 skip 지정") + ", Claude 자체 검증 PASS"


def load_plan(n):
    path = iter_dir(n) / "plan.json"
    return {**PLAN_DEFAULTS, **json.loads(read(path))} if path.exists() else None


def load_json(path):
    return json.loads(read(path)) if path.exists() else None


def approach_key(plan):
    """접근법 id (git 브랜치 이름에 쓸 수 있는 형태)."""
    raw = (plan or {}).get("approach_id") or (plan or {}).get("approach") or ""
    key = re.sub(r"[^a-z0-9-]+", "-", raw.lower()).strip("-")[:40]
    return key or "unnamed"


def approach_branch(key):
    return f"{BRANCH_PREFIX}{key}"


def approach_ledger(upto=None, since=None):
    """접근법별 시도 기록. 반복 파일에서 매번 다시 계산한다.

    {approach_id: {"name", "attempts", "iters", "status", "branch", "base", "commits"}}
    upto를 주면 그 반복이 속한 연구 목표 안에서만 센다 (목표가 바뀌면 시도 횟수를 새로 센다).
    """
    if upto is not None and since is None:
        since = goal_start(upto)
    ledger = {}
    for n in existing_iterations():
        if upto is not None and n > upto:
            break
        if since is not None and n < since:
            continue
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


def load_goals():
    goals = load_json(GOALS_FILE)
    if goals:
        return goals
    if GOAL_FILE.exists():
        # GOALS.json 도입 전: GOAL.md 하나가 처음부터의 목표
        return [{"goal": read(GOAL_FILE).strip(), "start_iter": 1, "time": ""}]
    return []


def goal_entry(n):
    """반복 n에 적용되는 목표 (그 반복 이전에 시작된 마지막 목표)."""
    goals = load_goals()
    current = [g for g in goals if g["start_iter"] <= n]
    return current[-1] if current else (goals[0] if goals else {"goal": "", "start_iter": 1})


def goal_for(n):
    return goal_entry(n)["goal"]


def goal_start(n):
    return goal_entry(n)["start_iter"]


def current_iteration():
    """완료되지 않은 반복이 있으면 그 번호, 없으면 다음 번호."""
    iters = existing_iterations()
    if not iters:
        return 1
    last = iters[-1]
    return last + 1 if is_done(last) else last


def is_done(n):
    return (iter_dir(n) / "done.json").exists()


def post_flags(n):
    """리뷰 뒤 처리(논문·커밋·마일스톤·알림) 중 이미 한 것. 재실행 시 중복을 막는다."""
    return load_json(iter_dir(n) / "post.json") or {}


def set_post_flag(n, key):
    flags = post_flags(n)
    flags[key] = now()
    save(iter_dir(n) / "post.json", json.dumps(flags, indent=2))


def stage_of(n):
    d = iter_dir(n)
    if not (d / "plan.md").exists():
        return "계획"
    if not (d / "claude_report.md").exists():
        return "Claude 구현" if (d / "git.json").exists() else "계획 확인"
    if not (d / "review.json").exists():
        return "리뷰"
    return "리뷰 후 처리"


def code_version():
    """지금 돌고 있는 orchestrator 버전 (main 커밋 + 커밋 안 된 수정 여부)."""
    sha = git("rev-parse", "--short", "HEAD")[1].strip()
    dirty = git("status", "--porcelain", "--", "orchestrator.py", "notifier.py", "agent/prompts",
                "agent/tiers.json", "agent/claude_settings.json")[1].strip()
    return f"{sha}+수정" if dirty else sha


def rebuild_index():
    lines = ["# Research Index", ""]
    goal_starts = {g["start_iter"]: (i, g["goal"]) for i, g in enumerate(load_goals(), 1)}
    for n in existing_iterations():
        if n in goal_starts:
            k, text = goal_starts[n]
            lines += ["", f"### 연구 목표 {k} (iter_{n:03d}부터): {text.splitlines()[0][:200] if text else ''}", ""]
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

    iters_all = existing_iterations()
    latest = iters_all[-1] if iters_all else 1
    ledger = approach_ledger(upto=latest)
    earlier = approach_ledger(upto=goal_start(latest) - 1, since=1) if goal_start(latest) > 1 else {}
    if earlier:
        lines += ["", "## 이전 목표들의 접근법 (참고용, 시도 횟수 제한에는 안 들어감)", ""]
        for entry in earlier.values():
            lines.append(f"- {entry['name']} [{entry['branch']}]: {entry['attempts']}회, 최근 판정: {entry['status']}, "
                         f"커밋: {', '.join(entry['commits']) or '없음'}")
    if ledger:
        lines += ["", f"## 접근법 기록 — 현재 목표 (같은 접근법 최대 {MAX_ATTEMPTS}회)", ""]
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
    rebuild_decisions()


def iteration_block(n):
    """DECISIONS.md의 반복 하나: 계획 → 결정 → 개발 → 검증 → 커밋 순서."""
    d = iter_dir(n)
    events = [json.loads(line) for line in read(d / "events.jsonl").splitlines() if line.strip()]
    if not events:
        return []
    plan = load_plan(n) or {}
    review = load_review(n) or {}
    git_info = load_json(d / "git.json") or {}
    iters = approach_ledger(upto=n).get(approach_key(plan), {}).get("iters", [n])
    attempt = iters.index(n) + 1 if n in iters else 1

    lines = [f"## iter_{n:03d} — {plan.get('approach', '?')} ({attempt}번째 시도) · {events[0]['time'][:16]}", ""]
    plan_question = None
    for ev in events:
        stage = ev["stage"]
        if stage == "think":
            lines.append(f"- 🔎 **사고 라운드 {ev.get('round')}** (GPT {ev.get('tier')}): {ev.get('summary')}")
            if ev.get("questions"):
                lines.append(f"  - 스스로 던진 질문: {' · '.join(ev['questions'])}")
            continue
        if stage == "plan":
            plan_question = ev.get("decision_reason") if ev.get("decision") == "ask_human" else None
            lines.append(f"- 🧭 **계획** (GPT {ev.get('tier')}): {ev.get('plan_summary') or ev.get('approach')}")
            alts = " · ".join(f"{i}) {a}" for i, a in enumerate(ev.get("alternatives") or [], 1))
            if alts:
                lines.append(f"  - 대안: {alts}")
            label = "사람에게 묻기로 함" if ev.get("decision") == "ask_human" else "1순위 선택 근거"
            lines.append(f"  - {label}: {ev.get('decision_reason', '')}")
        elif stage == "decision" and ev.get("by") == "auto":
            lines.append(f"- ▶ **결정**: 자동 진행 ({ev.get('mode')}) — {ev.get('result')}")
        elif stage == "decision":
            lines.append(f"- 🙋 **결정 (사람)**: \"{ev.get('reply')}\" → {ev.get('result')}")
            for concern in ev.get("concerns") or []:
                if concern != plan_question:
                    lines.append(f"  - 확인 이유: {concern}")
        elif stage == "override":
            lines.append(f"- ✏️ 사람이 {ev.get('what')}을 {ev.get('value')}(으)로 변경")
        elif stage == "claude":
            lines.append(
                f"- 🔧 **Claude** ({ev.get('tier')}): {ev.get('summary') or '(요약 없음)'} "
                f"[자체 검증 {ev.get('self_check')}, 파일 {ev.get('changed_files')}개 변경]"
            )
            if git_info.get("created"):
                branch_text = f"새 브랜치 `{git_info['branch']}` ← {git_info.get('base_ref')} ({git_info.get('base')})"
            else:
                branch_text = f"브랜치 `{ev.get('branch')}`에서 계속"
            if git_info.get("stashed"):
                branch_text += f"; 이전 브랜치 미커밋 작업은 stash로 보관"
            lines.append(f"  - {branch_text}")
            if ev.get("permission_denials"):
                lines.append(f"  - ⚠ 권한 거부 {ev['permission_denials']}건")
        elif stage == "review":
            lines.append(
                f"- 🔍 **리뷰** (GPT {ev.get('tier')}): [{review.get('verdict')} / {review.get('approach_status')}] "
                f"{review.get('one_line_summary', '')}"
            )
            if review.get("approach_note"):
                lines.append(f"  - 접근법 판단: {review['approach_note']}")
            if review.get("next_task"):
                lines.append(f"  - 다음: {review['next_task']}")
        elif stage == "review_skipped":
            lines.append(f"- ⏭ 리뷰 생략: {ev.get('reason')}")
        elif stage == "commit":
            lines.append(f"- 💾 **커밋** `{ev.get('sha')}` ({ev.get('branch')}): {ev.get('message')}")
        elif stage == "paper":
            lines.append(f"- 📚 논문 추천: {ev.get('title')} — PAPERS.md")
        elif stage == "milestone":
            lines.append(f"- 🏁 **마일스톤**: {ev.get('title')} — JOURNEY.md")
        elif stage == "goal":
            if ev.get("previous"):
                lines.append(f"- 🎯 **연구 목표 변경**: {ev.get('goal')}")
                lines.append(f"  - 이전 목표: {ev.get('previous')}")
            else:
                lines.append(f"- 🎯 **연구 목표**: {ev.get('goal')}")
        elif stage == "session":
            if ev.get("resumed_from"):
                lines.append(f"- ↻ 재실행: '{ev['resumed_from']}' 단계부터 이어서 (orchestrator {ev.get('version')})")
            else:
                lines.append(f"- ▶ 실행 시작 (orchestrator {ev.get('version')})")
        elif stage == "claude_resume":
            lines.append("- ↻ 끊겼던 Claude 세션을 이어서 진행")
        elif stage == "stopped":
            lines.append(f"- ⏹ 중단: {ev.get('reason')} ({ev.get('during')} 중)")
        elif stage == "needs_human":
            lines.append(f"- 🙋 **사람 결정 요청**: {ev.get('question')}")
            lines.append(f"  - 답: \"{ev.get('reply')}\" → {ev.get('result')}")
    lines += [f"- 📁 원본: `agent/runs/iter_{n:03d}/`", ""]
    return lines


def rebuild_decisions():
    lines = [
        "# 결정 기록 (DECISIONS)",
        "",
        "반복마다 계획 → 결정 → 개발 → 검증 흐름. 큰 흐름은 JOURNEY.md, 원본은 agent/runs/.",
        "",
    ]
    for n in existing_iterations():
        lines += iteration_block(n)
    save(DECISIONS_FILE, "\n".join(lines) + "\n")


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

    goal_change = ""
    if goal_start(n) == n and n > 1:
        previous = goal_for(n - 1)
        goal_change = f"""
=== 연구 목표 변경 (중요) ===
이번 반복부터 연구 목표가 바뀌었다.
이전 목표: {previous}
새 목표: {goal}

계획하기 전에 이전 기록을 먼저 읽어라: agent/JOURNEY.md(마일스톤), agent/INDEX.md, agent/DECISIONS.md,
agent/PAPERS.md, research/의 브랜치와 커밋(git -C research log --all --oneline).
새 목표에 쓸 수 있는 발견, 재사용할 코드, 실패에서 얻은 교훈을 정리한 뒤, 새 목표 기준으로 처음부터 다시 사고하라.
이전 목표의 접근법을 그대로 이어갈 필요는 없다. plan_markdown 맨 앞에 "# 이전 기록에서 가져올 것" 섹션을 넣어라.
"""
    prompt = f"""{read(PROMPT_DIR / "gpt_plan.md")}
{goal_change}
=== 이번 반복 ===
iter_{n:03d}

=== 연구 목표 ===
{goal}

=== 지금까지의 반복 요약 (agent/INDEX.md) ===
{read(INDEX_FILE, "없음")}

=== 연구 흐름의 마일스톤 (agent/JOURNEY.md, 최근 부분) ===
{read(JOURNEY_FILE, "없음")[-6000:]}
(반복별 결정 과정이 더 필요하면 agent/DECISIONS.md를 직접 열어 읽어라.)

=== 코드 위치 ===
연구 코드: research/ (자체 git 저장소, 현재 브랜치 {current_branch()}), 결과: research/results/
이전 수동 분석 기록과 입력 데이터: legacy/ (scripts, docs, eval_samples, eval_results)

=== 직전 결과 ===
{prev_text}

=== 사람의 추가 지시 ===
{read(d / "human_to_gpt.md", "없음")}

=== 규칙 ===
같은 접근법 최대 시도 횟수: {MAX_ATTEMPTS}
"""
    tier = plan_tier(args, n)
    think_dir = d / "think"
    think_dir.mkdir(exist_ok=True)
    while True:
        # 끝난 사고 라운드(think_more)는 round_NN.json으로 남아 있다. 끊겨도 다음 라운드부터 이어간다.
        done_rounds = sorted(think_dir.glob("round_[0-9][0-9].json"))
        r = len(done_rounds) + 1
        final = r >= args.max_think_rounds
        set_stage(n, f"GPT 사고 라운드 {r}")
        round_prompt = prompt + think_section(done_rounds, r, args.max_think_rounds, final)
        raw = with_retries(f"GPT 사고 라운드 {r}", lambda: run_codex(
            args, round_prompt, think_dir / f"round_{r:02d}.raw.json", d / "plan_codex.log", tier,
            schema=PROMPT_DIR / "plan_schema.json",
        ))
        try:
            plan = {**PLAN_DEFAULTS, **json.loads(raw)}
        except json.JSONDecodeError as e:
            raise AgentError(f"계획 JSON 파싱 실패: {e}. 파일: {think_dir / f'round_{r:02d}.raw.json'}")

        if plan["next_action"] == "think_more" and not final:
            save(think_dir / f"round_{r:02d}.json", json.dumps(plan, ensure_ascii=False, indent=2))
            questions = "\n".join(f"- {q}" for q in plan["open_questions"])
            save(think_dir / f"round_{r:02d}.md",
                 f"# 사고 라운드 {r}\n\n{plan['research_notes']}\n\n## 다음에 파고들 질문\n{questions}\n")
            print(f"\n🔎 사고 라운드 {r}: {plan['plan_summary']}\n다음 질문:\n{questions}")
            record_event(n, "think", round=r, tier=tier, summary=plan["plan_summary"],
                         questions=plan["open_questions"])
            rebuild_index()
            check_stop()
            continue

        if plan["next_action"] == "think_more":
            # 라운드를 다 썼는데도 방향을 못 정했다: 사람에게 묻는다
            plan["decision"] = "ask_human"
            plan["decision_reason"] = (
                f"사고 라운드 {r}번을 다 썼지만 GPT가 아직 구현 방향을 확신하지 못했습니다. "
                f"남은 질문: {' / '.join(plan['open_questions'])}"
            )
        break

    save(d / "plan.json", json.dumps(plan, ensure_ascii=False, indent=2))
    record_tier(n, "plan", tier)
    plan_md = plan["plan_markdown"]
    if plan["research_notes"].strip():
        plan_md += f"\n\n# 계획의 근거 (GPT 조사 노트)\n\n{plan['research_notes']}\n"
    if done_rounds:
        plan_md += f"\n이전 사고 라운드 노트: agent/runs/iter_{n:03d}/think/\n"
    # plan.md가 있으면 계획 단계는 완료로 본다 (마지막에 저장)
    save(d / "plan.md", plan_md)
    log(f"iter_{n:03d} GPT PLAN [{plan['approach']} / {plan['decision']}]", plan_md)
    print("\n" + plan_md)
    print("\n대안 순위:")
    for i, alt in enumerate(plan["alternatives"], 1):
        print(f"  {i}. {alt}")
    print(f"결정: {plan['decision']} — {plan['decision_reason']}")
    print(f"\nClaude 등급 제안: {plan['claude_tier']} — {plan['tier_reason']}")
    print(f"GPT 리뷰: {plan['review_mode']} — {plan['review_reason']}")
    record_event(n, "plan", tier=tier, think_rounds=len(done_rounds) + 1, **{k: plan.get(k) for k in (
        "plan_summary", "approach", "alternatives", "decision", "decision_reason",
        "claude_tier", "review_mode")})
    rebuild_index()


def think_section(done_rounds, r, max_rounds, final):
    """사고 라운드 안내와 이전 라운드들의 노트·질문."""
    text = f"\n=== 사고 라운드 {r}/{max_rounds} ===\n"
    for path in done_rounds:
        prev = json.loads(read(path))
        questions = "\n".join(f"- {q}" for q in prev.get("open_questions", []))
        text += (f"\n--- 라운드 {path.stem[-2:]}에서 알게 된 것 ---\n{prev.get('research_notes', '')[:4000]}\n"
                 f"라운드 {path.stem[-2:]}가 남긴 질문:\n{questions}\n")
    if done_rounds:
        text += "\n이번 라운드에서는 위 질문들에 먼저 답하라 (웹 검색, 논문, 코드·결과 파일 확인).\n"
    if final:
        text += ("\n이번이 마지막 사고 라운드다. next_action=implement로 전체 계획을 내라. "
                 "그래도 방향을 확신할 수 없으면 decision=ask_human으로 사람에게 구체적으로 물어라.\n")
    return text


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
        record_event(n, "decision", by="auto", mode=args.autonomy, result="1순위로 진행")
        return "go"

    def decided(action, result, reply):
        record_event(n, "decision", by="human", mode=args.autonomy, concerns=concerns,
                     reply=reply, result=result)
        rebuild_index()
        return action

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
            return decided("quit", "종료", reply)
        if cmd.isdigit() and 1 <= int(cmd) <= max(len(alternatives), 1):
            k = int(cmd)
            if k == 1:
                return decided("go", "1순위로 진행", reply)
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
            return decided("replan", f"대안 {k}번으로 재계획: {choice}", reply)
        if cmd == "t":
            if args.claude_tier:
                print("--claude-tier로 고정되어 있어 바꿀 수 없습니다.")
                continue
            picked = (rest or ask(f"등급 입력 ({' / '.join(CLAUDE_TIERS)}): ") or "").lower()
            if picked in CLAUDE_TIERS:
                save(d / "claude_tier_override.txt", picked)
                record_event(n, "override", by="human", what="Claude 등급", value=picked)
            else:
                print("알 수 없는 등급입니다.")
            continue
        if cmd == "r":
            picked = (rest or ask("리뷰 여부 입력 (full / skip): ") or "").lower()
            if picked in ("full", "skip"):
                save(d / "review_mode_override.txt", picked)
                record_event(n, "override", by="human", what="GPT 리뷰", value=picked)
            else:
                print("full 또는 skip만 가능합니다.")
            continue
        if cmd == "a":
            args.autonomy = "full"
            return decided("go", "1순위로 진행, 이후 자동 진행으로 전환", reply)
        if cmd == "f":
            feedback = rest or ask("Claude에게 줄 추가 지시:\n> ") or ""
            if feedback:
                save(d / "human_to_claude.md", feedback)
                log(f"iter_{n:03d} USER FEEDBACK", feedback)
            return decided("go", f"추가 지시 후 진행: {feedback}", reply)
        if cmd == "":
            return decided("go", "1순위로 진행", reply or "ENTER")
        print(f"알 수 없는 입력입니다: {reply}")
        notify(f"알 수 없는 입력입니다: {reply}")


def base_for_new_branch(cur):
    """새 접근법 브랜치의 출발점.

    직전 접근법이 success면 그 위에서 이어가고, 아니면 그 접근법이 시작했던 지점으로 돌아간다.
    """
    if cur == BASE_BRANCH or not cur.startswith(BRANCH_PREFIX):
        return cur
    entry = approach_ledger().get(cur[len(BRANCH_PREFIX):])
    if entry and entry["status"] == "success":
        return cur
    return (entry or {}).get("base") or BASE_BRANCH


def ensure_branch(n):
    """이번 반복 접근법의 브랜치로 research/를 맞춘다. 결과는 git.json에 기록."""
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


CLAUDE_RESUME_PROMPT = """이전 실행이 중간에 끊겼다 (서버·네트워크 문제 또는 사용자 정지).
지금까지 한 작업을 git status, git diff, results/ 파일로 확인하고, 계획의 남은 부분을 마친 뒤
최종 보고서를 지정된 형식으로 작성하라 (맨 끝의 SELF_CHECK, SUMMARY 줄 포함).
끊기기 전에 이미 끝낸 작업은 다시 하지 않는다."""

CLAUDE_RESTART_NOTE = """
=== 주의: 이전 시도가 중단됨 ===
이전 Claude 실행이 중간에 끊겼다. research/ 작업 트리와 results/에 부분적으로 만든 파일이
있을 수 있다. 먼저 git status, git diff로 확인하고, 쓸 수 있는 것은 이어서 쓴다.
"""


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
현재 디렉터리는 {RESEARCH_DIR} (연구 코드 git 저장소, 브랜치 {branch})다.
코드는 여기서만 만들고 고치고, 결과는 results/에 저장한다.
입력 데이터는 {LEGACY_DIR}/eval_samples/, 이전 수동 분석 코드·결과는 {LEGACY_DIR}/ 에 있다 (읽기 전용).
이전 코드를 쓰려면 research/로 복사해서 고친다. git 커밋과 브랜치 관리는 orchestrator가 한다.

=== 사용자 추가 지시 ===
{read(d / "human_to_claude.md", "없음")}
"""
    tier = claude_tier(args, n)
    record_tier(n, "claude", tier)
    session_file = d / "claude_session.txt"
    stream_log = d / "claude_stream.jsonl"

    def attempt():
        session = read(session_file).strip()
        if session:
            # 이전 실행이 끊겼다: 같은 세션을 이어서 마무리하게 한다
            print(f"이전 Claude 세션을 이어서 진행합니다 ({session[:8]}…)")
            record_event(n, "claude_resume", session=session)
            try:
                return run_claude(args, CLAUDE_RESUME_PROMPT, stream_log, tier, session_file, resume_id=session)
            except RetryableError as e:
                if "No conversation found" not in e.output:
                    raise
                print("이전 세션을 찾을 수 없어 새로 시작합니다.")
                session_file.unlink(missing_ok=True)
        restarted = stream_log.exists() and stream_log.stat().st_size > 0
        return run_claude(args, prompt + (CLAUDE_RESTART_NOTE if restarted else ""),
                          stream_log, tier, session_file)

    result = with_retries("Claude 구현/실험", attempt)

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
    record_event(n, "claude", tier=tier, branch=branch,
                 summary=parse_trailer(report, "SUMMARY"),
                 self_check=parse_trailer(report, "SELF_CHECK") or "없음",
                 changed_files=len(changed.splitlines()), permission_denials=len(denials))
    rebuild_index()

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
- 코드는 research/, 결과는 research/results/ 에 있다.

=== 이번 반복에서 바뀐 파일 (A 추가 / M 수정 / D 삭제) ===
{changed_text}
"""
    tier = review_tier(args, n)
    raw = with_retries("GPT 리뷰", lambda: run_codex(
        args, prompt, d / "review.raw.json", d / "review_codex.log", tier,
        schema=PROMPT_DIR / "review_schema.json",
    ))
    record_tier(n, "review", tier)
    try:
        review = json.loads(raw)
    except json.JSONDecodeError as e:
        raise AgentError(f"리뷰 JSON 파싱 실패: {e}. 파일: {d / 'review.raw.json'}")

    save(d / "review.md", review["review_markdown"])
    # review.json이 있으면 이 반복은 완료로 본다 (마지막에 저장)
    save(d / "review.json", json.dumps(review, ensure_ascii=False, indent=2))
    log(f"iter_{n:03d} GPT REVIEW [{review['verdict']}]", review["review_markdown"])
    record_event(n, "review", tier=tier)
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
    record_event(n, "paper", title=paper["title"], url=url)
    print(f"\n📚 논문 추천: {paper['title']}")
    notify(
        f"📚 읽어볼 논문 (iter_{n:03d})\n\n"
        f"{paper['title']} ({paper['authors_year']})\n{url}\n\n"
        f"지금 하고 있는 것:\n{paper['current_work']}\n\n"
        f"추천 이유:\n{paper['why']}\n\n"
        f"읽어볼 부분:\n{paper['what_to_read']}"
    )


def handle_milestone(n, review):
    """리뷰가 마일스톤으로 판단하면 JOURNEY.md에 흐름을 남기고 알린다."""
    milestone = review.get("milestone") or {}
    if not milestone.get("is_milestone") or not milestone.get("title"):
        return
    plan = load_plan(n) or {}
    entry = approach_ledger(upto=n).get(approach_key(plan), {})
    commits = ", ".join(entry.get("commits", [])) or "없음"
    iters = ", ".join(f"iter_{i:03d}" for i in entry.get("iters", [n]))

    if not JOURNEY_FILE.exists():
        save(JOURNEY_FILE, (
            "# 연구 흐름 (JOURNEY)\n\n"
            "연구 목표에 의미 있는 진전이 있을 때만 기록한다. 반복별 결정은 DECISIONS.md, 원본은 runs/.\n"
        ))
    text = (
        f"\n## 🏁 {milestone['title']}\n"
        f"*iter_{n:03d} · {now()[:16]} · 판정: {review['verdict']} / {review.get('approach_status', '')}*\n\n"
        f"{milestone['story'].strip()}\n\n"
        f"- 접근법: {plan.get('approach', '?')} (`{entry.get('branch', '')}`), 시도: {iters}\n"
        f"- 커밋: {commits}\n"
        f"- 자세히: DECISIONS.md의 iter_{n:03d}, `agent/runs/iter_{n:03d}/review.md`\n"
    )
    with JOURNEY_FILE.open("a", encoding="utf-8") as f:
        f.write(text)
    record_event(n, "milestone", title=milestone["title"])
    rebuild_index()
    print(f"\n🏁 마일스톤: {milestone['title']}")
    notify(f"🏁 마일스톤 (iter_{n:03d})\n{milestone['title']}\n\n{milestone['story'][:1500]}")


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
    record_event(n, "review_skipped", reason=reason)
    rebuild_index()
    print(f"summary: {summary}")
    return review


def step_commit(n, review):
    """GPT 리뷰가 commit_worthy로 판단했을 때만 연구 브랜치에 커밋한다."""
    if (iter_dir(n) / "commit.json").exists() or review.get("skipped") or not review.get("commit_worthy") or review.get("approach_status") == "abandon":
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
    record_event(n, "commit", sha=sha, branch=branch, message=title)
    rebuild_index()
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
            record_event(n, "needs_human", question=review["reason"], reply=reply, result="종료")
            rebuild_index()
            return False
        if cmd == "f":
            note = rest or ask("다음 계획에 반영할 지시:\n> ") or ""
            if note:
                save(iter_dir(n + 1) / "human_to_gpt.md", note)
                log(f"iter_{n + 1:03d} HUMAN NOTE", note)
            record_event(n, "needs_human", question=review["reason"], reply=reply,
                         result=f"지시 반영해 계속: {note}")
            rebuild_index()
            return True
        if cmd == "":
            record_event(n, "needs_human", question=review["reason"], reply=reply or "ENTER",
                         result="GPT 제안대로 계속")
            rebuild_index()
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
    p.add_argument("--max-think-rounds", type=int, default=4, help="반복당 GPT 사고 라운드 최대 횟수")
    p.add_argument("--goal", help="새 연구 목표. 이전 기록을 이어받아 새 목표로 다시 계획한다")
    p.add_argument("--reset", action="store_true", help="모든 기록을 archive로 옮기고 완전히 새로 시작")
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
    for path in (GOAL_FILE, GOALS_FILE, INDEX_FILE, DECISIONS_FILE, JOURNEY_FILE, PAPERS_FILE):
        if path.exists():
            shutil.move(str(path), str(dest / path.name))
    print(f"이전 연구를 {dest} 로 옮겼습니다.")


def change_goal(text):
    """새 연구 목표를 연다. 기록은 그대로 두고 반복 번호를 이어간다."""
    goals = load_goals()
    n = current_iteration()
    d = iter_dir(n)
    if goals and (d / "claude_report.md").exists() and not is_done(n):
        start = n + 1  # Claude 작업까지 끝난 반복은 이전 목표로 마무리한다
    else:
        start = n
        if goals and (d / "plan.md").exists():
            # Claude 시작 전인 계획은 버리고 새 목표로 다시 계획한다
            stamp = now().replace(" ", "_").replace(":", "")
            for name in ("plan.json", "plan.md", "git.json", "think"):
                if (d / name).exists():
                    (d / name).rename(d / f"rejected_{stamp}_{name}")
    previous = goals[-1]["goal"] if goals else None
    goals = [g for g in goals if g["start_iter"] < start]
    goals.append({"goal": text, "start_iter": start, "time": now()})
    save(GOALS_FILE, json.dumps(goals, ensure_ascii=False, indent=2))
    save(GOAL_FILE, text)
    record_event(start, "goal", goal=text, previous=previous)

    if previous:
        if not JOURNEY_FILE.exists():
            save(JOURNEY_FILE, "# 연구 흐름 (JOURNEY)\n")
        with JOURNEY_FILE.open("a", encoding="utf-8") as f:
            f.write(f"\n## 🎯 연구 목표 변경 (iter_{start:03d}부터, {now()[:16]})\n\n"
                    f"- 이전: {previous}\n- 새 목표: {text}\n")
        print(f"연구 목표를 바꿨습니다. iter_{start:03d}부터 새 목표로 계획합니다 (이전 기록 참고).")
        notify(f"🎯 연구 목표 변경 (iter_{start:03d}부터)\n이전: {previous[:300]}\n새 목표: {text[:500]}")
    rebuild_index()


def load_goal(args):
    """현재 목표를 돌려준다. --goal이 기존 목표와 다르면 새 목표를 연다. (목표, 바뀌었는지)"""
    goals = load_goals()
    if args.goal and (not goals or goals[-1]["goal"] != args.goal.strip()):
        change_goal(args.goal.strip())
        return args.goal.strip(), True
    if not goals:
        goal = ask("\n=== 연구 목표 입력 ===\n이번 연구에서 무엇을 할지 입력하세요:\n> ")
        if not goal:
            sys.exit("연구 목표가 비어 있습니다.")
        change_goal(goal)
        return goal, True
    if not GOALS_FILE.exists():
        save(GOALS_FILE, json.dumps(goals, ensure_ascii=False, indent=2))
    return goals[-1]["goal"], False


def status_text():
    if STATE["n"] is None:
        return "시작 준비 중입니다."
    minutes = int((datetime.datetime.now() - STATE["since"]).total_seconds() // 60)
    return f"iter_{STATE['n']:03d} · {STATE['stage']} 진행 중 ({minutes}분째)"


def request_stop():
    STOP_FILE.touch()
    HUMAN.interrupt()
    return f"현재 단계({STATE['stage']})를 마치면 멈춥니다. 다시 실행하면 이어서 진행합니다."


def request_stop_now():
    STOP_FILE.touch()
    STATE["stop_now"] = True
    if STATE["proc"] is not None:
        STATE["proc"].kill()
    HUMAN.interrupt()
    return f"진행 중인 작업({STATE['stage']})을 중단하고 멈춥니다. 다시 실행하면 이어서 진행합니다."


def record_stop(reason):
    """중단 사실을 반복 기록에 남긴다."""
    if STATE["n"] is None:
        return
    try:
        record_event(STATE["n"], "stopped", reason=reason, during=STATE["stage"])
        rebuild_index()
    except Exception as e:
        print(f"[WARN] 중단 기록 실패: {e}")


def main():
    global HUMAN, MAX_ATTEMPTS
    args = parse_args()
    MAX_ATTEMPTS = args.max_attempts
    HUMAN = Human(None if args.no_telegram else NOTIFY_ENV_FILE)
    HUMAN.add_command(["status", "상태"], status_text)
    HUMAN.add_command(["stop", "정지"], request_stop)
    HUMAN.add_command(["stop now", "즉시정지", "즉시 정지"], request_stop_now)
    if HUMAN.telegram:
        print("Telegram 알림 사용 중 (끄려면 --no-telegram). 폰 명령: status / stop / stop now")
    STOP_FILE.unlink(missing_ok=True)

    if not (CONDA_ENV / "bin" / "python").exists():
        sys.exit(f"conda env를 찾을 수 없습니다: {CONDA_ENV}")
    ensure_research_repo()

    if args.reset:
        reset()
    goal, goal_changed = load_goal(args)
    RUNS_DIR.mkdir(parents=True, exist_ok=True)

    banner("RESEARCH GOAL")
    print(goal)

    n = current_iteration()
    if not goal_changed and n > 1 and load_review(n - 1) and load_review(n - 1)["verdict"] == "DONE":
        print("\n직전 반복에서 DONE 판정이 났습니다. 새 목표로 이어가려면 --goal \"새 목표\"로 실행하세요.")
        if args.autonomy == "full" or (ask("계속할까요? [y/N] ") or "").lower() != "y":
            return

    first_line = goal.splitlines()[0][:200] if goal else ""
    notify(f"▶ 연구 루프 시작 (iter_{current_iteration():03d}부터, 최대 {args.max_iters}회)\n목표: {first_line}")

    first = current_iteration()
    events_file = iter_dir(first) / "events.jsonl"
    resumed = any(json.loads(line)["stage"] not in ("goal", "session")
                  for line in read(events_file).splitlines() if line.strip())
    version = code_version()
    record_event(first, "session", version=version,
                 resumed_from=stage_of(first) if resumed else None)
    if resumed:
        print(f"iter_{first:03d}의 '{stage_of(first)}' 단계부터 이어서 진행합니다 (orchestrator {version}).")

    completed = 0
    finished = False
    while completed < args.max_iters:
        n = current_iteration()
        d = iter_dir(n)
        d.mkdir(parents=True, exist_ok=True)

        check_stop()
        if not (d / "plan.md").exists():
            set_stage(n, "GPT 계획")
            step_plan(args, goal_for(n), n)
        if not (d / "claude_report.md").exists():
            check_stop()
            set_stage(n, "계획 확인")
            action = step_checkpoint(args, n)
            if action == "quit":
                print("종료합니다. 다시 실행하면 여기서 이어집니다.")
                return
            if action == "replan":
                continue
            check_stop()
            set_stage(n, "Claude 구현/실험")
            step_claude(args, goal_for(n), n)
        if not (d / "review.json").exists():
            check_stop()
            needs_review, reason = review_decision(args, n)
            if needs_review:
                print(f"\nGPT 리뷰 진행: {reason}")
                set_stage(n, "GPT 리뷰")
                step_review(args, goal_for(n), n)
            else:
                step_skip_review(n, reason)

        # 리뷰 뒤 처리: 끊겼다가 다시 실행해도 각각 한 번만 한다
        set_stage(n, "리뷰 후 처리")
        review = load_review(n)
        flags = post_flags(n)
        if "paper" not in flags:
            if not review.get("skipped"):
                handle_paper(n, review)
            set_post_flag(n, "paper")
        if "commit" not in flags:
            step_commit(n, review)
            set_post_flag(n, "commit")
        if "milestone" not in flags:
            handle_milestone(n, review)
            set_post_flag(n, "milestone")
        if "notified" not in flags:
            if review["verdict"] == "CONTINUE" and review.get("skipped"):
                notify(f"✅ iter_{n:03d} 완료 (GPT 리뷰 생략)\n{review['one_line_summary']}")
            elif review["verdict"] == "CONTINUE":
                notify(
                    f"✅ iter_{n:03d} 완료 [{review['approach_status']}]\n"
                    f"{review['one_line_summary']}\n"
                    f"접근법: {review['approach_note']}\n"
                    f"다음: {review['next_task']}"
                )
            elif review["verdict"] == "DONE":
                notify(f"🎉 iter_{n:03d} 연구 목표 완료 (DONE)\n{review['one_line_summary']}")
            set_post_flag(n, "notified")

        if review["verdict"] == "NEEDS_HUMAN":
            set_stage(n, "사람 결정 대기")
            if not handle_needs_human(review, n):
                print("종료합니다. 다시 실행하면 이 질문부터 다시 묻습니다.")
                return

        save(d / "done.json", json.dumps({"verdict": review["verdict"], "time": now()}, indent=2))
        completed += 1
        if review["verdict"] == "DONE":
            banner("연구 목표 완료 (DONE)")
            finished = True
            break

    if not finished:
        notify(f"⏸ 최대 반복 수({args.max_iters})에 도달해 멈췄습니다. 다시 실행하면 이어서 진행합니다.")

    banner("루프 종료")
    print(f"요약: {INDEX_FILE}")
    print(f"기록: {RUNS_DIR}")


if __name__ == "__main__":
    try:
        main()
    except StopRequested as e:
        record_stop(str(e))
        print(f"\n멈췄습니다 ({e}). 다시 실행하면 완료되지 않은 단계부터 이어서 진행합니다.")
        notify(f"⏹ 멈췄습니다 ({e}, {STATE['stage']} 중). 다시 실행하면 이어서 진행합니다.")
        sys.exit(0)
    except AgentError as e:
        record_stop(f"오류: {e}")
        print(f"\n[ERROR] {e}")
        notify(f"❌ 오류로 멈췄습니다\n{e}\n다시 실행하면 이어서 진행합니다.")
        print("다시 실행하면 완료되지 않은 단계부터 이어서 진행합니다.")
        sys.exit(1)
    except KeyboardInterrupt:
        record_stop("Ctrl+C")
        print("\n중단됨. 다시 실행하면 완료되지 않은 단계부터 이어서 진행합니다.")
        sys.exit(130)
