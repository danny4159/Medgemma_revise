# 요약

- **판정:** execution_failed, CONTINUE. C201 본진단은 미실행이며 부분 누락 가설은 미판정이다.
- **핵심 근거:** D24의 2·4 worker 각 48건은 token과 비교한 score가 일치했다. 재개 검사는 28/48건에서 중단됐다.
- **의미·한계:** 생성 경로의 동작은 확인했지만 위험 분별력·누락 회복·검출 개선은 아직 평가하지 못했다.
- **다음:** 실행 수명·평가·provenance 검증을 보완하고 C201 및 사전 조건부 E402를 이어간다.

# Assessment

계획·구조화 계획·Claude 보고서·changes.patch·reuse_manifest와 리뷰 SHA `5bdcbe2f56b219de1e5319c8a890061ec672a774`의 코드를 검토했다. commit.json의 대상 파일은 현재 작업 폴더와 모두 일치했고 unpreserved_paths는 비어 있다. 다만 커밋 보존은 재사용 승인과 다르다.

Claude 보고서는 재개 검사가 백그라운드에서 진행 중이라는 문장으로 끝난다. 실제 stream 말미에는 해당 worker와 대기 task가 stopped/killed 처리된 기록이 있다. 저장된 재개 출력도 28건뿐이다. 따라서 보고서의 대기 상태를 현재 실행 중이라는 근거로 사용할 수 없다. 리뷰 환경의 process 조회만으로 실행 호스트의 모든 작업 종료를 확정하지도 않는다.

리뷰에서는 파일을 수정하거나 GPU 실험을 실행하지 않았다. 저장 결과 집계·hash 대조를 수행했으며 테스트 스크립트는 결과 파일을 쓰므로 재실행하지 않았다.

# Key Findings

1. **D24 생성·병렬 정합성은 확인됐다.** `D24/attempt_2w`와 `attempt_4w`는 각각 O24/F24, 고유 요청 48건이며 모든 worker 종료 코드는 0이다. O의 원래 suffix 재현 실패와 F의 저장 prefix/강제 token 실패는 모두 0이다. 두 구성 사이 suffix 불일치는 0이고 Q·평균 NLL·평균 entropy·EOS NLL·첫 token entropy의 최대 차이는 0이다.
2. **4 worker 처리량은 유망하다.** launcher wall-clock은 252.67초에서 146.24초로 줄었다. 같은 48요청 기준 약 11.40→19.69요청/분, 약 1.73배다. record의 최대 allocated peak는 두 구성 모두 약 8.340GiB/프로세스다. 이는 GPU 전체 점유·reserved 메모리·긴 출력 안전 여유 검증을 대신하지 않는다.
3. **재개 완료는 미확인이다.** `resume_test`에는 O14/F14의 28건, 초기 `attempt1`에는 O3/F3의 6건이 있다. 두 완결된 처리량 attempt와 합쳐 저장 record는 130건이지만 같은 D 환자의 반복 실행을 본진단 표본으로 세면 안 된다.
4. **source의 제한된 연결 검사는 통과했다.** C201/E402의 저장 엄격 사건 수는 20/27이다. 별도 사각형 교집합 계산으로 완전 비중첩 GT index를 대조했으며 불일치가 없었다. 603개 현재 영상의 file SHA도 manifest와 일치했다. 이번 리뷰에서 raw/padded pixel 및 공식 tensor 동등성까지 새로 검증한 것은 아니다.
5. **iter_029 판정 교정은 기존 결론을 유지한다.** `correction_029/decision.json`은 token_nll_eos를 포함하고 E의 97.5% paired CI를 사용한다. Presence−entropy AUROC 차이는 −0.007099, CI 하한 −0.030440이며 추가 이득 gate는 false다. 연결된 C/E report·independent_verify의 세 hash는 현재 파일과 일치한다. 원시 통계를 이번에 다시 bootstrap한 것은 아니다.
6. **테스트 28/28은 제한된 범위다.** 저장 fixture는 사건·좌표·강제 processor·교정 decision·일부 기존 record 검사를 다룬다. 공식 입력, 전체 재개 완료, 새 평가 통계와 단계 gate 검증을 포함하지 않는다.

# Problems / Concerns

## 현재 판정을 막는 문제

C201의 O/F 전체 실행·평가·decision이 없다. E402 미실행은 C gate가 아직 없기 때문이며 부적절한 축소로 단정하지 않는다. D24의 실제 공식 입력 tensor 대조, M0 sanity, 선택 score의 float64 대조 및 계획한 재개 검사의 완료 산출물도 없다. 따라서 이번 반복을 유효한 H1/H2 실험으로 세지 않는다.

## 본실험 전에 수정할 평가 문제

`risk30_eval.h1_report`는 C/E 구분 없이 2.5/97.5 percentile을 사용한다. E 주비교는 계획대로 1.25/98.75 percentile의 97.5% CI여야 한다. `capture_at_k`는 round를 사용해 C201에서 40명, E402에서 80명을 선택하지만 계획은 ceil 기준 41명과 81명이다. 단일 class bootstrap을 재표집하지 않아 NaN이 CI에 전파될 수 있다.

