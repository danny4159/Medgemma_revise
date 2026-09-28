# 사고 라운드 1

## 핵심

기존 RSNA SFT의 영역 질의 전이를 우선 진단할 근거가 있다. iter_015–017은 영상 전체의 opacity 유무와 Normal 구분을 평가했으므로, 지정 영역에 따라 정답이 달라지는 능력은 아직 확인하지 않았다. 다만 bbox 주석으로 보장할 수 있는 정답과 query 누설을 먼저 정해야 한다. 다음 라운드는 이 두 설계 문제와 실제 재사용 경로를 확정하는 데 한정한다.

이번에는 기록·소스·저장 출력·checkpoint 파일을 읽고 문헌을 확인했다. 파일 생성·수정, 모델 로딩, 테스트 및 GPU 실험은 수행하지 않았다. 새로운 전이 성능 결과는 없다.

## 사용자 보완 적용: 유지·보류·변경

- 유지: GOAL, MedGemma 1.5, iter_012의 유효한 직접 SFT 개선, 기존 checkpoint·분할·원시 결과와 정상 사용 검증을 유지한다.
- 보류: iter_022의 longitudinal 계획, MRI 확대, 새 loss 및 추가 학습을 실행하지 않는다. MRI F139와 기존 reserve를 열지 않았다.
- 변경: 이번 질문을 같은 RSNA 영상·opacity 주석 안의 가까운 공간 질의 전이로 좁힌다. iter_022는 사용자 재계획으로 보존된 기록이며 실패가 아니다.
- 기존 confirm은 후속 개발에 사용됐으므로 이번에도 개발 자료다. 환자 분리와 모델 사전학습 미노출은 별개다. 이번 진단의 확대가 독립 확인을 자동으로 뜻하지 않는다.

## 이미 답한 질문과 남은 질문

`agent/runs/iter_012–018/plan.json`의 연구 질문·비교군·관련 실험 구간, 해당 원본 리뷰, `agent/LIMITATIONS.md`와 CODE_ASSETS의 관련 범위를 대조했다.

1. **bbox 적응 가능성은 확인됐다.** iter_012 확인 양성 400명의 F1@0.3은 official_long 0.1650, SFT seed17/29/43 0.6308/0.6359/0.6528, prior_set 0.4243이다. 강한 단순 baseline 대비 실제 출력 개선이며 일반적 공간 이해의 증명은 아니다.
2. **추가 loss의 제한된 결과는 직접 SFT를 기각하지 않는다.** iter_013 최종 D−C S_loc은 +0.0032였고, iter_014 full G−C는 −0.02583이었다. 현재 후보의 추가 투자 근거가 약하다는 결과와 기존 SFT 성과를 구분한다.
3. **큰 QA 저하에는 형식 효과가 있었다.** iter_016 E600에서 B0−M0 S_scope 차이는 strict −0.255에서 semantic −0.0317로 줄었다. 기존 semantic_v1의 Normal/Abnormal 대응은 Q_A 전용이며 새 영역 질문에 이식할 수 없다.
4. **검출·개수 전달과 좌표 활용은 구분됐다.** iter_017 E600에서 B−U +0.0533, K−B +0.0150이었지만 L과 K의 정답 쌍 성패는 600명 모두 같았다. 당시 Q_O/Q_A에는 위치를 반드시 알아야만 답할 구조가 없었다. 이 결과로 영역 조건부 활용 능력을 판단할 수 없다.
5. **다른 finding의 evidence 손상은 별도 불확정 결과다.** iter_018 CheXpert E48의 H=0.0625, CI [−0.0625, 0.1875]는 이번 동일 소견의 공간 전이 질문에 답하지 않는다.

실제 `research/results/iter_016/gen/e180_plain__{M0,B0,C}/gen_worker*.jsonl`도 확인했다. checkpoint별 360개 기록이며 target 값은 `A`, `O`다. C의 A 응답에는 `Normal<end_of_turn>` 같은 실제 출력이 있다. 이는 새 질문에서도 형식·의미를 분리해야 한다는 근거이지 전이 실패의 근거가 아니다.

