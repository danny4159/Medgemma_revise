# 요약

- **이번에 할 일:** iter_023의 실행·평가 경로를 복구하고 D24→E60→조건부 E200 사분면 QA를 완료한다.
- **필요한 이유:** RSNA SFT의 bbox 개선은 검증됐지만, 새로운 영역 질문에 대한 직접 활용은 아직 실행하지 못했다.
- **확인할 기준:** 동일 환자의 base/SFT 직접 답변, bbox+규칙, bbox reader를 비교한다. 원래 형식·oracle·확대 기준을 유지한다.
- **주의·다음:** 형식·지시 실패와 능력 전이를 구분한다. 새 학습·MRI F139·reserve는 사용하지 않으며, 이번 결과는 개발 진단이다.

# Current Understanding

iter_012의 확인 양성 400명에서 F1@0.3은 base official 0.1650, SFT 세 seed 0.6308–0.6528, prior_set 0.4243이었다. 이는 유효한 bbox baseline이며 일반적 공간 이해나 새 방법의 contribution은 아니다.

iter_015–016은 전역 Q_O/Q_A와 형식 효과를, iter_017–018은 evidence 인터페이스와 질문 범위를 다뤘다. 이번 질문은 동일 영상에서 지정 사분면에 따라 정답이 바뀌므로 기존 전역 질문의 반복이 아니다.

iter_023은 fixture 45개와 부분 bbox 생성까지 진행했다. 현재 정식 M0 bbox는 47/48건이고 QA는 미실행이다. 유효한 전이 실험이 없으므로 가설을 기각하지 않는다.

사용자 보완의 우선순위는 iter_023에서 이미 적용됐다. 기존 SFT 성과·checkpoint·split·원시 기록을 유지하고 longitudinal 계획과 MRI F139·reserve·추가 학습은 보류한다. 이번에는 같은 접근법에서 실행을 복구한다. 원본 iter_023 산출물은 보존하고 새 결과는 `ROI23_RUN_ROOT=results/iter_024` 아래에 저장한다.

# Strategy Check / 연구 방향 판단

iter_023 plan.md 및 review.md의 전략 판단을 유지한다. 중요한 질문은 위치 supervision의 결과를 미학습 판단에 재사용할 수 있는가이다. 현재 추가 loss 개발은 전이 범위를 설명하지 못하고, 다른 task로 전환할 새 과학적 근거도 없다. 기존 checkpoint 진단의 정보 이득이 가장 크다.

이번은 이미 승인한 진단의 복구이므로 광범위한 전략·문헌 재검토를 반복하지 않는다. 정상 사용·정답 gate를 확보할 수 없다는 구체적 근거가 생기거나 실제 결과가 나온 뒤 다음 투자를 재평가한다. 실행 유효성, 성능 차이, 전이 가설 지지, 신규 기여 가능성은 별도로 보고한다.

# Hypothesis

- H_transfer: bbox-only SFT B0가 미학습 사분면 질의에서 M0보다 환자별 네 답의 정확도 Q4를 높인다.
- H_external: B0 bbox+규칙이 M0 bbox+규칙보다 Q4를 높인다.
- 경쟁 설명은 형식 순응, 사분면 지시 해석, 답변 prior, 숫자 해석, 실제 위치 정보 활용이다.

H_external만 지지되는 결과를 직접 전이 또는 내부 표현 손실의 증거로 바꾸지 않는다. 원 계획의 가설·성공 기준은 유지한다.

# Limitation Evidence / Correct Usage Checks

`lesion-grounding-generalization`의 validated 범위는 iter_009·012의 정상 사용 RSNA bbox 결과다. `qa-format-compliance-after-grounding-sft`와 `rsna-evidence-interface-sensitivity`는 observed다. 사분면 전이 실패는 아직 검증되지 않았다.

모델 revision은 `91850547d9f0b2fdd21aa7c5f4f3d1a8a52c243b`로 고정하고 bf16·greedy·공식 chat template·값 보존 전처리를 유지한다. 보존된 `results/iter_009/source/official/cxr_anatomy_localization_with_hugging_face.ipynb`의 공식 messages 구성과 실제 D 입력의 input_ids·pixel_values를 대조한다. 로컬 원문 hash와 출처를 기록한다.

