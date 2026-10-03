# 요약

- **이번에 할 일:** 기존 MSD Task01 D6/E48에 HD-GLIO segmentation+OR를 적용하고 U8와 정확도·전체 pipeline 비용을 비교한다.
- **필요한 이유:** MRI 영상 신호와 잔여 오류는 확인됐지만 전문 대안으로 해결되는지는 모른다.
- **확인할 기준:** BA 5 pp 차이, sensitivity 보존, 실제 전체 비용, 오류가 분포한 case와 입력·정답 연결이다.
- **주의·다음:** HD-GLIO는 네 sequence 전체 volume을 사용한다. 동일 입력 우위나 신규 기여를 주장하지 않고 현재 조건의 대안 채택 또는 후속 투자 보류를 결정한다.

# Current Understanding

최종 GOAL과 MRI 우선 전략을 유지한다. OCT 보류와 과거 MRI reference 결과를 다시 판정하지 않는다. iter_056/057의 D6/E48·구간 정의·정답·U8 출력은 유지하며 이번 결과는 `results/iter_058/`에 저장한다.

E48·288구간에서 U8 BA는 0.768639이고 오류가 30개 case에 남는다. 위치 표준화 결과는 위치 index만으로 모든 신호를 설명하는 해석을 제한한다. 병변 인과성, 독립 환자 일반화, 전문 모델 대비 효용은 미확인이다. 복잡한 표집 투자는 계속 보류한다.

# Strategy Check / 연구 방향 판단

**관찰:** 기본 영상 신호와 잔여 오류가 있으나 U8와 DENSE의 차이는 작다. 위치 분석은 이번에 반복하지 않는다.

**남은 설명:** 전문 인식으로 오류가 줄어들 수 있고, 네 sequence·전체 volume이라는 추가 정보가 중요할 수도 있다. annotation 범위와 전문 모델의 출력 의미 차이도 경쟁 설명이다.

**최소 비교:** 공개 HD-GLIO checkpoint 한 개를 기존 case에 적용한다. FLAIR-only 입력을 지원하지 않는 모델에 영영상이나 복제 채널을 넣지 않는다.

**선택 비교:** 직접 SFT는 전문 대안 이후의 추가 가치가 불명확하다. 동일 FLAIR 전문 baseline 학습은 더 공정하지만 새 학습·수렴·분할 비용이 든다. 새 MRI 자료 탐색은 지금까지 확인한 신호를 활용하지 못한다. 따라서 기존 전문 모델의 실용 비교를 우선한다.

**결정 변화:** 추가 정보가 있는 단순 대안이 충분하면 현재 다중 sequence 이용 가능 조건의 VLM 구간 적응 투자를 보류한다. 대안이 약하면 원인을 한정하고, 그것만으로 새 loss를 발주하지 않는다. FLAIR-only가 중요한 독립 사용 조건임을 구체화할 때만 동일 정보 비교를 다음 후보로 삼는다.

track은 `mri-volume-evidence-use`를 유지한다. iter_056의 주비용은 자료 준비·생성이고 iter_057은 분석 구현·검증이었다. 이번에는 전문 환경 확보와 GPU 추론이 새 비용이다. 로그 없이 누적 비용 비율을 만들지 않는다.

# Hypothesis

공식 전문 segmentation을 구간 OR로 변환하면 U8의 잔여 FP/FN을 줄일 수 있다. 이는 기존 방법의 충분성을 확인하는 진단이며 새 방법 효과를 시험하지 않는다.

HD-GLIO의 개선은 전문 supervision·모델 구조·네 sequence·전체 volume의 결합 효과다. 이번 설계는 그 요인을 분해하지 않는다. 전체 volume의 예측을 구간으로 잘라 평가하므로 구간 밖 context 접근도 명시한다.

# Limitation Evidence / Correct Usage Checks

`limitation_ids=[]`다. iter_056/057은 유효하지만 해당 MRI 구간 한계를 등록한 limitation_update는 없다. 기존 SPIDER id를 method gate에 전용하지 않으며 이번은 diagnostic이다.

공식 HD-GLIO 소스·가중치·license·다운로드 출처와 SHA256를 저장한다. 문서상 학습 출처와 실제 checkpoint의 metadata를 대조한다. 환자 명단이 없으면 비중복을 확정하지 않는다. 알려진 평가 case 학습 중복이 발견되면 해당 결과를 학습 노출이 있는 기술 참고로 분리하고 대안 충분성 판정에 사용하지 않는다. 불명확성은 명시하되 탐색 실행 자체의 보편적 중단 조건으로 삼지 않는다.

