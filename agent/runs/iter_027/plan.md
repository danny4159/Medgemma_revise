# 요약

- **이번에 할 일:** 평가·decision·재개 검증을 보완하고 기존 E200의 미완료 요청을 마친다.
- **필요한 이유:** E60에서 SFT는 base보다 좋지만 전체 bbox 복사 대비 이득은 불확정이다. 다중 사분면 직접 선택 0/22는 사전 기준 10%를 아직 배제하지 못한다.
- **확인할 기준:** primary 160명과 다중 사분면 66명에서 기존 S·Q4_select·C_query·donor 기준을 적용한다.
- **주의·다음:** oracle 실패는 원인 해석의 한계로 유지한다. 새 학습과 독립 확인은 없으며 seed는 원래 조건을 충족할 때만 평가한다.

# Current Understanding

iter_012의 RSNA SFT 개선은 유효한 baseline이다. 확인 양성 400명에서 base official F1@0.3은 0.1650, SFT 세 seed는 0.6308–0.6528이었다. 이는 새로운 영역 선택 능력의 증명이 아니다.

iter_015–018에서 전역 QA의 형식 효과와 검출·개수·좌표 packet 효과를 이미 조사했다. 이번은 같은 분석을 반복하지 않고, 학습한 bbox 출력 형식에서 요청 영역만 바꾼 iter_026 진단을 완수한다. iter_025 marker 분석도 완료된 보완으로 보존한다.

iter_026 리뷰의 primary 48명 재계산은 B0−M0 S +0.228624, B0−Copy_B0 +0.000218, Rule_B0−direct B0 +0.403320이다. 다중 사분면 22명에서 직접 B0는 0명, 규칙은 11명 성공했다. D oracle도 두 모델 모두 다중 사분면 0/14이며 입력 목록 schema 불일치가 있다. 따라서 검출 향상과 선택 전이, 지시 해석과 시각 활용을 아직 완전히 분리하지 못했다.

유지: checkpoint·split·prompt·parser·metric·확대 및 성공 기준, 기존 원시 출력·protocol. 변경: 계획과 어긋난 집계·decision 및 실행 검증. 보류: oracle prompt 수정, 새 학습·loss, MRI F139·reserve·외부 자료. iter_022는 사용자 전환 기록으로 그대로 보존한다.

# Strategy Check / 연구 방향 판단

iter_026 계획과 리뷰의 전략 비교를 유지한다. 이번은 이미 정당화된 확대의 복구이며 새로운 대규모 투자가 아니다.

중요한 질문은 학습한 위치 정보를 미학습 선택 요청에 활용할 수 있는가이다. 현재 방법 개선은 이 질문을 구분하지 못하고, 다른 task로의 전환은 남은 정밀도 확보 기회를 버린다. 현재 진단 완수는 추가 환자 140명의 고정 요청으로 다음 판단을 바꿀 수 있다.

E200 이후에도 oracle·인터페이스 설명만 남거나 추가 표본이 투자 판단을 바꿀 근거가 없으면 자동 연장하지 않는다. 다음 전략 판단에서 현재 원인 진단, 방법 개발, 다른 질문을 비교한다. 음성 결과는 현재 인터페이스 범위로 한정한다.

# Hypothesis

B0가 M0보다 높은 직접 선택 성능을 보이며, 그 차이에 전체 bbox 복사로 설명되지 않는 질의 조건화와 환자 영상 대응이 포함된다는 기존 가설을 유지한다.

경쟁 설명은 전체 검출 개선에 따른 복사 점수 상승, 위치 prior, 외부 규칙으로 충분한 선택, 지시·좌표 인터페이스 실패다. E200은 이 가설의 사전 정밀도 보완이며 새로운 독립 확인이 아니다.

# Limitation Evidence / Correct Usage Checks

`lesion-grounding-generalization`은 RSNA 정상 사용 조건의 validated 한계다. 이번 직접 대상인 `rsna-region-selection-transfer`와 `rsna-quadrant-oracle-interface`는 observed이며 일반적 전이 실패로 승격하지 않는다.

