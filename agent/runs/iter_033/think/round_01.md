# 사고 라운드 1

## 새로 확인한 것

이번 방향은 사용자 보완에 따라 **RSNA 전용 detector 비교**로 정했다. VinDr 접근 승인을 다시 묻거나 외부 자료를 다운로드하지 않는다. 이번 라운드에서는 문서·소스·설치 metadata·저장 결과를 읽고, 기존 Python 환경의 import 가능 여부만 확인했다. 파일 생성·수정, 모델 생성·가중치 다운로드, GPU 학습·추론은 하지 않았다.

### 1. 유지·보류·변경 범위

- 유지: GOAL, MedGemma 1.5, iter_012의 직접 SFT 성과, 기존 checkpoint·분할·원시 출력·판정.
- 보류: iter_032의 VinDr 외부 전이 계획. 사용자 승인 대기로 보존하며 실패나 가설 기각으로 표시하지 않는다.
- 변경: 외부 전이보다 먼저 실제 전용 detector를 확보해 내부 grounding의 투자 가치를 비교한다.
- 종료 판단 유지: continuation 추가 방법 투자. 사분면·재질의·continuation GPU 진단을 반복하지 않는다.
- 병행 정리: iter_031의 남은 층별·민감도·오검출 비용 분석을 저장 출력으로 새 경로에 보완한다.
- MRI F139와 기존 reserve는 열지 않는다. VinDr 승인 통지 이후에는 안전한 단계 경계에서 그때까지의 결과를 반영해 외부 계획을 재검토한다.

`agent/GOAL.md`, `agent/REPORTING_STYLE.md`, `agent/LIMITATIONS.md`, `agent/CODE_ASSETS.md`, iter_009·012의 원본 review.json, iter_031의 review.md, iter_032의 plan.json 및 think 기록을 확인했다. iter_032에는 계획·조사·superseded 기록이 있으며 새 detector 구현 결과는 확인되지 않았다.

### 2. 실제 재사용할 RSNA 자료와 출력

`research/results/iter_010/manifests/{train_ids,validation_ids,confirm_ids}.json`과 `gt_manifest.json`을 직접 집계했다.

| 분할 | 환자 수 | opacity | Normal | NoOpacity/NotNormal | GT box 수 |
|---|---:|---:|---:|---:|---:|
| train | 2,400 | 1,200 | 600 | 600 | 1,774 |
| validation | 400 | 200 | 100 | 100 | 309 |
| 기존 confirm | 800 | 400 | 200 | 200 | 589 |

환자당 GT는 train·confirm에서 최대 4개, validation에서 최대 3개다. 음성 두 범주도 학습·평가에 유지해야 한다. opacity 음성을 임상적 정상으로 합치지 않는다.

`infer_manifest.jsonl`에는 영상 경로·file/pixel hash가 있고, GT에는 환자·SOP·원본 영상 연결과 `xyxy_px`, `yxyx_norm` 좌표가 있다. detector는 원본 pixel xyxy를 사용하고 평가 때 기존 padding canvas의 정규화 yxyx로 명시적으로 연결할 수 있다. 이번 라운드에서는 전체 영상 hash를 다시 계산하지 않았다. 구현 단계에서 실제 사용하는 입력·분할의 출처를 검증해야 한다.

`results/iter_012/final/confirm_result.json`과 `select/pick_seed17.json`에서 선택된 SFT가 lr2e-4·epoch05이고 seed17/29/43의 결과가 보존돼 있음을 확인했다. 기존 confirm 양성 400명의 F1@0.3은 각각 0.630750, 0.635917, 0.652833이다. base 및 세 SFT의 `confirm_*/gen_worker*.jsonl`에는 prompt·adapter·protocol·입력 hash, suffix, EOS, 생성 시간과 peak 메모리 필드가 있다. 본평가 재생성 없이 동일 환자 비교에 활용할 수 있다.

기존 confirm은 후속 연구 선택과 분석에 이미 사용됐다. 이번 detector 평가를 새 독립 확인이라고 부를 수 없다. 또한 iter_012 리뷰는 직접 SFT의 완전한 수렴을 확정하지 않았다. 이번 비교의 범위는 보존된 학습 조건이며, 의료 VLM의 최적 성능과 전용 detector 전체의 우열로 확대하지 않는다.

### 3. 공식 detector 후보와 실제 환경의 차이

