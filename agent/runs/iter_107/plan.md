# 요약

- **이번에 할 일:** 기존 다중 영역 소견 47개·36명에 CURE 공식 단일 phrase grounding을 적용하고 저장된 적응 MedGrounder 출력과 비교한다.
- **필요한 이유:** 미지원 복합 phrase에서 벗어나, 공식 독립 처리에도 일부 위치 근거만 빠지는 문제가 남는지 확인한다.
- **확인할 기준:** 두 판독자의 주석이 일치하는 10명에서 부분 누락을 구분하고 MedGrounder의 낮은 threshold로 해결되는지 본다.
- **주의·다음:** 개발 자료의 시스템 진단이다. 판독 정확성·내부 원인·신규 기여는 확정하지 않으며 종료 후 full review와 사용자 승인을 거친다.

## 알림 맥락

- 연구: 위치 근거와 판독 연결
- 데이터: 흉부 X-ray PadChest-GR의 기존 개발 V96
- 모델: frozen CURE와 저장된 적응 MedGrounder; 신규 학습 없음
- 과제: 원문 소견 하나와 영상을 받아 해당 위치들을 출력
- 가설: 일부 위치 근거 누락이 주석 차이와 단순 threshold 제외만으로 설명되지 않을 수 있음
- 질문: 한 소견의 여러 위치를 확인할 때 일부만 보여 주는 문제가 기존 대안에도 남는가?
- 변경: 구체화
- 연결: iter_106 복합 입력 손실은 보존하고, 공식 지원되는 자연 단일 소견의 다중 영역으로 비교를 좁힘
- 작업: 기존 비교군을 재사용한 작은 출력 비교로 최소 개입 검토 또는 투자 보류를 결정

# Current Understanding

iter_106의 독립 recall 0.875, 공동 0.234375/0.109375와 반복 손실 0.40625는 원 범위로 보존한다. 복합 입력 분포와 결합 능력은 분리되지 않았으며 이 실험의 정상 사용 한계 근거로 승격하지 않는다.

CURE는 자연 단일 phrase에 여러 box를 출력하는 경로를 지원한다. PadChest-GR의 `extra_boxes`는 다른 판독자의 대체 주석이다. 공식 box 수를 병변 개수로 간주하거나 두 주석을 합쳐 추가 정답으로 만들지 않는다. 공식 union IoU는 실제 영역 합집합을 계산한다.

기존 V96의 MedGrounder 출력에 연결되는 다중 box 소견은 47개·36명이다. 두 주석이 각각 두 개의 분리된 box이며 일대일 IoU≥0.5 대응을 갖는 핵심 집단은 10명이다. 이 숫자는 metadata 확인 결과이며 모델의 부분 누락 빈도는 아직 계산하지 않았다.

# Strategy Check / 연구 방향 판단

**시험 설정:** A/B 선택·복합 phrase·추가 LoRA는 보류를 유지한다. 공식 단일 phrase의 작은 비교만 선택한다.

**연구 관찰:** iter_106은 입력 확장의 출력 손실이다. 이번은 같은 원인의 재현이 아니라 공식 독립 처리에 남는 조건을 탐색하는 새 후보다. iter_046의 모듈형 적응 효과와 iter_048의 형식 학습 회복을 반대 근거로 유지한다.

**연구 질문:** 여러 위치에 근거한 문장을 검토할 때 일부 위치만 제시되는가? 기술 질문 → 분리된 두 근거 중 하나만 보존되는 실패 조건 → 두 독립 주석과 동일 phrase의 CURE/MedGrounder 비교 → 공개 주석상 위치 근거 보존이라는 범위로 연결한다. 자유 판독이나 임상적 병변 완전성은 측정하지 않는다.

후보는 두 가지다. 지원 공동 경로는 동일 정보 대조가 확인되지 않아 실행을 보류한다. 자연 다중 영역은 공식 지원·주석 합의 집단·강한 저장 비교군이 있어 선택한다. 단순히 낮은 점수를 찾는 것이 아니라, 부분 누락이 낮은 threshold의 모듈형 대안으로 해결되는지가 투자를 바꾼다.

가까운 기존 방법은 CURE PG와 적응 MedGrounder다. 이들이 충분하면 해당 성공을 받아들인다. 동일 예측을 다시 생성하거나 전체 V96 benchmark를 반복하지 않는다. 현재 추가 비용은 CURE 47개 요청과 한정 연결·평가이며 구현·검증 시간은 미측정이다.

# Hypothesis

