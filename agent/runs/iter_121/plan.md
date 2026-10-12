# 요약

- **이번에 할 일:** MR-RATE의 급성 뇌경색 보고서와 DWI–ADC를 연결하고, 조건이 성립하면 6명 동작 확인 후 별도 48명에서 관측 범위·분할 집계를 비교한다.
- **필요한 이유:** 과거 MRI 결과는 기본 인식·불충분 관측·공동 처리의 영향을 분리하지 못했다.
- **확인할 기준:** 같은 영상 예산에서 보고서 일치도와 비용이 달라지는지, 단순 집계로 충분한지 확인한다.
- **주의·다음:** 자동 보고서 라벨 기반 탐색이다. 임상 진단 정확도·일반 VLM 한계·새 방법 기여를 확정하지 않는다.

## 알림 맥락

- 연구: MRI volume 근거 활용
- 데이터: 영상 간 대상 대응 자료 → MR-RATE 뇌 MRI의 DWI–ADC
- 모델: MedGemma 1.5 4B, frozen 추론
- 과제: 여러 단면을 받아 급성 뇌경색 근거의 존재·부재·판단 불가를 출력
- 가설: 관측 범위 부족 또는 공동 처리 부담이 보고서 불일치의 일부를 설명할 수 있음
- 질문: 같은 수의 MRI 단면을 넓게 보거나 나눠 판단하면 답변이 개선되는가?
- 변경: 방향 전환
- 연결: iter_120은 적격 관계쌍 부재로 모델 미실행이며, 사용자 요청으로 기존 방향을 보류하고 MRI 탐색으로 전환
- 작업: 자료 조건 확인 후 실제 paired 추론으로 단순 대안 채택·한정 후속·투자 보류를 선택

# Current Understanding

최종 GOAL과 과거 판정은 유지한다. iter_120의 자료 설계 및 기존 grounding·초안 교정 방향은 보류하고 자동 재개하지 않는다. 상위 질문은 기존 mri-volume-evidence-use를 이어받는다.

iter_062는 key-image의 관측 충분성을 보장하지 못했다. iter_064의 context 손실은 모델 특이 가능성이 남았으며, iter_077에서는 일반 분류기가 강한 대안이었다. iter_083의 자료 연결 실패는 모델 능력의 반증이 아니었다. 이번에도 입력 수가 많다는 사실만으로 통합 능력을 시험했다고 부르지 않는다.

MR-RATE의 study·환자·series header는 이전 기록에서 확인됐지만 실제 적격 집단은 아직 없다. 현재 계획 환경에는 전용 외부 경로가 보이지 않는다. 구현 환경에서 승인된 경로를 확인하고, 불가하면 무단으로 SSD에 대체 반입하지 않는다.

# Strategy Check / 연구 방향 판단

1. **중요한 문제:** 제한된 영상 예산에서 MRI volume의 근거를 관측·활용하는 능력은 실제 VLM 사용의 정확도와 비용을 좌우한다.
2. **현재 근거:** iter_064 원 리뷰의 제한된 context 손실과 반대 모델 근거를 계승한다. MR-RATE에서의 실패는 아직 가설이다.
3. **쉬운 해결책:** 넓은 등간격 sampling과 분할 OR 집계가 충분할 수 있다. 전문 volume 모델도 중요한 대안이다.
4. **남은 설명:** 범위 부족, 공동 처리 부담, 기본 인식 부족, 보고서·영상 불일치를 구분해야 한다. 이번에는 앞의 두 설명을 비교하되 나머지를 제거했다고 주장하지 않는다.
5. **다음 결정:** 단순 대안이 충분하면 방법 투자를 보류한다. 중요한 잔여 차이가 있으면 타 계열·전문 대조와 독립 확인을 별도 계획한다. 자료 의미가 무너지면 현재 설계를 보류한다.

후보 비교는 급성 뇌경색·수막종·탈수초 질환에 한정한다. 첫 후보는 명시적 급성 소견·음성과 DWI–ADC 연결을 확인할 수 있다는 조건에서 선택했다. T1 조영 여부가 공식적으로 라벨링되지 않아 수막종을 우선하지 않는다. 후보별 메타데이터 빈도는 보고하되 세 질환을 모두 추론하지 않는다.

# Hypothesis

- **관측 범위 설명:** 같은 수의 단면에서 넓은 범위 입력이 중앙 범위 입력보다 일치도를 개선한다.
- **공동 처리 부담 설명:** 정확히 같은 넓은 범위 영상을 나눠 질의한 고정 집계가 공동 질의보다 개선된다.
- **경쟁 설명:** 둘 모두 낮으면 기본 인식, sampling으로 빠진 병변, 보고서 정답의 불확실성이 남는다. 분할 이득도 prompt 반복·OR의 sensitivity–specificity 변화로 설명될 수 있어 내부 통합 실패를 확정하지 않는다.

