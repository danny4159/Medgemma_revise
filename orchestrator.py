from pathlib import Path
import subprocess
import datetime
import sys

PROJECT_DIR = Path(__file__).resolve().parent
AGENT_DIR = PROJECT_DIR / "agent"
AGENT_DIR.mkdir(exist_ok=True)

GOAL_FILE = AGENT_DIR / "GOAL.md"
GPT_PLAN_FILE = AGENT_DIR / "GPT_PLAN.md"
CLAUDE_REPORT_FILE = AGENT_DIR / "CLAUDE_REPORT.md"
GPT_REVIEW_FILE = AGENT_DIR / "GPT_REVIEW.md"
LOG_FILE = AGENT_DIR / "RESEARCH_LOG.md"


def run_command(cmd):
    result = subprocess.run(
        cmd,
        cwd=PROJECT_DIR,
        text=True,
        capture_output=True,
    )

    if result.returncode != 0:
        print("\n[ERROR]")
        print(result.stderr)
        sys.exit(result.returncode)

    return result.stdout.strip()


def save(path, text):
    path.write_text(text, encoding="utf-8")


def log(title, text):
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(f"\n\n## {title} — {now}\n\n{text}\n")


# --------------------------------------------------
# 1. 연구 목표 입력
# --------------------------------------------------

if not GOAL_FILE.exists():
    print("\n=== 연구 목표 입력 ===")
    goal = input("이번 연구에서 무엇을 할지 입력하세요:\n> ").strip()

    if not goal:
        print("연구 목표가 비어 있습니다.")
        sys.exit(1)

    save(GOAL_FILE, goal)
else:
    goal = GOAL_FILE.read_text(encoding="utf-8")

print("\n==========================================")
print("RESEARCH GOAL")
print("==========================================")
print(goal)


# --------------------------------------------------
# 2. GPT가 연구 계획 수립
# --------------------------------------------------

print("\n\n==========================================")
print("[1/3] GPT가 연구 계획을 작성합니다.")
print("==========================================\n")

gpt_prompt = f"""
너는 이 프로젝트의 Research Scientist이자 Reviewer다.

현재 프로젝트 디렉터리를 충분히 살펴보고,
아래 연구 목표를 달성하기 위한 다음 연구 단계를 설계하라.

연구 목표:
{goal}

역할:
- 기존 코드와 현재 실험 상태를 먼저 이해한다.
- 필요한 경우 프로젝트 내 기존 결과 파일과 문서를 검토한다.
- 연구 가설을 명확히 한다.
- 지금 당장 Claude Code가 구현/실험할 수 있는 구체적인 작업을 제안한다.
- 불필요하게 큰 변경은 피한다.
- 검증 방법과 성공/실패 판단 기준을 제시한다.
- 아직 실제 코드를 수정하지 않는다.

출력 형식:

# Current Understanding
# Hypothesis
# Proposed Experiment
# Implementation Tasks for Claude
# Evaluation
# Risks / Checks
"""

gpt_plan = run_command([
    "codex",
    "exec",
    "-c",
    'model_reasoning_effort="high"',
    gpt_prompt
])

save(GPT_PLAN_FILE, gpt_plan)
log("GPT PLAN", gpt_plan)

print(gpt_plan)


# --------------------------------------------------
# 3. 사용자 개입
# --------------------------------------------------

print("\n\n==========================================")
print("사용자 확인")
print("==========================================")
print("""
ENTER : 그대로 Claude에게 전달
f     : 추가 지시 입력
q     : 종료
""")

choice = input("> ").strip().lower()

user_feedback = ""

if choice == "q":
    print("종료합니다.")
    sys.exit(0)

elif choice == "f":
    print("\nGPT 계획에 추가할 지시를 입력하세요.")
    user_feedback = input("> ").strip()
    log("USER FEEDBACK", user_feedback)


# --------------------------------------------------
# 4. Claude가 구현 / 실험
# --------------------------------------------------

print("\n\n==========================================")
print("[2/3] Claude가 구현/실험합니다.")
print("==========================================\n")

claude_prompt = f"""
너는 이 프로젝트의 Research Engineer다.

현재 repository와 파일을 직접 조사하고,
아래 GPT 연구 계획을 바탕으로 필요한 구현 및 검증을 수행하라.

=== GPT PLAN ===

{gpt_plan}

=== USER FEEDBACK ===

{user_feedback if user_feedback else "추가 지시 없음"}

중요 규칙:
- 실제 repository를 확인하고 작업한다.
- 필요한 코드 수정은 직접 수행한다.
- 기존 데이터를 함부로 삭제하지 않는다.
- 파괴적인 시스템 명령을 실행하지 않는다.
- 가능하면 실제 테스트나 작은 검증을 수행한다.
- 장시간 GPU 학습이 필요하면 임의로 거대한 실험을 시작하지 말고,
  무엇을 실행해야 하는지 명확히 보고한다.
- 수행한 변경 사항과 결과를 구체적으로 기록한다.

마지막 응답은 반드시 다음 형식으로 작성하라.

# Work Performed
# Files Changed
# Commands / Experiments
# Results
# Problems
# Recommendation to GPT
"""

claude_report = run_command([
    "claude",
    "--permission-mode",
    "acceptEdits",
    "-p",
    claude_prompt
])

save(CLAUDE_REPORT_FILE, claude_report)
log("CLAUDE REPORT", claude_report)

print(claude_report)


# --------------------------------------------------
# 5. GPT가 Claude 결과 리뷰
# --------------------------------------------------

print("\n\n==========================================")
print("[3/3] GPT가 결과를 리뷰합니다.")
print("==========================================\n")

review_prompt = f"""
너는 Research Scientist이자 엄격한 Reviewer다.

연구 목표:

{goal}

처음 세운 연구 계획:

{gpt_plan}

Claude Code가 수행한 결과:

{claude_report}

위 결과를 비판적으로 검토하라.

다음을 판단하라:
- 실험이 원래 가설을 실제로 검증했는가?
- 구현이나 평가에 문제가 있는가?
- 데이터 leakage, confound, 잘못된 metric 등의 위험이 있는가?
- 결과가 의미 있는가?
- 다음에 무엇을 해야 하는가?

출력 형식:

# Assessment
# Key Findings
# Problems / Concerns
# Interpretation
# Recommended Next Experiment
"""

gpt_review = run_command([
    "codex",
    "exec",
    "-c",
    'model_reasoning_effort="high"',
    review_prompt
])

save(GPT_REVIEW_FILE, gpt_review)
log("GPT REVIEW", gpt_review)

print(gpt_review)


print("\n\n==========================================")
print("1회 연구 루프 완료")
print("==========================================")
print(f"""
결과 파일:

{GPT_PLAN_FILE}
{CLAUDE_REPORT_FILE}
{GPT_REVIEW_FILE}
{LOG_FILE}
""")