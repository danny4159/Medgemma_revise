# 요약

- **이번에 할 일:** 공식 자료 접근을 확인한 뒤, 기존 RSNA SFT와 base의 VinDr Lung opacity grounding을 비교한다. iter_031의 남은 분석은 저장 출력으로 마무리한다.
- **필요한 이유:** continuation은 일부 후보를 회복했지만 FP 비용이 컸다. 기존 SFT가 외부의 더 넓은 target에서도 유용한지 확인하면 다음 투자를 결정할 수 있다.
- **확인할 기준:** 동일 입력·두 고정 prompt의 위치 성능, 음성 FP, invalid와 paired 불확실성을 함께 평가한다.
- **주의·다음:** 데이터 이용 권한·경로 확인 전 실행을 보류한다. 외부 전이와 신규 contribution은 미검증이며, 새 학습·MRI F139·기존 reserve는 이번 범위에 포함하지 않는다.

# Current Understanding

iter_012의 직접 LoRA SFT 성과는 유효하다. RSNA 확인 양성 400명의 F1@0.3은 세 seed에서 0.631–0.653이었다. iter_031의 continuation은 E 누락 사건 11/27을 회복했지만 전체 F1@0.3을 0.6276에서 0.4738로 낮췄다. 라운드 02의 사후 분석에서도 중복 제거만으로 비용 문제가 해소되지 않았다.

이미 답한 질문은 QA 평가의 큰 형식 효과, evidence 전달의 인터페이스 효과, 현재 사분면 선택에서 규칙 baseline의 우위, 빈 출력 위험 baseline과 continuation의 제한적 회복이다. 일반적 공간 전이와 외부 일반화는 미해결이다. 완료된 진단을 새 이름으로 반복하지 않는다.

유지할 것은 GOAL, 기존 checkpoint·출력·분할·판정이다. 보류할 것은 새 loss·학습, oracle prompt 재탐색, 합성 robustness 본평가와 iter_022 longitudinal이다. 변경할 것은 후속 투자 대상이다. 현재 continuation 설계의 추가 투자를 종료하고 기존 SFT의 외부 전이를 우선한다. 이 판단은 RSNA SFT 전체의 기각이 아니다.

현재 이용 가능한 것으로 확인한 VinDr 표본은 선택된 10개 영상이다. 공식 평가용 annotation·영상의 이용 권한과 경로는 미확인이다. 아래는 접근 확보 후 실행할 조건부 완성 계획이며, 사용자 답변만으로 실제 자료 검증 gate를 통과한 것으로 취급하지 않는다.

# Strategy Check / 연구 방향 판단

중요한 능력은 특정 grounding 적응의 이득이 다른 원천과 관련 target에서도 유지되는지다. 좁은 데이터 점수 개선을 일반적 공간 능력으로 확대하지 않는다.

1. **현재 방법 개선:** continuation의 FP 비용과 Pix2Seq의 종료·순서·sampling 선행을 고려하면 추가 head·loss 투자의 근거가 약하다. 현재 설계는 종료한다.
2. **원인·능력 전이 진단:** VinDr는 같은 modality에서 기존 adapter를 검증하면서 정답 box를 직접 사용할 수 있다. 결과는 adapter 유지와 외부 적응 투자 여부를 바꾼다. 다만 원천·target 이동의 인과 분리는 이번 범위 밖이다.
3. **다른 연구 질문:** 합성 배치 변화는 정확한 전처리 역변환이 강한 해법인 조건이어서 단독 방법 개발 경로가 약하다. 자료 접근을 확보하지 못하면 다른 질문을 명시적으로 선정하며 MRI·시간 변화로 자동 이동하지 않는다.

선택 이유는 GPU 비용의 최소화가 아니라 의사결정 가치다. 데이터 접근이 불가능하거나 target·영상·annotation 연결을 검증할 수 없으면 이 계획의 실행을 보류한다. 외부 점수 추가 자체를 contribution으로 삼지 않는다.

# Hypothesis

고정된 RSNA 직접 SFT B0는 VinDr Lung opacity 질문에서도 M0보다 양성 영상의 위치 성능이 높고, 음성 영상의 FP 비용은 크게 늘리지 않을 수 있다.

주효과 Δ는 양성 영상마다 두 prompt의 F1@0.3을 평균한 뒤 계산하는 B0−M0 차이다. 실질적 효과의 탐색 기준은 |Δ|=0.10, 목표 CI 반폭은 약 0.05로 둔다. 이 값은 임상 허용 오차가 아니라 다음 연구 투자 결정을 위한 기준이다.

