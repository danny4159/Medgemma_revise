# 사고 라운드 1

# 이번 판단

기존 보정·공동 grounding·교정·CT 설계의 투자 보류를 유지한다. 현재 근거로 새 loss나 추가 학습을 시작할 이유는 확보하지 못했다. 다음 검토 후보를 **영상의 기하 정보와 물리적 측정값 사이의 연결**로 좁혔다. 다만 가까운 선행이 단위 보정과 모듈형 비교까지 제공하므로, 구현 전에 남은 질문 하나를 확인해야 한다. 제안할 비교가 기존 실험을 반복하는지, 별도 실패 조건을 식별하는지다.

이번 라운드는 전략 비교와 출처 확인이다. 새 한계를 관찰하거나 방법 효과를 검증한 결과가 아니다. 다음 라운드는 광범위한 방향 탐색을 반복하지 않고 이 후보의 진입 여부만 판단한다.

# 기존 원문에서 확인한 근거

- `agent/GOAL.md`, `agent/GPT_USAGE_POLICY.md`, `agent/REPORTING_STYLE.md`, `agent/LIMITATIONS.md`, `agent/INDEX.md` 및 관련 `CODE_ASSETS.md` 항목을 확인했다. legacy 정리의 중대 정정도 읽었다. MedGemma 1과 1.5 혼동, 좌표·사용법 오류를 새로운 한계의 근거로 재사용하지 않는다.
- `iter_054/review.md`와 `review.json`은 유효한 175쌍 비교를 기록한다. O=0.6171 [0.5447, 0.7157], 최고 단일 영상 S=0.1657이다. 상대 평가 영상의 정보를 쓰는 O를 단일 영상의 달성 가능한 성능으로 해석할 수 없다. 사전 양성 기준 미달과 대안 충분성 미확인은 함께 유지한다.
- `iter_040/review.md`에서 직접 SFT의 큰 개선과 문장 대조의 제한된 추가 효과를 확인했다. M−C의 F1@0.3은 −0.005208, 97.5% CI [−0.038194, 0.026910]이다. baseline 상승 때문에 원 판정은 불확정이며, 이를 모든 대조 학습의 실패로 바꾸지 않는다.
- `iter_048/review.md`에서 공동 직접 SFT의 선택적 회복과 실용 기준 미달을 확인했다. 공동 F1은 E 0.333116, J 0.523251이고 적응 MedGrounder A는 0.594444다. J/E device-seconds 비율 0.963408은 비용 절감 근거가 되지 못했다. 잔여 손실만으로 새 방법을 추가하지 않는다.
- `iter_031/review.md`와 `iter_037/review.md`를 읽었다. continuation은 E402의 누락 사건 11/27을 회복했지만 F1은 0.6276→0.4738로 낮아졌다. detector의 낮은 threshold는 후보를 회복하지만 FP 비용이 증가한다. 이 관찰은 유효하지만 새로운 선택·재순위화 방법의 우위를 보장하지 않는다.
- `iter_053/review.md`의 oracle 183/192 실패와 E/F 미실행, `iter_052/review.md`의 CT 자료·기술 gate 실패를 유지한다. 해당 실패를 의료 VLM 전체의 능력 기각으로 확대하지 않는다.
- 위 수치는 원 리뷰의 검증 결과를 인용했다. 이번 라운드에서 원시 모델 출력을 다시 계산하거나 실험하지 않았다.

# Strategy Check / 연구 방향 판단

## 중요한 능력과 현재 해결된 질문

중요한 능력은 영상에서 얻은 근거를 요청한 답변으로 정확히 연결하는 것이다. 기존 연구는 직접 SFT로 grounding을 크게 개선할 수 있고, 공동 출력 형식의 손실도 직접 학습으로 상당 부분 회복된다는 점을 보여줬다. 적응 MedGrounder는 단순 baseline을 약하게 두고 VLM의 가치를 주장할 수 없음을 보여줬다.

남은 불확실성은 새로운 학습이 필요한 중요한 잔여 실패와, 이를 단순 대안보다 낫게 해결할 원리다. iter_040~054에는 유효 비교와 자료 준비·실행 실패가 섞여 있다. 반복 수를 유효 실험 수로 세지 않지만 누적 기회비용은 다음 선택에 반영한다.

## 세 선택의 비교