# Limitation Evidence / Correct Usage Checks

대상 id는 mri-explicit-target-context-effect지만 MR-RATE에 그 상태를 자동 이전하지 않는다. 이번 역할은 diagnostic이며 method gate를 통과한 것으로 간주하지 않는다.

공식 모델 revision·processor·chat template를 고정한다. NIfTI affine, orientation, spacing, 강도 범위, DWI b-value 또는 명시적 sequence 근거, ADC 대응, 영상 placeholder와 실제 tensor를 검사한다. 보고서·질병 label·원 파일명·임상 indication은 모델 입력에서 제외한다. DWI/ADC라는 중립 sequence 정보와 단면 순서만 제공한다.

# Contribution Path / Baselines / Reuse

새 방법은 없다. 직접 SFT·encoder+head·전문 모델 이후에도 남는 잔여 문제를 확인해야 향후 기여를 논할 수 있다.

실행 대조는 중앙 범위, 넓은 범위, 넓은 범위 분할 집계다. 분할 집계의 두 호출 비용을 숨기지 않는다. report 기반 정답을 받는 oracle 입력은 만들지 않는다.

NeuroVFM은 실제 공개 encoder·diagnostic head가 있는 가까운 대안이다. 이번에는 공식 MRI label 목록·가중치 접근 조건·학습 노출을 확인해 후속 가능성을 기록한다. 권한 없는 가중치를 우회하지 않고, 설치가 필요하다는 이유만으로 부적합 판정하지 않는다. ReMIND의 다중 sequence·modality-aware decoding과 이번 존재 판단의 차이도 기록한다.

현재 브랜치의 git status·diff·ls-files를 확인했다. 과거 MRI 실행기는 현재 tracked 파일에 없고 원 리뷰에 재개·provenance 결함이 있다. 이번에는 그 실행기를 선별 반입하거나 전수 복구하지 않는다. 현재 t3_*와 geometry는 과제가 달라 사용하지 않는다. 공식 processor에 기반한 이번 자료 전용 경로를 구현하며 과거 코드를 잃어버렸다고 보고하지 않는다. reuse_assets는 비운다.

# Proposed Experiment

## 1. 한정 자료 확인

공식 revision을 고정하고 splits.csv·mrrate_labels.csv를 먼저 확보한다. patient_uid–study_uid 중복·split 일관성, 세 후보 열의 실제 값·결측·환자 수를 집계한다. train/validation만 사용하고 test는 선택에 사용하지 않는다.

필요 batch는 seed121로 정한 순서에서 선택하며 metadata·reports 총량 250MB 안에서 먼저 확인한다. batch 선택에 따른 모집단 제한을 기록한다. 전체 batch 다운로드는 하지 않는다.

주과제는 **급성 뇌경색 보고서 일치**로 고정한다. Cerebral infarction 열은 후보 찾기에만 쓴다. 양성은 findings/impression에 현재 급성 뇌경색이 명시된 경우, 음성은 급성 경색 또는 급성 확산 제한의 부재가 명시된 경우로 제한한다. 만성 경색만 있는 사례는 급성 부재가 명시되면 음성이 될 수 있다. 병력만의 언급, 의심·배제 불가, 시간 범위 모호, 상충 문장은 unknown이다. 원문 span·규칙·제외 사유를 저장하고 새로운 LLM 판정을 정답으로 만들지 않는다. 표본을 채우려고 모호한 문구를 해석하지 않는다.

한 환자 한 study를 사용한다. 같은 환자에서 적격 study가 여러 개면 고정 hash 순서 첫 study를 선택한다. DWI와 ADC가 모두 있고 같은 검사에서 공간 대응·뇌 coverage가 확인돼야 한다. ADC는 derived라는 이유만으로 제외하지 않는다. localizer·b0-only·연결 불명확한 4D series는 제외하거나 명시적 metadata로 해소한다.

실제 label·report·sequence 연결이 성립하기 전에는 전체 실행기를 확장하지 않는다. 적격 부족이면 실제 수와 원인을 보고하고 수막종 등으로 자동 전환하지 않는다.

## 2. 동작 확인: 6명

양성3·음성3을 공식 train에서 고정한다. 주 탐색과 환자를 분리한다. ZIP 원격 크기를 합산하고 승인된 외부 경로에 study 단위로 받는다. 안전한 압축 해제, file hash, affine·spacing·series 대응과 실제 단면을 확인한다.