출력은 1000→2000→4000 EOS ladder를 유지한다. 최종 비EOS는 invalid다. 전체 yes/no와 유일한 answer 키의 JSON yes/no만 의미 동등하게 인정한다. 완결된 공식 thinking prefix 제거 여부를 기록하고 strict 결과를 함께 보존한다. 설명문·모순·bbox·빈 목록·불완전 marker 및 Q_A 전용 Normal/Abnormal mapping으로 구제하지 않는다.

# Contribution Path / Baselines / Reuse

## 비교와 기여 범위

iter_023에서 검토한 Targeted Visual Prompting·Ferret 등 영역 QA/grounding 접근과 단순 bbox+규칙이 가까운 비교 대상이다. 이번 진단 자체는 새 방법이 아니다. bbox-only SFT가 얻은 위치 개선의 직접 활용과 외부 활용이 구분되는지를 확인하는 것이 의사결정 가치다.

각 환자에 TL/TR/BL/BR 네 질문을 독립 대화로 실행한다. 조건은 D_M0, D_B0, B0 예측 bbox와 영상을 받는 M0 reader L, bbox 값만 unavailable인 동일 문구의 U, GT bbox oracle O_M0/O_B0다. M0 official_long·concise bbox 및 B0 concise bbox에 동일 규칙을 적용한다. 빈 bbox와 출처 실패를 구분한다. 누락·출처 검증 실패는 실행 오류로 중단하고, 검증된 실제 모델의 invalid bbox만 coverage 실패로 처리한다.

항상 yes/no, D24에서 고정한 사분면별 다수 답과 최빈 네 답 패턴, M0/B0 회색 영상 각 네 요청을 유지한다. E에서 찾은 최빈 패턴은 사후 prior 상한으로 별도 표시한다. Oracle은 실용 비교군이 아니다. 규칙의 bbox 생성 비용, reader의 추가 호출, 기존 출력 재사용으로 절약한 비용을 구분한다.

후속 방법 주장에는 직접 질의 SFT 및 동일 자료를 사용하는 detector/encoder+head 대안이 필요하다. 현재 SFT bbox를 전용 detector라고 부르지 않는다.

## 현재 자산과 수정 범위

현재 `approach/rsna-spatial-transfer`, HEAD `3271c85f34c135081bba28352baa31468125f842`를 유지한다. 필요한 코드가 현재 브랜치에 있으므로 새 선별 반입은 없다. 전체 스냅샷은 재사용 미승인이며 다음 실제 경로를 수정·검증한다.

- `roi23_spec.py`, `qa_spec.py`: 승인된 기하·질문·parser를 유지한다.
- `roi23_data.py`, `roi23_requests.py`: 원본 자료·bbox 출처 검증, 요청 재구성, 선택한 fmt 전달 및 조건부 seed 요청을 연결한다.
- `roi23_protocol.py`: stage별 필수 입력과 선행 decision 잠금을 강제한다.
- `roi23_gen.py`, `roi23_run.py`: 기존 worker·입력·completion 검증을 활용하고 실제 중단·재개 및 소유권을 검증한다.
- `roi23_pipeline.py`, `roi23_eval.py`: 단계 gate, 공통 완전성 검사, strict/semantic 지표와 보수적 CI의 판정 연결을 완성한다.
- `test_rsna_iter023.py`와 실제 의존하는 `generate.py`, `geometry.py`, `parse.py`, `metrics.py`, `lora.py`, `prompts.py`, `queue_lock.py`, `lock_protocol.py`, `inputs.py`, `eval_gate.py`, `qa_requests.py`, `__init__.py`를 현재 실행 범위에서 검사한다. 이전 반입 manifest의 미완료 required_checks를 결과에 연결한다.