1. **기존 관찰에 기반한 최소 방법 시험:** method pilot 진입에 활용할 observed/validated 근거는 존재한다. 그러나 후보 회복, 좌표 정밀도, 공동 형식 손실 중 어느 것을 바꾸든 강한 단순 대안 이후의 구체적 이점이 아직 부족하다. 방법 gate가 형식적으로 가능하다는 이유로 학습을 발주하지 않는다.
2. **기존 후보의 추가 진단:** MediConfusion 전체 가용 표본을 이미 사용했고, CT·교정은 자료 또는 기술 gate 비용이 컸다. 같은 자료의 prompt 탐색·추가 감사·seed 반복이 다음 투자 결정을 바꿀 근거는 찾지 못했다. 보류를 유지한다.
3. **정량 측정 질문으로 이동:** 물리 단위를 가진 크기·거리 측정은 위치, 단위 변환과 최종 답변을 별도로 대조할 가능성이 있다. 공개 선행에 자료 정의와 실행 가능한 모듈형 비교가 있어 처음부터 benchmark를 만들 필요도 없다. 다만 선행이 이미 상당 부분을 다루므로 현재 선택은 실행 확정이 아니라 한정된 진입 검토다.

현재 우선순위는 3이다. 기존 방법의 성공을 가정하거나 '수치를 못 말한다'는 새 한계를 미리 등록하지 않는다. 다음 확인에서 기존 계산 대안으로 질문이 소진되면 후보를 보류한다.

# 새로 확인한 선행과 의미

## 단순한 이전 방향의 변형은 차별성이 약하다

