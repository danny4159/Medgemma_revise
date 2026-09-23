# Work Performed

- **결론**: 계획한 24개 학습·평가를 모두 끝냈고 완료 판정(`eval_complete=true`)을 받았다. MLP의 Z − U(P(Z)) coarse soft-IoU 차이는 **+0.0003**, 95% CI [−0.0010, +0.0016]으로 투자 기준(≥0.03, CI 하한>0)에 미달했다. 이번 설정에서 pooling 가설은 **지지되지 않았다**. 좌표 canvas가 assumed 상태라는 조건이 붙은 결과다.
- **공식 자료 조회 (1단계)**: 공식 NIH Box의 공개 shared link로 README·FAQ·LOG PDF, `BBox_List_2017.csv`, `Data_Entry_2017_v2020.csv`를 받았다. 인증은 필요 없었고 10.6 MB, 요청 5건이었다(20 MiB·15분 예산 이내).
  - README·FAQ·LOG 어디에도 bbox 좌표계를 1024 PNG로 지정하는 직접 문장은 없다.
  - BBox CSV는 공식본과 미러가 **byte 단위로 같다**.
  - Data_Entry는 header의 열 이름 하나만 다르고(공식 `Patient Sex`, 미러 `Patient Gender`), header 아래 본문은 byte 단위로 같다.
  - README는 연락처 줄과 `OpenI`/`Openi` 표기만 다르다.
- **탐색 허용 gate (2단계)**
  - 13개 필수 검사를 다시 실행해 모두 통과했다.
  - 판정: canvas=assumed, 새 모순 없음 → `exploratory_probe_allowed=true`. 엄격한 `lesion_probe_ready=false`는 그대로 두었고 iter_005/006 파일은 수정하지 않았다(입력 hash가 실행 전후 같음).
- **전처리·추출 (3~5단계)**
  - L 영상은 같은 값을 RGB 세 채널로 복제했다. RGBA 1장(`00001369_000`)은 alpha가 모두 255라서 검정 배경 composite 결과가 RGB와 같다. 비불투명 영상이 0장이라 제외 민감도 분석은 하지 않았다.
  - 공식 processor(`Gemma3ImageProcessorPil`: 896 bilinear resize, rescale, normalize)만 썼다.
  - 모델 코드에서 feature 지점을 확인했다: Z = `vision_tower(...).last_hidden_state`(projector 입력), P = projector 안의 `AvgPool2d(4)` 출력. hook으로 둘 다 캡처했다.
  - backbone은 eval·no_grad·bf16으로 고정했다. RMSNorm·projection은 비교에 넣지 않았다.
- **head 학습·평가 (6단계)**: linear/MLP × Z/U(P(Z)) × lr{3e-4, 1e-3} × seed{0,1,2}로 24개를 학습했다. validation으로 lr을 고른 뒤(두 head 모두 1e-3), 선택 파일을 먼저 쓰고 그 다음에만 test 점수를 계산했다. 위치 prior·image-swap 대조군과 공유 patient bootstrap(2,000회)을 적용했다.
- **검증 (8단계)**: 8개 테스트를 CPU에서 모두 통과했다(`all_pass=true`).
  - 합성 패턴 token 정렬
  - affine head의 coarse logits·loss·gradient 동등성(float64, 1e-10)과 MLP는 다르다는 확인
  - unknown 쌍의 gradient 0
  - ID·patient 교체, feature 변조, feature 행 순서 교체, shape 변경을 cache가 모두 거부
  - donor가 같은 split·클래스의 다른 patient이고 전단사
  - seed 평균 후 bootstrap(seed를 patient처럼 쌓으면 거부)
  - batch 순서와 초기 가중치 공유
  - metric 집계 일치

# Files Changed

모두 새로 만든 파일이다. 기존 파일은 수정하지 않았다. `git status`는 권한 승인이 필요해 실행하지 못했다.
- `research/fetch_nih_official_iter007.py`: 공식 Box 공개 조회
- `research/gate_pooling_probe_iter007.py`, `research/pooling_probe/gate.py`: 공식본↔미러 대조와 탐색 허용 정책
- `research/pooling_probe/__init__.py`
- `research/pooling_probe/features.py`: 전처리, 재구현 P, 모델·processor digest, cache 검증
- `research/pooling_probe/probe.py`: head, coarse loss, 학습·예측
- `research/pooling_probe/evaluate.py`: seed 평균, swap, paired bootstrap
- `research/extract_pooling_features_iter007.py`: GPU 추출과 정렬 검사
- `research/run_pooling_probe_iter007.py`: 24개 학습, LR 선택, test 평가, 판정
- `research/test_pooling_probe_iter007.py`: 검증 테스트
- `research/notes/pooling_probe_iter007.md`: 결과 요약