모델 revision `91850547d9f0b2fdd21aa7c5f4f3d1a8a52c243b`, bf16, greedy, RGB·padding·좌표 규약, 공식 template, 1000→2000→4000 EOS ladder를 유지한다. 최종 비EOS는 invalid다.

공식 입력 근거는 보존된 `results/iter_009/source/official/cxr_anatomy_localization_with_hugging_face.ipynb`다. 기존 sanity는 한 영상·V_TL 및 공통 tensor key 비교에 한정됐다. 독립적으로 구성한 공식 입력과 실제 worker 입력에서 tensor key 집합·shape·dtype·값을 모두 검사하고 실패 시 비정상 종료한다. D의 고정 영상으로 실제 사용 V·reader 경로를 포함한다. text-only는 재사용하는 경우 해당 공식 경로도 검증한다.

B0 adapter hash·tensor digest·대상 모듈·실제 로드를 확인한다. 기존 D 전체 bbox 출력에서 hash로 고른 M0/B0 각 4건의 재현 sanity를 보완한다. 이미 완료된 같은 검사에 현재 코드·입력까지 연결된 근거가 있으면 재실행하지 않는다.

D oracle 출력과 schema 오류는 그대로 보존한다. 이번에는 oracle을 고쳐 새 성공 gate를 만들지 않는다. 목록 선택 실패를 시각 전이 실패로 해석하지 않는다.

# Contribution Path / Baselines / Reuse

신규 contribution은 미확정이다. iter_026에서 검토한 영역 지시·명시적 다중 과제 학습과 구별하려면 bbox-only 적응의 미학습 선택 전이를 입증해야 한다. 이번 결과만으로 새로운 선택 알고리즘이나 임상 reasoning을 주장하지 않는다.

비교군은 V_M0·V_B0, M0 official_long/concise·B0 bbox의 Rule/Copy, Empty, 원본 영상과 B0 proposal을 받는 Reader_M0다. 누락된 M0 concise와 보조 분석을 복원한다. Empty는 source bbox 유효성에 의존하지 않는 고정 빈 출력이다. source 누락은 실행 오류, 실제 invalid bbox는 모델 실패로 구분한다.

직접 4회, 규칙 bbox 1회, reader bbox 1회+reader 4회의 환자당 비용을 구분한다. 저장 출력도 원래 생성 비용을 보고한다. 기존 학습량을 명시하고 새 학습은 하지 않는다. 후속 방법에는 강한 직접 질의 SFT와 detector/encoder+head 대안이 필요하다.

현재 branch와 HEAD `b8be58c9f3c92266e885ca8c3f5384dbe412b4bd`를 이어간다. 다음 파일이 현재 branch에 있으므로 `reuse_assets=[]`다.

- 제한 승인 구성요소: `rsna_diag/__init__.py`, `parse.py`, `metrics.py`; 기존 범위의 `geometry.py`, `lora.py`.
- 수정 대상: `rsna_diag/roi26_eval.py`, `roi26_decide.py`, `roi26_protocol.py`, `roi26_requests.py`, `roi26_data.py`, `roi26_gen.py`, `roi26_run.py`.
- 연결 대상: `eval_iter026.py`, `decide_iter026_d.py`, `decide_iter026_e60.py`, `build_iter026_d.py`, `build_iter026_e.py`, `launch_iter026_d.py`, `launch_iter026_e.py`, `sanity_iter026.py`, `throughput_iter026.py`와 실제 import되는 입력·lock 모듈.

전체 스냅샷은 승인본이 아니다. 이번 호출 경로만 검증하며 MRI·학습 실행기의 주변 결함은 정비하지 않는다.

B0는 `results/iter_012/train/lr2e-4_s17/epoch_05/adapter.pt`, 기록된 SHA256은 `5f542af96df705e567bf4cfb000398b09313db2456c577e772bd76481799cf29`다. 조건부 s29/s43도 동일 경로 패턴의 epoch_05를 사용하고 iter_026 계획의 hash와 현재 파일을 대조한다. 출처 누락을 재학습이나 임의 checkpoint 대체로 해결하지 않는다.

