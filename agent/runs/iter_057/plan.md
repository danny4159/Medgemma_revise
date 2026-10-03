# 요약

- **이번에 할 일:** 기존 MSD FLAIR D6/E48 출력의 위치 통제 분석을 수행한다.
- **필요한 이유:** 전체 BA에는 위치 prior와 병변 관련 영상 신호가 섞일 수 있다. 동일 위치 내 신호는 이미 관찰됐지만 크기와 불확실성을 정리해야 한다.
- **확인할 기준:** 위치별 class 성능, 위치 표준화 BA, D에서 고정한 위치 baseline 대비 차이, 여러 case에 걸친 잔여 오류다.
- **주의·다음:** 사후 개발 분석이다. 새 생성·학습 없이 전문 모델 최소 대조의 필요성 또는 현재 방법 투자 보류를 결정한다.

# Current Understanding

기준 문서는 `agent/runs/iter_056/plan.md`이며 SHA256은 `4c19e538432e7cd48a17ebd268f28196333a21d6837ad38bf366007562ff9501`이다. 판정 근거는 같은 반복의 `review.md`와 `review.json`이다.

**유지:** MSD Task01 FLAIR, D6/E48, 여섯 구간, 비배경 annotation 합집합 정답, DENSE/U8/O8/TEXT, prompt·parser·생성 출력, case 분석 단위 및 iter_056 원 기준·success 판정이다. U8의 저비용 탐색 baseline 가치와 복잡한 표집 투자 보류도 유지한다.

**이번 변경:** 기존 출력에 위치 층화, D 기반 위치 규칙 및 paired 불확실성 분석을 추가한다. 이는 원 실험의 미완료 실행이 아니라 별도 사후 탐색이다.

**미검증:** 병변 자체의 인과적 사용, 환자 독립성, 전문 모델 대비 효용, 직접 SFT 대비 추가 가치, 신규 방법 효과다. 과거 MRI reference 결과는 현재 과제의 한계 근거로 전용하지 않는다.

# Strategy Check / 연구 방향 판단

iter_056 리뷰의 전략 판단을 유지한다. 새로운 연구 방향 재선정보다 한정된 미해결 설명의 정리가 먼저다.

- **관찰:** 전체 BA가 높고 U8와 DENSE 차이는 작다. slab1·4에서는 같은 위치 안에서도 구별 신호가 있다.
- **남은 설명:** 위치 index만으로 설명되는 부분과 위치 안에서 달라지는 영상 신호가 섞여 있다. 위치를 통제해도 병변 이외 영상 confound는 남을 수 있다.
- **최소 비교:** 전체 여섯 위치의 class별 성능과 D에서 정한 위치 규칙을 E에 적용한다.
- **결정 변화:** 신호와 잔여 오류가 함께 남으면 전문 segmentation+OR 비교를 구체화한다. 근거가 약하거나 추가 비교가 연구 결정을 바꾸지 못하면 현재 방법 투자를 보류한다.

현재 방법 개선은 단순 U8 이후의 큰 표집 격차가 없어 우선하지 않는다. 즉시 다른 모델·자료로 이동하면 기존 출력으로 답할 질문을 남긴다. 이번 재분석은 다운로드·학습·생성 없이 가능하다. iter_056의 세션 약52.7분과 E 생성 약19.1분은 리뷰 기록이며 준비 비용 비율은 산출하지 않는다. 이번에는 분석 구현·검증이 주된 작업이고 절감률은 주장하지 않는다.

# Hypothesis

MedGemma의 구간 답변은 위치 index만의 규칙보다 세부적인 구별 정보를 가질 수 있다. 반면 전체 BA 이득의 상당 부분은 위치 분포로 설명될 수 있다. 두 설명은 동시에 성립할 수 있다.

동일 위치의 sensitivity와 specificity를 함께 측정한다. 새로운 개입이 없으므로 결과를 병변 사용의 인과 증명으로 부르지 않는다.

# Limitation Evidence / Correct Usage Checks