B0/B29/B43은 `results/iter_012/train/lr2e-4_s{17,29,43}/epoch_05/adapter.pt`다. 이번 계획 단계에서 세 파일 SHA256이 iter_023 계획과 일치함을 확인했다. 실행 시 파일·tensor digest, rank16/alpha32, epoch·선택 파일 `results/iter_012/select/pick_seed{17,29,43}.json` 연결을 재검증한다.

# Proposed Experiment

## 1. 복구와 기존 출력 재사용

실행 호스트에서 부모·worker의 PID/starttime·lock·attempt·종료 상태를 확인한다. 살아 있는 작업을 중복 실행하거나 claim을 지우지 않는다. 현재 세션의 종료까지 자식을 관리하고 종료 코드를 수집하는 방식으로 실행한다. background 작업 시작 후 대기 문구만 남기고 호출을 종료하지 않는다. 권한 거부를 nohup 등 다른 수단으로 우회하지 않는다.

기존 manifest·요청·protocol·원시 출력은 읽기 전용 출처로 유지한다. 현재 코드와 과거 protocol의 차이를 파일별로 기록하고, 생성 의미에 영향이 없는 변경과 입력·prompt·생성 설정 변경을 구분한다. 재사용 가능한 record는 원본 파일 hash·record 식별자·원래 protocol/config/adapter/input digest를 연결한 별도 manifest로 가져온다. 과거 record의 protocol digest를 새 값으로 바꾸지 않는다.

부분 실행의 47개 record는 개별 검증 후 재사용할 수 있지만 과거 job 전체가 완료됐다고 표시하면 안 된다. 미완료 요청만 새 경로에서 생성하고, 검증된 출처 record와 새 record의 합집합으로 완전성을 확인한다. pilot과 정식 출력이 중복되면 명시적인 출처 우선순위로 한 요청을 한 번만 사용하고 충돌은 중단한다. 호환성을 입증하지 못한 record만 재생성하며 원본을 보존한다.

## 2. 고정 과제·자료

원 계획대로 주석 opacity bbox 중심이 지정 사분면에 하나 이상 있는지 판단한다. `[y_min,x_min,y_max,x_max]` 중심을 사용하며 500 경계는 lower/right, 좌우는 표시 영상 기준이다. 모든 환자에게 네 질문 전부를 주고 GT로 질문을 선택하지 않는다. direct prompt에 GT·category·box 개수를 넣지 않는다.

주평가는 모든 GT 중심이 두 중앙선에서 각각 25 이상 떨어진 환자다. 경계 집단도 동일 질문을 생성해 보조 결과로 보고한다. no는 해당 사분면에 주석 bbox 중심이 없다는 의미이며 임상 정상이나 병변 픽셀 부재가 아니다.

D24는 기존 validation opacity에서 가장 큰 bbox 중심의 네 사분면별 SHA256 순서로 6명씩 선택한 기존 집합을 유지한다. 선택 key `iter023-D24-v1|`도 변경하지 않는다. E60은 기존 E180 opacity 60명, E200은 기존 E600 opacity 200명이다. 주평가/경계 수는 각각 48/12명, 160/40명이다. 환자·영상 hash 중복과 train 연결을 확인하며 기존 reserve에서 새 표본을 뽑지 않는다.

## 3. 동작 확인: D24

새 학습 update는 0이다. 기하·parser 기존 검사를 실행하고 정확히 margin 25 및 그 직전 경계 검사를 보강한다. 최소 8개 D overlay로 네 사분면·단일/다중 box·경계 인접 사례를 확인한다. 실제 공식 입력 대조와 고정 8명의 과거 validation bbox 연결로 adapter sanity를 수행한다. 작은 sanity의 불일치는 입력·환경·token 차이로 분리하며 완료된 본학습을 재실행하지 않는다.

D24 bbox M0 48요청과 B0 24요청의 완전성을 확보한 뒤 여섯 QA 조건 24×4×6=576요청을 수행한다. 조건별 semantic valid 95% 이상을 요구한다. plain이 실패하면 원래 정한 JSON 출력 지시로 D24 전체를 한 번만 추가 실행한다. 공통 형식은 정답률이나 효과 크기가 아닌 모든 조건의 형식 통과 여부로 선택하고 둘 다 통과하면 plain을 쓴다.

