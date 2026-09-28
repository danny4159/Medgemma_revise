# 사고 라운드 1

## 핵심 판단

새 confidence 학습은 계속 보류한다. 다음 후보는 **비어 있지 않은 출력의 부분 누락**으로 좁히되, 아직 구현 계획으로 확정하지 않는다. 저장 출력에서 이 현상의 후보 사례를 확인했고, 새로 확인한 선행연구가 기여의 범위를 제한한다. 다음 라운드는 평가 사건과 강한 baseline을 정해 실제 GPU 진단의 가치를 판단하는 데 사용한다.

이번에는 문서·코드·논문 조회와 저장 결과의 읽기 전용 재집계만 수행했다. 파일 생성·수정, 모델 로딩, GPU 추론·학습은 하지 않았다.

## 기존 판단과 유지할 사항

`agent/GOAL.md`, `agent/REPORTING_STYLE.md`, `agent/LIMITATIONS.md`, `agent/CODE_ASSETS.md`, iter_029 원본 리뷰·계획, iter_028 계획과 `think/round_02.md`, iter_012–018 리뷰의 관련 결론을 확인했다.

- iter_012의 직접 LoRA SFT 개선은 유효한 출발점이다. 특정 추가 loss의 제한된 음성 결과를 SFT 전체의 실패로 해석하지 않는다.
- 전역 QA 형식 효과, 검출·개수·좌표 인터페이스, 사분면 선택은 이미 조사했다. 이를 이름만 바꾸어 반복하지 않는다.
- 사분면 선택의 일반적인 전이 부재는 여전히 미확정이다. 이번 후보가 그 원인을 해결한 것으로 표현하지 않는다.
- MRI F139, 기존 reserve, iter_022 longitudinal 계획과 새 actor 학습은 보류한다.
- C400과 E800은 모두 개발 자료다. 이번 재집계를 독립 확인이나 새로운 유효 실험으로 세지 않는다.

## 직전 결과가 실제로 말해 주는 범위

iter_029 리뷰에서 독립 검증한 E 빈 출력 398명의 entropy AUROC는 0.8224739, Presence B0는 0.8153746이다. V−T의 97.5% CI는 [−0.0304403, 0.0151615]다. 상위 80명 검토에서 entropy는 미검출 70명 중 43명을 포착한다. 따라서 현재 조건의 새 confidence head/loss 투자는 정당화되지 않는다. 남은 27명 자체도 새 방법의 필요성을 증명하지 않는다.

`research/run_iter029_decide.py`를 직접 확인했다. 재질의 추가 이득에 E 대신 C의 CI를 사용하고, token family에서 `token_nll_eos`를 누락하며, decision을 기존 경로에 덮어쓰는 문제가 남아 있다. 다음 구현에는 E의 97.5% paired CI, 전체 token family, 입력·calibration·검증 digest 연결, 기존 산출물 덮어쓰기 거부를 최소 보완으로 포함해야 한다. 현재 GPU 출력과 검증된 통계를 다시 생성할 이유는 없다.

## 새로 확인한 것 1: 빈 출력 평가 밖에도 주석 미포괄 사례가 있다

다음 저장 파일을 표준 JSON과 독립적인 사각형 교집합·IoU 계산으로 재집계했다.

- `research/results/iter_010/manifests/gt_manifest.json`
- C: `research/results/iter_012/train/lr2e-4_s17/epoch_05/val_gen/gen_worker*.jsonl`
- E: `research/results/iter_012/confirm_sft_seed17/gen_worker*.jsonl`

`concise` 출력만 사용했고, C 400명·E 800명의 ID 중복이 없으며 모두 EOS 종료임을 확인했다. 예측의 `box_2d`와 GT의 `yxyx_norm`을 같은 0–1000 좌표로 비교했다.

