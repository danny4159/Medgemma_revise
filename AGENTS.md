# MedGemma 연구 프로젝트 — 에이전트 공통 정보

이 파일은 Codex(GPT)와 Claude Code가 모두 읽는다 (Claude는 CLAUDE.md에서 import).
역할별 규칙은 `agent/prompts/`에 있고 orchestrator.py가 프롬프트로 넘긴다.

언어: 모든 서술은 한국어로 작성한다. 기술 용어, metric 이름, 코드, 파일 경로, 명령어는 영어 그대로 써도 된다.

## 환경
- Python: conda env `medgemma` (python 3.11). orchestrator가 PATH를 이 env로 맞춰 두므로
  그냥 `python ...`으로 실행하면 된다. `conda activate`, `pip install`은 하지 않는다.
- `HF_HOME=/SSD1_1TB/home/milab/daniel/08_medgemma/hf_cache` (모델 캐시, 수정 금지)
- 모델: `google/medgemma-1.5-4b-it` (bf16 약 8~10GB VRAM)
- GPU: RTX 3090 24GB x2 (0, 1). 공용 서버이므로 실행 전 `nvidia-smi`로 확인한다.
  GPU 선택은 명령 앞에 환경변수를 붙이지 말고 orchestrator의 `--gpus` 설정을 따른다.

## 폴더 구조
- `orchestrator.py`, `notifier.py`, `agent/`: 연구 루프 오케스트레이터와 기록 (main 브랜치)
  - `agent/GOAL.md` 현재 연구 목표
  - `agent/JOURNEY.md` 연구 흐름: 목표에 의미 있는 진전(마일스톤)만, 고민→시도→개발→결과→의미
  - `agent/DECISIONS.md` 반복별 계획→결정(자동/사람)→개발→검증→커밋 기록
  - `agent/INDEX.md` 반복(iteration)별 한 줄 요약과 접근법 기록
  - `agent/PAPERS.md` 사용자에게 추천한 논문 목록
  - `agent/runs/iter_NNN/` 반복별 plan.md, plan.json, claude_report.md, review.md, review.json, changed_files.txt
- `research/`: 오케스트레이터 연구 코드. 자체 git 저장소이고 접근법마다 `approach/<id>` 브랜치를 쓴다.
  브랜치·커밋은 orchestrator가 관리한다. 결과는 `research/results/` (git 제외).
- `legacy/`: 오케스트레이터 이전에 Claude와 대화하며 진행한 MedGemma 한계 분석 기록 (읽기 전용)
  - `legacy/scripts/` 데이터 수집(01)·평가(02)·진단(03)·공식 형식 재검증(04)·해법 검증(05)
  - `legacy/docs/MEDGEMMA_평가_전체정리.txt` 지금까지의 연구 정리 (맨 앞 "중대 정정" 먼저 읽을 것)
  - `legacy/eval_samples/` 입력 데이터, `legacy/eval_results/` 이전 실험 결과
- `hf_cache/`: 모델 캐시 (수정 금지)
