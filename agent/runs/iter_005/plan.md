# Current Understanding

iter_003과 iter_004에서 중단한 보정·선택 규칙은 다시 시도하지 않는다. 직전 리뷰가 제안한 해부구조→병변 grounding 전이는 유효한 후보지만, legacy의 anatomy 수치는 실제 organ annotation만으로 평가한 결과가 아니며 현재 병변 개발 영상에는 검증된 patient split이 없다. 단순 anatomy supervision의 선행 방법 중복도 크다.

이번 반복의 산출물은 **실제 데이터 연결 결과, 실패 시 재현 가능한 차단 사유, 수정된 평가 검증 코드, 후속 probe 명세**다. GPU 예산은 0 device-min이다. pooling probe·LoRA·bbox 생성 비교는 이번 실행에 포함하지 않는다.

# Hypothesis

- **이번에 검증할 실행 가능성 가설:** 소량의 공개 배포 자료만으로 영상·annotation·subject provenance를 검사하고, 후속 grounding 실험에 사용할 수 있는 집단과 아직 사용할 수 없는 집단을 구분할 수 있다.
- **후속 과학적 가설:** MedGemma 1.5의 pooling 전 feature에는 동일 용량 readout으로 접근 가능한 병변 위치 정보가 pooling 후보다 더 많이 남아 있을 수 있다. 이는 anatomy 전이 학습보다 먼저 검사할 전제이며 아직 사실로 간주하지 않는다.
- **반증 범위:** 데이터 확보 실패는 과학적 가설의 반증이 아니다. probe 차이가 없더라도 모든 decoder나 모든 의료 VLM의 정보 손실을 부정하는 결과로 일반화하지 않는다.

# Proposed Experiment

1. **CPU 데이터 감사.** NIH의 bbox·patient CSV·공식 split 목록을 연결하고, SCR의 영상·수동 anatomy mask archive를 검사한다. 실제 다운로드는 누적 256 MiB, 네트워크 작업 20분 이내로 제한한다. 재시도를 포함한 전송량을 계상하고 파일별 최대 2회 시도한다.
2. **NIH 소량 영상 접근 확인.** 고정 revision의 미러 ZIP에 HTTP Range가 실제로 지원되는지 확인한다. 설치된 라이브러리와 표준 ZIP reader를 이용할 수 있을 때만 필요한 member를 읽는다. Range 미지원·전체 응답·복잡한 호환성 문제가 있으면 해당 경로를 중단하고 전체 archive 다운로드로 전환하지 않는다. 최초 8개 고정 ID로 접근 검증 후, 사전 선택한 최대 160명·1명당 1영상까지 예산 안에서 확보한다.
3. **SCR 대체 경로.** 원저자 `jpg.zip`과 `masks.zip`을 검사해 파일명, 실제 해상도, mask 형식, organ별 대응률을 보고한다. JSRT의 결절 위치 자료가 명시적 배포 경로에서 확보되는 경우에만 연결한다. nodule 중심점이나 직경으로 만든 영역을 수동 bbox·segmentation GT로 부르지 않는다.
4. **CPU 측정 검증.** 합성 geometry fixture로 bbox 좌표 변환, union, fine/coarse occupancy target과 affine pooling 교환법칙을 검증한다. 기존 QES 결과는 별도 출력 경로에서 무결성을 재감사하며 GPU 재실행 없이 검증 가능한 범위만 보고한다.

# Implementation Tasks for Claude