# Proposed Experiment

## 1. 실행 상태와 보존

구현 전에 실행 호스트에서 기존 launcher·worker의 PID/starttime·소유 lock·부모 관계·종료 코드·진행을 확인한다. 살아 있는 정상 작업은 중복 실행하거나 소스를 수정하지 않고 완료를 기다린다. 진행 정체는 소유 작업만 기존 복구 절차로 처리한다.

신규 출력·평가·검사는 `results/iter_027/`에 기록한다. iter_026 원시 파일·claim·completion·protocol·report는 덮어쓰지 않는다. 기존 출력은 파일 hash와 요청별 출처를 가진 reuse manifest로 연결한다. 코드 변경 전후 SHA와 생성 의미의 호환성을 기록한다. 평가·소유권 수정 때문에 유효한 과거 출력을 재생성하지 않는다.

## 2. 동작 확인

새 학습 없이 CPU fixture와 필요한 GPU 검사를 수행한다. 고정 D 24요청에 M0/B0 각 12건, 네 영역·빈/비빈 GT를 포함한다. 무중단 기준, worker 중단/재개, 부모 종료/재개의 최종 24요청을 비교한다. 완료 token·provenance 일치, 누락·중복·잉여 0, 자식 회수·종료 코드·원자적 completion을 확인한다. 실패·재시도 출력도 보존한다.

입력·adapter·request·decision·source bbox·completion 변조, 부분 JSONL tail, 살아 있는 다른 소유자 claim, 완료 경로의 입력 변경을 거부하는 검사를 수행한다. tail 복구는 소유권 확보 후 새 attempt에서 수행한다.

## 3. 가능성 탐색 결과의 정정

새 E60 GPU 탐색은 하지 않는다. 기존 D488·E720을 검증해 재사용하고 새 경로에 수정 평가를 만든다. E60 primary 48명과 boundary 12명, 각각의 다중 사분면 집단을 분리한다. donor도 각 집단 안에서 기존 SHA 순서 규칙으로 구성한다.

D 형식 gate는 직접 각 96요청 중 valid≥92이며 실행·입력 검증도 충족해야 한다. E60 확대는 직접 각 모델 valid≥95%와 기존 세 조건 중 하나다. 형식은 전체 및 primary를 모두 명시하고 기존 전체 E60 분모를 다른 분모로 조용히 바꾸지 않는다.

기능적 차이 조건의 C_query≥0.05는 점추정이다. 모듈형 조건의 reader 차이는 reader−direct다. 정밀도 조건은 다중 사분면 Rule_B0 Q4≥0.20이고 direct exact CI가 0.10을 포함하는 것이다. 리뷰상 이 조건은 유지된다. 수정 결과가 다르면 원인을 해결하기 전 새 생성으로 진행하지 않는다.

## 4. 규모 확대

원래 E200: primary 160명, boundary 40명, 다중 사분면 각각 66명·24명. 모든 환자에게 동일 TL/TR/BL/BR 네 질의를 유지한다. GT 중심 margin·500 경계·표시 영상 좌우 규약과 prompt를 변경하지 않는다.

총 요청은 200×4×3=2,400건이다. E60 720건과 유효한 E200_extra 부분 출력을 재사용해 남은 요청만 생성한다. E200_extra 원래 규모는 140×4×3=1,680건이다. 조회한 M0 405행은 잠정 수치이므로 시작 시 고유·유효성 감사 후 정확한 잔여량을 고정한다.

완료 후 한 번 평가한다. 부분 성능으로 prompt·parser·표본·checkpoint·기준을 변경하지 않는다.

## 5. 조건부 seed와 독립 확인

기존 s29/s43은 E200 양성 기준을 모두 충족할 때만 자동 재현한다. 원 계획의 다른 경로는 형식과 oracle 해석이 확보된 명확한 규칙 격차지만, 현재 oracle 실패·schema 불일치로 이 전제는 충족되지 않았다. 규칙 격차만으로 이 경로를 열지 않는다. 이번에 새 oracle 실험으로 gate를 만들지 않는다.

