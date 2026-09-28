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
    Claude    : 계획의 claude_tier (기본 standard, creative / heavy / standard / light)
    GPT 리뷰  : creative→deep, heavy/standard→normal, light→light

연구 진단·방법 개발·독립 확인은 항상 GPT 리뷰를 한다. 나머지는 review_mode가 full일 때 한다.
skip이어도 Claude의 SELF_CHECK가
PASS가 아니거나 권한 거부가 있으면 리뷰한다. 리뷰를 건너뛴 반복은 다음 계획 단계에서
GPT가 Claude 보고서를 직접 읽고 확인한다.

자동화 정도 (--autonomy):
    manual : 매 반복 계획을 사람이 확인
    smart  : (기본) 계획이 ask_human이거나 규칙 위반일 때만 확인, 나머지는 1순위 대안으로 진행
    full   : 계획 확인 없이 진행 (--auto와 같음)
    어떤 모드든 리뷰가 NEEDS_HUMAN이면 사람에게 묻는다.
    --no-ask-until "09:00": 그 시각까지는 사람이 없다고 보고 계획 확인과 NEEDS_HUMAN 모두
    묻지 않고 GPT 제안대로 진행한다 (물었을 지점은 "사람 부재로 자동 결정"으로 기록·알림).

접근법 관리: 계획은 대안 순위(alternatives)와 이번 approach를 내고, 리뷰는 approach를
success / improve / inconclusive / execution_failed / abandon으로 판정한다.
--max-attempts는 유효한 실험 이후 방향을 재평가할 기준이며, 자동 포기 횟수가 아니다.

코드 버전 관리: Claude는 research/ 폴더(자체 git 저장소)에서 작업한다.
접근법마다 approach/<approach_id> 브랜치를 쓴다. 가설 성공 여부와 코드 보존을 분리하고,
검토된 재사용 가능 커밋 또는 계획이 지정한 재사용 반복에서 새 브랜치를 만든다.
구현 종료·안전한 중단 뒤 소스 변경은 검증 판정과 무관하게 체크포인트 커밋으로 보존한다.
전체/모듈 재사용 승인은 GPT 리뷰로 별도 기록하며, 명시한 모듈은 다음 구현 전에 선별 반입한다.
소유 범위가 불명확한 기존 미커밋 작업은 stash·영구 ref·patch로 보관한다.
브랜치는 research/ 안에서만 바뀌므로 오케스트레이터, agent/ 기록, legacy/는 그대로다.
연구 커밋에는 iter_NNN 태그를 붙여 브랜치를 지워도 기록이 가리키는 커밋이 남게 하고,
stash한 작업은 반복 폴더에 patch로도 저장한다.

기록 보존: agent/의 요약·판단 파일은 반복이 끝날 때와 멈출 때 main 저장소의 main 브랜치에
자동 커밋한다 (기록 파일만 골라서 커밋하므로 작업 중인 코드 수정은 섞이지 않는다).
원본 로그(claude_stream.jsonl, *_codex.log 등)는 서버에만 둔다.

논문 추천: GPT 리뷰는 실제 결과로 가능성이 분명해진 방향에 한해 드물게 논문 1편을 추천한다.
링크가 열리고 중복이 아니면 agent/PAPERS.md에 쌓고 Telegram으로 알린다.

산출물은 agent/runs/iter_NNN/ 에 저장된다. 상태는 모두 파일에 있으므로, 중간에 끊기거나
orchestrator.py를 고친 뒤 다시 실행해도 완료되지 않은 단계부터 이어서 진행한다.
    - 반복 완료 표시는 done.json. 리뷰 뒤 처리(논문·커밋·마일스톤)도 각각 한 번만 한다.
    - Claude가 작업 중에 끊기면 같은 세션을 --resume으로 이어서 마무리한다.
    - 에이전트 호출이 실패하면(네트워크 등) 1분·5분·15분 뒤 다시 시도한다.
    - GPT·Claude 사용 한도에 걸리면 한도가 풀릴 때까지 --limit-poll-minutes마다 다시 시도하며
      최대 --limit-max-hours 기다렸다가 자동으로 이어간다 (Telegram으로 대기·재개 알림).
      월간 지출 한도는 예외로 즉시 중단한다. 계정 상태 확인 후 수동 재개한다.
    - 예전 반복 파일에 없는 필드는 기본값으로 채워 읽는다.
연구 목표 변경: --goal "새 목표"는 기록을 지우지 않고 새 챕터를 연다. 반복 번호는 이어지고,
새 목표의 첫 계획(deep)은 이전 기록에서 가져올 것을 정리한 뒤 새 목표 기준으로 다시 사고한다.
접근법 시도 횟수는 목표별로 센다. 목표 이력은 agent/GOALS.json. --reset은 완전히 새로 시작할 때만.

정지: 터미널 Ctrl+C, `touch agent/STOP`(현재 단계 후), Telegram `stop` / `stop now` / `status`.

사용 예:
    python orchestrator.py                     # 횟수 제한 없이 진행, smart: 애매할 때만 확인
    python orchestrator.py --max-iters 3       # 이번 실행만 최대 3회로 제한
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
import contextlib
import fcntl
import hashlib
import json
import os
import re
import signal
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import urllib.request
import uuid

from notifier import Human
from claude_usage import summarize_stream, usage_report
import research_history as history
import gpt_usage
from presentation import notice, iteration_result

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
# main 저장소에 자동 커밋하는 연구 기록 (원본 로그는 .gitignore로 제외)
RECORD_PATHS = (
    "agent/GOAL.md", "agent/GOALS.json", "agent/INDEX.md", "agent/DECISIONS.md",
    "agent/JOURNEY.md", "agent/PAPERS.md", "agent/RESEARCH_LOG.md", "agent/runs", "agent/archive",
    "agent/CODE_ASSETS.md",
    "agent/LIMITATIONS.md", "agent/LIMITATIONS.json", "agent/interventions",
    # 오케스트레이터 도입 전 수동 실행 기록
    "agent/GPT_PLAN.md", "agent/CLAUDE_REPORT.md", "agent/GPT_REVIEW.md",
)
RECORD_BRANCHES = ("main", "master")
# 이 파일이 생기면 현재 단계를 마친 뒤 멈춘다 (Telegram stop도 이 파일을 만든다)
STOP_FILE = AGENT_DIR / "STOP"
# 에이전트 호출 실패 시 재시도 간격(초)
RETRY_DELAYS = (60, 300, 900)
LOG_FILE = AGENT_DIR / "RESEARCH_LOG.md"
TIERS_FILE = AGENT_DIR / "tiers.json"
RESOURCE_POLICY_FILE = AGENT_DIR / "RESOURCE_POLICY.md"
RESEARCH_POLICY_FILE = AGENT_DIR / "RESEARCH_POLICY.md"
CLAUDE_USAGE_POLICY_FILE = AGENT_DIR / "CLAUDE_USAGE_POLICY.md"
REPORTING_STYLE_FILE = AGENT_DIR / "REPORTING_STYLE.md"
CODE_ASSETS_FILE = AGENT_DIR / "CODE_ASSETS.md"
LIMITATIONS_FILE = AGENT_DIR / "LIMITATIONS.json"
LIMITATIONS_REPORT = AGENT_DIR / "LIMITATIONS.md"
RESUME_FILE = AGENT_DIR / "RESUME.md"
INTERVENTIONS_DIR = AGENT_DIR / "interventions"
LOCK_FILE = AGENT_DIR / ".orchestrator.lock"
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


class UsageLimitError(RetryableError):
    """구독 사용 한도 초과. 한도가 풀릴 때까지 기다렸다 다시 시도한다."""

    def __init__(self, message, output="", *, reset_at=None, limit_type=None):
        super().__init__(message, output)
        self.reset_at = reset_at
        self.limit_type = limit_type


class SpendLimitError(AgentError):
    """월간 지출 한도. 자동 재시도·지출 한도 인상 없이 중단한다."""


SPEND_LIMIT_PATTERN = re.compile(r"monthly\s+(?:spend(?:ing)?|cost)\s+limit", re.IGNORECASE)


# 한도 초과 에러 문구 (실제 문구를 보면 여기에 맞춰 다듬는다)
USAGE_LIMIT_PATTERN = re.compile(
    r"usage limit|rate.?limit|limit reached|hit your (usage )?limit|quota|too many requests"
    r"|\b429\b|resets? (at|in)|try again (at|in)|5-hour|weekly limit|overloaded",
    re.IGNORECASE,
)
# 사용 한도 대기 설정 (--limit-poll-minutes, --limit-max-hours로 덮어씀)
LIMIT = {"poll": 30 * 60, "max": 8 * 60 * 60}


def failure_error(message, output, *, limit_info=None):
    """실제 거절된 구독 window를 우선한다. 경고/불명확한 문구로 지출 한도를 우회하지 않는다."""
    info = limit_info if isinstance(limit_info, dict) else {}
    kind = info.get("rateLimitType")
    if info.get("status") == "rejected" and kind in ("five_hour", "seven_day"):
        reset_at = info.get("resetsAt")
        # 외부 입력의 비정상 timestamp가 대기/표시 경로를 중단시키지 않게 검증한다.
        if (isinstance(reset_at, bool) or not isinstance(reset_at, (int, float))
                or not 0 < reset_at < 253402300799):
            reset_at = None
        label = "5시간" if kind == "five_hour" else "주간"
        return UsageLimitError(f"{label} 사용 한도 도달: {message}", output,
                               reset_at=reset_at, limit_type=kind)
    if SPEND_LIMIT_PATTERN.search(output or ""):
        return SpendLimitError(
            f"월간 지출 한도로 중단 (자동 재시도 안 함): {message}\n"
            "Claude 계정의 /usage 또는 Settings > Usage에서 제한을 확인한 뒤 재실행하세요. "
            "지출 한도는 자동으로 올리지 않습니다."
        )
    if USAGE_LIMIT_PATTERN.search(output or ""):
        return UsageLimitError(f"사용 한도 초과로 보임: {message}", output)
    return RetryableError(message, output)


