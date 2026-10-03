# 사고 라운드 3

# 핵심 판단

**기존 grounding 자산에서 데이터 효율·능력 보존 방법으로 바로 진입하지 않는다.** 실제 적응 효과는 확인됐지만, 이번에 읽은 원 리뷰는 강한 단순 대안 이후의 중요한 보존 손상이나 annotation budget 병목을 입증하지 않았다. 이는 경량 적응 전체의 가치 부족이라는 판단이 아니다.

다음 후보를 **시간 비교에서 판독 불가능과 실제 불변을 구분하는 문제**로 좁혔다. 단순 longitudinal benchmark 점수나 영상 순서 일관성을 다시 측정하는 제안은 제외한다. 현재는 정답 의미와 공개 schema의 대응이 미확인이라 구현을 발주하지 않는다. 남은 판단은 전략 전반이 아닌 이 후보의 실행 gate이므로 다음 등급은 medium이다.

# 직전 질문에 대한 답

## 1. 기존 적응 결과에 데이터 효율·보존 방법의 실제 근거가 남는가?

`agent/runs/iter_012/review.md`, `iter_014/review.md`, `iter_016/review.md`, `iter_042/review.md`, `iter_048/review.md`와 각 review.json의 valid_experiment·blocking_issues·failure_scope를 확인했다. 해당 리뷰들은 유효한 실제 비교이며 blocking_issues는 비어 있다. 그러나 방법 pilot의 형식적 진입 가능성과 이번 후보의 과학적 투자 가치는 구분한다.

- **iter_012:** train 2,400명, 네 trajectory 각각 750 steps·12,000 presentations를 실행했다. 확인 양성400명의 직접 SFT F1@0.3은 세 seed에서 0.631–0.653이다. 이는 충분한 실제 적응 효과다. 여러 annotation budget의 학습 곡선이 아니므로 데이터 비효율의 증거로 사용할 수 없다. 마지막 epoch 선택과 잔여 위치 오류도 새로운 보존 방법의 필요성을 직접 입증하지 않는다.
- **iter_014:** full-train G−U S_loc은 +0.00125, 최종 G−C는 −0.02583이었다. 현 G 설계의 투자 중단을 유지한다. 작은 데이터에서 학습이 불가능하거나 모든 기하 supervision이 무효라는 결론은 아니다.
- **iter_016:** B0−M0 S_scope 차이는 strict −0.255에서 semantic −0.0317로 줄었다. opacity/Normal/NoOpacity의 변화가 상쇄되므로 완전한 보존을 주장할 수는 없다. 반대로 큰 strict 저하를 시각적 forgetting의 증거로 다시 사용하지 않는다.
- **iter_042:** presence gate 이후 음성 nonempty는 1/40이었다. C_neutral과 P0 gate의 양성 환자별 F1은 동일했다. C_short 대비 보존 CI가 넓다는 사실은 단순 대안의 구체적 실패와 다르다. 원 계획의 투자 보류를 유지한다.
- **iter_048:** 공동 직접 SFT는 공동 F1을 E 0.333116에서 J 0.523251로 회복했다. J의 독립 F1은 0.590476이며 적응 MedGrounder A는 0.594444였다. 잔여 공동 손실 0.067225는 유효하지만 기존 정확도·비용 판단을 뒤집는 새 근거는 아니다.

`agent/LIMITATIONS.md`의 관련 항목도 확인했다. validated RSNA grounding 한계를 일반적인 데이터 비효율·forgetting 주장으로 바꾸지 않는다. 기존 observed 상태와 미해결 질문을 유지한다. 위 수치는 원 리뷰의 검증을 인용했으며 이번에 원시 모델 출력을 재계산한 것은 아니다.

## 2. 기존 자산에서 최소 개입과 강한 대조가 구체화되는가?

