# 요약

- 이번에 할 일: 실제 반복 촬영 뇌 MRI에서 개별 품질 점수와 직접 비교를 대조한다.
- 필요한 이유: MR-RATE 질병 판별의 약한 정답과 다른 조건에서 관측 선택 능력을 시험할 수 있다.
- 확인할 기준: 전문가 등급이 다른 촬영쌍의 정확도, 순서 일관성, MRIQC 이후의 추가 가치와 비용이다.
- 주의·다음: 원 점수·영상 연결 확인 후 실행한다. 양성 근거가 있을 때만 보존20명으로 한 번 확인하며, 방법 개발은 별도 판단한다.

## 알림 맥락

- 연구: MRI 반복 촬영의 품질 근거 비교
- 데이터: 반복 촬영 T1w 뇌 MRI MR-ART
- 모델: MedGemma 1.5, VLM 학습 없음
- 과제: 같은 사람의 두 MRI 중 품질이 더 좋은 촬영을 선택한다
- 가설: 개별 점수의 보정 문제가 크면 직접 비교에서 판별이 회복될 수 있다
- 질문: MRI를 따로 채점하는 것보다 함께 비교하면 더 좋은 촬영을 안정적으로 고를 수 있는가?
- 변경: 방향 전환
- 연결: MR-RATE 질병 판별 후속 두 후보의 보류를 유지하고, 전문가 품질 점수가 있는 MR-ART로 정답 조건을 바꾼다
- 작업: 자료 연결 검사 후 개별 점수·직접 비교·MRIQC를 평가해 후속 투자 여부를 정한다

# Current Understanding

iter_131은 보류 기록이며 새로운 모델 증거가 아니다. 기존 MR-RATE 고정 응답 관찰은 유지한다. 이번 품질 질문의 observed 한계는 없으므로 limitation_ids는 비워 두고 diagnostic으로 실행한다.