class StopRequested(Exception):
    pass


# 지금 무엇을 하고 있는지 (Telegram status, 중단 기록용)
STATE = {"n": None, "stage": "시작 전", "since": None, "proc": None, "stop_now": False,
         "limit_wait": None, "limit_retry_at": None}


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


def usage_retry_delay(error, waited):
    """확인된 초기화 시각+60초까지 기다리고, 없거나 지난 시각이면 기존 주기로 확인한다."""
    delay = LIMIT["poll"]
    if error.reset_at is not None and error.reset_at > time.time():
        delay = int(error.reset_at - time.time()) + 61
    return max(0, min(delay, LIMIT["max"] - waited))


def with_retries(what, fn):
    """fn()을 실행한다.

    - 사용 한도 초과: 알려진 초기화 시각 이후 재시도, 미확인/계속 거절이면 poll 주기. 최대 max.
    - 그 밖의 일시적 실패(RetryableError): RETRY_DELAYS 간격으로 다시 시도.
    """
    last = None
    attempt = 0
    waited = 0
    limited = False
    while True:
        if limited and waited >= LIMIT["max"]:
            raise AgentError(f"{what}: 사용 한도 대기 상한({LIMIT['max'] / 3600:g}시간)에 도달함. 마지막 오류: {last}")
        try:
            result = fn()
        except UsageLimitError as e:
            last = e
            if waited >= LIMIT["max"]:
                raise AgentError(f"{what}: 사용 한도가 {waited // 3600}시간 동안 풀리지 않음. 마지막 오류: {e}")
            delay = usage_retry_delay(e, waited)
            retry_at = datetime.datetime.fromtimestamp(time.time() + delay)
            reaches_budget = waited + delay >= LIMIT["max"]
            action = "대기 상한으로 종료" if reaches_budget else "재시도"
            label = {"five_hour": "5시간 사용 한도", "seven_day": "주간 사용 한도"}.get(
                e.limit_type, "일시적 사용 한도")
            hours = LIMIT["max"] / 3600
            print(f"\n[한도] {what}: {label} → {retry_at:%m-%d %H:%M:%S} {action} (최대 {hours:g}시간 대기)")
            notify(notice(f"⏳ {what} | {label}로 대기", [
                ("현재", "완료된 작업·세션을 보존하고 대기합니다. 지출 한도는 올리지 않습니다."),
                ("다음", f"{retry_at:%m-%d %H:%M:%S}에 {action}합니다. 초기화 시각이 없거나 이후에도 거절되면 "
                         f"{LIMIT['poll'] // 60}분 주기로 확인합니다. 최대 총 {hours:g}시간 대기합니다."),
            ]))
            if STATE["n"] is not None:
                record_event(STATE["n"], "limit_wait", what=what, limit_type=e.limit_type,
                             reset_at=e.reset_at, retry_at=retry_at.isoformat())
            if not limited:
                STATE["limit_wait"] = (what, datetime.datetime.now())
            limited = True
            STATE["limit_retry_at"] = None if reaches_budget else retry_at
            sleep_with_stop(delay)
            waited += delay
            continue
        except RetryableError as e:
            last = e
            if attempt >= len(RETRY_DELAYS):
                raise AgentError(f"{what}: {len(RETRY_DELAYS)}번 다시 시도했지만 실패. 마지막 오류: {last}")
            delay = RETRY_DELAYS[attempt]
            attempt += 1
            minutes = delay // 60
            print(f"\n[재시도] {what} 실패 → {minutes}분 뒤 다시 시도 ({attempt}/{len(RETRY_DELAYS)})")
            notify(notice(f"🔁 {what} | 일시적 실패", [
                ("오류", str(last)),
                ("다음", f"{minutes}분 뒤 다시 시도합니다 ({attempt}/{len(RETRY_DELAYS)})."),
            ]))
            sleep_with_stop(delay)
            continue

        if limited:
            minutes = waited // 60
            print(f"\n[한도] 사용 한도가 풀려 {what}을(를) 이어갑니다 ({minutes}분 대기)")
            notify(f"▶ 사용 한도가 풀려 {what}을(를) 이어갑니다 ({minutes}분 대기)")
            if STATE["n"] is not None:
                record_event(STATE["n"], "limit_resume", what=what, minutes=minutes)
        STATE["limit_wait"] = None
        STATE["limit_retry_at"] = None
        return result


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