현재는 아니다. replay·distillation·adapter routing을 도입할 수 있다는 사실만으로 개입 대상을 확보한 것이 되지 않는다. 가까운 선행에는 semantic adapter와 memory consolidation을 사용하는 [MedPEFT-CL](https://arxiv.org/abs/2511.17668), routed expert를 다루는 [Sparse Spectral LoRA](https://arxiv.org/abs/2604.01310)가 있다. 이번에는 공식 초록 수준에서 관계를 확인했으며 구현 동등성이나 재현 성능을 검증하지 않았다.

이 문헌들이 모든 새 방법을 배제한다는 뜻은 아니다. 기존 관찰을 일반적인 보존 손상으로 재해석하고 이미 알려진 adapter 구성을 붙이는 경로에는 현재 투자 근거가 부족하다는 판단이다. annotation budget 곡선만 새로 만드는 실험도 구별할 방법 가설 없이 발주하지 않는다.

## 3. 다른 사용 과제 중 무엇을 우선하는가?

**이전 검사와 현재 검사를 비교할 때, 비교 근거 부족을 실제 불변으로 오인하지 않는 능력**을 우선 후보로 선정했다. 원천 전문가 판정과 실제 연속 영상이 있고, 단일 영상 품질 문제와 pair 비교 문제를 분리할 가능성이 있기 때문이다. 새로운 한계가 관찰됐다는 뜻은 아니다.

`agent/runs/iter_022/plan.md`를 읽었다. 당시 temporal 후보는 CheXpert Plus 자료 접근이 미확인이라 실행하지 않았다. 또한 시간순 정규화만으로 얻는 일관성을 기여로 삼지 않도록 이미 경고했다. 이번에도 이 교훈을 유지한다. iter_022의 미실행을 가설 실패로 세지 않으며, 새 후보를 시간 비교 연구의 첫 시도처럼 기록하지 않는다.

# 새로 확인한 자료와 가까운 선행

## MARIO: 실제 연속 OCT 비교 자료

[공식 저장소](https://github.com/YouvenZ/MARIO-Challenge-MICCAI-2024)는 Task 1을 연속 검사에서 얻은 두 B-scan의 변화 판정으로 정의하고, 현재 [Zenodo 공개 배포](https://zenodo.org/records/15270469)를 연결한다. 과거 challenge 등록 절차와 현재 공개 배포 경로를 구분해야 한다. 공개 record는 Task 1/2 multipart archive와 train/val/test CSV 구조를 설명한다. 전체 배포는 21.8 GB다. 실제 archive 내부·이용 조건 원문·환자별 split을 아직 검증하지 않았다.

[공식 논문 §4](https://arxiv.org/html/2506.02976v1)는 136명의 자료, 원 주석 Uninterpretable 2,303쌍과 Appeared and Eliminated 9쌍을 설명한다. 축약 Other는 2,312쌍으로 둘을 합친다. 따라서 Other 전체를 단순한 영상 품질 불량의 정답으로 쓰면 안 된다. 약 10%의 연속 획득에서 follow-up mode 누락에 따른 registration 문제가 있었다고 기술하지만, 이것이 각 Uninterpretable 사례의 원인을 표시한 annotation이라는 뜻은 아니다. 판독자는 인접 slice를 볼 수 있었으므로 단일 B-scan 입력과 정답 근거의 범위도 확인해야 한다.

공식 [Task 1 제출 규약](https://raw.githubusercontent.com/YouvenZ/MARIO-Challenge-MICCAI-2024/main/Task%201/README.md)은 prediction 0~3을 요구한다. 논문의 −1/0/1/2와 실제 CSV code의 대응은 이번 조회에서 확인하지 못했다. 이 불일치는 단순 표기 차이일 수 있지만 추측으로 해결하지 않는다.

## 기존 temporal RAG와의 구별

[TrajRAG 공식 논문 페이지](https://papers.miccai.org/miccai-2026-sat/MedAgent_010.html)는 MARIO·OLIVES의 longitudinal retrieval과 calibration을 이미 다룬다. 초록은 retrieved-label copying을 별도 대조로 확인했다고 설명한다. 따라서 retrieval bank를 추가하거나 낮은 temporal 점수·confidence 오류를 재측정하는 것만으로는 충분한 새 질문이 아니다. PDF 본문 조회는 도구 오류로 실패했으므로, 판독 불가능 사례와 품질 gate를 실제로 평가했는지는 아직 확인하지 못했다.

[공개 Siamese 비교 구현](https://github.com/EmreTaha/Siamese-EMD-for-AMD-Change)과 [fusion CNN 구현](https://github.com/pzhangwj/mario_challenge_code)도 확인했다. 후자는 checkpoint 미포함을 명시한다. 전용 비교군이 존재하므로 zero-shot VLM만 비교해 일반적인 해결책 필요성을 주장하지 않는다. 실제 재현에는 checkpoint 확보 또는 동일 annotation으로 학습하는 비용을 포함해야 한다.

OLIVES도 검토했지만 이번 후보의 우선 자료로 선택하지 않았다. [공식 설명](https://github.com/olivesgatech/OLIVES_Dataset)은 biomarker 주석이 있는 9,408장과 전체 clinical metadata를 구분한다. endpoint biomarker 차이를 임의로 임상적 악화·호전으로 바꾸는 별도 정답 설계를 추가할 이유가 없다.

# Strategy Check / 연구 방향 판단

1. **기존 적응 방법 개선:** 실제 SFT 자산은 가치가 있지만 데이터 효율·보존의 구체적 잔여 문제는 이번 원문 확인으로 확보하지 못했다. 추가 loss·routing·replay 투자는 보류한다.
2. **기존 주변 진단 연장:** 이미 반복 사용한 RSNA·PadChest·MediConfusion 자료의 prompt·seed·budget 확대는 새 투자 선택을 구별할 근거가 약하다. 기존 보류 범위를 유지한다.
3. **시간 비교의 근거 충분성:** 실제 판독 불가능 annotation과 강한 pair 모델이 있어 판별력 있는 비교를 구성할 가능성이 있다. 다만 label 의미가 결정적이므로 이를 확인한 뒤에만 실행한다.

선택은 3의 한정 진입 검토다. 해결된 질문은 기존 결과를 일반적 forgetting이나 데이터 비효율로 재포장할 수 없다는 점이다. 남은 질문은 판독 불가능 정답의 식별성, 단순 품질·confidence 대안 이후의 비교 가능성이다. 이 후보가 성립하지 않으면 새 데이터셋 이름으로 같은 진단을 계속하지 않는다.

가능한 후속 기여는 같은 오류 수준의 coverage 개선 또는 같은 coverage의 부적절한 확정 감소다. 이를 입증하려면 직접 SFT·거부 supervision·encoder+head보다 나은 결과가 필요하다. 모델이 자주 틀리거나 거부한다는 관찰만으로 method pilot을 승인하지 않는다.

# 조회 실패와 다음 확인 범위

공식 GitHub 일부 directory/API, Zenodo API 및 TrajRAG PDF의 웹 조회가 실패했다. 읽기 전용 Python의 공식 API 조회도 DNS 오류였다. 이를 자료 자체가 비공개이거나 구현 환경에서 설치 불가능하다는 근거로 사용하지 않는다.

다음 라운드는 광범위한 후보 검색을 반복하지 않는다. 공식 배포의 readme·CSV schema 또는 공개 loader에서 label mapping과 patient/eye/visit 연결을 확인하고, TrajRAG 본문에서 겹치는 비교 범위를 확인한다. label 정의에 따라 실험의 정답·비교군·독립 단위가 달라지므로 현재 불완전한 계획을 Claude에게 넘기지 않는다.

# 보존·권한·자산

현재 research의 `git status --short`는 비어 있다. 새 실행 경로가 확정되지 않아 반입 모듈을 지정하거나 기존 checkpoint 재사용을 승인하지 않았다. 이미 완료한 iter_050 인계·감사는 round_01의 원문 확인 범위를 유지하며 반복하지 않는다. 현재 구현 담당은 Claude다.

기존 한계 상태, 계획·리뷰·checkpoint·reserve를 변경하지 않았다. 파일 생성·수정·설치·실험은 수행하지 않았다. 실행이 결정되면 두 GPU의 batch 또는 복수 worker 처리량과 메모리를 실제 입력으로 비교하며, OCT pair 비용을 기존 단일 영상 scoring 시간으로 대신 추정하지 않는다.

# 대규모 GPU 필요 후보

다기관 longitudinal volume과 판독 가능성 annotation을 함께 사용하는 encoder–projector–decoder 공동 적응을 장기 후보로 남긴다. 현재 그 필요성이나 우위를 확인한 것은 아니며, 두 RTX 3090에서 가능한 직접 SFT·pair head·경량 개입보다 우선하지 않는다.

이번 문헌 확인은 조사 기록이며 사용자 논문 추천이 아니다.

## 다음에 파고들 질문
- MARIO 공개 Task 1의 CSV code 0~3은 원 주석과 어떻게 대응하며, Uninterpretable과 복합 변화 Other를 분리할 수 있는가? 공식 archive readme·CSV schema·공개 loader를 확인하고, 분리 불가능하면 판독 불가능 진단 후보를 보류한다.
- 환자·eye·방문·pair ID와 annotator별 label이 공개 자료에 남아 있는가? 인접 slice를 보며 작성한 정답과 입력 범위를 맞출 수 있는지 확인해 독립 분석 단위·자료 규모를 확정한다.
- TrajRAG와 MARIO의 강한 pair 모델이 이미 판독 불가능–불변 혼동 및 품질·confidence gate를 비교했는가? 원문과 실행 경로를 확인해 차별화된 한정 diagnostic·후속 직접 SFT 대조가 성립하는지 결정한다.
