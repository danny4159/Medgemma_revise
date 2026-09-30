# MedGemma 연구 프로젝트 — 에이전트 공통 정보

이 파일은 Codex(GPT)와 Claude Code가 모두 읽는다 (Claude는 CLAUDE.md에서 import).
역할별 규칙은 `agent/prompts/`에 있고 orchestrator.py가 프롬프트로 넘긴다.

언어: 모든 서술은 한국어로 작성한다. 기술 용어, metric 이름, 코드, 파일 경로, 명령어는 영어 그대로 써도 된다.

사람이 읽는 설명·보고서·알림·사용자 답변은 `agent/REPORTING_STYLE.md`를 따른다.
핵심을 먼저 쓰고 근거·의미/한계·다음 행동을 명료하게 나눈다. 전문용어는 필요한 만큼 유지한다.
가독성을 이유로 구현·검증·기계 판독 형식은 바꾸지 않는다.

## 환경
- Python: conda env `medgemma` (python 3.11). orchestrator가 PATH를 이 env로 맞춰 두므로
  기본 실험은 `python ...`으로 실행한다. 필요한 패키지 설치·별도 환경 생성은 자율적으로 허용한다.
  환경별 Python 절대경로나 `conda run -p ...`로 대상을 명시한다. 실행 중인 기본 환경은 변경하지
  않고 실험별 격리 환경을 우선한다. 설치·검증·재현 기록 기준은 `agent/RESOURCE_POLICY.md`를 따른다.
- `HF_HOME=/SSD1_1TB/home/milab/daniel/08_medgemma/hf_cache` (모델 캐시, 수정 금지)
- 모델: `google/medgemma-1.5-4b-it` (bf16 약 8~10GB VRAM)
- GPU: RTX 3090 24GB x2 (0, 1). 두 장 모두 마음껏 써도 된다 (사용자 허락).
  - 실행 직전에 `nvidia-smi`로 각 GPU의 남은 메모리를 확인하고, 남은 메모리가 많은 GPU부터 쓴다.
  - MedGemma 4B bf16은 프로세스당 약 8~10GB. 남은 메모리가 (필요량 + 2GB 여유) 이상이면
    같은 GPU에 프로세스를 더 올려도 된다 (24GB 한 장에 보통 2개). OOM이 나지 않는 선을 지킨다.
  - 다른 사용자의 GPU 프로세스는 절대 종료하거나 건드리지 않는다.
  - GPU당 1개 프로세스로 고정하지 않는다. 다음 실험 준비 시 batch 확대·GPU당 복수 worker의
    전체 처리량과 peak 메모리를 비교해 안전하고 빠른 구성을 선택한다. 상세 기준·적용 시점은
    `agent/RESOURCE_POLICY.md`를 따른다. 이미 실행 중인 iter_009 실험은 이 변경 때문에 중단하지 않는다.
  - orchestrator를 `--gpus`로 실행하면 그 GPU만 보인다 (CUDA_VISIBLE_DEVICES). 명령 앞에 직접 붙이지 않는다.

## 연구 자원 활용
- GPT 계획·리뷰는 `agent/GPT_USAGE_POLICY.md`의 관련 문맥·1라운드 기본·변경점 중심 기준을 따른다.
  모델 설정과 필수 결과 검증은 유지하고, 원본 출처를 보존한다. 모델 교체는 추후 별도 판단한다.
- `agent/CLAUDE_USAGE_POLICY.md`의 모델 선택·중복 작업 절감 기준을 따른다. 필수 검증·GPU 활용은 줄이지 않는다.
- `agent/RESEARCH_POLICY.md`의 실험 판정·코드 보존·재사용 기준을 따른다.
- `agent/RESOURCE_POLICY.md`의 사용자 의도와 실행 기준을 따른다.
- 제한된 GPU란 현재 두 장의 메모리·가용 자원 안에서 실행한다는 뜻이다. CPU-only나 GPU 최소 사용을 목표로 삼지 않는다.
- 두 GPU를 적극 활용하며, 타당성과 실행 가능성을 확인한 pilot은 필요한 본실험으로 확장한다.
  iter_011 이후 새 계획은 동작 확인과 가능성 탐색을 구분하고, 일부 표본·우선 1개 seed의 실제 결과로 확대 여부를 판단한다.
  매 epoch 전체 validation·모든 후보의 다중 seed 실행을 기본으로 삼지 않는다. 상세 기준은 `agent/RESEARCH_POLICY.md`에 있다.
  실행 중인 iter_010은 기존 계획을 유지하며 새 규모 규칙 때문에 중단·축소·재계획하지 않는다.
- 일률적인 1시간 GPU 금지나 근거 없는 45/55 device-minute 상한을 두지 않는다.
  실제 처리량과 필수 실험 규모로 예산을 정하고, 명시된 사용자 제한은 지킨다.