O_M0/O_B0 각각 전체 96개 질문을 분모로 정확도 90% 이상을 요구한다. invalid도 분모에 포함한다. 형식 또는 oracle gate가 해결되지 않으면 E로 진행하지 않고 형식·지시 문제로 보고한다. 새 prompt 탐색이나 학습을 자동 추가하지 않는다.

현재 경로에서 고정 D 요청 24개의 정상 실행과 자기 worker 중단·재개, 자기 pipeline 중단·재개를 비교한다. 자식 회수·claim 소유권·tail 격리·고유 요청 수·greedy suffix 일치를 검증한다. 별도 fixture에서 완료 후 source/query/adapter/completion 변조, 요청 누락·중복·잉여, stage 우회, 기존 decision 변조를 거부하는지 확인한다.

## 4. 가능성 탐색: E60

D gate와 실행 검증을 통과하면 여섯 조건의 60×4×6=1,440개 요청을 생성한다. bbox 규칙은 검증한 iter_012 원시 출력을 사용한다. M0/B0 gray는 각각 네 고유 요청이며 환자 수만큼 복제 생성하지 않는다.

E 이전에 prompt·fmt·parser·집합·margin·metric·prior·확대 규칙을 잠근다. 기존 E는 개발 자료다. E의 semantic valid와 oracle 결과도 보고하고 해석 gate를 만족하지 않으면 의미 능력 결론 및 후속 확대를 보류한다.

## 5. 조건부 규모 확대: E200

자료·실행·형식 gate 통과 후 원래 기준 중 하나를 만족하면 추가 140명, 3,360요청을 생성한다. E60 결과를 검증해 재사용하며 중복 실행하지 않는다.

- Δ_direct 또는 외부 규칙 개선 G의 점추정이 0.10 이상.
- R_B0 또는 reader L의 Q4가 D_B0보다 0.10 이상 높음.
- 위 관련 paired 비교의 CI가 +0.10을 포함하며, discordance 비율 Wilson 상한으로 계산한 `1.96*sqrt(q_upper/160)`이 0.12 이하.

마지막 기준은 정밀도 개선의 근사이며 검정력 보장이 아니다. 평가 함수와 독립 소규모 기준 계산이 같은 decision을 내는지 확인한다. 확대하지 않으면 실제 효과·CI와 해당 기준의 실패 이유를 남긴다.

## 6. 조건부 seed 비교와 독립 확인

E200에서 아래의 신뢰할 만한 직접 전이 또는 해석 가능한 직접·외부 활용 차이가 확인되면 기존 B29/B43을 평가한다. 각 seed의 D24 oracle 96요청, 형식 및 adapter sanity를 먼저 통과해야 한다. 직접 질의는 200×4×2=1,600요청이며 저장 bbox에 같은 규칙을 적용한다. gate 실패 seed는 별도 보고하고 최고 seed를 고르지 않는다.

이번 반복은 개발 진단이며 seed 추가도 독립 환자 확인이 아니다. 새로운 독립 확인 집단은 이번에 평가하지 않는다. 유망한 결과가 나오면 다음 계획에서 동일 소견을 평가할 다른 원천 자료 또는 적절한 미사용 환자로 독립 확인을 설계한다. MRI F139와 기존 reserve는 보존한다.

## 7. GPU 배치·비용·재개

매 실행 직전 nvidia-smi로 허용 GPU 0,1의 UUID·가용 메모리를 확인하고 여유가 큰 장치부터 배정한다. 상속된 가시성과 논리/물리 장치 대응을 기록한다. 다른 사용자의 프로세스는 건드리지 않는다.

대표 D QA 48개를 고정해 총 2 worker와 메모리가 허용하는 총 4 worker를 비교한다. M0/B0와 reader/oracle 입력 길이를 포함하고 동일 요청의 greedy suffix·누락·중복이 일치해야 한다. 최장 prompt와 4000-token KV 상한의 별도 메모리 stress도 수행한다. 이 stress 출력은 과학적 평가에 넣지 않는다.

