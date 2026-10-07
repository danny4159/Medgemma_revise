# 요약

- **판정:** execution_failed. 자료·기술 검사는 실행됐지만 가설 검증 실험은 미실행이다.
- **핵심 근거:** 초기 GPU 검사 14/19 통과, 본학습 update 0, 신규 판독 생성 0. 현재 소견을 제거하는 temporal 필터 결함이 확인됐다.
- **의미·한계:** 동일 shape 비간섭과 결정적 λ=0 대조는 통과했다. 위치 학습의 판독 효과나 내부 원인은 판단할 수 없다.
- **다음:** 같은 R/G 비교의 자료 규칙·수치 검증을 한정 보완하고 원 계획의 조건부 학습으로 연결한다.

## 알림 요약

- 결과: 흉부 X-ray PadChest-GR D8 검사에서 현재 소견 누락과 입력 길이별 수치 불일치를 확인해 본학습 전에 중단했다.
- 의미: 잘못된 target으로 학습하는 것을 막았지만 위치 supervision이 판독을 개선하는지는 아직 모른다.
- 후속: 같은 비교의 자료·기술 경로를 보완한 뒤 계획된 실제 학습과 판독 평가로 진행할 것을 권고한다.

# Assessment

실제 구현 담당은 engineer_backend.json과 claude_meta.json에서 Codex, gpt-6-astra/medium으로 확인했다. 보고서의 SELF_CHECK: FAIL과 실행 로그·결과 파일이 일치한다. 원 계획의 기술 gate를 통과하지 않은 상태에서 본학습을 중단한 조치는 타당하다. valid_experiment=false이며 모델 가설 기각으로 해석하지 않는다.

리뷰 대상은 ee00917e09032fddb27118b8f7404a2d0f76d734다. commit.json의 14개 경로는 현재 파일과 모두 일치하고 unpreserved_paths는 없다. changes.patch의 반입 학습 파일과 신규 report89 소스를 확인했다. execution_status에 연결된 산출물 hash 불일치는 0이었다. amendment는 확인되지 않았다.

# Key Findings

1. selection을 독립 집계해 T512/V64/E128=512/64/128명과 세 집단 간 환자 교집합 0을 확인했다. T512는 abnormal_box 303명, abnormal_no_box 27명, no_abnormal_annotation 182명이다. 이는 임상 정상 분류가 아니다. 전체 pixel 중복 검사는 미완료다.
2. temporal_audit의 개별 제외 기록을 다시 집계하면 T/V 제외 문장은 146/17개다. progression이 없고 changes 계열에 걸린 문장은 78/10개다. 88개 전부가 오제외라는 뜻은 아니다. 퇴행성 척추 변화 등 직접 제시된 현재 상태 문구의 오제외는 코드의 chang 계열 정규식과 일치한다.
3. tech/a1/result.json의 19개 검사 중 14개 통과를 재집계했다. 공식 forward와 별도 CE의 차이 3.5763e-07도 저장 성분으로 재계산했다. 실패는 길이 변경 report 대조 3개, 초기 λ=0 gradient 반복 대조, 길이 변경 gradient 대조다.
4. numeric_control과 실제 도구 로그에서 결정적 동일 shape λ=0 loss·gradient 차이 0 및 adapter·optimizer·RNG 일치를 확인했다. 같은 길이 미래 attention 차단에서도 hidden/logits/NLL 차이는 0이다. 반면 짧은 입력과의 logits 차이 0.75, NLL 차이 0.04595는 남는다.
5. 기술 optimizer step은 2회지만 본학습 update·신규 판독 생성은 각각 0이다. E 영상 추출·reference 작성·평가도 미실행이다. 종료 로그의 GPU 점유는 0번 87 MiB, 1번 15 MiB로 기술 작업 종료와 일치한다.

# Problems / Concerns

현재 소견 필터 오류는 target 의미를 바꾸므로 학습 진입 blocker다. 원래 abnormal 플래그를 보존했다고 target 누락이 해결되지는 않는다. 규칙 수정 뒤 잔여 문맥 의존 표현과 층·적격성 변화까지 점검해야 한다.

