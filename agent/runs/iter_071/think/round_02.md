# 사고 라운드 2

## 핵심 결정

**현재 RadGenome FLAIR 신호 분류의 직접 적응은 발주하지 않는다.** 자료 부족이나 GPU 제약 때문이 아니다. 검토한 비교로 확인할 수 있는 것은 고정 영상 feature의 분류·생성 연결이며, 그 결과가 중요한 다중 관측 근거 사용 문제의 다음 투자를 바꿀 경로를 확보하지 못했다. 직전 라운드의 ‘단순 이진 분류 개선만 남으면 투자하지 않는다’는 종료 조건을 적용한다.

## 직전 질문에 대한 답

### 1. 정답과 subject 분리를 구성할 수 있는가?

`research/results/iter_070/data/radgenome/train_val_test_split.json`을 읽어 BraTS_GLI ID만 집계했다. train은 161 case·159 subject 문자열, val은 23 case·23 subject 문자열, test는 46 case·46 subject 문자열이다. `BraTS-GLI-<subject>` 기준으로 세 split의 subject 교집합은 각각 0이었다. 이는 ID 규칙에 따른 분리 확인이며 환자 신원이나 checkpoint 학습 노출의 독립성을 새로 증명한 것은 아니다.

train에 속함을 먼저 확인한 `BraTS-GLI-00291-000`과 `BraTS-GLI-00106-000`의 global/FLAIR 기술을 읽었다. 전자는 두 병변의 mixed high/low, 후자는 병변의 high signal이라는 대응이 있다. 따라서 제한된 보고서 기술 target 구성은 가능하다. 다만 전체 mask와 문장 속 병변·성분의 단위가 항상 일치한다는 보장은 없다. 이번에 전체 train 정답을 승인하지 않았다.

원문 라운드 01에서 확인한 sequence별 보고서의 GPT-4 분해 생성 경로는 유지한다. subject 분리를 해도 보고서 기술이 단일 관측에서 충분히 판독 가능한지, 복수 관측이 반드시 필요한지를 자동으로 정해 주지는 않는다. RGv2가 RadGenome으로 학습됐으므로 train 내부 재분할을 checkpoint에 미노출인 독립 평가로 부를 수도 없다.

이번에는 test 보고서 본문을 추가로 읽지 않았다. 라운드 01의 `00006-000`, `00014-001` 보고서 노출 이력은 유지한다. split metadata의 집계는 추가 성능 평가가 아니다.

### 2. 공식 SFT와 단순 분류 대조는 무엇을 구분하는가?

보존된 공식 소스 revision `9670703c88e8f599c0c7edc472a5ffce4dd72b0e`의 `AutoRG_Brain/network_training/nnUNetTrainerV2_llm_resize_new.py`를 읽었다. patched 사본뿐 아니라 원본에서도 다음을 확인했다.

- `initialize_network`는 `train_with_seg=false`일 때 `pool_conv`를 제외한 영상 network parameter를 freeze한다.
- 그러나 `run_iteration`의 fp16 경로는 region feature를 `item.cpu().detach().numpy()`로 변환한 후 새 tensor로 만들어 언어 모델에 전달한다(원본 1036·1038행).
- 따라서 이 경로의 언어 loss는 영상 network와 pooling 쪽으로 역전파되지 않는다. optimizer에 network parameter가 들어 있다는 사실만으로 영상 표현이 학습된다고 해석하면 안 된다.
- non-fp16 분기는 `pass`이며 완성된 대체 학습 경로로 사용할 수 없다.
- README의 학습 schema는 region별 보고서와 mask 또는 anatomy label을 연결한다. 단일 sequence 보고서 기술의 학습 경로이지, 복수 sequence 필요성을 명시한 QA 정답 schema는 아니다.

이는 소스에서 확인한 계산 경로이며 GPU gradient 실측이나 원 저자의 실제 학습 run 전체에 대한 판정은 아니다. 이번 연구에서 이 경로를 사용한다면 직접 생성 SFT와 동일 feature 분류 head의 비교는 고정 feature의 답변 연결 차이를 다룬다. head가 성공해도 일반적 영상 인식이 충분하다고 단정할 수 없고, 둘 다 실패해도 MRI 표현 전체를 기각할 수 없다. gradient 연결을 새로 바꾸는 일은 공식 baseline의 단순 실행과 구분해야 하며 이번에 발주하지 않는다.

### 3. 성공하면 중요한 잔여 근거 사용 조건이 남는가?

현재 HIGH/MIXED_HIGH_LOW 과제에서는 확인하지 못했다. 분류 head가 충분하면 이진 답변을 그대로 출력할 수 있다. 생성 SFT가 개선돼도 그것만으로 복수 관측 선택·결합을 검증하지 않는다. 여러 sequence label을 나열하거나 규칙으로 조합하는 과제를 붙이는 것도 임상적으로 상보 근거가 필요하다는 정답을 대신하지 못한다.

