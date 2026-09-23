# iter_006 grounding 측정 기반: 좌표 근거, fail-closed readiness, 클래스별 target, probe 규약

이 노트는 iter_005 명세(`grounding_probe_spec_iter005.md`)를 갱신한다. 이번 반복에서는 GPU를 쓰지 않았다(0 device-min).
모델 feature 추출과 head 학습은 실행하지 않았고, pooling 정보 손실 가설은 여전히 **미검증**이다.

## 1. NIH bbox 좌표 근거 (`results/iter_006/nih_coord_evidence_judgement.json`)

코드(`grounding_data/coord_evidence.py`)가 아래 인용문이 해당 쪽 text에 실제로 있는지 확인했다. 원문 PDF와 쪽별 text는 `results/iter_006/coord_evidence/`에 있다.

| 구분 | 출처 (sha256 앞 12자) | 쪽 | 내용 |
|---|---|---|---|
| documented | NIH 저자 README, HF 미러 PDF (`93d1614fa2ec`) | 1 | "112,120 frontal-view chest X-ray PNG images in 1024*1024 resolution" |
| documented | 같은 README | 2 | "Bbox[x, y, w, h]. [x y] are coordinates of each box's topleft corner. [w h] represent the width and height of each box." |
| documented | Wang et al. CVPR 2017, arXiv 1705.02315v5 (`d2053b286b2c`) | 4 | "resized as 1024×1024 bitmap images" |
| documented (간접) | 같은 논문 | 8 | heatmap 32×32와 "original image dimensions (1024 × 1024)"를 대비하고, 계산한 B-Box를 GT B-Box와 비교한다 |
| documented | 같은 논문 | 7 | "983 images with 1,600 annotated B-Boxes". 배포 CSV는 984 box / 880 영상으로, 논문 기술과 수치가 다르다 |
| **inferred** | 위 항목들의 연결 | – | bbox 좌표를 배포 1024×1024 PNG pixel 좌표로 해석한다. **이를 직접 말하는 문장은 찾지 못했다** |

- 판정: `coordinate_canvas_status = assumed`, `direct_canvas_statement_found = false`.
- 좌표 범위(최대 x1 = 1012.1, y1 = 1022.0)와 영상 크기는 이 가정과 모순되지 않는다는 반증 검사일 뿐이다. 이것으로 verified로 올리지 않는다.
- 공식 NIH Box 폴더(`nihcc.app.box.com/v/ChestXray-NIHCC`)는 목록 JSON만 확인했다(파일 본문은 받지 않음). 공식 목록과 크기를 비교한 결과:
  - `BBox_List_2017.csv`(92,416 B), `test_list.txt`, `train_val_list.txt`는 미러와 크기가 같다.
  - `Data_Entry_2017_v2020.csv`는 공식 9,003,496 B(2025-04-02 갱신), 미러 9,003,499 B로 다르다.
  - `README_CHESTXRAY.pdf`는 공식 848,327 B(2022-12-18), 미러 847,223 B로 다르다.
  - 크기가 같아도 byte 동일성의 증거는 아니다. 미러와 원배포의 동일성은 여전히 **unverified**다.
- 네트워크: ledger 계상 9.46 MiB(9,915,379 B), 2.9초, 요청 3건. wall-clock은 3.7초다. ledger는 이 스크립트의 GET 본문만 계상한다. DNS·TLS·header와 다른 도구의 조회는 포함하지 않는다.

## 2. Readiness 계약 (`grounding_data/nih_audit.py`, `results/iter_006/readiness_iter006.json`)

- 필수 검사 13개(`REQUIRED_CHECKS`): metadata blob, bbox header·행 형식, 유한 좌표·양의 크기, 가정 canvas 범위, ID 중복, finding 연결, patient 연결, annotation과 CSV 일치, split 재생성, 160/80/32/48, 주분석 4클래스 최소 인원, 실제 영상 hash·크기, split 간 중복.
  - key가 없거나 값이 정확히 `True`가 아니면 실패로 본다(fail-closed).
- 경고(readiness에는 영향 없음): `Infiltrate`→`Infiltration` 표기 대응, 선택 영상이 모두 공식 test 소속이라는 점.
- `integrity_gate_pass = true`: 현재 자료로 13개 모두 통과했다. 선택 영상 160장의 file·pixel hash가 모두 일치했고, 감사 전후 입력 173개 파일의 hash도 같았다.
- **`lesion_probe_ready = false`**: 정의는 `integrity_gate_pass AND coordinate_canvas_status == documented_direct`다. blocker는 좌표 canvas 직접 근거 부재 하나뿐이다.
- `audit_run_complete = true`는 감사 실행이 끝났다는 뜻이다. 데이터 준비 완료를 뜻하지 않는다. iter_005의 `package_complete`는 이 두 필드로 대체했다.