D6에서 네 sequence의 modality mapping, 공통 affine·shape·spacing·비뇌 영역과 공간 정렬을 확인한다. source schema를 기준으로 HD-GLIO의 `[T1,T1c,T2,FLAIR]` 순서에 대응시킨다. 원본 label을 inference 입력이나 전처리 선택에 사용하지 않는다.

HD-GLIO의 두 foreground 영역과 MSD 비배경 합집합의 의미를 공식 문서·checkpoint metadata에서 표로 정리한다. necrotic/non-enhancing core 포함 여부를 특히 확인한다. 합집합 의미가 완전히 같지 않으면 그대로 기록하고, 해당 영역 관련 FN을 별도 기술한다. 의미 차이가 전체 구간 정답 비교를 해석할 수 없게 만들면 대안 충분성 판정을 보류한다. D의 정확도나 oracle 100% 정답을 기술 gate로 요구하지 않는다.

# Contribution Path / Baselines / Reuse

가장 가까운 방법은 nnU-Net 기반 전문 segmentation+OR다. 이번 실험은 이를 새로운 방법으로 부르지 않는다. baseline이 충분한 과제에서 VLM loss를 추가하는 투자를 피하거나, 실제 남는 문제를 식별하는 것이 의사결정 가치다.

주 비교는 HD-GLIO 대 기존 U8이며 DENSE·TEXT·D 위치 규칙은 참고 수치다. HD-GLIO는 추가 sequence·전체 volume·전문 supervision을 사용한다. U8는 FLAIR 구간의 8장과 기존 prompt를 사용한다. annotation budget·입력·학습량은 같지 않다. O8은 GT 기반 진단 oracle이므로 실용 대안의 성능·비용 기준에서 제외한다.

현재 branch와 HEAD `144227e1c8a0faf1a8f88df126e8a49803030db8`를 유지한다. `reuse_assets=[]`이며 다른 branch로 전환하지 않는다.

- `msd56_data.py`: 현재 native RAS FLAIR·구간·정답 함수는 iter_056 승인 범위에서 재사용한다. 네 sequence 추출과 전문 모델 좌표 변환은 새 검증 대상이다.
- `msd57_analysis.py`, `test_msd57.py`: 원시 문자열 해석·paired 통계와 회귀 fixture를 재사용하되 protocol 내부 requests/code 연결, GT 중복 key, case/split 대응과 cond_map 완전성 검사를 보완한다.
- `msd56_run.py`: U8 timing에 필요한 로딩·입력·생성 경로만 재사용한다. 필수 검사 근거 연결, 실패 attempt 처리와 실제 GPU admission을 먼저 수정한다. 과거 protocol은 보존된 당시 코드로 검증하고 새 코드 hash로 덮어쓰지 않는다.
- `msd56_sanity.py`: 재사용하면 기록만 하는 실패 조건을 실제 실패로 연결하고, 첫 영상 tensor 비교를 수행하지 않고 true로 쓰는 경로를 제거한다.

미사용 Qwen와 breakdown 경로는 정비하지 않는다. 기존 고정 결과의 유효성을 코드 전체 재사용 승인으로 확대하지 않는다.

# Proposed Experiment

## 1. 자료·환경과 동작 확인

기존 archive와 D/E 파일을 재사용한다. 새 대량 다운로드나 남은 training/test의 출력은 없다. 전용 환경은 `results/environments/hdglio58/`, 새 모델 cache와 결과는 git 제외 경로에 둔다. 기존 medgemma와 hf_cache는 변경하지 않는다.

공식 HD-GLIO version 2.0 코드의 실제 commit을 고정하고 nnUNet v1 의존성과 CUDA/PyTorch 호환성을 확인한다. 설치 전 디스크와 Python을 확인하고 설치 후 import·GPU·D 실제 출력까지 검사한다. 공식 weights 경로만 별도 cache로 바꾸는 경우 patch를 보존한다. 모델 구조·추론 설정은 바꾸지 않는다. 공식 단일 case와 folder 경로의 fold 0, checkpoint, 전처리·후처리·TTA 설정을 기록해 동일하게 유지한다.

D6에서 전처리 적합성과 출력의 native grid 복원을 확인한다. 기존 자료가 이미 정렬·brain extraction 조건을 만족하면 불필요한 재등록을 하지 않는다. 필요 변환은 영상만으로 정하고 invertible axis 변환과 nearest-neighbor mask 복원을 검사한다. 원본 구간 경계는 변환 후 새로 만들지 않는다.

