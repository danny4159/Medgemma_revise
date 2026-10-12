# 요약

- **이번에 할 일:** 같은 질문 유지 · 본비교 실행 복구. 고정 174명에서 696요청을 한 번 수행한다.
- **필요한 이유:** iter_116은 영상 없는 조건의 응답 기준 때문에 멈췄으며 교정·보존 효과는 아직 검증하지 못했다.
- **확인할 기준:** 원 성능 기준을 유지한다. 별도로 강한 단순 대안 이후 중요한 실패 조건이 남는지 판단한다.
- **주의·다음:** 반복 개발 RSNA의 선택 집단이다. 새 학습·prompt 탐색·자동 연장은 없으며 리뷰 뒤 사용자 승인을 기다린다.

## 알림 맥락

- 연구: 위치 근거와 의료 VLM 판단의 연결
- 데이터: 흉부 X-ray RSNA 개발 E600의 고정 부분집단
- 모델: frozen MedGemma 1.5, 저장 detector17 및 grounding SFT 출력; 새 학습 없음
- 과제: 영상·이전 yes/no 판단·자동 위치 근거를 받아 지정 opacity의 최종 yes/no를 출력한다
- 가설: 유용한 조언 선택이 가능할 수도 있지만 초안 고수·근거 추종·단순 합의로 충분할 수도 있다
- 질문: 틀릴 수 있는 자동 근거를 보고 잘못된 답만 고칠 수 있으며, 실패한다면 단순 대안으로 설명되지 않는 문제가 남는가?
- 변경: 실행 복구
- 연결: 기술 검사에서 영상 없는 조건이 5/12만 답변을 확정해 본비교가 중단됐다. 사용자 승인으로 이 조건의 응답 성공만 필수 gate에서 분리한다
- 작업: 같은 174명의 실제 교정·손상과 비교군 결과를 평가하고 성능 성공과 연구 관찰의 가치를 따로 보고한다

# Current Understanding

기준 문서는 `agent/runs/iter_116/plan.md`, SHA256 `be752099da4cd90c2b14fe16ac4659b054de1cb114111364c8dcf8b93a46d009`다. 원 계획과 `agent/runs/iter_116/review.json`을 먼저 읽는다. 이번 amendment와 충돌하지 않는 원 입력·metric·평가 조건을 상속한다.

**유지:** 동일 87명 불일치·87명 일치 대조, TECH12명, prompt와 packet 문자열, parser, 모델 revision, detector 운영점, 생성 설정, 성능 기준, bootstrap, 원본·실패 기록.

**변경:** T의 resolved≥6/12만 본평가 필수 조건에서 제외한다. T 자체의 입력 무결성·결과 저장은 유지하며 응답 거부와 unresolved를 보조 보고한다. 필요한 verifier와 processor tensor 검증을 보완하고 새 결과 경로를 쓴다. 성능 판정과 연구 관찰 가치 판단을 분리한다.

**미완료:** MAIN 174명·696요청 및 실제 출력에 대한 본평가·독립 검산이다. 기존 TECH_w2/TECH_w4 각각48건, RESUME8, 직접 생성 대조4건은 재생성하지 않는다.

iter_116의 execution_failed와 valid_experiment=false는 유지한다. 기존 N/E/R/T의 resolved는 12/9/9/5이며 N/E/R은 원 응답 기준을 충족했다. 저장 불일치 집단의 K/B/G/M 정답은 47/40/54/54, G/M 교정20·손상13이다. 이는 R의 성능 결과가 아니다.

# Strategy Check / 연구 방향 판단

직전 리뷰가 비교한 본비교 복구와 현재 설정 보류 중 사용자가 전자를 승인했다. 전수 후보·문헌 검토를 반복하지 않는다. 같은 현상에 대한 미실행 비교이며 새 후보 탐색이 아니다.

**기술 질문 → 실패 조건 → 공개 정답 비교 → 주장 범위:** 오류가 섞인 조언을 선택적으로 사용하는가 → 직접 답과 detector가 충돌할 때 잘못된 조언 채택 또는 유용한 조언 거부 → 명시적 opacity 존재 정답과 양성 box로 교정·손상 및 근거 정합성 비교 → 현재 frozen 모델·고정 단일 소견·반복 개발 선택 집단에 한정한다.

