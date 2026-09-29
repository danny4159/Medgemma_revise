# 사고 라운드 2

## 핵심 판단

현재 단일 continuation 설계의 추가 방법 투자는 종료하는 쪽이 타당하다. 상보적인 후보는 존재하지만 중복 제거만으로 FP 비용이 해결되지 않고, 후보 수를 맞춘 비교에서도 일관된 우위가 없다. 출력 순서와 회복의 연관은 확인했으나 그 설명 자체도 Pix2Seq와 겹친다.

전환 후보는 기존 RSNA checkpoint의 입력 변화에 대한 적응 안정성이다. 다만 이번에 확인한 MedFM-Robust가 MedGemma 1.5의 LoRA grounding과 기하·해상도 관련 perturbation을 이미 평가하므로, 단순 robustness benchmark로 바로 진행하지 않는다. 정보 손실과 좌표계 변화, 적응 효과를 분리하는 최소 질문이 가능한지 한 라운드 더 확인한다.

이번 작업은 문서·소스·웹 조회와 저장 출력의 읽기 전용 재계산이다. 파일 생성·수정, 모델 로딩, GPU 추론·학습은 수행하지 않았다.

## 기존 기록과 사용자 보완의 적용

라운드 01의 조사 기록을 이어받고 iter_031 원본 리뷰, iter_030·031 계획의 관련 기준, LIMITATIONS와 CODE_ASSETS의 현재 범위를 대조했다.

- 유지: iter_012 직접 LoRA SFT의 유효한 검출 개선, checkpoint·원시 출력·기존 판정.
- 이미 답한 것: QA 형식 효과, evidence 전달 효과, 현재 사분면 선택에서 규칙 baseline의 우위, 빈 출력 entropy와 nonempty continuation의 제한적 회복.
- 미해결: 일반적인 공간 능력 전이, 사분면 oracle의 원인, 후보 선택의 실용성, 외부 일반화.
- 보류: QA·사분면 재탐색, 새 head/loss·학습, iter_022 longitudinal, MRI F139, 기존 reserve.
- 변경: continuation 후보의 추가 생성보다 기존 적응이 다른 입력 조건에서도 유효한지 조사하는 방향을 우선 비교한다. 사용자 능력 전이 지시를 아직 수행하지 않은 과제로 되돌리지 않는다.

`lesion-grounding-generalization`의 validated 범위는 유지한다. 순서 편향과 적응 안정성은 새 후보 설명이며, 기존 validated 상태를 자동 상속하지 않는다.

## 질문 1의 답: 순서와 회복의 연관은 있지만 인과 설명은 미확정

학습 소스 `783d2d04671ae296f3dc0c700e575f8af8e021c9:rsna_diag/sft_data.py::target_boxes`를 재확인했다. 반올림한 GT를 중심 x, 중심 y, 좌표 순으로 정렬한다. 이번에는 해당 사실을 반복 조사한 것이 아니라 실제 출력과 누락 위치를 연결했다.

입력은 `research/results/iter_030/source_audit.json`과 `research/results/iter_031/{C201,E402}/attempt1/gen_worker*.jsonl`이다. 총 1,206개 record의 ID×task 중복과 개수를 검사했다. 저장 tokenizer vocabulary로 JSON을 해석하고 O가 audit의 seed17 bbox와 같으며 F의 기존 bbox prefix가 보존되는지 확인했다. 별도 최대 cardinality matching으로 원래 추가 TP·FP와 F1 차이를 재현했다.

| 관찰 | C201 | E402 |
|---|---:|---:|
| 원래 O 목록의 중심 x 순서 유지 | 201/201 | 402/402 |
| F 전체 목록의 중심 x 순서 유지 | 147/201 | 305/402 |
| 마지막 O보다 앞쪽인 추가 후보 | 56 | 109 |
| 마지막 O보다 뒤쪽인 추가 후보 | 158 | 322 |

엄격한 부분 누락 사건에 속한 완전 비중첩 GT만 따로 보면 다음과 같다. 분모는 환자가 아닌 GT box이며 한 환자에 여러 GT가 있을 수 있다.

| 누락 GT 위치 | C 회복/GT | E 회복/GT |
|---|---:|---:|
| 마지막 O보다 앞쪽 | 1/10 | 0/13 |
| 마지막 O보다 뒤쪽 | 7/11 | 11/16 |