`limitation_ids=[]`를 유지한다. iter_056은 유효한 실제 출력 관찰이지만 새 MRI 한계를 등록하지 않았으며, 이번에도 method gate를 사용하지 않는다.

현재 입력의 annotation·PNG 연결과 tensor 대조는 iter_056 리뷰의 승인 범위 및 불변 hash를 확인해 재사용한다. 공식 예제 직접 대조·일반 affine 검사의 미완료를 완료로 바꾸지 않는다. 영상이나 GT를 재생성하지 않는다.

원시 `suffix_text_raw`를 기존 parser 규칙으로 다시 해석한다. invalid는 각 class의 오답이며 ABSENT로 바꾸지 않는다. 저장 answer와의 불일치는 즉시 보고하고 원인을 해결하기 전 새 통계를 확정하지 않는다.

# Contribution Path / Baselines / Reuse

이 과제는 segmentation+OR로 풀 수 있다. 이번 분석의 가치는 향후 volume 근거 사용 연구에 필요한 모델 적합성과 오류 범위를 명확히 하는 것이다. 새로운 contribution은 미확정이다.

실행 baseline은 D 기반 위치 규칙, TEXT, 상수 PRESENT/ABSENT다. DENSE/U8/O8는 기존 출력 그대로 비교하며 O8은 실용 방법이 아닌 diagnostic oracle이다. 전문 segmentation+OR와 직접 SFT의 미실행을 명시한다.

현재 브랜치와 HEAD `da6e75570dcd01f957cde9b9f33b1b57217fcb70`를 이어간다. 필요한 파일이 모두 있어 `reuse_assets=[]`다.

- `msd56_data.py`와 기존 자료 manifest: native RAS·현재 FLAIR·annotation 연결에 한정한 승인 근거를 재사용한다.
- `msd56_eval.py`: confusion·metric의 정의를 유지하고 원시 응답 해석, 요청·조건·GT·protocol provenance 검증을 보완한 분석 경로에서 사용한다.
- `msd56_breakdown.py`: 상한 오표기와 import 시 쓰기를 수정하고 명시적 입력·출력 인자로 실행하도록 한정 보완한다. 기존 `results/iter_056/`에는 쓰지 않는다.
- `msd56_run.py`: parser와 record 형식만 필요한 범위에서 참조한다. GPU runner 전체 재사용 승인이 아니다.
- D 본 실행은 `source/msd56_run_v1_used_for_D_main.py`와 원 `protocol_D.json`에 연결한다. 현재 코드와 hash가 다르다는 이유로 검사를 완화하지 않는다.

launch admission, Qwen, 범용 sanity·재개 경로의 나머지 reuse issue는 이번 실행에서 사용하지 않으므로 보류한다. 향후 GPU 실행 전에 해결해야 한다.

# Proposed Experiment

## 1. 동작 확인과 분석 입력 잠금

원시 생성은 `results/iter_056/gen/D/`와 `gen/E/`의 본 실행만 사용한다. 재개 테스트 출력은 섞지 않는다. `data/cases.json`, `case_order.json`, `gt_slabs.json`, `requests_D/E.jsonl`, `cond_map_D/E.json`, 해당 protocol과 원시 record의 hash를 새 분석 manifest에 저장한다.

D/E case 분리, case당 slab0~5, 조건 행의 유일성, 공유 rid의 명시적 연결, 요청 누락·중복·추가, protocol digest 및 원시 응답 해석을 검증한다. 공유 TEXT/U8/O8 요청은 독립 관측으로 부풀리지 않는다. 필요한 원본 연결이 깨지면 해당 결론을 중단하고 blocker를 보고한다.

E 고유 요청766개, 조건 행1152개와 원 confusion 수치를 회귀 검사한다. D는 고유 요청97개·36구간이며 위치 규칙 선택에는 D 정답만 쓴다.

## 2. 위치 baseline 고정

