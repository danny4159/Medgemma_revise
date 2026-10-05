# 요약

- 이번에 할 일: iter_073의 test label 노출 기록과 annotation 해석을 정정하고 실제 로더의 접근 경계를 보완한다.
- 필요한 이유: train/val prior는 유효하지만 통합 MOAKS 집계에는 test 환자 행이 포함됐다.
- 확인할 기준: 원본 보존, 추가 test grade 분석 없음, 파싱 전 차단, 고정 hash 검증, 해석의 범위 제한이다.
- 주의·다음: 모델 실험이나 method gate 통과가 아니다. 한 번 보완한 뒤 OAI 자료를 기다린다.

# Current Understanding

기준은 `agent/runs/iter_073/plan.md`, SHA256 `86cd9691497d35da3670ad2929876b9ee7efc53889bcacec5e19a0a7678c7ca2`다. 해당 원문과 `review.md`, `review.json`을 함께 읽는다. 사용자 보완 `20261005_032747_b802ff04`는 유지한다.

유지: GOAL, MRI 후보, train/val 분포·prior, 조건부 비교 설계, 자료 인수 기준, 기존 원본·판정.

이번 변경: test 보호 완료 주장, 결측 치환의 원인 단정, unique의 의미를 정정하고 실제 재사용 경계를 차단한다.

미완료: 공식 방문·부위·size/depth·VERSION 연결, 임상 정답 일치, 영상 정합·관측 충분성·학습 노출. 이번에는 미확인으로 남긴다.

현재 브랜치의 HEAD는 `0e5de720949a422d8defabd0112001dbad313235`이며 필요한 세 소스가 모두 있다. 새 산출물은 `research/results/iter_074/`에 저장한다. iter_073의 결과·보고서·manifest는 덮어쓰지 않는다.

# Strategy Check / 연구 방향 판단

iter_073 리뷰의 전략 판단을 유지한다. 부위별 prior와 불균형은 확인했지만 인식·선택·결합의 모델 실패는 관찰하지 않았다. 남은 과학적 질문은 동일 적응 조건에서 직접 SFT·영역 지원·단순 영역 분류기 이후 중요한 문제가 남는가이다.

현재 방법 개선이나 다른 연구 질문 탐색보다 이미 발생한 노출과 해석을 바로잡는 것이 우선이다. 최소 비교는 실제 로더의 허용·거부 fixture이며 바뀔 결정은 준비 산출물을 어떤 범위로 재사용할 수 있는가 하나다. 지배 비용은 코드 경계 보완과 기록 정정이다. 새로운 GPU 실험·문헌 조사·benchmark 탐색은 이 결정을 바꾸지 않는다.

# Hypothesis

모델 가설은 검증하지 않는다. 확인할 기술 조건은 혼합·미확인 label 출처가 실제 분석 진입점에서 파싱 전에 거부되고, 허용된 train/val 출처는 고정 provenance 아래에서만 사용되는가이다.

# Limitation Evidence / Correct Usage Checks

`limitation_ids=[]`다. 이전 MRI 한계를 이 무릎 과제의 방법 근거로 전용하지 않는다.

iter_073 리뷰에서 test 환자 행 1,957개가 통합 MOAKS 파일에 포함됐고 전체 집계에 사용됐음을 확인했다. 이는 행 수이며 환자 수가 아니다. test.json 미다운로드와 test 정답 전체 비분석은 다른 주장이다. 모델 학습·test 성능 계산이 있었다고 확대하지도 않는다.

`TIME_FILE`, `SUBREGION_COL`, VERSION 선택의 미확정 상태를 유지한다. `orig_size_status='unique'`는 유효 후보 값이 하나라는 뜻이며 원 행 하나 또는 임상 정답 인증이 아니다.

# Contribution Path / Baselines / Reuse

가장 가까운 선행과 직접 SFT·영역 지원 비교는 기준 계획의 조사 근거를 재사용한다. 이번은 새 기여가 아니라 평가·정답 해석의 복구다.

재사용 대상은 현재 브랜치의 `rk73_fetch.py`, `rk73_audit.py`, `test_rk73.py`다. 세 파일 모두 직전 리뷰에서 needs_fix이며 이번 수정 후에도 전체 pipeline을 자동 승인하지 않는다. 표준 라이브러리, pandas 및 fetch의 huggingface_hub 의존성은 기존 환경에서 확인한다. 다른 checkpoint의 파일 반입은 없다.

train-only prior 수치는 직전 리뷰의 독립 검증을 재사용한다. 같은 실제 자료의 전체 집계는 다시 실행하지 않는다. 새 fixture에서는 null/0, 후보 값 중복, train-only majority 계산의 불변성을 확인한다.

# Proposed Experiment

