# 요약

- 이번에 할 일: 측뇌실 확장 여부가 명시된 뇌 MRI에서 균등 8장과 자동 해부학 선택 8장을 비교한다.
- 필요한 이유: 기존 FLAIR 판별은 종료됐다. 이번에는 관측 대상을 명확히 하고 전문 segmentation+규칙을 함께 비교한다.
- 확인할 기준: 선택에 따른 BA 개선, 전문 대안 대비 정확도·비용, 보고서와 영상 연결의 유효성을 본다.
- 주의·다음: 보고서 일치도 탐색이며 임상 진단 정확도나 신규 방법의 증명이 아니다. 탐색 후 자동 학습·확대하지 않는다.

## 알림 맥락

- 연구: MRI 관측과 근거 활용
- 데이터: 뇌 MRI MR-RATE의 axial T2와 측뇌실 크기 보고서
- 모델: frozen MedGemma 1.5, 전문 대조 SynthSeg
- 과제: T2 영상8장을 받아 양측 측뇌실 확장 여부를 출력한다
- 가설: 같은 영상 예산에서 관측할 위치를 바꾸면 판별이 달라질 수 있다
- 질문: 필요한 구조가 보이도록 영상을 고르면 답이 나아지며 전문 모델보다 남는 가치가 있는가?
- 변경: 방향 전환
- 연결: FLAIR 고신호 고정 판별 종료 → 정답 의미와 해부학 관측을 연결하기 쉬운 구조 소견 대조
- 작업: 자료 적격성 확인 후 균등 선택·해부학 선택·전문 부피 점수를 비교해 다음 투자 여부를 결정한다

# Current Understanding

iter_124의 양성11·음성12명에서 두 VLM 모두 PRESENT·BA0.50이었다. 현재 FLAIR 후보의 prompt·환자·모델 확대는 하지 않는다. 상위 MRI 근거 활용 질문과 과거 관찰은 유지한다.

round_01에서 남긴 질문의 답은 다음과 같다. 보유54 ZIP과 공식 guide는 배포 DWI/ADC 부재를 파일 구성 수준에서 뒷받침한다. 그러나 없는 sequence의 문장 억제는 ReMIND MARC와 직접 겹치고 단순 규칙 이후 남는 문제도 아직 없다. 이 후보는 실행하지 않는다. 구조 후보에서는 공식 train·axial T2·측뇌실 확장/정상 크기 문장의 연결을 확인했다. 최종 적격성은 전체 보고서 검토와 ZIP 확인이 필요하다.

이번 대상은 양측 측뇌실의 크기 기술이다. 수두증 원인·압력·치료 필요성을 평가하지 않는다. mild 또는 atrophy-associated enlargement도 양성 기술에 포함한다. 미표기·제4뇌실만 정상·질환 라벨0을 음성으로 사용하지 않는다.

# Strategy Check / 연구 방향 판단

출처는 iter_124/review.md와 iter_125/think/round_01.json이다. research_track은 유지한다.

1. 중요한 문제: 제한된 MRI 관측 예산에서 관련 해부학을 선택하는 것으로 VLM의 판단을 회복할 수 있는가?
2. 현재 근거: 기존 고정 응답은 유효 관찰이다. 새 구조 후보는 자료 연결만 확인했으며 모델 한계는 미관찰이다.
3. 쉬운 해결책: 자동 해부학 slice 선택과 전문 부피 점수를 직접 비교한다. 단순 대안으로 충분하면 새 방법 투자를 보류한다.
4. 남은 설명: sampling, 기본 인식·입력, 보고서 의미, segmentation 오류를 구분한다. 자동 선택이 해부학적 가시성을 완전히 보장한다고 가정하지 않는다.
5. 다음 결정: 선택의 유용성 보존, 전문 대안 채택 후 투자 보류, 또는 근거 부족으로 후보 보류 중 하나로 끝낸다.

# Hypothesis

H1: 관측 sampling이 중요한 병목이면 U보다 A에서 보고서 일치도가 높아진다.

H2: 단순 sampling만으로 해결되지 않으면 A에서도 낮은 수행이 남는다. 전문 점수 S가 높은 판별력을 보이는 경우에만 현재 자료에 판별 신호가 있다는 보조 근거가 된다. S도 실패하면 자료·정답·전문 모델의 적합성 설명이 남는다.

A의 개선을 순수 내부 선택 능력의 인과 증명으로 해석하지 않는다. 관측 위치·분포가 함께 바뀐다.

