# 사고 라운드 1

## 새로 확인한 것

**현재 명시적 target 실험을 확대할 이유는 없다. 다만 전문 대안의 존재만으로 MRI 근거 사용 연구 전체를 종료할 근거도 없다. 다음 판단은 실제 잔여 가치에 집중해야 한다.**

### 1. 원 리뷰가 허용하는 해석

`agent/GOAL.md`, `iter_064/plan.md`, `iter_064/review.md`와 `review.json`, `agent/LIMITATIONS.md`의 해당 항목을 확인했다. MedGemma의 S/R/C BA는 0.80208/0.77083/0.50000이고 R−C는 0.27083, 95% CI [0.20313, 0.33854]다. Qwen의 S/R/C는 0.71875/0.71875/0.77083이다. MedGemma S specificity는 30/48이어서 원 기본 신호 기준에 미달한다. 이 기준을 변경하지 않는다.

공식 입력·target tensor·정답 연결 검사는 원 리뷰에서 확인됐고 blocking issue는 없다. 따라서 context 손실 관찰은 보존한다. 그러나 충분한 인식 이후의 선택 실패, 공통 모델 현상, 상보적 결합 실패는 미확정이다. routing도 S 출력을 공유한 참고 경로이며 검증된 임상 판독기가 아니다.

`iter_059/review.md`를 확인했다. 기존 E48에서 HD-GLIO+OR BA는 0.950457, U8은 0.768639다. D6 전체 비용 비율은 0.600989였다. 이는 현재 네 sequence 전체 volume 대 FLAIR 부분 입력 조건에서의 대안 채택 근거다. subtype·관계 질문까지 이미 해결했다고 확대할 수는 없지만, mask에서 만드는 새 QA에 전문 대안을 생략할 수 없다는 근거다.

`iter_063/review.md`도 확인했다. 삭제문 영상 정답률은 Qwen 2/20, MedGemma 3/20이며 삭제문 text-only에는 형식 오류·거절이 많았다. 이 자료를 곧바로 관측 충분성 정답이나 결합 능력 평가로 재사용하지 않는다.

### 2. 기존 정답으로 무엇을 정의할 수 있는가

실제 `research/results/iter_056/source/dataset.json`을 읽었다. 채널은 FLAIR/T1w/t1gd/T2w이며 정답은 background/edema/non-enhancing tumor/enhancing tumour다. 따라서 subtype 존재·범위·기하학 관계는 mask에서 정의할 수 있다. 하지만 이 schema는 특정 sequence가 필수라는 정답, 부분 영상만으로 판독 가능한지에 대한 정답, 추가 관측의 임상적 필요성 정답을 제공하지 않는다. segmentation label과 관측 충분성을 동일시하면 안 된다.

현재 `msd56_data.py`의 `load_case`는 네 채널 원본에서 FLAIR만 반환하고 `mask_slice`는 비배경 label을 합친다. subtype 또는 multi-sequence 과제로 변경하려면 새 연결 검사가 필요하다. 기존 binary 검증이 자동 승계되지 않는다.

OmniBrainBench 저장 annotation의 첫 실제 레코드와 필드 구조도 확인했다. question/image_path/answer/source_file 등의 연결은 있으나 확인한 레코드에는 영상별 필요 근거 주석이 없다. 이 한 레코드만으로 전체 자료에 그런 주석이 없다고 단정하지 않는다. 기존 선택 집단의 충분성 문제는 iter_063의 원 판정을 유지한다.

`iter_060/claude_report.md`는 UCSF-PDGM-VQA의 당시 QA 확보 실패를 명시한다. 이번에는 공개 상태를 다시 확인하지 않았으므로 현재도 접근 불가능하다고 갱신하지 않는다. MR-RATE 역시 이번 라운드에서 새 접근 확인을 하지 않았으며 대체 자료로 자동 채택하지 않는다.

### 3. 가까운 기존 방법과의 관계