## 1. 원본과 노출 이력 연결

기준 계획·리뷰·source manifest·annotation_audit·handoff_design 및 관련 기존 실행 로그를 연결한 정정 기록을 만든다. 기존 소스에서 입력→load_moaks→moaks_lookup→집계의 경로를 기록한다. 정규 audit 이외 과거 임시 명령의 통합 label 값 분포 조회도 기존 로그에서 확인되는 범위로 포함한다.

리뷰의 1,957행과 전체 MOAKS key·중복·충돌 집계가 split 제한 없이 계산됐다는 사실을 출처와 함께 옮긴다. 개별 test grade나 새로운 test 분포를 추출하지 않는다. 로그만으로 범위를 확정할 수 없는 부분은 미확인으로 남긴다. 다운로드만 된 파일과 실제 파싱·집계된 파일을 구분한다.

공식 test를 완전 미노출 집단이라고 부를 수 없음을 후속 인수 문서에 명시한다. 이번에 전체 test의 영구 폐기나 새 확인 집단을 임의 결정하지 않는다.

## 2. 해석 정정

별도 정정 문서에 원 표현·수정 표현·근거·영향을 연결한다.

- 결측이 0으로 치환됐다는 단정 → 가정한 mapping에서 유효 원 후보가 없지만 배포 값이 존재한다는 관찰.
- 원 MOAKS 정답과 약 95% 일치 → 가정한 방문·부위 연결에서 유효 후보 값이 유일한 항목의 배포 값 일치.
- 단일 후보 행 → 유효 후보 값 하나. 복수 행·VERSION이 있을 수 있음.
- test 보호 완료 → test JSON은 미다운로드했으나 통합 원 label 집계 노출이 있었음.

기존 train/val 분포와 prior, 자료 인수 기준 및 최초 입력 점검 순서는 유지한다. 기존 숫자를 재평가해 유리한 새 과제를 고르지 않는다.

## 3. 필요한 코드 경계만 보완

통합 label 파일과 출처 범위가 미확인인 label은 fetch/분석의 실제 진입점에서 거부한다. 파일명에 test가 없다는 이유로 허용하지 않는다. 현재 통합 CSV를 먼저 파싱한 뒤 train/val로 필터하는 우회는 금지한다. 안전한 train/val 전용 원 label 출처는 현재 확인되지 않았으므로 실제 원 label 연결 재집계는 보류한다.

`rk73_audit.py`의 기본 진입점이 기존 `load_moaks()`를 무조건 호출하지 않도록 한다. 금지된 원 label 분석을 요청하면 명시적으로 중단하거나 해당 분석이 보류됐음을 표시해야 하며, 빈 결과를 검증 완료로 보고하지 않는다. 독립 로더 호출에서도 같은 경계를 적용한다.

허용 파일의 재사용은 iter_073의 고정 source_manifest에 있는 SHA256·revision·경로와 대조한다. 현재 파일의 hash를 계산해 기대값 자체를 덮어쓰는 방식은 금지한다. mismatch·누락은 중단하며 자동 재다운로드하지 않는다. hash는 byte 동일성 근거이며 split 안전성의 증명과 구분한다.

출력 경로를 명시적으로 받아 iter_074로 제한한다. 과거 테스트의 import 시 결과 경로 생성과 iter_073 fixtures 덮어쓰기를 제거한다. 기존 CLI를 무심코 실행해 원본이 바뀌지 않도록 검사한다. 범용 framework나 학습기 정비는 하지 않는다.

## 4. 경계 회귀 검증

작은 synthetic fixture로 실제 수정된 진입점과 로더를 호출한다. 혼합 label·미확인 범위·test 답변은 parser 호출 전에 거부됐음을 spy 또는 예외로 확인한다. 허용된 train/val fixture는 정상 처리돼야 한다. 같은 크기의 byte 변조, 잘못된 revision, manifest 누락도 거부한다.

허용 출처 내부에서 fixture의 환자 membership 불일치가 발견되면 grade 집계 전에 실패해야 한다. test ID metadata의 허용과 test grade 접근을 구분한다. null/0, 같은 값의 복수 후보 행, 충돌 후보, majority 동률·없는 class의 기존 의미를 유지한다.

실제 원 label은 열지 않는다. 실제 안전한 기존 산출물과 필요한 train/val 파일은 hash 확인에 한정하고, prior 수치는 기존 검증 기록을 참조한다. 시험 전후 기존 iter_073 산출물 hash가 유지되는지 확인한다.

# Implementation Tasks for Claude

