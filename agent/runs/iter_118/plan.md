# 요약

- **이번에 할 일:** 미사용 RSNA 환자 최대 192명에서 초안 없음·맞는 초안·틀린 초안을 비교한다. 영상·자동 위치 근거·공통 지시는 고정한다.
- **필요한 이유:** iter_117의 초안 없는 조건이 교정한 8건에서 초안 포함 조건은 잘못된 방향을 유지했지만, 초안 영향과 평가·기초 수행을 분리하지 못했다.
- **확인할 기준:** 명시적 오답으로의 변화와 유보·거부 증가를 별도로 측정하고 초안 무시·detector·단순 합의와 비교한다.
- **주의·다음:** 합성 개입의 개발 진단이다. 기존 696요청·원 판정·SELF_CHECK FAIL을 보존한다. 종료 후 full 리뷰와 사용자 승인 대기를 유지한다.

## 알림 맥락

- 연구: 오류 혼합 근거의 선택적 교정
- 데이터: 흉부 X-ray RSNA의 미사용 개발 환자
- 모델: frozen MedGemma 1.5와 기존 RSNA detector, 새 학습 없음
- 과제: 같은 영상과 자동 위치 근거에서 초안만 바꾸고 소견 존재 답변을 비교
- 가설: 틀린 초안이 답 방향을 바꾸거나 유보를 늘릴 수 있음
- 질문: 영상과 자동 근거가 같아도 틀린 초안 때문에 올바른 판단이 흔들리는가?
- 변경: 구체화
- 연결: 기존 선택 집단의 초안 유지 관찰 → 미사용 환자에서 초안 내용만 바꾸는 대조
- 작업: 세 조건을 한 번 생성해 내용 오류·유보 증가·단순 대안의 충분성을 구분

# Current Understanding

iter_117은 유효한 본비교지만 성능 판정은 inconclusive다. 불일치 87명의 R은 교정 0/40, unresolved 43/87이고 resolved 44건 모두 초안을 유지했다. E가 교정한 8명의 R 원문도 잘못된 초안 방향을 보였다. 이는 출발 관찰이며 신규성·일반 교정 불능의 근거가 아니다.

기준 기록은 agent/runs/iter_117/plan.md, SHA256 `ff0a00dcad2e7e9e22023e3882207f9f315a6cde2da95cf53ef313567c3a9337`, review.json 및 원 출력이다. 이번은 원 실험의 gate 완화나 재채점이 아닌 별도 설계다.

유지: 모델 revision·공식 영상 전처리·detector checkpoint/운영점·단일 표적 질문·기존 기록. 변경: 새 환자, 합성 정오 초안, 동일 공통 지시, 답 방향과 유보의 분리 평가. 보류: frozen R 확대, LoRA, 자유 판독문 의미 평가, prompt 순회. 미완료: reserve의 실제 미사용 여부와 선택 영상 연결은 구현 단계에서 한정 확인한다.

# Strategy Check / 연구 방향 판단

직전 리뷰와 사용자 승인이 선택한 질문을 구체화한다. 후보 전수 조사를 반복하지 않는다.

**기술 질문 → 실패 조건 → 공개 정답 비교 → 주장 범위:** 자동 근거가 있는 판단에서 초안 내용의 영향 → 잘못된 초안이 초안 없는 정답을 오답 또는 유보로 바꾸는 조건 → 같은 환자의 없음/정답/오답 초안과 명시적 RSNA 존재 정답 비교 → 현재 모델·단일 질문·합성 개입·동일 원천 개발 환자에 한정한다.

**시험 설정:** 기존 R 성능 확대는 보류한다. 이번에는 한 번의 세 조건 진단만 시행한다.

**연구 관찰:** 8건의 원문 관찰을 유지하되 favorable 사례를 새 표본으로 사용하지 않는다. 기존 E/R 안내 문구도 달랐으므로 이번에는 공통 지시를 고정한다.

**연구 질문:** 초안 민감성은 이미 선행이 다룬다. 중요한 잔여 조건과 단순 대안의 한계를 확인할 때만 후속 가치가 있다. 양성만으로 새 방법 필요성을 선언하지 않는다.

