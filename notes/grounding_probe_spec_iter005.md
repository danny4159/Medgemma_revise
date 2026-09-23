# iter_005 후속 pooling probe 명세와 데이터 준비 결과

이 노트는 `agent/runs/iter_005/plan.md`의 후속 probe 명세를 고정하고, 이번 CPU 데이터 준비에서 확인한 사실을 연결한다.
이번 반복에서는 probe를 실행하지 않았다(GPU 0 device-min).

## 1. 이번에 확보·검증한 데이터 (실측)

결과 파일: `results/iter_005/readiness.json`, `nih_audit.json`, `nih_manifest.json`, `scr_audit.json`, `provenance.json`, `download_ledger.json`.

- **NIH ChestX-ray14 (HF 미러 `alkzar90/NIH-Chest-X-ray-dataset`, revision `36778e3b…`)**
  - bbox CSV: 984 box / 880 영상 / 726명. header는 `Image Index,Finding Label,Bbox [x,y,w,h],,,`(9열, trailing 3열 빈 값).
    데이터 행은 모두 6열이다. 완전 중복 box는 0개다. bbox의 8개 클래스 가운데 `Infiltrate`만 Data_Entry 표기 `Infiltration`과 다르다.
    대응을 적용하면 984개 box 전부 해당 영상의 Data_Entry finding 목록에 포함된다.
  - bbox 영상 880장은 전부 공식 `test_list.txt` 소속이다. 따라서 우리 split은 공식 test 영상에서 새로 나눈 **supervised development split**이며, 공식 benchmark test 성능이 아니다.
  - patient ID는 Data_Entry의 `Patient ID`를 사용했다. filename prefix와의 불일치는 0건이다.
  - 좌표 canvas: 받은 영상 164장이 모두 1024×1024다(`L` 163, `RGBA` 1). 전체 984 box의 좌표 범위는 x0,y0 ≥ 5.4, x1 ≤ 1012.1, y1 ≤ 1022.0이며 1024 canvas 밖 좌표는 0건이다.
    Data_Entry `OriginalImage` 폭(2500, 3056 등)은 사용하지 않았다. 미러 README의 1024 언급은 로딩 예시 한 줄뿐이라 근거로 약하다.
  - 영상은 HTTP Range(206)로 12개 ZIP의 central directory와 필요한 member만 읽었다. 표준 `zipfile`로 CRC-32를 검사했다.
    ZIP 전체 sha256은 부분 읽기라서 검증하지 못했다(`unverified`). NIH 원배포와의 동일성도 `unverified`다.
  - 개발 split(seed 20260924): 1명당 bbox 영상 1장(사전순 첫 영상)을 쓴다. stratum은 bbox patient 수 상위 4개 클래스(Atelectasis, Effusion, Cardiomegaly, Pneumonia)이며, stratum마다 20/8/12명을 배정해 train/validation/test = 80/32/48명이다.
    클래스별 patient 수(train/val/test): Atelectasis 22/10/13, Effusion 20/9/13, Cardiomegaly 20/8/12, Pneumonia 20/8/12, Infiltrate 4/3/6, Mass 2/0/2, Pneumothorax 1/0/1.
    **최소 기준을 충족한 클래스는 4개다.** Mass·Nodule·Pneumothorax·Infiltrate는 이 split에서 클래스별 평가가 불가능하다.
  - split 간 patient·file hash·pixel hash 중복은 0이다. 선택한 160장의 join·hash는 100% 통과했다. → `lesion_probe_ready = true`.
    (**iter_006 정정**: 좌표 canvas를 직접 명시한 문서 근거가 없어 엄격한 `lesion_probe_ready = false`다. 무결성 검사는 통과했다. `grounding_probe_spec_iter006.md` 참조)
- **SCR (Zenodo 7056076, Bram van Ginneken, CC-BY-4.0)**
  - `jpg.zip`: 247 case(JPCLN 154, JPCNN 93)이며, 모두 **256×256 RGB JPEG**다.
    **영상에 annotation 윤곽선(폐·심장·쇄골)이 그려져 있다.** 247/247 case에서 자동 검사 결과 mask 경계 hit rate 중앙값은 0.972였고, 12px 이동 기준선은 0.072였다. 육안으로도 확인했다.
  - `masks.zip`: case당 **단일** 1024×1024 binary TIFF다. 구조물 정의는 배포 문서에 없다. 무게중심 x가 모든 case에서 0.22–0.35이므로 영상 왼쪽 폐(환자 우폐)로 보이지만 문서로 확인하지는 못했다.
  - 결론: 윤곽선이 그려진 영상을 모델 입력으로 쓰면 정답이 노출된다. 따라서 **`anatomy_only_ready = false`**다.
    원시 JSRT 영상과 결절 위치는 JSRT 등록 양식을 제출한 뒤 이메일 비밀번호로 받는 방식이라 명시적 공개 경로가 아니다(`blocked_data`).
    `points.zip`/`landmarks.zip`(organ 윤곽점 추정)은 이번에 받지 않았다.