iter_023의 pilot peak allocated 약 8.126/8.237GiB와 장치 전체 약 17.7GiB는 참고값이다. 현재 긴 출력의 측정 peak와 worker당 최소 2GiB, 다른 프로세스 점유의 합이 장치 용량 이내일 때만 복수 worker를 배치한다. 전체 요청/분, 로딩 포함 wall-clock, 긴 출력 지연, allocated/reserved 및 장치 전체 peak, CPU·I/O 경합과 오류를 기록한다. 안전성과 정합성을 통과하고 총 완료시간이 줄어드는 구성을 선택한다. 이득이 없거나 메모리가 부족하면 2 worker를 유지하는 근거를 남긴다.

최대 주요 QA는 E200 4,800건, 추가 seed 1,600건, D24 576건과 seed oracle 192건이며 fallback·sanity·재개·처리량 검사가 별도다. E60은 E200에 포함된다. 원 계획의 20–60 requests/min 가정에서는 로딩·검사를 포함해 약 2–8시간이지만 미측정 추정이다. D의 실제 bbox/QA 처리량을 분리해 남은 요청 수로 예상 시간을 갱신한다. 임의 시간 상한은 두지 않는다.

worker별 원시 출력, 원자적 claim·completion·decision, attempt별 PID/starttime·종료 코드, 진행량·자원 로그를 남긴다. OOM·진행 정체·비정상 입력 발생 시 자기 작업을 안전하게 종료하고 원인을 기록한 뒤 batch/동시성을 조정한다. protocol이나 claim 삭제로 재개를 우회하지 않는다.

# Implementation Tasks for Claude

1. 실행 호스트 상태와 현재 branch·사용자 변경 범위를 확인한다. 이전 작업·기록을 보존하고 `results/iter_024`의 복구 manifest 및 호환성 설명을 만든다.
2. stage별 필수 provenance를 정의한다. 코드·query·집합·정답·현재 영상·checkpoint 선택/adapter·원본 bbox record 및 completion·이전 stage decision이 해당 stage protocol에 반드시 연결되게 한다. 자기 protocol을 자기 자신에 잠그는 순환 구조는 피한다.
3. 하나의 공통 검증 경로로 manifest에서 예상 환자×질문×조건×checkpoint 행렬을 재구성한다. 요청 파일·현재 protocol/config/adapter·원시 결과·completion을 모두 대조한다. 요청 파일 자체의 누락도 검출해야 한다.
4. D 형식 선택→E60 허용→E200 확대→seed 허용의 decision을 구현한다. CLI 직접 실행, 재개, 완료 건너뛰기, 평가에서도 검증하며 파일 존재만으로 통과하지 않는다. 선택 fmt를 모든 요청·평가에 전달한다.
5. 기존 `verify_job`·`verify_completion`을 실제 평가와 bbox source 경로에 연결한다. 새 검증기가 과거 실패 completion을 성공으로 바꾸지 않도록 한다. 과거 부분 record 재사용은 개별 출처 검증과 새 완료 집합 검증으로 분리한다.
6. 전체 분모의 oracle 정확도, strict/semantic 결과, 환자별 네 답, 사분면별 지표, box 개수별·경계 집단 결과와 고정 prior를 저장한다. 퇴화 CI의 차이 구간을 계산해 모든 판정에 사용한다.
7. 필수 CPU·GPU·재개·처리량 검증 후 같은 호출에서 D24와 허용된 E 단계를 실제 완료한다. 단순 코드 준비나 background 시작을 실험 완료로 보고하지 않는다.
8. 재현 명령·실제 사용량·stage별 decision·확대/보류 사유·미실행 조건·원시 결과 위치를 보고한다. 기존 SFT 성과와 이번 신규 결과를 구분한다. 소스 보존 커밋은 orchestrator에 맡기고 무관한 MRI·학습 실행기 리팩터링은 하지 않는다.

# Evaluation (성공/실패 기준 포함)