6개 위치의 PRESENT/ABSENT 조합64개를 D36구간에 적용해 전체 BA가 최대인 규칙을 고른다. 동률은 PRESENT 위치 수가 작은 규칙, 이어 slab0부터의 0=ABSENT/1=PRESENT tuple 사전순으로 정한다. 선택 알고리즘을 E 비교 계산 전에 저장하며 결과에 따라 바꾸지 않는다.

고정 규칙을 E288구간에 적용한다. D6가 작으므로 이 규칙의 안정성이나 최적 일반화를 주장하지 않는다. bootstrap CI는 선택된 D 규칙에 조건부인 E case 불확실성임을 명시한다. 이번에 교차적합·추가 규칙 후보를 더하지 않는다.

E 다수 class 규칙 BA0.719336과 E 자체 BA 최댓값0.761664는 기존 리뷰 정정의 회귀 확인으로만 남긴다. 후자는 6-index 결정적 이진 규칙 집합의 in-sample 최댓값이지 모든 위치 기반 방법의 상한이 아니다.

## 3. 고정 E 분석

모든 위치와 네 조건에 대해 P/N, TP/FN/TN/FP, sensitivity, specificity, BA, invalid 수와 case 수를 보고한다. 한 class가 없는 위치의 해당 metric은 null로 표시하고 다른 위치를 복제하거나 smoothing하지 않는다.

주 위치 통제 지표는 양쪽 class가 존재하는 위치의 BA를 동일 가중 평균한 위치 표준화 BA다. 지원 위치 집합은 E GT만으로 고정하며 현재 리뷰상 slab0·1·2·4·5다. slab3은 sensitivity와 오류를 별도로 반드시 보고한다. 이 estimand는 전체 구간 BA와 다른 질문에 답하며 유리한 위치만 고른 점수가 아니다.

DENSE를 주 분석, U8를 실용 baseline 비교, O8/TEXT를 설명용으로 구분한다. 위치 표준화 BA−0.5, DENSE/U8의 전체 BA−D 고정 위치 규칙, U8−DENSE의 전체 및 위치 표준화 차이를 계산한다.

seed57·10,000회 case-cluster bootstrap을 사용한다. 같은 재표집 case를 모든 조건·고정 baseline에 공통 적용하고 여섯 구간을 함께 가져간다. 95% percentile CI와 유효 replicate 수를 보고한다. 고정 지원 위치 중 한 class가 사라진 replicate는 해당 표준화 metric을 undefined로 기록하며 나머지 위치로 재가중하지 않는다. 희소 class로 인한 조건부 CI 한계를 명시한다. 기존 seed56 CI는 원 수치 회귀용으로만 별도 재현한다.

## 4. 잔여 오류와 종료 판단

위치별 DENSE/U8의 FP/FN 및 양방향 정답 변화의 case 목록을 제공한다. 양성 오류는 기존 annotation voxel·coverage와 연결하고, U8가 놓친 DENSE 정답 양성5건 중 완전 annotation 누락0건이라는 기존 관찰을 회귀 확인한다. 병변 크기 cutoff를 새로 탐색하거나 어려운 사례를 제외하지 않는다.

DENSE와 U8가 함께 틀리는 오류, 한쪽만 틀리는 오류, D 위치 규칙과 다른 정답·오답을 분리한다. 여러 오류가 같은 case에 몰리는지 표시한다. annotation 부재 구간의 FP를 임상 정상 오진으로 부르지 않는다.

## 5. 규모 확대와 독립 확인

이번 규모는 D6/E48의 기존 출력 전체다. 학습0, 새 모델 요청0, 새 case0이다. 독립 확인은 하지 않는다. 결과를 본 후 prompt·seed·위치 가중치를 추가하지 않는다. 후속 GPU 비교가 필요하면 별도 계획과 full review를 거친다.

# Implementation Tasks for Claude

