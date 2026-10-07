# 요약

- **이번에 할 일:** 저장된 target·NLL·V32 판독을 연결해 정상문 편중과 선택 영향을 점검한다.
- **필요한 이유:** iter_092의 R/G 비교는 유효하지만 report-only baseline이 약해 위치 학습 효과를 일반화할 수 없다.
- **확인할 기준:** 구체적 보완 하나를 지지하는 환자별 근거와 의미 평가 민감도를 확보한다.
- **주의·다음:** 원 E128 판정은 보존한다. 분석 후 보완 시험 하나 제안 또는 현재 recipe 투자 보류로 끝낸다.

## 알림 맥락

- 연구: 위치 학습과 판독 정확성
- 데이터: 흉부 X-ray PadChest-GR
- 모델: MedGemma 1.5의 report-only/위치 보조 LoRA
- 과제: 저장된 판독문과 학습 정답을 비교해 baseline 부적합의 설명을 좁힌다
- 가설: 정상문 편중에는 target 구성·checkpoint 선택·의미 평가가 관여할 수 있다
- 질문: 위치 학습 효과를 다시 시험하기 전에 판독 baseline에서 무엇을 고쳐야 하는가?
- 변경: 구체화
- 연결: iter_092에서 위치 출력은 개선됐지만 판독 이득은 기준 미달이었고 R/G 모두 base보다 낮았다
- 작업: 저장 train/validation 분석으로 구체적인 보완 하나의 시험 가치 또는 투자 보류를 결정한다

# Current Understanding

기준 기록은 `agent/runs/iter_092/plan.md` SHA256 `70bbf0f32bafaaa2c0f267c9fa75efc57e562d282765437d5258c3d8ef062e7f`와 해당 review.md/json이다. 부모 iter_090 plan SHA256은 `a305c99f6f0473e832560a875d854dafdf9dbe7ace5a330b0abc23a98ce45fb8`다. 원 amendment와 recovery/stage_decision_rules.json, 최종 선택 기록을 함께 연결한다.

네 trajectory epoch6와 E128 평가가 완료됐다. 인계 지시의 checkpoint 재개는 이미 끝난 일회성 작업이므로 반복하지 않는다. append-only 보존·완료 확인·대기 운영 원칙은 유지한다.

원 E128 recall 적격 94명에서 G−R은 +0.532pp, 추가 회복 1명으로 기준 미달이다. R/G가 일반 정상문을 많이 생성한 사실과 그 원인은 구분한다. V32의 epoch2/6 실제 출력은 있지만 선택된 epoch1의 동일 V32 생성 유무는 입력 목록에서 명확히 확인해야 한다. 서로 다른 V32와 E128 점수 차이를 epoch 효과로 해석하지 않는다.

# Strategy Check / 연구 방향 판단

**관찰 → 남은 설명 → 최소 비교 → 결정:** grounding 개선이 판독 개선을 보장하지 않았다 → 약한 판독 baseline, NLL 선택, target 노출, 의미 규칙이 얽혀 있다 → 동일 V32의 저장 궤적과 T512/V64를 연결한다 → 근거 있는 baseline 보완 하나 또는 현재 recipe 보류를 선택한다.

직전 리뷰의 권고를 유지하며 같은 현상을 구체화한다. 새로운 후보 탐색이 아니다. 즉시 새 loss·seed를 실행하면 약한 baseline을 반복할 위험이 있고, 즉시 전환하면 이미 확보한 궤적의 정보 가치를 버린다. 이번에는 저장 자료 분석을 우선한다. 현재 결과는 인식·선택·결합 중 특정 내부 원인을 식별하지 않았다.

지배 비용은 이전 학습·생성에서 이미 지출됐다. 이번 비용은 자료 연결과 필요한 문장 검토다. GPU를 피하는 것이 아니라 다음 GPU 개입을 특정하는 해석상 blocker를 해소한다. 저장 근거가 보완을 지지할 때 별도 계획에서 실제 개입 비교로 넘어간다.

# Hypothesis