지원된 단일 소견에서도 분리된 공간적 근거 중 일부만 출력할 수 있다. 주석 분할 차이, 전체 위치 실패, threshold에 따른 후보 제외를 경쟁 설명으로 둔다. 두 주석에서 일관된 부분 누락과 낮은 threshold 대조를 통해 설명 범위를 좁힌다. autoregressive 종료나 내부 attention을 원인으로 가정하지 않는다.

# Limitation Evidence / Correct Usage Checks

연결 id는 `cure-composite-phrase-grounding-output-loss`다. 이는 이전 관찰을 계승하기 위한 연결이며 새 가설의 observed 인증이 아니다. 이번 역할은 diagnostic, method_stage=none이다.

`agent/runs/iter_106/review.md`, 해당 LIMITATIONS 항목, iter_105 review.json의 한정 실행 승인과 iter_046/048 원 리뷰를 기준으로 한다. CURE는 MedGemma 1 기반 adapter다. `report86_common.py`의 base revision `290cda5eeccbee130f987c4ad74a59ae6f196408`, adapter revision `4bb5dc5a5025a854d1f25e475769949915b08b44`와 실제 자산을 확인한다. MedGemma 1.5에 adapter를 로드하지 않는다.

공식 `Ground the phrase: {원문}`과 기존 CLAHE 448 processor 경로, greedy, seed17, NF4/bf16 계산 조건을 유지한다. 이 양자화 실행 조건을 결과에 명시하며 논문의 모든 수치 재현으로 부르지 않는다. cap은 기존 1024→2048→4096 비EOS 재시도 규약을 유지한다. 좌표가 없는 정상 종료는 내용 관찰이며 진입 실패로 취급하지 않는다.

# Contribution Path / Baselines / Reuse

기여는 미확정이다. 부분 근거 누락이 강한 단순 대안에도 남아야 후속 개입 검토의 근거가 된다. 새 metric·일반적인 검출 오차·모델 순위 자체를 contribution으로 삼지 않는다.

MedGrounder는 `results/iter_046/mg/V96_A_w2b4/raw_worker0.jsonl`과 `raw_worker1.jsonl`을 사용한다. `final_selection.json`의 A_U_e5, 선택 threshold 0.8과 고정 threshold 0.4를 유지한다. 저장된 원본 좌표 `boxes_orig_xyxy`를 읽고 새 후처리나 threshold 선택을 하지 않는다. 양쪽에 동일 영상·원문 소견을 제공하지만 학습량·사전학습·양자화는 다르므로 방법 효과 비교가 아니다.

기존 iter_085/086 GRG·anatomy 출력은 입력 정보가 달라 PG 대체물로 쓰지 않는다. 새 학습·직접 SFT·새 모델 설치는 이번 진단에 필요하지 않다. MedGrounder 원 실행의 검증은 원 리뷰와 digest 연결을 재사용한다. 결과 파일의 patient/target/image/sentence hash와 공식 GT 연결은 이번에 확인한다.

선별 반입 파일은 reuse_assets에 지정했다. `lk105_run.py`의 모델 로딩·공식 입력·생성·재개 경로를 새 `nr107_*` 실행 파일에 필요한 범위로 적용한다. 원본 파일과 과거 결과는 수정하지 않는다. lk105의 A/B parser·충분성 판정과 lk106의 clean_subset 해석은 사용하지 않는다. 전체 snapshot 재사용 승인이 아니다.

# Proposed Experiment

## 1. 고정 집단과 자료 적합성

`results/iter_039/data/manifest_private.jsonl`에서 iter_046 V96 raw 출력에 환자·target으로 연결되는 공식 box 2개 이상 항목 47개를 전부 선택한다. ImageID·PatientID·finding_index·원문 hash·원본 GT·split을 원 metadata와 대조한다. 36명임을 확인하고 모두 반복 개발 자료로 표시한다. 학습 노출 미확인은 유지한다.

핵심 집단은 출력과 무관하게 다음으로 고정한다: 공식·대체 주석이 각각 정확히 두 box, 각 집합 내부 IoU=0, 두 집합 사이 일대일 대응의 각 IoU≥0.5. 현재 10명·10개다. 개수나 연결이 다르면 오류를 조사하되 기준을 완화하거나 환자를 교체하지 않는다. 나머지 37개는 주석 차이를 포함한 기술통계이며 핵심 사건 기준에 합치지 않는다.

