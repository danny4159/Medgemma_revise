# 요약

- 이번에 할 일: 공식 자료 연결과 저장 출력의 thought/final 구조를 한 번 확인한다.
- 필요한 이유: iter_134는 생성은 완료됐지만 자료·기술 gate가 미충족이었고, 첫 줄과 설명도 어긋났다.
- 확인할 기준: 이용 근거·개별 release 연결·환자 중복 확인 범위와 출력 구조를 각각 증거로 구분한다.
- 주의·다음: 기존 출력의 재채점과 GPU 재실행은 하지 않는다. 후속 비교의 구체적 계약 또는 현재 설계 보류로 끝낸다.

## 알림 맥락
- 연구: MRI 관측 추가와 근거 통합
- 데이터: RadGenome–BraTS 뇌종양 FLAIR MRI의 기존 자료·출력
- 모델: MedGemma 1.5, 신규 추론·학습 없음
- 과제: 기존 영상·정답 연결과 생성 응답의 구조를 확인한다
- 가설: 첫 줄 실패에는 답변 인터페이스와 실제 판별 부족이 함께 있을 수 있다
- 질문: 이 자료와 출력 형식으로 관측·통합 효과를 유효하게 비교할 수 있는가?
- 변경: 실행 복구
- 연결: iter_134의 자료 gate 미완료와 첫 줄·설명 불일치 때문에 확대 전에 비교의 성립 여부를 확인한다
- 작업: 공식 연결 증거와 출력 계약을 확인하고 후속 비교 제안 또는 현재 설계 보류를 결정한다

# Current Understanding

기준은 `agent/runs/iter_134/plan.md`, SHA256 `7251f04a3a36b83b0aeaffed02c4bae1037235f31af465d1ed4bb1ef3710c544`와 원 review.json이다. 이는 원 실험을 통과시키는 amendment가 아니라 후속 가능성을 판단하는 setup이다.

유지: 원 표본·prompt·strict metric·수치·execution_failed 판정, observed 한계의 범위, 코드와 원시 출력.

변경: 신규 생성 대신 자료 연결과 출력 구조의 한정 확인을 수행한다. 신규 독립 환자라는 주장을 전제하지 않는다.

미완료: 공식 이용 근거, 개별 release 연결, MSD 개발 집단과의 관계, 사전 출력 계약을 지킨 실제 비교.

회귀 확인: 기존 파일 hash와 strict 집계가 변하지 않았는지 확인한다. 기존 결과 파일이나 review를 수정하지 않는다.

# Strategy Check / 연구 방향 판단

1. 중요한 문제: 관측 누락과 제공된 근거의 활용 실패를 분리해야 다음 방법 투자에 의미가 있다.
2. 현재 근거: iter_134 원 리뷰를 계승한다. 추가 확인은 NONE 대표 원문의 final UNKNOWN과 영상 조건의 명시적인 첫 줄·설명 불일치다. 새로운 임상 판별 성능은 확인하지 않았다.
3. 쉬운 해결책: 응답의 final 경계를 정상적으로 읽으면 NONE 형식 문제 일부를 설명할 수 있다. 그러나 영상 조건의 모순과 자료 연결은 별개다.
4. 남은 설명: 출력 인터페이스, 영상 판별 부족, annotation과 가시성의 차이, 공동 처리 효과다. 이번에는 첫 두 설명을 분리할 후속 계약의 성립 여부까지만 판단한다.
5. 다음 결정: 구체적인 후속 비교가 성립하면 하나만 제안한다. 성립하지 않으면 현재 frozen 존재 설계를 보류한다. 다른 자료·모델의 실패 수집으로 자동 이동하지 않는다.

# Hypothesis

현재 strict 실패의 일부가 출력 경계 문제라면 NONE의 raw token에서 final 답이 확인될 수 있다. 반면 영상 조건에서 final 자체가 PRESENT이고 설명이 부재를 말하면 경계 처리만으로는 해결되지 않는다. 이 둘을 구분하는 것은 출력 구조 감사이며 시각 인식의 증명이 아니다.