주지표 Q4는 환자의 네 답을 모두 맞힌 비율이며 invalid 하나라도 실패다. 주 비교는 `Δ_direct=Q4(D_B0)-Q4(D_M0)`, 보조 위치 개선은 `G=Q4(R_B0)-Q4(R_M0_official)`이다. M0 concise, L−U, R_B0−D_B0, L−D_B0도 함께 보고한다.

환자 단위 paired bootstrap 10,000회, seed 23023, 95% CI를 유지한다. 개선·악화·동일 환자 수를 저장한다. 퇴화 시 개선/악화 확률 각각에 Bonferroni 보정한 CP 구간을 구하고 차이 구간 `[L_improve-U_worsen, U_improve-L_worsen]`을 [-1,1]로 제한해 판단에 사용한다. bootstrap 원본 구간도 보존한다.

사분면별 sensitivity/specificity·balanced accuracy, 평균 질문 정확도, strict/semantic valid, bbox invalid/empty와 coverage, oracle, 1/2/3개 box 및 경계 결과를 보고한다. 영상 응답의 환자 연관성은 네 답 벡터를 함께 옮기는 10,000회 permutation으로 보조 평가하고 `(b+1)/(B+1)` 보정을 사용한다. 유효 환자만 포함한 범위와 누락 coverage를 명시한다.

- **양성:** E200에서 Δ_direct≥0.10, CI 하한>0, B0가 고정 prior·gray보다 높고 영상별 응답 연관성이 지지되며 semantic valid가 조건별 95% 이상이면 가까운 질의 전이를 지지한다. 원 계획의 조건부 seed 비교로 진행하고 이후 외부 원천 재현을 검토한다. 신방법·임상 reasoning·일반적 공간 이해의 증명은 아니다.
- **직접·외부 활용 차이:** G의 CI 하한>0, R_B0−D_B0≥0.10 및 그 CI 하한>0, Δ_direct CI 상한<0.10이며 oracle≥90%·semantic valid≥95%·실행/정답 검증을 통과하면 해석 가능한 활용 차이로 보고한다. 작은 양의 전이는 그대로 보존한다. seed 비교 후 지시 영향·재현 범위를 판단하고 다음 방법 계획에서만 강한 직접 질의 SFT와 비교한다.
- **음성:** 직접 전이와 외부 규칙 개선이 작고 CI가 +0.10을 배제하면 현재 과제의 추가 전이 근거가 부족하다고 판단한다. 기존 bbox SFT 전체를 기각하지 않는다. 규칙/reader가 충분한 경우 유효한 baseline으로 보존하고 내부 학습의 추가 가치가 필요한 조건을 검토한다.
- **불확정:** E60에서는 사전 확대 규칙을 적용한다. E200 이후에도 중요한 효과를 구분하지 못하면 효과·CI·미해결 설명을 보고하고 추가 표본이 다음 판단을 바꿀지 후속 계획에서 검토한다. reserve를 자동 개방하지 않는다.
- **gate 또는 실행 실패:** 형식·oracle 실패는 의미 능력의 실패와 분리한다. source 불일치·잘못된 adapter·누락·중복·좌표 오류는 유효성 문제다. 준비 성공이나 partial bbox를 유효한 전이 실험으로 계산하지 않는다.

# Risks / Checks

bbox 중심은 주석 기하이며 실제 병변 segmentation 중심이나 임상 음성을 보장하지 않는다. 모든 환자가 opacity 양성이므로 정상 specificity를 주장하지 않는다. margin 적용 coverage와 경계 결과를 함께 보고한다.

D24는 지시·연결 확인을 위한 층화 자료이고 E60/E200은 기존 개발 자료다. 환자·영상 비중복은 사전학습 미노출을 보장하지 않는다. GT oracle 통과도 직접 시각적 지시 이해의 완전한 통제는 아니다.

잠금·completion·decision 검사 보완은 현재 사용할 경로로 제한한다. 검증 완료된 일회성 자료 준비는 hash·호환성을 확인해 재사용하며, 과거 프로토콜을 현재 코드에 맞춰 덮어쓰지 않는다. 현재 실행 호스트 생존 여부와 긴 출력 메모리는 실행 시 확인해야 한다.