47개를 `sha256(ImageID|finding_index)`로 정렬한 첫 4개로 영상·주석 overlay, uint16→uint8와 공식 transform, 좌표 원점·정규화, 문장 연결을 확인한다. overlay는 연결 확인용이며 임상 정답을 assistant가 새로 판정하지 않는다.

## 2. 동작 확인

고정 4개를 실제 CURE PG로 생성한다. 공식 processor 입력과 tokenization, 모델 자산 hash, 요청 ID와 출력 연결, EOS/cap, 재개를 검사한다. malformed bracket, 세 숫자, nan/inf, 비양수 폭·높이, 좌표 없는 prose를 구분하는 parser fixture를 먼저 고정한다. 정상 no_box를 malformed로 바꾸지 않는다. cxcywh→xyxy 변환 후 범위도 검사하며 clipping으로 오류를 숨기지 않는다.

기술 오류는 해당 경로만 수정한다. 모델 정답률이나 100% oracle 성능은 진입 기준이 아니다. 원문·정답·입력 연결이 성립하지 않으면 GPU 본비교를 보류하고 종료한다.

## 3. 가능성 탐색

설정·manifest·평가 코드를 잠근 뒤 47개 CURE PG를 완성한다. 동작 확인 4개는 설정이 불변이면 재사용한다. MedGrounder는 동일 47개의 두 고정 운영점 저장 결과를 읽는다. 양쪽 모두 원본 정규화 xyxy로 평가한다.

## 4. 규모 확대와 독립 확인

이번 반복의 본비교는 기존 집단 47개로 끝난다. 핵심 10명은 확증 표본이 아니며 다른 환자·기관의 독립 확인은 하지 않는다. 양성일 때에도 최소 개입 또는 독립 확인의 가치와 표본 설계를 리뷰에서 제안할 뿐 자동 확대하지 않는다. E96·추가 학습·seed·prompt 탐색은 없다.

## 자원·시간·재개

신규 과학 요청은 47개다. 과거 단일 PG 6.33초를 적용한 생성시간 합은 약 298초이며 이는 wall-clock이나 device-time이 아니다. 고정 4개의 loading·생성·검증 실측으로 남은 wall-clock을 산출한다. 임의 시간 상한은 두지 않는다.

실행 직전 nvidia-smi와 상속 CUDA_VISIBLE_DEVICES를 확인한다. 독립 shard를 두 GPU에 배정한다. 기존 CURE 약 10GB peak는 참고값이며 worker당 2GB 여유를 추가한다. GPU당 두 worker는 실측 peak 합계와 초기화 경합까지 안전할 때만 기술 입력에서 비교한다. 이 작은 workload에서 추가 loading·검사 비용이 예상 절약보다 크면 두 GPU 각 한 worker를 유지하고 근거를 기록한다. iter_106의 admission 거부를 처리량 비교 성공으로 쓰지 않는다.

worker별 출력·고유 요청 ID·원자적 소유권·행 단위 저장·partial 복구·completion digest를 유지한다. admission 실패도 배치·메모리·종료 상태를 기록한다. 새 결과와 cache는 `results/iter_107/` 아래에 저장하고 기본 환경과 hf_cache는 변경하지 않는다.

# Implementation Tasks for Claude

1. 지정 자산과 원 리뷰의 승인 범위를 확인하고 새 branch의 실제 파일을 연결한다. 누락 파일을 임의 재구현하지 않는다.
2. 기존 raw 결과를 읽는 한정 loader와 고정 47개/핵심 10명 manifest를 작성한다. GT와 extra를 별도 보존하고 모델 요청에는 GT를 넣지 않는다.
3. 기존 CURE 실행 경로를 적용한다. 큰 가중치 실제 hash 검증과 admission 실패 기록을 보완하고 이전 실험 출력 경로를 변경하지 않는다.
4. 아래 기하 지표와 사건 규칙을 고정한다. malformed·큰 box·중복 box·분할 box·빈 출력·두 주석 불일치 fixture를 검사한다.
5. 고정 4개 기술 확인 후 같은 설정으로 47개를 완성한다. 예상 요청 집합·실제 완료·중복/누락·cap·자원을 기록한다.
6. production 함수를 호출하지 않는 별도 기하 계산으로 핵심 10명의 사건과 공식 union IoU를 재계산한다. 47개 결과의 입력·출력 digest와 report를 연결한다.
7. 관찰·해석·후속 투자 결정을 구분해 보고하고 full review에 넘긴다. 보고용 추가 모델 호출과 무관한 리팩터링은 하지 않는다.

# Evaluation (성공/실패 기준 포함)