# Limitation Evidence / Correct Usage Checks

새 과제의 observed limitation은 없으므로 limitation_ids는 비운다. mrrate-flair-fixed-positive-response는 전환의 배경이며 이 과제의 method gate로 사용하지 않는다. 이번은 기존 도구와 입력 구성의 diagnostic이며 신규 selector 학습·loss 개발이 아니다.

모든 평가 정보는 모델 messages와 분리한다. 보고서·라벨·환자 식별자·selector 성공 여부를 prompt에 넣지 않는다. T2라는 정상적인 modality 안내와 inferior-to-superior 순서는 두 조건에서 동일하다. 공식 MedGemma processor·chat template을 사용하고 model/processor revision을 고정한다.

# Contribution Path / Baselines / Reuse

신규 기여는 미확정이다. 기존 SynthSeg와 sampling을 적용한 것 자체는 방법론 기여가 아니다. 가까운 선행과 실용 대조는 다음과 같다.

- ReMIND MARC: modality 누락 주장 억제에 직접 대응하므로 해당 후보를 보류한다. 공개 구현은 이번 조사에서 확인하지 못했으며 미설치를 실패로 취급하지 않는다.
- SynthSeg: 동일 T2 전체 volume의 측뇌실 segmentation·부피·ICV를 이용한다. 예측 mask는 입력 선택과 전문 대조에만 사용한다.
- 직접 SFT: 이번 관측 진단에는 학습하지 않는다. 후속 방법 pilot을 선택하려면 동일 supervision의 직접 적응을 포함할 별도 계약이 필요하다.

새 브랜치는 승인된 iter_082 기반을 요청한다. reuse_assets의 mr123_data.py, mr123_run.py, mr123_fetch.py를 선별 반입한다. 현재 브랜치에 있는 두 파일도 새 기반으로 넘어갈 때 반입 출처를 남긴다. 과거 코드를 찾지 못했다며 새로 복제 구현하지 않는다. 필요한 경로만 보완하며 iter_124의 Qwen 실행기·보고서 수동 lock은 재사용하지 않는다.