# Commands / Experiments (실제 실행한 명령과 성공/실패)

1. `python research/fetch_nih_official_iter007.py --page .../iter_006/coord_evidence/nih_box_official_page.html --out results/iter_007/official` → **성공** (파일 5개 모두 받음)
2. `python research/gate_pooling_probe_iter007.py --src results/iter_005 --evidence results/iter_006/coord_evidence --official results/iter_007/official --out results/iter_007` → **성공** (두 번 실행: 1차 결과에서 Data_Entry 전 행이 달라 보여, 원인이 열 이름 변경뿐인지 확인하는 검사를 추가하고 다시 실행)
3. `python research/extract_pooling_features_iter007.py --gpu 1 --split train --limit 4 --out results/iter_007/pilot` → **성공** (pilot: 영상당 0.39초, peak 9.1 GB)
4. `python research/run_pooling_probe_iter007.py --gpu 1 --features results/iter_007/pilot --pilot --out results/iter_007/pilot_train` → **성공** (24개 학습 예상 0.58 device-min, 추정치)
5. `python research/test_pooling_probe_iter007.py --out results/iter_007/tests_iter007.json --pilot results/iter_007/pilot` → **성공** (8/8 통과)
6. `nvidia-smi` 확인(두 GPU 모두 거의 비어 있음) 후 `python research/extract_pooling_features_iter007.py --gpu 1 --out results/iter_007/features` → **성공** (160장, 57.5초, peak 9.1 GB)
7. `python research/run_pooling_probe_iter007.py --gpu 1 --features results/iter_007/features --out results/iter_007/probe --extract-device-min 1.3` → **성공** (24개 완료, 34초)

- 총 GPU 사용량은 약 1.9 device-min으로 45 상한보다 훨씬 작다. 작업량이 작아 GPU 1장으로 순차 실행했다. 병렬 실행은 모델 로딩 비용만 늘어서 하지 않았다. OOM은 없었다.
- 모델 revision은 `91850547d9f0…`, 환경은 medgemma env (python 3.11.16, torch 2.14.0+cu130, transformers 5.17.0)다. torchvision이 설치되어 있지 않아 AutoProcessor가 PIL 백엔드로 로드됐다. 설정값은 `preprocessor_config.json`과 같다.

# Results (수치와 결과 파일 경로)

test 48명 기준이고, 각 수치는 3 seed를 patient 단위로 평균한 coarse soft-IoU(patient macro)다.

| 방법 | coarse soft-IoU | 클래스별 [Atel, Eff, Cardio, Pneu] |
|---|---|---|
| MLP Z | **0.2574** | 0.076 / 0.153 / 0.526 / 0.293 |
| MLP U(P(Z)) | **0.2571** | 0.075 / 0.153 / 0.525 / 0.292 |
| linear Z = linear U(P(Z)) | 0.1990 | 0.069 / 0.116 / 0.398 / 0.221 |
| train 위치 prior | 0.1751 | 0.038 / 0.070 / 0.472 / 0.123 |
| MLP Z image-swap | 0.1583 | |

**투자 기준 판정**
- MLP Z − U(P(Z)) = **+0.0003**, CI [−0.0010, +0.0016] → 0.03 기준 **미달**, CI 하한>0 **미달**
- seed별 차이: −0.0005, +0.0004, +0.0010
- 클래스별 차이: +0.0005, −0.0003, +0.0006, +0.0012 → 양수 3개 클래스(기준 충족이지만 크기는 무의미)
- Z − prior = +0.082, CI [0.057, 0.107] → 충족
- Z − image-swap = +0.099, CI [0.070, 0.130] → 충족
- 해석: head는 영상별 위치 정보를 실제로 읽지만, 그 정보는 pooling 후 feature에서도 똑같이 읽힌다.

**linear 대조군**: 두 조건의 coarse prob 차이는 최대 3.6e-7, macro 차이는 2.3e-10이다. 학습 전에 고정한 허용오차(prob 5e-3, macro 1e-3) 안이라 통과했다.

**fine 부차 분석** (fine 해상도 loss는 쓰지 않았다): MLP Z − U(P(Z)) = −0.019, CI [−0.028, −0.010]로 오히려 Z가 낮다. fine 해상도를 감독하지 않았으므로 subcell 위치 정보의 증거로 해석하지 않는다.