1. 반복되는 일반 정상문이나 소견별 노출 불균형이 target에 존재하며 생성 편중과 연관될 수 있다.
2. NLL 순위와 실제 소견 회복 순위가 다르므로 원 선택이 판독 능력을 대표하지 못할 수 있다.
3. 정상문·급성 부정의 의미 처리 차이가 모순 수치에 영향을 줄 수 있다.
4. 위 설명이 약하면 현재 recipe의 실제 판독 적응 부족이 남는다.

모든 가설은 탐색이며 단순 빈도 상관을 원인 증명으로 부르지 않는다.

# Limitation Evidence / Correct Usage Checks

이번 직접 대상은 iter_092의 유효한 결과와 reuse_issues이며 별도 등록 limitation이 없어 limitation_ids는 비운다. 방법 개발 gate로 전용하지 않는다.

기존 공식 입력·processor·template·수치·학습 완료 검증은 원 리뷰와 동일 hash 범위에서 재사용한다. 이번 필수 검사는 환자 ID와 NLL 순서, target 출처, 원문 anchor, 분모, 제외된 초기 비recovery 학습의 혼입 방지다. 모호하거나 미표기된 소견을 정상 정답으로 바꾸지 않는다.

# Contribution Path / Baselines / Reuse

새 기여는 아직 없다. 가장 가까운 직접 report-only SFT와 표준 공동 CE의 비교를 해석하기 위한 진단이다. CURE·MAIRA-2에 대한 기존 선행 기록은 유지하고 이번에 재조사하지 않는다. 시스템 간 학습량·base 차이는 위치 supervision 효과와 구분한다.

현재 `approach/grounding-report-transfer`의 HEAD `93193abc4d04c44cf40b2695376d520209fa1745`를 유지한다. 필요한 파일은 현재 브랜치에 있으므로 반입은 없다.

- `report86_common.py`, `report92_manifest.py`: 출처 연결의 한정 승인 범위를 재사용한다. 과거 결과 경로에 쓰는 main은 실행하지 않는다.
- `report90_data.py`, `report89_model.py`, `report90_train.py`, `report90_recovery_train.py`, `report90_select.py`: target·loss·순서·선택 규칙을 읽는 근거로 사용한다. trainer나 선택 파일을 수정·재실행하지 않는다.
- `report90_semantic_eval.py`, `report90_semantic_verify.py`: 실제 입력과 분모·anchor·집계 동작을 확인한 범위에서 사용한다. 독립 재계산은 별도 경로로 한다.
- `report92_autojudge.py`와 관련 judge 파일: needs_fix를 유지한다. 기존 판정 재현용과 새 민감도 평가를 분리하며 범용 의미 평가기로 승인하지 않는다.

## 대규모 GPU 필요 후보

여러 기관·모델·학습량에서 report-only, 정확한 위치 supervision, 교란 위치 supervision을 비교하는 연구를 보존한다. 현재는 강한 baseline과 잔여 문제를 확보하지 못해 실행하지 않는다.

# Proposed Experiment

## 1. 동작 확인과 입력 고정

새 결과는 `research/results/iter_093/`에만 저장한다. 기존 파일 hash와 실제 사용 경로를 manifest로 연결한다. T512/V64 manifest, V32 요청·reference v3, 네 recovery trajectory의 validation_01/02/04/06, epoch2/6 원출력·판정·평가, stage_decision_rules와 selection/final을 고정한다. base V32는 중복 없이 한 번만 센다.

학습 config의 val_sha와 실제 manifest를 대조하고 validate의 row 순서로 per_patient NLL을 연결한다. ID 순서를 추측해 정렬하지 않는다. 연결 실패면 해당 분석을 중단하고 필요한 연결 오류만 수정한다.

## 2. 가능성 탐색: target와 NLL

T512/V64에서 환자·문장 단위의 정상 전용, 양성 소견 포함, 양성+일반 부정 혼합, 불확실 표현을 구분한다. 반복 문구, 소견별 환자 노출, 위치·속성 포함 여부, 실제 target 구성과 제외 문장 기록을 집계한다. 정상문 문구 수와 정상 환자 수를 혼동하지 않는다. abnormal 플래그만으로 모든 문장의 의미를 확정하지 않는다.

네 trajectory×네 epoch의 V64 NLL을 환자와 층별로 제시한다. 환자 평균으로 원 전체 NLL을 재현한다. 정상 전용과 양성 포함 집단의 NLL 변화·순위가 전체 선택에 어떻게 기여했는지 분해한다. 저장 값은 sequence 평균이므로 token별 손실 기여가 저장되지 않았다면 이를 추정해 만들지 않는다.