## 3. 클래스별 target (`results/iter_006/nih_class_targets.npz`)

- 채널 순서는 `[Atelectasis, Effusion, Cardiomegaly, Pneumonia]`다.
- `fine[i,k]`는 영상 i에서 **클래스 k bbox들만의** union occupancy(64×64)이고, `coarse`는 그 4×4 평균(16×16)이다.
- `observed[i,k] = False`이면 해당 클래스 bbox가 없는 unknown이다. target은 0으로 채우지만 loss와 metric에서 제외한다. 음성 GT가 아니다.
- 관측 쌍은 167개다. 다중 클래스 영상은 22장이며, 22장 모두 클래스별 target이 전체 union target과 다르다.
- 관측 수(train/val/test): Atelectasis 22/10/13, Effusion 20/9/13, Cardiomegaly 20/8/12, Pneumonia 20/8/12.
- coarse와 fine 평균의 최대 오차는 0.0이고, 직접 16 격자와의 오차는 1.1e-16이다. 독립 raster로 확인한 클래스 간 누출은 0이다.

## 4. 후속 pooling probe 규약 (`grounding_data/class_targets.py`, 미실행)

- 비교: `Z`(pooling 전 64×64×1152) 대 `U(P(Z))`(실제 `AvgPool2d(4)` 후 nearest upsampling).
- Readout: 동일 용량의 **4-output pointwise** linear head와 1-hidden-layer MLP head를 둔다. paired 조건마다 초기화 seed, label, 영상, batch 순서, update 수를 맞춘다.
- Loss: `masked_bce`로 관측 클래스 channel만 사용한다.
- 출력: fine은 `sigmoid(logits)`, coarse는 `sigmoid(P(logits))`로 고정한다. `P(sigmoid(·))`가 아니다.
- Metric: soft-IoU = `sum(p*t)/(sum(p)+sum(t)-sum(p*t))`. 관측된 양성 target만 평가하고, 빈 target이 들어오면 오류를 낸다.
- 집계: 영상 안의 관측 클래스 점수를 먼저 평균한 뒤 patient macro를 계산한다(1명당 1영상). 클래스별 평균은 따로 보고한다.
- 대조군:
  - 위치 prior: train split의 클래스별 관측 target 평균(fine/coarse 각각).
  - image-swap: 같은 split·같은 클래스의 관측 영상에 대한 고정 derangement(`SWAP_SEED=20260924`)다. 항상 다른 patient로 보내고, 전단사이며 결정적이다.
- Bootstrap: patient 단위로 `bootstrap_indices(n, B, seed=20260925)`를 만들고 같은 index를 모든 방법에 적용한다(paired CI).
- 투자 기준(기존 기준 유지, 이번에 측정하지 않음): 3 seed 평균 MLP coarse soft-IoU 차이가 0.03 이상, paired patient bootstrap 95% CI 하한이 0보다 클 것. 위치 prior·image-swap보다 각각 0.03 이상 높고, 최소 두 클래스에서 방향이 같아야 한다.
- 해석 제한:
  - 차이가 없어도 병목을 LLM/decoder로 결론 내리지 않는다(**미확정**).
  - bbox occupancy는 segmentation GT가 아니다. 현재 4클래스로는 미세 결절 전반의 한계를 주장할 수 없다.
  - target은 좌표 canvas 가정(assumed)에 의존한다.

## 5. QES 검증 보완 (참고)

- `qes/preflight.check_subsets`는 저장된 calibration·verification 목록을 `fixed_subsets(requests)`의 재생성 결과와 ID 집합으로 대조한다. 순서는 의미가 없고, 중복은 정규화 전에 거부한다. runner·selector·evaluator가 모두 이 검사를 거친다.
- `evaluate_qes.py`는 시작할 때 이전 평가 산출물을 `invalidated/<run_id>_start/`로 옮기고 상태를 running으로 둔다. 산출물은 staging에 모두 기록한 뒤에만 게시하며, `evaluation_status.json`이 완료 판정의 유일한 근거다. 실패하면 게시 도중의 산출물도 무효화한다.

## 6. 대규모 GPU 필요 후보 (유지)

- 고해상도 vision tower와 pooling/projector 공동 학습으로 병변 공간 정보를 보존하는 의료 VLM 중간학습.
- anatomy·phrase grounding·보고서 결합 대규모 공동학습.