**시험 설정:** 원 성능 기준으로 R의 유용성을 판단한다. T의 거부를 해소하려고 prompt를 바꾸지 않는다. 성능 미달이면 현재 frozen 설정 확대를 보류한다.

**연구 관찰:** 성능 성공 여부와 별개로 전체 고정 표본에서 잘못된 조언 채택, 정답 초안 손상, 유용한 조언 거부를 본다. K/B/G/M/N/E/S, 기초 수행과 형식·거부가 설명하는 부분부터 구분한다. 실패 사례가 있다는 이유로 새로운 한계·유망성·신규성을 부여하지 않는다.

**연구 질문:** 단순 대안 이후에도 중요하고 판별 가능한 질문 하나가 남을 때만 다음 독립 비교를 제안한다. 남지 않으면 iter_115의 CURE 특화 투자 보류로 복귀한다. 복귀는 자동 재개할 실험이 있다는 뜻이 아니다.

현재 지배 비용의 정확한 비율은 미측정이다. 이번은 이미 수행한 연결·TECH·병렬 비교를 재사용해 새 모델 출력에 투자한다. 준비·검증·생성 시간을 구분해 기록한다.

# Hypothesis

R은 잘못된 초안40명에서 유용한 detector 조언을 받아들이면서, 정답 초안47명에서는 잘못된 조언을 거부할 수 있다. 경쟁 설명은 초안 유지, detector 추종, 기초 영상 판단의 부족, 응답 거부 또는 E/S/M으로 충분한 단순 재판단이다.

R−N과 R−E는 각각 현재 입력에서 자동 근거·초안 추가의 조건부 차이다. R−T는 거부 성향과 입력 적합성 차이를 포함하므로 시각 근거의 인과적 사용 증거로 쓰지 않는다.

# Limitation Evidence / Correct Usage Checks

`rsna-evidence-interface-sensitivity`와 `padchest-regional-report-concatenation-conflict`의 observed 상태를 유지한다. LIMITATIONS와 iter_017/088 원 리뷰의 evidence·usage_checks를 확인했다. 이 근거는 교정 실패의 재현이나 method 진입 승인이 아니다. 이번 역할은 diagnostic, method_stage=none이다.

MedGemma 1.5 revision `91850547d9f0b2fdd21aa7c5f4f3d1a8a52c243b`, bf16, eval, greedy, adapter=None을 유지한다. `ev109_extract_v1`, 질문 O를 유지한다. 미표기를 음성으로 만들지 않고 원 category가 opacity인 경우만 표적 양성으로 평가한다. normal과 not_normal_no_opacity는 표적 음성이지만 같은 임상 상태가 아니다.

기존 직접 대조는 input_ids·padding 영상 hash·생성 token 일치를 검사했다. processor pixel_values 직접 검증으로 표현하지 않는다. 기존 직접 대조4건의 같은 입력에서 실제 worker 전처리와 독립 공식 processor 경로의 tensor shape·dtype·값, attention/token 관련 입력을 비교한다. 모델을 로드해 새 generate를 실행할 필요는 없다. T에는 image token과 pixel_values가 없어야 한다. R/T 텍스트 일치, GT와 생성 입력 분리도 유지한다.

# Contribution Path / Baselines / Reuse

기여는 미확정이다. 기준 계획이 조사한 Anatomically-Grounded Fact Checking 및 FC-guided correction과의 관계를 상속한다. 선택적 수정 자체는 새로운 기여가 아니다. 자연 자동 근거 오류에 대한 잔여 현상과 단순 대안 이후 가치가 확인돼야 후속 투자를 논할 수 있다. 이번에는 기존 논문 시스템의 재현·우위를 주장하지 않는다.

대조 정의는 다음과 같이 고정한다.

- K: 저장 원본 영상 Q_O 직접 답 유지.
- B: detector17 epoch18, threshold0.70의 box 유무.
- G: iter_012 seed17 concise grounding의 유효 box 유무. invalid는 unresolved.
- M: K/B/G 다수결, G invalid이면 K.
- N: 영상+초안, 자동 근거 없음.
- E: 영상+자동 근거, 초안 없음.
- R: 영상+초안+자동 근거.
- T: R의 동일 텍스트에서 영상만 제거한 보조 조건.
- S: E가 resolved이고 B와 같으면 E, 나머지는 K.

