# 요약

- **이번에 할 일:** SPIDER의 임상의 Modic 등급에서 T1/T2 공동 입력을 단일 입력·고정 late fusion과 비교한다.
- **필요한 이유:** MSD의 mask 기반 답변에서는 영상 충분성과 기본 인식이 얽혔다. 이번에는 실제 임상 등급에 대한 추가 예측 가치로 질문을 좁힌다.
- **확인할 기준:** 기본 영상 신호, 공동 입력의 추가 이득, 복제 대조와 단순 결합의 설명력을 순서대로 확인한다.
- **주의·다음:** 사례별 관측 필요성과 희귀 유형의 결합 능력은 판정하지 않는다. 단순 대안이 충분하거나 기본 신호가 없으면 이 경로를 종료한다. 학습과 F139 사용은 이번 범위에 없다.

# Current Understanding

iter_059에서는 현재 MSD 과제의 전문 모델+규칙이 강한 대안이었다. iter_064의 MedGemma context 손실은 유효하지만 Qwen에서 같은 손실은 없었고, 기본 인식을 통제한 선택 실패는 미확정이다. iter_065의 질문별 정책은 위치 prior 이후의 가치를 확보하지 못했다. iter_066은 scoring으로 공동 생성의 극단적인 저하를 완화했지만 E12의 위치 prior를 넘지 못했다.

이번 계획은 이 종료 판단을 유지한다. MSD E48의 추가 prompt·문자열·학습을 수행하지 않는다. iter_055의 MRI 우선 보완은 이미 적용된 운영 기준이며 OCT 계획을 다시 다루지 않는다.

SPIDER는 전문의의 IVD별 Modic 0/I/II/III 등급을 제공한다. 그러나 각 sequence의 신호 주석과 사례별 충분성 주석은 없다. 기존 D/E의 paired T1/T2는 D 7명·51 IVD, E 43명·298 IVD다. E의 I·III는 각각 한 행뿐이다. 따라서 주분석은 사전에 빈도가 확인된 0/II 행의 구분이며, I/III 출력은 별도로 모두 보존·보고한다. 이는 결과를 보고 정한 제외가 아니다.

# Strategy Check / 연구 방향 판단

- **상위 질문:** 여러 관측의 정보를 함께 처리하는 것이 실제 답변에 추가 가치를 주는가?
- **관찰:** 기존 MRI 출력에는 context 손실과 인터페이스 효과가 있으나, 인식·선택·결합을 분리하지 못했다.
- **이번에 해결하지 않을 질문:** SPIDER 등급만으로 단일 관측이 충분한 환자와 복수가 필수인 환자를 구분할 수 없다. 그 경로는 현재 자료에서 종료한다.
- **남은 경쟁 설명:** 두 sequence의 추가 정보, 영상 수 증가, 답변 prior, 단일 sequence만으로 충분한 과제, 단순 late fusion의 충분성이다.
- **최소 비교:** T1/T2 단독 대 J, 동일 영상 복제 R, 고정 LF, text-only·위치 prior를 비교한다.
- **바뀔 결정 하나:** 이 임상 등급 조건에 공동 처리 연구를 더 투자할 근거가 있는가, 아니면 단순 baseline을 보존하고 종료할 것인가?

현재 방법 개선과 기본 인식 적응은 전문 대안 이후의 잔여 가치가 없어 우선순위가 낮다. 새로운 자료 탐색보다 이미 확보된 임상 등급의 한정 출력 비교를 선택한다. 일반적인 결합 실패를 주장하는 데 필요한 주석을 확보했다고 간주하지 않는다.

타 계열 비교는 같은 고정 사례에 기존 Qwen 하나를 포함한다. 기존 MSD 모델 차이를 SPIDER에 자동 이전할 수 없기 때문이다. 새 모델 설치나 모델 순위표는 만들지 않는다.

지배 비용은 자료 연결·기하 검증과 실제 입력 처리일 가능성이 있다. 기존 다운로드·모델 검증을 재사용하며, 사용하지 않을 실행기와 전문 모델을 정비하지 않는다. track 전체 비용 비율은 측정되지 않았다.