한 박스 층 Q−B*, 보조 사건·층별 분석과 전체 O/F의 F1 paired CI·FP/환자·추가 TP/FP가 빠져 있다. H2의 invalid는 회복 실패로 남지만 operational 검출 지표에서는 null을 어떻게 실패로 반영할지 완성되지 않았다. 성공 사례만으로 회복이나 실용 개선을 판단해서는 안 된다.

## 실행·재사용 문제

`validate_existing`은 adapter·split·pixel·중복만 검사한다. protocol/source/원래 suffix와 예상 요청 내용의 연결은 검사하지 않는다. protocol 인자는 선택 사항이며 잠금 목록도 필수 목록이 아니다. 현재 v3에는 source audit, 새 launcher·평가 진입점·decision 및 통계 의존 파일 일부가 빠져 있다. evaluator는 E의 B*를 문자열 인자로 받으며 잠긴 C 선택과의 연결을 강제하지 않는다. worker에는 D gate와 C→E gate가 없다.

F processor는 강제 전 prefix를 확인하지 않고 지정 index에서 token을 바꾼다. 사후 기록은 남지만 evaluator는 실행 무효 조건을 모두 거부하지 않는다. GPU 선택도 상속된 허용 집합을 검증하지 않는다. 이번 명령은 허용된 0/1을 사용했으므로 실제 범위 이탈을 관찰했다는 뜻은 아니다.

재개·동시 쓰기·손상 tail과 parent/child 종료 처리를 검증해야 한다. launcher는 기존 stdout/stderr 및 launch_result를 덮어쓸 수 있다. 모든 step의 vocabulary score와 cap attempt를 보관하는 구현은 scalar 중심이라는 계획과 다르며 긴 출력에서 메모리 비용이 커진다.

v3 protocol의 잠긴 파일은 현재 내용과 일치한다. v1/v2는 risk30.py가 달라졌으므로 기존 D 결과 재사용 전에 실행 당시 코드와 변경 범위를 연결해야 한다. 과거 protocol을 다시 잠그면 안 된다.

iter_029 correction은 세 report hash를 기록하지만 raw output·calibration·독립 검증 대상의 동일성을 충분히 강제하지 않는다. 또한 과거 fixture 경로가 실제 변경 목록에 포함되고 테스트 코드에도 직접 쓰기 경로가 남았다. 기존 연구 주수치의 훼손을 확인한 것은 아니지만 원본 보존 지시는 완전히 지켜지지 않았다.

# Interpretation

이번에 확인된 것은 구현과 실행 기반의 일부다. C/E는 기존 개발 자료이며 독립 확인이 아니다. source manifest와 audit을 나눈 구조는 GT를 생성 입력에서 분리하려는 설계에 부합하지만, 전체 provenance 검증 완료를 뜻하지 않는다.

D24에서 관찰한 개별 회복 사례는 C 확대 기준이나 H2 효과 크기를 대체할 수 없다. 부분 누락의 원인, 종료 신호의 추가 정보, 내부 시각 능력 또는 신규 방법의 필요성은 모두 미판정이다. 기존 limitation의 상태를 바꿀 근거가 없어 limitation_updates는 비워 둔다.

# Strategy Check / 연구 방향 판단

- **실행 유효성:** 동작·처리량 pilot은 실제 수행했지만 원 계획의 본 가설 검증은 미완료다.
- **성능 개선:** 새로운 위험 분별력이나 전체 검출 개선은 확인되지 않았다. iter_029 교정은 기존 단순 baseline 결론을 유지한다.
- **가설 지지:** O 재현과 F prefix 보존은 실험 조작의 타당성 근거이며 H1/H2 지지가 아니다.
- **신규 기여 가능성:** 아직 미확인이다. 단순 continuation·token baseline으로 충분한지를 확인한 뒤 방법 투자를 판단해야 한다.

iter_030 계획의 전략 비교를 유지한다. 현재는 추가 loss 개선이나 다른 질문 전환보다 이미 준비한 C201 진단을 완료하는 정보 이득이 크다. 실행 미완료만으로 부분 누락 질문을 버릴 근거는 없다. 반대로 D 사례만으로 새 학습·외부 확대를 예약할 근거도 없다. C/E에서 단순 baseline이 충분하거나 H1/H2가 음성이면 기존 계획대로 외부 확인 및 다른 GOAL 내 질문과 비교한다.

논문 추천은 보류한다. 이번 방향의 본실험이 미실행이고 D24 동작 확인만으로 후속 탐구의 유망성이 입증되지 않았다. 마일스톤도 부여하지 않는다.

# Recommended Next Experiment

실행 호스트의 소유 작업 상태를 확인하고 기존 기록을 보존하면서 재개한다. 필요한 평가·gate·provenance 수정과 실제 재개 검증만 우선 완료한다. 기존 D24 처리량 결과는 호환성 확인 후 재사용하며 긴 출력 안전 여유를 보완한다.

D gate 통과 후 C201을 수행한다. 원래 표본·prompt·score 방향·성공 기준을 유지하고, 사전 확대 조건을 충족할 때만 E402로 진행한다. 새 학습·reserve·MRI F139는 열지 않는다. 다음 보고서는 실행 단계, 완료 요청 수, 중단·재개 및 확대 여부를 명시하고 백그라운드 작업의 종료를 수집한 뒤 작성한다.