def save_atomic(path, text):
    """중단돼도 제어 상태 파일이 반쪽짜리 JSON으로 남지 않게 게시한다."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


@contextlib.contextmanager
def orchestrator_lock():
    LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    with LOCK_FILE.open("a") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise AgentError("orchestrator가 이미 실행 중입니다. 중단·종료를 확인한 뒤 다시 실행하세요.")
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def pending_interventions():
    return [p for p in sorted(INTERVENTIONS_DIR.glob("*/transaction.json"))
            if (load_json(p) or {}).get("status") == "preparing"]


def queue_replan(text):
    if not text.strip():
        raise AgentError("보완 지시가 비어 있습니다.")
    if RESUME_FILE.exists() or pending_interventions():
        raise AgentError("미적용 보완 지시가 있습니다. agent/RESUME.md를 확인하거나 먼저 적용하세요.")
    save_atomic(RESUME_FILE, text.strip() + "\n")


def apply_pending_replan():
    """실험 기록을 삭제하지 않고 새 반복으로 전환한다. 재시작 시 같은 전환을 마무리한다."""
    pending = pending_interventions()
    if len(pending) > 1:
        raise AgentError("미완료 보완 전환이 여러 개입니다. agent/interventions를 확인하세요.")
    if pending:
        tx_file = pending[0]
        tx = load_json(tx_file)
    else:
        if not RESUME_FILE.exists():
            return None
        instructions = read(RESUME_FILE)
        if not instructions.strip():
            raise AgentError("agent/RESUME.md가 비어 있습니다. 지시를 작성한 뒤 재개하세요.")
        source = current_iteration()
        # 아직 시작하지 않은 빈 반복은 그대로 사용한다. 산출물이 있으면 다음 번호로 전환한다.
        active = iter_dir(source).exists() and any(iter_dir(source).iterdir())
        target = source + 1 if active else source
        if active and iter_dir(target).exists():
            raise AgentError(f"전환 대상 iter_{target:03d}가 이미 있습니다. 덮어쓰지 않습니다.")
        identity = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_") + uuid.uuid4().hex[:8]
        tx_file = INTERVENTIONS_DIR / identity / "transaction.json"
        tx = {"id": identity, "status": "preparing", "source_iteration": source if active else None,
              "target_iteration": target, "source_stage": stage_of(source) if active else "새 계획",
              "instructions": instructions, "time": now()}
        save_atomic(tx_file, json.dumps(tx, ensure_ascii=False, indent=2))

    target = tx["target_iteration"]
    source = tx["source_iteration"]
    if source is not None:
        old = iter_dir(source)
        if ((old / "code_baseline.json").exists() and not (old / "checkpoint.json").exists()
                and not (old / "review.json").exists()):
            checkpoint_code(source, "before_replan")
    d = iter_dir(target)
    marker = load_json(d / "intervention.json")
    if marker and marker.get("id") != tx["id"]:
        raise AgentError("다른 보완 지시의 전환 대상과 충돌했습니다. 기존 기록은 유지합니다.")
    save_atomic(tx_file.parent / "request.md", tx["instructions"])
    save_atomic(d / "intervention.json", json.dumps(tx, ensure_ascii=False, indent=2))
    if source is not None:
        superseded = {"intervention": tx["id"], "successor": target, "time": tx["time"],
                      "reason": "사용자 보완으로 재계획. 성공·실패 판정 아님", "source_stage": tx["source_stage"]}
        save_atomic(iter_dir(source) / "superseded.json", json.dumps(superseded, ensure_ascii=False, indent=2))
    # 파일을 변경하는 동안 새 지시가 들어왔다면 새 지시는 남겨 다음 경계에서 별도로 처리한다.
    if RESUME_FILE.exists() and read(RESUME_FILE) == tx["instructions"]:
        RESUME_FILE.replace(tx_file.parent / "consumed_request.md")
    tx["status"] = "applied"
    save_atomic(tx_file, json.dumps(tx, ensure_ascii=False, indent=2))
    rebuild_index()
    print(f"보완 지시 적용: iter_{target:03d}에서 GPT 재계획 → 새 Claude 세션. 원본 기록·코드는 보존합니다.")
    return target


def intervention_context(n):
    starts = [i for i in existing_iterations() if goal_start(n) <= i <= n
              and (iter_dir(i) / "intervention.json").exists()]
    tx = load_json(iter_dir(starts[-1]) / "intervention.json") if starts else None
    if not tx:
        return "없음"
    source = tx["source_iteration"]
    origin = f"agent/runs/iter_{source:03d}/" if source is not None else "이전 미완료 반복 없음"
    return (f"보완 ID: {tx['id']}\n이전 기록: {origin}\n중단 당시 단계: {tx['source_stage']}\n"
            f"현재 사용자 지시:\n{tx['instructions']}\n"
            "이전 계획은 참고 후보이며 자동으로 이어서 실행하지 않는다. 현재 지시에 맞춰 재계획한다.\n"
            "기존 소스·부분 산출물은 먼저 확인하고 검증해 재사용한다. 새 결과는 이번 반복 경로에 저장한다.\n"
            "이미 검증 완료된 일회성 보완 작업은 반복하지 않는다. 이후 반복에도 유지할 운영 기준은 계속 적용한다.\n"
            "이전 세션·완료 표시·실험 결과를 삭제하거나 새 결과로 덮어쓰지 않는다.")


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


def run_streaming(cmd, log_path, timeout, env, on_line, cwd=PROJECT_DIR, *, stdin_text=None):
    """출력은 실시간 기록하고, 긴 입력은 UTF-8 원문 그대로 임시 파일 stdin으로 전달한다."""
    timed_out = threading.Event()
    tail = []

    with contextlib.ExitStack() as stack:
        log_f = None
        try:
            log_f = stack.enter_context(log_path.open("a", encoding="utf-8"))
            input_source = subprocess.DEVNULL
            if stdin_text is not None:
                # PIPE에 큰 입력을 동기 write하면 stdout과 서로 막힐 수 있다. 닫으면 제거되는
                # 비공개 임시 파일을 이용하며, 원문을 축약하거나 영구 로그에 복제하지 않는다.
                payload = stdin_text.encode("utf-8")
                input_source = stack.enter_context(tempfile.TemporaryFile(mode="w+b"))
                input_source.write(payload)
                input_source.seek(0)
                log_f.write(f"[input] transport=stdin bytes={len(payload)} "
                            f"sha256={hashlib.sha256(payload).hexdigest()}\n")
                log_f.flush()
            proc = subprocess.Popen(
                cmd,
                cwd=cwd,
                env=env,
                text=True,
                encoding="utf-8",
                stdin=input_source,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                bufsize=1,
                start_new_session=True,
            )
        except OSError as e:
            # E2BIG·실행 파일 누락·권한·임시 파일 오류도 기록/Telegram 경로로 전달한다.
            # 전체 cmd/env에는 프롬프트·민감 값이 들어갈 수 있으므로 오류에 넣지 않는다.
            message = (f"{Path(cmd[0]).name} 실행 준비 실패 (errno={e.errno}): {e.strerror}. "
                       f"로그: {log_path}")
            if log_f is not None:
                with contextlib.suppress(OSError):
                    log_f.write(f"[launch_error] {message}\n")
            raise AgentError(message) from e
        STATE["proc"] = proc

        def kill():
            timed_out.set()
            kill_agent_group(proc)

        # 0은 시간 제한 없음. 명시적으로 설정한 양수 timeout만 적용한다.
        timer = threading.Timer(timeout, kill) if timeout > 0 else None
        if timer is not None:
            timer.start()
        try:
            for line in proc.stdout:
                log_f.write(line)
                log_f.flush()
                tail = (tail + [line])[-20:]
                on_line(line)
            proc.wait()
        except KeyboardInterrupt:
            kill_agent_group(proc)
            proc.wait()
            raise
        except BaseException:
            kill_agent_group(proc)
            proc.wait()
            raise
        finally:
            if timer is not None:
                timer.cancel()
            proc.stdout.close()
            STATE["proc"] = None

    if STATE["stop_now"]:
        raise StopRequested("즉시 정지 요청")
    if timed_out.is_set():
        raise AgentError(f"{cmd[0]} 시간 초과 ({timeout}s). 로그: {log_path}")
    if proc.returncode != 0:
        raise failure_error(f"{cmd[0]} 종료 코드 {proc.returncode}. 로그: {log_path}", "".join(tail))


def kill_agent_group(proc):
    """이번 호출이 만든 전용 프로세스 그룹만 종료한다 (다른 사용자의 작업은 대상 아님)."""
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


# --------------------------------------------------
# 에이전트 호출
# --------------------------------------------------

GPT_TIERS = ["deep", "normal", "light"]
CLAUDE_TIERS = ["creative", "heavy", "standard", "light"]
# 같은 접근법의 유효한 실험을 재평가하는 기준 (--max-attempts로 덮어씀)
MAX_ATTEMPTS = 3
# Claude 작업 등급 → 그 결과를 검토할 GPT 리뷰 등급
REVIEW_TIER_FOR_CLAUDE = {"creative": "deep", "heavy": "normal", "standard": "normal", "light": "light"}


def tier_spec(agent, tier):
    return json.loads(read(TIERS_FILE))[agent][tier]


def resource_context(args):
    """재시도·세션 재개를 포함한 모든 호출에 최신 사용자 자원 정책을 전달한다."""
    policy = read(RESOURCE_POLICY_FILE).strip()
    if not policy:
        raise AgentError(f"연구 자원 정책이 없거나 비어 있음: {RESOURCE_POLICY_FILE}")
    research_policy = read(RESEARCH_POLICY_FILE).strip()
    if not research_policy:
        raise AgentError(f"연구 운영 정책이 없거나 비어 있음: {RESEARCH_POLICY_FILE}")
    usage_policy = read(CLAUDE_USAGE_POLICY_FILE).strip()
    if not usage_policy:
        raise AgentError(f"Claude 사용량 정책이 없거나 비어 있음: {CLAUDE_USAGE_POLICY_FILE}")
    visible = args.gpus if args.gpus is not None else os.environ.get("CUDA_VISIBLE_DEVICES", "미지정 (실행 전 확인)")
    timeout = f"{args.claude_timeout}초 (명시된 실행 제한)" if args.claude_timeout else "시간 제한 없음"
    return (
        f"=== 현재 사용자 자원 정책 (이전 계획의 임의 시간 상한보다 우선) ===\n{policy}\n\n"
        f"=== 현재 연구 운영 정책 (이전 자동 포기·코드 폐기 규칙보다 우선) ===\n{research_policy}\n\n"
        f"=== 현재 Claude 사용량 정책 (필수 검증·GPU 활용 유지) ===\n{usage_policy}\n\n"
        f"=== 사람이 읽는 설명·보고서의 표현 기준 (실행·검증 기준은 유지) ===\n{read(REPORTING_STYLE_FILE)}\n\n"
        f"=== 현재 실행 설정 ===\nCUDA_VISIBLE_DEVICES: {visible}\n"
        f"Claude 단계 timeout: {timeout}\n\n"
    )


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
    input_text = resource_context(args) + prompt
    cmd.append("-")  # 전체 지시문은 stdin으로. 인자 크기 제한 때문에 내용을 자르지 않는다.

    out_file.unlink(missing_ok=True)
    try:
        run_streaming(
            cmd, log_path, args.gpt_timeout, agent_env(args.gpus),
            on_line=lambda line: print(f"  [gpt] {line}", end="", flush=True),
            stdin_text=input_text,
        )
    finally:
        if log_path.exists():
            try:
                usage = gpt_usage.summarize_log(log_path)
                path = log_path.with_name(log_path.stem.replace("_codex", "") + "_usage.json")
                save_atomic(path, json.dumps(usage, ensure_ascii=False, indent=2))
            except (OSError, ValueError) as e:
                print(f"[WARN] GPT 사용량 요약 저장 실패 (원본 로그 보존): {e}")

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
        "--output-format", "stream-json", "--input-format", "text", "--verbose",
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
    input_text = resource_context(args) + prompt

    result = {}
    latest_limit = {}

    def on_line(line):
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            print(f"  [claude] {line}", end="", flush=True)
            return

        if event.get("type") == "rate_limit_event":
            # 이번 호출의 최신 상태만 사용해 과거 로그나 warning으로 오분류하지 않는다.
            latest_limit.clear()
            info = event.get("rate_limit_info")
            if isinstance(info, dict):
                latest_limit.update(info)

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

    try:
        try:
            run_streaming(cmd, log_path, args.claude_timeout, agent_env(args.gpus), on_line,
                          cwd=RESEARCH_DIR, stdin_text=input_text)
        except (UsageLimitError, SpendLimitError) as e:
            # 비정상 종료 코드에서도 stream으로 받은 정확한 한도 종류를 보존한다.
            raise failure_error(str(e), getattr(e, "output", "") or str(e),
                                limit_info=latest_limit) from e
    finally:
        # 실패·timeout·사용자 정지도 집계한다. 원본을 재집계하므로 누적값/재시도를 중복 합산하지 않는다.
        if log_path.exists():
            try:
                usage = summarize_stream(log_path)
                usage.update(last_requested_tier=tier, updated_at=now())
                save_atomic(log_path.with_name("claude_usage.json"),
                            json.dumps(usage, ensure_ascii=False, indent=2))
            except (OSError, ValueError) as e:
                # 집계 실패가 원래 실행 결과나 중단 이유를 가리지 않게 한다.
                print(f"[WARN] Claude 사용량 요약 저장 실패 (원본 로그 보존): {e}")

    if not result:
        raise RetryableError(f"Claude result 이벤트 없음. 로그: {log_path}")
    if result.get("is_error"):
        # 오류로 끝난 결과를 보고서로 저장하면 다음 실행에서 Claude 단계를 건너뛴다. 재시도한다.
        text = str(result.get("result", ""))
        raise failure_error(f"Claude가 오류로 종료: {text[:300]}", text, limit_info=latest_limit)
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


def commit_records(message):
    """agent/ 기록 파일만 main 저장소에 커밋한다. 기록은 사라질 수 있는 브랜치에 두지 않는다."""
    branch = git("rev-parse", "--abbrev-ref", "HEAD")[1].strip()
    if branch not in RECORD_BRANCHES:
        print(f"[WARN] main 저장소가 '{branch}' 브랜치라 연구 기록을 커밋하지 않았습니다. "
              f"main으로 돌아간 뒤 다시 실행하면 함께 커밋됩니다.")
        return
    paths = [p for p in RECORD_PATHS if (PROJECT_DIR / p).exists()]
    if not paths:
        return
    git("add", "--", *paths)
    if git("diff", "--cached", "--quiet", "--", *paths)[0] == 0:
        return
    # 경로를 지정해 커밋하면 다른 staged 변경(작업 중인 코드 등)은 섞이지 않는다
    code, out = git("commit", "-q", "-m", message, "--", *paths)
    if code:
        print(f"[WARN] 연구 기록 커밋 실패: {out}")
    else:
        print(f"기록 커밋: {git('rev-parse', '--short', 'HEAD')[1].strip()} {message}")


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
    "experiment_role": "legacy", "research_question": "", "contribution_path": "",
    "baseline_plan": "", "reuse_iteration": 0, "continuation_reason": "",
    "limitation_ids": [], "reuse_assets": [],
}
REVIEW_DEFAULTS = {
    "verdict": "CONTINUE", "approach_status": "", "approach_note": "", "commit_worthy": False,
    "commit_message": "", "one_line_summary": "", "next_task": "", "next_plan_tier": "normal",
    "reason": "", "review_markdown": "", "paper_recommendation": {}, "milestone": {},
    "valid_experiment": None, "reusable_code": None, "failure_scope": "", "goal_progress": "",
    "blocking_issues": [], "reuse_issues": [], "deferred_issues": [],
    "limitation_updates": [], "code_assets": [],
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
    if (iter_dir(n) / "intervention.json").exists():
        return "deep"
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
    if (d / "intervention.json").exists():
        return True, "사용자 보완 후 첫 반복은 전체 리뷰 필요"
    if args.always_review:
        return True, "--always-review 지정"
    if (load_plan(n) or {}).get("experiment_role") in {"diagnostic", "method", "confirmatory"}:
        return True, "연구 가설·방법·독립 확인 실험은 전체 리뷰 필요"
    entry = approach_ledger(upto=n).get(approach_key(load_plan(n)))
    if entry and entry["valid_experiments"] >= MAX_ATTEMPTS:
        return True, f"'{entry['name']}' 유효한 실험 {entry['valid_experiments']}회 이후 방향 재평가"
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


def validate_limitation_updates(review):
    seen = set()
    for update in review.get("limitation_updates", []):
        identity = update.get("id", "")
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,59}", identity) or identity in seen:
            raise AgentError(f"중복 또는 잘못된 한계 주장 id: {identity}")
        seen.add(identity)
        if update.get("status") not in {"candidate", "observed", "validated", "rejected"}:
            raise AgentError(f"잘못된 한계 주장 상태: {identity}")
        if not update.get("claim", "").strip() or not update.get("evidence"):
            raise AgentError(f"한계 주장과 근거 파일/출처가 필요합니다: {identity}")
        if update["status"] == "validated" and (
            review.get("valid_experiment") is not True or review.get("blocking_issues")
            or not update.get("usage_checks")
        ):
            raise AgentError(f"한계 재현 확인에는 유효한 실험·사용법 검증·현재 결론 무결성이 필요합니다: {identity}")


def limitation_registry(upto=None):
    """사용자 초기 판단과 반복별 리뷰를 합성한다. 과거 주장·정정 원문은 삭제하지 않는다."""
    entries = {entry["id"]: entry.copy() for entry in (load_json(LIMITATIONS_FILE) or {}).get("claims", [])}
    for n in existing_iterations():
        if upto is not None and n > upto:
            break
        review = load_review(n) or {}
        validate_limitation_updates(review)
        for update in review.get("limitation_updates", []):
            entries[update["id"]] = {**update, "goal_start": goal_start(n), "review_iteration": n}
    return entries


def limitations_text():
    lines = ["# 한계 주장과 검증 근거", "", "초기 판단: LIMITATIONS.json. 이후 변경 근거: 각 반복의 review.json/limitation_updates.",
             "validated는 명시한 조건에서 사용·평가 오류를 통제해 성능 문제를 재현했다는 뜻이며, 내부 원인 확정이 아니다.", ""]
    for identity, entry in limitation_registry().items():
        lines += [f"## {identity} — {entry['status']}", "", entry["claim"], "",
                  f"- 적용 목표 시작: iter_{entry.get('goal_start', 1):03d}"]
        if entry.get("review_iteration"):
            lines.append(f"- 최신 리뷰: agent/runs/iter_{entry['review_iteration']:03d}/review.json")
        for key, title in (("evidence", "근거"), ("usage_checks", "사용·평가 검증"), ("remaining_questions", "미해결")):
            lines += [f"- {title}: {value}" for value in entry.get(key, [])]
        lines.append("")
    return "\n".join(lines) + "\n"


def method_gate_errors(n, plan):
    if plan.get("experiment_role") not in {"method", "confirmatory"}:
        return []
    identities = plan.get("limitation_ids", [])
    if not identities:
        return ["방법 개발·확인 실험은 검증된 한계 주장 limitation_ids를 지정해야 합니다."]
    entries = limitation_registry(upto=n - 1)
    return [f"한계 {identity}: 현재 목표에서 재현 확인(validated)된 근거가 없습니다. 진단 계획이 먼저 필요합니다."
            for identity in identities if entries.get(identity, {}).get("status") != "validated"
            or entries.get(identity, {}).get("goal_start") != goal_start(n)]


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
            "valid_experiments": 0, "unclassified_experiments": 0,
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
            if review.get("valid_experiment") is True:
                entry["valid_experiments"] += 1
            elif review.get("valid_experiment") is None:
                entry["unclassified_experiments"] += 1
        elif (iter_dir(n) / "superseded.json").exists():
            entry["status"] = "사용자 보완으로 전환 (검증 미완료)"
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
    return (iter_dir(n) / "done.json").exists() or (iter_dir(n) / "superseded.json").exists()


def post_flags(n):
    """리뷰 뒤 처리(논문·커밋·마일스톤·알림) 중 이미 한 것. 재실행 시 중복을 막는다."""
    return load_json(iter_dir(n) / "post.json") or {}


def set_post_flag(n, key):
    flags = post_flags(n)
    flags[key] = now()
    save(iter_dir(n) / "post.json", json.dumps(flags, indent=2))


def stage_of(n):
    d = iter_dir(n)
    if (d / "superseded.json").exists():
        return "사용자 보완으로 전환"
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
    dirty = git("status", "--porcelain", "--", "orchestrator.py", "notifier.py", "presentation.py", "claude_usage.py", "gpt_usage.py", "research_history.py", "agent/prompts",
                "agent/tiers.json", "agent/claude_settings.json", "agent/RESOURCE_POLICY.md",
                "agent/RESEARCH_POLICY.md", "agent/CLAUDE_USAGE_POLICY.md", "agent/REPORTING_STYLE.md")[1].strip()
    return f"{sha}+수정" if dirty else sha


def rebuild_index():
    lines = ["# Research Index", ""]
    goal_starts = {g["start_iter"]: (i, g["goal"]) for i, g in enumerate(load_goals(), 1)}
    for n in existing_iterations():
        if n in goal_starts:
            k, text = goal_starts[n]
            lines += ["", f"### 연구 목표 {k} (iter_{n:03d}부터): {text.splitlines()[0][:200] if text else ''}", ""]
        review = load_review(n)
        superseded = load_json(iter_dir(n) / "superseded.json")
        if superseded:
            lines.append(f"- iter_{n:03d} [사용자 보완으로 전환 → iter_{superseded['successor']:03d}] "
                         f"기존 기록 보존, 성공·실패 판정 아님 ({superseded['source_stage']})")
            continue
        if review is None:
            suffix = " — 사용자 보완 반영, GPT 재계획부터" if (iter_dir(n) / "intervention.json").exists() else ""
            lines.append(f"- iter_{n:03d} [진행 중]{suffix}")
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
        lines += ["", "## 이전 목표들의 접근법 (참고용, 현재 목표의 재평가 횟수에는 안 들어감)", ""]
        for entry in earlier.values():
            lines.append(f"- {entry['name']} [{entry['branch']}]: {entry['attempts']}회, 최근 판정: {entry['status']}, "
                         f"커밋: {', '.join(entry['commits']) or '없음'}")
    if ledger:
        lines += ["", f"## 접근법 기록 — 현재 목표 (유효한 실험 {MAX_ATTEMPTS}회부터 방향 재평가)", ""]
        for entry in ledger.values():
            iters = ", ".join(f"iter_{i:03d}" for i in entry["iters"])
            commits = ", ".join(entry["commits"]) or "없음"
            lines.append(
                f"- {entry['name']} [{entry['branch']}]: {entry['attempts']}회 ({iters}), "
                f"유효한 실험 {entry['valid_experiments']}회, 미분류 {entry['unclassified_experiments']}회, "
                f"최근 판정: {entry['status']}, 커밋: {commits}"
            )
        lines += ["", f"현재 연구 브랜치: {current_branch()} (코드 위치: {RESEARCH_DIR})"]
        last_plan = load_plan(existing_iterations()[-1]) or {}
        if last_plan.get("alternatives"):
            lines += ["", "### 최근 계획의 대안 순위", ""]
            lines += [f"{i}. {alt}" for i, alt in enumerate(last_plan["alternatives"], 1)]
    save(INDEX_FILE, "\n".join(lines) + "\n")
    save(CODE_ASSETS_FILE, code_assets_text())
    save(LIMITATIONS_REPORT, limitations_text())
    rebuild_decisions()


def code_assets_text():
    """성공·실패와 관계없이 보존된 코드의 위치와 재사용 판정을 모은다."""
    lines = ["# 연구 코드 보존·재사용 목록", "", "보관본은 검증 완료를 뜻하지 않는다. 재사용 전 해당 리뷰의 결함을 확인한다.", ""]
    for n in existing_iterations():
        d = iter_dir(n)
        review = load_review(n) or {}
        commit = load_json(d / "commit.json") or load_json(d / "checkpoint.json")
        archive = load_json(d / "code_archive.json")
        if commit:
            if reusable_commit(n):
                label = "재사용 가능" if review.get("reusable_code") is True else "과거 success: 기존 정책에 따라 재사용 가능"
            else:
                label = "재사용 미승인: 리뷰 확인 필요"
            lines.append(f"- iter_{n:03d}: 커밋 `{commit['sha']}` ({label}), 리뷰: `{d.relative_to(PROJECT_DIR)}/review.md`")
            for asset in review.get("code_assets", []):
                lines.append(f"  - 모듈 {', '.join(asset['paths'])}: {asset['status']} — {asset['reason']}; "
                             f"검증: {'; '.join(asset['checks'])}")
            if commit.get("unpreserved_paths"):
                lines.append(f"  - 자동 커밋 제외/별도 확인: {', '.join(commit['unpreserved_paths'])}")
        if archive:
            lines.append(f"- iter_{n:03d} 전환 전 보관: `{archive['source_branch']}` → `{archive['ref']}` "
                         f"(stash `{archive['stash']}`); 미추적 파일이 있으면 해당 ref의 `^3` tree에 있다. "
                         f"기록: `{d.relative_to(PROJECT_DIR)}/code_archive.json`")
        if (d / "code_recovery.md").exists():
            lines.append(f"- iter_{n:03d} 선별 복구 출처·주의사항: `{d.relative_to(PROJECT_DIR)}/code_recovery.md`")
    return "\n".join(lines) + "\n"


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
    superseded = load_json(d / "superseded.json")
    if superseded:
        lines += [f"사용자 보완으로 iter_{superseded['successor']:03d}에서 재계획. 아래는 보존된 이전 기록이며 실패 판정이 아니다.", ""]
    if (d / "intervention.json").exists():
        lines += [f"사용자 보완 원문: agent/runs/iter_{n:03d}/intervention.json", ""]
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
            for concern in ev.get("concerns") or []:
                if concern != plan_question:
                    lines.append(f"  - 원래 물어볼 이유: {concern}")
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
                branch_text += f"; 이전 브랜치 미커밋 작업은 stash와 `stashed.patch`로 보관"
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
            for key, label in (("goal_progress", "목표 진전"), ("failure_scope", "판정 범위")):
                if review.get(key):
                    lines.append(f"  - {label}: {review[key]}")
            for key, label in (("blocking_issues", "현재 결론 무효"), ("reuse_issues", "재사용 전 수정"),
                               ("deferred_issues", "추후 개선")):
                for issue in review.get(key, []):
                    lines.append(f"  - {label}: {issue}")
            if review.get("next_task"):
                lines.append(f"  - 다음: {review['next_task']}")
        elif stage == "review_skipped":
            lines.append(f"- ⏭ 리뷰 생략: {ev.get('reason')}")
        elif stage == "commit":
            lines.append(f"- 💾 **커밋** `{ev.get('sha')}` ({ev.get('branch')}): {ev.get('message')}")
        elif stage == "checkpoint":
            lines.append(f"- 💾 **개발 이력 체크포인트** `{ev.get('sha')}`: {ev.get('reason')} (검증 승인 아님)")
            if ev.get("excluded"):
                lines.append(f"  - 자동 커밋 제외·확인 필요: {', '.join(ev['excluded'])}")
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
        elif stage == "limit_wait":
            lines.append(f"- ⏳ 사용 한도 도달 ({ev.get('what')}) → 대기")
        elif stage == "limit_resume":
            lines.append(f"- ▶ 사용 한도가 풀려 재개 ({ev.get('what')}, {ev.get('minutes')}분 대기)")
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
    superseded = load_json(iter_dir(n - 1) / "superseded.json") if n > 1 else None
    if superseded:
        prev_text = (f"직전 반복 iter_{n - 1:03d}은 사용자 보완으로 전환됐다. 실패나 완료 판정이 아니다.\n"
                     f"agent/runs/iter_{n - 1:03d}/의 계획·조사·부분 구현 기록을 읽되, 이전 next_task를 자동 수행하지 않는다.\n"
                     "아래 보완 지시와 한계 검증 근거에 따라 유지·보류·변경할 사항을 정한다.")
    elif prev and prev.get("skipped"):
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

=== 보존된 코드와 재사용 후보 ===
{code_assets_text()}
새 코드를 쓰기 전에 재사용할 파일이 현재 브랜치에 있는지 확인하라. 보관본은 코드 소실이 아니다.

=== 직전 결과 ===
{prev_text}

=== 사람의 추가 지시 ===
{read(d / "human_to_gpt.md", "없음")}

=== 중단 후 보완 지시 (이전 계획보다 우선) ===
{intervention_context(n)}

=== 한계 주장·사용법 검증·미해결 질문 ===
{limitations_text()}
방법 개발은 현재 목표에서 validated인 한계 주장과 연결해야 한다. 후보만 있으면 먼저 diagnostic을 설계한다.

=== 규칙 ===
같은 접근법의 유효한 실험 {MAX_ATTEMPTS}회부터 방향 재평가 (자동 포기 아님).
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
        text += (f"\n--- 라운드 {path.stem[-2:]}에서 알게 된 것 (원문: {path}) ---\n{prev.get('research_notes', '')}\n"
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
    before = approach_ledger(upto=n - 1, since=goal_start(n)).get(approach_key(plan))
    if before and not plan.get("continuation_reason", "").strip():
        if before["status"] == "abandon":
            concerns.append(f"'{before['name']}'의 기각 범위와 새 근거를 설명하는 continuation_reason이 없음")
        elif before["valid_experiments"] >= MAX_ATTEMPTS:
            concerns.append(f"'{before['name']}' 유효한 실험 {before['valid_experiments']}회 이후 계속할 정보 이득의 근거가 없음")
    return concerns


def step_checkpoint(args, n):
    """계획을 Claude에 넘기기 전 확인. 'go' / 'replan' / 'quit'."""
    d = iter_dir(n)
    plan = load_plan(n)
    gate_errors = method_gate_errors(n, plan)
    if gate_errors:
        raise AgentError("방법 개발 진입 보류:\n" + "\n".join(gate_errors)
                         + "\n--replan으로 검증 계획을 요청하세요. --auto도 이 검사를 생략하지 않습니다.")
    concerns = plan_concerns(n, plan)
    approach = plan.get("approach", "?")
    attempt = approach_ledger(upto=n).get(approach_key(plan), {}).get("attempts", 1)

    away = human_away(args) and bool(concerns)
    if args.autonomy == "full" or (args.autonomy == "smart" and not concerns) or away:
        mode = "사람 부재" if away else args.autonomy
        print(f"\n자동 진행 ({mode}): {approach} {attempt}번째 시도")
        note = ("\n원래는 물어볼 지점이었지만 사람 부재 시간이라 1순위로 진행:\n"
                + "\n".join(f"• {c}" for c in concerns)) if away else ""
        notify(notice(f"▶ iter_{n:03d} | 계획대로 자동 진행", [
            ("할 일", plan.get("plan_summary") or approach),
            ("이유", plan.get("decision_reason")),
            ("진행 설정", f"{approach} · {attempt}번째 시도 · Claude {claude_tier(args, n)} · GPT 리뷰 {plan.get('review_mode', 'full')}"),
            ("주의", note),
        ], reference=f"agent/runs/iter_{n:03d}/plan.md"))
        record_event(n, "decision", by="auto", mode=mode, result="1순위로 진행",
                     concerns=concerns if away else [])
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
        print("p [지시]       : 기존 반복 보존 후 새 반복에서 GPT 재계획")
        print(f"t [등급]       : Claude 등급 바꾸기 ({' / '.join(CLAUDE_TIERS)})")
        print("r full|skip    : Claude 작업 후 GPT 리뷰 여부 바꾸기")
        print("a              : 이후 확인 없이 자동 진행")
        print("q              : 종료 (다시 실행하면 여기서 이어짐)")

        reasons = "\n".join(f"• {c}" for c in concerns) or "(수동 확인 모드)"
        telegram_text = notice(f"🙋 iter_{n:03d} | 계획 확인 필요", [
            ("제안", plan.get("plan_summary") or approach),
            ("확인할 내용", reasons),
            ("대안 (1번이 현재 제안)", alt_text),
            ("진행 설정", f"Claude {tier} · GPT 리뷰 {review_mode}"),
        ], reference=f"agent/runs/iter_{n:03d}/plan.md", actions=(
            "ok 또는 1 → 1순위로 진행\n"
            "2, 3… → 그 대안으로 계획 다시\n"
            "f 지시내용 → 추가 지시 후 진행\n"
            "p 지시내용 → 보존 후 GPT부터 재계획\n"
            f"t {'|'.join(CLAUDE_TIERS)} → Claude 등급 변경\n"
            "r full|skip → GPT 리뷰 여부 변경\n"
            "a → 이후 자동 진행\n"
            "q → 종료"
        ))
        reply = ask("> ", telegram_text)
        if reply is None:
            return "quit"
        cmd, rest = split_reply(reply)

        if cmd == "q":
            return decided("quit", "종료", reply)
        if cmd == "p":
            note = rest or ask("GPT에게 줄 재계획 지시:\n> ") or ""
            if not note.strip():
                print("재계획 지시가 필요합니다.")
                continue
            queue_replan(note)
            return decided("replan", "사용자 보완으로 새 반복에서 재계획", reply)
        if cmd.isdigit() and 1 <= int(cmd) <= max(len(alternatives), 1):
            k = int(cmd)
            if k == 1:
                return decided("go", "1순위로 진행", reply)
            choice = alternatives[k - 1]
            note = f"사용자가 대안 {k}번을 선택했다: {choice}\n이 대안을 approach로 계획을 다시 세워라."
            if rest:
                note += f"\n추가 지시: {rest}"
            queue_replan(note)
            log(f"iter_{n:03d} USER CHOSE ALTERNATIVE", note)
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
    """가설 판정과 분리해 가장 최근 재사용 승인 커밋을 출발점으로 삼는다."""
    if cur == BASE_BRANCH or not cur.startswith(BRANCH_PREFIX):
        return cur
    for n in reversed(existing_iterations()):
        commit = reusable_commit(n)
        if commit:
            return commit["sha"]
    return BASE_BRANCH


def reusable_commit(n):
    commit = load_json(iter_dir(n) / "commit.json")
    review = load_review(n) or {}
    if review.get("reviewed_commit") and review["reviewed_commit"] != (commit or {}).get("sha"):
        return None
    # 과거 success 커밋은 기존 재사용 정책과 호환한다. 과거 abandon은 재심사 없이 승격하지 않는다.
    approved = review.get("reusable_code")
    if approved is None:
        approved = review.get("approach_status") == "success"
    return commit if (approved and not review.get("blocking_issues") and not review.get("reuse_issues")
                      and not (commit or {}).get("unpreserved_paths")) else None


def reuse_base(n, cur):
    source = (load_plan(n) or {}).get("reuse_iteration", 0)
    if not source:
        return base_for_new_branch(cur)
    if not isinstance(source, int) or source < 1 or source >= n:
        raise AgentError(f"reuse_iteration은 현재 반복보다 앞선 양수여야 함: {source}")
    commit = reusable_commit(source)
    if not commit:
        raise AgentError(f"iter_{source:03d}에 재사용 승인된 커밋이 없음. 보관본은 검토 후 선별 복구해야 함")
    return commit["sha"]


def archive_pending_code(n, source_branch):
    """stash를 영구 ref로 고정해 stash 정리 후에도 소스와 미추적 파일을 복구할 수 있게 한다."""
    d = iter_dir(n)
    try:
        files, excluded = history.source_state(RESEARCH_DIR)
        dirty = (history.listed(RESEARCH_DIR, "diff", "--name-only", "HEAD") |
                 history.listed(RESEARCH_DIR, "ls-files", "--others", "--exclude-standard"))
        unsafe = [p for p in sorted(dirty) if history.path_reason(p) or p in excluded
                  or ((RESEARCH_DIR / p).exists() and p not in files)]
        if unsafe:
            raise AgentError("브랜치 전환 보류: 자동 보관에서 제외되는 파일이 있습니다. "
                             "stash에 비밀정보·데이터를 넣지 않고 원본을 유지합니다: " + ", ".join(unsafe))
    except history.HistoryError as e:
        raise AgentError(f"브랜치 전환 전 보관 검사 실패: {e}") from e
    message = f"iter_{n:03d}: {source_branch}의 미커밋 작업 (접근법 전환 전 보관)"
    code, out = wgit("stash", "push", "-u", "-m", message)
    if code:
        raise AgentError(f"git stash 실패: {out}")
    code, sha = wgit("rev-parse", "stash@{0}")
    if code:
        raise AgentError("보관한 stash의 commit ID를 확인할 수 없음")
    sha = sha.strip()
    ref = f"refs/research-archive/before-iter-{n:03d}-{sha[:12]}"
    code, out = wgit("update-ref", ref, sha)
    if code:
        raise AgentError(f"코드는 stash에 보존됐으나 영구 ref 생성 실패: {out}")
    save(d / "code_archive.json", json.dumps({
        "source_branch": source_branch, "stash": sha, "ref": ref, "time": now(),
    }, ensure_ascii=False, indent=2))
    code, patch = wgit("stash", "show", "-p", "--include-untracked", sha)
    if code:
        raise AgentError("영구 ref는 보존됐으나 보관 코드 patch 생성 실패")
    save(d / "stashed.patch", patch)
    save(CODE_ASSETS_FILE, code_assets_text())
    return message


def ensure_branch(n):
    """이번 반복 접근법의 브랜치로 research/를 맞춘다. 결과는 git.json에 기록."""
    d = iter_dir(n)
    try:
        history.resolve_assets(RESEARCH_DIR, (load_plan(n) or {}).get("reuse_assets", []))
    except history.HistoryError as e:
        raise AgentError(f"재사용 준비 보류: {e}") from e
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
        # 잘못된 재사용 요청은 작업 트리를 바꾸기 전에 거부한다.
        base_ref = reuse_base(n, cur)
        if wgit("status", "--porcelain")[1].strip():
            info["stashed"] = archive_pending_code(n, cur)
            print(f"미커밋 작업을 stash·영구 ref·patch로 보관: {info['stashed']}")
        if wgit("show-ref", "--verify", "--quiet", f"refs/heads/{target}")[0] == 0:
            code, out = wgit("checkout", target)
        else:
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
    try:
        history.begin(RESEARCH_DIR, d)
        history.prepare_assets(RESEARCH_DIR, d, (load_plan(n) or {}).get("reuse_assets", []))
    except history.HistoryError as e:
        raise AgentError(f"연구 코드 준비 보류: {e}") from e
    # 중단 후 재실행해도 첫 시도 이전 상태와 비교하도록 스냅샷은 한 번만 찍는다.
    snap_file = d / "snapshot_before.json"
    if not snap_file.exists():
        save(snap_file, json.dumps(snapshot()))

    prompt = f"""이번 반복: iter_{n:03d}