원 LR→공통 epoch 선택을 정확히 재현한다. 모든 LR·epoch의 NLL 최소를 보는 대안은 사후 선택 민감도로만 보고하며 실제 선택 파일을 바꾸지 않는다. NLL만으로 대안 checkpoint의 판독 우위를 주장하지 않는다.

## 3. 동일 V32의 실제 생성 연결

base32개와 R/G×두 LR×epoch2/6의 256개 저장 출력을 모두 사용한다. strict/type-only recall, 정상문만 출력한 비율, 환자별 회복·소실, 모순·모호성·비EOS를 원문과 연결한다. 분모는 전체32명, 비정상21명, recall 적격20명을 구분한다.

동일 환자의 NLL 변화와 생성 변화를 연결하되, epoch1 생성이 없으면 결측으로 남긴다. 새 GPU 생성으로 빈칸을 메우지 않는다. 효과를 근거로 환자·소견을 제외하지 않는다. paired 환자 bootstrap 10,000회와 leave-one-patient-out으로 차이의 불확실성·집중도를 보고하며 확증 문턱으로 사용하지 않는다.

## 4. 의미 규칙의 한정 대조

일반 정상문, 'other' 범위가 있는 부정, 급성 부정, 특정 소견 부정, 위치·속성 대응의 다섯 규칙군을 점검한다. 각 군에 명시 지지·명시 모순·판단불가 사례를 포함해 최소 15개 대조를 만들고, 현재 실제 V32에서 해당하는 문장에 연결한다. fixture 정답과 근거를 구현 결과 전에 고정한다.

'No significant findings'는 중요도 범위가 모호할 수 있다. 'No acute process'는 급성 여부 근거 없이 모든 만성·존재 소견으로 반박하지 않는다. 구체적 부정은 같은 소견·범위의 확정 양성과 대조한다. 위치·속성은 substring 일치만으로 승인하지 않는다. 필요 사례에는 실제 reference/출력 span과 사례별 판단 이유를 기록한다. 일괄 retain은 검토 증거로 쓰지 않는다.

기존 규칙 결과와 수정된 보수적 민감도를 나란히 보고한다. 두 해석에서 결론이 갈리면 불확정으로 남긴다. E128의 추가 의미 재평가는 이번 범위에서 제외하고 기존 리뷰의 모순 지표 제한을 유지한다. 원 판독 개선 기준과 원 판정은 변경하지 않는다.

## 5. 규모 확대·독립 확인·비용

이번은 저장 자료의 전체 지정 범위를 분석하는 한정 진단이다. 신규 학습·생성·추가 seed·E 개방은 없다. 독립 임상 확인은 미실행이다. CPU 처리 시간과 실제 검토 사례 수를 기록하고 최초 집계 실측으로 남은 비용을 갱신한다.

후속 GPU 시험은 이번 결과가 하나의 구체적 개입 또는 하나의 판단 가능한 결측을 지지할 때 별도 계획으로 정한다. 그 계획에서 두 GPU의 허용 장치·peak와 worker당2GiB 여유를 확인하고 batch 확대 또는 복수 worker의 처리량을 비교한다. 이번에 GPU 점유율을 위해 불필요한 요청을 만들지 않는다.

# Implementation Tasks for Claude

1. 기준 문서·config·원출력의 연결 manifest와 입력 목록을 만든다. 완료된 인계·학습은 재개하지 않는다.
2. target 노출 표와 ID가 연결된 NLL 궤적을 만든다. 원 평균·선택을 독립 재현한다.
3. 동일 V32 저장 출력의 환자별 변화와 정상문 편중을 연결한다.
4. 다섯 의미 규칙군의 고정 대조와 실제 관련 사례를 검토하고 별도 민감도 결과를 만든다.
5. 신규 집계와 독립 verifier를 대조한다. 누락·중복·순서 오류·anchor 오류를 실패로 처리한다.
6. 보고서에서 근거가 지지하는 보완 하나, 결정을 막는 결측 하나, 또는 투자 보류 중 하나를 선택한다. 원 보고서의 recall 분모와 430/512=84.0% 정정은 새 보고서에 명시하고 과거 파일은 보존한다.