## 대규모 GPU 필요 후보

다양한 영역 질의·grounding·일반 QA의 vision encoder–언어 모델 공동 post-training을 후보로 보존한다. 현재는 필요성 미확정이며, 이번 직접 활용과 강한 외부 연결 비교 및 후속 직접 질의 SFT 근거가 먼저다.

# 계획의 근거 (GPT 조사 노트)

## 새로 확인한 것

읽기 전용으로 `agent/GOAL.md`, `REPORTING_STYLE.md`, `LIMITATIONS.md`, `CODE_ASSETS.md`의 관련 기록, iter_009·012의 원본 리뷰, iter_023의 plan.md·review.md·review.json·claude_report.md·reuse_manifest.json 및 현재 roi23 코드를 확인했다. iter_012–018의 질문 차이와 문헌 비교는 iter_023 계획의 원본 조사 기록을 이어받는다. 새로운 과학적 결과가 없어 같은 문헌의 광범위한 재조사는 하지 않았다.

- research HEAD는 `3271c85f34c135081bba28352baa31468125f842`다. `git status --short`와 `git diff --stat` 출력은 비어 있으며 roi23 모듈 8개와 `test_rsna_iter023.py`가 tracked 상태로 존재한다. 새 반입은 필요 없다.
- 저장 JSONL을 직접 읽어 정식 D24_bbox M0가 13+17+13+4=47건, pilot M0/B0가 각각 6건임을 확인했다. QA 성능은 아직 없다. 실행 호스트의 현재 프로세스 생존 여부는 이 파일 검사로 확정하지 않았다.
- B0/B29/B43 adapter.pt를 읽어 계산한 SHA256은 원 계획과 각각 일치한다: `5f542af96df705e567bf4cfb000398b09313db2456c577e772bd76481799cf29`, `d4db2f2ab10d134b4352c7f57cc0ca5c497da3bce388d9cc91751ec9ca6d1fc9`, `e6e4730add1d942c81fb89aabd5477a779668d2f0f8ef01cc21af33032584f4a`. tensor 로드와 GPU sanity는 이번 계획 단계에서 실행하지 않았다.
- `roi23_pipeline.py`는 E 요청 생성에 선행 decision을 요구하지 않고 fmt를 plain으로 고정한다. `_verify_and_collect`는 protocol digest를 첫 출력에서 받아들이며, D bbox 읽기는 중복을 사전 덮어쓰기로 처리한다.
- `roi23_protocol.py`의 extra는 선택적이다. 필수 source·집합·정답·checkpoint·decision의 stage별 누락을 강제 거부하지 않는다.
- `roi23_run.py`에는 재사용 가능한 `verify_job`·`verify_completion`, worker별 메모리 여유 계산과 자식 종료 처리가 이미 있다. 새 실행기를 중복 구현하기보다 이 검증을 실제 pipeline·평가 경로에 연결해야 한다.
- `roi23_eval.py`는 strict 파싱 결과를 계산하지만 보고서 연결이 부족하다. 퇴화 bootstrap에서 개선/악화 비율의 CP 구간만 기록하며 차이 구간을 판정에 연결하지 않는다. oracle 집계는 valid 응답만 분모로 삼고 있어 원 계획의 전체 질문 정확도와 다르다.
- `ROI23_RUN_ROOT`가 이미 구현돼 있어 `results/iter_024`를 새 결과 경로로 사용할 수 있다.

## 의미

기존 SFT bbox 개선은 유지된다. 이번 장애는 전이 가설의 음성 결과가 아니라 실행·평가 연결의 미완성이다. 알려진 결함의 수정과 실제 D24/E60 진단이 다음 선택을 바꿀 작업이다. 파일·코드 수정, 테스트 및 GPU 실험은 수행하지 않았다.

## 대규모 GPU 필요 후보

다양한 공간 질의·grounding·일반 QA를 결합한 vision encoder–언어 모델 공동 post-training을 후보로 보존한다. 이번 직접 활용과 외부 연결 비교가 그 필요성을 입증하지는 않는다.