=== 연구 목표 ===
{goal}

=== GPT 계획 ===
{d / "plan.md"} 와 {d / "plan.json"}을 먼저 읽고 그 계획을 구현/실행하라.
JSON의 연구 질문·기여 경로·baseline·재사용 조건도 확인한다.

=== 연구 운영 보완 지시 ===
{read(d / "execution_amendment.md", "없음")}

=== 보존된 코드와 재사용 후보 ===
{code_assets_text()}

=== 이번 계획의 선별 반입·검증 조건 ===
{read(d / "reuse_manifest.json", "없음")}
반입은 검증 승인이 아니다. required_checks를 구현·실험 전에 확인하고 결과를 보고하라.

=== 작업 위치 ===
현재 디렉터리는 {RESEARCH_DIR} (연구 코드 git 저장소, 브랜치 {branch})다.
코드는 여기서만 만들고 고치고, 결과는 results/에 저장한다.
입력 데이터는 {LEGACY_DIR}/eval_samples/, 이전 수동 분석 코드·결과는 {LEGACY_DIR}/ 에 있다 (읽기 전용).
이전 코드를 쓰려면 research/로 복사해서 고친다. git 커밋과 브랜치 관리는 orchestrator가 한다.

=== 사용자 추가 지시 ===
{read(d / "human_to_claude.md", "없음")}

