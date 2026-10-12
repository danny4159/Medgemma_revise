# 요약

- **이번에 할 일:** CT의 같은 target 영상에서 reference에 따라 다른 대상을 찾는 진단을 수행한다. 공개 관계쌍이 성립할 때만 실제 모델 비교로 진행한다.
- **필요한 이유:** 과거 SPIDER 결과는 좌표 복사와 약한 기본 localization 때문에 대상 대응 능력을 구분하지 못했다. 이번에는 공식 대응 모델과 단순 분해를 함께 둔다.
- **확인할 기준:** 같은 target pixels·서로 다른 공식 정답·case 연결을 확인하고, 직접 대응의 실패가 기본 인식 또는 단순 대안으로 설명되는지 판단한다.
- **주의·다음:** 신규성·일반 한계는 미확정이다. 새 학습 없이 종료하고, 후속은 full review 뒤 사용자 승인을 받는다.

## 알림 맥락

- 연구: 영상 간 대상 근거 연결
- 데이터: 흉부 X-ray RSNA 초안 교정 → MedSG Task3의 CT 직교 view, 한 원천만 사용
- 모델: frozen MedSeq-Grounder와 Qwen2.5-VL-7B-Instruct
- 과제: 참고 영상의 지정 영역을 보고 다른 view의 같은 target 영상에서 대응 영역을 출력
- 가설: 기본 위치 찾기는 가능해도 reference의 대상 정보 전달에서 손실이 남을 수 있으며 단순 언어 분해가 이를 설명할 수 있음
- 질문: 참고 영역이 바뀌면 모델도 올바른 다른 대상을 찾는가?
- 변경: 방향 전환
- 연결: iter_119 자연 초안 교정은 근거 부족으로 보류하며, 과거 iter_021에서 구분하지 못한 대상 대응을 더 식별 가능한 조건에서 한정 검토
- 작업: 공개 관계쌍 확인 후 성립하면 직접 대응·단순 분해·기본 localization을 비교해 추가 개입 필요성을 판단

# Current Understanding

iter_118의 합성 초안 손상과 iter_119의 제한된 자연 답 상보성을 보존한다. RSNA 교차표·parser·초안 무시 prompt·selector·CURE 오류 검토는 재개하지 않는다.

이번은 초안 손상의 원인 분석이 아니라 다른 질문의 재선별이다. 다만 대상 대응은 iter_019/021에서 이미 다뤘으므로 새 이력으로 초기화하지 않는다. 당시 MedSG는 실제 관계 연결 미확인이었고 SPIDER에서는 좌표 복사가 유리했다. 이번에는 공식 Task3의 대응 입력과 직접 적응 모델을 사용하며, 과거 point oracle 대신 정답 대상명을 이용한 기본 localization 진단을 둔다.

실제 Task3 bytes와 적격 수는 아직 확인하지 못했다. 이것은 자료 부재의 증거가 아니다. 이번 계획의 첫 단계에서 한정 확인하며, 성립하지 않는 비교를 평균 benchmark 점수로 바꾸지 않는다.

# Strategy Check / 연구 방향 판단

**기술 질문 → 실패 조건 → 공개 정답 비교 → 주장 범위:** reference가 제공하는 대상 정보를 다른 view로 전달할 수 있는가 → 같은 target에서 reference를 바꿔도 잘못된 대상에 머무는 조건 → 동일 target pixels와 두 공식 정답 영역을 연결한 paired 비교 → 선택한 CT 원천의 해부학적 대상 연결에 한정한다. 임상 진단·시간 변화·병변 동일성의 일반 주장은 하지 않는다.

후보는 두 개만 비교했다.

1. **대상 대응:** 과거 식별 실패라는 구체적 반대 근거가 있고, 현재 작은 공식 parquet와 전용 모델을 통해 이를 해결할 가능성이 있다. 기존 MedSeq-Grounder와 언어 매개 분해가 다루는 범위는 인정한다. 남는 질문은 기본 localization이 가능한 사례에서도 두 경로가 함께 대상 정보를 잃는가다. 지배 비용 후보는 자료 연결과 두 7B 모델 준비·추론이며 아직 미측정이다.
2. **시간 변화:** 중요한 질문이지만 iter_022/055의 영상 접근·정답 연결 문제를 해결한 새 근거가 없다. 순서 정규화로 해결되는 일관성만 다시 측정할 가치는 낮아 이번에는 선택하지 않는다.