대립 설명은 RSNA target에 대한 특화, 외부 영상 분포, 주석 범위, prompt 반응과 형식 차이다. 이번 비교만으로 이들을 내부 원인으로 확정하지 않는다.

# Limitation Evidence / Correct Usage Checks

`lesion-grounding-generalization`의 validated 범위는 iter_009·012의 RSNA 조건이다. 외부 실패의 검증 상태를 자동 상속하지 않는다. `rsna-partial-omission-continuation`은 observed이며 이번에는 저장 결과의 보완 분석만 한다.

모델은 MedGemma 1.5 revision `91850547d9f0b2fdd21aa7c5f4f3d1a8a52c243b`로 고정한다. processor·chat template·package 버전, adapter 파일 및 tensor digest를 기록한다. 보존된 공식 anatomy notebook을 입력 구성의 출처로 사용한다.

외부 target은 정확히 VinDr의 Lung opacity다. Pneumonia global label로 box의 원인을 지정하거나 Consolidation·Infiltration을 합치지 않는다. Lung opacity 음성은 해당 annotation 체계의 음성이며 임상적 정상과 같지 않다. [공식 label·파일 설명](https://physionet.org/content/vindr-cxr/1.0.0/)

DICOM의 원본 행·열, photometric interpretation, modality/VOI 변환과 padding을 기록한다. 정식 renderer 또는 검증된 라이브러리 경로를 사용하고 D의 실제 영상에서 독립 렌더링과 좌표 overlay를 대조한다. 복수 VOI 등 모호한 경우 모델 결과를 보기 전에 규칙을 고정한다. 좌우 반전·crop·GT clipping으로 오류를 감추지 않는다. 해석할 수 없는 입력이 있으면 임의 제외해 진행하지 않고 원인과 영향 범위를 보고한다.

실제 D 입력에서 공식 구성과 wrapper 전체 tensor를 비교한다. 기존 RSNA 개발 영상 6개로 B0 연결과 저장 suffix의 소규모 재현을 확인하고 M0의 adapter 비활성 경로를 별도로 확인한다. 기존 RSNA 본평가는 재실행하지 않는다.

# Contribution Path / Baselines / Reuse

## 비교군과 해석

- M0와 B0는 같은 원본 영상, 동일한 두 prompt, greedy 생성과 동일 출력 길이 ladder를 사용한다.
- 공식 grounding template의 object_name을 `lung opacity`로 바꾼 조건과 기존 concise의 target 구절만 같은 의미로 바꾼 조건을 모두 고정한다. 두 조건 중 결과가 좋은 것만 선택하지 않는다.
- 출력은 기존 JSON bbox schema와 엄격 parser를 사용한다. label 문자열의 지시 준수는 별도로 보고하며 parser 규칙을 모델별로 바꾸지 않는다.
- Empty와 전체 영상 box는 평가 sanity용이다. GT를 입력으로 제공하지 않는다.
- 이번 비교의 강한 직접 적응 자산은 iter_012 SFT다. 외부 target 직접 SFT나 detector를 실행한 것으로 표현하지 않는다. 후속 방법 우위 주장 전에는 같은 annotation·학습량의 직접 SFT와 detector/encoder+head 비교가 필요하다.

새로운 contribution은 미확정이다. 양성 결과는 기존 baseline의 활용 범위를 넓히며, 음성 결과는 외부 적응의 필요성을 검토할 근거가 된다. 어느 쪽도 새 loss 도입을 자동 지시하지 않는다.

## 코드·checkpoint

새 브랜치는 재사용 승인 iter_006을 기반으로 하고 `reuse_assets`의 11개 파일을 선별 반입한다. 출처는 `8dad463392de9bb0e9fe7d93d64b9c374492de9b`다. 기존에 보존된 함수를 다시 구현하지 않는다.

B0는 `results/iter_012/train/lr2e-4_s17/epoch_05/adapter.pt`다. 조건부 seed 확인은 같은 lr·epoch의 s29/s43을 사용하며 기존 선택 파일과 digest를 연결한다. B0 파일 SHA256은 `5f542af96df705e567bf4cfb000398b09313db2456c577e772bd76481799cf29`다.

generate의 모델·입력·adapter 함수를 활용하되 새 task의 요청·protocol·평가 연결을 명시한다. 기존 lock_protocol의 존재하는 파일만 수집하는 경로는 필수 입력 잠금을 대신하지 못한다. 과거 학습 실행기나 사용하지 않는 continuation GPU 경로까지 정비하지 않는다.

# Proposed Experiment

## 0. 접근·자료 gate와 기존 분석 마무리

사용자에게 필요한 범위는 공식 Test DICOM과 `annotations_test.csv`, `image_labels_test.csv`의 프로젝트 내 이용 가능 여부다. credentialing·교육·DUA는 사용자가 필요한 절차를 완료해야 한다. 비밀번호·토큰을 보고서나 대화에 넣지 않는다. 기존 승인 사본이 있다면 새 접근 승인을 반복 요구하지 않는다.

실제 annotation을 확보하면 전체 class·결측·box 유효성·image_id 연결을 검사한다. test 합의 주석과 train 판독자별 주석을 혼합하지 않는다. annotation-only 감사에서 적격 수를 계산하고 이후 분할·요청 행렬을 고정한다.

기존 VinDr 10개 영상과 모든 기존 연구 입력의 ID·file/pixel hash·가능한 변환 중복을 검사한다. 안정된 환자 연결이 있으면 환자 단위로 분리한다. 없으면 영상 단위 분할과 bootstrap을 사용하고 환자 독립성은 미확인으로 명시한다. 사전학습 미노출을 주장하지 않는다.

동시에 저장된 C201/E402 원시 1,206건으로 iter_031의 층별·IoU≥0.5·center-in-GT·비용 분석을 `results/iter_032/closure031/`에 보완한다. 원래 결과와 판정은 유지하고 새 분석은 사후 개발 분석으로 표시한다. 후보 수를 맞춘 라운드 02 계산도 재현 가능한 형태로 남기되 통계적 우위로 승격하지 않는다. C/E GPU 생성은 하지 않는다.

## 1. 동작 확인

외부 eligible 집단은 P=Lung opacity 양성, A=해당 소견 음성이지만 다른 이상 주석 존재, N=No finding으로 나눈다. label과 box가 모순되는 행은 데이터 gate에서 해소한다.

사전 seed `32017`과 stable ID hash로 층별 순서를 고정한다. D는 P 8개·A 4개·N 4개, 총 16개 영상 또는 환자 cluster다. 두 모델×두 prompt로 정식 D 생성은 64요청이다. 크기·box 수·종횡비가 다양한 입력의 overlay와 형식 검사를 포함한다.

D에서 형식 통과율이 모델×prompt별 90% 미만이면 parser를 임의 구제하거나 E로 넘어가지 않는다. 형식·길이·입력 문제를 보고하고 본 가설은 미판정으로 둔다. 형식 보정이 필요하면 변경 내용과 영향을 새 계획으로 고정한다. 낮은 위치 성능 자체는 gate 실패로 사용하지 않는다.

동일 32개 D 요청을 2 worker와 4 worker로 비교한다. 실제 24요청의 통제된 중단·재개와 변조 거부도 수행한다. 검증 요청은 D에서만 가져오며 E/H를 실행 구성 선택에 쓰지 않는다.

## 2. 가능성 탐색

D를 제외한 각 층을 hash 순서로 development 60%, 보존 확인 H 40%로 나눈다. 연결 가능한 환자·중복 cluster는 통째로 배정한다. 이후 모델 성능에 따라 H 비율이나 포함 ID를 바꾸지 않는다.

E1은 development에서 P 40·A 20·N 20, 총 80개 단위이며 320요청이다. 먼저 B0 seed17과 M0만 평가한다. 필요한 층별 표본이 없으면 표본을 복제하거나 양성만의 다른 성공 기준으로 바꾸지 않고 자료 식별성 부족으로 보고한다.

E1에서 Δ, prompt별 차이, F1@0.5, recall, FP/음성 영상, invalid와 환자 또는 영상 paired CI를 계산한다. 두 prompt는 동일 단위 안에서 평균하고 독립 표본처럼 세지 않는다.

## 3. 규모 확대

E는 개발 평가이며 확대 판단에 사용한다. E1의 CI가 실질적 효과 경계인 +0.10 또는 −0.10을 포함하고 반폭이 0.05보다 클 때, 추가 표본이 결정을 바꿀 수 있는지 판단한다.

양성 단위의 paired 차이 표준편차 s로 목표 수 `ceil((1.96*s/0.05)^2)`를 계산한다. 목표는 최소 기존 40개이며, 확보한 development 양성 수와 두 음성 층의 가용량이 허용하는 범위로 제한한다. 음성은 각각 양성 수의 절반을 유지한다. 수치는 GPU 결과를 보기 전에 고정한 hash 순서의 prefix로 채운다.

계산한 수와 실제 가용량, 예상 CI 반폭·요청 수·wall-clock을 expansion decision에 기록한다. 가용 표본으로 예상 반폭을 0.10 이하로 줄일 수 없고 구체적 판단 변화도 기대되지 않으면 불확정으로 보류한다. 확대는 한 번이며 전체 E에서 한 번 최종 평가한다. 개발 CI를 순차 검정의 확증 p-value로 사용하지 않는다.

뚜렷한 양성·음성 근거가 이미 있으면 E를 불필요하게 늘리지 않고 아래 H 진입 조건을 판단한다. 동작 확인만으로 최대 표본·모든 seed를 실행하지 않는다.

## 4. 조건부 독립 확인

E에서 |Δ|≥0.10이고 95% CI가 0을 제외하며 두 prompt의 차이 방향이 같으면 H 확인 후보가 된다. 양성 방향은 음성 FP 증가의 해석이 확보돼야 한다. 한 prompt만의 개선 또는 invalid 차이로 설명되는 결과는 직접 전이 양성으로 확대하지 않는다.

H의 표본 수는 E의 분산으로 계산한 반폭 0.05 목표와 보존 가용량으로 정하되, H 출력은 그 계산에 사용하지 않는다. 예상 반폭이 0.10을 넘으면 독립 확인의 식별력 부족을 보고하고 H를 자동 소진하지 않는다.

H에서는 M0와 기존 SFT seed17/29/43을 같은 두 prompt로 비교한다. 따라서 H 영상당 8요청이다. 새 학습은 없다. 고정된 seed 평균 효과를 주지표로 삼고 각 seed 결과를 모두 보고한다. 세 seed만으로 학습 seed 모집단의 불확실성이 충분히 추정됐다고 주장하지 않는다.

H는 이번 로컬 선택에서 보존된 영상 집단이다. 환자 연결을 검증하지 못했으면 독립 환자 확인으로 표현하지 않는다. foundation model의 사전학습 미노출도 보장하지 않는다. H 이후 prompt·checkpoint를 바꾸면 새로운 독립 확인 근거가 필요하다.

## 자원·시간·재개

실행 직전에 `nvidia-smi`로 GPU 0/1의 실제 여유와 상속된 허용 집합을 확인한다. M0/B0 또는 독립 shard를 두 GPU에 배치하며 worker 수와 GPU 수를 분리한다.

이전 E804의 2006.4초는 약 24요청/분의 참고 실측이다. 외부 직접 생성은 별도 작업이므로 초기 예상은 전체 10–24요청/분으로 두고 D에서 교체한다. E1 320요청은 생성 약 13–32분, 외부 400개 단위의 4조건은 약 1.1–2.7시간, H 200개 단위의 8조건도 약 1.1–2.7시간이다. 이는 예시 산식이며 데이터 확보·전처리·검증·모델 로딩 시간은 별도로 보고한다. 임의 시간 상한은 없다.

추론 process peak는 기존 8–10GiB 참고값에서 시작하되 실제 긴 출력의 allocated/reserved 및 GPU 전체 점유를 측정한다. 동시 peak 합과 다른 작업 점유에 worker당 2GiB 여유를 더해 장치 용량 안에 들어야 한다. 4 worker가 처리량을 높이고 token 정합성·오류 조건을 유지하면 채택한다. 여유 부족이나 실측 이득 부재 시 2 worker를 사용하고 근거를 남긴다. batch 확대는 4 worker보다 유망한 근거가 있을 때 대안으로 짧게 비교한다.

생성 길이는 공통 1000→2000→4000 ladder를 유지한다. 전체 vocabulary score는 이번 과제에 필요하지 않으므로 보관하지 않는다. D에서 긴 decode 경로의 메모리를 확인하고 cap을 낮춰 정합성 문제를 피하지 않는다.

요청별 immutable ID, worker별 결과 파일, 원자적 claim과 부모 소유 lock을 사용한다. 중단 시 소유 자식만 종료·회수하고 exit code를 수집한다. 손상 tail은 보존 후 복구한다. 완료 요청도 입력·prompt·adapter·protocol을 다시 검증하며 completion은 예상 행렬과 모든 종료 상태가 맞을 때만 기록한다. 진행량·latency·오류·메모리를 주기적으로 남긴다.

# Implementation Tasks for Claude

1. 데이터 이용 권한·경로 답변과 실제 파일을 확인한다. 조건 미충족이면 외부 모델 실행을 시작하지 않는다.
2. 반입 파일과 승인 범위를 확인하고 현재 작업·lock·PID/starttime을 검사한다. 살아 있는 작업과 claim을 건드리지 않는다.
3. 저장 결과만으로 closure031을 작성한다. 기존 주수치와 사후 분석, 비용 추정의 한계를 구분한다.
4. 외부 자료 감사, 렌더링·좌표 fixture, 중복 검사와 D/E/H manifest를 구현한다. 실제 annotation 개수로 단계별 정확한 단위·요청 수를 출력한다.
5. 두 prompt와 전체 예상 행렬, model/adapter·입력·코드 digest, 단계 decision을 잠근다. 사용하지 않는 과거 pipeline을 정비하지 않는다.
6. D의 공식 입력·adapter·길이·재개·변조·처리량 검사를 완료한다. gate 결과를 launcher와 직접 worker 진입점 모두에서 강제한다.
7. E1 및 사전 조건에 따른 단일 E 확대·H 확인을 실행한다. 생략 단계의 이유도 기록한다.
8. 원시 출력과 독립 matching·paired 통계 재계산을 연결한 보고서를 작성한다. 실행 유효성, 성능 차이, 가설 지지, 신규 기여 가능성을 따로 보고한다. 소스 보존·커밋 관리는 orchestrator에 맡긴다.

# Evaluation (성공/실패 기준 포함)

주지표는 양성 단위의 두 prompt 평균 F1@0.3 차이다. 보조 지표는 prompt별 절대 F1@0.3·F1@0.5, recall, 빈 출력률, A/N 각각의 FP/영상, invalid, 생성 시간·token·peak 메모리다. 낮은 M0 clean 성능에 따른 floor effect 때문에 상대 하락률로 비교하지 않는다.

환자 연결이 있으면 환자 cluster, 없으면 영상 단위 paired bootstrap 10,000회를 사용한다. invalid 출력은 양성 주지표에서 0으로 처리한다. FP는 valid-only와 전체 집단 기준 하한을 구분하고 invalid 자체를 별도 불이익으로 보고한다. 두 prompt 모두 유효한 쌍에 대한 보조 분석을 추가하되 이를 주분모로 대체하지 않는다.

- **양성:** H의 고정 seed 평균 Δ≥0.10, 95% CI 하한>0, 두 prompt 방향 일치. A/N 각각에서 추가 FP/영상의 95% CI 상한≤0.10이고 invalid 증가가 2 percentage points 이내여야 'FP 비용을 통제한 전이 이득'이라고 한다. 비용 조건을 충족하지 못하면 위치 이득과 부작용의 tradeoff로 보고한다. 다음에는 이 baseline을 유지하며 실제로 해결할 잔여 실패가 있는지 검토한다.
- **음성:** 정상 사용 gate 이후 H의 평균 Δ≤−0.10, CI 상한<0이고 prompt·seed별 방향이 일관되면 해당 외부 target에서 직접 SFT 활용을 보류한다. 원천·target 변화 중 원인을 확정하지 않는다. 후속 후보는 외부 target 직접 SFT와 모듈형 대안의 데이터 효율 비교이며 자동 학습은 하지 않는다.
- **실질적 차이 제한:** 충분한 정밀도의 CI가 [−0.10,+0.10] 안에 있으면 큰 전이 이득·손실의 근거가 약하다고 보고한다. 이것만으로 신규 방법을 만들 이유는 없다.
- **불확정:** CI가 투자 경계를 가로지르거나 prompt·seed·형식에 따라 결론이 갈리면 해당 범위를 명시한다. 사전 E 확대만 허용하고 H 결과를 보고 표본·조건을 바꾸지 않는다. 새로운 식별 근거 없이 prompt·loss 탐색을 반복하지 않는다.
- **실행 실패 또는 자료 보류:** 권한·좌표·입력 연결·완전성 gate를 충족하지 못하면 성능 가설을 판정하지 않는다. CPU 준비 완료를 유효한 실제 출력 진단이나 validated 승격으로 세지 않는다.

이번 diagnostic의 성공은 해석 가능한 전이 판단을 얻는 것이다. 양성 결과, 구현 성공, 새로운 방법의 기여와 최종 GOAL 달성을 같은 성공으로 묶지 않는다.

# Risks / Checks

- 가장 큰 현재 blocker는 공식 자료 이용 가능 여부다. 이는 GPU 재승인 문제가 아니다. 기존 권한을 확인하면 그 범위에서 진행한다.
- Lung opacity와 pneumonia-suspicious opacity의 target 차이를 모든 요약에 유지한다. Pneumonia 양성 subgroup도 원인 병변 box 정답을 제공하지 않는다.
- 영상 ID를 환자 ID로 오해하지 않는다. dedup 성공과 사전학습 미노출도 구분한다.
- 공식 template·정확한 좌표·충분한 출력 길이로도 남는 실제 오류와 format 차이를 따로 보고한다.
- 희귀·작은·복수 병변을 편의상 제외하지 않는다. 개발 자료에서 정한 크기·box 수 층별 결과를 보조 보고하되 주가설을 사후 교체하지 않는다.
- 기존 결과·protocol·report는 덮어쓰지 않는다. 접근법 종료는 코드 폐기나 과거 success 정정이 아니다.
- 외부 자료가 없다는 이유로 합성 배치·QA·사분면·continuation 실험을 자동 재개하지 않는다.

## 대규모 GPU 필요 후보

기관·소견별 annotation 의미를 정렬한 다기관 자료에서 vision encoder와 언어 모델을 공동 적응시키고 grounding·일반 질의 유지·입력 안정성을 함께 평가하는 post-training을 보존한다. 규모와 신규성은 미확정이며 이번에는 실행하지 않는다.

# 계획의 근거 (GPT 조사 노트)

## 이번 라운드의 결론

추천 방향은 VinDr-CXR의 Lung opacity에 대한 기존 RSNA SFT 전이 진단이다. 실행 계획은 구체화했지만 필요한 공식 자료의 이용 권한과 위치가 확인되지 않아 데이터 접근에 관한 사용자 답변이 필요하다. 이번 라운드에서는 파일·공개 문서·보존 Git blob만 읽었다. 파일 생성·수정, 다운로드 스크립트 실행, 모델 로딩과 GPU 실험은 하지 않았다.

## 질문 1: 무엇이 확보됐고 무엇을 요청해야 하는가?

로컬 `legacy/eval_samples/not_in_training/vindr_cxr/meta.json`의 고유 영상은 10개이며 Lung Opacity box 2개, Consolidation 2개가 있다. 원래 스크립트는 `sunday-hao/vindr-cxr-testset`에서 이상 class별 첫 영상을 선택했다. 대표 외부 평가 집단이 아니다. 스크립트에 인증 파일을 읽는 코드가 있지만 실행하거나 인증 내용을 열지 않았다. mirror의 dataset card/API 조회 실패는 계정 접근 불가의 증거가 아니다.

`research/results`와 `legacy/eval_samples`의 파일명 검색에서 추가 VinDr annotation 또는 CheXlocalize GT segmentation 파일을 찾지 못했다. 이는 해당 검색 범위의 결과이며 다른 저장소나 사용자 계정에 자료가 없다는 뜻은 아니다.

VinDr 공식 설명에서 필요한 파일은 `annotations_test.csv`, `image_labels_test.csv`, 이에 대응하는 Test DICOM이다. 공식 파일 접근에는 credentialing·지정 교육·DUA가 필요하다. 따라서 사용자가 이미 이용 가능한 사본과 권한을 보유했는지 확인하고, 없다면 공식 접근 절차를 진행할지 결정받는다. [VinDr-CXR 공식 자료](https://physionet.org/content/vindr-cxr/1.0.0/)

CheXlocalize는 대안으로 유지한다. 공식 안내는 StanfordAIMI 로그인·등록·약관 동의를 요구하며, 기존 CheXpert 영상 보유가 segmentation 확보를 뜻하지 않는다. mask를 병변 instance box로 바꾸는 추가 가정도 필요해 이번에는 직접 box 주석이 있는 VinDr를 우선한다. [CheXlocalize 다운로드 안내](https://raw.githubusercontent.com/rajpurkarlab/cheXlocalize/master/download_instructions.md), [자료 구조](https://github.com/rajpurkarlab/cheXlocalize)

## 질문 2: 정답이 보장되는 평가 범위는 무엇인가?

VinDr의 Lung opacity는 local finding이고 Pneumonia는 global diagnosis다. pneumonia 양성 영상의 모든 opacity box를 pneumonia 원인 병변으로 대응시킬 수 없다. 이번 target은 명시적으로 VinDr의 Lung opacity 주석이다. Consolidation·Infiltration을 사후 합치거나 RSNA target과 동등하다고 취급하지 않는다.

M0와 B0 모두 같은 넓은 target을 요청받는다. 따라서 비교는 'RSNA 적응 후 외부·확장 target에서 얻는 이득'이다. 음성 결과만으로 순수한 기관 일반화 실패, 시각적 forgetting 또는 일반적 공간 능력 부재를 주장하지 않는다. 기존 좁은 RSNA prompt의 결과를 넓은 GT로 채점해 같은 과제의 정답률로 표시하지 않는다.

공식 설명상 image_id는 SOP Instance UID 기반이며 환자 ID는 비식별화 과정에서 제거된다. 안정된 환자 연결을 추가로 확인하지 못하면 독립 단위는 영상이고 환자 독립성을 주장할 수 없다. 이 점을 데이터 gate와 CI 해석에 반영한다.

## 질문 3: 결과가 바꿀 투자 결정

- 양성: 직접 SFT를 외부 전이 baseline으로 유지한다. 새 loss의 필요성을 주장하지 않고, 이후 방법이 넘어야 할 성능·FP·비용 기준을 확보한다.
- 음성: 해당 target 이동에서의 직접 SFT 활용을 보류한다. 정상 사용과 두 고정 prompt에서 재현되는 경우에만 외부 target 직접 SFT 및 모듈형 대안의 데이터 효율 비교를 후속 후보로 검토한다. domain과 target의 원인은 이번 결과만으로 분리되지 않는다.
- 불확정: paired 정밀도가 판단을 바꿀 때만 사전 정한 범위로 확대한다. 이용 가능한 표본으로도 부족하면 제한된 결과로 종료한다.

외부 점수 추가 자체는 신규 contribution이 아니다. 이번 선택은 현재 checkpoint를 계속 투자할 출발점으로 삼을지 결정하는 진단이다. continuation·순서 설명과 Pix2Seq의 중복, 합성 배치 변화에 대한 정확한 재중앙화 대안, CURE·MedFM-Robust 관련 판단은 라운드 01–03을 유지한다. 해당 문헌을 이번에 다시 검색하거나 새 추천으로 제시하지 않았다.

## 실제 재사용 확인

research HEAD는 `8dad463392de9bb0e9fe7d93d64b9c374492de9b`이며 status/diff는 비어 있다. reuse_assets의 11개 파일은 모두 해당 SHA의 일반 blob이고 현재 파일과 같다. 새 기반으로 지정한 iter_006의 전체 SHA는 `68117cfd08429ffc3cb9b77e14fb1db3221d86ab`이며 반입 경로 충돌이 없다.

iter_012의 seed17/29/43 `lr2e-4`·`epoch_05/adapter.pt` 존재와 `final/confirm_result.json`의 선택 정보를 확인했다. B0 파일 SHA256은 라운드 01에서 검증한 `5f542af96df705e567bf4cfb000398b09313db2456c577e772bd76481799cf29`를 사용하며, 실제 실행 시 다시 검증한다. 모델 revision은 기존 `91850547d9f0b2fdd21aa7c5f4f3d1a8a52c243b`를 유지한다.

`agent/GOAL.md`, 정책 문서, LIMITATIONS, CODE_ASSETS, iter_009·012 원본 review.json, iter_031 원본 리뷰를 대조했다. 기존 validated 범위와 외부 전이의 미검증 상태를 구분한다. 사용자 보완에 따라 완료된 QA·사분면 진단을 반복하지 않고 MRI F139·reserve·longitudinal은 보존한다.

## 대규모 GPU 필요 후보

여러 기관·소견의 annotation 범위를 정렬한 뒤 vision encoder와 언어 모델을 공동 적응시키는 post-training은 후보로 보존한다. 충분한 해상도·seed·외부 확인까지 포함한 자원 필요성과 신규성은 미확정이다. 현재 두 GPU의 경량 적응 가능성을 배제하지 않는다.

이전 사고 라운드 노트: agent/runs/iter_032/think/