- Hi-Token은 좌표를 축별·자리별 구조로 표현하고 기하 reward를 결합한다. 따라서 숫자 token을 구조화한다는 설명만으로 새 좌표 방법을 정당화하기 어렵다. 초록과 버전을 확인했으며 전체 재현 결과를 검증한 것은 아니다. [Hi-Token v2](https://arxiv.org/abs/2608.03471v2)
- Dense Coordinate-List Fine-Tuning은 좌표 목록 적응 후 반복·종료 행동과 구조별 간섭을 다룬다. 기존 RSNA continuation 관찰과 같은 실험은 아니지만, 'grounding 적응이 출력 제어를 바꾼다'는 넓은 주장만으로는 차별화하기 어렵다. [원문](https://arxiv.org/abs/2606.14507)
- MedGemma-1.5-4B의 shared/task-specific Mixture-of-LoRA를 사용하는 공개 구현도 확인했다. adapter 분리나 routing 자체를 새 방법으로 선택하지 않는다. [공식 저장소](https://github.com/YuanYL03/MICCAI-FLARE-2026-Challenge-Task3-2D)
- 의료 VLM의 grounding–sycophancy 관계도 이미 연구되고 있다. 문구 압력에 따른 오류를 재측정하는 것만으로 새 방향을 결정하지 않았다. [원문](https://arxiv.org/abs/2603.22623)

이는 해당 분야에 새 연구가 불가능하다는 판단이 아니다. 구체적인 잔여 실패와 가장 가까운 대조가 먼저 필요하다는 뜻이다.

## 정량 측정의 가까운 선행은 MedVision이다

MedVision은 detection, 병변 크기, 각도·거리 측정을 다루며 SFT/RFT와 plane/target OOD 평가를 제공한다. 따라서 MedGemma의 정량 점수를 새로 보고하거나 동일 loss를 적용하는 것만으로 기여가 되지 않는다. [논문 v2](https://arxiv.org/html/2511.18676v2)

공식 전처리 문서는 모델이 보는 resize·padding 좌표계와 prompt의 image size·pixel spacing을 맞추도록 한다. 원본 spacing을 그대로 넣고 모델의 물리 단위 추론 실패라고 주장하면 사용 오류를 측정할 수 있다. 이 보정은 새 방법 후보가 아니라 정상 사용 조건이다. [공식 이미지 처리 규약](https://raw.githubusercontent.com/YongchengYAO/MedVision/master/docs/Model-Image-Processing.md)

공식 BiomedParse 비교는 pretrained와 detection 적응 경로를 모두 제공한다. 예측 mask를 bbox 또는 ellipse 축 길이로 변환하며, 적응 경로는 V0의 detection 학습 영상과 맞춘다고 설명한다. 반면 T/L 전용 학습은 없다고 명시한다. 코드가 있다는 사실과 동등한 전체 supervision을 사용했다는 주장은 구분해야 한다. 설치에는 CUDA·detectron2 의존성이 있지만, 미설치를 비교군 제외 이유로 삼지 않는다. [공식 비교 README](https://raw.githubusercontent.com/YongchengYAO/MedVision/master/script/ablation/biomedparse/README.md)

## 새로 드러난 중요한 해석 문제

MedVision v1.4.0의 T/L 정답은 segmentation의 연결 성분에 ellipse를 fitting해 얻는다. release 설명은 전체 성분 중 measurement 보유율 0.547과 20 mm 이상 성분의 0.992를 구분한다. 이는 임상적으로 측정 가능한 병변의 절반이 누락됐다는 뜻이 아니다. 버전별 selection과 fitting 규칙을 확인하지 않으면 정답 없는 예측, 측정 정의 차이와 모델 오류를 혼동할 수 있다. [공식 v1.4.0 설명](https://medvision-vlm.github.io/blog/tl-annotations-v140.html)

또한 ellipse의 major axis, bbox 폭, 최대 직경은 일반적으로 같은 정답이 아니다. 따라서 단순히 bbox 좌표에 spacing을 곱한 대안을 T/L measurement와 비교해서는 안 된다. 이 구분이 다음 라운드의 핵심이다. 실제로 같은 수량을 예측하게 만들 수 있는 대조만 후보로 남긴다.

# 다음 라운드에서 결정할 범위

광범위한 문헌 검색이나 새 benchmark 목록 수집을 반복하지 않는다.

1. MedVision의 한 측정 과제에서 정확한 target 정의, inference prompt, 반환 geometry와 채점 규칙을 연결한다. 위치 추정과 산술을 분리하는 대조가 같은 수량을 평가하는지 판단한다.
2. 공식 BiomedParse 평가·적응 코드와 MedVision baseline이 그 대조를 이미 포함하는지 확인한다. 이미 포함한다면 무엇이 별도로 남는지 설명할 수 있어야 한다.
3. 선택한 과제의 source-volume ID, train/evaluation 분리, 원천 이용 조건과 파일 확보 경로를 확인한다. 공개 annotation 카드만으로 영상 사용 가능성과 독립 표본 수를 확정하지 않는다.

구별할 주장과 실행 자료가 확인되면 실제 출력 diagnostic의 규모·비용·판정 계약을 완성한다. 확인되지 않으면 후보를 보류한다. CPU 자료 준비를 별도 구현 반복으로 먼저 발주하지 않는다.

# 인계·자산·사용 경계

iter_050의 두 RETRACTION 원문과 iter_051 리뷰를 확인했다. 후자의 redo 무효화 범위를 유지하며, iter_051에서 수행한 인계·감사를 반복하지 않는다. 현재 Claude 복귀 설정도 직전 리뷰와 일치한다. 일시적 담당 변경 지시를 미완료 실험 재개 명령으로 다시 해석하지 않는다.

현재 research HEAD는 `1d26362742c2c50216c9adfd55293592a2799568`이며 `git status --short`는 비어 있었다. `CODE_ASSETS.md`, iter_054 원본 code_assets와 `mc54_spec.py`·`mc54_run.py` 일부를 확인했다. parser·순수 함수의 승인은 현재 MC 규약에 한정된다. 실행기의 필수 evidence 집합과 판정 방어는 needs_fix다. 정량 측정 실행 경로는 아직 선택하지 않았으므로 반입 파일을 지정하거나 재사용을 승인하지 않는다.

파일 생성·수정, 다운로드·설치, 모델 추론 및 GPU 실험은 수행하지 않았다. 후속 실행 계획에서는 두 GPU의 실제 메모리·처리량과 batch 또는 복수 worker를 비교한다. 현재 후보의 긴 수치 출력 비용을 iter_054의 짧은 scoring 처리량으로 추정하지 않는다.

# 대규모 GPU 필요 후보

다양한 modality에서 segmentation·landmark·물리량을 함께 감독하는 visual encoder–projector–decoder 공동 적응은 장기 후보로 기록한다. 현재 두 GPU에서 가능한 경량 적응·모듈형 대조보다 우선할 근거는 없다. 대규모 학습의 필요성이나 encoder 병목을 확인한 것은 아니다.

이번 문헌은 조사 근거이며 사용자 논문 추천이 아니다.

## 다음에 파고들 질문
- MedVision의 T/L 또는 거리 과제 하나에서 직접 수치 출력과 예측 geometry+결정적 계산이 정확히 같은 정답을 평가하도록 구성할 수 있는가? 공식 prompt·annotation schema·평가기에서 확인하고, 정의가 다르면 해당 대조를 제외한다.
- MedVision의 전처리·산술 분석·SFT/RFT 및 BiomedParse 비교 이후에도 별도로 구별할 실패 조건이 남는가? 공식 비교 코드가 이미 답한 질문이면 이 후보를 보류한다.
- 선택한 과제의 원천 영상 이용 조건·volume 단위 분할·annotation 버전과 접근 경로가 유한한 진단을 허용하는가? 확인되면 독립 분석 단위와 효과·정밀도에 맞춘 규모를 정하고, 그렇지 않으면 자료 준비를 발주하지 않는다.
