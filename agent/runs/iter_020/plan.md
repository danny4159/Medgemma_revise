# 요약

- **이번에 할 일:** iter_019의 자료·좌표·실행 결함을 수정하고 D8→E48→조건부 F 진단을 완료한다.
- **필요한 이유:** 실제 환자 결과가 없어 reference 대상 선택 가설은 아직 검증되지 않았다.
- **확인할 기준:** 정상 입력·재개·완전성 gate를 통과한 뒤 원래 H와 baseline 기준으로 판단한다.
- **주의·다음:** 기존 결과를 보존하고 새 산출물은 `results/iter_020/`에 저장한다. 준비 검사 통과를 한계 재현이나 방법론 성공으로 보고하지 않는다.

# Current Understanding

iter_019는 execution_failed, valid_experiment=false다. images.zip은 현재 1,707,524,096 bytes이며 직전 리뷰에서 불완전 ZIP으로 확인됐다. D8/E48/F의 실제 환자 출력은 없다. 합성 wrapper 검사와 4000-token 메모리 측정은 일부 준비 근거로만 재사용한다.

현재 HEAD는 `ff16f12f6fca43e62c5e3ff795456db9200220b2`이고 작업 트리는 clean이다. 같은 연구 브랜치를 이어가며 추가 반입은 하지 않는다. 전체 스냅샷의 재사용 승인은 없으므로 아래 수정·검증을 거친 경로만 사용한다.

유지: 연구 질문, 조건별 입력, H, D8/E48/F 규모와 확대 기준, 모델 revision, 기존 결과·checkpoint·reserve. 변경: 방향·좌표 구현, 자료 고정 순서, 요청·출력 검증과 실행 복구, 결과 경로. 보류: 새 loss·MRI SFT·기존 범위 문구 탐색·추가 데이터셋. iter_008 일회성 보완을 다시 수행하지 않는다.

# Strategy Check / 연구 방향 판단

중요한 능력은 여러 영상에서 지정된 대상의 정체성을 유지하는 것이다. iter_019 계획과 리뷰의 전략 비교를 유지한다. 실제 환자 결과가 없으므로 광범위한 재조사를 반복할 시점은 아니다.

현재 grounding 개선은 새 학습 근거가 부족하고, 다른 임상 질문은 별도 자료·가설 구체화 비용이 든다. 현재 진단 복구는 이미 정한 비교로 대상 선택·localization·위치 shortcut·언어 매개 해결을 구분할 수 있다. 자료 식별성 실패, 정상 입력 gate 실패, 단순 baseline의 충분한 성능이 확인되면 추가 내부 대응 학습 투자를 낮추고 방향을 재평가한다.

# Hypothesis

O의 target 내부점 조건에서 두 인스턴스를 모두 localization할 수 있는 환자 중에도, reference를 제공한 J_RT와 J_TR에서 동일한 다른 인스턴스를 반복 선택하는 사건이 남는다. 전체 평가 환자를 분모로 하는 사건 빈도 H의 중요도 기준은 원래 15%다.

이는 임상 허용 오류율이 아니라 후속 연구 투자 기준이다. H가 높아도 내부 병목이나 신규 방법의 필요성이 확정되지는 않는다.

# Limitation Evidence / Correct Usage Checks

`context-sensitivity`는 observed이며 관련 출발점일 뿐 MRI reference 실패의 검증 근거가 아니다. RSNA의 validated grounding 한계도 이번 MRI 과제로 전이해 주장하지 않는다.

모델은 `google/medgemma-1.5-4b-it`, revision `91850547d9f0b2fdd21aa7c5f4f3d1a8a52c243b`를 유지한다. 기존 공식 다중 영상 chat 경로와 새 wrapper의 input_ids·pixel_values·영상 순서를 실제 D 입력에서 대조한다. square padding, yxyx 0–1000, single-box parser와 EOS 검사를 유지한다.