동일 D case 한 개에서 공식 CLI와 wrapper 출력의 label map·affine 일치를 확인한다. 두 case의 실제 multi-sequence 영상과 예측 overlay를 열어 공간 대응을 확인한다. 나쁜 예측을 기술 실패로 바꾸지 않는다.

## 2. 고정 전문 대안

전체 volume에 공식 HD-GLIO를 한 번 적용한다. 최종 label map의 모든 foreground를 합집합으로 만들고 원본 RAS grid에서 기존 각 구간에 foreground voxel이 하나라도 있으면 PRESENT로 변환한다. 연결성분 제거·voxel 수 threshold·GT 기반 crop은 추가하지 않는다. 공식 후처리가 있으면 그대로 유지하고 기록한다.

GT는 기존 비배경 mask 합집합의 구간 OR다. GT 규칙·여섯 구간·case 목록은 변경하지 않는다. 작은 병변이나 어려운 위치도 제외하지 않는다.

실패한 예측 파일은 ABSENT로 대체하지 않는다. 기술 실패는 복구하거나 미완료로 보고하고, 정상적으로 얻은 잘못된 예측은 오답으로 계산한다.

## 3. 가능성 탐색과 고정 본실행

D6의 기술 검사가 통과하면 성능 gate 없이 E48의 48 volume·288구간을 완료한다. D는 검사와 timing용이며 E 정확도에 합치지 않는다. 중간 E 점수로 threshold·전처리·모델·표본을 바꾸지 않는다.

E에서는 전체 BA·sensitivity·specificity, FP/FN, case별 오류, 위치별 결과와 U8와의 오류 겹침을 보고한다. 기존 위치 표준화 지표는 보조 지표로 유지한다. 전문 segmentation의 union Dice는 출력 의미·공간 대응 해석을 돕는 보조 수치이며 구간 BA와 직접 비교하지 않는다.

## 4. 비용과 GPU 배치

전체 비용의 단위는 원본 NIfTI가 있는 상태에서 한 case의 여섯 구간 답변을 저장하기까지다. HD-GLIO는 channel 분리·공식 전처리·segmentation·복원·OR를 포함한다. U8는 FLAIR 읽기·정규화·렌더링·processor·여섯 요청 생성·저장을 포함한다. GPU 비동기 구간은 synchronize해서 측정한다.

D6를 고정 순서의 두 case씩 세 block으로 나눈다. 각 block을 U8→HD, HD→U8 두 순서로 실행한다. 비교할 때 두 pipeline을 서로 다른 GPU 성능에 고정하지 말고 같은 허용 GPU에서 순차 측정하고 block 사이 장치를 균형 배정한다. 반대 GPU의 작업과 CPU/I/O 경합도 기록한다. 모델이 로드된 steady-state와 모델 loading을 포함한 batch 총비용을 각각 보고한다. 다운로드·설치 비용은 일회성 준비 비용으로 별도 표시한다.

D6 비용은 탐색적이다. 6 case의 paired 비용 비율과 범위를 보고하며 작은 timing 표본의 CI를 강한 비용 확증으로 표현하지 않는다. 기존 generation 시간 비율 0.371을 전체 비용에 전용하지 않는다.

시작 직전 nvidia-smi로 실제 여유와 논리/물리 GPU 대응을 확인한다. 두 GPU에 독립 case shard를 배정한다. HD-GLIO는 D6에서 GPU당 1 worker와 2 worker 중 가능한 구성을 비교한다. 실제 peak 합과 다른 프로세스 점유에 worker당 2GiB 여유를 더해 admission한다. 공식 4GB 요구량이나 과거 MedGemma 참고값만으로 배치하지 않는다.

U8 timing의 동시성은 양쪽 비용 비교를 해석할 수 있게 고정한다. U8 생산 처리량 확대가 필요하면 D에서 batch2 가능성을 우선 검사한다. VRAM·CPU/RAM/I/O 경합·오류·출력 정합성과 처리량으로 구성을 선택하며 E 정확도를 쓰지 않는다.

## 5. 규모 확대와 독립 확인

이번 반복은 전문 checkpoint 한 개의 E48 탐색까지다. 학습·다중 seed·reserve 사용은 없다. 기술 동작만으로 전체 training 또는 다른 모델을 실행하지 않는다.

후속 동일 FLAIR 학습이나 직접 SFT는 별도 계획에서 자료 분할·수렴·강한 대조와 method gate를 검토한다. E48은 이미 반복 사용한 개발 자료이며 독립 확인으로 부르지 않는다.

# Implementation Tasks for Claude