뇌의 유효 superior–inferior 범위는 제공 brain mask의 품질을 확인해 정한다. 이 mask는 해부학적 범위 산정용이며 병변 정답이 아니다. mask가 부적합하고 영상 기반 범위를 신뢰할 수 없으면 해당 사례를 제외한다. DWI–ADC가 동일 grid가 아니면 affine으로 같은 물리 위치에 대응시키고 경계·coverage를 검사한다. 임의 slice index 일치는 금지한다.

영상별 자동 대비 조절로 조건 차이를 만들지 않는다. volume별 고정 robust 강도 변환을 사용하고 ADC의 수치·단위·표시 변환을 보존한다. 모든 조건에서 동일 slice는 같은 pixel tensor여야 한다.

공식 다중 영상 입력 경로와 wrapper의 input_ids·pixel_values를 소수 입력에서 대조한다. 생성은 greedy, max_new_tokens=512에서 시작한다. 기술 집단에서 비EOS가 있으면 1024로 고정해 다시 검사한다. 그래도 잘리면 본실행을 멈춘다. 성능 점수로 prompt를 고르지 않는다.

## 3. 가능성 탐색: 별도 목표 48명

공식 validation의 적격 양성24·음성24를 seed121로 고정한다. 부족하면 train의 미사용 환자로 보충하고 split 출처를 층별로 보고한다. 적격 수가 40–47명이면 양성·음성 균형을 가능한 한 유지하고 실제 N과 낮아진 정밀도를 출력 전에 기록한다. 40명 미만이면 기술·소표본 관찰만 보존하고 본탐색 완료로 보고하지 않는다.

세 조건을 고정한다.

- **중앙 관측 C:** 유효 뇌 범위 중앙 50%에서 등간격 8개 위치의 DWI와 대응 ADC, 총16장.
- **넓은 관측 W:** 유효 뇌 범위 5–95%에서 등간격 8개 위치의 DWI와 대응 ADC, 총16장.
- **분할 집계 P:** W의 8개 위치를 아래쪽4·위쪽4로 분할한다. 각 요청은 DWI4+ADC4이며 총2요청이다. W와 동일 pixel을 사용한다.

C/W 질문은 제공된 영상에서 급성 뇌경색을 지지하는 근거가 있는지 묻는다. P는 각 묶음 내 근거를 묻는다. 답은 PRESENT/ABSENT/UNCERTAIN과 짧은 설명을 허용한다. P 집계는 하나라도 PRESENT면 PRESENT, 둘 다 ABSENT면 ABSENT, 나머지는 UNCERTAIN이다. 원시 답의 상충·거부·형식 오류는 별도로 보존한다.

환자당 C1+W1+P2=4요청, 48명에서192요청이다. 기술6명은24요청이며 재검사·처리량 비교는 별도 ledger에 남긴다. 본탐색 출력 이후 prompt·규칙·표본을 변경하지 않는다.

## 4. 규모 확대와 독립 확인

이번 48명은 개발 탐색이며 확증 집단이 아니다. 본 반복에서 추가 seed·학습·타 모델·새 환자 확대를 자동 실행하지 않는다. 중요한 차이가 관찰되면 full review에서 실제 discordance와 비용으로 후속 규모를 정한다. 후속은 단순 대안 이후의 잔여 문제와 새로운 독립 환자를 함께 다룰 때만 제안한다.

## 자원·시간·재개

데이터와 새 cache는 /home/test/.local/share/medgemma/mr_rate, 연구 소스는 research/, 결과는 iter_121 전용 경로에 저장한다. 메타데이터250MB·ZIP10GiB를 첫 안전 예산으로 사용한다. 압축 해제 예상량·실제 디스크 여유도 확인한다. 부족하면 조용히 다운로드를 늘리지 말고 필요한 비용·표본 영향을 기록한다.

실행 직전 nvidia-smi와 CUDA_VISIBLE_DEVICES의 논리·물리 대응을 확인한다. 두 GPU에 독립 환자 shard를 배정한다. 기술 입력에서 batch1 대비 batch2를 우선 비교하고, 메모리상 가능한 경우 GPU당2 worker를 검토한다. 동시 peak와 외부 점유에 worker당2GiB 여유를 더해 안전성을 판단한다. 16영상 입력은 모델 적재8–10GB만으로 증설하지 않는다.