공식 Faster R-CNN ResNet-50 FPN v2를 우선 후보로 좁혔다. 공식 COCO 사전학습 가중치와 학습·추론 인터페이스가 제공된다. 공식 문서의 COCO box mAP 46.7은 일반 검출 baseline 선택 근거이며 RSNA 성능 예상치가 아니다. [Torchvision 모델 문서](https://docs.pytorch.org/vision/0.20/models/generated/torchvision.models.detection.fasterrcnn_resnet50_fpn_v2.html)

공식 구현은 입력을 0–1 영상 tensor와 pixel xyxy box로 받고, 추론 시 box·label·confidence를 반환한다. 사전학습 모델을 불러온 뒤 배경+opacity의 predictor로 바꾸는 경로를 사용할 수 있다. 모델 자체의 학습과 기존 RSNA metric 계산에 COCO evaluator 전체가 반드시 필요한 것은 아니다. [공식 구현](https://raw.githubusercontent.com/pytorch/vision/v0.21.0/torchvision/models/detection/faster_rcnn.py)

공식 reference의 기본 학습률은 전체 batch 16을 전제로 하며, GPU 수·batch가 달라지면 조정하도록 설명한다. 따라서 공식 epoch 수나 LR를 현재 소규모 RSNA 적응에 그대로 복사하지 않고 실제 validation 추세로 충분한 학습을 확인해야 한다. [공식 학습 코드](https://raw.githubusercontent.com/pytorch/vision/v0.21.0/references/detection/train.py)

설치 환경은 다음처럼 구분됐다.

- **orchestrator가 지정한 medgemma:** login shell을 사용하지 않을 때 `python`은 `/home/test/.conda/envs/medgemma/bin/python`이다. metadata상 torch 2.14.0, transformers 5.17.0, numpy 2.4.6이 있다. torchvision·scipy·timm·pycocotools·ultralytics는 확인되지 않았다.
- **기본 login shell:** `/home/milab/anaconda3/bin/python`으로 바뀌었다. 여기서 torch가 없다는 첫 조회는 medgemma 환경의 결과가 아니므로 정정한다. 후속 확인에는 상속 PATH를 유지했다.
- **기존 daniel 환경:** `/home/milab/anaconda3/envs/daniel/bin/python`의 metadata는 torch 2.5.1·torchvision 0.20.1이다. 그러나 import에서 `libcusparse.so.11` 부재 오류가 발생했다. 현재 바로 실행 가능한 detector 환경으로 간주하지 않는다.
- **기존 natten_py310 환경:** `/home/test/.conda/envs/natten_py310/bin/python`에는 torch 2.6.0+cu124·torchvision 0.21.0+cu124·scipy 1.15.3이 있다. import는 현재 read-only 세션에서 사용 가능한 임시 디렉터리가 없다는 오류로 끝났다. 패키지 존재는 확인했지만 import·CUDA operator의 정상 동작은 미검증이다.

어떤 환경도 수정하지 않았고 `pip install`·`conda activate`를 실행하지 않았다. 별도 환경의 package를 medgemma의 PYTHONPATH에 섞는 우회도 하지 않았다. 다음 라운드에서는 기존 환경을 별도 detector 실행기로 사용하는 경로가 현재 Python 운영 지시와 양립하는지, 실행 단계에서 무엇을 필수 gate로 확인해야 하는지 확정해야 한다. 환경 차이를 숨긴 채 torchvision이 설치돼 있다고 가정한 구현 계획은 피한다.

RT-DETR를 transformers에 있다는 이유만으로 즉시 대체할 수도 없다. 설치된 `transformers/loss/loss_rt_detr.py`의 Hungarian matcher는 scipy를 필수 의존성으로 요구한다. torchvision 부재를 피하려고 다른 detector를 선택해도 학습 가능성이 자동 확보되지는 않는다. 의존성 때문에 약한 자체 detector를 새로 구현하는 것은 우선순위가 낮다.

### 4. 기존 평가 코드에서 새 입력 규모에 따른 주의점

`research/rsna_diag/metrics.py::match`는 GT마다 예측 후보를 재귀적으로 열거해 최대 cardinality와 총 IoU를 비교한다. 기존의 짧은 VLM box 목록에서는 검증됐지만 confidence threshold 이전 detector 후보가 많으면 계산량이 급증할 수 있다.

따라서 기존 metric 정의는 유지하되, detector의 많은 후보를 처리할 때 필요한 matching 구현을 확인해야 한다. 높은 confidence threshold나 임의 top-k로 후보를 줄여 계산 문제를 숨기면 검출기 비교를 왜곡한다. polynomial assignment를 사용할 경우 기존 exhaustive 함수와 작은 fixture·실제 VLM 출력에서 TP/FP/FN 및 동점 규칙을 대조해야 한다. 특히 GT별 오류 상보성은 matching 동점 처리에 영향을 받을 수 있다.

검출기의 confidence·NMS와 VLM의 순서 있는 생성 목록은 다른 출력 계약이다. 주평가에는 기존 VLM parser를 그대로 적용하고, detector threshold/NMS는 validation에서 고정해야 한다. F1@0.3 외에 F1@0.5, recall, FP/환자, 음성 범주별 오검출, 작은·복수 병변 오류를 함께 볼 필요가 있다. 오류 합집합의 GT 기반 상한은 실용적 앙상블 결과가 아니다.

### 5. 재사용 코드의 실재 확인

현재 research HEAD는 `8dad463392de9bb0e9fe7d93d64b9c374492de9b`이고 git status/diff는 비어 있다. 승인 기반 iter_006의 전체 SHA는 `68117cfd08429ffc3cb9b77e14fb1db3221d86ab`이다.

다음 11개 파일은 HEAD의 blob과 현재 bytes가 같음을 확인했다: `rsna_diag/__init__.py`, `geometry.py`, `parse.py`, `metrics.py`, `generate.py`, `lora.py`, `prompts.py`, `queue_lock.py`, `lock_protocol.py`, `risk28_eval.py`, `risk30_eval.py`. 앞의 10개 확인에서는 iter_006 기반의 경로 충돌이 없었고, lock_protocol의 bytes 일치도 별도로 확인했다. 최종 반입 목록과 전체 충돌 검사는 실행 경로를 확정한 뒤 고정한다.

geometry·parse·metrics의 승인은 기존 RSNA 규약 범위다. generate·lock·전체 evaluator는 재사용 미승인 사항이 남는다. 이번에는 사용하지 않을 continuation 생성기나 과거 pipeline을 정비하지 않는다. 저장 결과 읽기, detector 학습·평가, 필요한 소규모 latency 측정 경로에 한정해 결함을 해결한다. 현재 `reuse_assets=[]`는 전체 코드 승인이나 누락 파일 재구현 허용을 뜻하지 않는다.

### 6. iter_031 보완의 범위

원본 리뷰는 C201의 8/20, E402의 11/27 회복과 E F1@0.3 0.627612→0.473845를 검증했다. iter_032 라운드 02의 사후 분석에서는 중복 제거 후에도 E 추가 FP 383개와 F1 변화 −0.139173이 남았다. 같은 기록은 후보 수를 맞춘 비교의 비용 한계도 명시했다. 이를 다시 미확인으로 되돌리거나 continuation GPU 실험을 예약하지 않는다.

남은 정식 보완은 원래 box 수·양성/음성 층별 결과, IoU≥0.5 및 center-in-GT 민감도, FP와 invalid 분모의 명확화, 비교 가능한 범위의 비용 분석이다. 원시 출력·source audit·기존 protocol을 잠그고 새로운 결과 경로에 저장해야 한다. 기존 학습·추론 시간이 서로 다른 실행 구성에서 나왔다는 사실을 유지한다.

## 의미와 전략 판단

1. **RSNA detector 비교 — 1순위:** 사용자가 승인했고, 같은 annotation으로 실제 대안과 비교한다는 빠진 근거를 확보한다. 정확도·비용의 우위와 오류 중복 여부가 다음 투자를 직접 바꾼다.
2. **현재 grounding·continuation 개선 — 보류:** 기존 FP 비용과 가까운 선행의 중복을 뒤집는 근거가 없다. detector 비교 전에 새 loss·head를 학습할 이유가 약하다.
3. **외부 전이 또는 언어·근거 과제로 전환 — 후속 후보:** VinDr는 승인 대기다. 언어 과제는 VLM이 필요한 사용 목적과 강한 모듈형 비교군을 먼저 구체화해야 하며 이번 bbox 비교의 완료로 간주할 수 없다.

새 contribution은 미확정이다. detector가 정확도·비용에서 유리하고 오류도 크게 겹치면 단순 bbox 개선의 우선순위를 낮춘다. 상보성이 남으면 조건을 기술하되 결합 학습을 자동 시작하지 않는다. SFT가 특정 층에서 강하면 향후 VinDr 확인 후보로 보존한다.

## 추가 사고가 필요한 이유

연구 방향은 정해졌지만 실행 가능한 공식 detector 경로와 충분한 학습·선택 규약은 아직 확정하지 못했다. 특히 기본 환경의 torchvision 부재를 무시하면 준비만 끝나는 반복이 될 수 있다. 다음 라운드는 이 실행 경로, 수렴 판단, confidence와 matching 처리만 좁혀 확인한다. 광범위한 문헌 조사나 새로운 연구 질문 탐색은 추가하지 않는다.

## 대규모 GPU 필요 후보

다기관·다소견에서 vision encoder와 언어 모델을 공동 적응시키고 위치 출력과 언어·근거 연결을 함께 검증하는 post-training은 보존한다. 이번 detector 비교는 그 필요성을 판단하는 자료이며, 현재 두 GPU로 가능한 경량 적응의 가능성을 배제하지 않는다.

## 다음에 파고들 질문
- 기본 medgemma 환경을 변경하지 않고 공식 Faster R-CNN을 실행할 경로를 확정할 수 있는가? 기존 natten_py310을 별도 subprocess로 사용하는 범위와 구현 단계의 import·CUDA NMS/ROIAlign·가중치 검증 gate를 어떻게 명시할 것인가?
- COCO 사전학습 detector를 RSNA train 2,400명에 충분히 적응시키기 위한 한 가지 학습 recipe와 제한된 validation 선택은 무엇인가? 탐색 subset·1개 seed에서 본학습·수렴 보완·조건부 seed 확대를 결정할 기준을 어떻게 고정할 것인가?
- 기존 SFT 출력을 유지하면서 detector confidence/NMS 선택, 많은 후보의 matching, 작은·복수 병변 오류 상보성, 공정한 latency 측정을 어떤 사전 규약과 규모로 연결할 것인가?