1. 관련 원본 리뷰와 현재 파일을 확인하고 기존 결과의 hash를 잠근다. 이번 소스 변경 전후의 출처를 남기며 branch/commit은 orchestrator에 맡긴다.
2. HD-GLIO 공식 source·checkpoint·license·학습 출처와 정답 의미를 확인하고 전용 환경을 구성한다. 설치 실패 시 오류와 호환 구성 시도를 기록한다.
3. D6 multi-sequence 입력, 좌표 복원, 공식 CLI 대조를 검증한다. 실제 영상을 보지 않고 시각 검사를 통과했다고 쓰지 않는다.
4. 사용 경로에 한해 provenance·GT 대응·필수 gate·실패 attempt·메모리 admission 결함을 수정한다. GT 중복/누락·case 교환·요청 변조·실패 worker fixture를 추가한다.
5. 공식 segmentation adapter와 native-grid OR 평가를 구현한다. 예측 cache는 case·입력·모델·config digest에 연결하고 원자적 완료 표시를 사용한다. 중단 후 재개에서 중복·누락과 부분 파일 재사용 거부를 검사한다.
6. D 처리량·paired timing과 E48을 수행한다. 원시 segmentation과 비용 event를 보존하고 E 수치를 별도 계산으로 재현한다.
7. 정확도, 입력 차이, 학습 노출 불확실성, 전체 비용과 다음 투자 결정을 구분해 보고한다.

# Evaluation (성공/실패 기준 포함)

주지표는 동일 E48의 구간 BA와 HD−U8 차이다. case-cluster paired bootstrap 10,000회, seed58의 95% CI를 사용한다. sensitivity 차이와 specificity, FP/FN도 함께 보고한다. 위치 표준화 CI의 정의되지 않은 replicate 수를 공개한다. 구간을 독립 환자로 취급하지 않는다.

**전문 대안 충분성의 탐색 양성:** HD−U8 BA≥0.05, paired CI 하한>0, sensitivity 차이≥−0.05이며 D6 전체 pipeline 비용 비율 HD/U8≤1.0을 함께 만족한다. 비용 비율은 측정 범위·loading 조건을 명시하며 방향이 block마다 크게 뒤집히면 비용은 불확정으로 둔다. 이는 임상 성능 또는 독립 일반화의 확증 기준이 아니다.

양성이면 네 sequence가 사용 가능한 현재 개발 과제에서 전문 대안을 보존하고 VLM 구간 적응의 추가 투자를 보류한다. FLAIR-only와 언어 조건 과제까지 기각하지 않는다.

**음성:** BA 이득이 5 pp 미만이거나 sensitivity 손실·비용 증가가 있으면 복합 기준 미달 항목을 그대로 보고한다. 유효한 정확도 이득이 있더라도 비용 기준 미달과 연구 가치 부족을 같은 뜻으로 쓰지 않는다. 전문 모델 실패만으로 VLM 적응을 승인하지 않는다.

**잔여 문제의 다음 행동:** 양쪽 공통 오류가 5개 이상 case에 남으면 병변 부담·위치·annotation 의미·관측 정보 차이를 고정된 기술 분석으로 정리한다. 이것만으로 방법 필요성을 선언하지 않는다. 리뷰가 구체적인 변경 요인·강한 단순 대조·학습 자료를 제시할 수 있을 때만 최소 방법 시험을 권고한다.

**불확정:** CI가 넓거나 label 의미·학습 노출·timing 변동으로 선택을 못 하면 불확정 범위를 명시한다. 추가 표본 또는 비용 측정이 정확히 어느 결정을 바꿀지와 필요한 정밀도를 제시할 때만 별도 한정 보완을 권고한다. 이번에는 E를 늘리거나 유리한 component threshold를 탐색하지 않는다.

**실행 실패:** 잘못된 sequence, 좌표 복원 실패, GT 연결 오류, 공식 checkpoint 미확보 또는 미해결 worker 실패로 해석할 수 없으면 해당 범위의 실행 실패다. 유효한 모델 오답과 구분한다.

# Risks / Checks

