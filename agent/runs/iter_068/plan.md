# 요약

- **이번에 할 일:** SPIDER D/E12 저장 점수에서 순위 신호와 D 고정 보정의 성능을 한정 재분석한다.
- **필요한 이유:** 네 후보 argmax는 실패했지만 p(C)의 사후 순위가 보고됐다. 실제 판별 정보와 환자·위치·영상 수의 상관을 구분해야 한다.
- **확인할 기준:** 고정 S1의 교란 점검 후 순위, 환자별 안정성, D에서 선택한 단순 threshold의 E12 성능을 함께 본다.
- **주의·다음:** 신규 추론·학습·E 확대·F139 사용은 없다. 원 판정은 유지하며, 불확정이면 같은 자료의 추가 보정 탐색을 종료한다.

# Current Understanding

기준 문서는 `agent/runs/iter_067/plan.md`이며 SHA256은 `6d5ab65ba3630cd8c9241d05a1962f0445e969e0b138cdf251332a4b36d0f888`이다. 원본 가설·표본·BA02·확대 gate와 abandon 판정은 변경하지 않는다. 이번은 원 실험의 복구나 확대가 아니라 리뷰가 요청한 사후 분석이다.

유지할 것은 기존 D/E12 사례, GT, 후보 매핑 A=0/B=I/C=II/D=III, 저장 logits와 입력 조건이다. 변경할 것은 새 결과 경로의 순위·교란·보정 분석뿐이다. 미완료인 E 전체·독립 확인·정상 사용 범위 확대는 실행하지 않는다.

D는 7명·51 IVD이며 II 9행은 세 환자에 집중된다. E12는 12명·81 IVD, 0=53·II=28이다. 원 네 후보 BA02는 MedGemma J 0.09434, Qwen 영상 조건 0.5로 확대 기준에 미달했다. p(C)의 행 단위 AUROC는 사후 관찰이며 시각 신호의 증명이 아니다.

# Strategy Check / 연구 방향 판단

상위 질문은 여러 관측의 근거를 선택·결합하는 능력이다. 이번까지 확인한 것은 frozen 임상 등급 인터페이스의 낮은 정확도이며 충분한 인식 이후의 선택·결합 실패는 아니다.

남은 설명은 답변 편향 때문에 판별 순위가 답변으로 연결되지 않는 경우와, 환자·ordinal·영상 수만으로 순위가 생기는 경우다. 최소 비교는 기존 점수의 조건부 순위와 D 고정 threshold다. 이번 결과가 바꿀 결정은 현재 Modic 답변 보정에 후속 투자를 검토할 가치가 있는지 하나다.

즉시 적응은 데이터와 강한 baseline 비용이 들지만 현재 이용 가능한 신호가 불명확하다. 다른 자료 전환은 같은 질문의 불확실성을 해소하지 못한다. 저장 출력 재분석은 새 추론 없이 경쟁 설명을 좁힐 수 있어 우선한다. 두 계열 비교는 이미 있으므로 새 모델을 추가하지 않는다.

iter_056~067의 관찰과 종료 범위를 이어받는다. 이번 지배 비용은 평가 구현·검증이다. 원 분석의 순위가 환자 의존성 또는 조건부 비교 희소성으로 설명되면 Modic 보정을 보류한다. 후속 진단을 자동 발주하지 않는다.

# Hypothesis

H1: p(C)의 판별 순위가 ordinal·영상 수 설명을 점검한 뒤에도 남고, D에서 고정한 threshold가 E12의 제한된 이진 판별에 연결된다.

H0: 순위가 환자 구성·위치·영상 수에 의존하거나, D에서 고정한 보정이 E12로 연결되지 않는다.

어느 결과도 원래 네 class 과제의 일반적인 인식 능력, 내부 원인 또는 다중 sequence 결합 능력을 확정하지 않는다.

# Limitation Evidence / Correct Usage Checks

이번 Modic 관찰은 iter_067의 valid_experiment=true, blocking_issues=[]인 리뷰에 근거한다. 별도 한계 id는 등록되지 않았으므로 limitation_ids는 비운다. 기존 `mri-explicit-target-context-effect`는 다른 MSD 조건의 observed 주장으로 유지하며 이 분석의 method gate 근거로 사용하지 않는다.