=== 중단 후 보완 지시 (원문) ===
{intervention_context(n)}

=== 한계 주장과 검증 근거 ===
{limitations_text()}
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
                return run_claude(args, CLAUDE_RESUME_PROMPT + "\n\n" + prompt,
                                  stream_log, tier, session_file, resume_id=session)
            except RetryableError as e:
                if "No conversation found" not in e.output:
                    raise
                print("이전 세션을 찾을 수 없어 새로 시작합니다.")
                session_file.unlink(missing_ok=True)
        restarted = stream_log.exists() and stream_log.stat().st_size > 0
        return run_claude(args, prompt + (CLAUDE_RESTART_NOTE if restarted else ""),
                          stream_log, tier, session_file)

    try:
        result = load_json(d / "claude_result.raw.json")
        if result is None:
            result = with_retries("Claude 구현/실험", attempt)
            # 결과 응답 뒤 체크포인트/보고서 저장 중 끊겨도 모델·실험을 다시 호출하지 않는다.
            save_atomic(d / "claude_result.raw.json", json.dumps(result, ensure_ascii=False, indent=2))
    except BaseException:
        # 프로세스가 정리된 뒤에만 보존한다. 보존 실패가 원래 중단 원인을 가리지 않는다.
        try:
            checkpoint_code(n, "interrupted")
        except (AgentError, OSError) as e:
            print(f"[WARN] 중단 코드 체크포인트 보류 (작업 파일 유지): {e}")
        raise
    checkpoint_code(n, "implementation_finished", final=True)

    report = result.get("result", "").strip()
    denials = result.get("permission_denials") or []
    if denials:
        report += "\n\n# [orchestrator] 권한 거부된 도구 호출\n"
        for item in denials:
            detail = summarize_tool_input(item.get("tool_name"), item.get("tool_input", {}))
            report += f"- {item.get('tool_name')}: {detail}\n"

    changed = diff_snapshots(json.loads(read(snap_file)), snapshot())
    save(d / "changed_files.txt", changed + "\n")
    save(d / "claude_meta.json", json.dumps({
        key: result.get(key)
        for key in ("session_id", "is_error", "num_turns", "duration_ms", "total_cost_usd", "usage", "modelUsage")
    } | {"permission_denials": len(denials)}, indent=2))
    save(d / "claude_report.md", report)
    log(f"iter_{n:03d} CLAUDE REPORT", report)
    print("\n" + report)
    record_event(n, "claude", tier=tier, branch=branch,
                 summary=parse_trailer(report, "SUMMARY"),
                 self_check=parse_trailer(report, "SELF_CHECK") or "없음",
                 changed_files=len(changed.splitlines()), permission_denials=len(denials))
    rebuild_index()