**이번 비교가 바꿀 결정:** B0의 위치 개선이 새로운 직접 질의에서도 나타나는지, 예측 bbox를 외부 규칙으로 사용하는 편이 충분한지, 형식·지시를 통제한 후에도 구체적인 활용 단절이 남는지를 구분한다. Q_O/Q_A나 U/B/K/L을 이름만 바꾸어 반복하지 않는다.

## Strategy Check / 연구 방향 판단

중요한 능력은 위치 supervision으로 획득한 정보가 요청된 판단에 맞게 재사용되는가이다. 이는 의료 VLM post-training의 전이 범위와 학습 supervision 선택에 연결된다.

- **기존 방법 개선:** 더 높은 bbox 점수는 가능할 수 있지만 추가 loss의 이득 근거가 약하고, 사용자가 요청한 미확인 전이에 먼저 답하지 못한다. 지금 새 학습을 시작할 정보 가치는 낮다.
- **기존 checkpoint의 능력 전이 진단:** 이미 개선된 localizer와 원시 출력이 있어, 학습 없이 내부 직접 답변과 외부 활용을 같은 정보원으로 비교할 수 있다. 현재 1순위다.
- **다른 질문으로 전환:** longitudinal은 별도 자료 접근·정답 연결이 필요하고 여러 변수를 동시에 바꾼다. 현재 우선순위를 대체할 새로운 근거가 없으므로 보류한다.

유효한 영역 정답을 만들 수 없거나 질문 누설·형식 효과만 측정하게 되면 억지 실험을 만들지 않는다. 반대로 규칙 baseline이 충분히 좋다는 결과는 실패가 아니라 추가 내부 학습의 필요성을 판단할 근거다.

## 과제 후보를 좁힌 결과와 남은 설계 문제

우선 후보는 **고정된 질의 영역과 opacity 주석의 관계를 판단하는 과제**다. 같은 영상에서 영역만 달라져 정답이 바뀌는 사례를 포함해야 전역 검출 유무·개수와 구별된다.

중요한 제약은 RSNA bbox가 segmentation이 아니라는 점이다. bbox와 ROI가 겹친다는 사실이 그 겹친 모든 픽셀에 병변이 있다는 뜻은 아니다. 따라서 `영역에 임상적 병변이 없다`를 정답으로 만들지 않고, 주석으로 보장되는 공간 관계에 주장 범위를 한정해야 한다.

현재 두 세부안을 비교 중이다.

- 주석 bbox와 지정 영역의 겹침 판단: 예측 bbox+규칙과 정확히 같은 정답 규칙을 사용할 수 있다. 다만 경계 근처에서 주석 오차와 수치 해석 부담을 통제해야 한다.
- 지정 범위에 해당하는 bbox 선택: 기존 출력 형식과 가까워 형식 변화가 작다. 대신 단순 좌표 출력의 연장에 머물 수 있어, 사용자의 전이 질문에 주는 정보가 더 제한적일 수 있다.

GT box를 중심으로 매번 ROI를 만드는 방식은 query 위치·크기에 정답이 새어 나갈 수 있다. 환자와 무관한 고정 ROI 집합을 먼저 정하고 주석은 채점·균형 점검에 사용하는 구성을 우선 검토한다. 양성·음성 query를 사후 선택할 경우에도 ROI별 정답률, 환자별 선택 규칙과 coverage를 공개해야 한다. 여러 query를 독립 환자로 세지 않는다.

기존 `iter_015/manifests/sets.json`에는 D36=36명, E180=180명, E600=600명이 있다. 각 집단의 opacity 환자는 12/60/200명이다. `labels.json`은 총 636명이며 patient, category, 원본 xyxy와 정규화 yxyx를 담는다. 위치가 실제로 답을 바꾸는 환자 수와 경계 모호성은 아직 집계하지 않았다. 이 값이 과제·표본·paired 정밀도를 결정하므로 다음 라운드의 우선 확인이다. 필요하면 이미 개발 자료가 된 원래 confirm 양성 400명 범위도 검토하되 독립 확인으로 부르지 않는다.