1. **환경과 범위를 고정한다.** `sys.executable`, Python·필요 package 버전, 실제 경로와 네트워크 접근 결과를 기록한다. 안내된 `medgemma` 환경과 다르면 환경 문제를 명시한다. `conda activate`, `pip install`, 모델 로딩은 하지 않는다. git 브랜치와 커밋은 orchestrator에 맡긴다. `legacy/`, `hf_cache/`, 기존 결과 파일은 수정하지 않는다.
2. **직전 리뷰의 세 가지 검증 결함을 먼저 수정한다.** runner의 resume, selector, evaluator가 공통 preflight를 사용하도록 하며, 현재 실제 입력 파일·pixel 변환과 request 본문의 hash를 재계산한다. 완료된 요청도 검사한다. verification은 지정 ID 집합, 누락·중복·충돌, 관련 hash와 수치 기준을 검사하고 실패하면 `complete` 및 투자 판정을 출력하지 못하게 한다. selection의 config와 predictions digest를 현재 유효 prediction에 연결한다. 중복 비교와 digest에는 주평가·민감도·검증에 사용되는 모든 결과 필드를 포함하고 NaN/Inf를 거부한다. 실행 시간 등 비결과 metadata의 처리 규칙은 별도 명시한다.
3. **데이터 준비·검증 entry point를 구현한다.** 예시 위치는 `research/prepare_grounding_data.py`와 `research/grounding_data/`다. source URL, revision, 공개 checksum 유무, 받은 bytes, 실제 파일 hash, decoded pixel hash, annotation hash, 크기, 원래 ID, subject ID 출처를 기록한다. 원본에서 확인하지 못한 동일성은 `unverified`로 둔다. 다운로드 실패와 decode·join 실패를 구분한다.
4. **NIH CSV를 명시적으로 파싱한다.** bbox CSV의 비정상 header와 trailing 빈 열을 검사하고 `[x,y,w,h]`를 `[x0,y0,x1,y1]`로 변환한다. bbox 좌표의 기준 canvas는 배포 문서와 확인한 영상 규격으로 검증하며 `OriginalImage` 크기를 자동으로 사용하지 않는다. metadata의 `Patient ID`를 authoritative grouping으로 사용하고 filename prefix는 교차 확인만 한다. 중복 ID, 클래스 표기 차이, 범위 밖 좌표와 bbox별 official split 소속을 보고한다. annotation이 없는 finding을 음성 GT로 만들지 않는다.
5. **분할을 성능 관측 전에 고정한다.** NIH pilot 목표는 160명, train/validation/test 80/32/48명이다. 고정 seed 20260924, patient grouping, 클래스 분포를 고려한 결정적 절차를 사용하며 각 환자의 영상 선택 규칙도 고정한다. 이는 별도 supervised development split으로 명명하고 공식 benchmark test 성능이라고 부르지 않는다. 양성 bbox가 있는 클래스만 사용하며 최소 2개 클래스가 각각 train 20명, validation 8명, test 12명 이상이어야 후속 병변 probe를 `ready`로 판정한다. 예산·표본 부족 시 숫자를 임의 축소해 `ready`로 바꾸지 않는다. SCR은 subject 관계의 근거가 없으면 case-disjoint만 확인된 것으로 보고한다.
6. **연결과 geometry를 검증한다.** SCR organ별 실제 mask 대응, NIH image→bbox→patient 연결, split 간 subject·파일·pixel 중복을 검사한다. train/validation에서 사전 규칙으로 고른 최대 12개 overlay를 확인한다. test는 자동 schema·범위 검사에만 사용한다. 좌표 오류를 자동 정렬·scale 추정·clipping으로 숨기지 말고 원시 오류와 명시적 변환을 분리한다.
7. **CPU target 도구와 후속 명세를 작성한다.** NIH bbox union과 SCR 수동 mask는 서로 다른 annotation 유형으로 보존한다. 64×64 target은 각 cell에서 annotation이 차지하는 면적 비율이고, 16×16 target은 이를 4×4 평균한 값이다. 합성 rectangle·겹치는 box·작은 box·비정방형 resize에서 좌표와 면적 보존을 검사한다. 같은 고정 affine head에 대해 `P(h(Z))=h(P(Z))`를 float64 허용오차 1e-10으로 검증한다. 별도로 학습한 head나 sigmoid 이후 값까지 이 등식이 성립한다고 주장하지 않는다.
8. **보고서를 남긴다.** `research/results/iter_005/`에 provenance·join·split manifest, 검증 결과, 다운로드 ledger와 readiness JSON을 저장하고 `research/notes/`에 후속 probe 명세와 선행 방법 대비 남은 차이를 기록한다. 전체 패키지의 완료 여부와 `lesion_probe_ready`, `anatomy_only_ready`, `blocked_data`, `blocked_environment`를 분리한다. 실제 파일이 없는 URL 목록만으로 데이터 준비 완료를 선언하지 않는다.

# Evaluation (성공/실패 기준 포함)

**이번 반복의 코드 성공 기준**

- 기존 manifest를 그대로 둔 실제 이미지 변경, request 본문 변경, verification 누락·오류·중복, 오래된 selection, `m`은 같고 `m_fp32head`만 다른 중복 prediction을 실제 진입점 검사에서 모두 거부한다.
- 유효 fixture는 통과하며 불완전 결과에서 `complete`나 연구 투자 판정이 나오지 않는다. 기존 결과에 필요한 검증 정보가 없으면 새 정보를 꾸며 넣지 않고 불완전 상태로 보고한다.
- 실제 확보한 자료의 annotation·영상 연결률, 제외 이유, subject 근거와 split 중복 검사 결과가 재실행 가능한 manifest에 남는다. 선택한 집단의 필수 파일 연결과 hash 검사는 100% 통과해야 `ready`다.
- NIH 160명과 클래스별 최소 수, 검증된 좌표 canvas 및 patient-disjoint split을 모두 충족하면 `lesion_probe_ready`다. SCR 수동 organ annotation만 연결되면 `anatomy_only_ready`이며 병변 전이 평가 가능 상태로 승격하지 않는다.
- 다운로드가 막혀도 검증 코드와 구체적 접근 실패 기록은 유효한 산출물이다. 다만 데이터 준비의 성공이나 pooling 가설의 실패로 기록하지 않는다. GPU 사용은 0이어야 한다.