**시험 설정:** frozen 모델의 한 원천·한 관계 비교만 실행한다. **연구 관찰:** 기존 관찰을 보존하며 새 실패는 아직 없다. **연구 질문:** 관계 자료와 강한 대조가 성립하면 한정 탐색할 가치가 있다. 자료가 성립하지 않으면 모델 가설을 기각하지 않고 현재 실행 설계를 보류한다.

이전보다 달라지는 것은 Task3 metadata를 다시 읽는 일이 아니라 실제 pixels 수준의 관계 연결과 공식 적응 모델 비교다. 이 두 조건을 충족하지 못하면 재진입 근거가 없으므로 종료한다.

# Hypothesis

직접 대응 모델에서 reference 대상 정보가 손실될 수 있다. 경쟁 설명은 다음과 같다.

- 원자료가 동일 target·다른 대상 관계를 실제로 제공하지 않는다.
- 대상 자체를 localization하지 못한다.
- 좌표 prior 또는 영상 패턴 매칭만으로 충분하다.
- reference를 설명한 뒤 target을 찾는 단순 분해로 해결된다.
- 출력 형식·좌표 변환·generation cap이 비교를 가린다.

실패를 미리 가정하지 않는다. 단순 대안의 성공도 이번 의사결정의 유효한 결과다.

# Limitation Evidence / Correct Usage Checks

`mri-reference-interface-sensitivity`는 과거 식별 문제를 연결하는 observed 근거이며 이번 CT 실패의 근거나 method gate가 아니다. iter_021의 O pair success 0/48, J_TR 좌표 복사 79/96과 정상 사용 미완료 범위를 유지한다.