양성 경로가 열리면 두 seed 모두 E200 직접 800건씩, 총 1,600건을 평가한다. seed별 저장 bbox Rule/Copy도 비교하고 유리한 seed만 선택하지 않는다. 새 학습은 0 updates다.

이번 독립 확인은 미실행이다. E60/E200은 개발 자료이며 독립 표본 두 번으로 세지 않는다. reserve·MRI F139는 보존한다.

## GPU 배치·시간·재개

실행 직전 `nvidia-smi`로 허용 0,1의 실제 여유와 UUID 매핑을 확인한다. 기존 pilot은 M0-only였으므로 고정 D 24요청을 M0/B0 균형으로 2 worker와 4 worker에서 비교한다. 가능하면 재개 기준 출력과 공유해 중복 비용을 줄인다. 동일 요청·출력 길이·greedy 설정을 사용한다.

전체 wall 처리량, 로딩 제외 처리량, 긴 출력 지연, GPU별 peak, OOM·CPU/RAM/I/O 경합과 token 정합성을 기록한다. 안전한 구성 중 전체 wall이 짧은 것을 채택하고 차이가 불명확하면 낮은 동시성을 선택한다. 1 worker/GPU 채택 이유는 실측으로 남긴다. GPU당 2 worker도 허용하되 동시 peak 합계+다른 점유+worker당 2GiB가 용량 안에 들어야 한다. 기존 peak 약 17,897MiB는 참고이며 긴 출력 조건을 현재 경로에서 확인한다.

E60 실제 처리량은 M0 약 13.0, B0 34.1, reader 24.7 req/min이다. 이를 적용하면 미완료 1,680건 전체는 약 82분, M0 405건이 모두 유효하게 재사용되면 잔여 생성은 약 50분으로 추정된다. 이는 긴 출력·대기·검사 비용을 제외한 추정이다. 검증과 pilot을 포함한 전체 작업은 약 2–4시간을 예상하며 실측으로 갱신한다. 조건부 seed는 추가 1,600건/실측 처리량으로 별도 산출한다. 임의 시간 상한은 두지 않는다.

요청별 append·고유 ID·원자적 claim·worker별 파일·단계 checkpoint로 재개한다. OOM·비정상 수치·진행 정체 시 원인을 기록하고 batch/동시성만 조정한다. 성능 기준과 출력 길이는 유지한다.

# Implementation Tasks for Claude

1. 소유 프로세스 상태를 확인하고 원본·부분 결과를 보존한다. 신규 경로와 과거 결과의 호환 manifest를 만든다.
2. evaluator를 primary/boundary별로 수정한다. donor invalid는 해당 donor 점수 0으로 처리해 사전 invalid 규약을 유지하고 NaN 삭제로 환자·쌍을 제외하지 않는다. source 누락은 점수 0으로 숨기지 않고 오류로 중단한다.
3. report와 decision의 단일 schema를 정하고 D→E60→E200→seed의 내용·hash·필수 검증 상태를 모든 진입점에서 강제한다. 필드 부재를 기본 false나 성공으로 숨기지 않는다.
4. 잠긴 manifest/spec에서 예상 환자×조건×checkpoint×영역을 독립 재구성한다. 관측 요청 ID만으로 완전성을 정의하지 않는다. 요청·원시 결과·현재 입력·completion·checkpoint·source bbox와 대조한다.
5. 실제 launcher·평가기·decision 코드, source bbox 원시 파일·completion, checkpoint manifest·파일 digest, sets·labels·GT·이미지·공식 입력 근거를 단계별 필수 잠금에 포함한다. 생성 전 protocol과 생성 후 completion·report의 연결은 순환 hash 없이 단계별로 구성한다.
6. 공식 tensor key 전체 비교·adapter·기존 bbox sanity, 통제된 재개와 변조 거부를 실제 실행한다. 감사가 끝난 과거 완료 출력은 재사용하되 새 검사가 과거 실행 당시 수행됐다고 기록하지 않는다.
7. 동일 24요청의 2/4 worker 비교로 구성을 선택한 후 E200의 빠진 요청을 실행한다. 실제 행렬과 모든 종료 코드를 확인해 완료 처리한다.
8. M0 concise baseline, IoU@0.5, 요청 밖 FP·복사율·빈 출력·영역별·질의 유형별 분석을 복원한다. 기존 marker 보완은 반복하지 않는다.
9. 독립 작은 기준 구현으로 metric·CI·decision을 대조한다. 완벽한 선택 S=1/Q4=1, 전체 GT 복사 S=0.4/Q4=0/C_query=0, 빈 목록 S=0/Q4=0을 검증한다. 경계·중복 box·invalid·donor·reader 부호·점추정/CI 구분·seed gate fixture를 포함한다.
10. 실제 도달 단계, 재사용/신규/검사 요청 수, 비용, 결과별 해석과 미실행 조건을 보고한다. 코드 보존은 orchestrator에 맡기며 임의 commit·branch 전환을 하지 않는다.