| 저장 출력의 탐색적 분류 | C | E |
|---|---:|---:|
| 전체 환자 | 400 | 800 |
| 비어 있지 않은 출력 | 201 | 402 |
| 양성 중 비어 있지 않은 출력 | 164 | 330 |
| 그중 어떤 GT의 최대 IoU가 0.3 미만 | 54 | 101 |
| 그중 어떤 GT가 모든 예측과 교집합 면적 0 | 23 | 40 |
| 한 GT는 IoU≥0.3이고 다른 GT는 모든 예측과 교집합 0 | 20 | 27 |

이 수치는 **후보 현상의 규모를 확인하는 사후 개발 분석**이다. GT별 최대 IoU를 사용했으며 일대일 matching 기반 공식 FN 지표가 아니다. 낮은 IoU 101명을 모두 인지적 누락이라고 부를 수 없다. 교집합 0인 사례도 잘못된 위치 예측·주석 경계·대상 대응의 영향을 추가로 확인해야 한다.

다만 빈 출력 여부만 검사하면 놓치는 관찰 범위가 있다는 점은 분명하다. E의 27명은 적어도 한 병변에 예측이 대응하면서 다른 주석에는 어떤 예측도 겹치지 않는 조건이다. 이들이 조기 종료, 개수 prior, 시각 정보 부족 중 무엇과 연결되는지는 아직 모른다. entropy가 이 환자들의 위험을 구분하지 못한다는 증거도 아직 없다.

iter_028 조사에서도 부분 누락은 후보로 언급했지만 실제 실험은 빈 출력으로 한정했다. 따라서 이번 후보는 당시 미검증 범위를 다시 명시한 것이며, 이미 확인한 사실을 미확인으로 되돌리는 것이 아니다.

## 새로 확인한 것 2: 빈 출력 entropy 성능은 음성 비교군 구성에 따라 다르다

`research/results/iter_029/{C_eval/c_table.json,E_eval/e_table.json}`에서 미검출 양성은 유지하고 음성 category를 나누어 rank AUROC를 계산했다.

| 비교 | C | E |
|---|---:|---:|
| 미검출 opacity 대 Normal | 0.8679; 36 대 98명 | 0.8852; 70 대 195명 |
| 미검출 opacity 대 NoOpacity/NotNormal | 0.6385; 36 대 65명 | 0.7305; 70 대 133명 |

이는 사후 층별 비교이며 CI·독립 재현은 아직 없다. 각 category 내부에는 사건 class가 하나뿐이므로 category 내부 AUROC를 계산한 것이 아니다. opacity 양성과 각각의 음성 집단을 짝지은 비교다.

전체 AUROC가 정상 영상과의 구분에 일부 영향을 받는다는 해석은 가능하지만, 일반적인 abnormality score라는 원인 설명은 아직 입증되지 않았다. 이 관찰만으로 새 prompt 탐색이나 subgroup 전용 학습을 예약하지 않는다. 외부 확인을 설계한다면 음성 구성과 target 정의를 함께 고정해야 한다.

## 가까운 선행연구가 제한하는 주장

기존 문헌을 다시 확인한 이유는 빈 출력 baseline의 성공 이후, 부분 누락이라는 새 후보가 실제로 구별되는지 판단하기 위해서다. 아래는 조사 근거이며 사용자 논문 추천이 아니다.