# Limitation Evidence / Correct Usage Checks

`mri-explicit-target-context-effect`와 `radgenome-flair-fixed-category-response`의 observed 상태를 유지한다. iter_134는 blocking이 있으므로 method 진입 근거로 사용하지 않는다.

모델 revision·tokenizer revision·decode 설정과 실제 special token ID를 로컬 자산 및 공식 모델 자료로 확인한다. token 문자열을 임의 삭제하거나 마지막 상태 단어를 찾는 방식으로 정답을 만들지 않는다. 이미지 없는 입력의 응답과 영상 입력의 응답을 별도로 기술한다.

# Contribution Path / Baselines / Reuse

신규 contribution은 미확정이다. 이 작업의 가치는 무효한 비교를 근거로 타 모델·LoRA를 확대하지 않도록 다음 투자를 좁히는 데 있다.

현재 HEAD `7dfd466b5a42361f39ad7da0bf0a94b5dc134885`를 유지한다. `i134_common.py`와 `i134_spec.py`는 원 strict 추출·공통 유틸리티의 승인 범위만 사용한다. `i134_data.py`, `i134_fetch.py`, `i134_run.py`, `i134_lock.py`, `i134_tech.py`, `i134_eval.py`, `i134_posthoc.py`는 감사 대상이며 범용 재사용 승인이 아니다. 현재 작업에 필요하지 않은 실행기·worker 결함을 전수 수정하지 않는다.

가까운 직접 대조는 같은 영상의 개별 OR와 공동 입력이다. 전문 segmentation+규칙의 기존 실용 근거는 유지하되 동일 정보 비교로 해석하지 않는다. AutoRG RGv2의 RadGenome 학습 노출도 유지한다.

# Proposed Experiment

## 1. 자료 연결의 마지막 한정 확인

기존 기술4·평가32 case만 대상으로 증거표를 만든다. 각 항목을 확인/미확인/불일치로 표시하고 출처·revision·hash를 연결한다.

- RadGenome 공식 배포의 report key·split·원천 release 연결.
- 현재 미러 revision의 원문 이용 조건과 원천 BraTS 이용 조건, 해당 경로의 사용 가능 근거.
- 공식 `syn51615438` mapping의 실제 schema·행과 기존 case ID 연결. 승인된 접근만 사용하고 접근 거부를 우회하지 않는다.
- MSD 기존 manifest까지 이어지는 ID 관계의 존재 여부. mapping이 2017 ID를 제공해도 MSD 익명 ID와 연결되지 않으면 독립성은 미확인이다.
- 같은 환자의 다른 scan ID 가능성. 파일명이 다르다는 이유로 환자 독립성을 확정하지 않는다.

기존 자료로 확인되지 않는 관계를 영상 유사도나 파일명 추측으로 인증하지 않는다. 동일 voxel 발견은 중복의 양성 근거가 될 수 있지만 불일치는 다른 전처리 환자의 비중복 증명이 아니다. 전체 MRI 재다운로드는 하지 않는다.

## 2. 출력 구조의 한정 감사

저장 기술40·본320 출력의 token 경계 존재, EOS, 원 strict 상태, final 경계 이후 상태의 구조적 추출 가능 여부를 기록한다. final 상태는 새 정확도·BA·가설 판정에 사용하지 않는다.

첫 줄·설명 불일치는 이미 확인한 대표 사례와 자동 후보의 원문 위치로 보존한다. 설명문의 임상적 정답 여부를 평가하지 않고, 부정 범위나 대상이 모호하면 unresolved로 남긴다. 새 LLM 평가기를 호출하지 않는다.

NONE의 형식 실패를 영상 없이 병변을 단정한 것으로 보고하지 않는다. 반대로 NONE 처리 가능성이 영상 조건의 모순을 해결했다고 보고하지 않는다.

## 3. 후속 비교의 성립 판단