def step_review(args, goal, n):
    d = iter_dir(n)
    banner(f"[iter_{n:03d} · 3/3] GPT가 결과를 리뷰합니다.")
    commit = load_json(d / "commit.json") or {}
    if commit.get("kind") == "checkpoint":
        if wgit("rev-parse", "HEAD")[1].strip() != commit["sha"]:
            raise AgentError("리뷰 대상 체크포인트 이후 HEAD가 변경됐습니다. 코드 버전을 확인하세요.")
        dirty = set(wgit("diff", "HEAD", "--name-only")[1].splitlines())
        if dirty.intersection(commit.get("owned_paths", [])):
            raise AgentError("체크포인트 이후 리뷰 대상 코드가 변경됐습니다. 새 반복으로 검증하세요.")

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
{(load_plan(n) or {}).get("approach", "?")} — {approach_ledger(upto=n).get(approach_key(load_plan(n)), {}).get("attempts", 1)}번째 반복
유효한 실험 {MAX_ATTEMPTS}회부터 방향을 재평가하되, 횟수만으로 포기하지 않는다.

=== 연구 운영 보완 지시 ===
{read(d / "execution_amendment.md", "없음")}

=== 중단 후 보완 지시 (준수 여부도 검토) ===
{intervention_context(n)}

=== 현재 한계 주장과 검증 근거 ===
{limitations_text()}
브랜치: {current_branch()} (코드 위치: {RESEARCH_DIR})

=== 지금까지의 반복 요약과 접근법 기록 (agent/INDEX.md) ===
{read(INDEX_FILE, "없음")}

=== 이미 추천한 논문 (agent/PAPERS.md) ===
{read(PAPERS_FILE, "없음")}