- [PatchGate, arXiv:2608.21819v1](https://arxiv.org/html/2608.21819v1): 내부 patch의 lexical evidence로 object inventory를 만들고 누락된 object mention을 촉진하는 방법을 이미 제안한다. §3.1의 score는 object word별 patch/layer 최대값이다. 따라서 '내부 시각 근거를 읽어 출력 누락을 복구한다'는 설명 자체는 새 기여가 아니다. 동일한 opacity 클래스의 여러 인스턴스를 구별하는 문제가 이 방식과 얼마나 다른지는 추가 확인이 필요하다. 후자는 현재의 추론이지 논문이 그 조건에서 실패했다는 실험 근거가 아니다.
- [MedGrounder, arXiv:2512.01085v3](https://arxiv.org/abs/2512.01085): zero/one/multiple scored regions와 모듈형 grounded report 구성을 다룬다. 이전 기록은 v1을 인용했으며 이번에는 v3의 개요를 확인했다. 단순 set prediction·confidence 추가·의료 grounding 이식으로 기여를 주장할 수 없다. 버전별 세부 변경은 아직 대조하지 않았다.
- [BICR, arXiv:2605.10893v3](https://arxiv.org/abs/2605.10893): real/blank image hidden state를 이용하는 별도 probe를 제안한다. 일반적인 frozen confidence probe의 신규성 근거로 사용할 수 없다.
- [Detecting Clinical Hallucinations via Counterfactual Visual Grounding Uncertainty](https://papers.miccai.org/miccai-2026/0266-Paper4284.html): 응답에서 추출한 entity를 의료 grounding verifier로 검사한다. 출력된 entity 검증과 출력되지 않은 동일 클래스 인스턴스의 탐지는 구분해야 한다. 상세 구현을 재현하거나 누락 조건 성능을 확인한 것은 아니다.
- [Uncertainty Estimation for 3D Object Detection via Evidential Learning](https://arxiv.org/abs/2410.23910): missing detection uncertainty도 이미 연구한다. false negative 위험을 다룬다는 이유만으로 새로운 문제라고 주장하지 않는다.
- [ObjectTransforms](https://arxiv.org/abs/2510.16118)는 검출기의 불확실성 추정과 false-negative 복구를 다룬다. [Conformal Object Detection](https://proceedings.mlr.press/v204/andeol23a.html)도 기존 비교 범위로 유지한다.

검색에서 발견한 OpenReview `M2KLWLHzX0` 원문은 browser verification으로 열지 못했다. 검색 요약만으로 제목·학회·방법을 확정하거나 위 논문과 동일시하지 않았다.

## Strategy Check / 연구 방향 판단

중요한 사용 과제는 개선된 grounding 출력에서 필요한 병변이 빠졌는지 판단하고, 필요한 경우 추가 검토·검출로 연결하는 것이다. 이번 전략 재검토는 강한 단순 위험 baseline을 확보한 뒤 다음 투자를 고르는 과정이다.

1. **현재 빈 출력 방법 개선:** 구현 비용은 비교적 작지만 재질의의 큰 추가 이득은 지지되지 않았다. 새로운 head/loss의 정보 이득이 낮다. 최소 평가 결함만 고친다.
2. **잔여 부분 누락 진단:** 같은 영상·소견·SFT checkpoint를 유지한다. 저장 출력에서 후보 사례를 확인했으며, 빈 출력의 존재 판단과 집합 완전성을 구분할 가능성이 있다. 다만 위치 오류와의 구분, 가까운 선행 대비 차별성이 아직 미확정이다. 잠정 1순위로 추가 조사한다.
3. **동일 opacity 외부 확인:** 일반화 검증의 가치는 높다. 그러나 과거 조사에서 확인한 target 대응과 접근 조건은 그대로 남는다. [VinDr 공식 자료](https://physionet.org/content/vindr-cxr/1.0.0/)는 Lung opacity·Consolidation·Pneumonia를 구분한다. 로컬 `legacy/eval_samples/not_in_training/vindr_cxr/meta.json`은 존재하지만 과거의 소규모 사용 자료이며 독립 대표 집단으로 볼 수 없다. 접근 부담만으로 제외하는 것이 아니라, 지금 검증할 구체적 실패 조건을 먼저 정한다.
4. **다른 GOAL 내 질문:** 검출 적응 뒤 domain shift나 target 조건 변화에 대한 견고성은 후보로 남긴다. 그러나 현재 자산의 부분 누락보다 높은 정보 이득을 아직 확인하지 못했다. MRI·longitudinal로 자동 전환하지 않는다.

부분 누락이 단순 위치 오차이거나 기존 score·출력 개수·seed 비교로 충분히 설명되면 이 후보를 중단한다. 중요한 잔여 실패가 식별될 때만 실제 GPU 진단을 고정한다. 작은 subgroup의 불확정을 전체 VLM의 실패로 일반화하지 않는다.

## 코드·checkpoint 재사용 상태

현재 HEAD는 `0a47e99642921fb22fa49219e58805381e9eb25f`이며 `git status --short`와 diff는 비어 있다. 현재 브랜치에는 `risk28.py`, `risk28_eval.py`, `risk28_source.py`, `generate.py`, `geometry.py`, `parse.py`, `metrics.py`, `lora.py`, `prompts.py`, `queue_lock.py`, `lock_protocol.py`와 iter_029 평가 스크립트가 있다.

B0의 `results/iter_012/train/lr2e-4_s17/epoch_05/adapter.pt` 존재와 크기 119,369,709 bytes를 확인했다. 이번 라운드에서 weight SHA나 tensor digest를 다시 계산한 것은 아니다. 과거 승인 범위와 실행기 미승인 상태를 유지한다.

새 접근법을 선택하면 현재 작업 트리 파일이 새 기반에 자동 포함된다고 가정하지 않는다. 다음 라운드에서 실제 호출 경로·의존 파일을 정하고 전체 SHA를 연결한 `reuse_assets`를 작성한다. 이번 빈 배열은 새 브랜치의 반입 완료를 뜻하지 않는다.

## 다음 확인의 가치와 자원

추가 조사는 세 결정을 바꾼다. 부분 누락을 유효하게 정의할 수 있는지, 어떤 단순 baseline을 반드시 포함해야 하는지, C/E의 사건 수로 해석 가능한 진단이 가능한지다. 이들이 정해지면 구현으로 넘어간다. 문헌 목록을 계속 늘리는 조사로 확장하지 않는다.

GPU 진단을 채택하면 두 RTX 3090을 사용한다. 비어 있지 않은 긴 출력의 score 추출은 빈 출력보다 비용·메모리가 다를 수 있다. 동일 development 요청으로 총 2/4 worker 또는 batch 확대를 비교하고 worker당 2GB 여유, 전체 peak, token·score 정합성으로 선택한다. 현재 비용은 미측정이며 시간 상한을 설정하지 않는다.

### 대규모 GPU 필요 후보

다기관의 다중 병변 주석으로 검출 집합의 완전성·출력 종료·일반 QA를 함께 학습하는 전체 post-training은 후보로 보존한다. vision encoder와 decoder 공동 학습의 필요성은 미확정이다. 먼저 현재 장비의 직접 SFT·경량 적응·모듈형 baseline으로 구별할 수 있는 원리를 확인한다.

## 다음에 파고들 질문
- C/E의 비어 있지 않은 출력에서 일대일 matching, 예측–GT 교집합, 대표 원본 영상 검토를 함께 적용하면 위치 정밀도 오류와 구분되는 부분 누락 사건을 얼마나 확보할 수 있는가? 모델 결과에 유리하게 정답 정의를 고르지 않을 규약은 무엇인가?
- PatchGate의 클래스별 object inventory, MedGrounder의 scored set, 검출기의 missing-object uncertainty와 비교할 때 동일 opacity의 인스턴스 완전성에 실제로 남는 실패 조건은 무엇인가? 단순히 기존 방법을 의료 영상에 이식하는 수준을 넘을 가능성이 있는가?
- 출력 개수·길이 prior, 생성 확률·종료 선택 score, seed 집합 불일치 중 어떤 baseline이 새 진단을 가장 잘 반증하는가? 기존 GPU score의 재사용 범위와 비어 있지 않은 출력에서 추가 추출해야 할 정보는 무엇인가?
- 위 사건 정의와 baseline을 고정했을 때 C/E의 사건 수가 다음 투자 판단에 충분한가? 양성·음성·불확정별 행동, 조건부 확대 규모, 실제 재사용 파일을 확정할 수 있는가?