동일 shape 결과는 미래 token 누수 설명을 약화하지만 모든 입력의 비간섭이나 일반 report-only 경로와의 동등성을 증명하지 않는다. 길이 차이를 곧바로 causal attention 결함으로 단정할 수도 없다. 원 문턱을 사후 완화해 최초 실패를 통과로 바꾸지 않은 점은 적절하다.

reuse_manifest의 blob/import 검사는 전체 학습 재사용 승인이 아니다. 중간·epoch 재개, validation 상태 보존, 실제 생성 및 처리량 검사가 남는다. audit 코드의 고정 시각 관찰 문구도 새로운 manifest의 자동 판정으로 사용하면 안 된다.

GPU1 한 장에서 순차 기술 대조를 수행한 것은 현재 중단 범위에서 타당하다. 본학습 전에 batch 확대 비교와 두 GPU의 독립 trajectory 배정이 필요하다. 측정 peak reserved 14.19 GiB는 worker당 2 GiB 여유를 포함하면 GPU당 training worker 두 개를 지원하지 않는다. 고정 16000 MiB 시작 문턱도 충분한 여유를 일반적으로 보장하지 않는다.

# Interpretation

이번 결과는 학습 전 데이터·실행 결함 발견이다. 위치 학습의 누락 감소, 언급 성향, report-only 적응의 충분성 중 어느 설명도 실제 판독 결과로 구분하지 못했다. 기존 iter_088의 CURE 회복 신호와 C-H 충돌 관찰, iter_012의 grounding 개선은 그대로 유지한다. 새 모델 한계 주장을 추가하거나 기존 limitation을 승격할 근거는 없다.

이번에는 유효한 성능·진단 개선이 없어 논문 추천을 보류한다. 기술 검사 통과 일부를 연구 마일스톤으로 기록하지 않는다.

# Strategy Check / 연구 방향 판단

**관찰 계승:** iter_088의 시스템 비교에는 자료·학습 목적 혼입이 남았고, iter_089는 동일 base·판독 supervision의 R/G 대조를 선택했다. 이번 중단으로 그 선택의 과학적 가치는 반박되지 않았다.

**줄인 설명:** 검사한 입력에서 동일 길이 미래 token 내용과 attention은 첫 판독 출력을 바꾸지 않았다. 결정적 backend에서는 동일 shape gradient 불일치가 사라졌다. 다만 길이별 차이의 원인은 아직 확정하지 못했다.

**실행 / 성능 / 가설 / 기여:** 기술 준비 일부만 유효하다. 성능 비교는 없고 가설은 미판정이며 신규 기여 근거도 없다. 인식·선택·결합의 내부 설명과 타 모델 일반화는 검증하지 않았다.

**다음 투자:** 한정 보완을 선택한다. 현재 지배 작업은 자료 준비와 기술 재작업이며 실제 학습·의미 평가는 시작되지 않았다. 명시적인 target 오류와 수치 대조를 해결하면 원래 비교를 실행할 수 있으므로 후보 교체보다 정보 가치가 높다. 완료점은 필수 gate 통과 후 원 계획의 조건부 학습·E128 평가다. 기술 검사만 반복하며 연구 진전으로 세지 않는다. C-H와 E192 확대 보류는 유지한다.

# Recommended Next Experiment

iter_089 원 계획과 SHA를 기준으로 유지할 가설·평가·확대 기준, 수정할 temporal 규칙, 미완료 실행 경로를 구분한 보완 계획을 작성한다. 기존 selection과 실패 원자료는 보존하고 수정 결과는 새 경로에 둔다.

길이별 차이는 정밀도·연산 shape·attention 및 head 계산 경로를 좁혀 원인을 확인한다. 동일 shape의 독립 CE·gradient/update 대조를 유지하고 기존 짧은 입력 대조의 미달도 해결하거나 변경 근거를 사전 amendment로 명시한다. E 결과를 이용한 문턱 조정은 하지 않는다.

필수 재개·validation·누수·생성 검사를 통과하면 epoch2 실제 판독 탐색으로 진행하고 원 조건에 따라 epoch6/12와 E128 평가를 수행한다. 새로운 과제·모델 탐색이나 과거 E96 재평가는 이 복구의 기본 후속이 아니다.