**후속 probe 명세 — 이번에는 실행하지 않음**

- `Z`와 `U(P(Z))`를 동일 64×64 grid에서 비교한다. `P`는 실제 모델의 pooling, `U`는 nearest upsampling이며 RMSNorm·projection 효과는 섞지 않는다.
- 동일 pointwise linear head와 동일 1-hidden-layer MLP를 별개 비교군으로 둔다. 각 paired 조건은 초기화 seed, label, loss, 영상, batch 순서와 update 수를 맞춘다. 위치 prior는 train annotation만으로 만들고 image-swap은 다른 patient의 동일 클래스 feature로 고정한다.
- fine-grid 출력과 평균 logits에 sigmoid를 적용한 coarse-grid 출력을 각각 해당 occupancy target에 평가한다. 주지표는 patient macro soft-IoU이며 fine/coarse를 분리한다. NIH에서는 bbox occupancy 일치도이지 병변 segmentation 정확도가 아니다. 클래스별 결과와 train에서 고정한 작은 bbox 기준의 하위집단도 보고한다.
- 후속 추가 투자 기준은 MLP의 coarse soft-IoU 차이 `Z−U(P(Z)) ≥ 0.03`, patient bootstrap 95% CI 하한 > 0, 그리고 `Z`가 위치 prior·image-swap보다 각각 0.03 이상 높은 것으로 사전 고정한다. 3개 seed의 평균으로 평가하고 CI는 patient 단위로 계산한다. 최소 2개 클래스의 효과 방향도 확인한다. 수치는 논문급 효과 보장이 아닌 pilot 투자 기준이다.
- fine-grid에서만 개선되면 subcell 위치 정보의 이득으로 해석한다. CI가 실질적 개선과 무효를 모두 포함하면 불확실이며, 검증 실패·표본 부족과 과학적 음성 결과를 분리한다.
- 후속 GPU 상한은 총 45 device-min이다. 실행 직전 `nvidia-smi`로 여유를 확인하고, train 영상의 짧은 실측으로 비용을 추정한다. 정해진 집단·비교군이 예산에 들어가지 않으면 평가 표본을 사후 축소하지 않고 별도 계획으로 넘긴다.

# Risks / Checks

- bbox supervision은 병변 경계 mask가 아니며, SCR·CheXmask·NIH 간 수치를 직접 비교해 anatomy–lesion 능력 격차라고 주장할 수 없다. CheXmask는 도입하더라도 pseudo-label로 분리한다.
- 공개 미러의 읽기 가능성은 원본 동일성 확인과 다르다. HTTP Range 미지원 시 대용량 전체 다운로드로 전환하지 않는다. 네트워크 제한은 환경 차단 사유로 기록한다.
- MedGemma 사전학습 데이터와의 중복 가능성은 patient-disjoint probe split만으로 해결되지 않는다. 후속 결과는 probe 학습 집단에 대한 독립 평가이며 완전한 사전학습 미노출 증거가 아니다.
- feature probe의 개선은 제한된 readout의 접근성 차이다. LLM의 인과적 병목, 완결된 진단 답변 개선, 임상적 유용성 또는 새로운 방법론의 contribution으로 확대 해석하지 않는다.
- 데이터 확보가 끝나도 anatomy transfer를 자동 시작하지 않는다. 표현 분석 이후 동일 병변 supervision·총 update 수의 직접 학습, anatomy 보조 학습, 위치 prior를 비교할 근거가 생겼는지 판단한다.

## 대규모 GPU 필요 후보

- 고해상도 vision tower·pooling/projector를 공동 학습하며 미세 병변 정보를 보존하는 의료 VLM 사전학습 또는 중간학습: 충분한 병변 supervision과 다기관 데이터가 필요하다.
- AnatomiX/CURE 규모의 anatomy·phrase grounding·보고서 공동학습 재현: 소규모 probe로는 추가 데이터량과 표현 개선 효과를 분리하기 어려워 더 큰 학습 예산이 필요하다.
- 두 후보는 장기 대안으로 기록하며 이번 CPU 구현의 실행 범위에는 포함하지 않는다.

