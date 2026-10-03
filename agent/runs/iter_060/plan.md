# 요약

- **이번에 할 일:** UCSF-PDGM-VQA의 enhancement 형태·FLAIR extension 질문을 영상과 연결하고, text-only·균등 sequence 배분·질문별 고정 배분을 비교한다.
- **필요한 이유:** 기존 구간 판정은 전문 모델로 충분했다. 이제 질문별 정보 선택이 실제 답변을 바꾸는지 확인한다.
- **확인할 기준:** 자료·입력 무결성, 영상의 text-only 대비 이득, 같은 영상 예산에서의 배분 효과와 실제 비용이다.
- **주의·다음:** 공개 QA 파일 연결은 미검증이다. 통과하면 같은 반복에서 실제 출력을 얻고, 결과에 따라 방법 검토·모델 비교·투자 보류를 선택한다.

# Current Understanding

iter_059의 원 판정과 전문 대안 채택을 유지한다. MSD 개발 E48에서 U8/HD BA는 0.768639/0.950457이고 D6 전체 비용 비율은 0.600989였다. 현재 구간 판정의 VLM 적응·timing 반복은 종료한다. 네 sequence 전체 volume 대 FLAIR 구간 입력의 차이는 남지만 이를 분리하는 것만으로 후속 투자 가치는 생기지 않는다.