## 지표와 사건 정의

예측 box들의 실제 합집합을 P라 하고, 각 정답 box g의 coverage를 area(P∩g)/area(g)로 계산한다. box 일대일 matching을 강제하지 않아 분할 방식 차이를 줄인다. 예측이 없거나 malformed/truncated이면 coverage는 0으로 두되 상태를 별도 보고한다.

핵심 10명에서 두 주석의 일대일 대응을 고정한다. 한 공간적 근거가 두 판독자 각각에서 coverage≥0.5이고 다른 근거는 두 판독자 각각에서 coverage≤0.1이면 **주석 일치 부분 누락** 사건이다. recovered와 missing의 방향도 동일해야 한다. 0.1~0.5 사이 또는 주석별 방향이 다르면 모호함으로 남긴다. 이 기준은 뚜렷한 부분 누락을 탐색하기 위한 조작적 정의이며 임상적 완전성 기준이 아니다.

큰 예측 box가 모든 영역을 덮는 편법을 감추지 않도록 공식·대체 GT 합집합별 union IoU와 예측 면적 중 주석 밖 비율을 함께 보고한다. 주석 밖 비율은 임상 FP가 아니다. 예측 면적이 0이면 비율은 NA로 표시한다. 각 집합에 대한 최소/평균 coverage, 모두 coverage≥0.5인 비율, 예측 수·no_box·malformed·cap 상태를 병기한다.

47개 전체에서는 두 주석을 따로 평가하고 extra 부재는 결측으로 둔다. 공식 union IoU, coverage, 표준 matching recall@0.3은 기술통계로 보고한다. 이를 핵심 10명의 사건 분모와 섞지 않는다. 환자별 집계와 환자 bootstrap 10,000회의 95% 구간을 제시하되 유의성 통과를 탐색 진입 조건으로 쓰지 않는다.

## 결과별 투자 결정

- **양성 탐색:** CURE의 주석 일치 부분 누락이 3명 이상이고, 같은 환자에서 MedGrounder 0.8과 0.4에도 부분 누락이 유지된다. 한두 사례의 우연한 현상보다 반복된 검토 대상을 확보하는 문턱이며 확증 기준은 아니다. 원시 출력·기하 연결과 과잉 포함을 리뷰한 후 최소 개입 검토만 권고한다.
- **단순 대안으로 설명:** CURE 사건이 MedGrounder에서 완전 coverage로 회복되거나 threshold 0.4에서 해소된다. 과잉 포함 비용을 함께 보고하고 현재 부분 누락 방법 투자는 보류한다. 새로운 VLM 방법 필요성을 주장하지 않는다.
- **음성:** 핵심 집단에서 CURE 부분 누락이 없거나 공식 출력이 두 근거를 보존한다. 이 조건의 추가 투자를 보류하며 일반 grounding 충분성을 주장하지 않는다.
- **불확정:** 사건 1~2명, 판독자 간 불일치, 넓은 box와 coverage의 trade-off, 또는 두 근거 모두 실패하는 기본 위치 부족이 중심이다. 해당 설명과 한계를 남기고 현재 후보를 보류한다. 같은 자료를 더 유리하게 채점하거나 새 prompt를 추가하지 않는다.

실험 유효성과 양성 가설은 분리한다. 유효한 음성도 종료 가능한 연구 결과다. 모든 결과가 추가 진단으로 이어지지 않도록 이번에는 위 두 투자 선택으로 마친다.

# Risks / Checks

- 개발 V96 재사용과 checkpoint 학습 노출 미확인을 명시한다. 신규 생성이 독립 평가를 뜻하지 않는다.
- 핵심 집단은 판독자 합의가 높은 사례에 제한되며 전체 다중 영역 소견의 빈도로 일반화하지 않는다.
- 부분 coverage는 병변 수·문장 사실성·임상적 누락의 정답이 아니다.
- MedGrounder의 threshold는 0.8/0.4로 고정한다. 조사에서 확인한 다른 운영점은 이번 선택에 사용하지 않는다.
- 지원 공식 template의 실행 성공과 논문 전체 재현, 새 기여를 구분한다.
- 주석 분할 차이와 모델 오류를 섞지 않고 불일치는 그대로 보존한다. 추가 전문의 대기를 재개하지 않는다.
- 기존 iter_105/106 판정·코드·결과와 미해결 reuse 이슈는 소급 수정하지 않는다.
- `--confirm-each-iter`를 유지한다. 이번 비교 종료 후 다음 반복은 사용자 승인 뒤 시작한다.

