# MedGemma 1.5-4B-IT 서버 세팅

## 환경
- conda env: `medgemma` (python 3.11, `/home/test/.conda/envs/medgemma`)
  - `conda activate medgemma`
  - user-site(`~/.local`) 패키지와 격리되도록 `PYTHONNOUSERSITE=1`을 활성화 시 자동 설정함
- 주요 패키지: torch 2.5.1+cu121, transformers>=4.50, accelerate, huggingface_hub, pillow

## 모델
- HF repo: `google/medgemma-1.5-4b-it` (gated, 라이선스 동의 필요)
- 캐시 위치: `hf_cache/` (이 폴더 내부, `HF_HOME`으로 지정)
- 로그인: `huggingface_hub.login()`으로 계정(danny4159) 토큰 등록 완료
  (토큰은 `~/.cache/huggingface/token`에 저장됨. 새 셸에서 캐시 디렉토리를
  바꿔 쓸 경우 `token=` 인자로 명시적으로 넘겨야 함)

## 실행
```bash
conda activate medgemma
export HF_HOME=/SSD1_1TB/home/milab/daniel/08_medgemma/hf_cache
python legacy/run_medgemma.py
```

`legacy/run_medgemma.py`는 예시 흉부 X-ray 이미지를 다운받아 모델에게 설명을 요청하는
간단한 스모크 테스트입니다. 실제 사용 시 `pipeline(...)` 호출 부분을 필요한
이미지/프롬프트로 바꿔 쓰면 됩니다.

## 참고
- 모델 크기: 약 4B 파라미터, bf16 기준 GPU 메모리 약 8~10GB 필요
- 서버 GPU: RTX 3090 24GB x2 (인덱스 0, 1) — 충분히 여유 있음

## 현재 연구 우선순위

최종 목표는 `agent/GOAL.md`, 현재 MRI 우선 전략은 `agent/RESEARCH_FOCUS.md`에 있다.
2026-10-03 보완부터 자료·모델 적합성 확인 → 현상 탐색 → 최소 개입 → 독립 확인을 구분한다.
MedGemma는 초기 baseline이며 MRI 과제의 기본 능력이 부족하면 적절한 다른 모델을 비교한다.
공통 기준은 `agent/RESEARCH_POLICY.md`이며 GPT 계획·리뷰와 Claude/Codex 구현 호출에 전달된다.
전환 원문·이력은 `agent/interventions/`, 기존 결과는 각 `agent/runs/iter_NNN/`에 보존한다.

## 구현 담당 선택: Claude / Codex

일시적으로 Codex를 사용한 뒤 정해진 시각 이후 **시작하는 반복부터** Claude로 복귀할 수 있다.
이미 시작한 반복은 중간에 교체하지 않는다. 예약은 재시작해도 유지된다.

```bash
python orchestrator.py --engineer codex --codex-engineer-sandbox danger-full-access --gpus 0,1 --engineer-return-at '2026-10-03T04:30:00+09:00' --engineer-return-to claude
```

날짜·시간대를 명시한다. 예약 없이 `--engineer claude` 또는 `--engineer codex`를 새로 지정하면
이전 예약을 해제하고 해당 담당을 유지한다. 진행 중 세션 교체 제한은 그대로 적용한다.
반복별 `engineer_choice.json`은 계획 시작 때 선택한 담당과 예약의 원본을 보존한다.

GPT 계획·리뷰는 유지하고, 구현·GPU 실험·자체 검증 담당 전체를 선택할 수 있다.

```bash
python orchestrator.py --engineer codex --codex-engineer-sandbox danger-full-access --gpus 0,1
python orchestrator.py --engineer claude --gpus 0,1
```