현재 `approach/noisy-evidence-correction` 브랜치와 HEAD `66cd4542720d0efe69b2fbbdfabbe24ebe0253a0`를 이어간다. 작업 파일에 변경이 없음을 확인했다. 필요한 파일이 현재 기반에 있으므로 reuse_assets는 비운다. 전체 스냅샷 승인으로 해석하지 않는다.

`ed116_spec.py`, `ev109_extract.py`, `pg43_run.py`와 실제 `rsna_diag` 의존성, `ed116_link.py`, `ed116_verify_selection.py`, `ed116_baselines.py`의 승인 범위를 재사용한다. `ed116_eval.py`, `ed116_analyze.py`, `ed116_verify.py`, `ed116_build.py`, `test_ed116.py`는 실제 사용 경로의 수정·검증이 필요하다. `ed116_directcheck.py`는 검증 범위 정정과 processor 대조에만 사용한다. 미수정 `ev111_link.py`, adapter 경로와 무관한 과거 실행기는 정비하지 않는다.

# Proposed Experiment

## 1. 불변성 확인과 새 잠금

원 selection, ledger, GT, MAIN 요청, 모델·입력 출처를 현재 내용 hash와 연결한다. 기존 87/505/8 분모, 불일치87명과 일치 대조87명 및 TECH12명 ID를 그대로 유지한다. 선택 seed 문자열 `iter116|`도 바꾸지 않는다. 505명 중 SHA256 순서의 첫12명 TECH, 다음87명 control이라는 원 규칙을 유지한다.

기존 MAIN 요청의 request ID·prompt·packet·이미지·caps는 그대로 재사용한다. 새 결과는 `research/results/iter_117/`에 둔다. 원 산출물과 잠금을 덮어쓰지 않는다. 원 plan hash, 원 source SHA, 입력 artifact hash와 이번 코드 변경을 새 manifest/protocol에 연결한다. 구 코드의 iter_116 하드코딩 출력 경로는 이번 실행 경로에서만 명시적 인자로 분리한다.

기존 TECH 검증은 원 source SHA와 원 protocol에 연결해 재사용한다. 새 코드 hash로 과거 TECH를 생성했다고 기록하지 않는다. 입력·생성 경로가 변하지 않았음을 별도 기록하고 변경된 verifier·경로 처리만 회귀 검사한다.

## 2. 동작 확인: 재생성 없이 보완

T를 포함한 네 조건의 기술 record 완전성과 입력 무결성은 계속 필수다. 응답 수 문턱≥6/12는 N/E/R에만 적용한다. T의 5/12와 거부7건은 보조 결과로 남긴다. 기존 N/E/R=12/9/9를 재사용한다. MAIN 성능을 보고 새 응답 성공 문턱을 만들지 않는다.

verifier는 원시 출력에서 그룹·조건별 unresolved 수를 재계산해 보고서와 실제 비교한다. E→S와 G→M을 공유 변수로 둔 환자별 Yes/No 배정에서 교정·손상·paired 차이 범위를 독립 계산한다. 생산 평가 함수를 호출해 자기 결과를 검증하지 않는다.

최종 point/worst/best 기준과 label도 원 부등식으로 독립 재계산한다. 각 지표의 최선값은 서로 다른 배정에서 나올 수 있으므로 best 기준 통과를 동시에 가능한 양성 결과로 단정하지 않는다. 원 코드의 해당 분기는 보수적인 불확정 후보로 보고한다. 성공은 모든 배정의 최악값에서 모든 원 기준을 만족해야 한다.

합성 fixture로 unresolved 수 변조 탐지, 공유 변수 의존성, 경계값 교정10·손상5·차이5·일치 손상률5%, positive/hold/inconclusive 분기를 확인한다. 원 parser fixture와 필요한 metric 회귀 검사는 유지한다. 실제 processor tensor 대조는 기존 TECH 입력으로만 한다.

## 3. 가능성 탐색: 고정 본비교

