# 요약

- **이번에 할 일:** 뇌 MRI의 병변 신호와 주변 구조 변위에 답하도록 직접 적응한 뒤, 유용한 영상을 그대로 둔 추가 입력이 답변을 악화시키는지 비교한다.
- **필요한 이유:** 기존 전체/영역 차이는 별도 학습·해상도·context가 섞여 있었다. 이번에는 하나의 checkpoint와 보존된 입력 tensor로 비교한다.
- **확인할 기준:** 직접 SFT 이후의 영상 대응 신호, 복제 대비 결합 입력의 손실, 질문별 입력 선택과 공유 분류기의 정확도·비용을 함께 본다.
- **주의·다음:** 보고서–영상 연결은 아직 미검증이다. 두 질문이 단순 대안으로 충분하면 관찰만 보존하고 방법 투자를 종료한다. 신규 기여나 방법 효과를 미리 가정하지 않는다.

## 알림 맥락

- 연구: MRI 질문별 국소·주변 근거 사용
- 데이터: 뇌종양 MRI와 공개 판독문 자료 RadGenome-Brain MRI의 BraTS-GLI
- 모델: MedGemma 1.5 직접 LoRA SFT와 공유 ResNet18 분류기
- 과제: 같은 MRI의 전체 단면·병변 영역을 보고 FLAIR 신호와 midline 구조 변위에 답한다
- 가설: 직접 적응 후에도 필요한 영상 정보를 남겨둔 추가 입력이 답변을 방해할 수 있다
- 질문: 필요한 영상이 그대로 있어도 다른 범위의 영상을 함께 주면 답변이 나빠지는가?
- 변경: 방향 전환
- 연결: SPIDER의 판독·교정·오류 순위는 단순 대안 이후 가치를 확보하지 못해 보류하고, 뇌 MRI의 정보 보존 조건을 새로 시험한다
- 작업: 자료 연결을 확인한 뒤 직접 SFT·복제 대조·분류기를 비교해 최소 방법 시험의 근거 또는 후보 종료를 결정한다

# Current Understanding

현재 목표는 의료 VLM의 중요한 한계와 해결 방법을 검증하는 것이며, MRI 점수 개선 자체가 목표는 아니다. iter_080의 담당 인계는 iter_081에서 완료됐다. 해당 계획·세션·checkpoint를 다시 실행하거나 변경하지 않는다. Codex 담당 유지와 기존 자료 보존 지시는 계속 적용한다.

공식 RadGenome BraTS-GLI 목록에는 train 161 scan, val 23 scan, test 46 scan이 있다. train은 기존 조사에서 ID prefix 기준 159명이다. 이는 임상 환자 독립성의 최종 증명이 아니다. 이번에는 train 안에서만 자료 연결과 개발 비교를 한다. iter_070에서 사용한 공식 val과 공식 test는 열지 않는다.

정답 후보는 보고서의 명시적인 FLAIR HIGH/MIXED_HIGH_LOW와 midline 구조 변위 PRESENT/ABSENT다. 미언급, 병변의 midline 통과, 모호한 mixed 표현은 각각 음성·변위·고저 혼합의 정답이 아니다. 실제 train 영상과 보고서의 release 대응은 아직 확인하지 않았다.

# Strategy Check / 연구 방향 판단

**실제 선택은 SPIDER 묶음의 투자 보류를 유지하면서, 새 뇌 MRI 후보에 한정된 diagnostic 투자를 하는 것이다.** 같은 현상의 원인 규명이 아니라 같은 상위 질문 안의 새 현상 탐색이다.

이어받는 관찰은 다음과 같다.