1. 기준 plan SHA와 현재 HEAD·diff를 확인하고 기존 사용자 변경을 보존한다.
2. 기존 결과와 로그로 노출 기록·해석 정정을 작성한다. 새로운 원 label 집계는 하지 않는다.
3. 세 rk73 파일의 실제 접근·hash·출력 경계만 수정한다. 필요하면 작은 정정 전용 진입점을 추가하되 기존 계산을 재구현하지 않는다.
4. 수정된 production 경로를 통과하는 fixture를 실행하고 결과를 `results/iter_074/tests/`에 저장한다.
5. `results/iter_074/`에 정정 문서, 입력·원본 hash 연결, 테스트 결과와 수정된 인수 안내를 보존한다. 기존 산출물은 참조로 연결한다.
6. 구현 보고서에 유지된 사실, 정정한 주장, 미확인 사항, 실제 CPU 비용, 자료 대기 상태를 적고 종료한다. 커밋·브랜치 관리는 orchestrator에 맡긴다.

# Evaluation (성공/실패 기준 포함)

양성: 기존 수치의 의미를 유지하면서 노출·해석 정정이 완결되고 실제 차단·hash·원본 보존 검사가 통과한다. 준비 보완 완료로 보고하고 자료 대기로 종료한다. valid model experiment나 GOAL 완료로 보고하지 않는다.

음성: 금지된 경로가 파싱되거나 원본이 변경되거나 provenance 검증이 우회되면 해당 재사용 경로는 미승인이다. 영향 범위를 기록하고 이번 수정 범위에서 복구·재검증한다. 모델 가설 기각으로 확대하지 않는다.

불확정: 공식 mapping·VERSION·안전한 원 label 출처가 없으면 해당 연결은 미확인으로 유지한다. 이는 정정 기록과 차단 검증의 완료를 막지 않는다. 추가 조회·원 label 재집계·새 준비 iteration으로 연장하지 않는다.

# Risks / Checks

이번은 CPU setup이며 신규 다운로드·모델 요청·학습·GPU 사용은 0이다. 기존 audit의 18.9초는 과거 실측일 뿐 이번 비용 예측이 아니다. 이번 wall-clock은 hash 읽기와 fixture 실행을 측정해 보고하며 임의 시간 상한을 두지 않는다.

OAI 원본 영상 부재와 정답 연결의 미확인이 실제 후속 blocker다. 자료 도착 후 사용자 통지·경로를 확인하고 ID·정답 연결→방향·좌우·box overlay→관측 범위·공식 입력→소수 실제 출력 순서의 별도 계획을 확정한다. 이번에는 환자 수·epoch·GPU 메모리·처리량을 확정하지 않는다. 후속 GPU 계획에서 두 장의 가용 메모리, worker당 2GB 여유와 batch/worker 처리량 비교를 포함한다.

동작 확인은 이번 fixture에만 해당한다. 모델 가능성 탐색·규모 확대·독립 확인은 미실행으로 유지한다. 보완 후 같은 조사나 종료된 GPU 실험을 자동 재개하지 않는다.

## 대규모 GPU 필요 후보

기준 계획의 다기관 MRI vision encoder–connector–language 공동 적응 후보는 보존한다. 이번 정정은 그 필요성이나 효과의 근거가 아니다.

# 계획의 근거 (GPT 조사 노트)

원본 agent/GOAL.md, iter_073 plan.md·review.md·review.json·구현 보고서, CODE_ASSETS.md의 iter_073 항목과 현재 rk73 소스 3개를 확인했다. research HEAD는 0e5de720949a422d8defabd0112001dbad313235이며 git status와 diff는 비어 있다. 같은 브랜치에 필요한 파일이 있어 선별 반입은 필요 없다.

기준 plan.md SHA256은 86cd9691497d35da3670ad2929876b9ee7efc53889bcacec5e19a0a7678c7ca2다. load_moaks는 통합 CSV 전체를 읽고 moaks_lookup은 전체 연골 값을 집계한다. main은 이 경로를 무조건 호출한다. fetch는 기존 파일 크기만 확인하고 새 manifest에 현재 hash를 기록하므로 사전에 고정된 hash 검증을 대신하지 못한다. test_rk73.py는 import 시 iter_073 결과 경로를 만들고 마지막에 기존 fixtures.json을 덮어쓰는 구조이므로 그대로 재실행하면 안 된다.

직전 리뷰의 1,957개 test 환자 행 집계 노출과 prior 재현 근거를 재사용한다. 구현 보고서에 포함된 과거 명령에는 통합 label의 값 분포 조회도 있어, 정정 시 정규 audit뿐 아니라 해당 기존 로그의 접근 경로를 포함해야 한다. 추가 원 label 분석으로 노출 범위를 재측정하지 않는다. 가정한 mapping의 일치율은 공식 의미나 VERSION 선택을 증명하지 않는다. 이번 계획 단계에서는 파일 수정·실험 실행·test grade 추가 분석을 하지 않았다.
