# 사고 라운드 1

## 새로 확인한 것

입력별 SFT pilot의 근거는 확보됐지만, 학습 가능한 통합 지점은 아직 확정되지 않았다. 이번에는 그 문제를 실제 schema와 모델 구현 수준으로 좁혔다.

- `agent/GOAL.md`, `agent/runs/iter_142/review.md`, `agent/runs/iter_141/review.json`, 관련 `CODE_ASSETS.md` 항목과 실제 소스를 확인했다. iter_141은 valid_experiment=true, blocking 없음이며 현재 한계는 observed다. method pilot 진입 근거로 사용할 수 있지만 full 개발 근거는 아니다.
- iter_142의 공개 항목 일치율은 AutoRG 46.55%, 개별 MedGemma 45.65%다. 차이 +0.89pp의 95% 구간은 [−14.58,+19.35]pp로 전문 대안의 충분성은 불확정이다. 기존 결과는 재채점하지 않는다.
- 실제 후속 계약은 `research/results/iter_142/whole_sequence_supervision.md`에 있다. 이 문서는 전체 sequence target을 한 번 사용하고 국소 표현까지 gradient를 연결해야 한다고 명시한다. 구체적인 학습 구조나 실측 메모리는 제공하지 않는다.
- `research/results/iter_141/official/train_val_test_split.json`과 `ISLES22/global_finding.json`을 비변경 집계했다. ISLES22 DWI key는 train 175개, val 25개, test 50개이고 global 보고서는 250개다. 이는 metadata 수이며 새 환자의 영상 연결·적격 target 수를 확정한 것이 아니다.
- 확인한 보고서 예시들은 같은 병변의 위치·형상과 ADC 저신호/DWI 고신호를 한 문장에 함께 기술한다. DWI 절과 연결된 위치·형상은 사용할 후보지만 ADC·확산 제한·병인·시기를 자동으로 DWI supervision에 넣어서는 안 된다. 전체 집단의 target 변환 규칙은 아직 검증하지 않았다.
- 기존 8명의 유효 slice 수는 65, 69, 64, 70, 56, 60, 70, 65장이다. 로컬 MedGemma config의 `mm_tokens_per_image=256`에 따르면 기본 image token만 환자당 14,336–17,920개다. 텍스트·추가 crop을 제외한 산술값이며 실제 학습 메모리 측정은 아니다.

## 구현에서 확인한 중요한 차이

로컬 `/home/test/.conda/envs/medgemma/lib/python3.11/site-packages/transformers/models/gemma3/modeling_gemma3.py`의 `get_block_sequence_ids_for_mask`와 `create_masks_for_vision_model`을 읽었다. 파일 SHA256은 `db8fa09902358b1c209d01af6727ee1b223928c5fea163946360573ca16696c7`이다.

현재 소스는 image block 내부 bidirectional attention과 causal attention을 결합하며, 앞선 image에 대한 접근도 허용한다. sliding layer는 여기에 window 제약을 적용한다. 따라서 image feature를 같은 순서로 연결한 뒤 묶음 이름만 바꾸는 것은 개별/인접 개입이 아니다. 국소 attention을 제한한다면 중간 텍스트 token을 통한 다른 구간 정보의 우회도 검토해야 한다.