- iter_064: MedGemma의 복제 대비 다른 slice 추가 손실은 유지한다. Qwen의 결과가 달랐고 기본 인식 조건이 충분하지 않았으므로 공통 선택 실패로 확정하지 않는다.
- iter_077: 전체/영역 MAE 차이 0.29357과 영역 입력의 영상 대응 신호는 유지한다. 공유 분류기 대비 이점과 해상도·context·별도 적응의 기여는 미검증이다.
- iter_078: 참고영상의 추가 가치 불확정과 투자 보류를 유지한다.
- iter_079: 자료·비교 검사 연결 실패이며 모델 반증이 아니다.
- iter_080/081: 영상에 따른 답변 변화는 있지만 유용한 자동 교정은 미확보다. 인계 완료를 새 연구 진전으로 세지 않는다.
- iter_082: 같은 12개 검토에서 큰 오류 포착은 confidence 5개, 불일치 3개였다. 순위 조정과 추가 seed를 피한다.

기존 입력 차이에 개입하는 선택은 원인을 좁힐 수 있지만 강한 분류기 이후의 사용 가치가 부족하다. 새 후보의 장점은 다른 입력을 추가하면서도 원래 정보를 보존하는 조건을 직접 시험하고, 단순 대안의 충분성까지 같은 실험에서 판단한다는 데 있다. 자료 연결이 성립하지 않거나 두 분류 과제로 충분하면 이 후보도 보류·종료한다.

