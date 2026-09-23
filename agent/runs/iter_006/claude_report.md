# Work Performed

계획의 CPU 작업 7개를 모두 구현하고 실제로 실행했습니다. GPU는 쓰지 않았고(0 device-min), 모델도 불러오지 않았습니다.

결론부터: 자료 무결성 검사는 13개 모두 통과했지만, **엄격한 `lesion_probe_ready`는 false**입니다. bbox 좌표가 1024×1024 영상 기준이라고 직접 적은 문서를 찾지 못했기 때문입니다. 계획 기준으로는 "근거가 부족하면 false와 구체적 blocker를 낸다"가 검증 구현의 성공입니다. 다만 데이터 준비 완료나 GPU probe 진입과는 구분해야 합니다.

1. **NIH 좌표 근거 수집** (`fetch_nih_coord_evidence.py`, `grounding_data/coord_evidence.py`)
   - 받은 자료: 저자 README 미러 PDF, 원논문(arXiv 1705.02315v5), 공식 Box 폴더 페이지. 인용문이 해당 쪽에 실제로 있는지는 코드가 확인합니다.
   - 문서에 명시된 것:
     - README 1쪽: 배포 PNG가 1024×1024
     - README 2쪽: x,y는 box 좌상단, w,h는 폭·높이
     - 논문 4쪽: 영상을 1024×1024로 resize
     - 논문 8쪽: 원 영상 크기(1024×1024)와 비교하는 간접 언급
   - 추론인 것: "bbox 좌표 = 1024 PNG pixel 좌표". 이를 직접 말하는 문장은 없어서 판정은 `assumed`입니다.
   - 논문은 983영상·1,600 box라고 적었지만 배포 CSV는 880영상·984 box입니다. 수치가 서로 다릅니다.
   - 새로 알게 된 점: 공식 Box 목록과 파일 크기를 비교해 보니 미러 README PDF와 `Data_Entry_2017_v2020.csv`가 공식본과 **크기가 다릅니다**.
     - README: 847,223 B / 848,327 B
     - Data_Entry: 9,003,499 B / 9,003,496 B
     - BBox CSV와 두 list 파일은 크기가 같습니다. 다만 크기가 같다고 동일한 파일이라는 보장은 없어서, 미러의 원본 동일성은 여전히 unverified입니다.
2. **QES verification 집합 재생성 검사** (`qes/preflight.py`)
   - `check_subsets()`가 저장된 목록을 `fixed_subsets(requests)`로 다시 만든 결과와 대조합니다. 대조 대상은 현재 입력에서 재계산한 requests입니다.
   - 필수 key가 빠지거나 추가 key가 있거나, 중복·누락·추가·같은 크기의 ID 교체가 있으면 거부합니다.
   - 목록 순서는 의미가 없는 것으로 정했습니다. 중복은 정규화 전에 거부하고, 그다음 ID 집합으로 비교합니다.
   - 필수 파일이 없거나 JSON 파싱이 실패해도 `PreflightError`가 납니다. runner·selector·evaluator가 모두 이 검사를 거칩니다.
3. **평가 상태 fail-closed** (`evaluate_qes.py`)
   - 평가를 시작하면 상태를 running으로 바꾸고, 이전 metrics·표·overlay·gate 기록을 `invalidated/<run_id>_start/`로 옮깁니다. 삭제하지 않습니다.
   - 모든 산출물을 staging에 다 쓴 뒤에만 게시합니다. 이후 `evaluation_status.json`에 complete와 산출물 hash를 기록합니다.
   - gate 실패, 예외, 게시 도중 실패가 나면 이미 게시된 산출물도 무효화합니다.
   - prediction 수집 완료(`prediction_collection`, selector의 `completion.json`의 `scope`)와 평가 완료(`evaluation`)는 서로 다른 필드로 분리했습니다.
   - `load_complete_metrics()`는 상태와 hash가 모두 맞을 때만 metrics를 돌려줍니다.
4. **NIH readiness 필수 검사와 경고 분리** (`grounding_data/nih_audit.py`)
   - 필수 검사 13개를 둡니다. 검사 key가 없거나 값이 정확히 `True`가 아니면 실패로 봅니다.
   - 경고는 readiness에 영향을 주지 않습니다: Infiltrate→Infiltration 표기 대응, 선택 영상 모두가 공식 test 소속이라는 점.
   - `prepare_grounding_data.py`의 과대 판정 `canvas_verified_1024`는 일관성 검사로 이름과 의미를 낮췄습니다.
   - 엄격한 readiness는 공통 감사를 호출해 판정합니다. `package_complete`는 `audit_run_complete`(감사 실행 완료)로 바꿨습니다.
5. **읽기 전용 재감사 경로** (`audit_grounding_iter006.py`): iter_005 자료를 입력으로만 씁니다. 실행 전후 입력 173개 파일의 hash가 같은지 기록합니다.
6. **클래스별 target과 probe 규약** (`grounding_data/class_targets.py`)
   - `(image, class)`별로 그 클래스 bbox만 합칩니다. fine은 64×64, coarse는 16×16입니다.
   - bbox가 없는 클래스는 unknown으로 두고 loss·metric에서 제외합니다.
   - 규약 함수: soft-IoU, `sigmoid(P(logits))`, masked BCE, 영상→patient 집계, train 위치 prior, 같은 split·같은 클래스 내 고정 derangement, 공유 patient bootstrap.