1. 기준 plan·review와 현재 파일 상태를 확인하고 `results/iter_057/`에만 분석 산출물을 저장한다.
2. 기존 평가·분해 코드를 한정 수정해 원시 문자열·mapping·GT·protocol 연결을 강제하고 분석 manifest를 저장한다.
3. D 위치 규칙 선택, 고정 E 평가, 위치별 및 위치 표준화 metric, paired case bootstrap을 구현한다.
4. parser invalid, 단일 class 위치, bootstrap의 class 소실, baseline 동률, case 묶음 재표집과 중복 요청 처리를 fixture로 검증한다. GT·cond_map·raw digest의 변조 및 누락을 거부하는 검사도 수행한다.
5. 별도 직접 count 계산으로 주요 confusion과 위치 규칙 결과를 검산한다. 기존 평가와 불일치하면 원인을 보고하고 선택적으로 유리한 수치를 채택하지 않는다.
6. 결과·실측 CPU 시간·원본 hash·재현 명령과 투자 권고를 보고한다. 원 결과와 리뷰는 덮어쓰지 않는다. 코드 커밋·브랜치 관리는 orchestrator에 맡긴다.

# Evaluation (성공/실패 기준 포함)

분석 실행의 성공과 과학적 양성 결과를 구분한다. 원시 연결·회귀 검사 통과 및 고정 분석 완료가 실행 유효성의 조건이다.

**양성:** DENSE 위치 표준화 BA가0.5보다 높고 그 95% CI 하한도0.5를 넘으면 index-only 설명을 넘어서는 구별 연관의 근거로 해석한다. 이는 사후 탐색 기준이며 확증이나 병변 인과 증명이 아니다. U8 결과와 모든 위치의 class 수를 함께 본다. 유효한 FP/FN이 최소5개 case에 남으면 단일 사례 문제가 아닌 후속 비교 대상으로 기술한다. 이5개 기준은 기존 계획의 사건 분포 기준을 이어받은 투자 선별 기준이다.

양성만으로 method pilot에 진입하지 않는다. 전문 segmentation+OR가 같은 오류를 해결하는지에 따라 내부 VLM 적응 투자 여부가 달라진다는 구체적 비교 질문을 작성한다. 후속 실용 비교의 최소 관심 차이는 BA5 pp 또는 동등 정확도에서 의미 있는 비용 감소로 두되, 독립적인 검증 계획에서 확정한다. 현재 생성 비용37.1%는 전체 pipeline 비용으로 확대하지 않는다.

**음성:** 위치 표준화 BA의 CI 상한이0.55 이하이면 현재 출력에서5 pp 이상의 위치 통제 이득 근거가 약하다고 보고한다. 이5 pp는 작은 추가 투자 가치를 구분하기 위한 탐색 기준이며 보편적인 의료 성능 기준이 아니다. 현재 MedGemma 구간 과제의 방법 투자를 보류하고 모델 대조의 정보 가치만 별도로 판단한다. D baseline과의 전체 BA 차이가 작다는 사실만으로 동일 위치 신호를 부정하지 않는다.

**불확정:** 위 사이이거나 희소 class 때문에 CI가 불안정하면 위치와 원인을 명시한다. 이미 본 E의 다른 subset·가중치로 유리한 결론을 찾지 않는다. 추가 증거가 전문 모델 비교 또는 모델 재선택 결정을 어떻게 바꿀지 설명할 수 없으면 투자 보류로 종료한다. 필요한 경우 한 가지 최소 후속 비교를 별도 권고할 수 있으나 이번에 실행하지 않는다.

어떤 결과에서도 복잡한 표집 방법의 자동 확대, Qwen 분기의 소급 발동, 새로운 한계의 validated 승격은 하지 않는다.

# Risks / Checks

이번 CPU-only 범위의 이유는 새 출력 부족이 아니라 기존 출력의 위치 confound라는 해석상 blocker다. GPU 실험으로 넘어갈 조건은 의미 있는 신호·잔여 오류와 전문 모델 대조가 바꿀 투자 결정의 구체화다. 불필요한 GPU 호출을 만들지 않으며 이것을 연구 전반의 GPU 회피 원칙으로 사용하지 않는다.