# Evaluation (성공/실패 기준 포함)

기존 metric을 유지한다. IoU≥0.3과 예측 중심의 요청 사분면 일치를 요구하는 최대 cardinality matching으로 `S_i=2ΣTP/(Σ예측 수+ΣGT 수)`를 계산한다. 요청 밖 예측과 중복은 분모에 남긴다. 네 출력 중 하나라도 invalid면 환자 S·Q4·C_query는 0이다.

Q4_select는 네 영역 모두 TP=예측 수=GT 수일 때 1이다. C_query는 실제 배정 S에서 24개 출력 목록 순열의 평균 S를 뺀다. GT·요청 영역은 고정한다. donor는 primary/boundary 각각 SHA256('iter026-pair-v1|'+ID) 순 인접 쌍으로 구성한다.

환자 paired bootstrap 10,000회, seed 26026의 95% CI를 사용한다. donor는 쌍 단위 cluster bootstrap, Q4 성공률은 two-sided exact binomial CI를 쓴다. Q4 paired 차이와 discordance도 보고한다. 퇴화 bootstrap을 모집단 효과의 정확한 영점으로 해석하지 않는다.

**양성:** E200 primary에서 다음을 모두 충족한다: B0−M0 S≥0.05와 CI 하한>0; B0−Copy_B0 S≥0.05와 CI 하한>0; B0 C_query CI 하한>0; 다중 사분면 B0 Q4≥0.10 및 실제 성공 존재; B0 real−donor S CI 하한>0. 충족하면 기존 두 seed 재현을 수행한다. 기능적 전이 후보로 한정하고 외부 자료·직접 질의 SFT·모듈형 비교는 다음 계획에서 검토한다.

**음성:** 실행·형식이 유효하고 다중 사분면 direct Q4 exact 상한<0.10, Rule_B0 하한>0.20이면 현재 인터페이스의 신뢰할 만한 전체 선택이 제한된다는 근거다. 양의 C_query나 부분 F1은 함께 보고한다. oracle 실패가 남으므로 일반적 시각 전이 부재·내부 원인을 주장하지 않는다. 강한 규칙 baseline을 보존하고 다음 투자 가치를 재검토한다.

**불확정:** E200에서도 기준을 가로지르면 표본·seed·형식·인터페이스 중 원인을 명시한다. 환자 정밀도 부족을 seed 증가로 해결하지 않는다. 추가 실험이 의사결정을 바꿀 구체적 근거가 없으면 확대를 보류한다.

**실행 실패:** provenance·입력·완전성·재개 검증이 실패하면 같은 계획의 복구 대상으로 기록한다. 형식 실패는 현재 인터페이스 평가의 한계이며 SFT 전체의 기각이 아니다. 진단 완료와 가설 지지·신규 기여·GOAL 달성을 분리한다.

# Risks / Checks