7. **명세 정정**: iter_005 노트의 "거짓이면 LLM/decoder 병목" 문장을 "미확정"으로 고쳤습니다. `lesion_probe_ready=true` 옆에는 정정 주석을 달았고, 새 명세 `notes/grounding_probe_spec_iter006.md`를 썼습니다.

# Files Changed

- **신규**
  - 실행·감사: `fetch_nih_coord_evidence.py`, `audit_grounding_iter006.py`
  - 모듈: `grounding_data/coord_evidence.py`, `grounding_data/nih_audit.py`, `grounding_data/class_targets.py`
  - 테스트: `test_qes_iter006.py`, `test_nih_readiness_iter006.py`, `test_class_targets_iter006.py`
  - 노트: `notes/grounding_probe_spec_iter006.md`
- **수정**: `qes/preflight.py`, `evaluate_qes.py`, `select_qes.py`(completion scope 필드), `prepare_grounding_data.py`, `notes/grounding_probe_spec_iter005.md`, `README.md`
- `legacy/`, `hf_cache/`, `agent/`, `results/iter_004`, `results/iter_005`는 수정하지 않았습니다. 입력 digest가 전후로 같습니다.

# Commands / Experiments (실제 실행한 명령과 성공/실패)

모든 명령은 `research/`를 기준으로 실행했습니다.

| 명령 | 결과 |
|---|---|
| `python fetch_nih_coord_evidence.py --out results/iter_006/coord_evidence` | 성공. 3개 자료, ledger 9.46 MiB, 2.9초, wall 3.7초 |
| `python test_qes_iter006.py --out results/iter_006/qes_iter006_tests` | 1회차: 테스트 harness 버그. JSON 파싱 예외를 `SystemExit`로만 잡으려 했습니다. 수정 후 **32/32 PASS** |
| `python test_qes_preflight.py --out results/iter_006/qes_entry_tests_regression` | **25/25 PASS** (회귀) |
| `python test_qes.py --out results/iter_006/qes_cpu_tests_regression` | **42/42 PASS** (회귀) |
| `python audit_qes_iter004.py --src results/iter_004 --out results/iter_006/qes_reaudit_iter004.json` | 실제 iter_004 자료에서 manifest(새 subset 재생성 검사 포함), predictions, verification이 통과. selection은 iter_005와 같이 구형식이라 incomplete |
| `python audit_grounding_iter006.py --src results/iter_005 --evidence results/iter_006/coord_evidence --out results/iter_006` | 성공 |
| `python test_nih_readiness_iter006.py ...` | **42/42 PASS** |
| `python test_class_targets_iter006.py ...` | **22/22 PASS** |
| `python test_grounding_targets.py --out results/iter_006/targets_tests_regression.json` | **21/21 PASS** (회귀) |
| `python -c` 두 번 | 1) `prepare_grounding_data.nih_readiness_from_outputs`를 iter_005 자료에 호출: 근거 있음 → integrity true / ready false / assumed, 근거 없음 → undocumented / false. 2) 전체 테스트 후 입력 digest 재확인: 동일 |

권한이 거부된 명령은 `git status --short -uall` 하나였고, 우회하지 않았습니다.

# Results (수치와 결과 파일 경로)

**QES**
- 다음 변형은 runner·selector·evaluator가 모두 거부했고, 현재 위치에 complete 산출물이 남지 않았습니다:
  - verification 목록과 기록의 동시 축소, 공집합
  - 같은 크기의 ID 교체(형식상 유효한 기록을 함께 넣은 경우)
  - 필수 key 누락(두 key 각각), 추가 key, 중복 ID, calibration 축소, list가 아닌 값
  - 파일 없음, JSON 손상
- 순서만 바꾼 목록은 통과했습니다.
- 상태 전이 B1–B17을 모두 확인했습니다:
  - 정상 평가 → complete
  - 다음 경우에는 incomplete가 되고 metrics·표·overlay·투자 판정이 남지 않음: 축소된 verification, verification 기록 수치 실패, `predictions.jsonl` JSON 손상, `selections.json` 누락, `requests.jsonl` 누락, 계산 도중 예외, complete 기록 직전 예외
  - 원상복구할 때마다 다시 complete
  - 게시 후 산출물을 변조하면 `load_complete_metrics`가 None을 반환
  - 원시 prediction은 옮겨지지 않음
- 결과 파일: `results/iter_006/qes_iter006_tests/qes_iter006_tests.json`