현재 관찰은 순서 관련 실패 설명과 부합한다. 그러나 병변의 크기·좌우 분포·검출 난도와 위치가 함께 달라질 수 있어 학습 순서의 인과 효과로 해석하지 않는다. F에는 순서를 어기는 후보도 상당수 있으므로 모델이 앞쪽 좌표를 전혀 생성할 수 없다는 결론도 틀리다.

전체 nonempty 집단의 완전 비중첩 GT를 포함하면 C 앞/뒤는 13/11개, E는 22/21개다. 이 집계에는 TP가 없는 환자도 포함되므로 엄격한 사건 분석과 섞지 않는다.

## 질문 2의 답: 후보 상보성은 남지만 후보 수 대비 우위는 약하다

GT 없이 적용하는 탐색 규칙을 모든 후보원에 동일하게 사용했다. O를 고정하고 후보를 원래 출력 순서로 순회하며, O 또는 이미 채택한 후보와 IoU≥0.5이면 제거했다. seed 합집합의 순서는 seed29 다음 seed43이다. 이는 confidence 순위가 없는 결정적 중복 제거이며 최적 NMS라고 부르지 않는다.

| 집단·후보원 | 남은 추가 후보 | TP 순증가 | FP 순증가 | 엄격한 사건 회복 | 평균 F1@0.3 변화 |
|---|---:|---:|---:|---:|---:|
| C continuation | 194 | 14 | 180 | 8/20 | −0.121109 |
| C seed29 | 34 | 1 | 33 | 0/20 | −0.026036 |
| C seed43 | 34 | 4 | 30 | 1/20 | −0.013765 |
| C seed29+43 | 61 | 5 | 56 | 1/20 | −0.033002 |
| E continuation | 397 | 14 | 383 | 11/27 | −0.139173 |
| E seed29 | 77 | 12 | 65 | 7/27 | −0.013847 |
| E seed43 | 70 | 7 | 63 | 4/27 | −0.014760 |
| E seed29+43 | 122 | 15 | 107 | 8/27 | −0.024461 |

E continuation의 원래 FP 순증가 417개 중 이 규칙이 제거한 것은 34개다. 중복만 제거하면 문제가 해결된다는 설명은 지지되지 않는다. seed 합집합 역시 F1을 개선하지 못하므로 실용적 해법으로 승인하지 않는다.

추가로 중복 제거 후 환자당 첫 후보 하나만 유지했다. 그 후보들을 전체 집단에서 균일하게 비복원 선택하여 같은 개수만 채택할 때의 기대값을 계산했다. C의 공통 예산은 32개, E는 61개다. 환자당 후보가 하나이므로 TP·FP·사건 회복의 기대값은 각 합계에 예산/후보수를 곱해 정확히 구할 수 있다. 실제 sampling 실행이나 통계적 CI가 아니다.

| 집단·동일 후보 예산 | continuation 기대 TP/FP/회복 사건 | seed29 기대 TP/FP/회복 사건 | seed43 기대 TP/FP/회복 사건 |
|---|---|---|---|
| C, 32개 | 2.27 / 29.73 / 1.40 | 1.00 / 31.00 / 0.00 | 4.00 / 28.00 / 1.00 |
| E, 61개 | 2.31 / 58.69 / 1.82 | 8.97 / 52.03 / 6.28 | 7.00 / 54.00 / 4.00 |

이는 continuation의 큰 원시 회복 수를 후보 수와 분리해야 한다는 근거다. C/E 간 차이가 있고 사후 탐색이므로 일반적인 열등성이나 통계적 우위를 확정하지 않는다. 라운드 01의 E에서 continuation만 회복한 9사건도 그대로 유지된다.

이 비교가 맞춘 것은 채택 후보 수다. 실제 생성 비용은 맞추지 않았다. seed29/43에는 추가 adapter 학습과 별도 추론이 필요하고 continuation은 같은 B0를 사용한다. 저장 로그의 서로 다른 실행 조건을 동일 wall-clock으로 간주할 수 없다. 배포 비용 우위를 주장하려면 같은 B0의 sampling 및 실제 prefix 재사용 비용을 통제해야 하지만, 현재 근거로 그 GPU 비교를 우선 투자할 필요는 낮다.

## 질문 3의 답: 종료·순서·sampling 설명은 가까운 선행과 직접 겹친다

