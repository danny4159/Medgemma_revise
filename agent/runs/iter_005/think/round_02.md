# 사고 라운드 2

### 1. Prompt·좌표 규약: 공식 근거와 로컬 관측을 구분했다
- `agent/GOAL.md`, `agent/INDEX.md`, `agent/runs/iter_004/review.md`를 다시 확인했다. abandon된 두 접근법은 재선택하지 않는다.
- MedGemma 1.5 기술보고서 Table 12의 localization prompt는 `Where is the {object}?`이다. 해당 표는 출력 좌표 순서·JSON schema까지 명시하지 않는다. [기술보고서](https://arxiv.org/html/2604.05081v1)
- `legacy/scripts/04_official_format/rerun_localization_official.py`는 `Detect the ... box_2d ... label` 형식을 사용한다. 주석에 이 형식을 모델 probing으로 발견했다고 적혀 있다. 따라서 현재 근거로는 **공식 benchmark prompt가 아니라 로컬에서 검증한 detection prompt**로 기록하는 것이 정확하다. parser는 `[y0,x0,y1,x1]`, 0–1000을 가정하지만 값에 따라 0–1로 자동 전환하고 역전 좌표도 정렬한다. 후속 평가에서는 이런 보정과 원시 parse 성공을 분리해야 한다.
- 공식 문서가 연결하는 quick-start notebook은 찾았지만, notebook 본문을 충분히 확보하지 못해 MedGemma 1.5 전용 좌표 예제를 확인하지 못했다. Gemini나 최신 Gemma의 규약을 대신 근거로 삼지 않는다. [공식 시작 문서](https://developers.google.com/health-ai-developer-foundations/medgemma/get-started)
- 로컬 checkpoint `91850547d9f0b2fdd21aa7c5f4f3d1a8a52c243b`의 config·preprocessor는 모델 구조와 영상 변환을 명시하지만 bbox 출력 규약을 정의하지 않는다.
- 따라서 prompt 영향은 동일 영상·동일 실제 annotation에서 두 고정 prompt를 비교하고, anatomy 대리 정답 문제는 실제 organ mask에서 만든 bbox로 별도 검증해야 한다. legacy의 anatomy IoU≈0.256과 lesion IoU≈0.071 차이는 아직 전이 실패의 확정 근거가 아니다.

### 2. 데이터: 공개 배포와 실제 확보 가능성은 다르다
| 후보 | 확인한 annotation·분할 가능성 | 현재 판단 |
|---|---|---|
| JSRT + SCR | 247 CXR에 대한 수동 lung·heart·clavicle annotation. SCR 저자가 Zenodo에 masks·landmarks 등을 배포 | 실제 anatomy 평가의 우선 후보. JSRT 원본·nodule metadata 접근과 subject 대응은 추가 확인 필요 |
| NIH ChestX-ray14 + CheXmask | NIH 영상·metadata·병변 bbox에 CheXmask anatomy mask를 연결하는 경로 | 다중 병변 pilot 후보. CheXmask는 HybridGNet 생성 label이므로 anatomy GT로 취급하면 안 됨. 실제 bbox·patient metadata·영상 join은 미확인 |
| Chest ImaGenome + MS-CXR | 해부구조와 병변 phrase grounding을 MIMIC patient 단위로 연결 가능 | 현재 접근 권한·로컬 보유가 확인되지 않아 즉시 실행 대상으로 가정하지 않음 |
| CANDID-PTX | 병변 segmentation과 filename의 patient index를 제공 | 공식 배포에 신청 절차가 있어 이번 저비용 pilot의 즉시 대체재로 부적합 |

- SCR 원저자 저장소의 전체 자료는 12.5 MB이며 `masks.zip`은 4.0 MB다. `jpg.zip`이 있다는 사실만으로 원본 CXR와 병변 annotation까지 확보됐다고 판단하지 않았다. [SCR 원저자 배포](https://zenodo.org/records/7056076), [SCR 원논문](https://www.sciencedirect.com/science/article/pii/S1361841505000368)
- NIH 공식 배포 경로는 확인했지만, 로컬 NIH 관련 Hugging Face cache 일부는 README·loader만 존재한다. cache 디렉터리 이름만으로 학습 영상 보유를 판단할 수 없다. [NIH 원논문과 배포 링크](https://arxiv.org/abs/1705.02315)
- CheXmask는 모델 생성 anatomy segmentation이다. 병변 bbox와 함께 학습 보조 label로 쓸 수 있지만, 이를 정답으로 평가하면 외부 segmenter 모방 효과가 섞인다. [CheXmask 공식 배포](https://www.physionet.org/content/chexmask-cxr-segmentation-data/1.0.0/)
- CANDID-PTX는 patient grouping 정보를 제공하나 신청 완료 후 다운로드 링크를 받는다. [기관 배포 페이지](https://ourarchive.otago.ac.nz/esploro/outputs/dataset/CANDID-PTX/9926556140101891)
- **현재 확인 범위에서는 실제 anatomy annotation·병변 annotation·검증된 patient split을 모두 갖춘 즉시 사용 가능한 로컬 조합이 없다.** legacy VinDr 10영상을 학습 효과 검증에 재사용하지 않는다.

### 3. 선행 방법: 단순 anatomy supervision으로는 contribution이 부족하다
- **AnatomiX**: anatomy detector와 object token을 MedGemma 기반 LLM에 연결하고 projector·LoRA를 학습한다. anatomy token을 추가한다는 발상 자체는 이미 존재한다. [원문](https://arxiv.org/html/2601.03191v1)
- **CURE**: anatomy pretraining 뒤 grounding·report 관련 multitask curriculum을 수행한다. 4-bit LoRA rank 16, RTX A6000 48GB 한 장, 총 9,000 steps·약 45시간을 보고한다. 동일 데이터량·step 수를 맞춘 직접 병변 학습과 비교하지 않는 단순 curriculum은 약한 차별성이다. [원문 §4·§6](https://arxiv.org/html/2601.15408v1)
- **F-LMM**: frozen LMM attention을 학습 가능한 mask decoder로 읽는 선행 baseline이다. 작은 head를 붙이는 것만으로 novelty를 주장할 수 없다. 공식 코드의 기존 의존성과 현재 환경의 호환성은 별도 검증해야 한다. [공식 코드](https://github.com/wusize/F-LMM)
- **AG-KD**: Florence-2 0.23B 전체를 학습하며, 질병명을 형태·위치·밀도 등의 설명으로 바꾸는 semantic control을 제공한다. VinDr 16,087 training pairs, PadChest known/unknown 평가를 사용한다. 우리 pilot에서 설명 prompt만 가져오면 AG-KD 전체 재현이 아니라 부분 대조군으로 명시해야 한다. [원문 §2–3](https://arxiv.org/html/2503.03278v1)
- **VGMED/VGRefine**: GT 기반 평가로 grounding에 유용한 attention head를 선택하고 attention knockout을 수행한다. 따라서 label로 head를 고른다면 selection용 데이터와 최종 평가 데이터를 분리해야 한다. attention 정렬 개선과 bbox 출력·진단 개선도 각각 측정해야 한다. [ICLR 2026 원문](https://arxiv.org/html/2603.14323v1)
- **새롭게 발견한 직접 경쟁 방법은 EasyLens**다. 2026-09-14의 v3는 병변 prototype과 위치별 정상 anatomy reference를 만들고, patch 선택과 residual enhancement를 수행한다. MedGemma와 MedGemma1.5도 frozen backbone으로 언급한다. 따라서 '정상 anatomy 대비 병변 residual을 강조한다' 또는 'pooling으로 약해진 병변 신호를 복원한다'만으로는 새 방법이 되기 어렵다. 전체 supervision·interface·평가 조건 비교가 다음 라운드의 최우선 과제다. [EasyLens v3](https://arxiv.org/html/2606.06379v3)

### 4. 실행 가능성: frozen feature probe가 가장 현실적이다
- 현재 도구 shell의 기본 `python`은 `/home/milab/anaconda3/bin/python`으로 연구 환경과 달랐다. `orchestrator.py:131,308`에서 실제 환경 `/home/test/.conda/envs/medgemma`와 PATH 설정을 확인했다. 구현 단계에서는 먼저 interpreter가 맞는지 확인해야 한다.
- 실제 환경의 설치 metadata는 `torch 2.14.0`, `transformers 5.17.0`, `accelerate 1.15.0`, `datasets 5.0.1`이다. `peft`, `bitsandbytes`, `trl`의 설치 metadata는 없었다. 설치 금지 조건에서 기존 QLoRA recipe를 바로 실행할 수 있다고 가정하지 않는다.
- checkpoint config와 설치된 `transformers/models/gemma3/modeling_gemma3.py:662–696,790`을 대조했다. 896×896 입력, patch size 14이므로 vision encoder 출력은 **64×64×1152**이며, projector는 **4×4 average pooling → 16×16×1152 → 256×2560 projection**을 수행한다.
- 이에 따라 frozen encoder의 pooling 전·후에 동일 용량 head를 학습하는 CPU/GPU probe는 구현 가능성이 높다. pooling 전 bf16 feature는 영상당 약 9 MiB이므로 256영상이면 약 2.25 GiB다. 이는 배열 크기 계산이며 실측 VRAM이나 실행 시간이 아니다.
- 전체 attention을 반환하는 F-LMM 경로는 vision attention 메모리와 Gemma3 attention 구현 호환성 부담이 더 크다. LoRA는 activation memory·학습 속도 실측도 없으므로 24GB·1시간 이내 완료를 보장할 수 없다.
- 다음 pilot의 범위는 잠정적으로 **최대 256영상, feature 추출 1회, 동일 head 비교, 총 45 device-min 상한**이 적절하다. 실제 표본 수와 비교군은 데이터 확보 및 짧은 실행 예산 검증 후 고정해야 한다.

이번 라운드는 파일·설치 metadata·소스와 웹 문서를 읽었으며, 코드 수정·파일 생성·실험 실행은 하지 않았다.

## 다음에 파고들 질문
- EasyLens v3의 MedGemma1.5 적용 위치, prototype 구축 supervision, patient split, 데이터와 공개 코드 수준은 무엇인가? anatomy transfer 후보에 기존 방법과 구분되는 검증 가능한 차이가 남는가?
- JSRT/SCR의 영상·수동 anatomy mask·nodule metadata 또는 NIH bbox·patient metadata·CheXmask를 실제로 연결할 수 있는 공식 파일 경로와 schema는 무엇인가? 작은 다운로드만으로 충분한 독립 평가 집단을 구성할 수 있는가?
- pooling 전·후 동일 head 비교에서 정보 손실, 출력 해상도, probe 용량 효과를 어떻게 분리할 것인가? anatomy 보조 학습까지 넣는 것보다 이 반증 실험을 먼저 수행해야 하는가?
- 좌표 규약이 명시된 MedGemma 1.5 공식 예제를 확보할 수 있는가? 확보하지 못하면 두 고정 prompt와 독립 anatomy calibration으로 parser를 고정하는 절차 및 45 device-min 이내 요청 수를 어떻게 정할 것인가?