=== 검토 자료 (직접 열어 확인하라) ===
- 계획: agent/runs/iter_{n:03d}/plan.md
- 구조화된 계획: agent/runs/iter_{n:03d}/plan.json
- Claude 보고서: agent/runs/iter_{n:03d}/claude_report.md
- Claude 도구 호출 전체 기록: agent/runs/iter_{n:03d}/claude_stream.jsonl
- 코드 버전·제외 파일: agent/runs/iter_{n:03d}/commit.json (체크포인트이지 검증 승인이 아님)
- 코드 변경 diff (구현 전 SHA → 리뷰 대상 SHA): agent/runs/iter_{n:03d}/changes.patch
- 선별 재사용 출처·필수 검증: agent/runs/iter_{n:03d}/reuse_manifest.json
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

    validate_limitation_updates(review)
    validate_code_assets(n, review)
    if commit:
        review["reviewed_commit"] = commit["sha"]
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
        f"\n## [ ] {paper['title']} ({paper['authors_year']})\n\n"
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
    notify(notice(f"📚 iter_{n:03d} | 읽어볼 논문", [
        ("논문", f"{paper['title']} ({paper['authors_year']})\n{url}"),
        ("현재 연구와의 연결", paper["current_work"]),
        ("추천 이유", paper["why"]),
        ("먼저 읽을 부분", paper["what_to_read"]),
    ], reference="agent/PAPERS.md"))


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
        f"\n## 🏁 {milestone['title']}\n\n"
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
    notify(notice(f"🏁 iter_{n:03d} | 주요 연구 진전", [
        ("핵심", milestone["title"]), ("무엇이 달라졌나", milestone["story"]),
    ], reference="agent/JOURNEY.md"))


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
    """호환용 후처리 이름. 코드는 이미 보존됐으며 여기서는 리뷰와 SHA를 연결한다."""
    d = iter_dir(n)
    commit = load_json(d / "commit.json")
    if not commit:
        # 업그레이드 전 작업의 소유 범위가 불명확하면 무조건 add -A하지 않는다.
        if (d / "code_baseline.json").exists():
            commit = checkpoint_code(n, "legacy_review_boundary", final=True)
        else:
            return
    save_atomic(d / "code_review.json", json.dumps({
        "sha": commit["sha"], "review_skipped": bool(review.get("skipped")),
        "reusable_code": review.get("reusable_code", False), "code_assets": review.get("code_assets", []),
        "approach_status": review.get("approach_status"), "review_file": "review.json",
    }, ensure_ascii=False, indent=2))


def checkpoint_code(n, reason, final=False):
    """에이전트가 종료된 안전한 경계에서만 체크포인트를 저장한다."""
    if STATE["proc"] is not None:
        raise AgentError("에이전트 실행 중에는 코드 체크포인트를 만들지 않습니다.")
    d = iter_dir(n)
    try:
        entry = history.checkpoint(RESEARCH_DIR, d, n, reason)
        # 커밋 이후 HEAD diff가 비더라도 원래 구현 전후 비교를 유지한다.
        patch = history.git(RESEARCH_DIR, "diff", "--binary", entry["before_sha"], entry["sha"]).decode()
        save(d / "changes.patch", patch)
        if final:
            tag = f"iter_{n:03d}"
            existing = wgit("rev-parse", "--verify", f"refs/tags/{tag}")
            if existing[0] == 0 and existing[1].strip() != entry["sha"]:
                raise AgentError(f"기존 {tag}가 다른 커밋을 가리킵니다. 덮어쓰지 않습니다.")
            if existing[0] != 0:
                history.git(RESEARCH_DIR, "tag", tag, entry["sha"])
            entry = {**entry, "kind": "checkpoint", "tag": tag}
            save_atomic(d / "commit.json", json.dumps(entry, ensure_ascii=False, indent=2))
    except history.HistoryError as e:
        raise AgentError(f"체크포인트 보류 (작업 파일 유지): {e}") from e
    record_event(n, "checkpoint", sha=entry["sha"], reason=reason, excluded=entry["unpreserved_paths"])
    save(CODE_ASSETS_FILE, code_assets_text())
    print(f"💾 iter_{n:03d} 체크포인트: {entry['sha'][:12]} ({reason}, 검증 승인 아님)")
    return entry


def validate_code_assets(n, review):
    commit = load_json(iter_dir(n) / "commit.json")
    assets = review.get("code_assets", [])
    if not commit:
        if assets:
            raise AgentError("리뷰 대상 코드 SHA 없이 모듈 재사용을 승인할 수 없습니다.")
        return
    excluded = set(commit.get("unpreserved_paths", []))
    if review.get("reusable_code") and excluded:
        raise AgentError("커밋되지 않은 작업 파일이 있습니다. 전체 재사용 승인 대신 검증된 모듈만 지정하세요.")
    for asset in assets:
        if asset.get("status") not in {"approved", "needs_fix", "rejected"}:
            raise AgentError("code_assets의 재사용 상태가 올바르지 않습니다.")
        if asset["status"] == "approved" and (not asset.get("checks") or excluded.intersection(asset["paths"])):
            raise AgentError("모듈 승인에는 실제 검증 근거와 커밋에 포함된 파일이 필요합니다.")
        try:
            history.resolve_assets(RESEARCH_DIR, [{"source_commit": history.text_git(
                RESEARCH_DIR, "rev-parse", commit["sha"]), "paths": asset["paths"],
                "reason": asset["reason"], "required_checks": asset.get("checks") or ["미검증"]}])
        except history.HistoryError as e:
            raise AgentError(f"모듈 재사용 판정 오류: {e}") from e


def handle_needs_human(review, n):
    """NEEDS_HUMAN 처리. False면 종료."""
    banner("사람의 결정이 필요합니다")
    print(review["reason"])
    print("\nENTER / ok   : GPT 제안(next_task)대로 계속")
    print("f [지시]     : 다음 계획에 반영할 지시 입력 후 계속")
    print("q            : 종료")

    telegram_text = notice(f"🙋 iter_{n:03d} | 사용자 결정 필요", [
        ("질문", review["reason"]),
        ("현재 결과", review["one_line_summary"]),
        ("GPT 제안", review["next_task"]),
    ], reference=f"agent/runs/iter_{n:03d}/review.md", actions=(
        "ok → GPT 제안대로 계속\n"
        "f 지시내용 → 지시 반영해서 계속\n"
        "q → 종료"
    ))
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

def nonnegative_seconds(value):
    seconds = int(value)
    if seconds < 0:
        raise argparse.ArgumentTypeError("timeout은 0 이상이어야 합니다 (0=시간 제한 없음)")
    return seconds


def nonnegative_iterations(value):
    count = int(value)
    if count < 0:
        raise argparse.ArgumentTypeError("반복 수는 0 이상이어야 합니다 (0=횟수 제한 없음)")
    return count


def parse_args():
    p = argparse.ArgumentParser(description="GPT(Codex) ↔ Claude Code 자동 연구 루프")
    p.add_argument("--max-iters", type=nonnegative_iterations, default=0,
                   help="이번 실행의 최대 반복 수. 기본 0=횟수 제한 없음, 양수 지정 시에만 제한")
    p.add_argument("--autonomy", choices=["manual", "smart", "full"], default="smart",
                   help="계획 확인: manual=매번, smart=애매할 때만(기본), full=안 함")
    p.add_argument("--auto", action="store_true", help="--autonomy full과 같음")
    p.add_argument("--no-ask-until", help="이 시각까지는 사람에게 묻지 않고 진행. 예: 09:00 또는 '2026-09-24 09:00'")
    p.add_argument("--max-attempts", type=int, default=MAX_ATTEMPTS,
                   help="같은 접근법의 유효한 실험 재평가 기준 횟수 (자동 포기 아님)")
    p.add_argument("--max-think-rounds", type=int, default=4, help="반복당 GPT 사고 라운드 최대 횟수")
    p.add_argument("--goal", help="새 연구 목표. 이전 기록을 이어받아 새 목표로 다시 계획한다")
    p.add_argument("--reset", action="store_true", help="모든 기록을 archive로 옮기고 완전히 새로 시작")
    p.add_argument("--gpus", help="Claude 실험에 보일 GPU (CUDA_VISIBLE_DEVICES), 예: 1 또는 0,1")
    p.add_argument("--gpt-tier", choices=GPT_TIERS, help="GPT 계획/리뷰 등급 고정 (agent/tiers.json)")
    p.add_argument("--claude-tier", choices=CLAUDE_TIERS, help="Claude 등급 고정 (agent/tiers.json)")
    p.add_argument("--gpt-timeout", type=int, default=30 * 60, help="GPT 단계 제한 시간(초)")
    p.add_argument("--claude-timeout", type=nonnegative_seconds, default=0,
                   help="Claude 단계 제한 시간(초), 0=시간 제한 없음(기본). 양수 지정 시에만 강제 종료")
    p.add_argument("--always-review", action="store_true", help="계획과 상관없이 매 반복 GPT 리뷰")
    p.add_argument("--limit-poll-minutes", type=int, default=30, help="사용 한도 대기 중 다시 시도하는 간격(분)")
    p.add_argument("--limit-max-hours", type=float, default=8, help="사용 한도가 풀리길 최대 몇 시간 기다릴지")
    p.add_argument("--no-telegram", action="store_true", help="Telegram 알림/답장 끄기")
    p.add_argument("--replan", metavar="지시", help="현재 작업을 보존하고 보완 지시로 GPT부터 재계획")
    p.add_argument("--prepare-only", action="store_true", help="보완 지시의 재개 상태만 준비. 에이전트·실험·알림 실행 안 함")
    p.add_argument("--status", action="store_true", help="현재 단계·보완 대기 여부만 표시. 실행 안 함")
    p.add_argument("--usage", action="store_true", help="GPT·Claude 로컬 로그 사용량 조회. 모델·실험·알림 실행 안 함")
    args = p.parse_args()
    if (args.prepare_only or args.replan) and (args.reset or args.goal):
        p.error("보완 재개는 --reset/--goal과 함께 쓸 수 없습니다. 기존 목표와 기록을 보존합니다.")
    if args.status and (args.replan or args.prepare_only or args.reset or args.goal):
        p.error("--status는 조회 전용입니다. 상태 변경 옵션과 함께 쓸 수 없습니다.")
    if args.usage and (args.status or args.replan or args.prepare_only or args.reset or args.goal):
        p.error("--usage는 단독 조회 옵션입니다. 상태 변경 또는 --status와 함께 쓸 수 없습니다.")
    if args.auto:
        args.autonomy = "full"
    args.no_ask_until = parse_until(args.no_ask_until)
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
        notify(notice(f"🎯 iter_{start:03d}부터 연구 목표 변경", [
            ("새 목표", text), ("이전 목표", previous),
        ], reference="agent/GOAL.md · 변경 이력: agent/GOALS.json"))
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