[MR-ART 공식 점수](https://raw.githubusercontent.com/OpenNeuroDatasets/ds004173/main/derivatives/scores.tsv)의 bids_name과 score를 확인했다. [공개 IQM 표](https://raw.githubusercontent.com/brainhack-ch/interpret-iqms/main/data/IQMs.tsv)도 같은 식별자를 사용한다. 전체 연결·결측·실제 영상은 아직 검산하지 않았다. 원 자료는 건강한 성인의 지시된 움직임 촬영이며 일반 임상 재촬영 분포가 아니다.

# Strategy Check / 연구 방향 판단

출처: iter_131 리뷰 카드와 iter_132 think/round_01.json. 새 근거는 공식 점수 위치와 실제 영상 포인터의 확인이다.

1. 중요한 문제: 여러 관측 중 사용할 영상의 선택이다. 이번에는 질병 정확도와 분리한다.
2. 현재 근거: 전문가 품질 등급과 반복 촬영은 외부 자료 사실이다. MedGemma 품질 판별은 미실행이다.
3. 쉬운 해결책: 개별 점수 순위, MRIQC 단일 지표와 학습 분류기다. 충분하면 VLM 방법 투자 가치는 낮다.
4. 남은 설명: 절대 점수 보정, 시각적 손상 인식, 부분 관측, 순서 편향을 구분한다. 직접 비교 이득만으로 내부 원인을 확정하지 않는다.
5. 다음 결정: 실제 비교 후 한정 후속 투자 또는 현재 후보 보류를 선택한다. 같은 기록 정리·prompt 순회는 하지 않는다.

# Hypothesis

H1: 개별 점수 보정이 주요 제약이면 같은 영상을 직접 비교할 때 전문가 순위 일치도가 높아지고 양쪽 순서에서도 선택이 유지된다.

H2: 손상 인식 또는 제공 slice가 부족하면 직접 비교도 낮거나 불안정하다.

H3: 직접 비교 신호가 있어도 MRIQC가 이미 더 정확하면 현재 선택 과제의 새 VLM 방법 필요성은 약하다.

관측 비교의 양성 결과는 상대적인 신호 활용 가능성이다. 질병 인식·해부학 보존·일반 VLM 한계를 증명하지 않는다.

# Limitation Evidence / Correct Usage Checks

기존 mrrate-flair-fixed-positive-response와 mrrate-t2-ventricle-fixed-positive-response는 배경 관찰이며 이번 과제의 방법 진입 근거가 아니다. 기존 사용법 검사의 승인을 MR-ART로 옮기지 않는다.

공식 chat template, 실제 model/processor revision, 이미지 개수·순서, 입력 tensor, greedy 생성, EOS와 출력 길이를 검사한다. 모델에는 익명 A/B와 slice 위치만 제공한다. 원 filename·acq-standard/headmotion·전문가 score·IQM·보고서는 VLM 입력에서 제외한다.

# Contribution Path / Baselines / Reuse

[MMRQA](https://arxiv.org/html/2509.24888v1)의 지표 결합·품질 적응 자체와 구별되는 방법은 아직 없다. [MoMRISim](https://arxiv.org/html/2506.05975v1)의 별도 참고영상 기반 유사도와도 입력 조건이 다르다. 이번에는 동일 시각 정보에서 상대 비교가 드러내는 신호와 단순 대안 이후 가치만 판단한다.

필수 대조:

- 개별 VLM 연속 점수: 각 촬영에 0–100의 motion-related degradation score를 요청한다. 0은 최소 손상, 100은 심한 손상이다. 작은 점수가 좋은 영상이다. 3등급 강제 양자화로 순위 대조를 약화하지 않는다.
- 직접 VLM 비교: 두 촬영에 같은 slice를 제공하고 A/B/TIE/UNKNOWN을 요청한다. A→B와 B→A를 모두 실행한다.
- MRIQC 단일 지표: 낮은 CJV, 낮은 EFC, 높은 SNR_total 순위를 모두 보고한다. 개발60명의 교차검증에서 주대조 하나를 선택한다.
- MRIQC 학습 대조: IQM만 사용하는 L2 multinomial logistic regression과 random forest를 비교한다. 환자별 5-fold CV, seed132로 선택한다. logistic C={0.1,1,10}; forest 300 trees, min_samples_leaf={2,5}, max_features=sqrt. 선택 기준은 환자 평균 비동점쌍 정확도이며 동률이면 logistic을 우선한다. 표준화·결측 대치는 각 학습 fold 내부에서 적합한다. 기대 등급으로 순위를 만든다. 식별자·촬영 조건·점수·개인정보·size/spacing 열은 feature에서 제외한다.

이 학습은 강한 기존 대조를 만드는 작업이며 새 VLM 방법 개발이 아니다. MRIQC는 전체 volume과 별도 supervision을 사용한다. 같은 정보 비교라고 주장하지 않는다. 저장된 IQM의 예측 시간과 실제 IQM 생성 시간을 구분하며 미측정 전처리 비용을 0으로 두지 않는다.

재사용은 SHA 4682b4bacadbaf12cf0f379f41a5a4fb1b9cb983의 mr123_data.py 한 파일이다. normalization_window와 render_slice만 사용한다. MR-RATE의 extract·build_case·고정 경로와 실행기는 호출하지 않는다. 새 BIDS 연결·요청·평가 어댑터를 이번 과제에 맞게 만든다. 반입 파일은 현 기반에 없음을 확인했다.

# Proposed Experiment

## 1. 한정 자료 확인

영상 반입 전에 공식 scores.tsv, dataset_description, 선정에 필요한 파일 목록과 공개 IQM 표만 확보한다. 실제 revision·URL·license·SHA256을 고정한다. 공식 점수와 분석 저장소의 점수 복제본은 전체 bids_name/score로 비교한다. 불일치하면 공식 점수를 기준으로 원인을 확인하고, IQM의 촬영 연결이 불명확한 행은 제외한다. 자동 filename 변환은 규칙과 충돌 검사를 남긴다.

점수1/2/3, 고유 bids_name, subject ID, 촬영별 존재, 전체 IQM join, 결측·중복·동점 수를 기록한다. 기본 적격자는 세 촬영 모두 원 점수·IQM·영상 객체가 연결되는 사람이다. 불완전3촬영의 제외 수를 공개한다. 원 영상은 OpenNeuro의 실제 객체를 선택 반입한다. GitHub의 annex 포인터를 NIfTI로 취급하지 않는다.

여기서 출처 또는 영상 연결이 성립하지 않으면 완성형 실행기·모델 설치 전에 중단한다. 같은 metadata 감사만 다음 반복으로 넘기지 않는다.

## 2. split과 표본

seed132와 subject ID hash로 기술6명, IQM 학습60명, 개발 평가40명, 보존20명을 분리한다. 기술 집단에는 이미 예제로 본 sub-000103을 포함하고 나머지는 hash로 선정한다. 모든 split은 모델 출력 전에 잠근다. 점수 전체를 계획 중 열람했으므로 보존 집단은 미열람 정답 집단이 아니라 모델 출력과 설정 선택에 사용하지 않은 집단이라고 명시한다.

평가40명과 보존20명은 각자 headmotion1/headmotion2 등급의 동점 여부를 가능한 한 1:1로 층화한다. 희소 층은 전수 배정하고 부족분을 다른 층의 hash 순서로 채운다. 정확한 수와 추출 확률을 고정하고 층별 결과를 함께 보고한다. 보존20명은 탐색 단계에서 영상·출력을 열지 않는다.

126명의 완전 연결을 확보하지 못하면 확인된 적격 수와 영향만 보고하고 규모를 임의 재설정하지 않는다. 이는 자료 설계의 한정 실패이며 MRI 능력 실패가 아니다.

## 3. 동작 확인: 기술6명

각 volume을 RAS로 정렬한다. 별도 정합·denoising·bias correction은 하지 않는다. 정렬 후 axial dimension의15–85% 구간에서 등간격8장을 선택한다. 원 volume min–max 정규화와 기존896×896 spacing 보존 렌더링을 사용한다. 상수·비finite·8개 고유 slice 미충족은 기술 오류다. 임의로 보기 좋은 slice를 고르지 않는다.

실제 montage와 원 header를 확인한다. 뇌가 잘못 잘리거나 축이 틀리면 본실행 전에 해당 기술 결함만 수정하고 기술 출력을 새 경로에 남긴다. 품질 정확도를 보고 window나 slice 정책을 고르지 않는다. 전체 volume 점수와8장 관측의 차이는 남는 한계다.

개별3요청, 세 쌍×양쪽 순서6요청으로 사람당9요청이다. max_new_tokens512, greedy, 공식 template을 사용하고 첫 줄의 점수 또는 선택을 뒤의 설명과 분리한다. 유효한 임상 정답률을 기술 진입 gate로 요구하지 않는다. 잘못된 tensor 연결·출력 절단·실행 오류를 해소한 뒤 낮은 정확도라도 평가40명으로 간다. 설명은 새 임상 정답으로 평가하지 않는다.

## 4. 가능성 탐색: 개발40명

학습60명에서 IQM 대조를 선택·잠근 뒤 평가40명의 MedGemma360요청을 실행한다. 세 촬영의 모든3쌍을 사용하며 같은 등급의 쌍도 실행하되 주 방향 평가에서는 분리한다. 두 VLM 조건에는 byte가 같은 PNG를 제공한다.

주 metric은 전문가 비동점쌍의 환자 평균 pair accuracy다. 정답 선택1, 반대0, 명시적 TIE0.5, UNKNOWN·invalid0으로 고정한다. 개별 점수도 동일값이면0.5, 하나라도 invalid이면0이다. 직접 비교는 두 순서의 점수를 평균한다. 환자마다 적격 쌍을 평균한 뒤 환자를 같은 가중치로 평균한다. 비동점쌍이 없는 사람은 주 metric 분모에서 제외하되 수와 전체 출력은 보존한다.

보조로 TIE를0으로 둔 strict accuracy, 두 순서 모두 정답인 비율, 원 촬영으로 매핑한 순서 일관성, invalid/UNKNOWN, 등급 차이1/2별 결과, headmotion1/headmotion2 쌍 결과를 보고한다. 동점 등급은 세밀한 동등성 정답이 아니므로 TIE 미출력을 자동 오류로 만들지 않는다.

## 5. 규모 확대와 독립 확인

개발40명에서 직접 비교가 개별 점수보다10pp 이상, 선택된 최강 IQM 대조보다5pp 이상 높고, 순서 일관성90% 이상, invalid+UNKNOWN5% 이하이면 보존20명으로 한 번 확인한다. 두 이득의95% CI가 모두0을 넘으면 양성 탐색, 점추정치는 기준을 넘지만 CI가0을 포함하면 정밀도 보완으로 구분한다. 두 경우 모두 같은 보존20명만 사용한다.

점추정치가 이 기준에 못 미치면 자동 확대하지 않는다. 특히 직접 비교가 자체 대조만 이기고 IQM을 못 이기면 상대 신호 관찰은 보존하되 실용 방법 투자를 보류한다. 보존 집단에서는 prompt·baseline·checkpoint·전처리 변경 없이180요청을 실행한다. 보존 결과와 개발 결과는 따로 보고하며 자동 합산 CI를 확증으로 쓰지 않는다.

타 모델과 VLM 적응은 이번 범위에 없다. 양성 결과 후 일반성 확인과 필요한 직접 SFT를 포함한 다음 투자 판단을 별도로 한다.

## 6. 자원·비용·재개

선택 자료는 승인된 외부 저장 루트 아래 mr_art 하위 폴더에 분리하고 소스는 research/에 둔다. metadata250MB·영상10GiB의 기존 안전 예산 안에서 시작한다. 11.09MB인 대표1volume은 전체 평균이 아니므로 선정 객체의 실제 byte 합계와 압축 해제·PNG 공간을 반입 전에 계산한다. 전량 다운로드는 없다.

GPU 실행 직전 nvidia-smi와 상속된 CUDA_VISIBLE_DEVICES를 확인한다. 우선 두 GPU에 독립 worker를 배정한다. 기술 입력으로 batch1 대비 batch2를 먼저 비교하고, batch가 불리하고 메모리가 허용되면 GPU당2worker를 비교한다. 모델8–10GB는 참고치이며16영상 공동 요청의 실제 peak, KV cache, 다른 점유와 worker당2GB 여유를 포함한다. 여유가 큰 허용 GPU부터 배치한다.

기술 입력에서 요청 유형별 처리량·p95 latency·peak VRAM·OOM·CPU/I/O 경합을 측정한다. 동일 출력과 누락 없는 구성 중 전체 완료 시간이 짧은 구성을 고른다. GPU당1worker 유지 시 실측 이유를 남긴다.

기본 workload는 기술54+개발360=414요청, 조건부180요청이다. 처리량 시험·회귀 요청은 별도 ledger에 남긴다. 예상 시간은 기술 실측의 개별/공동 처리시간, 실제 병렬 처리량, 다운로드·렌더링 비용으로 본실행 전에 산출한다. 현재 wall-clock과 새 입력의 peak는 미측정이며 임의 시간 상한을 두지 않는다.

고유 request ID, 원자적 claim, worker별 출력, config/model/input hash, EOS/token count를 저장한다. 일부 완료 후 재개해 중복·누락·변조 거부를 기술 단계에서 확인한다. 학습 checkpoint 대신 IQM pipeline·split·선택 설정과 추론 완료 ledger를 보존한다.

# Implementation Tasks for Claude

현재 담당 Codex가 standard 등급으로 수행한다.

1. 원 점수·IQM·영상 객체 연결과 용량을 확인하고 조건 성립 여부를 먼저 보고한다.
2. split·선정·제외·출처 manifest와 고정 prompt/parser를 모델 출력 전에 보존한다.
3. 반입 렌더러의 승인 범위를 지키는 MR-ART 어댑터를 구현한다. 기존 MR-RATE 경로는 호출하지 않는다.
4. 환자 분리 IQM 대조를 적합하고 선택 결과를 봉인한다.
5. 기술 검사와 두 GPU 처리량 비교 후 개발40명을 평가한다. 정해진 조건일 때만 보존20명을 실행한다.
6. 원 출력부터 독립 평가 스크립트로 분모·정오·CI를 검산한다. 원 출력·분석·비용·미실행 항목을 results/iter_132에 남긴다.
7. 소스 보존은 orchestrator checkpoint 절차를 따른다. 과거 결과·분기·공통 정책을 수정하지 않는다.

# Evaluation (성공/실패 기준 포함)

환자 bootstrap10,000회·seed132로 직접−개별과 직접−IQM 차이의95% CI를 계산한다. 반복 촬영과 순서 출력은 독립 표본으로 세지 않는다. 층화 추출을 반영하고 모든 동점 처리·분모를 명시한다.

- 양성: 개발의 사전 효과·안정성 기준을 충족하고 보존에서도 두 이득의 방향과 크기 기준이 유지된다. 보존 CI가0을 포함하면 제한적 재현 관찰로만 보고한다. 다음은 타 모델·직접 적응 대조를 포함한 한정 후속 투자 검토다. 새 contribution 또는 method full 승인은 아니다.
- 음성: 유효 실행에서 직접 비교가 회복되지 않거나 IQM 이후 가치가 없다. 현재 frozen 비교 후보를 보류한다. 낮은 판별력을 MRI 전체의 실패로 해석하지 않는다.
- 불확정: 보존20명 후 CI·사건 수·순서 불안정·관측 범위 때문에 판단이 남는다. 원 관찰을 보존하고 추가 확대를 종료한다. 새 정보 없이 같은 자료 조건을 순회하지 않는다.
- 실행 실패: 정답 provenance·영상 연결·누수·tensor 오류로 비교가 무효다. 가능한 한 영향받은 경로만 복구하되 정답을 추측하거나 약한 대조로 교체하지 않는다.

5pp의 실용 이득과10pp의 개별 대비 이득은 이번 탐색 투자 기준이며 임상 유용성의 보편적 문턱이 아니다. 비용은 동일 환자의 세 촬영 순위를 얻는 전체 workload로 비교한다. 직접 양순서 비교는 영상 token 노출이 개별 평가보다 많으므로 동일 연산 예산의 우위라고 주장하지 않는다. IQM 생성 비용을 확보하지 못하면 비용 우월성은 미판정으로 둔다.

# Risks / Checks

- 공개 전문가 score는 전체 촬영의 거친 등급이다. slice별 손상 위치나 동점 내 세밀한 선호를 만들지 않는다.
- 건강한 성인·지시된 움직임·T1w·defacing 조건이다. 임상 재촬영과 다른 sequence로 일반화하지 않는다.
- 전체 점수 표 열람과 사전학습 노출 가능성을 기록한다. 환자 분리는 이번 baseline 학습 누수만 통제한다.
- MRIQC 분석 예제의 전역 표준화·영상 단위 분할을 그대로 복제하지 않는다. 모든 학습 변환과 CV는 환자 분리한다.
- 두 조건이 같은 부분 관측을 사용해도 전체 volume 품질 정답의 가시성을 보장하지 않는다. 양쪽 실패의 원인을 손상 인식으로 단정하지 않는다.
- 원천 자료 이용 조건, 실제 Python 경로·package 버전·모델 revision을 기록한다. 필요한 설치는 격리 환경에서 하고 hf_cache는 수정하지 않는다.
- 설명 문장의 타당성을 LLM 합의로 임상 검증하지 않는다. 논문 추천은 실제 유효 결과를 본 뒤 판단한다.

## 대규모 GPU 필요 후보

다양한 실제 획득 조건의3D 표현과 품질·소견 보존을 공동 적응하는 방향은 장기 후보로 남긴다. 이번 비교로 필요성을 입증한 것은 아니며 현재 두 GPU에서 가능한 경량 적응을 금지하는 근거로 쓰지 않는다.

# 계획의 근거 (GPT 조사 노트)

## 새로 확인한 것

직전 조사 원문 `agent/runs/iter_132/think/round_01.json`, 최종 GOAL, iter_131 원 리뷰를 읽었다. 이전 후보의 보류와 MRI 전체 미기각 판단을 유지한다.

1. [공식 scores.tsv](https://raw.githubusercontent.com/OpenNeuroDatasets/ds004173/main/derivatives/scores.tsv)를 찾았다. header는 `bids_name, score`이며 웹 표시는 header 포함437줄이다. 루트 경로404는 파일 부재가 아니라 위치 추정 오류였다. 동일인 내 동점과 촬영 지시와 반대인 점수가 실제로 존재한다. 예를 들어 sub-012059의 headmotion1/2 점수는3/2다. 전체 파일의 중복·결측·환자 수와 복제본 일치는 아직 기계 검산하지 않았다.
2. [MRIQC 분석 저장소의 IQMs.tsv](https://raw.githubusercontent.com/brainhack-ch/interpret-iqms/main/data/IQMs.tsv)는 같은 bids_name과 cjv·cnr·efc·snr 등의 수치 열을 제공한다. [점수 복제본](https://raw.githubusercontent.com/brainhack-ch/interpret-iqms/main/data/scores.tsv)도 확인했다. 구현에서는 공식 점수와 전체 key/value 일치를 검산해야 한다. 공식 derivatives의 IQM 추정 경로는 조회 실패했으므로 공식 원본이라고 부르지 않는다.
3. [대표 영상 경로](https://raw.githubusercontent.com/OpenNeuroDatasets/ds004173/main/sub-000103/anat/sub-000103_acq-standard_T1w.nii.gz)는 실제 영상이 아니라 git-annex 포인터다. 포인터에는 크기11,088,525 bytes와 MD5 식별자가 있다. 따라서 raw GitHub 응답을 NIfTI로 저장하면 안 된다. 모든 선정 영상의 크기·객체 연결·실제 다운로드는 구현에서 확인한다.

## 남은 질문에 대한 답

- 평가 단위는 환자다. 전문가 등급이 다른 촬영쌍에 대해서만 방향 정답을 구성한다. 같은 등급은 세밀한 품질 동등성을 보장하지 않으므로 주 방향 정확도에서 제외하고 별도 보고한다. 촬영 지시나 파일명을 정답으로 사용하지 않는다.
- 남은 기술 질문은 동일 시각 정보의 개별 점수와 직접 비교 사이에 순서에 안정적인 정보 차이가 있는지다. MRIQC 이후의 실용 가치가 없으면 방법 개발을 보류한다.
- 원 파일 위치와 대표 영상 식별자가 확인됐으므로 한정 자료 연결 검사와 실제 GPU 비교를 같은 계획으로 묶는다. 전체 연결 성공을 이미 확인했다고 표현하지 않는다.

## 선행과 구별할 범위

[MMRQA](https://arxiv.org/html/2509.24888v1)는 MRQy·QA 변환·LoRA를 결합한다. 해당 원문의 공개 코드 링크 검색에서 재현용 checkpoint를 확인하지 못했다. 비공개라고 단정하지 않으며 이번에는 해당 방법을 재현했다고 주장하지 않는다.

[MoMRISim 논문](https://arxiv.org/html/2506.05975v1)은 참고영상과의 유사도 및 reference-free VLM 평가의 한계를 다룬다. 본 계획에는 별도 깨끗한 정답 참고영상이나 재구성 알고리즘이 없다. 전문가 등급 순위를 해부학 보존의 정답으로 확대하지 않는다.

[공식 MedGemma 카드](https://huggingface.co/google/medgemma-1.5-4b-it)의 다중 영상 입력 조건과896 해상도를 확인했다. 카드도 과제 적응 필요성을 명시하므로 frozen 진단 실패는 모델의 적응 불가능성을 뜻하지 않는다.

## 코드 확인

현재 HEAD는 ee8078ab0acba94f0d84d3ab2997e76eeb117bb9다. 현재 파일 목록, CODE_ASSETS의 iter_129, 원 review.json/code_assets, 실제 보존 mr123_data.py를 확인했다. 해당 파일은 외부 Python package 외 로컬 import가 없으며 render_slice·normalization_window만 새 어댑터에서 사용한다. 기존 실행기는 고정 MR-RATE 계약 때문에 반입하지 않는다. 이는 소실 자산의 대체 구현이 아니라 새로운 과제의 입력·요청·평가 어댑터다.

## 한계

원 영상은 이번 계획 단계에서 열지 않았다. 표본 적격 수, IQM provenance와 영상 다운로드 성공은 조건부다. 이 한정 검사가 실패하면 모델 실패로 집계하지 않는다. 코드 수정·파일 생성·다운로드·모델 실행은 하지 않았다.

이전 사고 라운드 노트: agent/runs/iter_132/think/