공식 설명도 이미지당 256개 표현과 이미지 attention의 특성을 명시한다. [Google Gemma 3 구조 설명](https://developers.googleblog.com/gemma-explained-whats-new-in-gemma-3/), [Gemma 3 model card](https://ai.google.dev/gemma/docs/core/model_card_3). 이는 구조 이해의 근거이며 현재 MedGemma 전체 sequence 학습의 실행 가능성을 입증하지 않는다.

## 대안과 의미

1. **sequence target 아래 국소 attention 범위 제어:** 같은 전체 token과 target을 유지하면서 slice별/인접 구간별 상호작용만 제한하는 후보다. 추가 표현 압축을 피할 수 있지만 native attention 변경, 정보 우회, 생성 cache 일관성과 긴 sequence 메모리가 핵심이다.
2. **국소 문맥 표현 후 공유 sequence decoder:** 실제 1장/인접 묶음 처리와 전체 target의 gradient를 연결하기 쉽지만 표현 압축과 추가 통합 구조가 생긴다. 그 차이를 단순 입력별 LoRA 효과로 부를 수 없다.
3. **고정 국소 텍스트 통합기만 SFT:** 실행은 단순하지만 시각 생성기 자체가 적응되지 않는다. 현재 주 질문의 우선 대안으로 선택하지 않는다.

## 재사용 상태

현재 research HEAD는 `b6ba0f1d2312947199048f3e59772f91c9f7ff1b`이며 작업 트리 변경은 없다. `i141_data.py`, `i141_preflight.py`, `i141_select_download.py`, `i141_run.py`, `i141_common.py`가 현재 branch에 있다. 자료 모듈에는 고정 8명·경로·사례별 위치 목록이 있으므로 새 집단에 그대로 사용할 수 없다. 필요한 부분만 새 경로와 일반적인 원문 연결 규칙으로 분리해야 한다. `i141_judge.py` 및 `i142_judge.py`는 새 출력 평가기로 재사용하지 않는다. 아직 선별 반입할 외부 학습 모듈은 선택하지 않았다.

## Strategy Check

- 중요한 문제: 같은 관측과 supervision에서 공간 문맥을 함께 처리하는 적응이 소견 보존을 개선하는가?
- 현재 근거: iter_141의 출력 관찰과 iter_142 전문 대조는 유효하다. 적응 효과는 미실행이며 이번에는 전체 sequence 정답·token 규모·attention 경로를 확인했다.
- 쉬운 해결책: 직접 적응을 먼저 검증해야 한다. AutoRG의 현재 불확정 결과만으로 새 방법 필요성을 주장하지 않는다.
- 남은 설명: 적응 부족, 국소 상호작용, 압축 손실, 변경된 attention의 영향이다.
- 다음 결정: 두 학습 구조 중 하나를 골라 단일 seed method pilot으로 연결한다. 기존 6명의 frozen 순회는 종료한다.

## 남은 질문과 다음 확인

다음 라운드는 attention 범위 제어의 계산 그래프와 계층형 통합의 공정성을 비교해 하나를 선택한다. 로컬 Gemma3의 forward·mask·generation cache 경로와 실제 사용 가능한 학습 자산의 원 review/code_assets를 필요한 범위만 확인한다. read-only 조사로 메모리 실측을 대신하지 않으며, 구조 선택 뒤에는 조건부 GPU 동작 확인을 계획에 포함한다.

## 대규모 GPU 필요 후보

전체 해상도·전체 slice를 보존한 vision-language 공동 적응 또는 3D encoder와 decoder의 광범위한 학습은 후속 후보로 남긴다. 현재 두 24GB GPU에서의 가능 여부는 아직 실측하지 않았으며 곧바로 대규모 자원이 필수라고 단정하지 않는다.

## 다음에 파고들 질문
- 로컬 Gemma3의 mask·position·generation cache 경로에서 국소 구간 간 정보 우회를 막으면서 전체 보고서 target만 모든 관측에 접근하도록 만들 수 있는가? 가능하면 추가 압축 없는 attention 대조를 우선한다.
- attention 대조와 계층형 국소 표현 통합 중 어느 쪽이 같은 관측·학습 파라미터·target 노출을 더 명확하게 맞추는가? 선택한 방식에서 검증할 gradient 경로와 구조 변경의 해석 한계를 고정한다.
- 선택한 구조에 필요한 기존 학습 코드가 어느 보존 SHA에 있으며 어떤 reuse_issues가 있는가? 관련 원 review와 실제 파일만 확인한 뒤 단일 seed의 학습량·생성 평가·조건부 확대 기준을 확정한다.