## 2. 후속 probe 명세 (실행 전 고정, 계획에서 옮김)

- 입력: 위 NIH 개발 split 160명(1명 1영상). target은 bbox union의 64×64 occupancy(각 cell의 면적 비율)이고, 16×16 target은 그 4×4 평균이다(`grounding_data/targets.py`, `results/iter_005/nih_targets_fine64.npz`).
  이는 bbox 일치도 target이지 병변 segmentation GT가 아니다.
- 비교: `Z`(vision tower 출력 64×64×1152, pooling 전) 대 `U(P(Z))`(실제 projector의 `AvgPool2d(4)` 후 nearest upsampling)를 같은 64×64 grid에서 비교한다. RMSNorm·projection은 섞지 않는다.
  실제 projector 설정(patches 64, tokens 16, kernel 4)은 config로 확인했다(`test_grounding_targets.py`).
- readout: 동일 pointwise linear head와 동일 1-hidden-layer MLP를 별개 비교군으로 둔다. paired 조건마다 초기화 seed, label, loss, 영상, batch 순서, update 수를 맞춘다.
  같은 고정 affine head에서는 `P(h(Z)) = h(P(Z))`가 성립하며, float64 오차는 8.9e-16이었다. 따라서 **같은 가중치**라면 두 경로의 coarse logits가 같다.
  두 경로에서 따로 학습한 head나 sigmoid 이후 값에는 이 등식을 주장하지 않는다. 합성 데이터에서 sigmoid 이후 차이는 0.07이었다.
  **정보 손실 검사의 주비교는 MLP다.** linear는 구현 대조군으로 둔다.
- 대조군: train annotation만으로 만든 위치 prior, 다른 patient의 같은 클래스 feature로 고정한 image-swap.
- 평가: fine 출력과 평균 logits에 sigmoid를 적용한 coarse 출력을 각각 해당 target에 대해 평가한다. 주지표는 patient macro soft-IoU이며 fine/coarse를 분리한다.
  클래스별 결과(최소 기준 충족 4개 클래스)와 train에서 고정한 작은 bbox 기준 하위집단을 함께 보고한다.
- 투자 기준(사전 고정): MLP coarse soft-IoU 차이 `Z − U(P(Z)) ≥ 0.03`, patient bootstrap 95% CI 하한 > 0, `Z`가 위치 prior·image-swap보다 각각 0.03 이상 높을 것, 3 seed 평균, 최소 2개 클래스에서 같은 방향.
  fine에서만 개선되면 subcell 위치 정보 이득으로 해석한다.
- GPU 상한: 총 45 device-min. **추정치**(측정 아님): SigLIP vision tower forward 160장 + 특징 저장은 수 분 이내, probe 학습은 CPU/GPU 모두 소규모다. 실행 직전 train 영상으로 실측한 뒤 확정한다.
- 해석 제한: 제한된 readout에서의 접근성 차이다. LLM 인과 병목, 진단 답변 개선, 새 방법론 contribution으로 확대하지 않는다. MedGemma 사전학습 노출 여부는 이 split으로 해결되지 않는다.

## 3. 선행 방법 대비 남은 차이 (GPT 조사 노트 기반, 이번에 원문 재확인 안 함)

- AnatomiX·CURE: anatomy·phrase grounding 공동학습이다. 단순 anatomy supervision은 차별성이 없다.
- F-LMM·EasyLens: frozen VLM feature/attention 기반 grounding head다. frozen head나 feature 증폭만으로는 새롭지 않다.
- 남은 검증 가능 질문: MedGemma 1.5의 **pooling(64→16) 단계가 병변 위치 정보를 동일 용량 비선형 readout 기준으로 잃는가**. 이 질문이 참이어야 pooling 보존형 adapter 같은 방법론의 동기가 선다. 차이가 없더라도 병목 위치는 **미확정**이다
  (readout 용량·target 품질·표본 수 등 다른 설명이 남으며, LLM/decoder 병목으로 결론 내리지 않는다; iter_006 교정).
- anatomy→lesion 전이는 SCR 공개본이 윤곽선이 그려진 영상이라 현재 불가능하다. 원시 JSRT 확보, 또는 다른 수동 anatomy 자료가 필요하다.

## 4. 대규모 GPU 필요 후보 (계획에서 옮김)

- 고해상도 vision tower·pooling/projector를 공동 학습해 미세 병변 정보를 보존하는 의료 VLM 사전학습 또는 중간학습.
- AnatomiX/CURE 규모의 anatomy·phrase grounding·보고서 공동학습 재현.