재사용 검증은 원 리뷰의 E12 logits→softmax 오차 9e-8 미만, ID/CSV 연결, 입력 PNG hash 검증을 참조한다. D는 이번 평가에서 요청·정답·출력 연결을 확인한다. 모든 결과에 batch1·vision chunk8의 저장 출력 분석이라는 범위를 명시한다. patch 없는 공식 경로 동등성이 추가로 입증됐다고 쓰지 않는다.

# Contribution Path / Baselines / Reuse

새로운 기여는 아직 없다. threshold 보정과 위치 prior는 강한 단순 대안으로 취급한다. 이 대안이 충분하면 새 방법 투자를 종료한다. 전문 Modic classifier와 직접 SFT의 부족함은 이번에 검증하지 않는다.

현재 브랜치와 HEAD `acacfe155024c3673e8af606a723d1dd1a2df358`을 유지한다. 필요한 소스가 현재 브랜치에 있으므로 선별 반입은 없다. `sp67_eval.py`의 BA02·환자 집계, `sp67_verify.py`의 softmax·tie-aware AUROC, `sp67_select.py`의 D 선택 규칙을 재사용한다. 모든 모듈이 needs_fix임을 유지하며 분석에 필요한 함수만 검증한다. 모델 실행기 import 때문에 불필요한 GPU 의존성이 생기면 순수 산술 함수를 최소 분리하되 원 소스와 회귀 검사를 연결한다.

이번 필수 수정은 새 평가 진입점의 provenance, 엄격한 JSONL 검증, D 선택 재계산, 비교별 동일 행 집합이다. 기하 gate, worker 재개, R/LF timing, chunk 검증은 실행하지 않는 경로이므로 이번에 정비하지 않는다. 환자 35를 다시 포함하거나 기존 제외 사유를 물리적 불일치로 확정하지 않는다.

# Proposed Experiment

## 1. 동작 확인과 분석 고정

입력은 `results/iter_067/data/{pairs_D.json,pairs_E12.json,requests_D.jsonl,requests_E12.jsonl,protocol_D_v2.json,protocol_E12.json,select_D.json}` 및 `gen_D/{medgemma,qwen}/worker*.jsonl`, `gen_E12/{medgemma,qwen}/worker*.jsonl`이다. protocol_D.json과 v2를 임의 혼용하지 않는다. 각 record의 digest와 실제 사용 요청을 대조한다.

분석 코드를 실행하기 전에 새 설정에 점수 정의·주조건·보조 조건·threshold 규칙·bootstrap seed·결정 기준을 저장한다. 이는 이미 E12를 본 뒤 고정하는 사후 분석 규약이며 사전등록 또는 독립 확인으로 부르지 않는다.

D/E의 환자 분리, 요청별 출력 1개, 전체 요청 집합 일치, 후보 순서·유한 logits·확률 합, patient/ivd/cond/n_images 연결을 검사한다. LF는 기존 S1/S2 후보 확률의 0.5 평균으로 재계산한다. 원 BA02와 D 선택 B=t1을 재현한다. 원본 파일을 새 분석으로 덮어쓰지 않는다.

## 2. 고정 순위 분석

두 모델 각각 주조건은 원 D에서 선택된 S1이다. 점수는 네 후보 softmax의 p(C) 하나로 고정한다. logit 차이·확률 비율·점수 반전 중 유리한 것을 탐색하지 않는다. 보조 조건은 S2, J, RT1, LF, T이며 모두 보고하되 S1 실패를 보조 조건으로 대체해 통과시키지 않는다.

주분석은 전체 E12의 p(C) AUROC와 95% 환자 cluster bootstrap CI다. 높은 점수가 II를 뜻하도록 방향을 고정하고 tie는 0.5로 처리한다. 10,000회·seed68로 환자 전체 행을 함께 재표집한다. 두 모델·모든 비교에서 같은 환자 재표집을 사용한다. 단일 class replicate의 수를 보고하며 유효 replicate만으로 CI를 계산한다.

환자 구성에 대한 민감도는 두 가지로 확인한다. 첫째, 0/II가 함께 있는 환자 안에서 AUROC를 구하고 환자별 값을 동일 가중 평균한다. 기여 환자·행·양음성 pair 수와 미산출 환자를 보고한다. 둘째, 원래 E12의 각 환자를 한 번씩 제외한 AUROC 범위를 보고한다. 이를 독립 재현으로 세지 않는다.