자료 이용·연결이 확인되면 다음 비교가 가능한지 한 개의 계약 초안만 작성한다: 동일 pixels·모델·질문에서 범주 우선 출력과 근거 뒤 최종 범주 출력의 차이를 시험하여, 응답 순서 변경이 내용과 최종 답의 일치를 회복하는지 확인하는 diagnostic이다. 이 초안은 실행 승인이 아니다. 설명문을 정답으로 삼지 않고 annotation 일치도와 내부 일치를 분리해야 한다.

MSD 독립성이 확인되지 않으면 기존 자료를 반복 개발 자료로 명시한 paired 인터페이스 진단만 고려할 수 있다. 이는 원 신규 환자 gate의 충족이 아니며 외부 재현 주장을 할 수 없다. 이런 축소된 해석으로도 투자 결정이 달라질 이유가 없으면 제안하지 않고 보류한다.

이용·개별 연결이 미확인인 채 남으면 후속 GPU 비교를 제안하지 않는다. 이용 조건 확인과 과학적 독립성 제한은 서로 대체할 수 없다.

## 4. 단계·규모·자원

이번 도달 단계는 준비다. 가능성 탐색·규모 확대·독립 확인은 미실행이다. CPU만 사용하는 이유는 현재 자료·출력 계약이 GPU 비교의 해석을 막기 때문이다. 신규 학습·생성·MRI 다운로드는 0이다.

wall-clock은 조회·metadata 처리·출력 감사의 실측을 나눠 보고한다. GPU 시간을 임의로 제한하려는 선택이 아니다. 후속 실제 비교를 제안할 때에는 기술 표본, 고정 평가 표본, 두 GPU 배치, 전체 비용 및 종료 기준을 별도 계획에서 확정한다. iter_134의 2/4-worker 실측은 참고 가능하지만 새 workload의 안전성을 대신하지 않는다.

# Implementation Tasks for Claude

1. 기준 plan·review와 현재 HEAD를 확인하고 기존 산출물의 불변성을 기록한다.
2. 공식 metadata·이용 근거와 기존 manifest를 연결한 `data_evidence`를 새 `research/results/iter_135/`에 작성한다. 인증정보는 기록하지 않는다.
3. 저장 token의 구조만 감사하고 원 응답·strict 결과를 보존한다. 필요한 최소 보조 코드만 추가한다.
4. `followup_feasibility`에 각 blocker의 해소 여부와 증거를 적는다. 준비 통과와 유효 실험을 분리한다.
5. 후속 diagnostic 계약 하나 또는 현재 설계 보류 중 하나를 보고한다. 둘 다 가능하다는 열린 결론으로 끝내지 않는다.

# Evaluation (성공/실패 기준 포함)

- 준비 양성: 공식 이용·개별 자료 연결이 확인되고, 출력 구조 검토를 통해 임상 의미 재채점 없이 경쟁 설명을 구분할 후속 비교가 구체화된다. 별도 diagnostic 계획을 권고한다. 성능 개선·한계 검증·method 진입은 주장하지 않는다.
- 준비 음성: 자료가 연결되지 않거나 후속 비교의 판별 가치가 부족하다. 현재 frozen 존재 설계의 투자를 보류한다. 자료 부적합과 연구 가치 부족을 구분한다.
- 불확정: 필요한 mapping·이용 근거가 실제 접근 장애로 남는다. 특정 자산·오류·필요 권한을 남기고 현재 설계를 보류한다. 승인 범위 밖의 접근이 반드시 필요할 때만 구체적인 사용자 결정을 요청한다.

이 반복은 신규 모델 가설 검증을 하지 않으므로 `valid_experiment=true`의 근거가 되지 않는다. 원 iter_134를 소급 승인하지 않는다. 같은 한정 확인을 다음 반복으로 다시 발주하지 않는다.

# Risks / Checks