# 계획의 근거 (GPT 조사 노트)

### 남은 질문에 대한 답

1. **NIH의 metadata 경로는 확인했지만 소량 영상 확보는 아직 검증하지 못했다.** [bbox CSV 미러](https://huggingface.co/datasets/alkzar90/NIH-Chest-X-ray-dataset/blob/main/data/BBox_List_2017.csv)의 실제 header는 `Image Index,Finding Label,Bbox [x,y,w,h],,,`이며, 첫 annotation은 `00013118_008.png`에 연결된다. 단순히 정상적인 6열 header라고 가정하면 parser 오류가 생길 수 있다. patient metadata 파일 경로도 존재하지만 이번 도구에서는 원문 전체 읽기에 실패했다. [영상 배포 목록](https://huggingface.co/datasets/alkzar90/NIH-Chest-X-ray-dataset/tree/main/data/images)은 개별 PNG가 아니라 12개 ZIP이며, 첫 ZIP만 2.01 GB, 전체는 45.1 GB다. HTTP Range로 필요한 ZIP member만 읽는 경로는 구현 시 제한된 용량으로 확인할 후보이지, 확인된 다운로드 수단이 아니다. 미러의 출처 설명과 실제 원본 동일성 검증도 구분해야 한다.

2. **SCR의 실제 파일명은 확인했지만 해상도·병변 annotation 연결은 미확인이다.** [원저자 archive preview](https://zenodo.org/records/7056076/preview/jpg.zip?include_deleted=0)에는 `jpg/JPCLN001.jpg`부터 `JPCLN154.jpg`, `JPCNN001.jpg` 등의 파일명이 보인다. 따라서 JSRT case ID와의 연결 후보는 구체화됐다. 그러나 preview는 영상 크기를 제공하지 않으며 mask preview 읽기도 실패했다. 파일 크기로 해상도를 추정하거나 파일명만으로 patient 독립성을 확정하지 않는다. [SCR 원저자 배포](https://zenodo.org/records/7056076)의 `jpg.zip` 7.8 MB와 `masks.zip` 4.0 MB를 구현 단계에서 직접 검사하는 것이 가장 작은 다음 작업이다. 결절 위치 metadata를 확보하지 못하면 anatomy-only 자료로 분류한다.

3. **이번 반복은 GPU 없이 데이터 준비·측정 검증으로 제한한다.** 실제로 연결된 병변 영상·patient ID가 없으므로 45 device-min 추론 계획을 지금 실행 대상으로 확정하면 평가 집단을 실행 중 바꾸게 된다. 후속 pooling probe의 비교군·target·투자 기준은 문서로 고정하되, 이번에는 모델 feature 추출이나 학습을 실행하지 않는다.

### 코드·환경 확인

- `agent/GOAL.md`, `agent/INDEX.md`, `agent/runs/iter_004/review.md`를 읽었다. 기존 두 접근법은 abandon 상태다.
- `research/qes/store.py`는 prediction 중복 검사에서 `m`만 비교한다. `research/evaluate_qes.py`는 verification 성공과 selection의 prediction digest 연결을 완료 조건으로 강제하지 않는다. 기존 검증 코드 재사용 전에 실제 입력 재해시를 포함한 세 가지 결함을 수정해야 한다.
- 이번 셸의 `python` package metadata 조회에서는 `torch`와 `transformers`가 발견되지 않았다. 이는 현재 셸이 안내된 연구 환경과 다를 가능성을 뜻하며, MedGemma 연구 환경 자체에 패키지가 없다는 증거는 아니다. 실행 interpreter와 package 위치 확인을 구현의 첫 단계로 둔다. `conda activate`나 패키지 설치로 임의 수정하지 않는다.
- 파일을 저장하지 않는 외부 metadata 읽기를 시도했지만 셸에서는 DNS 오류가 발생했다. 웹 도구의 열람 성공과 Claude 실행 환경의 다운로드 가능성은 별도로 검증해야 한다.

### 연구 방향 판단

앞선 라운드에서 확인한 AnatomiX·CURE·F-LMM·EasyLens 때문에 anatomy supervision, frozen head, feature 증폭만으로는 차별성이 부족하다. 먼저 실제 annotation과 독립 분할을 확보하고, 동일 readout에서 pooling 전후의 접근 가능한 공간 정보 차이를 검증할 기반을 만든다. `P(h(Z))=h(P(Z))`인 affine control은 구현 검증이며, 그 자체가 정보 손실 실험은 아니다. 이번 작업은 새로운 방법론의 성공을 주장하는 단계가 아니다.

이전 사고 라운드 노트: agent/runs/iter_005/think/