## 대규모 GPU 필요 후보

다중 위치 근거를 빠짐없이 보존하도록 대규모 VLM을 재학습하는 방향은 장기 후보로만 남긴다. 현재는 문제와 단순 대안의 부족함이 검증되지 않아 실행하거나 필요한 해법으로 주장하지 않는다.

# 계획의 근거 (GPT 조사 노트)

## 새로 확인한 사실

- 이전 노트 `agent/runs/iter_107/think/round_01.json` 원문을 읽었다. `agent/GOAL.md`, iter_106 원 리뷰와 한계 항목, iter_105/106 code_assets, iter_046/048 원 리뷰의 투자 범위를 확인했다. 연구 작업 트리는 clean이며 이번 계획 단계에서 파일 수정·생성·모델 실험은 하지 않았다.
- [PadChest-GR 원 논문](https://arxiv.org/html/2411.05085v2)은 양성 finding마다 두 판독자가 독립적으로 box 집합을 작성하고 공식 집합을 선정했다고 설명한다. `extra_boxes`는 추가 병변 목록이 아니라 대체 주석이다. box 수를 병변 수 정답으로 사용할 수 없다.
- CURE 로컬 공식 `vlm_research_kit/data/datasets/padchest_dataset.py`는 finding의 `boxes`를 사용하고 각 문장의 여러 box를 보존한다. 이전 라운드에서 확인한 공식 union IoU는 실제 polygon union이며 외접 사각형 평가가 아니다. [CURE 공식 저장소](https://github.com/PabloMessina/CURE)의 단일 phrase 경로를 유지한다.
- `research/results/iter_039/data/manifest_private.jsonl`과 `research/results/iter_046/mg/V96_A_w2b4/raw_worker*.jsonl`을 환자·target으로 연결하면 다중 공식 box 소견은 47개·36명이다. 주석 두 집합이 각각 정확히 두 box이고, 각 집합 내부 box IoU가 0이며, 두 집합 사이 일대일 IoU≥0.5 대응이 가능한 항목은 10개·10명이다. 이는 출력 성능을 사용하지 않은 metadata 조건이다.
- 대표 원문에는 양측 흉막 비후, prominent hila, 양측 흉수 등이 있다. 두 영역을 출력한 MedGrounder 사례도 실제로 확인했다. 다른 사례에서는 공식 6개 box와 대체 1개 box가 있어 개수 기반 누락 해석이 부적절했다. 이번 확인은 성능 집계나 대안 충분성의 확증이 아니다.
- `iter_046/decisions/final_selection.json`의 모델은 A_U_e5, checkpoint SHA256 `b9c2bccd04dde8b7445aa5f60e082a0c93f1f2412af8a583a4ca5ee207c8718a`, 선택 threshold 0.8, 고정 threshold 0.4다. 조사에서 일부 다른 threshold의 예측을 보았지만 후속 평가에서 운영점을 재선택하지 않는다.
- iter_085 D8 C 출력은 GRG·anatomy 설명이며, iter_086 E96 readings는 판독 조건들이다. 이들은 같은 정답 phrase를 입력받은 PG 결과가 아니므로 직접 재사용하지 않는다. iter_105/106 PG는 단일 box 두 소견을 선정했으므로 새 다중 영역 집단의 대체 출력으로 쓰지 않는다.

## 선택과 정보 가치

지원 공동 경로 후보는 동일 정보 대조가 확인되지 않아 보류한다. 자연 다중 영역 후보는 공개 주석의 합의 범위를 명시하고 기존 강한 대안과 직접 연결할 수 있어 작은 진단을 선택한다. 과거 문장별 총점 비교를 재현하는 것이 아니라, 부분 근거 누락이 주석·threshold로 설명되는지에 투자 결정을 한정한다. 47개 신규 요청보다 구현·출처 검증이 지배 비용일 가능성이 있으나 전체 시간은 미측정이다. 범용 평가기나 신규 모델 설치는 하지 않는다.

## 재사용

현재 HEAD는 `e6f7855f6596f113ec8d0940dc514f21284e18c5`다. 반입 대상 commit `f6b2942c2fcf2138feace3000f5bbdbfadb9a825`와 지정 파일의 존재를 git으로 확인했다. iter_105의 승인 범위는 한정 실행 경로이며 전체 snapshot 승인이 아니다. iter_106 parser·가중치 계승·admission 결함은 새 경로에 그대로 가져오지 않는다.

이전 사고 라운드 노트: agent/runs/iter_107/think/
