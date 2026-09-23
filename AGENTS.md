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

## 코드 위치 (중요)
- 연구 코드의 정본은 git worktree `/SSD1_1TB/home/milab/daniel/08_medgemma_research`에 있다.
  접근법마다 `research/<approach_id>` 브랜치를 쓰고, 브랜치·커밋은 orchestrator가 관리한다.
- main 폴더(`08_medgemma`)의 `scripts/`, `docs/`는 worktree를 만들 때 복사한 옛 사본이다.
- 데이터(`eval_samples/`), 결과(`eval_results/`), 모델 캐시(`hf_cache/`)는 main 폴더에 하나만 있고
  worktree에서는 링크로 연결된다. 브랜치와 상관없이 공유된다.

## 디렉터리
- `scripts/01_data` 데이터 수집, `02_eval` 평가, `03_diagnosis` 진단,
  `04_official_format` 공식 형식 재검증, `05_remedy` 해법 검증
- `eval_samples/` 입력 데이터 (읽기 전용)
- `eval_results/` 실험 출력 (새 파일 추가는 가능, 기존 파일 덮어쓰기 금지)
- `docs/MEDGEMMA_평가_전체정리.txt` 지금까지의 연구 정리 (맨 앞 "중대 정정" 먼저 읽을 것)
- `agent/GOAL.md` 현재 연구 목표
- `agent/INDEX.md` 반복(iteration)별 한 줄 요약과 접근법 기록
- `agent/PAPERS.md` 사용자에게 추천한 논문 목록
- `agent/runs/iter_NNN/` 반복별 plan.md, plan.json, claude_report.md, review.md, review.json, changed_files.txt