- 과거 report를 덮어쓰거나 새 protocol로 과거 출처를 위장하지 않는다. 수정 집계에는 원본과 차이의 원인을 명시한다.
- oracle 실패를 숨기거나 schema 수정 후 점수를 기존 oracle과 합치지 않는다.
- 직접 점수 상승·복사 대비 비유의 차이·영상 대응 효과만으로 새로운 선택 정책을 단정하지 않는다.
- RSNA 주석 밖 소견이나 빈 영역을 임상적 정상으로 해석하지 않는다. boundary를 별도 보고한다.
- 개발 환자의 중복 통제와 사전학습 미노출은 별개다. 이번은 독립 일반화 증명이 아니다.
- 실행 중 소스 변경·중복 worker·공유 출력 충돌을 방지하고 다른 사용자의 프로세스를 건드리지 않는다.

## 대규모 GPU 필요 후보

영역 선택·grounding·일반 QA를 결합한 vision encoder–언어 모델 공동 post-training을 후보로 보존한다. 다기관 자료·큰 batch·여러 seed를 포함하면 추가 메모리와 처리량이 필요할 수 있다. 필요성·신규성은 미확정이며 이번 진단 결과만으로 실행을 예약하지 않는다.

# 계획의 근거 (GPT 조사 노트)

## 확인한 사실

- `agent/GOAL.md`, `agent/LIMITATIONS.md`, iter_026 원본 계획·리뷰·보고서, CODE_ASSETS의 최신 항목과 실제 평가·decision·launcher·protocol 코드를 읽었다.
- 현재 research HEAD는 `b8be58c9f3c92266e885ca8c3f5384dbe412b4bd`이며 status와 diff에 변경이 없다. roi26 모듈과 iter026 실행 파일들이 현재 branch에 있어 선별 반입은 필요 없다.
- 리뷰의 독립 계산에서 E60 primary 48명 B0−M0 S=0.228624, B0−Copy_B0=0.000218이다. 다중 사분면 22명은 직접 B0 0명, 규칙 11명 성공이다. 이는 전체 복사를 넘는 선택 전이의 증거가 아직 부족하다는 뜻이지 동등성이나 일반적 전이 부재의 증명이 아니다.
- 코드에서 primary/boundary를 합친 metric·donor 구성, C_query 점추정을 CI 하한으로 대체한 확대식, reader 차이 부호 반전, report와 decision의 schema 불일치, oracle 해석 조건이 빠진 seed gate를 확인했다.
- iter_026 리뷰는 D oracle의 다중 사분면 성공을 두 모델 모두 0/14로 재계산했다. 보고서의 oracle 정상 해석은 유지할 수 없다. 제공 목록 schema 불일치도 남아 있다.
- 이번 조회 시 E200_extra M0 worker 출력은 합계 405개 비어 있지 않은 행이었다. 고유·유효 요청 수나 현재 프로세스 생존을 검증한 수치는 아니다. E200_extra completion은 조회되지 않았다. 구현 시작 시 다시 확인해야 한다.
- E60 completion의 실제 wall은 M0 1,106.7초, B0 422.6초, reader 583.8초로 각 240요청이었다. 처리량은 각각 약 13.0, 34.1, 24.7 req/min이다. 기존 D pilot의 2/4 worker는 2.41/2.33 req/min으로 4 worker 우위를 보이지 않았고 모두 M0였다. 따라서 균형 잡힌 개발 요청으로 실행 구성을 보완 비교한다.

## 의미와 다음 결정

iter_026의 전략 판단과 사전 확대를 유지한다. 새 문헌 조사나 oracle prompt 탐색보다 평가를 바로잡고 이미 승인된 E200을 마치는 정보 이득이 크다. 기존 계획에 기록된 Targeted Visual Prompting·CURE와의 차별성 검토를 유지하며 이번에는 새로운 선행연구 주장을 추가하지 않는다. 신규 기여와 독립 일반화는 여전히 미검증이다.

이번 단계에서는 읽기만 수행했고 파일 수정·생성, 모델 로딩, GPU 실험은 하지 않았다.