[Pix2Seq v2의 §2.3, §3.3, Appendix C](https://arxiv.org/html/2109.10852v2)를 확인했다. 이전 라운드의 종료 지연 설명에 더해 이번에는 순서 ablation과 sampling 부분을 읽었다. 해당 논문은 고정 순서에서 앞서 놓친 객체를 나중에 회복하기 어렵다는 설명, random ordering의 이점, nucleus sampling의 recall 개선을 이미 다룬다.

따라서 현재 관찰만으로 random-order SFT, 종료 완화, 추가 생성 후 filtering을 새로운 방법으로 예약하지 않는다. MedGemma의 의료 JSON 출력과 차이는 있지만 적용 대상 차이만으로 contribution이 생기지는 않는다. 현재 설계 투자를 종료할 수 있으며, 이것은 RSNA SFT 전체나 모든 후보 선택 방법의 기각이 아니다.

## 질문 4의 답: 입력 변화 진단을 잠정 우선하되 새로운 선행 중복을 해결해야 한다

### 동일 opacity 외부 확인

외부 일반화는 중요하지만 현재 continuation을 그대로 외부에 반복할 근거는 약하다. iter_028의 자료 점검상 로컬 VinDr는 10개 영상뿐이고 target 대응·접근 권한은 미확정이다. NIH는 RSNA 원천과 연결돼 외부 기관 대조로 대체할 수 없다. 이번에도 credentialed 접근 가능성은 확인하지 않았다. 일부 공식 페이지 추가 조회는 실패했으므로 새로운 접근 상태를 주장하지 않는다.

[CURE의 §7.4와 §9.2](https://arxiv.org/html/2601.15408v1)는 외부 VinDr 평가와 bbox-aware augmentation을 이미 다룬다. 이번 재확인은 외부 점수 추가나 통상적인 공간 증강만으로 차별성이 생기는지를 판단하기 위한 것이었다.

### 입력 변화에 대한 적응 안정성

이번에 [MedFM-Robust 원문](https://arxiv.org/html/2605.19027v1)과 [MICCAI 2026 공식 페이지](https://papers.miccai.org/miccai-2026/0633-Paper2490.html)를 확인했다. 이 연구는 MedGemma 1.5를 포함하고 scaling·translation·pixelation 등의 변화를 평가한다. 논문 §2.2는 grounding에 vision encoder attention LoRA를 사용한다고 기술한다. 우리 자산의 언어층 LoRA와 학습 위치가 다르다.

논문은 MeCoVQA grounding에서 MedGemma 1.5의 Acc@IoU≥0.5가 69.2%에서 29.0%로 낮아졌다고 보고한다. 이는 우리 RSNA F1과 직접 비교할 수 없다. 또한 full FT 대비 LoRA의 전반적 순위를 우리 언어층 적응의 인과 결론으로 옮겨서는 안 된다. [공식 repository](https://github.com/AbnerAI/MedFM-Robust)의 README까지 확인했으며, 실제 VLM 학습·변환 구현과 결과 연결은 아직 검토하지 않았다.

새로 남길 질문은 광범위한 corruption 점수표가 아니다. 동일 병변 정보를 유지한 좌표계·배치 변화에서 SFT의 검출 이득이 유지되는지, 실패한다면 정보 손실과 출력 좌표 prior를 구분할 수 있는지가 후보이다. 실제 실패는 아직 관찰하지 않았다.

로컬 고정 revision의 `preprocessor_config.json`은 896×896 resize와 `do_pan_and_scan=null`을 기록한다. `generate.load_image`는 값 보존 RGB와 정사각 padding을 사용한다. 따라서 원본 파일의 해상도 변경이 그대로 모델 입력 해상도 변경이라고 볼 수 없다. padding 변형도 processor 이후 병변 크기와 보간을 함께 바꿀 수 있어 tensor 수준의 대조 설계가 필요하다.

단순히 언어층 LoRA라는 차이만으로 신규성을 주장하지 않는다. M0는 원래 grounding 점수가 낮으므로 clean 대비 하락폭이 작다는 이유로 더 robust하다고 판단하는 floor effect도 피해야 한다.

## Strategy Check / 연구 방향 판단

1. **RSNA 입력 변화와 적응 안정성 진단 — 잠정 1순위.** 기존 SFT 성과·동일 target·checkpoint를 유지하면서 사용 조건에 따른 능력 유지라는 질문으로 연결된다. 다만 MedFM-Robust와 구별되는 인과 대조 및 정답 보존이 가능해야 한다.
2. **동일 opacity 외부 확인 — 2순위.** 사용 가치는 높지만 접근·target 정합성과 재현할 구체적 실패 조건이 아직 부족하다. 접근 부담만으로 영구 배제하지 않는다.
3. **후보 수·순서 원인 추가 진단 — 3순위.** 관찰상 연관은 있으나 선행 중복과 FP 비용 때문에 추가 sampling·순서 실험이 다음 방법 투자를 바꿀 가능성이 낮아졌다.
4. **현재 continuation 방법 개선 — 보류에서 투자 종료 권고로 변경.** 재개하려면 회복을 유지하면서 FP를 낮추는 구체적 선택 근거와 가까운 baseline 대비 이점이 새로 필요하다.

think_more의 이유는 새로 발견한 직접 선행이 전환 후보의 가치를 바꾸기 때문이다. 다음 라운드는 해당 구현의 적용 범위와 최소 대조 설계에 한정한다. 구별할 조건이 없으면 robustness 실험을 억지로 만들지 않고 외부 일반화 또는 다른 구체적 질문을 선택한다.

## 재사용·미완료 보완·자원

research HEAD는 `8dad463392de9bb0e9fe7d93d64b9c374492de9b`이며 status와 diff는 비어 있다. 현재 `generate.py`, `geometry.py`, `lora.py`, `metrics.py`, `parse.py`, `risk30_source.py`, `risk30_eval.py`의 tracked 존재를 확인했다. 새 접근법 기반과 선별 반입 목록은 방향 확정 뒤 정한다. 이번 빈 reuse_assets는 실행 승인이나 누락 파일 재구현 허용이 아니다.

최초 tokenizers import는 현재 계획용 Python에서 ModuleNotFoundError로 실패했다. 설치하거나 환경을 변경하지 않았다. 이후 tokenizer.json의 decoder 규칙과 vocabulary를 읽고, 대상 token에 byte fallback이 없음을 검사한 뒤 표준 라이브러리로 JSON을 해석했다. 이는 이번 저장 출력 분석용이며 공식 tokenizer 실행 검증을 대체하지 않는다.

iter_031의 정식 층별·IoU≥0.5·center-in-GT 민감도·비용 분석은 여전히 새 결과 경로에 보완해야 한다. 이번 사후 분석으로 전체 보완 완료를 선언하지 않는다. C/E 본 GPU 출력은 재생성하지 않는다. 실행기 결함은 실제 새 GPU 경로를 선택할 때만 필요한 범위를 수정한다.

이번에는 GPU 계획을 확정하지 않았다. 다음 implement 계획에서 실제 입력의 두 GPU 병렬 배치, 2/4 worker 또는 batch 비교, 전체 peak와 worker당 2GiB 여유, 출력 정합성, 실측 처리량에 따른 표본 확대·시간·재개 기준을 정한다. 이전 약 8.4GiB allocated peak를 새 설정의 안전 보장으로 사용하지 않는다.

### 대규모 GPU 필요 후보

다기관·다소견에서 vision encoder와 언어 모델을 함께 적응시키고 검출·일반 질의·입력 변화 안정성을 공동 평가하는 post-training을 보존한다. 충분한 해상도·batch·seed 비교에는 더 큰 자원이 필요할 수 있으나, 필요성과 신규성은 미확정이며 현재 두 GPU의 경량 적응을 배제하지 않는다.

## 다음에 파고들 질문
- MedFM-Robust의 실제 VLM 학습·변환 코드에서 LoRA 위치, 모델 revision, 기하 변환 후 GT 처리와 processor 입력은 어떻게 연결되는가? 우리 언어층 SFT에서 별도로 식별할 질문이 남는가?
- 병변 정보 손실과 좌표계 변화 효과를 분리하는 최소 입력 대조를 현재 896×896 processor 조건에서 구성할 수 있는가? M0의 낮은 clean 성능과 위치 prior를 통제할 비교·metric은 무엇인가?
- 그 대조의 양성·음성 결과가 각각 어떤 후속 투자를 바꾸는가? 구별 가능한 결과가 없다면 동일 opacity 외부 일반화의 target·접근·정답 조건을 갖춘 경로 중 무엇을 우선할 것인가?