**head 크기**: 파라미터는 linear 4,612개, MLP 148,100개다. 학습 시간은 run당 0.4–2.3초다.

**결과 파일** (`research/results/iter_007/` 아래)
- `gate_iter007.json`, `official/` (공식 원본, 쪽별 text, `fetch_summary.json`, download ledger)
- `features/cache_meta.json`, `features/extract_checks.json` (Z_bf16.npy 1.5 GB 포함)
- `tests_iter007.json`, `pilot/`, `pilot_train/pilot_cost.json`
- `probe/probe_results.json`, `probe/validation_selection.json`, `probe/status.json` (산출물 28개의 sha256 포함)
- `probe/predictions/*.npz` (24개), `probe/train_losses.json`, `probe/bootstrap_indices.npy`

# Problems

- 두 head 모두 validation이 lr 후보 중 큰 쪽(1e-3)을 골랐고, 200 update 끝에도 loss가 아직 내려가는 중이었다(MLP 약 0.10). 학습이 덜 된 상태일 수 있다. 다만 결과를 본 뒤 설정을 바꾸지 않는다는 계획에 따라 그대로 판정했다.
- 좌표 canvas는 공식 문서로도 여전히 assumed다. 공식 원본 영상 파일은 받지 않았으므로 영상 pixel이 원배포와 같은지는 unverified로 남아 있다.
- `git status`는 권한 승인이 필요해 실행하지 못했다. 변경 파일 목록은 직접 정리한 것이다.
- 정리 과정에서 발견한 코드 문제 두 가지가 있다. 이번 결과 수치에는 영향이 없다.
  - `run_pooling_probe_iter007.py`의 `complete` 판정은 테스트 통과·gate·24개 완료·산출물 개수만 본다. 정렬·pooling·linear 대조 검사는 기준 5(`integrity_alignment_linear_complete`)와 `all_criteria_pass`에만 반영된다. 이번에는 모든 검사가 통과해서 결과는 같다.
  - `extract_pooling_features_iter007.py`는 입력 hash 불일치 시 파일 hash만 확인하고 pixel hash는 확인하지 않는다.

# Recommendation to GPT

- 결론: 16×16 coarse target, 동일 용량 pointwise head 조건에서는 pooling 전후 feature의 위치 readout이 사실상 같다(차이 0.0003). "projector pooling이 병변 위치 정보를 잃는다"는 방향에 경량 adapter를 투자할 근거는 없다. 이 approach는 이번 설정 기준 **가설 불지지**로 닫기를 권한다.
- 남은 가능성은 16×16보다 세밀한 수준의 위치 정보뿐이다. 이를 보려면 fine(64×64) loss를 사전 등록한 별도 실험이 필요하다. 다만 현재 fine 결과는 오히려 Z가 낮고, bbox target 자체가 거칠어 기대 이득이 작다.
- 대신 볼 만한 방향: vision feature 수준(Z와 P(Z) 모두)에서 위치 정보가 선형·MLP로 읽힌다(prior보다 +0.08, image-swap보다 +0.10). 그렇다면 grounding 한계는 pooling이 아니라 LLM/decoder가 위치를 출력하는 단계(언어화·좌표 출력)에 있을 가능성을 다음 후보로 검토할 수 있다. 이번 결과는 이를 증명하지 않는다.

SELF_CHECK: PASS
SUMMARY: 공식 NIH 자료 대조 후 탐색 gate를 통과해 MedGemma 1.5 Z 대 U(P(Z)) probe 24개를 완료했다. MLP coarse soft-IoU 차이는 +0.0003 (CI −0.0010~+0.0016)으로 투자 기준에 미달해, 이번 설정에서 pooling 가설은 지지되지 않았다.

# [orchestrator] 권한 거부된 도구 호출
- Bash: git -C /SSD1_1TB/home/milab/daniel/08_medgemma/research ls-files
- Bash: grep -n "class Gemma3MultiModalProjector" -A 45 /home/test/.conda/envs/medgemma/lib/python3.11/site-packages/transformers/models/gemma3/modeling_gemma3.py
- Bash: grep -n "def get_image_features" -A 30 /home/test/.conda/envs/medgemma/lib/python3.11/site-packages/transformers/models/gemma3/modeling_gemma3.py
- Bash: git -C /SSD1_1TB/home/milab/daniel/08_medgemma/research status --short