유효 요청/분, GPU별 peak, 긴 출력 지연, OOM, CPU·I/O 경합과 출력 정합성으로 구성을 고른다. GPU당1 worker면 실제 메모리·처리량 근거를 남긴다. 예상 wall-clock은 기술 확인의 처리량 r에서 남은 요청수/r와 다운로드·전처리 실측을 합산한다. 현재 시간 실측은 없으며 임의 시간 상한을 두지 않는다.

요청 ID는 환자·조건·prompt·입력·model hash에 연결한다. worker별 결과를 쓰고 완료 ID를 검증해 재개한다. 손상 JSONL을 조용히 버리거나 완료 claim을 재실행하지 않는다. 최종 중복·누락·출력 수와 process 종료를 확인한다.

# Implementation Tasks for Claude

1. 기준 문서와 현재 소스를 확인하고 실행 환경·외부 경로·공식 revision을 기록한다. 토큰은 HF_TOKEN_PATH로만 참조한다.
2. 한정 metadata 집계와 정답 span·DWI–ADC 연결 검사를 구현한다. 후보 수·제외·unknown을 기록한다.
3. 조건이 성립하면 6명으로 영상·processor·출력 길이·처리량을 확인하고 manifest와 평가 규칙을 잠근다.
4. 고정 탐색 환자의 paired 추론을 두 GPU로 실행한다. 완료·재개·출처 검증을 포함한다.
5. 원시 응답을 독립 집계하고 보고서에 실제 규모·비용·해석 한계·투자 선택을 쓴다. 소스 checkpoint는 orchestrator 보존 절차를 따른다.

# Evaluation (성공/실패 기준 포함)

주지표는 전체 적격 환자에서 UNCERTAIN/invalid를 정답으로 세지 않는 BA다. sensitivity, specificity, 명시 답 coverage, unknown·거부·비EOS·invalid를 함께 보고한다. 명시 답만의 conditional accuracy는 보조값이다.

주비교는 W−C, 보조 비교는 P−W다. 환자 paired bootstrap10,000회·seed121의95% CI와 양방향 전환 수를 보고한다. 두 비교는 탐색적이며 선택된 최대값을 확증 효과로 쓰지 않는다. 상충 응답을 구현자의 의미 추측으로 재채점하지 않는다.

- **양성 탐색:** BA 이득≥10pp이고 CI 하한>0. W 이득은 sampling 가치, P 이득은 분할 처리의 실용 가치로 제한한다. 내부 원인·일반 MRI 능력은 미확정이다.
- **단순 대안 충분성 후보:** W 또는 P가 BA≥0.80, sensitivity·specificity 각각≥0.75이면 현재 개발 조건에서 단순 대안을 보존한다. 작은 표본으로 임상 충분성을 확정하지 않는다. 새 방법 투자는 우선 보류한다.
- **음성:** 차이의 CI 상한<10pp이면 현재 대조의 큰 이득 근거가 약하다고 판단한다. 모든 조건의 BA가0.60 이하이면 현재 frozen 설정의 기본 수행 부족을 보고하고 통합 실패로 명명하지 않는다.
- **불확정:** 나머지는 표본 변동·unknown·라벨 연결 중 지배 요인을 명시한다. 추가 표본이 판단을 바꿀 조건을 산출하되 이번에는 자동 확대하지 않는다.

비용은 원 NIfTI 읽기부터 답변 저장까지와 model load를 분리한다. P의 추가 prompt·output token과 호출 수를 포함한다. 이득10pp 미만의 비용 증가를 새 방법 가치로 포장하지 않는다.

자료·입력 무결성이 깨지면 execution_failed로 제한한다. 실제 출력 비교가 유효하지만 CI가 넓으면 inconclusive이며 실행 실패와 구분한다.

# Risks / Checks

- 자동 병리0은 명시 음성이 아니다. 급성·만성·병력과 현재 소견을 분리한다.
- 보고서 일치도는 임상 진단 정확도가 아니다. 일부 slice에 병변이 보인다는 공간 정답도 없다.
- W는 coverage와 slice 간격을 함께 바꾼다. 순수 coverage의 내부 인과 효과라고 부르지 않는다.
- P는 질문 범위·호출 수와 OR 편향이 달라진다. specificity 손실을 포함해 판단한다.
- DWI–ADC 대응, b0 혼입, ADC 단위, mask 오류, orientation·강도·토큰 수를 검사한다.
- 다른 질환 동반·장비·batch·split 분포와 제외율을 보고하고 깨끗한 정상만 고른 것으로 일반화하지 않는다.
- NeuroVFM 접근 조건과 MR-RATE 권한은 별개다. 필요한 추가 권한만 구체적으로 질문한다.
- 이번 계획에서 과거 관찰의 상태 승격·새 학습·공식 test 선택·개인 TOF·OAI 재개는 하지 않는다.