# Evaluation (성공/실패 기준 포함)

- **양성:** 동일 V32에서 여러 환자의 생성 회복과 NLL 순위 불일치가 의미 민감도·한 환자 제거에도 유지되거나, 실제 target 구성의 구체적 결함이 원문으로 확인되면 그 근거에 대응하는 보완 하나를 제안한다. 새 학습의 효과를 입증한 것으로 부르지 않는다.
- **음성:** 저장된 target·validation에서 구체적 보완 근거가 없으면 현재 recipe의 추가 seed·epoch·위치 loss 투자를 보류한다. 위치 학습 전체는 기각하지 않는다.
- **불확정:** 의미 모호성이 결정을 좌우하면 평가 한계를 명시하고 보류한다. epoch1 V32 부재만 남고 그 측정이 선택 보완 여부를 실제로 바꿀 수 있으면 해당 한정 생성 비교만 다음 계획 후보로 제안한다. CI가 넓다는 이유만으로 확대하지 않는다.
- **기술 실패:** ID/NLL/출력 provenance 연결이 성립하지 않으면 해당 분석을 무효로 표시한다. 모델 능력의 음성 결과로 바꾸지 않는다.

단순 코드 검사 통과와 가설 판별을 구분한다. 원 E128의 +0.532pp·회복1명·기준 미달은 유지하며, 이번 분석으로 과거 실험을 성공으로 재판정하지 않는다.

# Risks / Checks

- V32와 E128의 집단 차이를 checkpoint 효과로 오해하지 않는다.
- 사후 분석과 사전 선택, 새로운 독립 확인을 명확히 구분한다.
- 문장 빈도와 token loss, 미표기와 음성, 중요도와 급성 여부를 혼동하지 않는다.
- 초기 제외266 updates와 비recovery 결과를 유효 궤적에 섞지 않는다.
- 원 evaluator·trainer·config·checkpoint·결과를 덮어쓰지 않는다.
- 이번 범위를 범용 평가기 개발이나 문헌·모델 순회로 넓히지 않는다.

# 계획의 근거 (GPT 조사 노트)

직전 review.md와 review.json/code_assets, iter_092 plan, 현재 GOAL, 관련 CODE_ASSETS 및 LIMITATIONS, 실제 선택·학습·평가 소스를 확인했다. research HEAD는 93193abc4d04c44cf40b2695376d520209fa1745이고 git status는 깨끗하다.

iter_092 plan SHA256은 70bbf0f32bafaaa2c0f267c9fa75efc57e562d282765437d5258c3d8ef062e7f, iter_090 plan은 a305c99f6f0473e832560a875d854dafdf9dbe7ace5a330b0abc23a98ce45fb8이다. stage_decision_rules.json과 report90_select.py에서 epoch6 NLL로 LR을 고른 뒤 공통 epoch NLL 합으로 선택하는 규칙을 확인했다. 원 선택은 위반이 아니다.

저장 epoch2/6 V32 평가에서 R LR1e-4 strict recall은 0.125→0.175, R LR2e-4는 0.1667→0.2000이다. base는 0.1667이다. 각 조건 32명 중 recall 적격은 20명이다. 이는 원시 문장과 평가 규칙의 추가 검토가 필요한 저장 수치이며, 선택된 epoch1의 E128과 직접 비교해 epoch 효과를 단정할 수 없다.

validation_02.json에 환자별 NLL 64개가 저장돼 있고 trainer validate는 입력 rows 순서를 따른다. 따라서 manifest 순서와 config hash를 확인하면 층별 분석이 가능하다. report90_recovery_train.py는 T512/V64 manifest를 기본 입력으로 사용한다. report90_data.py의 target amendment와 제외 문장 기록도 보존돼 있다.

report92_autojudge.py는 일반 정상문, 구체적 부정, 급성 부정에 다른 대응 규칙을 사용하며 위치·속성에는 substring 대응이 남아 있다. 원 리뷰의 needs_fix를 유지한다. report92_manifest.py/report86_common.py는 출처 연결 용도로만 승인돼 있다. 이번에는 문헌 주장이나 새로운 방법을 선정하지 않아 문헌 조사를 반복하지 않는다.