이번 대상은 공개 보고서에서 만든 brain MRI 소견 QA다. enhancement 형태와 FLAIR extension의 구체적 예시는 [UCSF-PDGM-VQA Appendix E](https://arxiv.org/html/2605.17140v1)에 있다. 공개 annotation archive·study ID·정답 순열의 실제 연결은 아직 확인하지 못했다. 논문 예시를 별도 GT로 옮겨 실험하지 않는다.

유지: 최종 GOAL, MRI 우선 전략, 기존 결과·checkpoint·reserve. 변경: 단순 구간 존재 판정에서 질문별 소견 QA로 이동. 보류: MSD 추가 적응, OCT/MARIO, 이번 자료의 학습과 독립 확증.

# Strategy Check / 연구 방향 판단

- **중요한 능력:** 제한된 영상 예산에서 질문에 필요한 MRI 근거를 선택해 답변하는 능력이다.
- **관찰:** 기존 과제는 전문 segmentation+규칙으로 정확도·비용 기준을 충족했다. 현재 QA에서 VLM의 기본 영상 신호와 routing 효과는 미관찰이다.
- **남은 설명:** 입력 배분 문제, 기본 판독 능력 부족, 질문·선택지 prior, 보고서 기반 정답 모호성이다.
- **최소 비교:** 같은 QA와 영상 수에서 U와 R을 비교하고 T 및 선택지 순서 대조를 둔다.
- **결정 변화:** R의 이득은 단순 routing 채택 근거이며 새 방법의 증명이 아니다. 영상 신호가 없으면 같은 과제의 모델 적합성을 먼저 검토한다. 단순 대안이 충분하면 routing 방법 투자를 종료한다.

기존 MSD 개선은 준비 비용이 낮지만 질문의 추가 가치가 작다. UCSF QA는 자료 연결 비용이 있으나 모델·입력 선택을 직접 구분한다. OmniBrainBench는 다중 영상 loader가 있으나 현재 확인한 schema만으로 study별 sequence 연결을 보장하지 않는다. longitudinal MRI는 추가 자료 준비가 필요해 후순위다.

같은 mri-volume-evidence-use track에서 iter_056~059를 연결한다. iter_059의 지배적인 재작업은 계측·검증 보완이었다. 이번에는 자료 성립 여부를 먼저 확인하고 사용할 경로만 검증한다. 범용 실행기 정비를 별도 연구 반복으로 만들지 않는다.

# Hypothesis

같은 총 slice 수에서 질문 관련 두 sequence에 더 많은 관측을 배분하는 R이 네 sequence 균등 배분 U보다 정확할 수 있다. 효과가 있더라도 sequence 제거·관측 밀도·context 변화의 결합 효과다. 이를 순수한 내부 통합 기전으로 해석하지 않는다.

T와 비슷한 정확도는 영상 신호 부족의 후보 근거지만 영상 무사용의 증명은 아니다. 쉬운 질문, ceiling, 정답 모호성도 함께 확인한다.

# Limitation Evidence / Correct Usage Checks

이번 과제에 연결할 observed/validated limitation은 아직 없으므로 limitation_ids는 비운다. SPIDER reference 좌표 관찰이나 RSNA grounding 한계를 전용하지 않는다. experiment_role=diagnostic, method_stage=none이다.

MedGemma 1.5 revision 91850547d9f0b2fdd21aa7c5f4f3d1a8a52c243b, bf16, 공식 processor/chat template, greedy decoding을 사용한다. sequence별 volume min-max와 동일 RGB 채널, axial inferior→superior 순서를 적용한다. affine에서 orientation을 계산하며 MSD의 channel 0·native RAS 가정을 옮기지 않는다. sequence 이름과 slice 순서를 입력에 명시한다.

공식 volume 경로와 이번 wrapper의 실제 tensor를 D에서 대조한다. 파일 누락 시 text-only로 묵시 전환하지 않는다. 모델의 오답은 기술 검사 실패가 아니다. 100% oracle 정답 gate를 두지 않는다.

# Contribution Path / Baselines / Reuse

가장 가까운 비교는 UCSF-PDGM-VQA의 기존 영상/text 평가와 단순 다중 sequence 입력이다. 이번 기여는 미확정이며, 새 방법 이전에 저비용 고정 routing이 얼마나 해결하는지 확인한다.

- T: 영상 없이 동일 질문·선택지를 제공한다.
- U: T1, T1ce, T2, FLAIR에 총 영상 예산을 균등 배분한다.
- R: enhancement 형태는 T1/T1ce, FLAIR extension은 T2/FLAIR에 절반씩 배분한다. routing은 질문 유형만 사용한다.
- prior: 선택지 위치 빈도와 D에서 정한 유형별 다수 답변 문자열을 보고한다. D에 없는 문자열은 사전 고정한 위치 fallback을 사용하고 적용 수를 표시한다. E 정답으로 prior를 맞추지 않는다.

HD-GLIO+OR는 형태 및 특정 해부구조로의 extension을 직접 답하지 않는다. 따라서 현재 결과를 해당 QA의 강한 전문 baseline 성능으로 대입하지 않는다. 반대로 전문 모델로 불가능한 과제라고 주장하지 않는다. mask의 단순 존재·부피 계산으로 정답이 결정되는 문항은 이번 대상에서 제외한다. 후속 방법 투자에는 직접 SFT와 적절한 전문 encoder/segmentation+질문별 head의 정확도·학습자료·비용 비교가 필요하다.

재사용 출처는 iter_059 SHA 463d215b4d5a92a17dec80f2be29daefab44cc3e의 msd56_run.py다. 현재 파일 존재와 실제 함수·의존성을 확인했다. 새 branch의 자동 기반 차이에 대비해 해당 파일만 reuse_assets로 지정한다. load_model, env_info, build_inputs, generate만 호출하거나 최소 adapter로 연결한다. 새 MC parser·자료 loader가 필요한 이유는 기존 코드가 MSD FLAIR 이진 질문에 고정돼 있기 때문이다. 기존 전체 runner를 승인된 것으로 복사하지 않는다.

# Proposed Experiment

## 1. 한정 자료 적합성 확인

먼저 논문이 연결한 QA 배포와 공식 TCIA metadata·영상 배포 목록을 확보한다. URL, revision/수집일, 이용 조건, 크기와 digest를 기록한다. 실제 QA 파일에 study ID, 질문, 선택지 네 개, 유일한 answer 연결이 있는지 확인한다. answer가 문자열이면 순열 전후 동일 문자열로 검증한다. 공개 shuffled 버전과 원본을 혼합하지 않는다.

[TCIA 변경 이력](https://www.cancerimagingarchive.net/collection/ucsf-pdgm/)의 여섯 follow-up alias를 포함해 환자 ID를 정규화한다. 같은 환자의 반복 study는 가장 이른 study 하나만 사용한다. 이를 판별할 수 없는 alias는 격리한다. 전체 501 study를 501 독립 환자로 간주하지 않는다.

질문 유형은 다음 두 개만 허용한다.

1. 병변의 enhancement 형태를 직접 묻는 문항. enhancement를 질문에 이미 설명하고 크기만 묻는 문항은 제외한다.
2. T2/FLAIR 이상 신호가 어느 해부구조로 연장되는지 묻는 문항.

시간 변화, 유전자·병리 등 영상만으로 보장할 수 없는 정답, 임상 이력 필요 문항, 질문에 답이 명시된 문항, 주관적 정도 표현만으로 갈리는 문항, 정답 연결이 모호한 문항을 제외한다. 원문과 제외 사유를 보존하며 질문·정답을 새로 생성하지 않는다. 유형 분류는 question/options로 먼저 잠그고 answer는 연결 검증에만 사용한다. 공개 reasoning/report는 정답 근거 점검용이며 모델·routing 입력에서 차단한다.

최초 D6에서 네 sequence의 실제 파일, shape/affine, 조영 전후 구분과 QA 연결을 확인한다. 각 유형 3명의 다양한 입력을 우선하되 해당 수가 없으면 가용한 모든 적격 사례를 쓴다. 실제 렌더를 표시해 orientation·영상 품질·sequence 연결을 확인한다. 이 점검은 전문의 재판독 인증이 아니다. 남은 임상 정답 불확실성은 별도로 기록한다.

annotation·ID 연결이 확보되기 전에 영상 전체를 다운로드하지 않는다. 적격 목록 확정 후 선택 환자의 네 sequence만 받는다. 배포 단위상 전체 archive가 불가피하면 크기·여유 디스크·선택 다운로드 불가 이유를 먼저 기록한다. 별도 접근 승인이 실제 필요하면 그 자산만 중단한다. 이번 반복에서 Omni나 다른 자료로 자동 대체하지 않는다.

## 2. 동작 확인과 입력 예산 고정

D6는 개발 자료다. E 성능을 보기 전에 preprocessing·parser·입력 예산을 잠근다.

총 B=80장을 우선 사용한다. 이는 네 sequence에 균등 분할하면서 공식 연구의 최대 85장 조건에 가까운 예산이다. U는 sequence당 20장, R은 선택 sequence당 40장이다. 각 sequence의 전체 axial 범위에서 등간격 표집하고 GT·segmentation을 사용하지 않는다. 80장 요청이 현재 24GB에서 안전하게 실행되지 않으면 D에서만 B=32로 낮춘다. U는 8장씩, R은 16장씩이다. 변경 이유와 입력 손실 가능성을 기록한다. B=32도 안전하지 않으면 기술 blocker로 종료하며 임의 montage로 바꾸지 않는다. 짧은 volume으로 중복 slice가 필요한 경우 양 조건의 실제 고유 slice 수를 기록한다.

각 QA의 선택지는 ID 기반 고정 permutation과 그 역순 두 가지다. answer 위치를 이용해 순서를 고르지 않는다. 모든 조건에 같은 두 순서를 적용하고 원본 answer 문자열로 역매핑한다.

고정 prompt는 sequence/순서 설명, 원문 질문과 선택지, 마지막 단독 줄에 ANSWER: A|B|C|D를 쓰라는 지시로 구성한다. parser는 마지막 비공백 줄의 이 형식만 허용한다. cap 512에서 시작하고 EOS 없이 끝난 요청만 동일 입력으로 2048까지 한 번 재시도한다. 두 attempt와 비용을 모두 보존한다. invalid는 오답 처리하며 비율을 별도 보고한다. D 이후 prompt/parser를 바꾸지 않는다.

필수 기술 검사는 GT 연결, 순열 역매핑, affine/orientation, 공식 processor와 tensor 일치, T의 영상 token 부재, U/R의 영상 수·순서, 실제 요청 ID·출력 provenance다. 정답률을 기술 진입 조건으로 사용하지 않는다.

## 3. 가능성 탐색 E24

D와 환자 단위로 분리한 적격 집단에서 SHA256(seed60, canonical_patient_id) 순서를 만든다. 질문 유형이 두 가지면 유형별 환자 후보를 번갈아 추가해 E 목록을 구성한다. 환자당 유형별 질문 한 개를 QA ID hash 순서로 고른다. 부족한 유형을 임의의 다른 질문으로 채우지 않는다.

E24 및 조건부 누적 E64의 목록을 출력 전에 함께 잠근다. 각 환자 최대 2문항, 문항당 T/U/R×두 순서다. E24는 최대 288요청이다. 두 유형이 모두 존재하면 유형별 결과를 반드시 보고한다. 하나만 존재하면 그 유형의 모델 적합성·배분 비교로 범위를 줄이며 질문 유형 간 선택 능력을 주장하지 않는다. 적격 환자가 24명 미만이어도 실제 출력을 얻고 탐색으로 보고한다.

## 4. 조건부 규모 확대

기술적으로 유효한 E24를 완료한 뒤 U−T, R−T, R−U의 점추정치와 환자 cluster bootstrap 95% CI를 계산한다. 다음 중 하나면 미리 잠근 E64까지 한 번 확대한다.

- U−T 또는 R−T가 0.10 이상이다.
- R−U가 0.05 이상이고 R−T가 양수다.
- 위 조건은 미달하지만 U−T 또는 R−T의 CI 상한이 0.10 이상이며, 영상과 T의 정오가 다른 환자가 6명 이상 있어 추가 표본이 영상 신호 판단을 바꿀 수 있다.

마지막 분기는 유망성 판정이 아니라 정밀도 보완이다. 이 조건이 없으면 현재 MedGemma의 routing 확대를 중단한다. 자료 오류·모호성이 주된 원인인 경우 표본 확대 대신 영향을 명시한다. 표본이 부족하면 잠근 가용 집단까지만 수행한다.

E64는 기본 신호와 약 10 pp 수준의 큰 차이를 탐색할 규모다. 독립 Bernoulli 정확도의 최악 조건에서도 95% 반폭은 약12 pp이므로 작은 차이 확증에는 부족하다. 실제 paired 분산·환자 내 의존성을 보고한다. CI 폭을 좁히기 위해 E64 이후 추가 환자·seed를 자동 투입하지 않는다.

## 5. 독립 확인

이번 반복에서는 하지 않는다. D/E는 모두 개발 자료다. 선택되지 않은 환자의 답변을 생성하거나 기존 다른 실험의 reserve를 소비하지 않는다. 향후 학습·모델 선택을 마친 뒤 별도 환자·외부 자료에서 확인해야 한다.

## 자원·시간·재개

학습은 없다. 최대 D 72요청, E 768요청이며 기술·처리량 반복과 cap 재시도는 별도 집계한다. 원시 요청량은 실제 적격 환자/QA 수로 다시 계산해 실행 전 기록한다.

실행 직전 nvidia-smi로 허용 GPU 0/1의 UUID·여유 메모리를 확인하고 여유가 큰 GPU부터 배정한다. 기존 U8 peak 9312 MiB는 80장 입력의 예측치로 쓰지 않는다. B의 긴 입력과 2048 token cap에서 실제 peak를 측정하고 worker당 최소 2GB 여유를 확보한다.

두 GPU 각 1 worker로 독립 shard를 처리한다. D의 같은 요청으로 batch 확대 또는 GPU당 2 worker 중 메모리가 허용하는 유망 구성 하나를 추가 비교한다. 전체 요청/분, GPU별 실제 peak, 긴 출력 지연, OOM·CPU/I/O 경합과 출력 정합성을 확인한다. 추가 동시성이 안전하지 않으면 측정 수치로 이유를 남긴다. 성능에 따라 배치를 선택하지 않는다.

예상 wall-clock은 자료 전송량/실측 전송률 + 초기 loading + 조건별 요청량/실측 전체 처리량 + 검증 시간으로 산출한다. 80장 입력의 실측이 없으므로 현재 숫자 시간을 만들지 않는다. D 후 E 진입 전에 추정 범위와 실제 메모리·병렬 배치를 보고서에 기록한다. 임의 device-minute 상한은 두지 않는다.

요청 ID에는 환자·QA·입력 조건·선택지 순열·영상 순서·모델/config digest를 포함한다. worker별 파일과 원자적 완료 기록을 사용한다. source/입력/protocol hash가 다른 완료 결과를 재사용하지 않는다. attempt별 실패·원시 출력·진행량을 보존하고 중단 후 미완료 요청만 재개한다.

# Implementation Tasks for Claude

1. 결과 경로 research/results/iter_060을 사용하고 자료 연결 검사부터 수행한다. 기존 결과를 덮어쓰지 않는다.
2. 공식 QA·TCIA metadata·선택 영상의 출처 및 이용 조건을 기록한다. study→환자 alias, answer 연결, 적격·제외 목록과 D/E manifest를 만든다.
3. 필요한 source만 선별 재사용하고 새 자료 loader·MC adapter·평가기를 구현한다. 기존 MSD 전용 parser/ID/launcher를 무검증 호출하지 않는다.
4. 변경 경로의 필수 fixture를 실제 실행 경로에 연결한다. 질문/정답 순열 오류, source/request/protocol 변조, 누락 영상, 중복 환자·출력, 기술 gate 실패가 nonzero로 끝나는지 확인한다.
5. D에서 실제 이미지 표시·tensor 대조·모델 출력·메모리·처리량·중단 재개를 확인하고 설정을 잠근다. 그 후 E24 및 조건부 E64를 수행한다.
6. 고정 MC parser와 독립 집계 경로로 원시 응답에서 점수·CI·누락/중복을 재계산한다. 원시 문자열과 token, 조건별 비용을 보존한다.
7. 보고서에 준비 완료/실제 모델 관찰/확대 여부/독립 확인 미실행을 구분한다. 자료 확보가 막히면 실제 오류·시도·남은 blocker를 남기고 미실행을 성공으로 표시하지 않는다.

# Evaluation (성공/실패 기준 포함)

주지표는 환자별 QA·두 순서 정확도를 평균한 뒤 환자 간 평균한 accuracy다. 전체 QA micro accuracy, 유형별 accuracy, 두 순서 모두 맞힌 비율, 순서 간 답변 불일치, invalid/EOS 비율을 함께 보고한다. T/U/R의 차이는 동일 환자에서 계산하고 10,000회 patient-cluster bootstrap, seed60의 95% CI를 제시한다. 개발 탐색의 CI이며 독립 확증으로 부르지 않는다.

- **영상 기본 신호 양성:** U−T 또는 R−T가 0.10 이상이고 해당 CI 하한이 0보다 크다. 둘 중 유리한 것만 숨기지 않고 두 비교를 모두 보고하며 다중 비교의 탐색 성격을 유지한다.
- **routing 양성:** R−U가 0.05 이상, CI 하한이 0보다 크고 두 선택지 순서에서 방향이 같다. 이는 같은 영상 예산에서 단순 규칙의 의미 있는 이득이다. 5 pp는 후속 선택 방법이 넘어야 할 실용 차이의 탐색 기준이며 확증 문턱으로 일반화하지 않는다.
- **비용:** 원본 읽기→렌더/전처리→생성→답변 저장의 monotonic wall과 GPU 사용 시간을 조건별로 보고한다. loading은 분리한다. R의 비용이 U보다 증가하면 정확도·비용 trade-off로 보고하고 저비용 개선이라고 부르지 않는다. 별도 timing 캠페인은 만들지 않는다.
- **양성 결과의 다음:** routing baseline을 보존한다. 중요한 잔여 문제와 강한 대안의 부족함이 구체적일 때만 다음 리뷰에서 method pilot을 검토한다. 관찰만으로 학습을 자동 승인하지 않는다.
- **음성 결과의 다음:** 영상 기본 신호가 부족하면 MedGemma 전용 sequence 방법 개발을 보류하고 같은 과제의 다른 적절한 모델 비교를 우선 검토한다. U/R이 모두 높고 R의 추가 이득이 없으면 현재 routing 방법 투자를 종료한다. 하나의 모델·자료 결과를 MRI 전체에 일반화하지 않는다.
- **불확정 결과의 다음:** 사전 확대를 마친 뒤에도 방향이 불분명하면 이 후보 투자를 보류한다. 특히 정답 모호성·한 유형 부족·순서 효과가 결론을 지배하면 그 범위를 명시한다. 새로운 prompt·표본·seed를 붙이지 않는다.

자료/ID/tensor/GT 연결 오류는 execution_failed 범위다. 올바른 입력에서의 오답·형식 오류는 내용 관찰로 포함한다. 정답을 바꿔 점수를 회복하지 않는다. 결과를 본 뒤 발견한 annotation 문제는 원점수를 보존하고 사유가 고정된 별도 민감도 분석으로만 제시한다.

# Risks / Checks

- 보고서 유래 QA는 모든 항목이 독립 임상 gold인 것은 아니다. 모델 오류와 정답 불확실성을 구분한다.
- TCIA 영상의 공개 조건과 QA 배포 조건은 별개다. 확인되지 않은 권한을 가정하거나 접근을 우회하지 않는다.
- 환자 alias·중복 영상·학습 노출을 확인 가능한 범위에서 기록한다. 사전학습 비노출을 보장하지 않는다.
- U/R은 동일 영상 수지만 포함 sequence와 slice 밀도가 함께 달라진다. 순수한 sequence 통합 기전의 증명은 아니다.
- 질문별 rule은 정답·보고서·mask를 보지 않는다. 정상 소견이 드문 종양 집단을 일반 정상/비정상 평가로 해석하지 않는다.
- 새 branch 반입 충돌·누락은 실행 전에 해결한다. 보관된 소스를 새 구현으로 대체하지 않는다.
- 라이브러리 추가가 필요하면 격리 환경을 만들고 Python 경로·패키지 버전·출처·작은 실제 입력 검사를 남긴다. hf_cache와 기본 환경은 수정하지 않는다.

## 대규모 GPU 필요 후보

다중 sequence 3D encoder와 언어 모델의 공동 사전학습은 장기 후보로 보존한다. 큰 자료·연산이 필요하며 이번 계획으로 필요성이나 신규성이 입증되지 않는다. 현재 두 GPU에서는 고정 입력 대조와 이후 근거가 생긴 경량 적응을 우선한다.

# 계획의 근거 (GPT 조사 노트)

## 이번 라운드의 결정

UCSF-PDGM-VQA를 우선 선택한다. 공개 archive의 실제 annotation은 아직 열지 못했으므로, 한정 자료 점검과 통과 시 실제 GPU 출력 탐색을 같은 계획으로 묶는다. archive 미확인을 자료 부재로 판단하지 않는다.

## 직전 질문에 대한 답

1. **UCSF-PDGM-VQA 연결:** 논문 Appendix E에 enhancement 형태와 FLAIR extension 질문이 실제로 있다. Appendix B/D의 생성 schema는 question/answer/reasoning 등을 설명하지만 배포 파일의 study ID 연결까지 입증하지는 않는다. 논문 연결 Kaggle과 익명 코드 페이지는 이번에도 web 도구에서 Internal Error였다. 따라서 shuffled answer의 실제 연결과 영상 파일 대응은 구현 단계의 선행 검사로 남긴다. [논문과 배포 링크](https://arxiv.org/html/2605.17140v1)
2. **OmniBrainBench:** 공식 loader는 closed-ended-qa_6823.json을 읽으며 image_path의 문자열·목록을 모두 지원한다. 다중 영상 지원 자체는 확인했지만 동일 환자의 sequence 대응을 보장하는 경로는 확인하지 못했다. 파일 로드 실패 시 일부 영상을 건너뛰거나 text-only로 진행하는 코드도 있어 그대로 실행할 수 없다. HF viewer의 공개 예시에는 sequence 식별 질문이 있다. 현재 질문에 더 직접적인 UCSF 자료를 우선하며 Omni 전체를 부적합으로 기각하지 않는다. [공식 loader](https://raw.githubusercontent.com/CUHK-AIM-Group/OmniBrainBench/master/utils/OmniBrainBench/OmniBrainBench.py), [배포 viewer](https://huggingface.co/datasets/FrankPN/OmniBrainBench)
3. **단순 대안:** enhancement는 T1/T1ce, FLAIR extension은 T2/FLAIR에 영상 예산을 배분하는 고정 규칙을 직접 비교한다. 이는 새 방법이 아니라 후속 방법이 넘어야 할 baseline이다. 구간 OR만으로 답을 계산할 수 없는 소견 질문에 한정한다. 전문 anatomy segmentation 등 더 풍부한 모듈형 대안의 충분성은 미검증이다.

## 새로 확인한 자료 위험

TCIA 공식 검색 결과는 UCSF-PDGM의 501 study가 495명에 해당하며 여섯 ID가 추적 촬영으로 재명명됐음을 명시한다. 이전 논문 수준의 study 수를 독립 환자 수로 사용하지 않는다. 영상 배포는 CC BY 4.0으로 표시되지만 QA 배포 조건은 따로 확인해야 한다. 논문의 DUA 설명과 현재 배포 안내가 다르므로 실제 endpoint의 조건을 따른다. [TCIA 공식 자료 및 변경 이력](https://www.cancerimagingarchive.net/collection/ucsf-pdgm/)

## 기존 근거와 코드

round_01.json 원문, iter_059 review.md 및 iter_056/059 review.json의 code_assets, GOAL, LIMITATIONS의 MRI 항목, CODE_ASSETS 관련 구간을 확인했다. research HEAD는 463d215b4d5a92a17dec80f2be29daefab44cc3e이고 작업 트리는 깨끗하다. msd56_run.py의 실제 함수와 의존성을 확인했다. 모델 로딩과 생성 함수만 제한 재사용하며 새 자료의 preprocessing·정답 연결은 별도 검증한다.

## 의미와 한계

이번 계획은 기본 능력과 단순 입력 배분의 진단이다. 신규 contribution·임상 정확도·내부 통합 결함을 미리 주장하지 않는다. 실험·파일 생성·코드 수정은 이번 계획 단계에서 수행하지 않았다. 문헌은 조사 근거이며 추천 등록 대상이 아니다.

이전 사고 라운드 노트: agent/runs/iter_060/think/