## 대규모 GPU 필요 후보

전체 volume의 다중 sequence 표현 학습과 시각 encoder–언어모델 공동 적응은 장기 후보로 남긴다. 많은 volume token과 대규모 영상–보고서 학습이 필요할 수 있다. 현재는 단순 sampling·집계 이후의 잔여 필요성이 미확인이므로 이 투자를 발주하지 않는다.

# 계획의 근거 (GPT 조사 노트)

## 확인한 사실

- agent/GOAL.md, MR_RATE_DATA_NOTES.md, iter_120 계획 기록·review.md, iter_062/064/077/083 review.md, LIMITATIONS의 MRI 항목과 CODE_ASSETS 관련 항목을 확인했다. 현재 research의 status와 diff는 깨끗하며 git ls-files로 현재 소스를 확인했다.
- iter_064의 MedGemma 복제 대비 context 손실은 BA 27.08pp였지만 Qwen에서는 같은 저하가 없었다. 기본 신호 기준도 미달했으므로 일반 통합 실패로 계승하지 않는다. iter_077의 영역 판독 MAE 0.777은 분류기 0.776 대비 추가 가치를 확립하지 못했다.
- 공식 guide는 병리 CSV를 findings에서 추출한 binary presence label로 설명한다. 따라서 0을 명시적 임상 음성으로 해석할 수 없다. 보고서는 번역·구조화 과정을 거쳤으며, T1 조영 여부는 현재 명시적으로 라벨링되지 않았다. [공식 자료 안내](https://github.com/forithmus/MR-RATE/blob/main/data-preprocessing/docs/dataset_guide.md)
- 공식 metadata 설정에는 SeriesDescription, ProtocolName, 선택적 diffusion b-value 등이 있다. 실제 행에 값이 존재하거나 정확하다는 보장은 아니다. [공식 metadata 설정](https://github.com/forithmus/MR-RATE/blob/main/data-preprocessing/src/mr_rate_preprocessing/configs/config_metadata_columns.json)
- 공식 MR-RATE 카드의 연구 이용 조건과 자동 라벨·예측 segmentation 설명을 확인했다. 병변 공간 정답으로 사용하지 않는다. [데이터 카드](https://huggingface.co/datasets/Forithmus/MR-RATE/blob/main/README.md)
- MedGemma 공식 카드는 CT/MRI 전처리와 공식 processor 사용을 안내한다. 이번 입력이 공식 MRI 임상 성능 재현이라는 주장은 하지 않는다. [모델 카드](https://huggingface.co/google/medgemma-1.5-4b-it)

## 가까운 대안과 선택

- NeuroVFM은 공개 3D encoder와 study diagnostic head를 제공하지만 가중치 접근 승인과 FlashAttention 의존성이 있다. MR-RATE 접근 승인이 이 모델의 승인까지 뜻하지 않는다. 현재 설치 여부로 배제하지 않으며 label 대응·중복·권한을 후속 투자 전에 확인한다. [공식 구현](https://github.com/MLNeurosurg/neurovfm)
- ReMIND는 다중 sequence MRI와 modality-aware decoding을 다룬다. 논문상 지원과 현재 사용 가능한 checkpoint를 구분해야 한다. 이번 제한된 존재 판단·관측 비교는 보고서 decoding 방법의 재현이 아니다. [원 논문](https://pmc.ncbi.nlm.nih.gov/articles/PMC13060454/)
- 후보는 급성 뇌경색, 수막종, 탈수초 질환으로 한정 비교했다. 급성 뇌경색은 명시적 부재 문구와 DWI–ADC 연결이 성립할 경우 관측 대조를 구체화할 수 있어 조건부 1순위다. 수막종은 T1 조영 구분이 추가 문제이고, 탈수초 질환은 질환 존재와 비특이 신호의 정답 의미가 더 얽힌다. 어느 후보의 적격 수나 성능도 확인한 것으로 쓰지 않는다.

## 남은 자료 조건

계획 환경에서 /home/test/.local/share/medgemma/mr_rate는 존재하지 않았다. 승인 철회나 구현 환경의 접근 실패로 해석하지 않는다. 실제 CSV 값·질환별 환자 수·명시적 음성 수·DWI–ADC 대응은 미확인이다. 다운로드 없는 계획 역할을 유지했고, 이를 구현의 한정 자료 점검과 조건부 추론으로 묶었다. 토큰 내용은 읽거나 출력하지 않았다.