공식 출처는 [MedSG 저장소](https://github.com/Yuejingkun/MedSG-Bench), [Task3 parquet](https://huggingface.co/datasets/MedSG-Bench/MedSG-Bench-parquet/tree/main), [평가 코드](https://raw.githubusercontent.com/Yuejingkun/MedSG-Bench/main/eval/MedSG_Bench.py), [모델 카드](https://huggingface.co/MedSG-Bench/MedSeq-Grounder)다. 구현 전에 실제 revision과 이용 조건을 고정한다. 카드의 학습 노출 상세 미기재를 미노출로 해석하지 않는다.

공식 직접 조건은 원문 질문·영상 순서·reference 표시·모델별 좌표 규약을 유지한다. 실제 PNG 크기, metadata size, 출력 좌표 canvas와 processor resize를 대조한다. 모든 영상을 336×336으로 가정하지 않는다. target 정답 box·대상명·파일명은 일반 생성 worker에 제공하지 않는다. 대상명 진단 요청만 privileged 조건으로 분리한다.

# Contribution Path / Baselines / Reuse

신규 contribution은 미확정이다. MedSeq-Grounder의 직접 적응을 가까운 강한 기존 방법으로 실행한다. 그 base Qwen2.5-VL-7B를 함께 비교해 한 모델의 낮은 기본 수행을 일반 한계로 읽지 않는다. MedGemma를 추가로 실행하지 않는 이유는 이번 질문의 공식 지원 경로와 가장 가까운 전용 대조가 Qwen 계열이기 때문이다.

각 모델에 다음 조건을 둔다.

- **직접 대응:** 공식 reference와 target 입력으로 target box 생성.
- **언어 매개 분해:** reference 영상·지정 영역만 보고 대상을 한 문장으로 기술하고, 그 원문과 target 영상으로 box 생성. 중간 설명을 GT로 수정하거나 대체하지 않는다. reference 좌표는 target 단계에 넘기지 않는다.
- **대상명 진단:** 공식 metadata가 명확히 제공하는 대상명과 target만 입력한다. target 정답 좌표는 주지 않는다. 이는 privileged 기본 localization 대조이며 실용 정확도 순위에서 제외한다.
- **좌표 복사:** reference box의 원본 정규화 좌표를 target 크기로 옮긴다.
- **NCC:** 고정 세 scale의 영상 template matching. 단순 대조이며 학습된 대응 모델의 충분성을 대표하지 않는다.

분해는 직접 조건과 원정보가 같지만 호출 수가 두 배다. 정확도와 함께 단계 전체 latency·생성 token·실패율을 보고한다. 직접 SFT를 새로 학습하지 않는다. 공식 적응 모델이 이번의 강한 학습 baseline이며 동일 학습 예산의 방법 효과 비교는 아니다.

재사용 기반은 승인된 iter_082다. `reuse_assets`에 지정한 iter_021의 세 파일만 반입해 NCC·좌표 계산에 쓴다. 기존 SPIDER loader와 생성기는 새 과제의 입력·모델 규약이 달라 호출하지 않는다. 새 Task3 loader와 공식 Qwen adapter는 이 차이에 필요한 범위로 작성한다. 기존 rsna_diag 좌표를 Qwen 좌표로 그대로 재사용하지 않는다.

# Proposed Experiment

## 1. 한정 자료 적합성 확인

`bench_task3.parquet` 한 파일과 대응 설명만 확보한다. 전체 benchmark·MedSG-188K 영상·원천 volume은 다운로드하지 않는다. 필요한 학습 overlap 확인은 해당 Task의 공개 metadata 범위로 제한하고, 확인되지 않으면 노출 불명으로 남긴다.

CT 직교 view 항목만 후보로 삼는다. 같은 원천·case·target decoded-pixel hash를 공유하면서 reference가 지정하는 두 대상과 공식 target box가 다른 쌍을 찾는다. target의 표시·crop·view가 다르면 같은 target으로 합치지 않는다. filename의 장기명만으로 정답을 새로 만들지 않고 공식 행의 대상 의미와 연결한다. 서로 다른 두 GT box의 IoU가 0.1 이하인 쌍만 사용해 어느 대상을 선택했는지 구분한다. 이는 겹치는 해부구조 전체에 대한 평가가 아님을 보고한다.

원천별 적격 case 수를 모델 출력 전에 집계한다. 이용 조건·case 단위·대상명 의미가 성립한 원천 중 적격 case가 가장 많은 하나를 선택하고 동률은 원천명 사전순으로 정한다. 자료 이름을 바꿔 모델 실패를 찾지 않는다. case마다 유효 쌍 하나를 행 ID 사전순으로 선택한다. 적격 전체와 제외 사유, 좌표 복사 성공 여부를 보존하며 복사가 실패한 사례만 본표본으로 고르지 않는다.

적격 관계가 없거나 이용 조건·정답 의미를 확인하지 못하면 여기서 종료한다. 다른 Task·MRI·temporal 자료로 자동 이동하지 않는다. 모델 다운로드도 하지 않는다.

## 2. 동작 확인

case hash의 고정 순서로 최대 4 case를 TECH에 배정하고 나머지는 MAIN 후보로 보존한다. TECH에서 양 대상·세 조건·두 모델을 실행한다. 정확도 100%는 진입 조건이 아니다.

필수 검사는 영상 순서·reference 표식·GT canvas·비정사각 변환, 공식 processor와 wrapper의 input_ids 및 pixel_values 대응, 정답 파일 비접근, 생성 suffix·EOS·cap, 원시 출력과 request ID 연결이다. 분해의 두 번째 요청은 첫 출력 digest를 기록한다. 좌표 fixture는 정답/다른 대상/영상 밖/중복 box/형식 실패를 포함한다.

bbox parser는 공식 Qwen 형식을 기준으로 하나만 고정한다. 추가 설명에 유일한 유효 box가 있는 경우의 처리도 TECH 전에 정하고 전체에 동일 적용한다. 여러 box·비유한 값·역전 좌표는 invalid로 남긴다. 결과를 본 뒤 유리한 parser를 추가하지 않는다. 기본 max_new_tokens는 256, greedy decoding이다. TECH에서 cap 문제가 있으면 전체 조건을 512로 고정해 TECH를 한 번 다시 확인할 수 있으나, 이 재생성은 추가 검사 32회 한도에 포함하며 부족하면 MAIN을 보류한다.

## 3. 가능성 탐색과 최대 규모

MAIN은 최대 32개의 서로 다른 case다. case당 두 reference 요청이므로 모델·조건별 64개 target box를 얻는다. 초기 성능을 보고 조기 종료하거나 표본을 바꾸지 않고 잠긴 집단을 한 번 평가한다. 32 case는 case 단위 사건 하나가 약 3.1pp이며 흔한 실패 조건을 탐색하는 규모다. 작은 효과의 확증용 power를 주장하지 않는다.

적격 자료가 적으면 가용 MAIN 전체를 쓰되 8 case 미만에서는 빈도·투자 문턱 판정을 하지 않고 사례 기반 적합성 결과로 종료한다. 8은 확증 gate가 아니라 한두 사례를 반복 현상으로 부르지 않기 위한 제한이다. 8–31 case 결과도 저정밀 탐색으로 표시한다.

두 모델 각각 case당 직접 2회, 분해 4회, 대상명 진단 2회다. TECH+MAIN 최대 36 case에서 총 576회이며, 처리량·안전 재개 검사는 최대 32회 추가해 전체 608회다. 학습·seed 탐색·prompt 탐색은 없다. 이번 MAIN이 본비교의 최대 범위다. 독립 확인과 method pilot은 이번에 실행하지 않는다.

## 4. 자원·비용·재개

실행 직전 `nvidia-smi`로 GPU 0,1의 여유와 논리 index 대응을 확인한다. 두 7B 모델은 GPU별 하나를 우선 배정한다. bf16 weight만 약 15–17GB라는 추정이며 activation·KV를 포함한 실제 peak는 TECH에서 측정한다. worker당 최소 2GB 여유를 둔다.

TECH 입력으로 batch1과 batch2의 전체 처리량·peak·긴 출력 지연·출력 정합성을 비교한다. 동일 GPU의 두 bf16 worker는 예상 weight 합계만으로 24GB를 넘으므로 기본 후보에서 제외하고 이 근거를 기록한다. batch2도 안전하지 않거나 느리면 batch1을 유지한다. 모델당 한 장이 불가능하면 허용된 두 GPU에 단일 모델을 분산하고 모델을 순차 실행할 수 있으며 비용 변경을 기록한다. 임의 양자화로 공식 재현 조건을 바꾸지 않는다.

시간은 TECH의 모델별 유효 요청/분과 분해 단계 비용으로 계산한다. 예상 wall-clock은 두 모델 병렬 workload 중 큰 값에 준비·검증 시간을 더해 보고한다. 현재 처리량이 없으므로 수치 시간을 만들지 않는다. 임의 device-minute 상한은 두지 않는다.

새 환경이 필요하면 경로·이유를 먼저 알리고 승인된 격리 환경에서 설치한다. 기본 환경과 hf_cache는 변경하지 않는다. 공식 소스 revision·checkpoint·패키지·다운로드 checksum을 보존한다.

request별 원자적 claim과 worker별 append-only 결과, 성공 상태·종료 코드·digest를 검증하는 completion을 둔다. 통제 중단·재개와 중복 launch 거부를 TECH에서 확인한다. 이미 성공한 요청은 재생성하지 않으며 실패 attempt도 보존한다. 결과는 `research/results/iter_120/`에 저장한다.

# Implementation Tasks for Claude

1. 기준 원문은 이번 계획, iter_120 round_01 노트, iter_021 review의 한계·선별 모듈 승인 범위다. 과거 SPIDER 계획의 표본·gate를 계승하지 않는다.
2. Task3 한정 자료 연결 보고서를 만들고 성립 여부·선정 원천·case·pixel hash·두 GT·제외 사유를 잠근다. 실패하면 나머지 실행을 하지 않는다.
3. 공식 모델 adapter와 고정 조건을 구현하고 실제 입력·좌표·정답 분리·중간 출력 연결을 검사한다.
4. TECH에서 처리량·메모리·재개를 확인하고 실행 구성·예상 시간을 잠근 뒤 MAIN을 한 번 실행한다.
5. 원시 출력에서 주지표와 실패 사건을 계산하고 별도 검산 코드로 case별 결과·분모·비용을 확인한다. 범용 평가기나 기존 실행기 전수 정비는 하지 않는다.
6. 보고서는 시험 설정, 연구 관찰, 연구 질문의 판정을 분리한다. 자료 연결만 완료됐으면 새 모델 현상을 발견했다고 쓰지 않는다.

# Evaluation (성공/실패 기준 포함)

## 지표와 사건

전체 MAIN case를 분모로 조건별 두 대상 모두 IoU≥0.5인 pair success, 요청별 mean IoU·Acc@0.5, invalid·cap 비율을 보고한다. 모델 내 직접−분해 차이는 case 단위 paired bootstrap 10,000회 95% 구간으로 제시한다. 이는 개발 탐색의 불확실성 표현이며 독립 확증이 아니다.

명시적 다른 대상 선택은 자기 GT IoU<0.3이고 상대 GT IoU≥0.5일 때다. 단순 부정확한 box와 분리한다. 두 reference에서 같은 box를 냈다는 사실만으로 대상 무사용을 단정하지 않는다.

주요 진단 사건은 대상명 조건이 두 대상을 모두 맞힌 case에서 직접 조건이 적어도 하나를 명시적으로 다른 대상으로 선택하는 경우다. 전체 분모의 빈도와 대상명 성공 집단 내 조건부 빈도를 함께 보고한다. 단순 분해·좌표 복사·NCC가 이 사건을 해결하는지도 같은 case에서 보고한다.

## 양성·음성·불확정과 행동

- **잔여 현상의 양성 탐색:** 전용 MedSeq-Grounder에서 위 사건이 MAIN의 15% 이상이면서 최소 4 case에 나타나고, 직접·분해가 함께 명시적 대상 혼동을 보이는 case가 최소 3개면 개입 필요성을 검토할 근거로 보존한다. 15%는 임상 허용 오류율이 아니라 작은 방법 시험을 검토할 빈도 기준이다. 정밀도·노출·원천 제한을 유지한다. 좌표 복사/NCC가 대부분 해결하거나 자료 결함이 설명하면 이 분기를 승인하지 않는다. 후속 후보는 reference 대상 정보 전달을 보존하는 최소 개입 하나이며 이번에 학습하지 않는다.
- **단순 대안의 양성:** 분해가 직접 대비 pair success를 10pp 이상 높이면 정확도 회복과 두 단계 비용을 보고한다. 이는 기존 분해의 유용성이지 새 방법의 필요성 증명이 아니다. 남은 공동 실패가 위 기준에 못 미치면 현재 추가 개입 투자는 보류한다. 10pp 미만의 효과도 원수치·구간을 보존한다.
- **음성:** 전용 직접 모델이 대상 변경에 잘 대응하거나 단순 대안이 오류를 대부분 설명하면 현재 설계의 추가 투자를 보류한다. 일반 대응 문제가 모두 해결됐다고 주장하지 않는다.
- **불확정:** 기본 대상명 localization 부족, 적격 수 부족, 형식 문제, 모호한 정답 또는 넓은 구간 때문에 구분되지 않으면 근거 부족으로 보류한다. 낮은 기본 성능을 대응 결함으로 바꾸지 않는다. 같은 표본의 조건·문턱을 조정하지 않는다.

위 분기는 효과를 보기 전에 잠근다. 어떤 분기에서도 새 Task·추가 모델·학습을 자동 실행하지 않는다. 다음 사용자 승인 요청에는 선택한 후속 하나와 보류 범위를 명확히 보고한다.

# Risks / Checks

- 공식 Task3에 필요한 같은-target 관계가 없을 수 있다. 이 경우 자료 적합성 실패로 종료하며 metadata 접근 성공을 연구 성과로 과장하지 않는다.
- anatomy 이름은 instance 추적 정답과 다르다. 이번 주장은 공식 대상 category의 view 간 연결이며 동일 병변의 임상적 추적이 아니다.
- CT 원천의 이용 조건과 case 의미를 확인한다. 파일명의 case를 근거 없이 환자 ID라고 부르지 않는다.
- target 정답과 파일명 의미를 일반 입력에 누설하지 않는다. 대상명 조건은 명시적 privileged 진단이다.
- 공개 전용 모델의 학습 노출이 불명확하면 개발 진단으로 한정한다. 이를 해결하려고 전체 학습 영상 감사를 추가하지 않는다.
- NCC는 orthogonal view의 강한 대응 모델이 아니다. 실패만으로 VLM의 필요성을 주장하지 않는다. 직접 적응 모델과 언어 매개 분해가 필수 대조다.
- 정답 대상명 조건도 확장 입력이다. 그 실패는 기본 인식과 인터페이스의 혼합이며, 성공한 사례에서만 제한된 분해 해석을 한다.
- 대규모 GPU 필요 후보는 다중 영상 대응과 단일 영상 인식을 함께 보존하는 공동 적응이다. 현재 필요성은 미확정이며 이번 실행에 포함하지 않는다.
- GOAL·원 결과·checkpoint를 보존한다. full review 후 --confirm-each-iter 승인 대기를 유지한다.

# 계획의 근거 (GPT 조사 노트)

## 이번 선택

후보 둘 중 **reference에 따른 영상 간 대상 대응**의 조건부 진단을 선택한다. 시간 변화 후보는 기존 영상 접근·변화 정답 연결을 해결한 새 근거가 없어 실행하지 않는다. 자연 초안 교정과 CURE 오류 검토의 투자 보류는 유지한다.

## 직전 질문에 대한 답

1. **실제 관계쌍 확보 여부:** 아직 확인되지 않았다. 공식 parquet 목록에서 `bench_task3.parquet` 70.4MB를 확인했고 일반 viewer에서 image bytes와 원문 metadata가 있는 배포 구조를 확인했다. Task3 실제 행 조회는 실패했다. 따라서 관계가 성립했다고 쓰지 않으며, 이 한 파일의 bytes·metadata 연결을 구현의 첫 한정 점검으로 둔다. 파일 접근 성공과 연구 적합성은 별개다. [공식 파일 목록](https://huggingface.co/datasets/MedSG-Bench/MedSG-Bench-parquet/tree/main)
2. **과거와 달라지는 식별 근거:** `iter_019/think/round_02.md`와 `round_03.md` 원문은 과거에도 Task3 metadata·case 이름·비정사각 size를 확인했음을 보여준다. 새로운 발견으로 재포장하지 않는다. 이번 진입은 같은 target pixels에서 두 정답이 구분되는 관계와 공식 적응 모델을 실제로 연결하는 경우에만 정당하다. 단일 관계의 평균 점수 평가로 대체하지 않는다.
3. **강한 대안과 남는 질문:** MedSeq-Grounder는 Qwen2.5-VL-7B-Instruct를 MedSG-188K로 적응한 공개 모델이다. 현재 카드의 학습·평가 상세에는 미기재 부분이 있어 독립 미노출을 주장할 수 없다. 단순 reference 설명→target grounding도 같은 정보의 실용 대조로 실행한다. 이 대안이 충분하면 추가 방법 투자는 보류한다. [공식 모델 카드](https://huggingface.co/MedSG-Bench/MedSeq-Grounder)

## 출처와 해석 경계

- `agent/runs/iter_120/think/round_01.json` 원문, GOAL, iter_119 리뷰, iter_019 계획·조사 노트, iter_021 리뷰와 code_assets, LIMITATIONS의 해당 항목을 확인했다.
- iter_021의 O pair success 0/48, J_TR 좌표 복사 79/96은 현재 일반 대응 한계의 증거가 아니다. 이번에도 기본 인식이 약하면 해석을 제한한다.
- MedSG 논문 Task3은 실제 multi-view와 volume 직교 단면을 함께 다룬다. 여기서는 CT 직교 view의 해부학적 대상 연결로만 좁히며 시간 변화·임상 병변 추적을 주장하지 않는다. [논문 §3.2](https://arxiv.org/html/2505.11852v1)
- 공식 평가기는 `multi_view`에서 target size를 별도로 처리한다. 원본 PNG·GT canvas·Qwen processor resize의 대응을 검사해야 한다. [공식 평가 코드](https://raw.githubusercontent.com/Yuejingkun/MedSG-Bench/main/eval/MedSG_Bench.py)
- 현재 research HEAD는 `0846c0834bf179cc9e7ca6044c0cf0f4bd629486`이며 status와 diff에 변경이 없었다. 새 기반 iter_082에는 선택한 rsna_diag 파일이 없어 승인 모듈만 선별 반입한다. 기존 생성기 재사용 문제를 이번 승인으로 해제하지 않는다.

## 대규모 GPU 필요 후보

다중 영상 대응과 단일 영상 인식을 함께 보존하는 공동 적응은 장기 후보로 남긴다. 현재는 잔여 현상과 단순 대안의 부족함이 미확인이라 대규모 학습의 필요성·효과를 주장하지 않는다. 이번에는 frozen 모델 비교만 수행한다.

이전 사고 라운드 노트: agent/runs/iter_120/think/