def parse_until(text):
    """'09:00'(가장 가까운 그 시각) 또는 '2026-09-24 09:00'."""
    if not text:
        return None
    now_dt = datetime.datetime.now()
    try:
        return datetime.datetime.strptime(text, "%Y-%m-%d %H:%M")
    except ValueError:
        t = datetime.datetime.strptime(text, "%H:%M").time()
        target = datetime.datetime.combine(now_dt.date(), t)
        return target if target > now_dt else target + datetime.timedelta(days=1)


def human_away(args):
    """--no-ask-until 시각 전이면 True (사람에게 묻지 않고 진행)."""
    return bool(args.no_ask_until) and datetime.datetime.now() < args.no_ask_until


def status_text():
    if STATE["n"] is None:
        return "시작 준비 중입니다."
    minutes = int((datetime.datetime.now() - STATE["since"]).total_seconds() // 60)
    text = f"iter_{STATE['n']:03d} · {STATE['stage']} 진행 중 ({minutes}분째)"
    if STATE["limit_wait"]:
        what, since = STATE["limit_wait"]
        waited = int((datetime.datetime.now() - since).total_seconds() // 60)
        text += f"\n⏳ {what}: 사용 한도가 풀리길 기다리는 중 ({waited}분째)"
        if STATE.get("limit_retry_at"):
            text += f"\n다음 재시도: {STATE['limit_retry_at']:%m-%d %H:%M:%S}"
    return text


def request_stop():
    STOP_FILE.touch()
    HUMAN.interrupt()
    return f"현재 단계({STATE['stage']})를 마치면 멈춥니다. 다시 실행하면 이어서 진행합니다."


def request_stop_now():
    STOP_FILE.touch()
    STATE["stop_now"] = True
    if STATE["proc"] is not None:
        kill_agent_group(STATE["proc"])
    HUMAN.interrupt()
    return f"진행 중인 작업({STATE['stage']})을 중단하고 멈춥니다. 다시 실행하면 이어서 진행합니다."


def record_stop(reason):
    """중단 사실을 반복 기록에 남긴다."""
    if STATE["n"] is None:
        return
    try:
        record_event(STATE["n"], "stopped", reason=reason, during=STATE["stage"])
        rebuild_index()
        commit_records(f"research records: iter_{STATE['n']:03d} stopped ({reason[:60]})")
    except Exception as e:
        print(f"[WARN] 중단 기록 실패: {e}")


def main():
    args = parse_args()
    if args.usage:
        print(usage_report(RUNS_DIR))
        print("\n" + gpt_usage.usage_report(RUNS_DIR))
        return
    if args.status:
        n = current_iteration()
        print(f"현재: iter_{n:03d} / {stage_of(n)}")
        print(f"보완 지시 대기: {'있음' if RESUME_FILE.exists() or pending_interventions() else '없음'}")
        print(f"지시 파일: {RESUME_FILE}")
        info = load_json(iter_dir(n) / "intervention.json")
        if info:
            print(f"반영된 보완: {info['id']} (원문: {iter_dir(n) / 'intervention.json'})")
        return
    with orchestrator_lock():
        if (args.reset or args.goal) and (RESUME_FILE.exists() or pending_interventions()):
            raise AgentError("대기 중인 보완 지시가 있습니다. 먼저 기존 목표에서 반영한 뒤 목표 변경/초기화하세요.")
        if args.replan:
            queue_replan(args.replan)
        target = apply_pending_replan()
        if args.prepare_only:
            print(f"준비 완료: iter_{current_iteration():03d}, 실험·에이전트·알림 미실행. "
                  + ("새 보완 지시를 적용했습니다." if target else "새 보완 지시가 없습니다."))
            return
        run_loop(args)


def run_loop(args):
    global HUMAN, MAX_ATTEMPTS
    MAX_ATTEMPTS = args.max_attempts
    LIMIT.update(poll=args.limit_poll_minutes * 60, max=int(args.limit_max_hours * 3600))
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
    # 직전 반복이 DONE이어도, 그 뒤에 새 목표가 시작됐으면 묻지 않는다 (DONE은 이전 목표의 완료)
    if (not goal_changed and n > 1 and goal_start(n) < n
            and not (iter_dir(n) / "intervention.json").exists()
            and load_review(n - 1) and load_review(n - 1)["verdict"] == "DONE"):
        print("\n직전 반복에서 DONE 판정이 났습니다. 새 목표로 이어가려면 --goal \"새 목표\"로 실행하세요.")
        if args.autonomy == "full" or (ask("계속할까요? [y/N] ") or "").lower() != "y":
            return

    first_line = goal.splitlines()[0] if goal else ""
    away_text = (f"\n{args.no_ask_until:%m-%d %H:%M}까지는 묻지 않고 진행합니다 (그 후 원래 규칙)."
                 if args.no_ask_until else "")
    notify(notice(f"▶ iter_{current_iteration():03d} | 연구 루프 시작", [
        ("목표", first_line), ("진행 범위", f"이번 실행에서 최대 {args.max_iters}회 반복" if args.max_iters
         else "반복 횟수 제한 없이 계속 진행합니다. 목표 달성·오류·정지 요청 시 종료하고, 필요한 사용자 판단은 기다립니다."),
        ("사용자 확인", away_text),
    ], reference="agent/GOAL.md"))

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
    while args.max_iters == 0 or completed < args.max_iters:
        # 외부 에이전트가 실행되는 중에는 작업을 바꾸지 않고 다음 안전한 단계 경계에서 전환한다.
        check_stop()
        apply_pending_replan()
        n = current_iteration()
        d = iter_dir(n)
        d.mkdir(parents=True, exist_ok=True)

        check_stop()
        if not (d / "plan.md").exists():
            set_stage(n, "GPT 계획")
            step_plan(args, goal_for(n), n)
        if RESUME_FILE.exists() or pending_interventions():
            continue
        if not (d / "claude_report.md").exists():
            check_stop()
            set_stage(n, "계획 확인")
            action = step_checkpoint(args, n)
            if action == "quit":
                commit_records(f"research records: iter_{n:03d} paused at plan check")
                print("종료합니다. 다시 실행하면 여기서 이어집니다.")
                return
            if action == "replan":
                continue
            if RESUME_FILE.exists() or pending_interventions():
                continue
            check_stop()
            set_stage(n, "Claude 구현/실험")
            step_claude(args, goal_for(n), n)
        if RESUME_FILE.exists() or pending_interventions():
            continue
        if not (d / "review.json").exists():
            check_stop()
            needs_review, reason = review_decision(args, n)
            if needs_review:
                print(f"\nGPT 리뷰 진행: {reason}")
                set_stage(n, "GPT 리뷰")
                step_review(args, goal_for(n), n)
            else:
                step_skip_review(n, reason)
        if RESUME_FILE.exists() or pending_interventions():
            continue

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
                notify(iteration_result(n, review))
            elif review["verdict"] == "CONTINUE":
                notify(iteration_result(n, review))
            elif review["verdict"] == "DONE":
                notify(iteration_result(n, review))
            set_post_flag(n, "notified")

        if review["verdict"] == "NEEDS_HUMAN" and human_away(args):
            record_event(n, "needs_human", question=review["reason"], reply="(사람 부재, 자동)",
                         result="GPT 제안대로 계속")
            rebuild_index()
            notify(notice(f"▶ iter_{n:03d} | 설정된 부재 시간에 따라 자동 진행", [
                ("원래 확인할 질문", review["reason"]), ("진행할 일", review["next_task"]),
                ("주의", "사용자가 승인한 답변이 아니라, 기존 부재 시간 설정에 따른 자동 결정입니다."),
            ], reference=f"agent/runs/iter_{n:03d}/review.md"))
        elif review["verdict"] == "NEEDS_HUMAN":
            set_stage(n, "사람 결정 대기")
            if not handle_needs_human(review, n):
                commit_records(f"research records: iter_{n:03d} waiting for human decision")
                print("종료합니다. 다시 실행하면 이 질문부터 다시 묻습니다.")
                return

        save(d / "done.json", json.dumps({"verdict": review["verdict"], "time": now()}, indent=2))
        commit_records(f"research records: iter_{n:03d} [{review['verdict']}] {review['one_line_summary'][:80]}")
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


def cli_main():
    """CLI 종료 경로를 한곳에 둬 예기치 않은 예외도 조용히 종료되지 않게 한다."""
    try:
        main()
    except StopRequested as e:
        record_stop(str(e))
        print(f"\n멈췄습니다 ({e}). 다시 실행하면 완료되지 않은 단계부터 이어서 진행합니다.")
        notify(f"⏹ 멈췄습니다 ({e}, {STATE['stage']} 중). 다시 실행하면 이어서 진행합니다.")
        return 0
    except AgentError as e:
        record_stop(f"오류: {e}")
        print(f"\n[ERROR] {e}")
        notify(notice("❌ 오류로 중단", [
            ("오류", str(e)),
            ("다음", "오류 내용을 확인하세요. 다시 실행하면 미완료 단계부터 이어갑니다."),
        ]))
        print("다시 실행하면 완료되지 않은 단계부터 이어서 진행합니다.")
        return 1
    except KeyboardInterrupt:
        record_stop("Ctrl+C")
        print("\n중단됨. 다시 실행하면 완료되지 않은 단계부터 이어서 진행합니다.")
        return 130
    except Exception as e:
        # 알림에는 종류만 표시한다. 상세 traceback은 실행 로그(stderr)에 보존한다.
        traceback.print_exc()
        reason = f"예기치 않은 오류: {type(e).__name__}"
        record_stop(reason)
        notify(notice("❌ 예기치 않은 오류로 중단", [
            ("현재", f"iter_{STATE['n']:03d} / {STATE['stage']}" if STATE["n"] is not None else "시작 전"),
            ("오류", type(e).__name__),
            ("다음", "실행 로그의 traceback을 확인하세요. 완료 기록은 유지되며 수정 후 미완료 단계부터 재개합니다."),
        ]))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(cli_main())