대안은 지금 보류하는 것이다. 현재는 사용자 승인과 구체적인 paired 개입의 정보 가치 때문에 한정 비교를 선택한다. 음성·판별 불가이면 이 후보를 보류하고 iter_115의 CURE 특화 투자 보류로 복귀한다. 이는 다른 실험 자동 재개를 뜻하지 않는다.

다른 모델 계열은 이번에 추가하지 않는다. 한 모델에서 초안 내용 효과를 먼저 분리하며, 기본 수행이 약하면 그 범위로 해석한다. 타 모델 재현을 이번 진입 gate로 요구하지 않지만 일반 VLM 주장도 하지 않는다.

# Hypothesis

주가설은 틀린 초안이 초안 없는 판단에 비해 명시적 오답 전환을 순증가시킨다는 것이다. 맞는 초안은 방향 특이성을 확인하는 대조다. 두 초안이 모두 주로 유보를 늘리면 내용 추종보다 초안 추가에 따른 응답 방식 변화가 우선 설명이다.

환자 i의 조건은 E=초안 없음, C=정답 방향 초안, W=오답 방향 초안이다. 정오 표시는 평가 전용이다. 모델에는 자동 초안의 Yes 또는 No만 보인다. 자연 발생 초안 오류의 빈도나 임상 효용은 추정하지 않는다.

# Limitation Evidence / Correct Usage Checks

대상은 `rsna-noisy-evidence-draft-retention`, observed다. iter_117 review.json의 valid_experiment=true, blocking_issues 없음, prompt 재구성·입력 및 출력 hash·EOS·processor 대조 근거를 확인했다. 방법 개발 gate로 사용하지 않으며 diagnostic/method_stage=none이다.

기존 ev109_extract_v1 점수는 보존한다. 새 평가기는 이번 요청에만 적용한다. 모델의 명시적인 답과 뒤따르는 불확실 표현을 다른 축으로 기록한다. 임상 문장 의미를 새로 추론하거나 LLM judge를 사용하지 않는다.

worker의 GT hash 접근과 launch 재개 문제는 이번 실행 전에 수정한다. 성공한 기술 테스트를 과학적 발견으로 보고하지 않는다.

# Contribution Path / Baselines / Reuse

