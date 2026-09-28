# 요약

- **판정:** CONTINUE / inconclusive. D488·E720의 실제 출력은 확인됐지만 E200과 최종 판정은 미완료다.
- **핵심 근거:** 계획된 primary 48명을 독립 재계산하면 B0−M0 S는 +0.2286, B0−전체 복사는 +0.0002다. 다중 사분면 22명에서는 직접 B0 0명, 규칙 11명이 성공했다.
- **의미·한계:** bbox 검출 개선만으로 질의별 선택 전이를 주장할 수 없다. oracle도 다중 사분면 0/14이므로 일반적 전이 부재나 시각적 원인은 미확인이다.
- **다음:** 평가·gate·재개 검증을 보완하고 기존 E200을 완료한다. oracle 해석 없이 seed·새 학습을 자동 확대하지 않는다.

# Assessment

리뷰 대상은 `b8be58c9f3c92266e885ca8c3f5384dbe412b4bd`다. `commit.json`, 구현 전후 `changes.patch`, 계획·보고서·실행 코드·결과와 의심 구간의 Claude 로그를 확인했다. 변경된 18개 소스는 해당 SHA와 일치했고 현재 git status/diff는 비어 있다. `unpreserved_paths`와 선별 반입 목록은 비어 있으며 execution_amendment는 없다.

이번 리뷰는 파일 생성·수정, 모델 로딩 또는 GPU 실험 없이 원시 파일의 읽기 전용 재계산으로 수행했다. D488·E720은 해석 가능한 개발 진단이므로 `valid_experiment=true`다. 다만 전체 계획 완료나 보고서의 원인 해석까지 승인하지 않는다. 전체 스냅샷 재사용은 보류한다.

# Key Findings

**출력과 입력 연결:** 완료된 1,208건에서 고정 환자×네 영역의 예상 행렬, 요청 ID 중복·누락, 주요 request-record provenance 불일치는 0이었다. stage·split·checkpoint·condition·target·prompt·adapter·config·protocol 연결을 확인했다. 영상 84개의 현재 file/raw pixel/padded input hash도 모두 일치했다. D/E60 completion의 요청 수와 worker 종료 코드도 확인했다. 현재 D/E60/E200_extra protocol의 잠긴 파일은 각각 38/34/34개 모두 현재 내용과 일치한다.

**독립 채점:** 별도 JSON 추출·좌표 검사와 최대 cardinality matching으로 재계산했다. 완료 1,208건의 parser 판정·box 불일치는 0이었다. D 점수와 저장 E60 전체 60명 집계를 재현했지만, 저장 집계는 계획한 primary 분석이 아니다.

| E60 primary 48명 비교 | 평균 차이 | 환자 bootstrap 95% CI |
|---|---:|---:|
| B0−M0 S | +0.228624 | [0.171281, 0.284445] |
| B0−Copy_B0 S | +0.000218 | [-0.030970, 0.032546] |
| Rule_B0−direct B0 S | +0.403320 | [0.318012, 0.482821] |
| reader−direct B0 S | -0.008551 | [-0.045705, 0.026010] |

primary의 평균 S는 M0 0.045139, B0 0.273763, reader 0.265212, B0 규칙 0.677083이다. B0 C_query는 0.010661, CI [-0.002794, 0.026342]다. M0 C_query의 CI 하한은 약 0.000087로 양수다. 따라서 보고서 요약의 'M0·B0 모두 CI가 0을 가로지른다'는 문장은 잘못됐다. 작은 양의 부분 효과와 신뢰할 만한 전체 선택은 구분해야 한다.

primary 내부에서 계획대로 환자 쌍을 다시 구성한 B0 real−donor S는 약 0.2009, cluster bootstrap CI는 약 [0.134, 0.267]이었다. 이는 영상별 정보 활용을 지지하지만 새로운 선택 정책 획득의 인과 증명은 아니다.