## 폴더 구조
- `orchestrator.py`, `notifier.py`, `agent/`: 연구 루프 오케스트레이터와 기록 (main 브랜치)
  - `agent/GOAL.md` 현재 연구 목표, `agent/GOALS.json` 목표 변경 이력 (반복 번호별)
  - `agent/JOURNEY.md` 연구 흐름: 목표에 의미 있는 진전(마일스톤)만, 고민→시도→개발→결과→의미
  - `agent/DECISIONS.md` 반복별 계획→결정(자동/사람)→개발→검증→커밋 기록
  - `agent/INDEX.md` 반복(iteration)별 한 줄 요약과 접근법 기록
  - `agent/PAPERS.md` 사용자에게 추천한 논문 목록
  - `agent/CODE_ASSETS.md` 체크포인트·모듈별 재사용 판정·미검증 보관본의 위치·출처
  - `agent/LIMITATIONS.md` 한계 주장별 현재 상태·근거·사용법 검사·미해결 질문 (자동 합성)
  - `agent/LIMITATIONS.json` 초기 점검 결과. 이후 변경은 각 review.json의 limitation_updates에 누적
  - `agent/RESUME.md` 미적용 사용자 보완 지시 (있으면 다음 실행/단계 경계에서 재계획)
  - `agent/interventions/` 보완 지시 원문과 적용 이력. 사용법은 `agent/RESUME_WORKFLOW.md`
  - `agent/runs/iter_NNN/` 반복별 plan.md, plan.json, claude_report.md, review.md, review.json, changed_files.txt
    - `code_baseline.json`, `checkpoints/`, `checkpoint.json`: 실행 전 범위·중단/완료 코드 이력
    - `commit.json`, `changes.patch`, `code_review.json`: 리뷰 대상 SHA·구현 전후 diff·재사용 판정 연결
    - `reuse_manifest.json`: 선별 반입한 파일·출처 SHA·필수 검증 조건 (반입은 승인 아님)
- `research/`: 오케스트레이터 연구 코드. 자체 git 저장소이고 접근법마다 `approach/<id>` 브랜치를 쓴다.
  브랜치·커밋은 orchestrator가 관리한다. 결과는 `research/results/` (git 제외).
- `legacy/`: 오케스트레이터 이전에 Claude와 대화하며 진행한 MedGemma 한계 분석 기록 (읽기 전용)
  - `legacy/scripts/` 데이터 수집(01)·평가(02)·진단(03)·공식 형식 재검증(04)·해법 검증(05)
  - `legacy/docs/MEDGEMMA_평가_전체정리.txt` 지금까지의 연구 정리 (맨 앞 "중대 정정" 먼저 읽을 것)
  - `legacy/eval_samples/` 입력 데이터, `legacy/eval_results/` 이전 실험 결과
- `hf_cache/`: 모델 캐시 (수정 금지)

## 관리 정책과 연구 브랜치의 독립성

- 공통 관리 코드·정책·프롬프트·테스트·README의 기준은 상위 저장소 `main`이다.
  `research/`의 접근법 전환·중단·실패 때문에 이 파일들을 이전 버전으로 되돌리지 않는다.
- 실험별 설정·가설·판정은 연구 코드와 해당 iter 기록에 남긴다. 공통 규칙 변경은 상위 저장소에서
  검토·테스트 후 별도 커밋한다. 실패한 접근법에서 얻은 유용한 공통 개선도 별도로 검토해 유지한다.
- 상위 관리 코드의 기능 브랜치가 필요하면 별도 worktree에서 개발하고 검증 후 main에 반영한다.
  실행 중인 오케스트레이터 작업 폴더의 상위 브랜치를 바꾸지 않는다. 결함 있는 정책의 수정·되돌림은
  연구 브랜치 복귀와 구분하여 명시적으로 처리한다.
- 상위 저장소 push는 제외된 `research/` 저장소·모델·데이터·결과를 백업하지 않는다.
  자동 기록 커밋에 관리 변경을 섞지 않고, push는 사용자가 허용한 원격·범위에서 별도로 수행한다.

## 중단 후 보완 작업을 하는 에이전트

- 일반 실행은 `--max-iters 0`(기본)으로 반복 횟수 제한 없이 진행한다. 목표·직전 리뷰를 이어받으며
  `smart`의 사용자 확인, 목표 달성·오류·정지 처리와 재평가 기준은 유지한다. `--auto`를 임의로 추가하지 않는다.
  유한 실행이 필요할 때만 사용자가 지정한 양수 `--max-iters`를 사용한다.

- 사용자가 보완·재계획을 요청하면 GOAL을 임의 변경하거나 --reset하지 않는다.
- 코드/운영 규칙 수정만으로 이미 저장된 계획이 재작성되지는 않는다. 재계획이 필요하면
  RESUME.md에 사용자 의도·유지할 것·바꿀 것·검증 기준을 명시하거나 --replan을 사용한다.
- `python orchestrator.py --prepare-only`는 보완 전환만 적용하며 모델·실험·알림은 실행하지 않는다.
  실행 중인 orchestrator를 먼저 정상 중단하고 종료를 확인한다. 새 실행은 lock으로 중복을 거부한다.
- 기존 plan·think·Claude 세션·결과를 지우지 않는다. 이전 반복의 superseded 표시는 사용자에 의한
  전환이며 실패/DONE이 아니다. 원본과 코드 보관 위치를 사용자에게 알려준다.
- 실험 재시작은 별도 요청 범위에 맞춘다. 보완 세팅 요청만으로 GPU 실험을 자동 시작하지 않는다.