참고: [MR-RATE guide](https://github.com/forithmus/MR-RATE/blob/main/data-preprocessing/docs/dataset_guide.md), [SynthSeg 공식 코드](https://github.com/BBillot/SynthSeg), [ReMIND 원문](https://www.medrxiv.org/content/10.64898/2026.03.30.26349106v1.full).

# Proposed Experiment

## 1. 자료 확인과 동작 확인

기존 batch04·batch23 metadata/reports/splits만으로 시작한다. 공식 train, 한 환자 한 study, 이전 iter_123/124 환자 제외를 적용한다. seed125의 SHA256 환자 순서로 batch×양음성 층을 고정하고 선정 전에 전체 규칙을 저장한다.

양성은 양측 측뇌실 또는 이를 포함한 명시적 복수 측뇌실 확장 기술이다. 음성은 양측 측뇌실의 정상 크기·폭 또는 명시적 확장 부재다. unilateral-only enlargement, 위치가 모호한 ventricular 표현, 같은 대상의 정상/이상 상충은 unknown으로 분리한다. 정규식은 후보 검색만 담당한다. findings·impression·report 전체에서 인용 구간과 제외 사유를 기록한다. 다른 소견의 상충까지 무조건 제외하지 않되 목표 소견 해석에 영향을 주는지 명시한다. 새로운 LLM의 추론으로 정답을 보충하지 않는다.

각 batch×label에서 기술2명·calibration3명·탐색10명을 선택하여 총60명을 계획한다. 경도·위축·기타 동반질환 분포를 기록하고 어려운 사례를 성능 때문에 제외하지 않는다. 최종 적격 수가 부족하면 GPU 실행 전 실제 규모·정밀도 영향을 보고하고 본 설계를 보류한다. 임의 질환 전환은 하지 않는다.

series는 axial T2 중 작은 slice spacing, 작은 in-plane voxel area, series_id 사전순으로 선택한다. 원영상과 brain mask 연결·3D 여부·finite intensity·affine·brain coverage를 검사한다. 기준을 통과하지 못한 경우 출력 전에 고정된 다음 후보로만 대체한다.

ZIP은 선택 study 단위로만 다운로드한다. 기존 ZIP과 신규 ZIP의 합계·revision·SHA를 확인하며 누적10GiB 예산과 실제 추출 용량을 먼저 산출한다. 예산이 필요한 표본을 막으면 다운로드 전에 비용 근거를 보고하고 멈춘다. 다른 파일을 삭제하지 않는다.

SynthSeg 공식 revision·가중치·license·노출 정보를 확인하고 격리 환경에 설치한다. 기술8명에서 실제 GPU segmentation, 좌표 연결, 측뇌실 label 의미, ICV 출력, QC 및 명백한 segmentation 실패를 검사한다. 공식 label table의 실제 위치를 확인하며 숫자 label을 추측하지 않는다. 설치가 막히면 공식 호환 환경을 한정 시도하고 오류·남은 blocker를 기록한다. 전문 대조 없이 본평가를 시작하지 않는다.

## 2. 입력과 전문 대조

U: 원 T2의 brain-mask 유효 axial 구간 5–95%에서 등간격 고유8장.

A: 동일 T2에 적용한 SynthSeg 양측 측뇌실 합집합을 원 T2 격자로 nearest-neighbor 변환한다. 측뇌실 면적이 해당 volume 최대 면적의5% 이상인 slice의 최소–최대 구간에서 등간격 고유8장을 선택한다. 8개 고유 slice를 얻지 못하거나 segmentation이 실패하면 U로 fallback하고 사건을 별도 보고한다. 결과를 보고 slice를 손으로 고르지 않는다.

두 조건은 같은 원본 해상도·brain percentile1–99 window·896 canvas·방향·영상8장·생성 설정을 사용한다. mask overlay나 정답 위치는 보여주지 않는다. 기술 montage에서 변환·해부학 포함 여부를 확인하되 연구자가 확장 여부를 새로 판독하지 않는다.

S: 같은 T2의 양측 측뇌실 부피/ICV 연속 점수. calibration12명에서 BA를 최대화하는 한 threshold를 고정한다. 동률이면 specificity, 이어서 큰 threshold 순으로 결정한다. 탐색40명에서 threshold BA와 threshold-free AUROC를 함께 보고한다. calibration 규모가 작으므로 threshold 불안정성도 기록한다. 원영상 전체를 보는 S와 8장만 보는 VLM의 정보 차이를 숨기지 않는다.

고정 prompt:
`You are shown 8 axial T2-weighted slices from one brain MRI examination, ordered from inferior to superior. Is there evidence of enlargement of both lateral ventricles in the images shown? Answer on the first line with exactly one word: PRESENT, ABSENT, or UNCERTAIN. Then give a brief justification in at most two sentences.`

MedGemma는 bf16·greedy·max_new_tokens512로 시작한다. 기술 단계의 cap 도달만 길이 부족으로 판정하며 그 경우 기술 전체를1024로 한 번 재검사한 뒤 최종 cap을 잠근다. 내용 점수에 따른 prompt 변경은 없다.

## 3. 가능성 탐색

기술8명의 동작·메모리·출력 검사를 통과하고 calibration threshold를 잠근 뒤 탐색40명에서 U/A80건을 생성한다. 기술 단계의 낮은 정확도만으로 탐색을 취소하지 않는다. 명시적 답·UNCERTAIN·형식 실패·거부를 분리한다. calibration 환자의 VLM 출력은 필요하지 않다.

두 조건 모두 같은 환자를 포함하며 selector 실패도 primary intent-to-process 평가에서 유지한다. segmentation 성공 집단의 보조 결과를 함께 내되 좋은 사례만 남겨 primary를 바꾸지 않는다.

## 4. 규모 확대와 독립 확인

이번 반복은 탐색40명까지다. 이는 개발 자료이며 독립 확인이 아니다. 양성 기준과 전문 대안 이후의 잔여 가치를 충족하면 새 환자의 독립 확인 또는 최소 방법 pilot 중 하나를 다음 계획에서 결정한다. 본격 학습·다중 seed·공식 test 평가는 자동 진행하지 않는다.

# Implementation Tasks for Claude

1. 원 리뷰·반입 manifest를 확인하고 새 protocol, 환자 split, 적격성 표, 입력 및 코드 hash를 저장한다.
2. 기존 fetch/data의 결과 경로를 명시적 인자로 바꾸고 study/series/revision/settings별 캐시와 원자적 ledger를 적용한다. 기존 산출물은 변경하지 않는다.
3. SynthSeg 격리 환경과 실제 기술 출력, label·좌표·ICV 검사를 완료한다. T2 원영상은 한 번 선택한 뒤 모든 대조가 공유한다.
4. U/A 요청과 S calibration을 고정한다. strict JSONL·중복 검사·완료 수 실패 반환·실제 설정 검증을 구현한다. 기존 손상 무시 reader와 실행 중 claim 삭제는 사용하지 않는다.
5. 공식 processor 비교, 방향·mask 왕복, label 누출, threshold의 calibration 전용 사용, 중복·누락·손상 입력의 실패 반환을 검사한다.
6. 탐색 출력을 보존하고 별도 계산 경로로 환자별 정오·BA·AUROC·paired CI·fallback·비용을 검산한다.

## GPU·시간·재개

실행 직전 nvidia-smi와 허용 논리 장치 매핑을 확인한다. 두 GPU에 독립 환자를 나누고 작업 의존성이 허용하면 segmentation 전처리와 준비된 VLM shard를 병렬 처리한다. TensorFlow의 전체 메모리 선점을 제한하고 실제 peak를 측정한다.

MedGemma8–10GB는 참고값이다. 기술 입력에서 GPU당 worker1과 batch2를 먼저 비교한다. batch2가 부적합하고 메모리상 가능하면 GPU당 worker2를 후보로 검사한다. 처리량이 증가하고 동일 출력·평가 조건을 유지하며 worker당2GiB 여유를 확보한 구성만 채택한다. 과거 Qwen batch2 결과는 이번 MedGemma 메모리 근거로 대체하지 않는다.

예상 시간은 측정 전 미정이다. 기술 단계에서 다운로드·추출·SynthSeg·render·VLM·저장 시간을 분리 측정하고 남은60 volume 및80요청의 wall-clock을 병렬 처리량으로 산출한다. 임의 시간 상한을 두지 않는다. stage lock, 고유 요청ID, worker별 출력, 종료 확인 후 미완료 재개를 사용하며 stage별 manifest와 결과 seal을 남긴다.

# Evaluation (성공/실패 기준 포함)

Primary는 탐색40명의 report-agreement BA다. UNCERTAIN·INVALID·거부는 정답으로 세지 않으며 각 비율을 별도 보고한다. sensitivity·specificity, U/A 환자별 paired 변화, S AUROC·BA를 함께 보고한다. batch×label 층화 환자 bootstrap10,000회로95% CI를 산출한다. S−A/U 차이도 동일 환자에서 계산한다.

- 양성 관측: A−U BA≥0.15, paired CI 하한>0, A BA≥0.75, sensitivity·specificity 각각≥0.65. 이는 후속 검토 기준이며 임상 성능 기준이 아니다.
- 단순 대안 충분성: S BA≥0.80이고 A가 S를0.05 이상 개선하지 못하며 전체 실행 비용이 더 크면, 현재 이진 구조 판별에 대한 VLM 방법 투자를 보류한다. 작은 calibration의 불안정성과 CI를 함께 보고하여 보편적 충분성을 주장하지 않는다.
- 음성: U와 A 모두 BA≤0.60이면 현재 frozen 설계를 종료한다. S가 높으면 단순 sampling만으로 회복되지 않았다는 범위로 보존하고, S도 낮으면 정답·자료 적합성이 남았다고 보고한다.
- 불확정: 나머지 성능, 높은 fallback, 정답 상충 또는 넓은 CI는 근거 부족으로 보류한다. 같은 환자에서 prompt·threshold·selector를 조정하거나 세 번째 모델을 추가하지 않는다.

관측 양성과 투자 판단은 분리한다. A가 개선되어도 전문 대안 이후 잔여 가치가 없으면 새 방법은 개발하지 않는다. 최소 가치 있는 성능 차이는0.05 BA로 보되 비용·정보량 차이를 함께 보고한다. 모델 load 포함 cold-start와 NIfTI 읽기부터 답 저장까지 warm workload 비용을 구분한다.

# Risks / Checks

- 보고서는 자동 번역·구조화된 약한 정답이다. 명시적 크기 기술의 일치도만 주장한다.
- SynthSeg는 예측 도구다. mask·부피·ICV를 임상 정답으로 승격하지 않는다. 같은 예측을 A와 S가 공유하는 의존성을 명시한다.
- 구조적 확장은 정도·위축·압력과 얽힌다. mild/atrophy 양성을 임의 제외하거나 수두증으로 재명명하지 않는다.
- 보유 ZIP의 modality 이름 확인은 독립적인 영상 modality 판독과 다르다. 이번 T2 입력에서도 metadata·원파일·시각적 기술 검사를 수행한다.
- 관측 예산은 같아도 A에는 전문 segmentation 비용이 추가된다. 전처리·실패·저장 비용을 누락하지 않는다.
- 과거 모델 노출과 독립 외부 일반화는 미확인이다. 결과를 MRI 전체의 한계로 확대하지 않는다.

## 대규모 GPU 필요 후보

전체3D 다중 sequence 표현과 질문별 관측을 공동 학습하는 적응은 장기 후보로 보존한다. 현재의 단순 대안 이후 잔여 문제가 검증되기 전에는 발주하지 않는다. 필요한 자원량과 신규성은 아직 산정·확정하지 않았다.

# 계획의 근거 (GPT 조사 노트)

## 새로 확인한 것

- round_01.json 원문, GOAL, iter_124 원 리뷰와 code_assets, iter_123 code_assets, LIMITATIONS의 현재 MR-RATE 항목을 확인했다. 기존 FLAIR 후보 종료를 유지한다.
- 로컬 ZIP 54개의 img member를 비변경 조회했다. 영상439개는 T1w171·FLAIR136·T2w75·SWI57개이며 DWI/ADC 이름의 member는 없었다. 이는 파일명·공식 분류 범위의 확인이며 모든 voxel의 modality를 독립 검증한 결과는 아니다.
- [MR-RATE 공식 guide](https://github.com/forithmus/MR-RATE/blob/main/data-preprocessing/docs/dataset_guide.md)는 배포 modality를 T1w/T2w/FLAIR/SWI/MRA로 명시한다. 따라서 보고서의 diffusion 문장을 배포 영상의 임상 정답으로 사용할 수 없다. 평가할 수 있는 것은 제공하지 않은 sequence를 직접 관측했다고 주장하는지 같은 제한된 범위다.
- [ReMIND 원문](https://www.medrxiv.org/content/10.64898/2026.03.30.26349106v1.full)의 검색 제공 본문에서 MARC의 modality cue·polarity 가중 검증, 후보4개 reranking, 위반 문장 삭제와 중립 fallback을 확인했다. natural-missing 및 modality 제거 후 주장 지속을 평가하며 보고서 품질과의 trade-off도 다룬다. 직접 본문 접속은 오류, PMC는 CAPTCHA였고 공개 코드 경로는 확인하지 못했다. 이 미확인을 구현 불가능으로 해석하지 않는다. 현재의 누락 sequence 후보는 단순 목록·삭제 이후 잔여 평가가 구체화되지 않아 보류한다.
- 구조 후보를 수두증 진단이 아닌 측뇌실 크기 기술로 좁혔다. 공식 train·axial T2 연결 후 명시적 표현을 검색한 고유 환자 후보는 batch04 양성101/음성1026, batch23 양성29/음성858이었다. 부정·상충·해부학 범위의 전체 검토 전 후보 수이며 적격 인원은 아니다. 3BSXTVK4LF의 양측 측뇌실 확장과 IBMBN6LSZS의 명시적 정상 폭 등 원문 사례를 확인했다. 경도 확장·위축 관련 확장은 제외하지 않으며 수두증과 동일시하지 않는다.
- [SynthSeg 공식 README](https://github.com/BBillot/SynthSeg/blob/master/README.md)는 다양한 contrast/resolution의 segmentation, 부피·ICV·QC 출력과 1mm 출력 격자를 지원한다고 설명한다. 현재 환경 설치·가중치 접근·T2 출력은 미검증이다. 이는 전문 대조의 실행 조건이며 예측 mask의 정답 승인이 아니다.
- 현재 research HEAD는 a1a2743d0f29b0c6df592b97c572d03778b12b0d이며 작업 트리는 깨끗하다. mr123_data/run의 실제 코드와 e39ba…의 mr123_fetch 원문을 확인했다. data.extract의 study-only 캐시와 run.read_jsonl의 손상 무시 경로는 그대로 쓰지 않는다.

## 선택과 한계

누락 sequence 진단은 가까운 선행과 단순 규칙에 직접 겹치므로 보류한다. 구조 소견에서는 실제 양음성 문장·관련 T2·전문 대조가 연결될 가능성을 확인했으므로 한정 자료 검증과 실제 비교를 묶는다. 새 한계·방법 효과는 아직 관찰하지 않았다. 전문 대안 이후 가치가 없으면 이 후보도 종료한다.

이전 사고 라운드 노트: agent/runs/iter_125/think/