CPU 시간은 첫100 bootstrap 반복의 처리량으로10,000회 소요시간을 추정하고 실제 시간과 함께 보고한다. 임의 timeout은 두지 않는다. 원본 manifest와 고정 규칙·설정을 먼저 저장하고 최종 파일은 원자적으로 완성한다. 재개 시 입력 hash를 확인하며 기존 iter_056 파일에 쓰지 않는다.

향후 GPU 비교는 시작 직전 실제 점유를 확인하고 두 GPU 배치·batch 확대 또는 복수 worker의 처리량을 검토해야 한다. 이전11.5GiB 가정은 쓰지 않으며 실제 전체 peak와 worker당2GiB 여유를 적용한다. 이번에는 GPU를 실행하지 않아 해당 결함 수정·처리량 재측정을 요구하지 않는다.

위치 표준화는 동일 slab 안의 정밀한 해부학적 위치·영상 특성·병변 부담 confound를 모두 제거하지 않는다. D6의 prior 선택 불안정성, E의 반복 사용, 환자 대응 및 사전학습 중복 미확인을 유지한다. CI를 독립 확증이나 임상 신뢰도로 표현하지 않는다.

## 대규모 GPU 필요 후보

전체 multi-sequence volume의3D encoder–언어모델 공동 적응과 대규모 MRI instruction tuning은 장기 후보로 보존한다. 현재 분석은 그 필요성·신규성을 검증하지 않으며 이번 투자 범위에 포함하지 않는다.

# 계획의 근거 (GPT 조사 노트)

## 확인한 근거

- `agent/GOAL.md`, GPT 사용량 정책, iter_056의 plan·review·review.json·claude_report, CODE_ASSETS와 LIMITATIONS 관련 항목을 확인했다.
- 기준 계획은 `agent/runs/iter_056/plan.md`, SHA256 `4c19e538432e7cd48a17ebd268f28196333a21d6837ad38bf366007562ff9501`이다.
- 현재 research HEAD는 `da6e75570dcd01f957cde9b9f33b1b57217fcb70`이며 작업 트리 변경은 없다. 필요한 `msd56_*.py`와 D/E 원시 자료·protocol·보존된 D v1 runner가 현재 기반에 있다.
- 리뷰에서 E48 DENSE/U8/O8 BA 0.776335/0.768639/0.752766, U8−DENSE CI [−0.057085, 0.037979]를 검증했다. 새 분석에서 이를 회귀 기준으로 유지한다.
- 위치 다수 class 규칙의 0.719336은 BA 상한이 아니다. E 자체의 64개 규칙 최댓값은 0.761664이며 실용 baseline으로 사용할 수 없다.
- slab1·4의 DENSE BA 0.7424·0.8000은 이미 리뷰에 있는 관찰이다. slab0 양성3개, slab2 음성2개, slab3 음성0개 때문에 위치별 불확실성 처리가 필요하다.

## 재사용 판단

`msd56_eval.py`는 저장 answer와 외부 cond_map·GT를 신뢰한다. 이번에는 원시 문자열 재해석과 입력 hash 연결을 보완한다. `msd56_breakdown.py`는 import 시 실행·쓰기하며 위치 prior 표기도 잘못되어 그대로 실행하지 않는다. 기존 계산을 수정·확장하되 출력은 iter_057로 명시한다. 미사용 GPU launch·Qwen·sanity 경로의 결함은 이번 작업에 섞지 않는다.

## 선택 이유

D 기반 위치 규칙은 작은 D의 불안정성이 있지만 E 정답 최적화를 피하고, 교차적합과 재학습 bootstrap을 추가하지 않고도 명료한 대조를 제공한다. 모든 위치의 층화 성능을 함께 제시해 이 baseline 하나에 결론을 의존하지 않는다. 새 문헌이나 모델 적합성 주장을 추가하지 않는 한정 재분석이므로 외부 문헌 재조사는 필요하지 않다.