첫 기본값은 Claude다. 명시한 선택은 서버의 `agent/engineer_selection.json`에 저장되어,
이후 `python orchestrator.py --gpus 0,1`로 재개해도 유지된다. 이 서버별 설정은 Git에 올리지 않는다.
`--status`는 실제/선택 담당을 보여주며 설정을 변경하지 않는다. 동시 실행은 기존 lock으로 막는다.
현재 실행 중인 프로세스는 설정 추가로 바뀌지 않는다. 정상 중단·종료 확인 후 다음 실행에 적용한다.
실행 없이 선택만 저장하려면 종료 상태에서 `--prepare-only --engineer codex`를 쓴다.
단, 대기 중인 RESUME.md가 있으면 기존 prepare-only 동작대로 그 보완 전환도 적용한다.

이미 구현을 시작한 반복에서는 담당을 조용히 교체하지 않는다. 기존 담당으로 완료하거나,
정상 중단 후 `--engineer codex --replan "기존 코드·결과를 보존하고 남은 작업을 인계해 재계획"`처럼
명시적으로 새 반복으로 넘긴다. 목표·원본 기록·checkpoint는 보존한다.

`--engineer-tier standard`와 `--engineer-timeout 0`으로 등급·timeout을 설정할 수 있다.
기존 `--claude-tier`, `--claude-timeout`도 같은 옵션의 호환 별칭이다. 모델 설정은
`agent/tiers.json`의 `claude` / `codex_engineer`로 분리된다. 계획/리뷰의 `gpt` 설정은 바꾸지 않는다.
Codex 구현은 `gpt-6-astra`이며 standard·light는 low, heavy는 medium, creative는 high다.

Codex의 초기 권한은 research/ 기준 workspace-write다. 이 서버에서는 해당 sandbox가 NVIDIA
접근을 막고, 장치 파일만 허용하면 CLI 초기화가 실패하는 문제가 확인됐다. 위 GPU 실행 예시는
사용자가 명시적으로 `danger-full-access`를 선택하는 것이다. 이 선택도 서버에 저장된다.
이 모드는 OS 파일쓰기 제한 없이 현재 계정의 호스트 권한으로 실행하므로, 연구 폴더 밖 쓰기
금지는 작업 정책으로 지키며 OS 강제 보호라고 주장하지 않는다. 계획/리뷰는 read-only를 유지한다.
작업 폴더 쓰기만 필요하면 `--codex-engineer-sandbox workspace-write`로 선택할 수 있다.

