# 사고 라운드 1

# 새로 확인한 것

현재 MSD 구간 판정의 추가 적응을 보류하고, **질문에 따라 필요한 MRI sequence 근거가 달라지는 소견 QA**로 후보를 좁혔다. 다만 공개 annotation과 실제 영상 연결을 확인하지 못해 실행 설계는 확정하지 않았다.

## 기존 결과와 보존할 판단

- `agent/GOAL.md`, `agent/runs/iter_056/plan.md`, `iter_057/review.md`, `iter_059/review.md`와 `review.json`, `agent/LIMITATIONS.md`, `agent/CODE_ASSETS.md`의 관련 항목을 확인했다.
- iter_059의 개발 E48에서 U8/HD BA는 0.768639/0.950457이고 D6 전체 비용 비율은 0.600989다. 네 sequence 전체 volume의 전문 모델과 FLAIR U8 비교이므로 동일 입력 우위나 일반적 VLM 가치 부재를 뜻하지 않는다. 기존 구간 판정 투자 종료는 유지한다.
- iter_057에서 위치 prior만으로 설명되지 않는 신호가 관찰됐지만 전문 대안 이후 추가 방법의 필요성을 보장하지 않는다. 남은 오류만으로 loss를 설계하지 않는다.
- `mri-reference-interface-sensitivity` 원문은 reference 좌표 복사와 미완료된 공식 입력 대조를 포함한다. 이번 sequence 질문의 방법 진입 근거로 전용하지 않는다. 현재 후보의 limitation id는 없다.

## 공식 출처 조사

1. **UCSF-PDGM-VQA:** 논문은 473개 MRI study의 2,387 QA를 설명한다. 보고서에서 생성한 정답이며 공개 버전의 선택지 shuffle을 명시한다. 원래 첫 선택지 정답 비율이 84.7%였다는 점은 prior 대조의 필요성을 보여준다. 예시에는 enhancement 형태, mass effect, FLAIR extension이 있으나 각 항목의 실제 공개 파일과 sequence 대응은 미확인이다. 논문이 연결한 Kaggle·익명 코드 페이지는 이번 web 도구에서 열리지 않았다. 접근 실패를 자료 부재로 판정하지 않는다. [논문 원문](https://arxiv.org/html/2605.17140v1)
2. **OmniBrainBench:** 공식 저장소와 배포 card를 확인했다. 소개의 전체 QA 수와 HF closed-ended test의 약6.82k 행은 범위가 다를 수 있으므로 모순으로 단정하지 않는다. viewer에는 question, image_path, modality_type, source_file, options, answer가 보인다. MRI의 질문 유형·다중 sequence 연결과 원천 의존성은 실제 annotation에서 확인해야 한다. [공식 저장소](https://github.com/CUHK-AIM-Group/OmniBrainBench), [공식 연결 배포](https://huggingface.co/datasets/FrankPN/OmniBrainBench)
3. **ReMIND:** 다중 sequence VQA를 이미 다루므로 단순 통합 효과를 신규성으로 주장할 수 없다. 확인한 원문은 NACC benchmark 공개를 향후 계획으로 설명하고 원자료에는 표준 신청 절차를 명시한다. 현재 즉시 실행 가능한 공개 자료라고 가정하지 않는다. [원문](https://www.medrxiv.org/content/10.64898/2026.03.30.26349106v1)
4. **Time-Aware MRI:** 공식 README에서 HF benchmark가 coming soon이고 원천 MRI는 별도 확보해야 함을 확인했다. 시간 변화 과제는 추가 자료 연결 비용이 있어 현재 우선 후보에서 제외한다. 전반적인 시간 추론의 실패를 확정한 것은 아니다. [공식 저장소](https://github.com/wafaAlghallabi/Time-Aware-MRI)

## 전략 비교

- **기존 MSD 개선:** 실행 자산은 가장 준비돼 있지만 전문 대안 이후 필요한 사용 가치가 확인되지 않았다. 동일 점수 추격과 sequence ablation만을 위한 투자는 선택하지 않는다.
- **질문별 sequence 근거 사용:** 현재 우선 후보다. 균등 입력과 질문별 고정 규칙을 비교하면 선택·통합의 추가 가치가 있는지 판단할 수 있다. 단, 정답을 먼저 보고 sequence를 선택하거나 모든 QA를 임상 gold로 취급하면 안 된다.
- **새 longitudinal MRI 질문:** 중요성은 있으나 현재 확인한 배포 상태와 자료 연결 비용을 고려하면 후순위다. OCT로 복귀하거나 새 modality 목록을 늘리지 않는다.

## 재사용 확인

`research/` HEAD는 `463d215b4d5a92a17dec80f2be29daefab44cc3e`이며 `git status --short` 출력은 비어 있다. `msd56_data.py`, `msd56_run.py`, `hdglio59_u8.py`, `msd56_qwen.py`의 실제 파일과 관련 함수·의존성을 확인했다. `msd56_data.py`는 FLAIR channel 0과 MSD 경로에 묶여 있어 새로운 자료 loader로 그대로 사용할 수 없다. `msd56_run.py`의 모델 로딩·생성은 제한적 재사용 후보이나 launcher·provenance·재개는 승인되지 않았다. Qwen 경로는 기존 실험에서 실제 실행되지 않았으므로 검증된 대안으로 표현하지 않는다. 아직 사용 파일을 확정하지 않아 선별 반입은 요청하지 않는다.

## 비용과 남은 확인

iter_059 원문상 준비·재작업의 주요 비용은 계측·검증 보완이었다. 다음에는 과제 선정 전에 범용 실행기를 정비하지 않는다. 로컬 Python의 HF metadata 읽기도 DNS 오류로 실패했다. 네트워크 권한 우회나 다운로드는 하지 않았다.

다음 라운드는 두 후보의 공식 annotation·loader와 구체적 질문을 확인해 한 과제로 수렴한다. read-only에서 archive 확인만 남으면 구현 단계의 한정 자료 점검과 통과 시 실제 출력 탐색을 같은 계획으로 묶을 수 있다. 그러나 현재는 archive 접근 외에도 질문·대조군 선택이 남아 있어 구현을 발주하지 않는다.

## 대규모 GPU 필요 후보

다중 sequence 3D encoder와 언어 모델의 공동 사전학습은 장기 후보다. 큰 자료·연산이 필요하며 현재 관찰로 필요성이나 신규성이 입증되지 않았다. 먼저 현재 두 GPU에서 실행 가능한 고정 입력·단순 선택·경량 적응의 가치부터 확인한다.

문헌은 조사 근거이며 사용자 논문 추천으로 등록하지 않는다.

## 다음에 파고들 질문
- UCSF-PDGM-VQA의 공식 공개 annotation·코드에서 study ID, shuffled 정답, sequence 목록과 enhancement 또는 FLAIR 소견 질문을 실제로 연결할 수 있는가? 가능하면 해당 하위 과제를 우선한다.
- OmniBrainBench의 공식 TSV와 loader에서 같은 study의 여러 MRI sequence 및 영상으로 판정 가능한 소견 질문을 식별할 수 있는가? 교육용 이미지·원천 문서 의존성이 크면 어떤 제한된 비교만 가능한가?
- 선택 과제에서 질문별 고정 sequence 규칙 또는 전문 segmentation+규칙이 제공하는 강한 대안은 무엇인가? 그 이후 남을 수 있는 정확도·비용 질문이 없으면 해당 후보 투자를 종료할 것인가?