필수 입력·verifier 확인 후 같은 Claude 호출에서 174명×4조건=696요청을 완료한다. 중간 성능 확인으로 표본·prompt·운영점을 바꾸지 않는다. N/E/R/T 모두 생성하며 T의 거부로 N/E/R 평가를 막지 않는다.

생성 cap 1000→2000→4000은 원 규칙대로 비EOS 상한 도달에서만 재시도한다. 거부·unresolved를 이유로 재질의하지 않는다. 고유 요청 수와 실제 attempt 수를 분리한다.

## 4. 규모 확대·독립 확인

이번 규모가 승인된 최대 본비교다. 추가 환자·seed·모델·학습·prompt 탐색은 없다. 독립 확인은 결과와 잔여 질문을 검토한 뒤 다음 사용자 승인에 제안할 수만 있다. 현재 E600 선택 집단을 독립 test로 부르지 않는다.

## 5. GPU·예상 시간·재개

기존 TECH의 2/4 worker 비교를 재사용한다. 48요청 wall-clock은 105.43/60.30초이며 token 일치가 확인됐다. 4 worker 기록의 최대 reserved는 8.268GiB, 생성 구간39.861초다. 새로 같은 TECH를 생성하는 비용을 피한다.

실행 직전 nvidia-smi로 허용 GPU0,1의 여유와 논리/물리 대응을 확인한다. 각 GPU에2 worker를 우선하되 다른 프로세스 점유와 동시 peak 및 worker당 최소2GiB 여유를 포함해 안전할 때만 사용한다. 기존 peak는 짧은 TECH의 값이므로 긴 출력 중 메모리를 관찰한다. 부족하거나 OOM·경합이 있으면 기존 요청을 보존하고 동시성을 낮춘다. 한 GPU당1 worker로 낮추면 실제 사유를 기록한다.

동일 길이 가정에서 본생성은 약10~15분으로 추정되며 loading·긴 출력·검증은 추가다. 시간 상한이 아니다. 실제 처리량과 남은 요청으로 갱신한다. 새 요청량을 늘리지 않는다.

고유 request ID, 원자적 claim, worker별 출력, 완료 digest와 누락·중복 검사를 유지한다. 중단 시 같은 새 protocol의 검증된 완료 요청만 재사용한다. 원 claim이나 원 결과를 지우지 않는다. 기존 재개 검사는 제한 종료와 부분 행 복구 범위였음을 밝히며 SIGKILL·동시 소유권의 일반 보장을 주장하지 않는다. 입력·소스 변경으로 재사용이 불가능하면 원인을 보고하고 임의 덮어쓰기를 하지 않는다.

# Implementation Tasks for Claude

1. 기준 plan/hash와 이번 amendment, iter_116 code_assets를 확인한다. 새 결과 경로·원 자산 연결·변경 범위를 기록한다.
2. 기존 selection과 MAIN 요청을 그대로 연결하고 실제 읽는 입력의 hash를 확인한다. 표본을 다시 선정하거나 기존 분석을 전수 재실행하지 않는다.
3. T 응답 성공의 gate 분리, verifier의 unresolved·범위·최종 분기 대조, 필요한 processor tensor 검증과 경로 처리만 보완한다.
4. 변경 경로의 fixture·회귀 검증 후 MAIN 이전에 평가·관찰 보고 규약과 새 protocol을 잠근다.
5. 기존 처리량 비교를 근거로 안전한 GPU 배치를 선택하고 696요청을 한 번 완료한다.
6. 원문·추출값·조건·GT·초안/조언 정오·교정/손상·위치 정합성·request ID를 환자별 표로 연결한다.
7. 생산 평가와 독립 verifier로 원 수치·범위·판정·출력 완전성을 대조한다. 결함이 실제 평가를 바꾸면 원인·영향을 기록하고 기준은 바꾸지 않는다.
8. 원 성능 판정과 아래 연구 관찰 판단을 분리해 보고한다. 실행 유효성·성능 개선·가설 지지·신규성은 별도로 쓴다. full 리뷰 뒤 다음 승인을 기다린다.

# Evaluation (성공/실패 기준 포함)

## 원 성능 기준: 변경 없음