- 공식 release 관계, 개별 파일 연결, 이용 권한, 환자 독립성은 별개다.
- 현재 웹 카드와 사용 revision의 license 차이를 기록하고 어느 쪽도 임의 선택하지 않는다.
- mask 부재는 임상 정상이나 FLAIR 가시성 부재를 보장하지 않는다.
- final 경계 검사는 설명 정확도의 검증이 아니다. 원 결과에 새 parser를 적용한 성능표를 만들지 않는다.
- 원 코드·결과·판정은 보존하고 새 파일만 iter_135 경로에 둔다. 구현 종료 후 코드 보존은 orchestrator에 맡긴다.

## 대규모 GPU 필요 후보

3D encoder–언어 모델 공동 적응과 다양한 관측 수를 포함한 MRI instruction tuning은 장기 후보로 유지한다. 현재 자료·응답 계약과 강한 단순 대안 이후의 필요성이 확인되지 않았으므로 실행하지 않는다.

# 계획의 근거 (GPT 조사 노트)

## 새로 확인한 것

- `agent/GOAL.md`, iter_134의 plan.md·review.md·review.json, iter_064 원 리뷰, 관련 LIMITATIONS·CODE_ASSETS 항목과 현재 소스를 확인했다.
- 현재 research HEAD는 `7dfd466b5a42361f39ad7da0bf0a94b5dc134885`이며 작업 트리는 깨끗했다. 필요한 i134 파일은 현재 브랜치에 있어 선별 반입이 필요 없다.
- 기준 계획 SHA256은 `7251f04a3a36b83b0aeaffed02c4bae1037235f31af465d1ed4bb1ef3710c544`다.
- `research/results/iter_134/data/data_manifest_v2.json`은 공식 data use 인증과 MSD 연결을 미확인으로 명시한다. `problems=[]`는 이 선행 조건을 통과했다는 뜻이 아니다.
- 저장 원문 `BraTS-GLI-00478-000__N1`과 `__N1N2`는 PRESENT 뒤에 병변 부재를 명시한다. 설명을 임상적으로 정답이라고 판단한 것은 아니다.
- 같은 case의 NONE은 thought/final 구분 token을 포함하며 final에는 UNKNOWN과 영상 미제공 설명이 있다. 현재 parser는 전체 문자열의 첫 줄만 읽으므로 이 구조를 구분하지 못한다. 이는 대표 사례 확인이며 32건 전체의 의미 재채점은 하지 않았다.
- [공식 BraTS release 설명](https://www.synapse.org/Synapse:syn51156910/discussion/threadId=10714)은 2021/2023 train 관계와 ET label 4→3을 설명한다. [공식 mapping 항목](https://www.synapse.org/Synapse:syn51615438)의 파일명은 `BraTS2023_2017_GLI_Mapping.xlsx`다. 실제 행 내용과 MSD ID 연결은 이번 조회로 확인하지 못했다.
- [BraTS2021 공식 문서](https://www.med.upenn.edu/cbica/brats2021/)는 주석 의미와 이전 release 관계를 설명한다. 이것만으로 현재 미러 파일의 이용 조건·개별 동등성을 인증할 수 없다.
- [AutoRG 공식 구현](https://github.com/ljy19970415/AutoRG-Brain)은 공식 자료를 [JiayuLei/RadGenome-Brain_MRI](https://huggingface.co/datasets/JiayuLei/RadGenome-Brain_MRI)로 연결한다. 처음 시도한 RadGenome 조직 URL의 조회 실패를 자료 전체의 접근 실패로 해석하지 않는다.
- 현재 MedOtter 웹 카드의 license 표시는 cc-by-4.0이다. 과거 문서의 MIT 문자열과 다르므로 실제 사용 revision의 원문을 분리해야 하며, 어느 문자열도 원천 이용 조건 확인을 대체하지 않는다.

## 의미

추가 GPU 생성 전에 해결할 항목이 구체적이다. 그러나 NONE의 형식 설명만으로 영상 조건의 고정 응답이나 통합 문제를 해결했다고 할 수 없다. 이번에는 자료 연결과 출력 구조에 대한 최종 한정 확인을 선택하며, 과학적 비교를 수행한 반복으로 계산하지 않는다.