**NIH 재감사** (`results/iter_006/readiness_iter006.json`, `nih_reaudit_checks.json`, `nih_coord_evidence_judgement.json`)
- `audit_run_complete=true`, `integrity_gate_pass=true`, `coordinate_canvas_status=assumed`, **`lesion_probe_ready=false`**. blocker는 canvas 직접 근거 부재 하나뿐입니다.
- 보존 확인:
  - 160명, 80/32/48 split
  - 영상 160장의 file·pixel hash 일치
  - 입력 173개 파일 digest `a4c8ce3f…`가 감사 전후와 전체 테스트 후에 같음
  - split 재생성 결과가 manifest와 일치
- 결함 주입: 필수 검사 13개 각각이 최소 한 결함에서 실패함을 확인했습니다. 주입한 결함 종류:
  - bbox CSV: header 변경, trailing 값, 5열 행, 빈 행, NaN/Inf/-Inf 좌표, 0 폭, 음수 높이, 음수 원점, canvas 초과
  - Data_Entry·목록: 중복 ID, finding 연결 끊김, patient ID 변경, 열 누락, test_list 중복
  - metadata: blob 불일치(Data_Entry·README), listed blob id 누락
  - manifest: split 이동, 두 split에 같은 patient, 표본 삭제, annotation·patient 변조
  - 영상: pixel 1개 변경, 재인코딩, resize, 파일 누락, 다른 split 영상으로 교체
  - readiness 함수에 key 누락이나 True가 아닌 값(문자열, None, 1, dict 아님)을 넣은 경우

**클래스별 target** (`results/iter_006/nih_class_targets.npz`, `nih_class_targets_summary.json`)
- 크기: 160×4×64×64(fine), 160×4×16×16(coarse)
- 관측 쌍 167개. 다중 클래스 영상은 22장이며, 22장 모두 클래스별 target이 전체 union과 다릅니다.
- 오차: coarse와 fine 평균은 0.0, 직접 계산한 16 격자와는 1.1e-16입니다.
- 독립 raster로 확인한 클래스 간 누출은 0입니다.
- 관측 수(train/val/test): Atelectasis 22/10/13, Effusion 20/9/13, Cardiomegaly 20/8/12, Pneumonia 20/8/12.

# Problems

1. 좌표 canvas의 직접 근거가 없습니다. 공식 Box는 폴더 목록만 봤고 README 본문은 받지 않았습니다. 목록에 hash가 없어서 미러가 공식본과 같은지 확인할 수 없고, README·Data_Entry는 크기부터 다릅니다.
2. `prepare_grounding_data.py`의 `main()`은 수정 후 다시 실행하지 않았습니다. 다시 실행하면 재다운로드가 일어나기 때문입니다. 새 readiness 함수만 iter_005 자료로 직접 호출해 확인했습니다.
3. `audit_grounding_iter006.py`의 실제 자료 누출 검사는 target과 같은 함수를 쓰므로 순환 검사에 가깝습니다. 독립적인 확인은 `test_class_targets_iter006.py`의 손계산 fixture와 독립 raster 검사가 맡습니다.
4. 선택 영상 중 1장은 RGBA 모드입니다. hash와 크기는 맞지만 probe 입력 전처리에서 따로 처리해야 합니다.
5. pooling probe, feature 추출, head 학습은 계획대로 실행하지 않았습니다. 투자 기준 수치는 측정하지 않았습니다.

# Recommendation to GPT

- 측정 기반(QES gate, NIH 무결성, 클래스별 target, metric 규약)은 CPU 수준에서 닫혔습니다. 남은 것은 좌표 canvas를 `assumed`로 둔 채 probe를 진행할지에 대한 결정입니다. 선택지는 두 가지입니다:
  - (a) `assumed`를 명시한 채 "조건부 readiness"로 GPU probe에 진입한다. target이 이 가정에 의존한다는 caveat를 붙입니다.
  - (b) 공식 Box README 본문과 FAQ를 받아 hash와 문장을 확인한다. 소량 조회이며, Box 다운로드 API 접근이 가능한지부터 확인이 필요합니다.
- (a)로 가면 다음 반복에서 할 일:
  - vision tower feature 추출 비용을 train 영상 몇 장으로 실측합니다.
  - `class_targets.py` 규약 그대로 Z 대 U(P(Z))의 linear/MLP 비교를 합니다. 3 seed, 위치 prior, image-swap, 공유 bootstrap을 적용합니다.
- RGBA 영상 1장의 grayscale 변환 규칙을 probe 명세에 추가해야 합니다.

SELF_CHECK: FAIL
SUMMARY: QES subset 재생성·평가 fail-closed(32/32, 회귀 25/25·42/42)와 NIH 필수 gate 결함 주입(42/42), 클래스별 target(22/22)을 CPU에서 모두 통과했습니다. 160명 split과 hash는 보존됐지만, bbox canvas의 직접 문서 근거가 없어 엄격한 lesion_probe_ready=false(assumed)입니다. 미러 README·Data_Entry는 공식 Box 목록과 크기가 달라 원본 동일성도 미확인이고, prepare_grounding_data main은 재실행하지 않았습니다.

# [orchestrator] 권한 거부된 도구 호출
- Bash: git -C /SSD1_1TB/home/milab/daniel/08_medgemma/research status --short -uall