불일치87명의 K 오답40명에서 correction, K 정답47명에서 harm을 계산한다. unresolved는 주 보수적 정답 수에 포함하지 않으며 보수적 harm과 실제 resolved 오답 손상을 분리한다. 일치87명에서는 실제 K 정답 수를 손상률 분모로 쓴다.

양성 탐색은 R의 교정≥10/40, 손상≤5/47, K/B/G/M/N/E/S 각각보다 정답≥5명 증가, 일치 대조 K 정답 손상률≤5%를 모두 만족할 때다. unresolved의 보수적 배정에서도 모두 유지돼야 한다. M=54/87이므로 R≥59/87은 필요조건일 뿐 충분조건이 아니다. CI 하한>0 등 새 gate를 추가하지 않는다.

그룹별 환자 paired bootstrap10,000회·seed11617·95% CI를 유지한다. 그룹을 합쳐 E600 대표 성능으로 보고하지 않는다. 원 category와 Yes→No/No→Yes를 빠짐없이 보고한다.

공동 지표는 최종 Yes이면 고정 detector box 유지, No이면 제거한다. unresolved는 공동 성공으로 세지 않는다. 양성은 Yes 및 IoU0.3 최대 일대일 matching의 TP=n_GT=n_pred, 음성은 No와 빈 box가 공동 성공이다. IoU0.5·양성 F1·FP/FN은 원 정의대로 gate 후 box에서 계산한다. box 경계 수정이나 누락 위치 생성은 시험하지 않는다.

## 연구 관찰 가치: 성능 판정과 분리

본결과 전에 다음 표를 고정하며 새로운 수치 gate나 유리한 소집단 탐색을 추가하지 않는다.

- **K 정답/B 오답47명:** 각 정책의 정답 유지, resolved 오답 전환, unresolved. R의 잘못된 조언 채택은 이 집단에서 R=B인 resolved 응답으로 센다. N도 같은 환자에서 틀렸는지 함께 보여 단순 재판단 손상과 구분한다.
- **K 오답/B 정답40명:** 각 정책의 교정, resolved 초안 유지, unresolved. R=K인 resolved 응답은 유용한 조언을 받아들이지 않은 관찰이며 원인 확정은 아니다. E/S/G/M의 같은 환자 결과를 함께 제시한다.
- **일치 대조87명:** K/B 모두 정답인 환자와 모두 오답인 환자의 실제 분모를 분리해 손상·회복·unresolved를 보고한다.
- 모든 표에서 K/B/G/M/N/E/R/S를 나란히 두고 T는 보조로 표시한다. 전체 분모를 유지하며 valid-only 수치로 결론을 대체하지 않는다. 고정 parser의 source/reason과 strict 형식 준수·EOS를 별도 보고한다.

R−N, R−E의 paired 결과와 환자별 반대 사례를 함께 보아 기초 수행, 초안 영향, 자동 조언 전달, 형식·거부 중 어떤 설명이 남는지 논한다. 입력 차이와 선택 집단 때문에 내부 원인을 확정할 수 없다. 공개 box 정합성은 위치 주석과의 일치이며 임상 진위를 대신하지 않는다. 여러 조건의 오류가 겹친다는 이유만으로 일반적인 선택 실패를 선언하지 않는다.

**성능 양성:** 제한적 유용성 근거로 보존하고 단순 대안 대비 비용·추가 가치가 있는 독립 확인을 제안한다.

**성능 음성:** 현 frozen R 확대는 보류한다. 그래도 전체 표에서 일관된 중요한 잔여 현상이 확인되면 관찰 범위·반대 사례·경쟁 설명·가까운 기존 방법과 구별할 다음 질문 하나를 제안할 수 있다. 실패 자체나 사후 사례 이름만으로 투자하지 않는다.

**불확정:** unresolved 또는 표본 변동으로 남은 핵심 불확실성을 특정한다. 판별 가능한 독립 비교의 정보 가치가 명확할 때만 후속을 제안한다. 그렇지 않으면 현 설정 보류와 iter_115 복귀 기준을 적용한다.

어느 경우에도 이번 실행을 연장하지 않는다. 다음 반복은 --confirm-each-iter 사용자 승인 대상이다.

# Risks / Checks