위치 대조는 같은 ordinal이며 서로 다른 환자인 양음성 pair만 비교한 AUROC로 고정한다. 기여 ordinal과 환자 수를 보고한다. 비교 가능한 pair가 없는 범위는 NA이며 다른 ordinal로 합치는 규칙을 사후 추가하지 않는다. 이 지표와 전체 AUROC의 모집단이 다름을 명시한다.

## 3. 영상 수·ordinal 대조

각 행의 n1/n2는 S1/S2 요청의 실제 영상 수로 정의한다. p(C)를 logit으로 변환한 값 s=log(p/(1-p))를 분석하며 수치 안정화 clipping은 1e-8로 고정한다. 이 변환은 새로운 점수 선택이 아니라 같은 순위의 회귀용 표현이다.

D에서만 s를 ordinal one-hot과 n1/n2로 회귀한다. 연속 변수는 D 평균·표준편차로 표준화하고 표준편차 0이면 해당 열을 0으로 둔다. ordinal 범주는 기존 주석 schema의 1~9로 고정한다. 절편은 비벌점, 나머지 계수는 평균 제곱오차+계수 제곱합의 ridge 계수 1을 사용한다. label은 이 회귀에 넣지 않는다. 튜닝하지 않는다.

D에서 얻은 회귀를 E12에 적용해 잔차 s-residual의 AUROC를 계산한다. 회귀가 예측한 nuisance 점수의 AUROC도 함께 보고한다. 원 점수·잔차·nuisance의 비교에 같은 bootstrap을 사용한다. D에서 관측하지 못한 ordinal 및 D 영상 수 범위 밖 E 행을 표시하고, 해당 행을 제외한 결과도 정해진 민감도 분석으로 보고한다. 지지가 없거나 제외 후 두 class가 사라지면 통제 충분성을 주장하지 않는다.

이 잔차화는 제한된 선형 설명의 점검이며 모든 교란을 제거하거나 순수 영상 신호를 식별하지 않는다. 같은 환자 내 순위는 환자별 영상 수를 통제하지만 ordinal은 통제하지 않으므로 두 분석을 함께 해석한다.

T는 J 문구에만 대응한다. J와 T의 p(C) 및 J의 잔차화 결과를 보조 비교한다. S1−T를 완전한 영상 제거 효과로 해석하지 않는다. J−RT1, J−LF는 관측 수·복제·단순 집계에 대한 보조 결과이며 결합 능력 지표가 아니다.

## 4. D 고정 단순 보정

각 모델의 S1 p(C)에 대해 D의 실제 0/II 행에서 BA를 최대화하는 threshold 하나를 선택한다. 후보는 서로 다른 D 점수 사이 중점과 양 끝의 상수 예측점이다. p(C)>=threshold이면 II, 아니면 0으로 한다. 동률이면 가장 큰 threshold를 선택한다. E12를 읽어 threshold를 조정하지 않는다.

같은 규칙으로 T의 threshold를 D에서 정한다. D global 및 ordinal별 II prevalence도 계산한다. ordinal prevalence는 (II 수+1)/(0/II 수+2), 미관측 ordinal은 같은 방식의 global prevalence를 사용한다. prevalence의 threshold도 동일 D 규칙으로 정한다. 이 단순 대조들을 E12에 그대로 적용한다.

E12에서 BA, 두 class recall, confusion, baseline 대비 paired BA 차이와 환자 bootstrap CI를 보고한다. 원 네 후보 argmax BA02는 별도 표에 그대로 둔다. 새 이진 예측은 실제 class support를 0/II로 제한한 진단이며 원 네 class 과제의 성능 회복 또는 배치 가능한 전체 Modic 분류기로 보고하지 않는다.

D threshold의 안정성은 D 환자를 하나씩 제외해 재선택한 threshold 범위와 고정 E12 예측 변경 비율로만 보고한다. 이 중 좋은 threshold를 선택하거나 평균하지 않는다. D fit 불확실성을 반영한 추가 표시는 D/E 환자를 독립 재표집하고 D threshold를 다시 맞추는 10,000회 nested bootstrap으로 고정한다. class 소실 횟수와 유효 횟수를 남긴다.

## 5. 규모·비용·종료