primary 다중 사분면 22명의 Q4_select는 M0/B0/reader 모두 0/22, B0 규칙은 11/22다. 직접 B0 성공률의 exact 상한 15.44%는 10% 기준을 포함하므로 정밀도 보완 확대 근거가 유지된다. boundary 12명은 별도로 보면 B0 S=0.2125이며, 그중 다중 사분면 7명은 직접 0/7·규칙 5/7이다.

**Oracle:** D24에서 O_M0/O_B0 형식은 각각 96/96 유효하지만 Q4_select는 각각 1/24다. 다중 사분면 14명에서는 모두 0/14다. 목록을 출력할 수 있다는 사실과 올바르게 선택한다는 사실은 다르다.

**미완료 범위:** 리뷰 시 읽은 E200_extra V_M0에는 405건이 있었고 completion은 없었다. V_B0와 RD_M0의 해당 추가 생성은 아직 없었다. 이는 보고서의 약 368건 이후 진행된 부분 상태이며 완료 증거가 아니다. 저장 attempt의 running 표기만으로 호스트 프로세스 생존을 확정하지 않는다.

# Problems / Concerns

1. **계획과 다른 집계:** `eval_iter026.py`는 primary와 boundary를 합쳐 주지표·CI·donor mapping을 계산한다. 진부분집합 22명만 수정됐으며 주요 분석의 분리는 남았다. donor invalid를 NaN으로 제외하는 것도 0점 처리한 real과 비대칭이다.
2. **Decision 결함:** E60 기능적 차이 조건은 C_query 점추정≥0.05인데 코드가 CI 하한≥0.05로 바꿨다. reader 차이 부호도 반대다. 이번 확대는 독립적으로 정밀도 조건이 성립하므로 취소할 이유는 없지만 코드는 수정해야 한다. E200 classifier와 seed decision이 요구하는 `primary`, `valid_rate_primary`는 실제 report에 없다. seed decision에는 oracle 해석 조건도 빠져 있다.
3. **Gate 미완성:** D decision은 형식률만 확인한다. 계획된 통제 중단·재개·변조 거부 검사 없이 E로 진입했고, launcher·worker·평가에서 선행 decision 검증이 강제되지 않는다. 현재 원시 출력의 독립 감사는 통과했지만 이를 일반적인 실행기 신뢰성으로 확대할 수 없다.
4. **출처 잠금 부족:** protocol은 실제 top-level 평가·launcher·decision, 원시 bbox source와 completion, checkpoint manifest를 필수로 잠그지 않는다. evaluator는 provenance와 completion을 검사하지 않고 요청 파일을 따라 읽는다. 이번 기록의 독립 대조 통과와 향후 변조·누락 거부 능력은 별개다.
5. **Oracle 해석:** `O_TMPL`은 숫자 배열 목록을 제공하면서 원래 `box_2d`와 label을 그대로 반환하라고 요구한다. 이 schema 불일치와 낮은 선택 성능 때문에 지시·좌표 인터페이스 설명이 남는다. oracle 실패는 사전 계획상 direct E 평가의 중단 gate는 아니지만 일반적 전이 부재 주장과 조건부 seed 확대를 제한한다.
6. **Sanity 범위:** `sanity_post.json`의 14/14는 D의 한 V_TL 입력 tensor 대조, B0 digest와 이번 V/O 8건 재생성이다. 과거 iter_012 bbox baseline 재현 8건과 다르다. 공통 tensor key만 비교하며 검사 실패의 비정상 종료도 강제하지 않는다.
7. **누락 분석:** M0 concise 규칙·복사 baseline과 IoU@0.5, 요청 밖 FP·복사율·영역별 결과 등 계획된 분석이 빠졌다. E200·seed 생성부터 최종 판정까지 코드가 모두 준비됐다는 보고서 설명은 과장됐다.

# Interpretation