- 반복 개발 RSNA의 불일치 선택 집단으로, 자연 모집단 정확도·일반 VLM 한계·자유 판독 개선을 주장하지 않는다.
- K/B 불일치에서는 두 이진 답 중 하나가 맞는 구조다. 이 선정 효과를 명시한다.
- 자동 근거와 초안에는 GT를 넣지 않는다. 생성 worker가 평가 전용 GT를 읽지 않게 한다.
- T의 거부는 유지하며 R−T만으로 시각적 근거 사용을 주장하지 않는다.
- 기존 원 계획의 실패와 TECH 출력을 보존한다. 새 잠금이 원 잠금을 대체했다고 기록하지 않는다.
- verifier 보완을 과학적 발견으로 보고하지 않는다. 본평가 미실행이면 교정 가설은 계속 미판정이다.
- 서비스 비용에는 기존 초안·detector·SFT와 추가 교정 비용이 포함된다. 이번 저장 자산 재사용 비용과 구분하며 미측정 비용을 만들지 않는다.
- 다른 모델 계열과 직접 교정 SFT는 이번 승인 범위에 추가하지 않는다. 관찰이 기초 능력 부족으로 설명되면 현재 모델·설정의 한계로 좁힌다.
- **대규모 GPU 필요 후보:** 다기관 verifier/editor 공동 post-training은 장기 후보로만 보존한다. 현재 잔여 문제와 필요성이 미확정이며 새 학습을 발주하지 않는다.
- 구현 Claude와 현재 등급, GOAL, 기존 checkpoint·캐시·기본 환경을 유지한다. Telegram에는 같은 질문의 본비교 복구와 실제 교정·손상·대조 결과를 연결해 보고하고 다음 승인 대기를 유지한다.

# 계획의 근거 (GPT 조사 노트)

원 계획 agent/runs/iter_116/plan.md를 직접 읽고 SHA256 be752099da4cd90c2b14fe16ac4659b054de1cb114111364c8dcf8b93a46d009를 확인했다. iter_116 review.md/review.json, iter_115 복귀 권고, GOAL, CODE_ASSETS의 관련 항목, LIMITATIONS의 두 항목과 iter_017/088 원 review.json을 확인했다.

현재 research HEAD는 66cd4542720d0efe69b2fbbdfabbe24ebe0253a0이며 status/diff에 변경이 없다. 필요한 ed116 파일은 현재 브랜치에 있어 선별 반입은 필요 없다. 생성기 adapter=None 경로와 고정 명세·parser·원 자산 연결은 모듈별 승인됐지만 전체 스냅샷은 미승인이다.

ed116_verify.py는 n_unresolved_cells 검사를 실제 비교 없이 True로 기록한다. ed116_eval.py의 환자별 공유 변수 열거는 E→S, G→M 의존성을 반영하지만 독립 verifier는 범위와 최종 분기를 대조하지 않는다. 최선의 개별 범위가 동시에 실현 가능한지는 별개이므로 이를 성공 가능성의 확정 근거로 과장하지 않아야 한다. 원 성능 부등식은 유지한다.

ed116_directcheck.py와 tests/direct_check.json을 확인했다. 기존 4건은 input_ids, padding 영상 hash, 생성 token의 일치와 text-only 영상 부재를 검사했다. processor pixel_values의 직접 일치를 검사한 것은 아니다. 같은 TECH 입력에서 processor만 실행하는 대조로 부족한 범위를 보완할 수 있어 추가 모델 생성은 필요 없다.

TECH_w4/completion.json의 실측은 48건 wall 60.300초, 생성 구간 39.861초, 최대 reserved 8.268GiB, p95 request wall 4.307초다. 직전 리뷰의 2 worker wall은 105.43초이며 두 구성의 출력 token은 같았다. 이번에 동일 비교를 다시 생성할 정보 이득은 낮다.

가까운 선행의 관계는 기준 계획에 보존된 조사에서 상속한다. 이번은 지원 범위·문헌 주장을 새로 정하는 계획이 아니라 승인된 본비교 복구이므로 문헌 전수 재조사는 하지 않았다. R 성능 실패와 연구 질문 가치의 분리만 사용자 승인에 따라 사전 해석 항목으로 추가한다.