- HD-GLIO의 문서상 학습 출처는 확인했지만 환자 단위 중복 부재는 확정하지 못했다. MedGemma 사전학습 노출도 미확인이다.
- 전문 모델은 네 sequence·전체 volume·전문 annotation을 사용한다. 성능 격차를 동일 정보 처리 능력이나 language reasoning의 차이로 해석하지 않는다.
- MSD mask 부재는 해당 annotation 부재이며 정상 환자나 임상적으로 정상이라는 뜻이 아니다. HD-GLIO와 MSD의 core/FLAIR 영역 의미 차이를 숨기지 않는다.
- 과거 D protocol은 당시 보존 코드와 검증하고 과거 결과·plan·review를 수정하지 않는다. 새 분석은 새 경로에 둔다.
- 예상 시간은 D의 실측 case/s와 U8 전체 pipeline 시간으로 `남은 case/처리량 + loading + 전처리 + 검증`을 계산해 본실행 전에 남긴다. 현재 전문 경로 실측이 없어 정확한 시간 수치를 제시하지 않는다. 임의 시간 상한은 두지 않는다.
- 모델당 peak·전체 GPU 점유·CPU/RAM/I/O를 측정한다. OOM이면 동시성·배치를 낮추되 입력 sequence·slice·해상도를 조용히 바꾸지 않는다. 다른 사용자 프로세스는 건드리지 않는다.
- 재개 시 완료 case의 입력·checkpoint·설정 hash와 출력 완전성을 확인한다. 실패 attempt의 시간도 보존하며 기존 파일 존재만으로 성공 처리하지 않는다.

## 대규모 GPU 필요 후보

3D multi-sequence encoder와 언어모델의 공동 적응, 대규모 MRI instruction tuning은 장기 후보로 남긴다. 현재 비교가 이 방법의 필요성이나 신규성을 증명하지 않으며 이번 반복에서는 실행하지 않는다.

# 계획의 근거 (GPT 조사 노트)

## 확인한 근거

- `agent/GOAL.md`, `agent/GPT_USAGE_POLICY.md`, `agent/INDEX.md`, iter_056 plan·보고서·review.json, iter_057 review.md·review.json, `CODE_ASSETS.md`의 056/057 항목과 `LIMITATIONS.md`를 확인했다. 현재 MRI 구간 한계에 등록된 id는 없으며, SPIDER reference 한계를 전용하지 않는다.
- iter_057은 유효한 분석이다. E48에서 U8 BA=0.768639, 위치 표준화 BA=0.766460이고 오류가 30개 case에 남는다. DENSE의 위치 표준화 BA=0.716711이며 위치 규칙 대비 전체 BA 차이는 불확정이다. 전문 대안 비교가 다음 결정이다.
- research HEAD는 `144227e1c8a0faf1a8f88df126e8a49803030db8`이며 status와 diff는 비어 있다. `msd56_data.py`, `msd56_run.py`, `msd57_analysis.py`, `test_msd57.py` 등이 현재 브랜치에 있다. 동일 접근법 브랜치를 유지하며 선별 반입은 필요 없다.
- HD-GLIO 공식 저장소는 Heidelberg 및 다기관 임상 자료로 개발했다고 설명한다. 네 sequence, brain extraction, co-registration을 요구하며 FLAIR-only는 지원한다고 명시하지 않는다. BraTS/MSD 학습을 명시한 후보보다 출처가 적합하지만 환자 단위 비중복을 증명하지는 못한다. [공식 저장소](https://github.com/CCI-Bonn/HD-GLIO)
- 공식 실행 코드는 `[T1,T1c,T2,FLAIR]`, fold 0과 `model_final_checkpoint`를 사용한다. 설치 코드는 nnUNet v1 계열 의존성을 요구한다. 따라서 전용 환경에서 버전·가중치·실제 입력 검증이 필요하다. [공식 추론 코드](https://raw.githubusercontent.com/CCI-Bonn/HD-GLIO/master/hd_glio/hd_glio_predict.py), [설치 정의](https://raw.githubusercontent.com/CCI-Bonn/HD-GLIO/master/setup.py)
- MONAI BraTS bundle도 네 sequence를 사용하는 BraTS 2018 학습 모델이다. 현재 MSD와의 학습 중복을 배제할 근거가 부족해 이번 우선 후보로 선택하지 않았다. [공식 모델 설명](https://raw.githubusercontent.com/Project-MONAI/model-zoo/dev/models/brats_mri_segmentation/docs/README.md)

## 의미와 미확인 사항

HD-GLIO 비교는 동일 입력 실험이 아니다. 추가 sequence와 전체 volume을 허용하는 실제 대안의 충분성을 먼저 판단한다. 이를 위해 짧은 새 학습보다 기존 전문 checkpoint 비교의 정보 가치가 높다. 반대로 HD-GLIO의 저성능은 FLAIR-only VLM 방법의 필요성을 증명하지 않는다.

checkpoint 다운로드 가능성·정확한 label 의미·현재 환경 호환성·D6의 네 sequence 전처리 적합성은 아직 실행으로 확인하지 않았다. 구현 단계의 한정 점검과 실제 출력으로 연결한다. 이번 계획 단계에서는 파일 수정·환경 설치·실험 실행을 하지 않았다.