PerFact는 같은 보고서 계열에서 전문 인식 결과 제공과 직접 SFT를 비교한다. 보고서 생성의 이득을 현재 VQA의 근거 보존 효과로 옮길 수는 없다. 논문도 보고서와 VQA의 결과를 구분한다. 이번 대조는 그 논문을 반박하거나 재현하는 실험이 아니다. [PerFact 원문](https://arxiv.org/html/2608.17926v1)

**해결할 질문:** 직접 적응·입력 수 통제 이후에도 정보 보존 손실이 있는가, 단순 입력 선택·분류기로 충분한가. **이번에 해결하지 않을 질문:** 일반적인 언어 이해, 임상적 근거 결합, 외부 일반화, 새 방법의 신규성.

과거 비용에서는 iter_077 본학습 worker wall 약 2.73시간이 확인됐지만 준비·감사·재작업의 전체 비용은 분리되지 않았다. 이번에는 기존 학습 경로를 재사용하고 현재 결론에 필요한 검증에 집중한다.

# Hypothesis

주가설은 동일 checkpoint가 단독 입력에서 이용한 정보를 결합 입력에도 그대로 받는데 답변이 악화되는 경우가 있다는 것이다.

- H0: 직접 SFT와 균형 있는 입력 형식 노출로 차이가 해소된다.
- H1: 입력 수·복제 효과를 넘어 추가 영상 내용과 연결된 손실이 남는다.
- H2: 단독 입력부터 기본 판독이 약하거나 보고서–표현 대응이 불충분하다.
- H3: 손실이 있더라도 질문별 고정 입력 선택 또는 공유 분류기로 충분해 새 방법의 투자 가치는 작다.

H1은 attention 내부 원인이나 복수 영상의 필수 결합을 뜻하지 않는다. 두 질문이 다른 답을 요구한다는 사실만으로 결합 필요성을 주장하지 않는다.

# Limitation Evidence / Correct Usage Checks

역할은 diagnostic, method_stage는 none, limitation_ids는 빈 배열이다. 기존 observed 주장을 새 뇌 MRI method gate로 대신 쓰지 않는다. 직접 SFT는 기본 능력과 형식 노출을 통제하는 기존 baseline이며 새 방법이 아니다.

필수 검사는 실제 환자·scan 연결, 원문 정답 span, sequence 의미, 영상·mask shape/affine, 정상화·orientation, 공식 chat template, assistant-only labels, 충분한 생성 길이, 고정 parser, 입력 tensor 대응, split 누수다. 올바른 입력에서의 오답은 내용 관찰로 기록한다. 모델의 100% 정답을 실행 gate로 요구하지 않는다.

# Contribution Path / Baselines / Reuse

가까운 방법은 영역 crop·표시를 활용하는 Targeted Visual Prompting과 전문 인식 결과를 제공하는 PerFact다. crop 추가나 표준 다중 규모 SFT의 개선 자체는 신규성이 아니다. [Targeted Visual Prompting 공식 구현](https://github.com/sergiotasconmorales/locvqallm)

필수 비교는 다음과 같다.

1. **직접 SFT:** 한 MedGemma 1.5 checkpoint에 두 질문과 모든 입력 형식을 노출한다. 형식별 adapter를 따로 학습하지 않는다.
2. **공유 분류기:** ImageNet ResNet18 encoder를 fine-tune하고 질문별 binary head를 둔다. 동일 원천 영상 tile, 동일 환자·정답을 사용한다. 전체·영역 feature를 구분해 결합하는 head와 view-presence 표시를 허용하며, 모든 영상을 무조건 평균해 약한 대조로 만들지 않는다.
3. **질문별 고정 입력 선택:** V에서 질문별로 G/L/GL 중 BA가 가장 높은 입력을 선택한다. 동률은 낮은 추론 비용, 그다음 G/L/GL 순서다. E를 보고 선택하지 않는다. VLM과 분류기 각각에 적용한다.
4. **train-only prior와 영상 교환:** class prior를 보고하고, 고정 환자 순환 교환으로 영상 대응 신호를 확인한다. 교환은 실제 tensor를 바꿔 실행하며 정답이 다른 환자만 사후 선택하지 않는다.

현재 답변이 두 binary label로 닫혀 있으므로 분류기 예측을 답변 문자열로 변환하는 것이 강한 모듈형 대안이다. 별도 생성기를 붙인 사실 문장 전달은 필수가 아니며, 이를 PerFact 전체 재현이라고 부르지 않는다. GT segmentation은 공통 oracle 위치 지원이다. annotation 비용·실제 예측 ROI의 오류는 이번에 평가하지 않는다.

기반은 재사용 승인된 iter_082다. reuse_assets의 iter_077 파일은 보존 SHA에서 선별 반입한다. sp75_train의 loss·LoRA·재개 경로와 sp75_c의 초기화·학습 패턴을 task adapter로 확장한다. 기존 SPIDER 상수·등급 parser·split·MAE는 사용하지 않는다. sp77_stage/pipeline의 알려진 완료 재사용·GPU 예약 결함이 있는 CLI는 반입하지 않는다. 새 실행 경로에도 같은 결함이 생기지 않도록 검사한다.

# Proposed Experiment

## 1. 자료 적합성: 대량 확보 전 한정 연결

먼저 보존된 global_finding.json, modal_wise_finding.json, train_val_test_split.json의 기존 hash를 확인한다. 공식 train에서 환자별 가장 앞선 scan ID 하나를 선택하는 규칙을 정답 적격성 판정 전에 적용한다.

두 label은 원문 span과 함께 추출하고 별도 재독해로 확인한다. HIGH는 명시적 고신호이고 상충하는 저신호·혼합 기술이 없어야 한다. MIXED_HIGH_LOW는 같은 병변에 고·저 신호가 함께 명시돼야 한다. midline 변위는 구조의 displacement/shift와 명시적 부재를 구분하며 crossing이나 not mentioned를 대체 정답으로 쓰지 않는다. global과 FLAIR의 해당 진술이 충돌하거나 대상이 불명확하면 제외 사유를 남긴다. 영상 관찰로 새 임상 정답을 만들어 채우지 않는다.

처음에는 기존 조사 사례를 포함한 train의 최대 8개로 원문–영상–mask 연결을 확인한다. 이 수는 기술 사례 범위이지 평가 표본 상한이 아니다. 가능한 label 조합과 모호한 사례를 포함한다. BraTS2021로 설명된 원천과 기존 BraTS2023 mirror의 대응은 공식 mapping·release 설명 또는 동일 원본 voxel/metadata 비교로 뒷받침해야 한다. ID와 shape 일치만으로 충분하다고 하지 않는다. 확인되지 않으면 적격 train 전량 다운로드와 학습을 중단하고 확인한 경로·오류·남은 증거를 보고한다. 접근 실패를 자료 부재라고 단정하지 않는다.

연결이 성립하면 두 질문의 적격 환자만 확정한다. 두 label 사이의 관계도 보고한다. 한 질문의 label만으로 다른 질문을 완전히 결정하는 조합만 있으면 질문별 근거 비교의 가치가 부족하므로 본학습을 발주하지 않는다.

## 2. 입력과 정답의 적용 범위

동일 FLAIR volume을 volume별 min-max·동일 RGB 채널로 렌더링한다. 전체 병변 mask의 axial 범위에서 정답 class를 보지 않고 등간격 8개 slice를 선택한다. G는 해당 slice의 전체 단면, L은 같은 slice의 병변 영역 crop이다. crop은 mask bounding box에 각 축 10% 여유를 더하고 aspect ratio를 보존해 padding한다. 복수 병변은 임의 한 병변을 고르지 않고 정답 대상과 union의 대응을 검사한다.

각 view의 8개 slice를 순서가 고정된 두 개의 2×2 montage로 만든다. montage는 896×896, 각 tile은 448×448이다. G와 L을 각각 한 번 렌더링하고 이후 조건은 재렌더링 없이 이 자산을 참조한다. 분류기는 같은 448×448 tile을 입력받는다. 모델별 normalization과 processor 차이는 기록한다.

- G: 전체 단면 montage 2장.
- L: 병변 영역 montage 2장.
- GG/LL: 해당 montage를 그대로 복제한 4장.
- GL: G 2장 다음 L 2장, 총 4장.

GL에서 G는 GG의 첫 block, L은 LL의 두 번째 block과 pixel_values가 같아야 한다. 단독 조건과도 tensor를 대조한다. 이미지 수·순서·실제 token 수를 저장한다.

G는 전체 volume이 아니라 병변 범위의 8개 전체 단면이다. 보고서의 모든 근거가 포함됐다고 가정하지 않는다. 기술 사례에서는 원 volume과 선택 영상의 구조적 대응을 확인한다. 기본 신호 부족이 남으면 인식·표집 부족을 구분하지 못한 것으로 기록한다. 반면 보존된 L 또는 G의 추가 입력 손실은 해당 동일 표현에 한정해 해석할 수 있다.

질문은 고정된 FLAIR HIGH 대 MIXED_HIGH_LOW, midline displacement PRESENT 대 ABSENT다. 답변은 HIGH/MIXED 및 YES/NO로 고정한다. 보고서·정답 span·class를 암시하는 파일명은 추론 입력에 넣지 않는다.

## 3. Split과 규모

적격 환자 N을 두 label의 조합으로 층화해 seed83으로 T/V/E 약 60/20/20으로 나눈다. V와 E는 각각 ceil(0.2N), 나머지는 T다. 앞선 계획에서 입력·문구 설계에 사용한 사례와 기술 사례는 T에 고정하고 이를 층화 시 반영한다. 환자 prefix·복수 scan·파일 hash 중복을 확인한다.

N≤159이므로 최대 규모는 T95/V32/E32다. 실제 N과 label별 수를 모델 출력 전에 manifest에 봉인한다. 각 질문의 두 class가 분할에 존재할 수 없으면 해당 설계가 성립하지 않는 것으로 종료한다. 소수 class 때문에 E가 작아지는 경우에도 실제 탐색 출력은 허용하지만, E<20명 또는 질문별 소수 class<5명이면 방법 투자 양성 판정은 하지 않고 제한된 적합성 결과로 끝낸다. 이는 확증용 power gate가 아니라 결과의 해석 범위다.

T 안에서 최대 32명을 같은 조합 층화로 선택해 T32로 삼는다. 32명은 최초 두 LR의 기본 학습 신호를 비교하기 위한 단계이며 전체 표본 상한이 아니다. 공식 val/test는 이번에 사용하지 않는다.

## 4. 동작 확인

T의 기술 사례에서 영상·label 연결, 두 답변의 token 길이, 공식 loss, LoRA 초기 항등, 비LoRA 동결, 유한 gradient와 update를 확인한다. greedy 생성 cap은 32 token, whole-string parser는 지정 단어와 끝의 단일 마침표만 허용한다. invalid·비EOS를 별도 집계한다. model 정답률 100%를 요구하지 않는다.

모든 입력 형식의 기술 출력과 짧은 학습·중단·재개를 확인한다. 새 형식 순환과 sampler 상태까지 복구해야 한다. 재개 전후 입력·checkpoint·code hash가 달라지면 기존 결과를 재사용하지 않는다.

## 5. 가능성 탐색과 조건부 학습 확대

MedGemma는 고정 revision 91850547d9f0b2fdd21aa7c5f4f3d1a8a52c243b, bf16, 언어층 rank16 LoRA, alpha32, dropout0.05, effective batch8, seed17을 사용한다. LR은 2e-5와 2e-4 두 개다. 기타 optimizer 설정은 검증된 sp75_train 경로를 계승한다.

환자당 epoch마다 두 질문을 한 번씩 사용한다. G/L/GG/LL/GL은 고정 patient·question offset과 epoch에 따라 순환해 다섯 epoch마다 동일한 노출 수를 갖게 한다. 이는 표준 직접 SFT의 입력 형식 균형이며 새로운 loss가 아니다.

- T32에서 두 LR을 10 epoch 학습한다. epoch5/10에 V 생성과 CE를 측정한다.
- V 선택은 G/L/GL의 두 질문 평균 BA, 동률은 CE·이른 epoch·작은 LR 순서다.
- 적어도 한 질문에서 V BA≥0.60이며 영상 교환보다 높거나, epoch5→10에서 V CE가 5% 이상 낮아지고 train CE도 10% 이상 낮아지면 전체 T 확대를 허용한다. 단순한 코드 동작 확인만으로 확대하지 않는다.
- 확대 시 선택 LR 하나로 base에서 새 trajectory를 시작해 전체 T 20 epoch를 학습한다. epoch10/20에 V 생성한다. epoch10→20 V CE가 5% 이상 개선되고 평균 BA가 5 pp 넘게 악화되지 않으면 같은 trajectory를 epoch40까지 한 번 연장한다. schedule은 처음부터 40-epoch horizon으로 고정한다.
- 확대 조건 미달이면 T32 결과로 종료 평가를 한다. 짧은 학습의 음성을 모든 적응 가능성의 실패로 일반화하지 않는다.

분류기는 같은 T32에서 LR1e-4/1e-3 두 개로 시작한다. 실제 영상 대응 신호 또는 validation 학습 추세가 있으면 같은 전체 T로 확대한다. 최대 64 epoch, epoch8/16/32/64에서 V를 확인하고 세 번 연속 CE·BA 개선이 없으면 종료한다. encoder를 실제 fine-tune하며 frozen head만으로 대체하지 않는다. 학습량 차이는 ledger에 기록한다.

새 Qwen 학습은 이번에 포함하지 않는다. iter_064의 계열 차이를 이미 알고 있으므로 이번 관찰을 VLM 공통 현상으로 확대하지 않는다. 우선 직접 적응 이후의 현상과 단순 대안 충분성을 판별하며, 큰 방법 투자 전에 타 계열·독립 환자 비교의 필요성을 별도로 판단한다.

## 6. 설정 잠금과 E 평가

V만으로 checkpoint와 질문별 입력 정책을 선택하고 입력·prompt·parser·가중치·환경·코드 hash를 잠근다. 이후 E에서 두 질문×다섯 입력의 10개 출력을 모든 환자에 생성한다. G와 L의 두 주 질문에 대해 고정 환자 순환 교환 2개 출력을 추가한다. 분류기는 동일 조건을 평가한다. text-only 출력은 질문별 동일 입력이므로 불필요하게 환자 수만큼 반복하지 않는다.

E 결과를 보고 checkpoint·LR·입력 수·표본·prompt를 바꾸지 않는다. E는 본 반복 안에서 보류한 개발 평가이며 외부 독립 확인이나 사전학습 비노출 자료로 부르지 않는다.

## 7. GPU·시간·재개

실행 직전 nvidia-smi와 상속된 CUDA_VISIBLE_DEVICES를 확인한다. 두 LR의 학습을 두 GPU에 병렬 배정한다. classifier·독립 생성 shard는 메모리와 처리량이 허용하는 장치에 배정한다.

기술 입력에서 microbatch1 대비 2를 먼저 비교한다. 생성에서는 batch 확대 또는 GPU당 두 worker 중 예상 이득이 큰 구성 하나를 짧게 확인한다. 전체 처리량, GPU별 실제 peak, output 일치, 오류/OOM·I/O 경합을 기록한다. worker당 2GB 여유와 외부 프로세스 점유를 반영한다. 과거 3영상의 약 11.59GiB 학습 peak를 새 4영상 peak로 대체하지 않는다.

N=159의 최대 VLM 학습은 약 1,120 updates다. iter_077의 576 updates·worker wall 약 2.73시간은 약 17초/update의 참고값이므로 같은 속도라면 약 5.3 worker-hours다. 새 기술 실행의 step·생성 속도로 학습, validation, E, loading을 분리해 예상 wall-clock을 갱신한다. 초기 일정은 수 시간 규모이며 실측이 더 길면 필요한 작업을 수행한다. 임의 시간 상한은 두지 않는다.

학습 checkpoint에는 adapter·optimizer·scheduler·RNG·sampler/형식 순환 위치·입력 digest를 포함한다. epoch 경계와 중간 update checkpoint를 원자적으로 저장한다. 각 trajectory와 생성 shard는 고유 소유권을 가지며 중복/누락·비정상 수치·진행 정체를 검사한다. 작업이 남아 있는 상태에서 구현 보고서를 완료로 제출하지 않는다.

# Implementation Tasks for Claude

실제 구현 담당은 Codex이며 호환용 섹션 이름을 유지한다.

1. reuse_assets를 확인하고 새 task adapter·manifest·평가기만 추가한다. 기존 SPIDER CLI를 새 자료에 실행하지 않는다.
2. results/iter_083 아래에 자료 연결·정답 span·제외 사유·split·환경 기록을 보존한다. 기존 results/iter_070과 모든 이전 산출물을 수정하지 않는다.
3. 한정 자료 검사를 통과한 뒤 필요한 train 영상만 확보한다. 격리 환경이 필요하면 승인된 경로에 만들고 Python 절대경로·package/version·revision·실제 입력 검사를 기록한다. 기본 환경과 hf_cache는 변경하지 않는다.
4. 입력 tensor 보존, 답변 mask/loss, 실제 동결, 중단·재개, 완료 산출물 변조 거부를 새 입력에 대해 검증한다. 불변 저수준 코드의 전체 감사를 반복하지 않는다.
5. 단계별 학습·확대 조건을 코드와 설정으로 고정하고 두 GPU에서 실측에 따른 배치를 실행한다.
6. E 전 잠금, 원시 출력, 요청별 provenance·비용 ledger와 별도 metric 재계산을 남긴다. 모든 worker 종료를 확인한 뒤 SELF_CHECK와 보고서를 작성한다.

# Evaluation (성공/실패 기준 포함)

주 metric은 질문별 BA와 두 질문 평균 BA다. class recall, accuracy, invalid, confusion matrix, 실제 정답→오답·오답→정답 환자 수를 함께 보고한다. invalid는 오답으로 처리하며 유효 출력만의 보조 수치로 대체하지 않는다.

주 대조는 신호 질문의 LL−GL, 변위 질문의 GG−GL이다. 각 단독 입력과 복제 입력 차이도 보고해 복제 자체의 효과를 구분한다. 모든 환자를 포함한 paired 비교가 주분석이며 단독 정답 사례만 고른 분석은 보조로 표시한다. 환자 bootstrap 10,000회 CI와 leave-one-patient-out 방향을 보고하고 class 누락 replicate 수를 명시한다.

**제한된 양성 관찰:** 해당 질문의 단독 입력 BA≥0.70·두 class recall≥0.50이고 영상 교환보다 BA가 0.10 이상 높으며, 복제 대비 GL 손실이 0.10 이상이고 순손실이 최소 3명에 걸쳐 나타나며 한 환자 제거로 방향이 뒤집히지 않을 때다. 이 수치는 열 명당 한 명 수준의 손실을 선별하려는 탐색 기준이며 임상적 최소 효과나 확증 기준이 아니다. CI가 0을 포함하면 불확실성을 그대로 남긴다.

**후속 투자 판단은 위 관찰과 별개다.** V에서 고정한 입력 정책·분류기의 정확도와 동일 경계의 비용을 비교한다. 두 질문 모두 BA≥0.80이고 VLM의 고정 정책 대비 차이가 5 pp 이내인 더 저렴한 분류기, 또는 추가 학습 없이 손실을 해소하는 입력 정책이 있으면 현재 두 질문의 방법 투자를 종료한다. 넓은 CI를 근거로 대안의 통계적 동등성을 선언하지 않는다.

단순 대안 이후에도 BA 5 pp 이상의 정확도 차이를 바꿀 여지와 여러 환자에 걸친 VLM의 실제 추가 정답이 함께 남을 때만 다음 method pilot의 가치를 리뷰한다. per-patient oracle로 유리한 입력을 고른 점수를 실용 성능으로 쓰지 않는다. 가능한 oracle 선택 이득만으로 후속 학습을 승인하지 않는다.

- **양성:** 정보 보존 손실 관찰을 보존한다. 단순 대안으로 충분하면 후보 종료, 충분하지 않으면 중요한 잔여 오류와 비용을 근거로 최소 개입 또는 독립 확인을 별도 판단한다.
- **음성:** 직접 SFT로 손실이 해소되거나 단순 대안이 충분하면 현재 후보를 종료한다. 새로운 loss를 붙이지 않는다.
- **기본 신호 부족:** 인식·표집·학습 적합성의 미확정으로 제한하고 현재 recipe 확대를 끝낸다. 새로운 frozen 모델 순회를 자동 발주하지 않는다.
- **불확정:** 허용된 validation 기반 연장 후에도 표본·수렴·대응 문제로 판단이 남으면 현재 후보를 보류한다. E를 본 추가 표본·seed는 실행하지 않는다.
- **자료·기술 실패:** 영향받은 연결이나 실행 경로를 명시한다. 모델 한계를 판정하지 않는다.

# Risks / Checks

- 공개 보고서 label은 임상 재판독 정답이 아니다. 모호한 문구의 사후 해석 변경을 금지한다.
- BraTS release 대응, 복수 scan·병변 연결, 원천 학습 노출을 확인한다. 불명확한 항목은 주장 범위를 제한하거나 자료 gate를 막는다.
- GT ROI와 8개 slice 표집은 oracle 지원·제한된 표현이다. 실제 volume 판독, 자동 ROI의 비용·정확도를 주장하지 않는다.
- montage와 processor가 입력을 다시 crop하거나 tensor 수를 늘릴 수 있으므로 실제 pixel_values·token mapping을 검증한다.
- 두 고정 질문은 일반적인 언어 조건부 능력을 입증하지 못한다. 질문별 head나 고정 입력 선택으로 충분한 결과를 정당한 종료 결과로 인정한다.
- 분류기에 같은 원천 해상도·영상·정답을 제공하고 충분한 학습 기회를 준다. 모델 크기·사전학습·입력 normalization·최적화량 차이는 공개한다.
- 이번은 diagnostic이다. 유효한 실제 출력 없이 limitation을 승격하지 않으며, 양성도 method full·논문 기여·독립 일반화의 승인이 아니다.

## 대규모 GPU 필요 후보

질문별 국소 세부와 주변 구조를 함께 보존하는 3D encoder·connector 공동 적응은 장기 후보로 기록한다. 표준 다중 규모 SFT와 모듈형 대안 이후의 부족함이 확인되지 않았으므로 대규모 학습의 필요성이나 신규성은 아직 주장하지 않는다.

# 계획의 근거 (GPT 조사 노트)

# 이번 결정

현재 후보에 한정된 diagnostic 투자를 선택한다. SPIDER 보류는 유지하고, 뇌 MRI에서는 단순 전체/영역 점수 비교 대신 **동일 정보를 남겨둔 추가 입력의 영향**을 시험한다. 새로운 방법 개발은 승인하지 않는다.

## 직전 질문에 대한 답

1. **가까운 선행 이후의 실패 조건:** PerFact의 Method·Evaluation·Results를 확인했다. 전문 3D 인식의 사실 제공과 보고서 생성 효과를 평가하며, VQA는 별도 답변 형식 적응과 token probability로 측정한다. §Specificity to Report Generation은 보고서 효과와 VQA 효과를 구분한다. 따라서 이를 현재 두 질문의 해결 또는 실패 근거로 직접 옮기지 않는다. 동일 국소 tensor를 유지한 추가 영상 대조는 논문의 직접 평가 범위가 아니다. [PerFact 원문](https://arxiv.org/html/2608.17926v1)
2. **구분할 설명:** 단독 대 결합만으로는 입력 수와 정보 내용이 섞인다. 같은 checkpoint의 G/L/GG/LL/GL 비교와 형식별 균형 노출을 사용한다. LL−GL 및 GG−GL은 근거 tensor를 보존한 내용 추가의 효과를 좁히지만 attention 내부 원인이나 복수 근거의 필수성을 증명하지 않는다.
3. **조건부 학습 범위:** 공식 train 안의 보고서–영상 대응을 먼저 확인하고, 정답이 성립한 경우에만 T32 직접 SFT와 공유 분류기를 실행한다. 실제 train 영상 대응은 아직 미검증이다. BraTS2021로 설명된 보고서 원천과 기존 BraTS2023 mirror의 ID 일치만으로 통과시키지 않는다. [AutoRG 공식 자료 설명](https://github.com/ljy19970415/AutoRG-Brain)

## 투자 가치와 한계

두 고정 질문은 분류기나 질문별 입력 선택으로 해결될 수 있다. 이것은 반드시 시험할 종료 대안이다. 단순 대안이 충분하면 새 loss나 language-conditioning 기여로 확장하지 않는다. 실험의 정보 가치는 직접 적응 이후의 잔여 현상과 단순 대안 충분성을 같은 실행에서 결정하는 데 있다. 기여가 이미 확보됐기 때문에 실행하는 것은 아니다.

## 확인한 원본·재사용

round_01/02 원문, iter_082 review.md, iter_070/075/077/078/079/081/082의 관련 리뷰 항목, LIMITATIONS.md, CODE_ASSETS.md를 확인했다. iter_077의 학습·입력·분류기 소스와 import 의존성을 보존 SHA에서 읽었다. 현재 HEAD는 ee8078ab0acba94f0d84d3ab2997e76eeb117bb9이며 작업 트리는 깨끗하다. 필요한 GPU 학습 파일은 현재 기반에 없고 보존 commit에 있다.

기존 observed 한계는 유지하지만 새 뇌 MRI 과제의 method 진입 근거로 대신 사용하지 않는다. limitation_ids는 비운다. 이번 계획·조사에서 파일 작성, 다운로드, 학습, 추론은 수행하지 않았다.

이전 사고 라운드 노트: agent/runs/iter_083/think/