동작 확인 뒤 기존 D/E12 전체를 한 번 분석한다. 별도 가능성 표본을 더 뽑지 않는다. 이미 출력이 존재하고 추가 forward 비용이 없기 때문이다. 이번 본분석 규모는 D 7명·51 IVD와 E12 12명·81 IVD, 두 모델이다. 추가 E 확대와 독립 확인은 수행하지 않는다.

CPU만 사용하는 이유는 현재 투자 blocker가 저장 순위의 교란과 D 보정의 전이 여부이기 때문이다. 동일 출력을 다시 생성해도 이 불확실성은 해소되지 않는다. GPU worker/batch 비교는 이번 작업에 해당하지 않는다. 미래 GPU 진입은 별도 리뷰·계획에서 중요한 잔여 문제, 비교군, method gate를 확인한 뒤 결정한다.

정확한 wall-clock 실측은 없다. 작은 테이블 분석이지만 10,000회 반복의 구현 비용은 첫 100회 실측으로 환산한다. 모델별 분석은 CPU 병렬화할 수 있으나 중복 bootstrap과 출력 충돌을 피한다. 분석 단계별 입력 hash·설정·완료 결과를 원자적으로 저장해 중단 시 검증된 단계만 재사용한다.

# Implementation Tasks for Claude

1. 현재 SHA와 관련 needs_fix 범위를 확인하고 기존 분석 산술을 최소 재사용한다.
2. `results/iter_068/`에 입력 manifest, 고정 analysis config, D fit 결과, 순위/보정 결과, 검증 기록을 저장한다.
3. 새 분석 진입점은 현재 코드·설정·D 선택·원시 결과 hash를 연결한다. 기존 protocol이 연결하지 않은 항목을 과거부터 봉인됐다고 주장하지 않는다.
4. 원 BA02·D 선택을 재현하고 새 AUROC·조건부 pair 계산·threshold 선택을 구현한다.
5. 환자 bootstrap과 고정 민감도 분석을 수행한다. E12 결과로 점수·조건·회귀 계수·threshold 규칙을 바꾸지 않는다.
6. 별도 계산으로 원 주수치와 새 primary AUROC·BA를 대조한다. 보고서에 원 판정, 사후 관찰, 새 투자 결정과 제한을 분리한다.

# Evaluation (성공/실패 기준 포함)

이번 기준은 제한된 후속 투자 후보의 선별 기준이다. 원 iter_067 gate를 대체하지 않으며 독립 확증 기준도 아니다.

**후속 투자 검토 후보:** 한 모델의 고정 S1에서 전체 및 잔차 AUROC가 각각 0.70 이상이고 잔차 AUROC의 95% cluster CI 하한이 0.5보다 커야 한다. 같은 환자 내 및 같은 ordinal 대조의 점추정 방향도 0.5보다 높아야 한다. 필요한 대조가 NA이거나 D support 밖 결과에 의존하면 통제 미확정으로 분류한다. D 고정 threshold의 E12 BA는 0.65 이상, 각 recall은 0.60 이상이며 global/ordinal prior 및 T 보정 각각보다 5 pp 이상 높아야 한다. 이 값은 이번 제한된 이진 후보의 최소 후속 검토 폭이며 임상 유용성 기준이 아니다. 환자 제외·D threshold 불안정성과 nested CI가 강한 반대 근거를 보이면 자동 통과시키지 않고 불확정으로 둔다.

위 조건을 충족해도 새로운 방법은 승인하지 않는다. 단순 threshold가 현재 목적에 충분하면 baseline을 보존하고 새 보정 방법 투자를 종료한다. 잔여 문제가 중요하고 다른 자료·직접 SFT·전문 대안과 구별할 가설이 구체화될 때만 별도 method pilot을 검토한다. 이번 한정 이진 과제로 원 네 class 실용 가치를 대신하지 않는다.

**음성:** 고정 S1의 통제 후 순위가 약하거나 보정이 단순 대조를 넘지 못하면 현재 Modic 답변 보정 투자를 종료한다. 보조 조건 하나의 좋은 값으로 primary를 교체하지 않는다. 영상 정보 전체가 없다고 일반화하지 않는다.

**불확정:** 조건부 비교 희소성, 넓은 환자 CI, D의 세 양성 환자에 대한 threshold 의존성, 순위와 보정의 충돌이 남으면 현재 경로를 보류한다. 같은 자료의 다른 변환·threshold·prompt·모델을 추가하지 않는다.