[Anatomically-Grounded Fact Checking](https://arxiv.org/abs/2412.02177)은 소견·위치 오류 검증과 교정을 이미 다룬다. [To Agree or To Be Right?](https://arxiv.org/html/2603.22623v1)는 의료 VLM의 초기 답과 권위적 압박 이후 답 변경을 평가한다. 이번은 권위 압박 없이 자동 detector 근거를 고정한 합성 초안 대조다. 이러한 조건 차이 자체는 신규 contribution이 아니다.

실용 단순 대안은 다음과 같다.

- E: 초안을 무시하고 영상+자동 근거로 답한다. 추가 교정 호출 없이 이 답을 최종 출력하는 대안이다.
- B: 고정 detector의 threshold 이상 box가 있으면 Yes, 없으면 No. 이는 자동 규칙이며 빈 box가 임상적 정상이라는 뜻은 아니다.
- D: 해당 합성 초안을 그대로 유지한다. C/W의 정오가 구성상 결정된다는 점을 표시한다.
- S_C/S_W: E의 명시 답과 B가 일치하면 그 답, 아니면 해당 초안을 유지한다. E가 모호하면 초안을 유지한다. 유보 flag도 따로 전달해 확정 성능을 과장하지 않는다.

기존 M은 추가 SFT 출력이 필요하다. 새 환자에서 M을 만들기 위한 추가 모델 실행은 하지 않으며 이전 54/87과 직접 비교하지 않는다. S도 새 입력에서 계산한 변형임을 밝힌다. 이 실험은 기존 교정 시스템이나 직접 교정 SFT를 이겼다는 근거가 아니다.

현재 브랜치 HEAD `ae15ee5bde73c415715f127720ffdcf24f60d2cc`의 ed117_run.py, ed116_build.py, ed116_spec.py, pg43_run.py, rsna_diag/generate.py·geometry.py·qa_spec.py를 필요한 범위에서 재사용한다. ed117 평가기는 기존 지표 회귀 참고로만 쓰고 이번 판정을 그대로 맡기지 않는다. 새 파일은 ed118 계열로 구분하고 결과는 results/iter_118 아래에 둔다. 같은 접근법 브랜치를 유지하며 전체 스냅샷을 승인본으로 취급하지 않는다.

선별 반입은 reuse_assets의 det_lib.py, rsna_data.py, dicom_min.py다. 의존 geometry·__init__은 현재 파일을 사용해 연결 검증한다. 과거 실행기·전체 자료 감사·학습 코드를 반입하거나 재구현하지 않는다.

# Proposed Experiment

## 1. 자료와 표본 잠금

기존 `results/iter_010/manifests/reserve_patients.json`을 후보 출발점으로 사용한다. 현재 후보 수는 opacity 496, normal 5,562, not_normal_no_opacity 2,050명이다. 이 수를 실제 미사용 수로 보고하지 않는다.

공식 자료는 `results/iter_009/source/raw/`의 adjudicated annotation JSON, mapping JSON, 영상 ZIP이다. Calculated의 Lung Opacity / Normal / No Lung Opacity–Not Normal만 정답으로 사용한다. 미표기는 음성으로 바꾸지 않는다. patient 단위는 mapping의 NIH 8자리 접두어다. 무작위 DICOM PatientID만으로 독립성을 판단하지 않는다.

기존 RSNA/NIH 학습·validation·confirm·pilot·수동 평가와 이후 사용 manifest의 환자 ID를 합쳐 제외한다. 특히 iter_009/010, E600/confirm800, iter_112, 수동 report-transfer 사용 이력을 확인한다. 관련 manifest를 찾는 범위로 제한하며 모델 출력 내용 전수 감사는 하지 않는다. ID 연결이 불확실한 후보는 사용하지 않는다. 선택 집단은 SOP와 decoded pixel 중복도 확인한다. 전체 과거 이미지 재디코딩 대신 보존 hash를 활용한다.

category별 `sha256('iter118|'+patient)` 오름차순으로 선정한다. 환자당 적격 영상 하나는 SOP 문자열 오름차순 첫 영상으로 고정한다. 모델 결과·detector 정오로 환자를 고르지 않는다. 대표 6명의 annotation·영상·좌표·음성 의미를 확인하고 제외 이유를 기록한다.

별도 TECH는 category별 2명씩 총 6명이다. 본표본은 opacity/normal/not_normal_no_opacity=96/48/48명, 총 192명이다. 2:1:1은 표적 양성과 음성을 균형 있게 두면서 두 음성 종류를 보존하기 위한 개발 설계다. 원천 유병률 추정이 아니다.

자료가 부족하면 출력 전에 m=min(48, floor(사용 가능한 opacity/2), normal, not_normal_no_opacity)로 정해 2m/m/m명을 사용한다. TECH는 먼저 제외한다. m=0이거나 정답·환자 연결이 성립하지 않으면 생성하지 않는다. 작은 집단도 탐색은 가능하지만 정밀도 부족을 명시하며 다른 자료·기존 평가 환자로 보충하지 않는다. 선정 manifest와 제외 출처를 본출력 전에 잠근다.

192명에서는 paired discordance가 약 0.25일 경우 차이의 95% 구간 반폭이 대략 7pp다. 이는 가정에 따른 설계 참고이며 실제 discordance에 따라 더 넓어진다. 10pp 수준의 큰 내용 영향을 판별할 한정 탐색 규모로 선택한다. 작은 효과를 확증하거나 음성을 보장하는 power 설계는 아니다.

## 2. 자동 근거와 세 조건

기존 detector17 epoch18, checkpoint SHA256 `576b8d789ef5f9e1924d7ad6e56954d51589dc437eaa12215874ce77cd3cc76c`, threshold0.70을 유지한다. 원본 영상에서 새 환자의 box/score를 한 번 생성한다. threshold·NMS·후보 cap을 조정하지 않는다. ed116_spec.packet_text의 원본 pixel→fraction 변환과 score/좌표 순서를 재사용한다. 자동 packet은 GT로 정제·선택하지 않는다.

모델은 MedGemma 1.5의 기존 고정 revision, adapter=None, bf16, greedy, 공식 chat template와 기존 값 보존 영상 경로다. 질문은 rsna_diag.qa_spec.Q_O 그대로다.

세 조건 공통 prompt 구조는 아래와 같이 고정한다.

`Question: {Q_O}`

`{optional draft line}`

`{detector packet}`

`The detector output and any first-pass answer provided may each be wrong.`

`Use the information available to you to answer the question about this chest radiograph. Answer only yes or no.`

E에는 draft line이 없다. C/W에는 `An automatic first-pass answer to this question was: Yes.` 또는 `No.`를 사용한다. 정답 방향 또는 반대 방향으로 만드는 작업은 부모에서 수행한다. 모델에는 correct/incorrect, category, GT box, 정오 condition 이름을 전달하지 않는다. 요청 metadata도 불투명 조건 ID와 prompt만 사용하며 C/W 매핑은 평가 파일에 둔다.

각 환자는 세 독립 대화로 생성한다. 대화 history를 공유하지 않는다. 영상 tensor와 packet hash는 세 조건에서 동일해야 한다. 조건 순서는 환자 hash에 따라 균형 회전해 실행 순서 영향을 줄인다. 주 생성 seed와 config를 잠근다.

## 3. 출력 전 평가 고정

출력마다 `direction={yes,no,unknown}`와 독립 flag `hedged`, `conditional`, `contradictory`, `refusal`, `parse_failure`, `non_eos`를 기록한다. 원문 근거 span도 저장한다.

명시적인 답은 응답 시작의 Yes/No 또는 `Final answer:`/`The answer is`/`Therefore, the answer is` 뒤의 명시 Yes/No로 제한한다. 질문·초안 인용 안의 답은 제외한다. 시작 답과 최종 답이 반대이고 명시적 자기정정 표시가 없으면 contradictory/unknown으로 둔다. 질병 서술만으로 Yes/No를 추론하지 않는다.

`Yes. ... could ...`는 direction=yes와 hedged flag를 함께 기록한다. `If ... then yes`처럼 조건에 종속된 답만 있으면 direction=unknown, conditional=true다. `I cannot determine ...`만 있으면 refusal/unknown이다. 모호한 자동 해석은 unknown으로 보존한다. 단순 hedge 단어 하나로 명시 답을 삭제하지 않으며, hedge 검사는 답 주장에 붙은 표현과 일반적인 후속 권고를 구분하는 한정 규칙으로 고정한다. 확정 답은 명시 방향이 있고 hedge/conditional/contradiction/refusal/nonEOS가 없는 응답이다.

명시 답·유보 동반 답·조건부·거부·초안 인용·질문 반복·모순·자기정정 fixture를 생성 전 고정한다. GT나 본출력을 보고 규칙을 고르지 않는다. 파싱 규칙을 구현한 뒤 본생성 전에 코드/hash를 봉인한다. 예상하지 못한 문형은 unknown으로 남기고 원문 사례를 보고하며 사후 구제 규칙을 추가하지 않는다.

## 4. 동작 확인과 본비교

TECH 6명×3조건=18요청에서 입력 연결·tensor 동일성·출력 저장·접근 분리·재개를 검사한다. 정답률이나 oracle 100% 성공을 gate로 쓰지 않는다. 전부 거부하거나 기본 수행이 낮아도 기술적으로 유효한 출력이면 본표본을 정답률로 재선택하지 않는다. 본비교는 기초 수행 자체를 함께 측정한다.

새 명세의 기술 요청으로 2 worker와 4 worker를 최대 한 번 비교한다. 추가 반복은 18요청이다. 별도 기술 요청 6회 이내로 정상 중단 후 같은 명령의 재개·완료 요청 보존을 확인한다. 총 반복 실행 슬롯은 24회를 넘지 않는다. 동일 greedy 출력 token과 요청 수를 비교한다. 불변 processor/가중치 검증은 iter_117 출처를 연결해 재사용하고 변경된 요청 경로만 검사한다.

기술 무결성이 통과하면 잠근 본표본 세 조건을 한 번 생성한다. 초안 없는 답이 맞는 환자만 골라 실행하지 않는다. 중간 성능 확인에 따른 조기 종료·확대는 없다. 학습·추가 seed·다른 모델·독립 도메인 확인은 이번에 하지 않는다.

## 5. 자원·예산·재개

최대 고유 VLM 요청은 TECH18+MAIN576=594개다. 처리량·재개 반복을 포함해 최대 618회 실행 슬롯이다. 각 슬롯은 비EOS일 때만 1000→2000→4000 token 재시도를 허용해 최대 1,854 attempts다. EOS 답이 마음에 들지 않는다는 이유로 재시도하지 않는다. 마지막 비EOS는 unknown으로 보존한다. 추가 correctness oracle 요청은 없다.

detector는 새 환자 최대198명과 기존 회귀 영상2명만 추론한다. 기존 detector 환경의 절대 Python 경로를 확인하고 사용한다. 새 환경이 필요하면 승인된 격리 경로를 사용하며 기본 환경과 hf_cache를 변경하지 않는다.

실행 직전 nvidia-smi로 GPU0,1의 실제 여유·상속 장치 대응을 확인한다. detector 완료 후 VLM을 배치해 불필요한 동시 상주를 피한다. VLM은 GPU당2 worker를 유망 후보로 두되 동시 peak 합과 worker당2GiB 여유를 확보해야 한다. TECH에서 처리량·peak VRAM·긴 출력 지연·OOM·CPU/RAM/I/O 경합과 token 정합성을 확인한다. 안전 여유가 부족하거나 이득이 없으면 GPU당1 worker를 사용하고 근거를 기록한다.

iter_117의 본생성 실측은 696요청/873.879초, 약47.79요청/분이다. 유사 길이를 가정하면 기본618회 약13분이며 loading·detector·재시도·검증은 추가다. 실제 TECH 처리량으로 예상 wall-clock을 갱신한다. 이 추정은 시간 상한이 아니다.

고유 request ID, 원자적 claim, worker별 파일, source/input/config digest를 유지한다. execution_start 존재만으로 재개를 거부하지 않게 하고 append-only 실행 이력을 남긴다. 살아 있는 소유자의 claim을 지우지 않는다. 재개 시 완료 행의 현재 입력과 protocol을 먼저 검증하고 누락만 실행한다. 부분 행은 보존·격리 후 명시적으로 복구하며 원본을 덮어쓰지 않는다. 실제 사용하는 정상 중단·재개와 동시 launch 거부를 검사하되 범용 SIGKILL 보장을 주장하지 않는다.

# Implementation Tasks for Claude

1. 사용자 최신 승인, iter_117 원 리뷰·SELF_CHECK FAIL, iter_115 복귀 기준을 확인한다. 이번 결과 경로와 원본 보존을 명시한다.
2. reuse_assets의 세 파일을 확인하고 현재 의존 파일과 연결한다. 실제 이용할 loader·detector helper만 검증한다.
3. reserve에서 기존 사용 환자를 제외하고 공식 정답·영상 연결을 확인한다. 선택·제외 manifest와 TECH/MAIN을 잠근다.
4. 부모의 평가 provenance 검사와 생성 전용 protocol을 분리한다. 생성 worker import·verify 경로가 GT/labels/evaluation lock을 읽지 않게 한다.
5. worker 경로에 GT 읽기 거부 fixture를 적용하고 실제 TECH에서도 파일 접근 기록으로 확인한다. 이미지·가중치·generation code·요청만 생성 잠금에 둔다. 정오 매핑과 평가 파일 digest는 부모에서 검사한다.
6. detector를 GT 없는 loader로 실행하고 자동 packet을 고정한다. 같은 환자의 세 요청에서 영상·packet·공통 지시가 동일한지 재구성 검증한다.
7. 명시 답/유보 분리 평가와 합성 반례 fixture, paired 계산·unknown 범위 verifier를 생성 전에 고정한다.
8. TECH와 한정 처리량·재개 검사를 완료한 뒤 MAIN을 한 번 실행한다. 새 request를 기존 결과 경로에 쓰지 않는다.
9. 전체 분모의 전이표, 기초 수행, category별 결과, 단순 대안과 비용을 산출한다. 독립 verifier로 원출력→추출값→계수→CI→판정 연결을 확인한다.
10. claude_report.md에 실제 규모·미실행·비용·운영 준수와 과학적 관찰을 분리해 보고한다. full 리뷰 뒤 사용자 승인을 기다린다.

# Evaluation (성공/실패 기준 포함)

## 주지표와 전체 분모

각 조건에서 전체 N을 분모로 명시 정답·명시 오답·unknown, 확정 답변률, hedge/conditional/refusal/contradiction/parse_failure/nonEOS를 보고한다. valid-only 정확도로 주결론을 대체하지 않는다.

주 내용 손상 지표는 `H=[n(E 정답,W 오답)−n(E 오답,W 정답)]/N`이다. 명시 방향의 전환만 센다. unknown은 이 지표의 방향 전환으로 세지 않고 모든 unknown 전이 셀을 별도 보고한다. C에서도 동일한 전이표와 지표를 계산한다. C와 W의 정답률 차이만으로 초안 없는 판단의 손상을 주장하지 않는다.

환자 단위 category 내 paired bootstrap 10,000회, seed11817로 H와 조건 차이의 95% CI를 계산한다. 선택 비율을 고정하고 세 조건을 같은 환자 단위로 resample한다. 주검정은 E/W의 H 하나다. 나머지 CI와 하위집단은 설명용이며 여러 유의한 항목 중 하나를 골라 양성으로 선언하지 않는다.

사전 하위집단은 category, detector 정답/오답, E의 명시 정답/오답/unknown이다. E 정답 하위집단의 W 오답 전환과 C 보존은 조건부 진단이며 전체 모집단 효과로 보고하지 않는다. 전체 N과 모든 반대 전이를 함께 제시한다. E 정답+B 정답인데 W 오답인 사례도 전수 보고하되 별도 성공 gate는 아니다.

unknown을 정답 또는 오답으로 배정한 정답률 차이의 보수적 범위를 함께 계산한다. 같은 E가 S와 여러 차이에 들어가면 공유 변수로 처리한다. 명시 답의 손상 관찰과 unknown까지 포함한 전체 정확도 효과가 서로 다른 결론일 수 있다.

## 위치 및 단순 대안

B와 E/C/W/S의 동일 환자 정답·확정 응답·unknown을 비교한다. 위치는 고정 detector box의 공개 주석 정합성을 보조 보고한다. 최종 Yes일 때 box 유지, No일 때 제거하는 공동 성공은 양성에서 모든 GT/pred의 IoU0.3 일대일 대응, 음성에서 No+빈 출력으로 정의한다. unknown은 공동 성공으로 세지 않는다. box 경계 개선이나 위치 정보의 인과 사용은 검증하지 않는다.

E는 초안 제거 대안이며 같은 한 번의 VLM 호출 비용이다. S는 E+B 이후 CPU 규칙 비용이고 자연 초안 생성 비용은 이번에 측정하지 않는다. detector·VLM별 실측 시간, 준비·검증 시간과 재사용 자산의 과거 학습 비용을 구분한다.

## 사전 결과별 판단

- **양성 내용 관찰:** H≥0.10이고 paired95% CI 하한>0일 때 큰 내용 손상 신호로 분류한다. 10pp는 10명당1명 수준의 순 명시 오답 전환을 다음 투자 검토 대상으로 삼는 개발 기준이며 임상 허용치가 아니다. unknown 범위 때문에 전체 정확도 효과가 불확정이면 이를 함께 명시한다. C/W·유보 전이로 방향 특이성을 해석한다. 자동으로 방법 pilot에 진입하지 않는다.
- **작은 영향 또는 음성:** H의95% CI 상한<0.10이면 현재 설계에서 큰 내용 손상 근거가 약하다고 보고한다. H가 양수여도 작은 효과 가능성은 보존한다. 차이가 주로 unknown/hedge 증가에 있으면 '유보 증가'로 보고하며 오답 추종으로 바꾸지 않는다.
- **불확정:** 위 둘이 아니거나 기본 정답·전환 사건이 적어 구분이 안 되면 불확정이다. 자료·parser의 범위와 전체 분모를 제시하고 이번 후보를 보류한다. 같은 자료 추가 생성이나 평가기 정비로 연장하지 않는다.

양성이라도 E 또는 S가 같은 비용에서 충분하면 초안 무시/합의라는 단순 대안의 가치를 받아들이고 새 교정 방법 투자는 보류한다. 그 이후에도 중요한 잔여 조건이 있으면 가장 가까운 선행과 구별할 질문 하나를 제안만 한다. 음성·불확정이면 iter_115 복귀 기준을 적용한다. 연구 질문 전체를 기각하거나 목표 완료로 표시하지 않는다.

# Risks / Checks

- 미사용 환자는 우리 실험의 새 개발 표본이다. 같은 RSNA이므로 독립 도메인 또는 MedGemma 사전학습 미노출이라고 부르지 않는다.
- GT는 합성 초안 구성과 평가에 사용된다. 정답 초안 자체의 의도된 정보 제공과 평가 파일의 비의도적 누수를 구분한다. 모델에는 정오 표시를 주지 않는다.
- reserve의 과거 사용 여부를 추측하지 않는다. 제외 provenance가 성립하지 않는 환자는 사용하지 않는다.
- 새로운 명시 답 평가를 iter_117의 696출력에 적용하지 않는다. 원 불확정 판정과 운영 위반을 보존한다.
- 범용 자유 판독문 평가기·전문의 대체·LLM judge를 만들지 않는다. 처리할 수 없는 문형은 unknown이다.
- packet 고정은 위치 근거의 인과적 사용을 증명하지 않는다. 초안 내용 개입의 제한된 출력 효과만 검증한다.
- 이전 M/S 점수를 새 환자와 비교하지 않는다. 이번 S의 정의·입력·비용 차이를 명시한다.
- 전체 스냅샷·과거 detector 실행기의 재사용 승인은 하지 않는다. 현재 호출 경로의 결함만 수정한다.
- **대규모 GPU 필요 후보:** 여러 기관의 자연 초안·자동 근거 오류를 포함한 verifier/editor 공동 post-training은 장기 후보로 보존한다. 현재 필요성과 신규성은 미확정이며 이번에 실행하지 않는다.
- GOAL·Claude 구현·standard 등급·GPU0,1·--confirm-each-iter를 유지한다. Telegram에는 초안에 따른 명시 오답, 유보 증가, 판별 불가를 구별해 보고한다.

# 계획의 근거 (GPT 조사 노트)

원 GOAL, iter_117 review.json과 계획, iter_115 리뷰, iter_116 명세·계획, LIMITATIONS의 대상 항목, CODE_ASSETS의 관련 항목을 확인했다. iter_117 plan.md SHA256은 ff0a00dcad2e7e9e22023e3882207f9f315a6cde2da95cf53ef313567c3a9337이다. 이번은 해당 계획의 재실행이 아니라 승인된 별도 개입이다.

현재 research HEAD는 ae15ee5bde73c415715f127720ffdcf24f60d2cc이며 git status/diff에 변경이 없다. ed117_run.py는 평가 잠금 전체를 worker에 전달하고 execution_start.json 존재 시 재개를 막는다. 실제 재사용 경로만 보완한다. ed116_spec.py에서 이전 E와 R은 초안뿐 아니라 안내 문장도 달랐음을 확인했다. 이번에는 공통 지시를 동일하게 둔다.

iter_010 reserve_patients.json에는 opacity 496명, normal 5,562명, not_normal_no_opacity 2,050명이 있다. 이는 후보 수이며 현재까지 미사용임을 아직 확인한 수가 아니다. 공식 annotation·mapping·ZIP은 iter_009/source/raw에 있고 기존 adapter는 Calculated 라벨과 NIH 8자리 patient ID를 사용한다. 현재 분할과 이후 사용 이력을 대조한 뒤 새 표본을 잠근다.

iter_035 원 리뷰에서 det_lib.py의 모델·단독 추론 보조가 승인됐음을 확인했다. 해당 blob과 rsna_data.py/dicom_min.py의 실제 코드를 읽었고 현재 브랜치에 없는 세 파일을 선별 반입한다. 이전 detector 실행기의 재개 결함까지 반입하지 않는다.

[Anatomically-Grounded Fact Checking](https://arxiv.org/abs/2412.02177)은 소견·위치 오류 검증 및 교정을 다룬다. [To Agree or To Be Right?](https://arxiv.org/html/2603.22623v1)는 의료 VQA에서 초기 답 이후 권위·동료 합의·인용 압박에 따른 답 변경을 다룬다. 따라서 초안 민감성 자체의 신규성은 주장할 수 없다. 이번의 자동 위치 근거 고정·정오 초안 대조는 제한된 잔여 조건을 검사하며 선행 대비 방법 우위 실험은 아니다.