## 가까운 선행연구: 신규성의 경계

- [Targeted Visual Prompting for Medical Visual Question Answering](https://arxiv.org/abs/2408.03043)과 [공식 구현](https://github.com/sergiotasconmorales/locvqallm)은 이미 의료 영역 질의와 crop/draw-region 비교를 다룬다. 영역 질문이나 표시 방식 자체는 새로운 기여가 아니다.
- [Ferret](https://arxiv.org/abs/2310.07704)은 영역 입력과 grounding 출력을 함께 학습하는 선행 방법이다. 이번 기존 bbox-only checkpoint의 미학습 질의 전이와 학습 조건을 구분해야 한다.
- [Localization-Grounded Supervision 원문, §3](https://papers.miccai.org/miccai-2026/paper/3411_paper.pdf)은 진단 답과 좌표를 함께 출력하도록 표준 autoregressive CE로 학습한다. 따라서 향후 답변+좌표 다과제 SFT를 그대로 제안하는 것만으로는 새 방법이 되지 않는다. 이번에 검토하는 것은 그런 답변 supervision을 추가하기 전의 전이 범위다.

이 문헌들은 가까운 비교를 정하기 위한 조사다. 현재 우리 영역 질의의 실제 양성 근거가 없으므로 사용자 논문 추천으로 등록할 단계는 아니다. 제한된 확인으로 분야 전체에 같은 진단이 없다고 주장하지 않는다.

## Checkpoint와 코드의 실제 상태

현재 research HEAD는 `933eebaba2689d6eb654808ea177d8625ca2ca4c`이고 `git status --short`와 diff에서 변경이 없었다. `git ls-files`와 이전 SHA의 tree를 대조했다.

다음 adapter 파일은 모두 존재하며 각 크기는 119,369,709 bytes다. SHA256은 이번에 파일을 직접 읽어 계산했다.

- B0: `results/iter_012/train/lr2e-4_s17/epoch_05/adapter.pt` → `5f542af96df705e567bf4cfb000398b09313db2456c577e772bd76481799cf29`
- B29: `results/iter_012/train/lr2e-4_s29/epoch_05/adapter.pt` → `d4db2f2ab10d134b4352c7f57cc0ca5c497da3bce388d9cc91751ec9ca6d1fc9`
- B43: `results/iter_012/train/lr2e-4_s43/epoch_05/adapter.pt` → `e6e4730add1d942c81fb89aabd5477a779668d2f0f8ef01cc21af33032584f4a`
- C: `results/iter_014/full/C_lr2e-05/epoch_03/adapter.pt` → `a194e3aafc1f46f5a4435143c191a467ad46542ad7194f6ccf1f7c7572b9a96a`

B0/B29/B43의 현재 파일 hash는 각각 `iter_012/select/pick_seed{17,29,43}.json`의 선택 epoch 근거와 일치했다. 기존 `iter_015/manifests/checkpoints.json`에는 B0 tensor digest `e13f3c4461b826a060c90dfe4e4ee4c2ebac36a08f84be1a45a37495816cec11`, C tensor digest `89bb76c2c30b67d4ca8ac1d379ccdabdcd3e6743cab46bd4ff96fc674fc33e2e`가 기록돼 있다. 이번에는 tensor digest 재계산·실제 adapter 로드를 하지 않았다. C는 추가 SFT 단일 trajectory이며 독립 seed나 최적 선택 checkpoint가 아니다.

현재 브랜치에는 `generate.py`, `lora.py`, `geometry.py`, `parse.py`, `metrics.py`, `inputs.py`, `eval_gate.py`, `queue_lock.py`, `qa_gen.py`, `qa_run.py`, `qa_requests.py`, `qa_protocol.py`, `qa_spec.py`가 있다. 그러나 `qa_protocol.REQUIRED_CODE`는 현재 브랜치에 없는 `qa_data.py`, `sft_eval.py`, `run_shards.py`, ev17/cx18 모듈 등을 요구한다. 파일 몇 개가 남아 있다는 사실만으로 QA 실행 경로가 완성됐다고 볼 수 없다.

누락 파일은 소실되지 않았다. `4e453bbba4b0e798c0deeb6a940644dd62707fa3`의 tree에서 이전 QA·자료·평가 모듈들을 확인했다. 새 브랜치 기반 후보인 승인 iter_006에는 rsna_diag가 없다. 따라서 implement 전 실제 사용할 모듈과 의존 파일을 선별하여 전체 SHA·개별 경로·필수 검사로 reuse_assets를 완성해야 한다. 현재 빈 배열은 반입 확정 전이라는 뜻이다.

필수 수정은 새 경로의 자료·정답·query·checkpoint·재사용 bbox 출처 잠금, 예상 요청 집합 검증, completion 내용과 종료 코드 재검증, 실제 중단·재개 검사에 한정한다. 미사용 MRI downloader나 과거 학습 수치 검사를 이번에 다시 수리할 이유는 없다. 기존 loader·LoRA·worker를 새로 구현하지 않는다.

## 다음 라운드의 결정과 실행 경계

정답·query 구성의 타당성과 개발 환자 coverage를 확인하면 구현 계획으로 넘어간다. 모델 선택·유리한 prompt 선택에 새 성능 결과를 사용하지 않는다. 실제 구현 계획에는 두 GPU의 총 2/4 worker 또는 유망한 batch 확대 비교, worker당 2GiB 안전 여유, 긴 출력 peak, greedy 정합성, 단계별 요청 수와 실측 처리량에 따른 시간 추정을 포함한다. 이전 QA 처리량을 새 질문의 보장값으로 복사하지 않는다.

첫 GPU 진단은 기존 개발 환자와 우선 B0 한 seed에서 시작한다. 의미 있는 전이 또는 해석 가능한 단절이 관찰되고 추가 정밀도가 의사결정을 바꿀 때만 개발 표본·기존 seed로 확대하도록 설계한다. 독립 확인은 reserve 보존 지시를 지키는 별도 후속 설계로 남기며, 개발 확대를 독립 확인으로 표시하지 않는다.

## 대규모 GPU 필요 후보

다양한 공간 질의·grounding·일반 QA를 결합한 vision encoder–언어 모델 공동 post-training과 능력 보존 혼합 학습을 후보로 보존한다. 현재 그 필요성은 입증되지 않았다. 먼저 기존 LoRA의 전이 범위와 규칙·reader 대안으로 해결되는 범위를 확인해야 한다.

## 다음에 파고들 질문
- 기존 개발 opacity 주석에서 고정 ROI의 겹침 판단과 범위별 bbox 선택 중 어느 것이 경계 모호성과 query 누설을 통제하면서 충분한 환자·양방향 정답 변화를 확보하는가? 모델 출력 없이 coverage와 ROI별 정답 분포를 확인해 한 과제를 고를 수 있는가?
- 선택한 과제에서 숫자 좌표 해석·출력 형식·실제 영상 활용을 구분할 최소 대조는 무엇인가? GT oracle, query-only, 동일 문구의 bbox reader 대조를 어떻게 배치하고 개발 단계의 형식 gate를 고정할 것인가?
- 선택한 과제에 필요한 기존 QA 모듈의 정확한 반입 의존성과 provenance 수정 범위는 무엇인가? 개발 환자 수와 환자 단위 paired 변동을 기준으로 탐색·확대·seed 재현 규칙을 어떻게 정하고, reserve를 보존하면서 독립 확인을 후속 설계로 분리할 것인가?