Codex는 저장된 CLI 인증을 사용하되 사용자 config는 무시하고 모델·권한을 이 호출에서 고정한다.
로그인 셸은 끄며 medgemma 환경과 CUDA_VISIBLE_DEVICES를 상속한다.
Claude의 도구 allowlist를 흉내 내지 않으며 완전히 같은 보안 구현은 아니다. 연구 코드·결과 쓰기,
공개 자산 조회와 격리 환경 구성은 허용하되 상위 관리 파일·모델 캐시·기존 데이터는 보존한다.
자동 API 과금 전환이나 실패 시 권한 승격은 하지 않는다. Codex CLI가 PATH에 있어야 한다.
비대화형 실행·JSONL·세션 재개는 [공식 Codex 실행 문서](https://developers.openai.com/codex/noninteractive)를 따른다.

반복별 `engineer_backend.json`에 실제 담당을 기록한다. Codex 구현의 세션·도구 로그·사용량은
`codex_engineer_session.txt`, `codex_engineer_stream.jsonl`, `codex_engineer_usage.json`으로 분리한다.
계획/리뷰와 세션을 공유하지 않는다. 기존 기록 호환을 위해 구현 보고서·메타·완료 응답은
`claude_report.md`, `claude_meta.json`, `claude_result.raw.json` 이름을 유지한다.
`--usage`에서 Codex 구현 사용량도 따로 확인한다. 토큰은 구독 잔여량을 의미하지 않는다.

## 연구 루프의 GPU 활용

연구 자원 기준은 `agent/RESOURCE_POLICY.md`에 있다. 현재 두 GPU의 실제 여유 메모리 안에서
추론·경량 학습과 baseline·ablation을 적극 수행한다. pilot 이후에는 타당성과 처리량을 근거로
본실험을 진행하며, 일률적인 1시간 금지나 45/55 GPU-minute 제한은 적용하지 않는다.

```bash
python orchestrator.py --gpus 0,1
```

계획·구현·리뷰와 Claude 세션 재개 호출에 최신 자원 정책이 전달된다. 과거 계획·결과는
보존하고 미완료 작업부터 새 정책을 적용한다. 연구 목표 이력을 새로 시작할 필요는 없다.
이미 실행 중인 에이전트 호출에는 소급 적용되지 않으므로 다음 호출 또는 재개 때 반영된다.

후속 실험에서는 GPU당 worker 1개를 고정하지 않는다. 같은 GPU에 여러 worker를 올리는 구성이나
batch 확대를 짧게 비교해 전체 처리량·peak 메모리·출력 정합성으로 결정한다.
두 GPU에 각 2개 worker도 가능하지만 자동으로 4개를 띄운다는 뜻은 아니다.
현재 실행 중인 iter_009 실험은 그대로 마치며, 최신 정책은 다음 계획·리뷰·구현 호출에 재시작 없이 전달된다.

`--claude-timeout` 기본값은 `0`(시간 제한 없음)이다. 필요한 경우 초 단위 양수를 지정해
제한할 수 있다. 기존 Telegram 정지 명령과 `agent/STOP`에 의한 단계 종료 후 정지는 유지된다.
장시간 실험에는 진행 로그·checkpoint·재개 기능이 필요하다.

## 연구 판정과 코드 재사용

관리 계층과 연구 계층은 별도 Git 저장소다. 상위 `main`의 오케스트레이터·공통 정책·프롬프트·테스트는
`research/`의 접근법 브랜치를 전환하거나 해당 접근법을 중단해도 유지한다. 연구 실패는 정책 되돌림의
근거가 아니다. 실험별 설정과 판정은 해당 연구 코드·iter 기록에 남기고, 유용한 공통 개선은 별도로
검토·테스트·커밋한다. 관리 코드에 별도 기능 브랜치가 필요하면 실행 폴더가 아닌 worktree에서 작업해
검증 후 main에 반영한다. 정책 자체에 결함이 있으면 연구 브랜치 복귀와 별개로 수정한다.

연구 기록 자동 커밋은 관리 코드 변경을 포함하지 않는다. 관리 변경은 완료 시 선별 커밋하고,
허용된 원격·범위에서 push한다. 상위 저장소 push에는 별도 저장소인 연구 코드와 Git 제외 데이터·결과가
포함되지 않으므로 각각의 원격 보관·백업은 별도로 구성해야 한다.

`agent/RESEARCH_POLICY.md`에 실험·리뷰 기준을 정리했다. 개발 이력 보존·재사용 승인·가설 판정은 별개다.
Claude 구현 종료·안전한 중단 뒤에는 성공/실패와 무관하게 orchestrator가 소스 체크포인트를 만든다.
GPT는 저장 여부가 아니라 전체/모듈별 재사용 가능 범위를 판단한다. 새 접근법은 재사용 승인 커밋에서 시작한다.
특정 기반을 고를 때는 계획의 `reuse_iteration`을 쓴다(0이면 자동, 기존 브랜치는 그대로 유지).
소유 범위가 불명확한 미커밋 작업 등은 전환 시 stash·영구 Git ref·patch에 남기며,
위치와 검토 기록은 `agent/CODE_ASSETS.md`에서 확인한다. results/ 등 git 제외 파일은 별도다.

다른 접근법의 일부 코드만 필요하면 GPT가 `reuse_assets`에 출처 commit SHA·파일·필수 검증을 지정한다.
실행 전 선별 반입하며 누락·충돌은 덮어쓰기 대신 중단한다. 현재 브랜치에 이미 있는 코드는 그대로 쓴다.
모듈별 재사용 판정은 리뷰의 `code_assets`에 남긴다. 실패한 실험의 로더·평가기만 가져올 수도 있다.

반복 폴더의 `checkpoint.json`/`checkpoints/`에는 중단·완료 이력, `commit.json`에는 리뷰 대상 SHA,
`code_review.json`에는 해당 SHA의 재사용 판정, `reuse_manifest.json`에는 반입 출처와 검증 조건이 남는다.
리뷰 diff는 `changes.patch`의 구현 전→후 SHA 비교이므로 커밋 후에도 사라지지 않는다.
기존 사용자 변경·데이터·모델·비밀정보 의심 파일은 자동 커밋에서 제외한다. 브랜치는 자동 삭제하지 않는다.
비밀정보 검사 오탐은 검토된 정확한 값과 사용 문맥에 한정해 보완한다. 현재 iter_010의 HF loss
테스트 항목명은 `check()` 첫 인자일 때만 허용하며, 파일 전체나 `hf_` 접두사를 통째로 제외하지 않는다.
해당 파일에 다른 토큰이 있으면 여전히 보관·브랜치 전환을 차단한다. 탐지 검사는 완전한 보안 감사가 아니다.
과거 기록은 소급 커밋/승인하지 않으며, 현재 계획 전인 iter_009부터 새 흐름을 적용할 수 있다.

`--max-attempts`는 유효한 실험 누적 후 재평가 기준이다. 횟수만으로 자동 포기하지 않는다.
불확정·실행 실패·설계 기각을 구분하고, 리뷰는 현재 결론 무효 / 재사용 전 수정 / 추후 개선을 나눈다.
계획에는 실제 VLM 출력 검증과 baseline으로 이어지는 경로를 명시한다.

중단된 iter_008은 `agent/runs/iter_008/execution_amendment.md`를 구현·리뷰 프롬프트에 함께 전달한다.
이전 소스 11개의 복구 출처와 미해결 결함은 같은 폴더의 `code_recovery.md`에 있다.
이 보완 작업 자체는 실험을 재시작하지 않는다.

## 단계별 실험 규모 (iter_011 이후 새 계획)

동작 확인 → 일부 표본의 가능성 탐색 → 근거에 따른 규모 확대 → 독립 확인 순으로 진행한다.
매 epoch 전체 validation·모든 후보의 다중 seed 실행을 기본으로 삼지 않고, 고정 subset의 실제 출력과
학습 추세로 다음 단계를 판단한다. 표본·평가 빈도·확대/중단 기준은 결과를 보기 전에 정한다.
작은 실패를 전체 방법의 실패로 단정하지 않으며 필요한 본실험·GPU 활용·독립 검증은 유지한다.
상세 기준은 [RESEARCH_POLICY.md](agent/RESEARCH_POLICY.md)에 있다.

2026-09-24 사용자 지정에 따라 실행 중인 iter_010은 변경하지 않는다. 다음 새 계획부터 적용하며,
이를 위한 중단·RESUME.md·replan은 필요 없다. 이미 시작한 호출에 정책을 소급 주입하지 않는다.

## 중단 후 점검 내용을 반영해 재개

### GPT 문맥·계획 비용 관리 (2026-09-29)

모델과 사고 수준 설정은 유지한다. [GPT_USAGE_POLICY.md](agent/GPT_USAGE_POLICY.md)에 따라
GPT에는 접근법별 최신 관찰·최근 미해결 문제·코드 자산 색인·관련 한계 근거를 전달한다.
전체 INDEX/CODE_ASSETS/LIMITATIONS와 과거 계획·리뷰는 삭제하거나 축약해 저장하지 않는다.
다른 접근법 선택·재시도·코드 재사용 시 관련 원문의 검증 조건과 반증 범위를 확인해야 한다.
GOAL·현재 사용자 지시·공통 자원/연구/권한 정책은 계속 원문으로 전달한다.

일반 후속 계획은 1라운드 완료를 기본으로 한다. 추가 세션은 미해결 질문의 답이 선택·설계·해석을
바꿀 때만 요청하며 `--max-think-rounds 4`는 목표 횟수가 아닌 기존 안전 상한이다.
직전 사고 노트는 원문으로, 더 오래된 노트는 요약·질문·원본 경로로 전달한다.
같은 실험의 보완은 기준 plan 경로·SHA256과 유지/변경/미완료/회귀 검증 중심으로 작성한다.
리뷰는 변경 영향에 집중하되 새 원시 결과·실행 완료·누수·metric·필수 독립 검증을 생략하지 않는다.

`--usage`의 GPT 표에는 호출 시도별 전달 KiB가 추가된다. 실행 준비 실패도 포함할 수 있으며,
전달 바이트나 CLI 표시 토큰은 구독 소진율이 아니다. 절감 측정용 추가 모델 호출은 하지 않는다.
관리 코드 변경은 안전한 단계 경계에서 재시작 후 적용한다. 기존 실험을 replan/reset하지 않는다.

Telegram 일반 알림은 핵심 결과·중요한 한계·다음 행동 위주로 한 화면 분량으로 표시한다.
긴 실행 과정과 전체 결함 목록은 원본 기록에 보존하며, 결정 요청의 질문·답장 명령은 별도로 유지한다.
리뷰가 의미 있는 실제 관찰을 milestone으로 선정하고 실험 유효성이 확인되면 결과 알림에
`💡🔎 중요한 결과·관찰`을 표시한다. 유효한 음성 관찰도 가능하지만, 단순 실행 성공·미검증 가설·
실험 무효에는 발견 표시를 붙이지 않는다. JOURNEY 기록은 유지하고 마일스톤 중복 알림은 보내지 않는다.

GPT 입력은 `codex exec -`, Claude 입력은 `claude -p --input-format text`의 표준입력으로 전달한다.
전체 정책·기록·사고 노트의 UTF-8 원문을
비공개 임시 파일에 쓰고 stdin으로 연결하며, 종료 시 임시 파일을 닫아 제거한다. 명령행 인자 크기
제한을 피하기 위해 내용을 축약·삭제하지 않는다. 입력 byte 수와 SHA-256은 각 실행 로그
(`*_codex.log`, `claude_stream.jsonl`의 비JSON 메타데이터 줄)에 기록한다.
모델 context 한도와는 별개이며, 모델·사고 등급·권한·JSON 출력 규약은 바꾸지 않는다.

프로세스 실행 준비 오류(E2BIG, 실행 파일 누락, 권한 등)는 정상 중단 기록·Telegram 알림 경로로
처리한다. 예기치 않은 예외도 현재 단계와 오류 종류를 기록·알림하고 상세 traceback은 실행 로그에
남긴다. Telegram 전송은 기존 통신 상태에 의존하며, 오류를 성공으로 처리하거나 무한 재시도하지 않는다.

기본 실행은 **반복 횟수 제한 없이** 이전 리뷰·목표를 이어받아 계속한다 (`--max-iters 0`).
기본 `smart` 모드에서 사용자 판단이 필요한 경우 Telegram 확인을 기다리고, 목표 달성·정지 요청·
자동 복구 범위를 넘는 오류에는 멈춘다. 사용 한도 대기와 같은 접근법 재평가 기준은 유지한다.
횟수 제한 제거는 `--auto`(계획 확인 생략)와 다르다. 종료 조건을 무시하거나 같은 실패를 무조건 반복하지 않는다.
이번 실행만 제한하려면 `--max-iters 3`처럼 양수를 지정한다.

보완 지시가 없으면 기존 단계부터 재개한다. 방향을 수정하려면 중단·종료 확인 후
`agent/RESUME.md`에 지시를 적거나 `--replan`을 사용한다.

```bash
python orchestrator.py --replan "방법 개발 전에 공식 사용 조건에서 한계부터 검증해줘." --prepare-only
python orchestrator.py --status
python orchestrator.py --gpus 0,1
```

첫 명령은 전환 준비만 한다(에이전트·실험·알림 없음). 마지막 명령은 실제 연구를 재개한다.
미완료 반복과 세션은 삭제하지 않고 보존하며 새 반복에서 GPT 계획·새 Claude 세션으로 시작한다.
사용법: [RESUME_WORKFLOW.md](agent/RESUME_WORKFLOW.md), 템플릿: [RESUME_TEMPLATE.md](agent/RESUME_TEMPLATE.md).

한계 주장·근거는 [LIMITATIONS.md](agent/LIMITATIONS.md)에 누적한다. 재현 확인된 한계가 없는
method/confirmatory 계획은 --auto에서도 실행 전 보류한다. 기존 목표와 연구 코드 보존 정책은 유지한다.

## 보고서·알림의 가독성

사람이 읽는 계획·구현 보고서·리뷰·연구 기록·Telegram에는
[REPORTING_STYLE.md](agent/REPORTING_STYLE.md)의 공통 기준을 적용한다.
핵심 → 근거 → 의미·한계 → 다음 행동 순으로 짧게 정리하고, 상세 근거·재현 명령은 원문에 남긴다.
전문용어는 유지하되 필요한 경우 짧게 설명한다. 미검증·판단 보류·실행 실패와 목표 달성을 구분한다.

Telegram은 짧은 문단으로 보내며 원문 위치와 필요한 답장 명령을 함께 표시한다.
긴 내용을 축약하면 이를 명시하고 원문 확인을 안내한다. 추가 모델 호출은 하지 않는다.
실행·권한·자동 진행·검증 기준·JSON 형식은 바꾸지 않는다.
최신 기준은 다음 에이전트 호출(Claude 세션 재개 포함)에 전달된다. 알림 템플릿은 다음 orchestrator 실행부터 적용된다.
이미 저장된 과거 보고서 원문은 다시 쓰지 않는다.

## 연구 방향 재검토 (2026-09-27 보완)

큰 연구 목표는 유지하되, 점수 개선과 후속 투자 가치를 별도로 판단한다.
기준선 확보·불확정 반복·새로운 큰 투자 직전에는 현재 방법 개선 / 원인·능력 전이 진단 /
다른 연구 질문을 비교한다. success/improve만으로 같은 접근법을 자동 연장하지 않는다.

- 기준: `agent/RESEARCH_POLICY.md`의 **연구 질문과 다음 투자 판단**.
- 판단 원문: 각 반복 `plan.md`, `review.md`의 **Strategy Check / 연구 방향 판단**.
  구조화된 기록은 기존 `contribution_path`, `alternatives`, `goal_progress`, `next_task` 필드를 사용한다.
- 계획은 양성·음성·불확정 결과별 다음 행동을 정하고, 리뷰는 실행·성능·가설·기여를 구분한다.
  방향상 중요한 미확인 사항과 다음 판단은 기존 요약·Telegram 전달 경로에도 남긴다.
- iter_014는 기존 실험·조건부 후속 비교·평가를 유지한다. 다음 리뷰는 원래 기준으로 판정하면서
  후속 전략 재검토를 요청하고, 그다음 첫 새 계획에서 기존 checkpoint 진단 등을 비교한다.
  특정 새 연구 주제나 신규성을 미리 확정하지 않는다.
- 정책·역할 프롬프트는 다음 호출 시 다시 읽힌다. 이번 변경은 재시작이나 `--replan`이 필요 없고,
  진행 중인 반복을 교체하는 `RESUME.md`도 만들지 않는다. 별도 모델 호출·사용자 승인 단계를 추가하지 않는다.

## 논문 추천과 Telegram

가설만 세운 단계의 논문은 추천하지 않는다. 실제 비교·진단 실험에서 더 파볼 만한 긍정적 근거가
확인된 방향에 한해 GPT 리뷰가 최대 1편을 추천한다. 단순 학습 실행이나 불확정 결과의 보완 확대는
추천 근거가 아니며, 최종 논문 수준의 증명까지 기다려야 하는 것은 아니다.
이미 계획·문서에 인용한 논문도 사용자에게 추천한 적이 없다면 포함한다.

추천은 `agent/PAPERS.md`에 누적하고 기존 Telegram 알림으로 제목·링크·실험 근거·추천 이유와 한계·
먼저 읽을 부분을 전달한다. 적격 논문이 없으면 리뷰에 보류 이유를 남긴다.
상세 기준은 `agent/RESEARCH_POLICY.md`와 `agent/prompts/gpt_review.md`에 있으며 다음 리뷰 호출부터 적용된다.

## GPT·Claude 사용량 절감과 조회

새 계획은 일반 구현에 `standard`(Sonnet/medium)를 기본으로 선택한다. 어려운 디버깅·중요한
구현 판단은 `heavy`(Opus/low), 실제 새로운 방법의 설계·구현은 `creative`(Opus/high)로 구분한다.
`standard`의 GPT 리뷰는 기존 `heavy`와 같은 `normal`/low다. 필수 검증·독립 리뷰·GPU 실험 규모는 줄이지 않는다.
구체적인 기준과 재사용·로그 읽기 원칙은 [CLAUDE_USAGE_POLICY.md](agent/CLAUDE_USAGE_POLICY.md)에 있다.

```bash
python orchestrator.py --usage
```

모델·실험·알림 없이 과거 GPT·Claude 로컬 로그도 함께 집계한다. 호출 종료 시 각 반복의 `claude_usage.json`에
실패를 포함한 사용량을 저장한다. 세션 누적 비용·모델별 토큰은 중복 제거하며, 비용은 실제 구독 청구액이 아니다.
result 없이 끊긴 호출에는 미집계 사용량이 있을 수 있다. Claude stream의 `rate_limit_event`가
`rejected`와 `five_hour`/`seven_day`를 명시하면 모순된 월간 한도 안내문보다 이를 우선한다.
확인된 `resetsAt` + 60초 이후 같은 세션으로 재시도하며, 시각이 없거나 이미 지났으면 기본
30분 주기로 확인한다. 5시간 한도는 중단 시점부터 무조건 5시간 추가 대기한다는 뜻이 아니다.
대기 중 Telegram/status에 다음 재시도 시각을 표시하며, 총 대기 상한은 기존 기본 8시간
(`--limit-max-hours`)이다. 상한보다 늦은 초기화에는 상한에서 종료·알림한다.
구조화된 구독 거절 근거가 없는 월간 지출 한도는 자동 재시도하지 않고 중단·알림한다.
경고만으로 월간 지출 한도를 무시하지 않으며, 지출 한도 인상·유료 overage 전환은 하지 않는다.

읽기 전용 GPT 계획·리뷰가 마지막 `ERROR: Reconnecting... N/M` 상태에서 시간 초과되면
기존 1·5·15분 간격으로 최대 3회 재시도한다. 단순 장시간 사고의 timeout이나 구현 실행에는
이 예외를 적용하지 않는다. 30분 기본 제한·모델 등급은 유지하며, 로그와 완료된 사고 라운드는
보존한다. 미완료 호출은 새 세션으로 재시도하므로 그 호출의 일부 조사는 반복될 수 있다.

기존 계획·CLI 등급 지정·일반 재개 동작은 보존한다. 새 기준은 다음 새 계획부터 적용된다.
준비된 iter_009는 계획 전이므로 별도 reset/replan 없이 평소 명령으로 실행하면 새 기준을 사용한다.

GPT 계획은 `gpt-6-astra`의 `deep_medium`(medium)을 깊은 검토의 기본으로 쓴다.
`deep_high`(high)는 연구 방향·핵심 기여·중요한 해석을 결정할 때, 결정할 선택·어려운 근거·오판의
영향을 모두 기록한 경우 사용한다. `normal`·`light`는 low다. 문헌 검토·새 실험이라는 이유만으로
high를 고르지 않는다. 추가 사고 라운드는 남은 판단에 따라 medium↔high를 조정하며 기존 조사를 재사용한다.
`--plan-tier deep_medium`/`deep_high`는 계획만 고정한다. 기존 `--gpt-tier deep`는 계획·리뷰의
high 지정을 유지한다. 자동 선택에서 옛 `deep` 추천은 medium으로 해석하고 원본 기록은 보존한다.
구현·GPT 리뷰 등급, 최대 사고 라운드 4회, 필수 검증은 그대로다. 리뷰의 `deep`는 계속 high다.
선택 로직은 새 프로세스에서 적용하므로 실행 중 작업은 완료한 뒤 안전한 단계 경계에서 재개한다.
라운드별 실제 선택·근거는 `agent/runs/iter_NNN/think/round_NN.tier.json`과 `events.jsonl`에 남는다.
조사 중인 `think_more`에서는 긴 임시 구현 계획 대신 조사 근거·대안 비교·남은 질문을 남기고,
최종 `implement`에서 전체 계획을 작성한다. 이전 조사 노트는 잘라내지 않는다.
이미 확인한 자료는 활용하되 모순·미확인 세부·최신성 검증이 필요하면 다시 확인한다.

GPT 사용량은 `plan_usage.json`, `review_usage.json`에 남긴다. 기존 텍스트 로그의 `tokens used`
표시값 기반 참고치이며, 캐시·입출력 토큰 구분이나 과금·구독 소진율로 환산하지 않는다.
실제 구독 잔여량은 Codex CLI `/status` 또는 계정 usage dashboard에서 확인한다.
`python orchestrator.py --status`는 연구 진행 상태 조회이며 구독 잔여량 조회와 다르다.
# 진단에서 방법 개발로 넘어가는 기준 (2026-09-30)

새 계획은 `research_track`·`related_iterations`로 큰 질문의 이력을 연결하고,
`decision_contract`에 결과별 다음 행동·비용·종료 결정을 남긴다. 방법 개발은
`method_stage=pilot`(유효한 실제 관찰 기반 최소 대조 실험)과 `full`(validated 근거 기반 확대)을
구분한다. pilot도 사용법 검증·이전 full review·현재 결론의 무결성이 필요하며 자동 확대하지 않는다.
새 필드는 과거 계획에 소급 요구하지 않는다. 실행 중 iter_039의 실험·판정 기준은 유지한다.
상세 기준은 `agent/RESEARCH_POLICY.md`를 따른다. 기계 검사는 신규성·과학적 타당성을 보장하지 않는다.

## 비로그인 실행에서 Codex를 찾지 못할 때

오케스트레이터는 기존 PATH의 Codex를 우선한다. 없으면 `NVM_BIN`, `NVM_DIR` 또는 사용자
`.nvm/versions/node/*/bin`에서 Codex와 Node가 함께 설치된 경로를 찾아 자식 PATH에 추가한다.
conda Python·GPU 범위·모델 등급·구독 로그인은 유지하며, 전역 PATH 수정이나 자동 설치는 하지 않는다.
실제 연구 루프 시작 전 `codex --version`을 검사하므로 리뷰 단계까지 진행한 후에야 실행 경로
문제를 발견하지 않도록 한다. `--status`, `--usage`, `--prepare-only`는 이 점검을 실행하지 않는다.

## 별도 문헌·산업 수요 탐색기

의료 데이터 특성에서 출발하는 연구 분야·핵심 문제 탐색은
[discovery/README.md](discovery/README.md)를 참조한다. `discovery_orchestrator.py`는
gpt-6-astra/high로 문헌 조사·후보 심사만 수행하며 기존 실험 GOAL·Telegram·상태와 독립이다.
기본 실행은 상태 조회이고 `--run`으로만 탐색을 시작한다.