B0는 현재 primary에서 M0보다 높은 공간 검출 성능을 보이지만, 전체 bbox를 반복 반환하는 baseline보다 낫다는 근거는 없다. 다중 사분면 Q4_select의 직접 0/22 대 규칙 11/22는 외부 규칙을 강한 baseline으로 유지할 이유다. 다만 차이가 유의하지 않다는 사실은 두 방법의 동등성 증명이 아니며, 검출 품질이 개선의 '대부분'을 인과적으로 설명한다고 확정할 수도 없다.

E60은 기존 확인 집단을 후속 개발에 사용한 자료다. 새 독립 확인이 아니며 이번 반복은 새 학습을 수행하지 않았다. MRI F139·reserve를 열거나 원래 RSNA SFT 성과를 기각할 근거는 없다.

iter_025 marker 분석은 27건을 구제했고 그중 20건 정답·7건 오답이었다. 저장 분석상 OB_T 정답 추가 17건, OC_T 3건이다. 이는 기존 형식 누락의 보완이며 새로운 능력 성공으로 세지 않는다.

# Strategy Check / 연구 방향 판단

- **실행 유효성:** 완료된 D/E60의 입력·출력은 독립 감사 범위에서 유효하다. 전체 실행·재개 보증과 E200 완료는 별도 미해결 사항이다.
- **성능 개선:** primary B0−M0 +0.2286은 재현됐다. 전체 복사 대비 추가 개선은 불확정이며 규칙 경로가 더 높다.
- **가설 지지:** 신뢰할 만한 질의별 전체 선택이 제한되는 패턴은 관찰됐다. oracle 실패 때문에 일반적 시각 전이 부재와 지시·좌표 해석을 분리하지 못했다.
- **신규 기여 가능성:** 영역 질의 자체나 단일 RSNA 격차는 contribution이 아니다. 실제 사용 조건에서 직접 질의 SFT·모듈형 대안 대비 필요한 이점은 미확인이다.

iter_026 계획의 전략 비교는 아직 유효하다. 지금은 추가 loss 개선이나 다른 task 전환보다 이미 확대 기준을 충족한 E200을 정확히 마무리하는 정보 이득이 크다. 완료 후에도 oracle 해석이 남으면 seed를 자동 추가하지 않고 현재 인터페이스 진단의 한계와 다음 투자 가치를 판단한다. 광범위한 문헌 조사나 새 benchmark 구축은 이번 복구의 선행 조건이 아니다.

두 GPU에 각각 두 worker를 사용했고 E60의 장치별 peak는 최대 약 17,897 MiB로 기록됐다. 두 worker에 필요한 총 4 GiB 여유를 남겼다. pilot의 동일 24건 token은 2/4 worker 간 모두 일치했지만 모두 M0였고, 4 worker 처리량은 2.33 req/min으로 2 worker의 2.41보다 낮았다. 기존 실측 재사용의 이유는 기록됐으나 새 prompt에서 4 worker가 더 빠르다는 증거는 아니다. 이는 현재 출력 무효 사유가 아니다.

논문 추천은 보류한다. 이번 결과는 불확정 진단이며 oracle·평가 결함과 미완료 확대가 남아 있어 특정 방법 방향의 유망성이 확인됐다고 보기 어렵다.

# Recommended Next Experiment

현재 호스트의 launcher·worker·lock·종료 상태부터 확인한다. 살아 있는 실행은 중복 시작하거나 소스를 변경하지 않는다. 완료·부분 출력과 기존 protocol/report를 보존한다.

필요한 평가·decision·provenance·실행 수명 관리만 보완하고 실제 중단/재개·변조 거부를 검증한다. 수정 평가 결과는 기존 파일을 덮어쓰지 않는 별도 경로에 남긴다. 정밀도 확대 조건이 유지되므로 입력·prompt·표본·metric은 그대로 두고 유효한 E60·E200 부분 출력을 재사용해 E200을 완료한다.

그 뒤 원 계획의 양성·음성·불확정 기준을 적용한다. oracle 실패를 숨기거나 사후에 기준을 완화하지 않는다. B29/B43은 실제 조건을 충족할 때만 실행하며, 새 loss·학습·외부 자료·reserve는 자동 투입하지 않는다.