sequence 누락에 강한 MRI segmentation은 기존 연구 주제다. HeMIS는 이용 가능한 modality의 표현을 집계하는 방법을 제시했고, mmFormer는 불완전한 modality 조합에서 segmentation을 다룬다. 따라서 sequence 삭제 실험이나 평균 집계만으로 새로운 원리라고 주장할 수 없다. 이번에는 원 논문 페이지의 초록·서지 정보를 확인했으며 구현 재현이나 최신 최강 baseline 검토까지 완료한 것은 아니다. [HeMIS](https://arxiv.org/abs/1607.05194), [mmFormer](https://arxiv.org/abs/2206.02425)

OmniBrainBench의 공식 저장 README와 논문 페이지도 연결했다. 일반적인 뇌 영상 다중 과제 QA 자체를 신규 기여로 삼을 수 없다. [OmniBrainBench](https://arxiv.org/abs/2511.00846)

### 4. 재사용 확인

`agent/CODE_ASSETS.md`의 iter_064 항목과 원 review.json/code_assets를 확인했다. 현재 branch에는 `s64_data.py`, `s64_checkdata.py`, `msd56_data.py`, `msd56_run.py`, `s64_run.py`, `s64_eval.py`, `s64_test.py`, `s64_verify_eval.py`가 있다. git status와 diff --stat에는 변경이 없었다. 이번에 파일을 수정하거나 실행하지 않았다.

승인 범위는 기존 target 선택·입력 연결과 제한된 수치 재계산이다. 평가 진입점의 protocol–labels–requests–model 연결, GPU 허용 집합 검사, flush 이전에 끝나는 비용 측정은 재사용 전 수정이 필요하다. 아직 실행 경로를 선택하지 않았으므로 수정을 별도 과제로 발주하지 않는다. 새 branch나 선별 반입도 결정하지 않았다.

## Strategy Check / 연구 방향 판단

- **관찰:** MedGemma의 큰 조건부 context 손실은 있지만 명시적 routing으로 회피 가능하고 Qwen에서는 재현되지 않았다.
- **해결된 질문:** 현재 고정 영상에서 다른 slice 추가의 영향과 모델별 차이는 확인했다. 동일 대조를 다시 실행할 필요가 없다.
- **남은 설명:** 현재 과제는 선택 실패보다 기본 인식·입력 충분성에 제한될 수 있다. 이와 별개로 질문별 관측 사용의 비용 가치는 아직 검증하지 않았다.
- **현재 방법 개선:** 명시적 target에 새 학습을 붙이는 선택은 우선순위가 낮다. 반복된 QA 삭제·prompt 조정도 새로운 결정을 만들지 못한다.
- **같은 질문의 재구성:** 질문별 관측 선택은 후보지만, mask-derived QA를 늘리는 것만으로는 부족하다. 전문 모델+규칙 대비 구별할 정확도·비용 목표가 있어야 한다. 이것은 VLM이 전문 모델에 없는 기능을 반드시 만들어야 한다는 조건은 아니다.
- **다른 질문으로 전환:** 위 가치가 구체화되지 않으면 현재 mask 기반 QA 경로를 보류하는 것이 타당하다. MRI 우선과 최종 GOAL은 유지한다.
- **비용:** iter_064 본생성은 약198초였다. 현재 병목은 GPU 실행시간보다 무엇을 검증할지의 판단이다. 다만 구현·감사·재작업 비용의 비율은 기록에서 분리하지 못했으므로 수치화하지 않는다.

## 남은 핵심 판단과 다음 확인

다음 라운드에서는 기존 정답으로 구성되는 질문의 **답변 정확도**와 **관측 충분성**을 분리한 상태에서, 관측 선택의 효율을 연구할 가치가 있는지 결정한다. 확인 대상은 iter_056~059의 실제 입력·비용 기록과 HD-GLIO의 지원 출력, HeMIS/mmFormer의 비교 설정이다. 이 자료를 사용해 강한 고정 정책보다 나을 구체적인 조건이 나오지 않으면 현재 경로를 보류한다. 새 benchmark 목록 조사나 전수 QA 감사를 추가하지 않는다.

## 대규모 GPU 필요 후보

질문 조건부 3D·multi-sequence 표현과 언어모델의 공동 적응은 장기 후보로 남긴다. 현재 결과는 그 필요성이나 전문 대안 대비 이점을 입증하지 않았으므로 대규모 학습의 근거로 사용하지 않는다.

## 다음에 파고들 질문
- MSD의 subtype·범위 정답으로 정의되는 질문 하나에서, 관측 충분성을 임의로 라벨링하지 않고도 질문별 관측 선택의 정확도·전체 비용을 평가할 수 있는가? 기존 iter_056~059 입력·비용 기록을 기준으로 실험 성립 여부를 결정한다.
- 전문 모델+규칙과 강한 고정 관측 정책을 허용했을 때 남는 개선 목표는 무엇인가? HD-GLIO의 실제 지원 출력과 HeMIS/mmFormer의 원 비교 조건을 확인해 최소 대조와 가치 기준을 구체화한다.
- 위 두 조건이 성립하지 않으면 현재 MRI mask 기반 QA 경로를 보류하고 어떤 GOAL 내 연구 질문으로 전환할 것인가? 기존 실패 범위와 자산을 연결해 하나를 선택하며 새 benchmark 순회를 시작하지 않는다.