**기술 오류:** 누락·중복·label 연결·수치 계산 결함은 execution failure로 구분한다. 저장 원본만으로 복구 가능하면 동일 분석 규칙에서 수정한다. 신규 추론이 필요하면 이번 범위를 종료하고 blocker를 보고한다.

# Risks / Checks

- p(C) 관찰 이후 설계한 사후 분석이다. E12는 개발 자료이며 선택 편향과 다중 비교 가능성을 명시한다.
- D의 II는 세 환자에 집중된다. IVD 51개를 독립 학습 표본 51개로 해석하지 않는다.
- 이진 threshold는 네 후보 과제를 변경한다. 원 BA02와 단순히 비교해 전체 Modic 성능 개선을 주장하지 않는다.
- 잔차화는 지정한 선형 설명만 점검한다. 미측정 환자·기관·영상 획득 교란과 임상적 충분성은 미확인이다.
- 고정 조건부 분석의 pair coverage·환자 수·class 소실을 모두 보고한다. 희소한 대조를 통과한 것으로 처리하지 않는다.
- 실제 평가 진입점에서 label/선택/record 변조, duplicate/missing ID, 비유한 logits와 후보 순서 불일치를 거부하는 검사를 수행한다. AUROC tie·상수 점수·단일 class, threshold 동률, bootstrap의 환자 전체 복제도 검사한다.
- 원 자료·결과·protocol은 보존한다. F139, 나머지 E, hf_cache, 기존 환경을 변경하지 않는다.
- 비용 측정 결함이 남은 기존 timing으로 새로운 비용 우위를 주장하지 않는다.

## 대규모 GPU 필요 후보

국소 신호와 임상 등급을 연결하는 MRI volume–text 사전학습은 장기 후보로 유지한다. 현재 저장 출력의 판별 정보와 단순 대안 이후의 잔여 가치가 미확정이므로 이번에는 투자하지 않는다. 두 RTX 3090에서 가능한 경량 적응 전체를 기각하는 뜻은 아니다.

# 계획의 근거 (GPT 조사 노트)

원문 `agent/GOAL.md`, `agent/runs/iter_067/{plan.md,review.md,review.json,claude_report.md}`, `agent/INDEX.md`, `agent/CODE_ASSETS.md`, `agent/LIMITATIONS.md`의 관련 항목과 현재 소스를 확인했다. 현재 research HEAD는 `acacfe155024c3673e8af606a723d1dd1a2df358`이며 작업 트리는 깨끗하다.

iter_067 리뷰는 실제 비교를 유효하다고 판단했지만 두 모델의 확대를 종료했다. E12는 12명·81 IVD이며 MedGemma J BA02=0.09434, Qwen 영상 조건 BA02=0.5다. 보고된 p(C) AUROC 0.56–0.77은 행 단위 사후 분석으로, 환자·ordinal·영상 수 통제가 없다.

저장 record에 cand_logits, cand_probs, patient, ivd, cond, n_images 및 protocol_digest가 있어 신규 추론 없이 분석할 수 있다. D 선택 파일은 두 모델 모두 B=t1을 지정한다. 따라서 E에서 높은 AUROC를 보인 조건을 다시 고르지 않고 S1을 주조건으로 고정한다. D 정답을 확인하면 II 9행이 세 환자에 집중돼 있어 threshold 안정성과 환자 의존성 점검이 필요하다.

`sp67_run.py`의 T는 J와 같은 문구에 영상을 제거한다. S1/S2와 완전히 대응하는 text-only가 아니므로 모든 singleton의 순수 영상 기여를 식별할 수 없다. `sp67_eval.py`의 null은 donor가 없는 행을 제외하면서 실제 성능은 전체 행에서 계산한다. 새 분석은 동일 평가 행 집합을 사용해야 한다.

관련 모듈은 모두 needs_fix다. 이번에는 기존 출력과 검증된 산술만 사용하며 실행기·렌더·기하 gate를 재실행하지 않는다. 실제 사용 경로인 평가 입력 연결, D 선택 재계산, 중복·누락 거부 및 새 분석 봉인만 보완한다. 원래 기하·chunk 동등성·동시 재개 문제는 미해결 상태로 보존한다. 신규 문헌 주장이나 모델 선택이 필요한 계획이 아니므로 광범위한 문헌 재조사는 하지 않았다.