# Hypothesis

H1: 임상의 등급에서도 단일 sequence와 고정 LF가 공동 입력의 성능을 설명한다. 이 경우 새로운 공동 처리 방법의 투자 가치는 낮다.

H2: J는 두 단일 입력·LF·복제 R보다 높은 성능을 보인다. 이 경우 공동 처리의 추가 예측 가치 후보가 생기지만, 사례별 필요성이나 새로운 방법 효과는 아직 입증되지 않는다.

H3: 단독과 공동 입력 모두 text-only·위치 prior 및 영상 대응 제거 대조를 충분히 넘지 못한다. 이 경우 현재 frozen 모델·입력 조건의 적합성이 부족하며 결합 능력 해석을 보류한다.

# Limitation Evidence / Correct Usage Checks

대상 이력은 observed인 `mri-explicit-target-context-effect`다. iter_064의 입력 tensor·정답 연결 검증과 context 손실은 유지한다. SPIDER에 같은 한계가 존재한다고 전제하지 않으며 method gate의 근거로 확대하지 않는다.

자료 출처는 [SPIDER v4](https://zenodo.org/records/10159290), [저자 논문](https://www.nature.com/articles/s41597-024-03090-w), [공식 label 안내](https://spider.grand-challenge.org/data/)다. 전문 방법의 신호 주석과 최종 등급의 차이는 [SSD+ResNet18 연구](https://pmc.ncbi.nlm.nih.gov/articles/PMC10782244/)를 근거로 구분한다.

실행 자료는 `results/iter_021/source/`를 사용한다. iter_019의 불완전 images.zip을 사용하지 않는다. 기존 완성본 checksum 기록과 파일 크기·선택 member CRC를 연결하고, 출처 불변성을 확인할 수 없을 때만 전체 checksum을 다시 계산한다.

CSV의 Patient×IVD label을 mask의 200+IVD label과 연결한다. 아래부터의 ordinal label을 해부학적 L5/S1 이름으로 바꾸지 않는다. T1/T2에서 같은 ordinal이 같은 수준을 나타내는지 실제 anatomy와 전체 label 순서로 확인한다. 일치하지 않으면 해당 연결을 추정하지 않는다.

GT anatomy는 위치 지정용 oracle다. Modic 등급, 병변 위치 mask, 등급으로부터 만든 신호 설명은 모델 입력에 넣지 않는다. 전체 정상 환자 진단으로 확대하지 않고, Modic 0도 다른 질환이 없다는 뜻으로 쓰지 않는다.

# Contribution Path / Baselines / Reuse

기여는 아직 없다. paired MRI 분류, sequence별 신호 판별+규칙은 기존 접근이다. 이번 비교가 밝히는 것은 현재 VLM의 공동 처리와 단순 분리 처리의 상대적 가치다.

모델별 baseline은 다음과 같다.

1. S1: T1 단독.
2. S2: T2 단독.
3. J: 같은 대상의 T1 뒤 T2를 제공.
4. R: D의 0/II 주지표에서 선택한 단일 sequence를 두 번 제공. 동률이면 T1. 두 묶음이 복제임을 입력에서 명시한다.
5. LF: S1/S2의 네 후보 확률을 가중치 0.5로 평균해 argmax. 학습·threshold 탐색 없음.
6. 동일 문구의 text-only와 D 기반 global/IVD-ordinal prior. D에 없는 ordinal은 global prior, 동률은 작은 등급을 선택한다.

J의 최종 추가 가치 판단은 D 선택 B뿐 아니라 S1과 S2 각각을 상대로 한다. 평가 결과를 보고 유리한 singleton을 공식 baseline으로 바꾸지 않는다. LF는 기존 출력만으로 계산한다.

source 재사용은 JSON의 manifest를 따른다. 새 브랜치 기반은 자동 선택한다. 현재 확인한 자동 기반은 iter_006이며 필요한 여섯 파일을 선별 반입한다. `mi19_data`의 reference slice-pair 선택이나 과거 MSD 평가기를 새 과제에 적용하지 않는다. m65에서는 모델 로딩·공식 입력 구성·기초 저장 함수를 재사용하고, MSD 전용 CLI와 sidecar 비용 경로를 호출하지 않는다.

직접 SFT와 전문 Modic classifier는 큰 방법 투자 전 필요한 비교다. 이번에는 아직 공동 처리의 추가 가치도 미확인이고 원 전문 방법의 sequence별 ROI 주석이 없으므로 재현했다고 주장하지 않는다. 미설치를 제외 근거로 삼는 것이 아니라 현재 판단 범위를 제한한다.

# Proposed Experiment

## 1. 자료 연결과 동작 확인

기존 `results/iter_021/data/split.json`의 D/E만 사용한다. paired T1/T2가 없는 환자는 사전에 제외하고 목록을 보존한다. F139와 그 영상은 열지 않는다.

D에서 실제 T1/T2·mask·CSV 연결을 확인한다. RAI와 ASL 방향을 모두 검증하며, D에 필요한 방향 예제가 없으면 E의 header와 anatomy만으로 해당 변환을 검사하되 모델 출력은 보지 않는다. SimpleITK를 독립 기준으로 decoded array와 index-to-physical 대응을 대조한다. 비유한 영상, 잘못된 grid·ordinal 연결은 기술 오류다.

영상은 각 sequence의 native sagittal stack을 유지한다. anatomy로 지정한 IVD 주변을 모든 sagittal slice에서 같은 in-plane 범위로 보여 준다. crop은 IVD의 물리 bbox를 기준으로 superior/inferior에 각각 해당 disc의 AP 폭만큼, AP에는 폭의 25%씩 확장한다. 좌우 slice 범위는 줄이지 않는다. 이 규칙은 인접 endplate·marrow를 포함하기 위한 위치 안내이며 병변 GT를 사용하지 않는다. 경계 clipping과 실제 포함 범위를 기록한다.

각 sequence의 전체 volume으로 고정한 1–99 percentile window, 같은 RGB 채널, 물리 종횡비 보정을 적용한다. anatomy mask를 병변처럼 채색하지 않는다. D에서 crop이 잘못된 수준을 가리키거나 인접 endplate를 잘라낸 경우 기하 오류를 수정한다. 임상적으로 충분하다는 판정은 만들지 않는다. 표현 범위를 바꿔야 한다면 E 출력 전에 규칙과 이유를 고정한다.

공식 모델 processor를 사용한다. S1/S2의 영상 tensor와 J/R 안의 해당 영상 tensor가 같은지 검사한다. 조건별 resize가 달라지면 동일 관측 비교가 성립하도록 고정한다. 영상 수 때문에 입력을 조용히 자르거나 일부 환자만 해상도를 낮추지 않는다.

## 2. 답변 인터페이스

고정 질문은 지정한 IVD 주변 Modic 등급을 묻고 선택지를 A=0, B=I, C=II, D=III로 제공한다. sequence 종류·순서는 사실대로 알린다. 기하 정보 이외의 CSV 값은 넣지 않는다. 단일 조건에서도 동일 네 후보를 유지한다.

이번 primary 출력은 자유 생성이 아니라 고정 후보 분류다. 공식 `model.forward`의 assistant 시작 위치 logits에서 A/B/C/D 점수를 얻어 네 후보 내 softmax와 argmax를 저장한다. 후보가 해당 tokenizer에서 각각 정확히 한 token인지 D에서 확인한다. 실패하면 임의 문자열을 탐색하지 말고 공식 teacher-forced 후보 likelihood 경로로 기술 구현을 고정한 뒤 E 전에 기록한다.

D에서 공식 generate 첫 단계 logits와 직접 대조한다. custom lm_head나 m66 helper를 사용하지 않는다. 한 token 분류의 종료를 비EOS 생성 실패로 취급하지 않으며, 자유 생성 능력으로도 보고하지 않는다. 후보 밖 최고 token과 후보 전체 확률 질량을 별도로 기록해 인터페이스 부적합 가능성을 남긴다.

## 3. 가능성 탐색

D 적격 7명·최대 51 IVD에서 baseline 선택과 실행 구성을 고정한다. 학습은 없다. R을 선택하기 위한 D 성능을 확증으로 사용하지 않는다.

E12는 기존 E 순서를 유지한 paired 적격 환자 첫 12명이다. 영상·정답 연결을 통과한 모든 IVD를 포함하고 모델 정오답으로 표본을 고르지 않는다. 두 모델 모두 S1/S2/J/R 및 파생 LF를 수행한다. 기술 실패 사례는 정답이나 모델 성능을 보고 대체하지 않는다.

E12의 primary는 정답이 0 또는 II인 행에서의 두 class 평균 recall이다. 예측 I/III는 오답이다. 실제 I/III 행은 별도 네 class confusion table과 사례별 출력으로 보고하며 정상/II로 합치지 않는다.

확대 조건은 Evaluation을 따른다. 한 모델이 부적합하다고 다른 모델까지 자동 중단하지 않는다. E12는 탐색이며 확증용 CI 통과를 실행 gate로 요구하지 않는다.

## 4. 조건부 규모 확대

확대 조건을 통과한 모델만 기존 paired E 전체 최대 43명·298 IVD를 완료한다. E12 출력은 재사용한다. 이는 개발 확대이며 독립 확인이 아니다. 전체 E의 기본 분석 단위는 환자 cluster이고 IVD 행을 독립 환자로 세지 않는다.

E까지 완료한 뒤에는 threshold·prompt·후보 문자열·seed·모델을 추가하지 않는다. F139 사용이나 새로운 학습은 별도 연구 판단이 필요하다.

## 5. 자원·비용·재개

실행 직전 `nvidia-smi`와 상속된 허용 장치의 UUID 대응을 확인한다. 여유가 큰 GPU부터 배정하고 두 모델 또는 독립 환자 shard를 GPU 0/1에 나눈다.

D의 대표적인 짧은/긴 stack으로 batch1과 유망한 batch 확대를 비교한다. 메모리가 허용하면 같은 GPU의 두 worker도 후보로 삼되, 모든 구성을 전수 탐색하지 않는다. GPU 전체 점유에 worker당 2 GiB 여유를 더한다. m66 batch2 실패를 새 경로에 자동 이전하거나 무시하지 말고, 이번 공식 forward의 후보 확률 오차≤1e-3와 예측 일치를 확인한다. 실패하면 검증된 batch1을 쓴다.

기록 항목은 유효 항목/분, 영상 수·token 수별 latency, peak allocated/reserved 및 GPU 전체 점유, OOM·CPU/I/O 경합이다. 답변과 timing은 같은 원자적 record에 저장한다. source 읽기·render·processor·forward·저장 시간을 구분하며 LF의 두 singleton 비용을 모두 포함한다. GT anatomy 획득 비용이 빠진 oracle 비교임을 명시한다.

최대 영상 forward는 349 IVD×4조건×2모델=2,792개다. 이는 기술 제외 전 상한이며 실제 E 확대는 조건부다. 기존 iter_066의 432 candidate forward·618초는 다른 입력의 참고 처리량일 뿐이다. native stack 수가 더 많아질 수 있으므로 고정된 시간 상한을 두지 않는다. D에서 모델별 조건별 처리량을 측정한 뒤 `남은 항목×조건별 평균 시간/검증된 병렬 처리량 + loading·render`로 E12와 E 전체 예상 wall-clock을 실행 전에 적는다. 수 시간이 필요해도 현재 두 GPU 범위에서 실행한다.

요청은 환자·IVD·모델·조건의 고유 ID를 갖는다. worker별 파일·원자적 claim·출력 seal을 사용한다. 실제 저장 직후 종료, append 중 다른 worker 읽기, 부분 마지막 행, 중간 손상 거부 및 재개를 검사한다. 완료된 record를 비용만 누락된 채 완료 처리하지 않는다.

# Implementation Tasks for Claude

1. manifest의 소스와 의존성을 확인하고 선택된 함수만 연결한다. 기존 결과·환경·hf_cache를 변경하지 않는다.
2. `results/iter_067/`에 source provenance, paired 환자 목록, grading 연결과 기술 제외 사유, 고정 요청·설정을 저장한다.
3. 새 과제에 필요한 grading/위치 안내 adapter와 evaluator를 구현한다. 과거 reference·MSD의 선택 규칙을 재사용하지 않는다.
4. 필요한 경우 SimpleITK 등은 승인된 격리 환경에 구성하고 Python 경로·버전·설치·실제 입력 검증을 남긴다.
5. D에서 기하·공식 입력·후보 점수·재개·처리량 검사를 완료한다. 모델 오답은 기술 gate 실패로 바꾸지 않는다.
6. 두 모델의 E12를 실행하고 고정 기준으로 모델별 확대 여부를 기록한다. 통과한 모델만 E 전체를 완료한다.
7. raw logits·후보 확률·예측·confusion counts·환자 bootstrap·비용을 저장하고 별도 계산으로 주수치를 검증한다.
8. 보고서 첫머리에 선택한 자료·실제 표본·기본 신호·추가 가치·종료 결정을 적는다. 새로운 방법, 임상 성능, 결합 능력으로 과장하지 않는다.

# Evaluation (성공/실패 기준 포함)

## 지표와 대조

주지표 BA02는 실제 0/II 행의 class별 recall 평균이다. I/III 오예측도 각 class의 오답에 포함한다. 4-class confusion, 전체 정확도, 환자별 오류 수, 실제 I/III의 모든 출력, 후보 밖 최고 token 비율을 함께 보고한다.

95% CI는 환자 단위 paired bootstrap 10,000회·seed67로 계산한다. 단일 class만 남는 bootstrap replicate는 제외 수를 보고한다. 환자별 여러 IVD를 독립 재표집하지 않는다. 탐색적 여러 비교의 CI를 확증적 다중 가설 검정으로 설명하지 않는다.

영상 대응 제거 대조는 같은 ordinal의 다른 환자에 저장된 예측을 재배정해 계산한다. 자기 환자는 donor에서 제외한다. donor가 없는 ordinal은 null 분석의 미산출 범위로 표시하며 값을 만들어 넣지 않는다. 이를 모델의 내부 영상 사용 원인 증명으로 해석하지 않는다.

## E12 확대 기준

각 모델에서 S1/S2/J/LF 중 적어도 하나가 BA02≥0.65이며, D 위치 prior와 해당 text-only 및 영상 대응 제거 대조를 각각 5 pp 이상 넘어야 한다. 이는 기본 영상 신호의 탐색 기준이며 임상 적합성 기준이 아니다.

동시에 J 또는 LF가 D 선택 singleton B와 절대 5 pp 이상 차이나야 한다. 이 차이는 개선 또는 저하 모두 허용한다. 기본 신호가 있는 상태에서 처리 방식이 투자 판단을 바꿀 만큼 달라질 가능성을 확인하기 위한 조건이다. CI 유의성을 확대 gate로 요구하지 않는다.

둘을 만족하지 못하면 그 모델의 추가 E를 실행하지 않는다. 양 class가 없거나 유효한 null 비교 범위가 없어 기준을 계산할 수 없다면 통계적 음성으로 부르지 않고 불확정으로 종료한다. 부족한 class를 찾아 E 순서를 바꾸지 않는다.

## 최종 결과별 결정

- **공동 처리 추가 가치 후보:** J의 BA02≥0.70, 0/II 각각 recall≥0.60, prior·text-only·null 대비 각각 ≥5 pp를 요구한다. 또한 J가 S1과 S2 각각 및 LF보다 ≥5 pp 높고, 그 차이의 95% CI 하한이 0보다 커야 한다. J−R도 양의 CI 하한을 요구한다. 5 pp는 영상 두 묶음을 처리하는 비용을 감수할 후속 확인의 최소 투자 폭으로 이번 과제에 한정한다. 통과하면 고정 baseline과 관찰을 보존하고 독립 확인의 가치를 다음 리뷰에서 판단한다. 결합 실패나 신규 방법은 주장하지 않는다.
- **단순 대안 충분:** 기본 신호가 있고 singleton 또는 LF가 J보다 좋거나, J의 추가 이득이 위 기준에 못 미치면 해당 대안을 보존한다. 특히 LF가 저하를 회복해도 기존 방법 효과이지 새 contribution이 아니다. 현재 공동 처리 방법 투자를 종료한다.
- **기본 신호 부족:** 두 모델에서 기본 신호가 확보되지 않으면 현재 frozen Modic 경로를 종료한다. 부분 영상·인식·인터페이스의 원인은 미확정으로 남기고 적응을 자동 시작하지 않는다.
- **불확정:** 점추정은 유망하지만 E 전체의 정밀도가 부족하면 현재 경로를 보류한다. rare I/III의 두 행이나 추가 prompt로 이를 해결하지 않는다. 독립 자료와 강한 비교군이 구체적으로 확보되는 새 근거가 있을 때만 재개한다.
- **기술 오류:** ID·GT·좌표·입력·scoring 오류는 execution failure로 분리한다. 영향을 받는 요청만 고정 조건으로 복구할 수 있으며 반복된 설계 변경이나 성능 기반 재선택은 허용하지 않는다.

# Risks / Checks

- 전문의의 최종 등급은 sequence별 신호 정답과 다르다. 모델 정오답으로 관측 필요 집단을 만든다면 사후 탐색이며 primary에 쓰지 않는다.
- 0/II 중심의 결과를 I/III 또는 모든 Modic 유형으로 일반화하지 않는다. 희귀 유형을 숨기거나 0으로 합치지 않는다.
- anatomy crop은 oracle 위치 안내다. 주변 marrow 포함은 기하적으로 확인하되 임상적 충분성을 보증하지 않는다.
- 기존 SPIDER D/E는 개발 자료다. F139·공식 hidden test를 소비하지 않는다. 사전학습 노출과 외부 일반화는 미확인이다.
- m65의 답변/비용 sidecar와 m66의 custom scoring·batch2 결함을 새 경로에 반입하지 않는다. 필요한 공식 입력·저장 경로의 검증만 수행한다.
- 모델별 해상도·image token·크기·학습 노출·비용을 기록한다. 모델 차이를 내부 원인으로 확정하지 않는다.
- 전문 classifier나 직접 SFT를 실행하지 않은 상태에서 기존 해결책의 부족함이나 VLM 우위를 주장하지 않는다.

## 대규모 GPU 필요 후보

sequence별 국소 신호 주석과 임상 등급을 함께 사용하는 volume–text 사전학습은 장기 후보다. 현재는 주석과 공동 처리의 추가 가치가 확인되지 않아 투자하지 않는다. 이 보류는 두 RTX 3090에서 가능한 LoRA·adapter 전체를 금지하는 뜻이 아니다.

# 계획의 근거 (GPT 조사 노트)

## 이번 판단

기본 MRI 인식 적응은 이번에 선택하지 않는다. iter_059의 전문 대안은 현재 MSD 구간 과제에서 BA 0.950 대 U8 0.769, 전체 비용 비율 0.601이었다. iter_065의 선택 정책과 iter_066의 scoring도 위치 prior 이후의 가치를 확보하지 못했다. 새로운 잔여 과제 없이 같은 자료를 직접 SFT하는 것은 다음 투자 결정을 명료하게 만들지 못한다.

SPIDER에서도 사례별 관측 필요성은 식별할 수 없다. 임상 정의는 유형의 일반적 신호 조합을 설명하지만, 해당 환자의 부분 영상 충분성을 보증하지 않는다. 따라서 ‘상보적 근거 결합 실패’ 대신 ‘임상의 등급에 대한 공동 처리의 추가 예측 가치’를 이번 질문으로 한정한다. 양성 결과도 독립 확인 후보이지 신규 방법 근거가 아니다.

## 직전 질문에 대한 답

1. 임상 정의만으로 실제 sequence별 충분성·필요성을 확정할 수 없다. 기존 전문 방법은 sequence별 ROI 신호를 별도로 주석해 학습했다. SPIDER 최종 등급을 그런 주석으로 역변환하지 않는다. 다만 같은 최종 정답으로 singleton·joint·late fusion의 예측 성능은 비교할 수 있다. [가까운 전문 방법](https://pmc.ncbi.nlm.nih.gov/articles/PMC10782244/)
2. MSD 기본 인식 적응은 전문 대안 이후의 중요한 잔여 가치가 없어 보류한다. 원 리뷰의 종료 범위를 유지하며 MRI 적응 전체를 기각하지 않는다.
3. 제한된 실제 출력 비교는 기존 개발 split 안에서 가능하다. CSV를 다시 집계한 paired T1/T2는 D 7명·51행(0=42, II=9), E 43명·298행(0=187, II=109, I=1, III=1)이다. 실제 영상-mask 연결은 구현 단계에서 확인한다. F139는 개방하지 않는다.

## 자료 경로 정정

round_01은 iter_019/source의 archive 존재를 확인했지만 완전성을 확인하지 않았다. 이번 zip directory 읽기에서 해당 images.zip은 BadZipFile이었다. 검증된 완성본은 iter_021/source/images.zip이다. images_zip_verify.json은 크기 3,700,562,886 bytes, 공식 MD5 7a9fa44aac0c72e2937bdef62cff88db 및 CRC 통과를 기록한다. 이번에는 ZIP directory와 D/E의 MHA header를 실제 읽었으며 전체 MD5를 다시 계산하지 않았다. 새 다운로드가 필요한 상황은 아니다.

헤더에는 RAI와 ASL이 함께 있어 첫 번째 배열 축을 일률적으로 sagittal로 쓰면 안 된다. 원 모듈의 독립 물리좌표 검증 문제가 이번 사용 경로에 직접 관련된다.

[공식 배포](https://zenodo.org/records/10159290)는 IVD별 Modic grading을 제공한다. [저자 논문](https://www.nature.com/articles/s41597-024-03090-w)은 전문 근골격 영상의학과 의사의 수작업 grading과 환자별 series 연결을 설명한다. [공식 label 안내](https://spider.grand-challenge.org/data/)에서 IVD는 아래부터 201, 202 순이며 위쪽 척추 label에 대응한다. 이를 L5/S1 등 해부학 이름으로 자동 변환하지 않는다.

## 재사용 판단

iter_021·065·066 원 review.json/code_assets와 실제 소스를 읽었다. m65의 모델 로딩·공식 입력 구성만 사용하고, 과거 MSD protocol과 비용 sidecar 경로는 사용하지 않는다. m66의 batch2 및 custom scoring helper도 사용하지 않는다. 후보는 한 token인지 확인한 A/B/C/D이며 공식 forward로 점수를 얻는다.

현재 HEAD는 7bc3601ddfc6f4525a8ad73edf281f4c824b2fc6이고 작업 트리는 깨끗하다. orchestrator의 새 브랜치 기반 선택과 승인 기록을 확인했으며 자동 기반은 iter_006이다. 따라서 현재 브랜치에 존재하는 필요한 소스도 선별 manifest에 명시했다.

## 비용과 한계

새 archive·모델·환경 전면 구축은 필요하지 않다. 필요한 새 작업은 grading 연결, anatomy 위치 안내와 전체 sagittal 관측 범위, 고정 후보 평가다. 여전히 구현·자료 연결 검증이 GPU 출력보다 큰 비용일 수 있어 범용 실행기나 전문 분류기를 추가 개발하지 않는다. 결과에 따라 현재 세부 경로를 끝낼 수 있는 계약을 고정한다.

이번 문헌은 설계 근거이며 사용자 추천으로 등록하지 않는다.

이전 사고 라운드 노트: agent/runs/iter_067/think/