이는 신규성을 완전히 증명하지 못했다는 이유로 최소 실험을 막는 결정이 아니다. 양성·음성 결과가 현재 상위 질문의 다음 투자 선택을 어떻게 바꾸는지 구체화하지 못했기 때문이다. 현재 후보는 보류하고 같은 train 감사·head 실험·gradient 복구를 별도 준비 반복으로 만들지 않는다.

## Strategy Check / 연구 방향 판단

해결된 질문은 ‘현재 RadGenome 자료와 공식 경로로 제한된 적응 비교를 구성할 수 있는가’다. 기술적으로 일부 가능하지만, 제안된 인식 대 출력 연결 해석은 과장돼 있었다. 이제 남은 판단은 후보 구현이 아니라 상위 질문 유지·전환이다.

기존 사실은 충돌 없이 보존한다. iter_064의 context 손실은 실제 관찰이나 명시적 routing 이후의 방법 필요성이 없다. iter_059의 전문 대안은 해당 구간 판정에서 강했다. iter_070의 P/G 기준 미달은 새로운 관측 결합 한계를 만들지 않는다. 반면 과거 직접 SFT와 공동 형식 적응의 실제 개선은 학습 가능성을 지지하지만 전문 대안 이후의 연구 가치까지 확정하지 않는다.

다음 판단은 MRI 우선과 다중 관측 질문을 같은 강도의 고정 조건으로 취급할지 검토해야 한다. MRI는 사용자 우선순위이고 최종 GOAL은 중요한 의료 VLM 방법론이다. 단순히 새 데이터·모델이 있다는 이유로 전환하지 않으며, 기존 유효한 적응 결과가 지지하는 실패 조건과 현재 MRI 가설의 판별 가능성을 비교한다. 이번에 어느 새 방법이 유망하다고 미리 결정하지 않는다.

## 확인한 원문과 자산 경계

`agent/runs/iter_071/think/round_01.json`, `agent/GOAL.md`, iter_070의 review.md/review.json, iter_064의 review.md, 관련 LIMITATIONS/CODE_ASSETS 항목을 직접 읽었다. 현재 research HEAD는 `02a8adade58f7cea84638f9e96bf963a0fb64d55`이며 `git status --short` 출력은 비어 있었다.

AutoRG README와 공식 trainer는 `research/results/iter_070/external/src/AutoRG-Brain-9670703c88e8f599c0c7edc472a5ffce4dd72b0e/`에 보존돼 있다. 원본과 patched 사본을 구분해 읽었다. `ar70_labels.py`의 승인은 val 수동 기록에 한정되며 train 자동 추출기로 확대하지 않는다. 기존 runner·평가기의 needs_fix는 그대로 남는다. 사용하지 않을 코드를 정비하거나 반입하지 않는다.

## 다음 판단의 범위와 종료점

추가 라운드에서는 이 RadGenome 후보의 정답·학습 경로를 다시 조사하지 않는다. 기존 직접 적응의 큰 개선과 전문 대안 이후의 잔여 문제를 원 리뷰에서 연결하여 연구 질문의 유지·전환을 결정한다. 새 benchmark 순회나 frozen 모델 추가를 대안 목록으로 삼지 않는다. 실행 질문이 성립하면 구현 계획을 작성하고, 성립하지 않으면 그 부족함을 명시한다. 형식적인 setup으로 구현 단계를 채우지 않는다.

## 대규모 GPU 필요 후보

영상 encoder·connector·언어 모델의 공동 적응은 장기 후보로 유지한다. 이번에 확인한 공식 trainer의 gradient 단절은 해당 경로의 해석 문제이며, 대규모 공동 학습이 필요하거나 효과적이라는 실험 근거는 아니다.

## 다음에 파고들 질문
- iter_012·037·048의 원 리뷰에서 직접 적응의 개선과 전문 대안의 충분성을 분리하면, 현재 MRI 근거 선택·결합보다 판별 가능성이 높은 학습·전이 실패 조건 하나가 남는가? 남으면 그 조건을 실제 출력과 강한 단순 대조로 검증할 투자로 전환하고, 없으면 기존 과제를 재개하지 않는다.
- MRI 우선은 유지하되 다중 관측 선택·결합을 당장의 고정 연구 질문에서 내릴 필요가 있는가? iter_059·064·070과 이번 적응 후보 종료 근거를 기준으로, 기존 MRI 자산에서 중요한 과제를 정의하는 선택과 다른 의료 VLM 학습 질문으로 전환하는 선택 중 하나를 결정한다.