방향 행렬은 [MetaIO 공식 규약](https://docs.itk.org/en/latest/learn/metaio.html)에 따라 해석하되 직렬화·행렬 곱·numpy 축을 분리해 검증한다. AnatomicalOrientation 문자열만으로 배열을 정렬하지 않는다. 비대칭 비항등 행렬, 축 순열·반전, 비등방 spacing·origin을 포함하는 독립 물리좌표 fixture가 필요하다. 실제 자료에서는 원본 slice 축을 보존하고 동일 변환을 image와 mask에 적용한다. 방향이 모호하거나 지원되지 않는 자료를 추측으로 보정하지 않는다.

# Contribution Path / Baselines / Reuse

기여는 미확정이다. 가까운 방법의 비교는 iter_019 조사 기록을 이어받는다. 직접 다중 영상 SFT, 언어 매개 grounding, association 학습과 구별할 방법은 이번에 제안하지 않는다.

조건은 환자당 두 인스턴스에 대해 다음을 유지한다.

- J_RT/J_TR: 같은 R/T와 reference box를 제공하되 영상 순서와 역할 지시를 함께 바꾼다. 각 2회 호출.
- S: R/T로 대상 설명을 생성한 뒤 T와 그 설명으로 grounding한다. 4회 호출. 설명을 GT로 교정하지 않는다.
- A: T와 reference box만 제공한다. 2회 호출. reference pixels 제거 대조다.
- O: T와 해당 mask의 내부점을 제공한다. 2회 호출. 추가 정답 정보가 있는 oracle이다.
- C: 같은 volume grid와 표시 affine으로 reference 위치를 전달한다.
- N: 표시 box가 그려지지 않은 grayscale reference template으로 고정 scale {0.75,1.0,1.25} NCC를 수행한다. 전체 target 검색, 최대 NCC, scale 1과 가까운 순서 및 좌상단 동점 규칙을 유지한다. target GT를 검색·선택에 사용하지 않는다.

MedSAM2는 기존 호환 설치가 있을 때만 공식 코드·checkpoint를 고정해 D에서 검증한다. 두 slice 조건과 중간 slice 추가 조건은 분리하고 추가 입력·비용을 공개한다. 설치 변경은 하지 않는다. 미실행이면 신경망 모듈 대비 우열은 미확인이다. 기존 RSNA adapter는 MRI 직접 SFT baseline으로 사용하지 않는다. 방법 개발은 과제에 맞는 충분한 직접 SFT·학습된 모듈형 대안과 추가 원천 비교를 다음 계획에서 마련한 뒤 판단한다.

재사용 파일은 현재 브랜치에 존재한다. `mi19_render.py`, `geometry.py`의 승인은 올바르게 정렬된 배열에서의 표시·좌표 변환 범위다. `mi19_mha.py`, `mi19_data.py`, `mi19_manifest.py`, `mi19_baseline.py`, `mi19_requests.py`, `mi19_protocol.py`, `mi19_gen.py`, `mi19_run.py`, `mi19_pipeline.py`, `mi19_eval.py`는 아래 결함 수정 후 검증한다. `generate.py`, `mi19_spec.py`, `parse.py`, `metrics.py`, `queue_lock.py`, `lock_protocol.py`와 현재 의존 파일을 실제 protocol에 연결한다. 기존 네 `test_rsna_iter019_*` 파일은 출력 경로를 지정할 수 있게 해 이전 결과 덮어쓰기를 막는다.

# Proposed Experiment

## 1. 복구와 자료 gate

실행 호스트에서 기존 다운로드·pipeline·worker의 PID/starttime·소유 lock·종료 상태를 먼저 기록한다. 살아 있는 작업을 중복 실행하거나 claim을 지우지 않는다. 이전 다운로드가 종료됐으면 별도 `results/iter_020/source/` 경로에서 복구한다. 원본 부분 파일은 보존한다. 이어받기는 원본 객체의 URL·길이·validator 및 Range 응답을 확인할 수 있을 때만 사용하며, 불명확하면 새 경로에 다시 받는다. 완료는 원저자 checksum, 자체 SHA256, ZIP 구조·member CRC로 검증한다. 기존 작은 파일은 checksum을 재확인해 읽기 전용 출처로 연결할 수 있다.

방향 처리 후 모든 후보의 image/mask shape·spacing·origin·direction·payload·유한 intensity·정수 label을 검사한다. 원본 sagittal slice 축과 in-plane 축·반전, index→physical→display 변환을 저장한다. 비항등 방향과 `107_t2.mha`를 반드시 회귀 사례에 포함한다. 실제 overlay는 D8 전체와 D8에서 대표되지 않은 방향 유형을 확인하되 성능 출력은 보지 않는다.

척추 label 범위와 전체 volume 연결성을 검사한다. 작은 분리 성분을 임의 제거하거나 label을 합치지 않는다. 연결성 이상·지원하지 않는 방향은 결과를 보기 전에 정한 자료 판정으로 처리하고 제외 이유를 남긴다. 임상 level 이름을 만들지 않는다.

원래 적격 규약을 유지한다: regular T2 한 series/환자, 서로 다른 원본 sagittal slice 간격 6–15 mm, 공통 인스턴스 2개 이상, 원본 면적 128 pixels 이상·해당 인스턴스 최대 slice 면적의 20% 이상·bbox 각 변 8 pixels 이상. volume 비배경 유한 intensity의 1–99 percentile window와 spacing 기반 표시를 사용한다.

pair와 인스턴스 선택은 `iter019-reference-v1` salt를 포함한 후보별 SHA256 순서로 구현한다. 후보 직렬화·R/T 역할 규칙·동점 규칙을 출력 전에 고정하고 열거 순서가 바뀌어도 선택이 같은지 검사한다. C/N 성능으로 쌍을 고르지 않는다.

환자 ID·source volume hash·decoded pixel hash와 기존 자료를 대조한다. 중복 연결요소는 split을 넘지 않게 처리하고, 독립 환자 수를 부풀리지 않는다. 익명 legacy의 완전한 중복 배제와 사전학습 미노출은 보장하지 않는다.

현재 manifest가 build 실패 환자를 split에 남기는 경로를 수정한다. 모든 자료 gate와 렌더링을 완료한 적격 집합에서만 N을 확정하고 D8/E48/F를 구성한다. 단순 구현 오류 환자를 조용히 제외하지 않는다. 기관 metadata가 신뢰 가능하면 기관 비율을 보존하는 결정적 할당을 적용한다. 규칙·ID·제외 사유·입력 hash를 생성 전에 잠근다. N<56이면 자료 식별성 부족으로 종료하고 조건을 완화하지 않는다.

## 2. 동작 확인: D8

학습 없음, greedy generation, seed 19. 환자당 12회로 기본 96회다. J와 O는 정확히 한 box를 요구하며 빈 list·복수 box·invalid·잘림을 분리한다. 출력 cap은 1000→2000→4000이고 EOS가 없을 때만 확대한다. S 설명도 같은 ladder를 적용하고 모든 시도를 보존한다.

J_RT/J_TR/O 각각 valid 단일 box≥95%, 최종 cap 도달≤5%가 필요하다. 실패하면 입력·형식 문제로 보류하고 E에서 prompt/parser를 조정하지 않는다.

고정 D 요청 24개로 정상 실행과 pipeline 부모 SIGTERM·worker 강제 중단·마지막 record 절단 후 재개를 비교한다. S1→S2 경계를 포함하고 완료 요청 재사용, 중복·누락 0, greedy suffix 일치, 자식 종료 코드와 소유권을 확인한다. 손상된 원본은 보존한 뒤 소유권이 확보된 복구 경로만 수정한다.

## 3. 가능성 탐색: E48

D gate와 실행 검증 통과 후 48명×12=576회와 C/N을 수행한다. 평가를 한 번 완료한 뒤 판단하며 D는 주지표에 합치지 않는다. 각 조건의 pair success, instance별 IoU, wrong-instance·경계 오차·빈 출력·형식 실패를 보고한다. 기관·간격·크기별 분석은 보조 관찰이다.

## 4. 규모 확대와 독립 확인: F

F=N−56을 보존하고 다음 원래 조건을 모두 만족할 때만 실행한다.

1. 자료·입력·형식 gate 유지, O pair success≥0.75.
2. C/N/S 어느 것도 pair success≥0.90에 도달하지 않음.
3. F≥64명.
4. H_E≥0.15. 또는 H_E<0.15이지만 Wilson 95% 상한≥0.15이고, 예상 F Wilson 반폭≤0.10 및 E 반폭의 80% 이하. 예상 p=(k+0.5)/49를 사용한다.

진입하면 모든 F에 동일 설정으로 12×nF회를 실행한다. 중간 성능에 따라 멈추거나 조건을 조정하지 않는다. E/F를 분리하며 F가 독립 확인 집단이다. 조건 미충족이면 F를 보존하고 이번 진단을 종료한다. 추가 데이터나 seed·학습을 자동 투입하지 않는다.

## 5. GPU 배치·비용·재개

실행 직전 nvidia-smi로 허용 GPU 0,1의 UUID·가용 메모리를 확인하고 여유가 큰 장치부터 배정한다. 물리 장치와 worker 내부 논리 index를 기록한다.

D의 24개 혼합 요청으로 총 2 worker와 안전한 총 4 worker를 비교한다. 실제 프로세스 peak와 다른 점유에 worker당 최소 2GiB 여유를 더해 GPU 용량 안에 들어야 한다. 다중 영상·4000-token 출력과 긴 S1 설명을 받는 S2의 메모리를 포함한다. 4 worker가 안전하지 않으면 batch 확대가 유망한지 확인하고, 불가능하거나 느리면 2 worker 유지 근거를 남긴다.

동일 요청의 greedy suffix·평가 결과가 유지되고 전체 wall-clock 처리량이 개선되는 구성을 채택한다. GPU별 전체 peak·allocator peak·긴 요청 지연·CPU/RAM/I/O 경합과 OOM을 기록한다. 성능 점수로 실행 구성을 선택하지 않는다.

기본 D/E 호출은 672회, F는 12×nF회다. 원래 T2 series 상한 210 아래 기본 행렬 최대 2,520회이며 실제 N은 미확정이다. 2–10 calls/min 시나리오에서 E 약 1–5시간, 전체 기본 행렬 약 4.2–21시간으로 추정한다. 다운로드·전처리·재개 검사는 별도다. D 실측 조건별 처리량과 S 의존성을 반영해 본실행 예상 시간을 다시 기록한다. 임의 시간 상한은 없다.

요청별 원자적 할당·worker별 결과·attempt별 PID/starttime·종료 코드·진행량·자원 로그를 남긴다. 추론 checkpoint는 완료 요청과 검증된 protocol이다. OOM은 동시성/배치만 낮춰 같은 조건으로 재개한다. 다운로드 대기나 background 시작을 작업 완료로 보고하지 않는다.

# Implementation Tasks for Claude

1. `results/iter_020/`를 명시적으로 받도록 source/data/run/test 경로를 연결한다. iter_019를 가리키는 하드코딩 출력 경로를 검사하고 원본 덮어쓰기를 차단한다.
2. MHA 방향·sagittal 축·표시 affine·사전 pair 선택을 수정한다. 독립 물리좌표 fixture, 비항등 실제 자료, image/mask overlay와 bbox·내부점 왕복을 검증한다.
3. NCC는 padded 좌표계에서 직접 crop·정규화 변환하도록 수정한다. top 또는 left가 0이 아닌 비정사각 영상, 알려진 이동·scale, 상수 template·경계·동점 fixture를 추가한다. 공통 geometry 함수의 기존 의미를 바꿔 다른 경로를 깨뜨리지 않는다.
4. 필수 source provenance·gate·manifest·split·요청·모델/생성 설정·실행/평가 코드의 hash를 protocol에서 강제한다. 요청 ID·prompt hash를 재계산하고 manifest에서 재구성한 전체 예상 행렬과 대조한다. 완료 재사용에서도 현재 입력 file/pixel hash를 재검증한다.
5. S2는 검증된 S1 완료와 원시 출력 파일·선택 record·설명 hash를 잠근다. phase1 실패 시 S2를 시작하지 않는다. S 설명을 임의 구제·절단하지 않고 마지막 cap 잘림은 별도 실패로 남긴다.
6. pipeline 진입 경로에도 SIGTERM·단일 소유권·자식 정리·종료 수집을 적용한다. completion 파일의 존재가 아닌 내용·요청 집합·종료 상태를 검증한다. 실패한 attempt의 과거 completion을 유효한 것으로 재사용하지 않는다.
7. 평가에서 고정 환자×인스턴스×조건의 정확한 집합, S1/S2 연결, 중복·누락·잉여 0을 먼저 강제한다. D 통과 없이는 E, E 확대 결정 없이는 F를 실행할 수 없게 한다. gate 결정과 근거 hash를 저장한다.
8. 기존 evaluator fixture를 새 경로에서 재실행하고 독립 계산으로 H·IoU·pair success·Wilson·확대 경계를 대조한다. paired 차이의 discordance와 그 비율의 이항 구간을 추가한다. discordance=0에서 bootstrap [0,0]을 모집단 효과의 영점으로 해석하지 않는다.
9. D 재개·처리량 검증 후 E와 조건부 F를 같은 호출 안에서 진행한다. 보고서에는 도달 단계·실제 환자/요청 수·미실행 단계·종료 코드·확대/보류 이유·원본 및 신규 산출물 위치를 남긴다. 소스 checkpoint는 orchestrator가 보존하도록 변경 파일을 명시한다.

# Evaluation (성공/실패 기준 포함)

단일 target 성공은 IoU≥0.5, 두 target 모두 성공하면 환자 pair success다. IoU≥0.3과 평균 IoU는 보조다.

wrong-instance는 지정 GT IoU≤0.1이면서 다른 척추 GT와 IoU≥0.3이고 그 대상이 유일 최대인 경우다. 다른 선택 인스턴스도 경쟁 GT에 포함한다. 동점·큰 box·단순 저IoU를 강제로 wrong-instance로 분류하지 않는다.

환자 H=1은 O에서 두 target 모두 성공하고, 적어도 한 reference에서 J_RT와 J_TR이 각각 유효 단일 box로 동일한 다른 인스턴스를 선택한 경우다. 전체 환자가 분모다. invalid·잘림은 H 사건에 포함하지 않지만 전체 실패 분해에 포함한다.

H는 Wilson 95% CI, pair success 차이는 환자 paired bootstrap 10,000회·seed 19019를 사용한다. discordance 비율의 95% 이항 구간을 함께 보고하되 이를 효과 차이 CI로 잘못 표시하지 않는다. 두 reference를 독립 환자로 세지 않는다.

- **양성:** F에서 H≥0.15, Wilson 하한>0.05, 모든 gate 유지이면 이 SPIDER 구성의 반복 대상 선택 실패를 지지한다. 다음 계획에서 충분한 직접 SFT·학습된 모듈형 대안·다른 원천을 비교한다. 신규 방법 성공으로 해석하지 않는다.
- **음성/투자 보류:** H 상한<0.15이면 사전 중요도 크기의 사건을 약화한다. C/N/S pair success≥0.90이면 단순 해결 경로를 보존하고 새 대응 학습 투자를 낮춘다. O가 낮으면 localization·표시·주석 범위가 더 중요한 경쟁 설명이다.
- **불확정:** CI가 기준을 가로지르면 사전 F 규칙만 적용한다. F 이후에도 불확정이거나 확대 요건이 없으면 이번 진단을 종료하고 정보 이득을 재평가한다. 다른 loss·prompt 탐색으로 자동 연결하지 않는다.
- **실행 실패:** checksum·방향·정답·입력 연결·재개·완전성 gate 실패면 모델 가설을 판정하지 않는다. N<56은 자료 식별성 부족이지 모델 능력의 음성 결과가 아니다.

# Risks / Checks

같은 volume의 위치 shortcut, GT 기반 적격 선택, 전체 vertebra와 body-only의 주석 차이, oracle 추가정보, 사전학습 노출 불확실성을 보고한다. mask·target 좌표·instance label이 허용되지 않은 prompt나 N 검색에 들어가지 않는지 확인한다. reference는 box 좌표로 지정하고 target에는 표시하지 않는다. overlay 파일과 모델 입력 파일은 구분한다.

방향 수정은 단순 행렬 transpose만으로 승인하지 않는다. 파일 규약과 index→physical 기준의 일치, 원본 slice 보존, 실제 overlay를 모두 확인한다. 평가 코드 수정이나 실행 경로 변경 뒤 과거 합성 검사만으로 현재 버전의 유효성을 인증하지 않는다.

## 대규모 GPU 필요 후보

여러 anatomy·modality의 reference 관계를 vision encoder와 언어 모델이 공동 학습하는 post-training, 단일 영상 능력을 유지하는 혼합 학습을 후보로 보존한다. 이번에는 필요성이 미확인이다. 현재 두 GPU에서는 진단 후 근거가 생길 때 LoRA 또는 frozen correspondence 모듈과 충분한 직접 SFT를 우선 비교한다.

# 계획의 근거 (GPT 조사 노트)

## 새로 확인한 것

- agent/GOAL.md, LIMITATIONS.md, REPORTING_STYLE.md, CODE_ASSETS.md, iter_019 계획·리뷰·보고서 및 context-sensitivity의 출처인 iter_003 리뷰를 읽었다.
- research HEAD는 ff16f12f6fca43e62c5e3ff795456db9200220b2이며 git status --short와 git diff --stat 출력은 비어 있다. 필요한 mi19 모듈과 네 개 기존 fixture 파일이 현재 브랜치에 있다. 선별 반입은 필요하지 않다.
- images.zip의 현재 크기는 1,707,524,096 bytes로 직전 리뷰와 같다. 현재 결과 목록은 source·gate·합성 tests이며 실제 환자 생성 결과는 확인되지 않았다. 실행 호스트의 프로세스 생존 여부는 이번 계획 단계에서 판정하지 않았다.
- mi19_data.py와 mi19_manifest.py는 배열 마지막 축을 sagittal 축으로 고정한다. pair 선택은 선언한 SALT별 후보 SHA 순서 대신 pid hash의 modulo를 사용한다.
- mi19_manifest.main은 build_one 실패를 errors에 기록하면서 실패 전 적격 목록으로 만든 split을 저장한다. 완성된 manifest와 split의 정확한 집합 일치를 강제해야 한다.
- mi19_baseline.condition_N은 padded 영상에 padding을 뺀 좌표로 crop하고 결과에는 padding을 다시 더한다. 비영 padding fixture가 필요하다.
- mi19_pipeline은 phase1 실패 후에도 S2를 구성하며, 기존 요청 파일을 존재만으로 재사용한다. protocol의 필수 자료 목록과 S1→S2 연결, D/E/F gate, 평가의 예상 집합 검증을 보완해야 한다.
- 합성 4000-token stress 기록은 allocator peak 8.241 GiB, reserved 8.313 GiB, 305.27초다. 실제 환자·S2 긴 입력·GPU 전체 점유·동시 worker의 안전성을 입증하지 않는다.

## 공식 규약 재확인

방향 결함의 수정 기준을 확인하려고 [MetaIO 공식 문서](https://docs.itk.org/en/latest/learn/metaio.html)를 재조회했다. 문서는 방향 행렬의 column-major 직렬화와 AnatomicalOrientation 문자열 변경만으로 영상이 재정렬되지 않는다고 명시한다. 단순 transpose 수정만으로 검증을 끝내지 않고 index→physical 변환을 독립 fixture와 실제 header에 대조해야 한다.

## 의미와 선택

iter_019의 전략 판단을 유지한다. 실제 환자 결과가 없는 상태에서 문헌 조사나 새 loss 탐색을 반복하는 것보다 확인된 결함을 수정해 원래 진단을 완료하는 정보 이득이 크다. 연구 질문·H·표본 수·확대 기준은 유지하며, 새 결과는 iter_020에 보존한다. 기존 mask gate의 210은 검증된 적격 환자 수가 아니다. 새 한계와 신규 기여는 미확인이다.
