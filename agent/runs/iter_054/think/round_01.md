# 사고 라운드 1

# 이번 판단

기존 두 소견 교정, PadChest 공동 grounding, CT 압축·재접근 본평가의 투자 보류를 유지한다. 현재 근거로 새 loss나 추가 학습을 승인하지 않는다. 다음 후보는 **같은 질문에 영상에 따라 정답이 달라지는 자연 영상쌍의 판별**로 좁혔다. 다만 가까운 선행을 확인하자 평가쌍의 추가 정보를 활용하는 조건과 단일 영상 사용 조건을 구분해야 한다는 중요한 설계 문제가 드러났다. 다음 라운드는 이 문제와 실제 자료·평가기 확인에 집중한다.

# 원문에서 확인한 근거

- `agent/GOAL.md`, `agent/GPT_USAGE_POLICY.md`, `agent/LIMITATIONS.md`의 관련 항목, `agent/CODE_ASSETS.md`, 관련 INDEX 기록과 legacy 정정문을 확인했다. 전략 판단에는 iter_037·042·048·052·053의 리뷰, iter_049 계획과 iter_053 조사 기록을 사용했다. iter_042·048·052·053의 `review.json`에서 유효성 및 blocker도 대조했다.
- iter_053은 oracle 183/192로 실패했고 E48/F105는 미실행이다. D의 수정–보존 점추정은 방법 진입 근거가 아니다. 오류의 정답·초안 대응은 직전 리뷰에서 이미 확인했으므로 별도 재분석 반복을 만들지 않는다.
- iter_048은 유효한 비교다. 공동 직접 SFT의 공동 F1@0.3은 0.523251로 추가 독립 SFT의 0.333116보다 높지만, 적응 MedGrounder는 0.594444였다. J/E device-seconds 비율 0.963408은 사전 비용 기회를 충족하지 못했다. 새로운 근거 없이 이 설계를 다시 열 이유가 없다.
- iter_042의 presence gate는 음성 오류를 크게 줄였다. C_neutral 대비 P0 gate의 양성 환자별 F1도 동일했다. 넓은 양성 CI를 단순 대안의 실패로 바꾸어 negative SFT나 새 loss를 정당화하지 않는다.
- iter_052는 CT 적격 287개, D24 제외 E263/280으로 본평가가 미실행이다. D24에는 비EOS 20/296건과 최종 invalid 35/120건이 남았다. 생성 466건의 시간 합 13,358.49초는 준비·재개를 포함한 generation 집계이며 정확한 총 device 점유시간이 아니다. 이 비용과 iter_049~052의 자료 감사 비용을 고려하면, 미확인 가설을 살리기 위한 추가 자료 감사의 우선순위는 낮다.
- 위 수치는 원 리뷰의 검증 결과를 인용했다. 이번 라운드에서 원시 모델 출력을 다시 계산하거나 실험하지 않았다.

# 전략 비교

1. **기존 유효 관찰의 최소 방법 시험:** RSNA 위치 불일치는 validated이고 경량 SFT 효과도 확인됐다. 그러나 현재 후보에 대해 강한 직접 SFT·detector·MedGrounder 이후 어떤 중요한 부족함을 해결할지 새 근거가 없다. 기존 관찰의 유효성과 후속 방법 투자의 가치를 구분해 보류한다.
2. **교정·CT의 한정 보완:** 기존 자산은 있지만 본가설의 내용상 실패가 분리되지 않았다. 새 문구나 자료 감사로 이어가는 비용 대비 정보 가치가 낮다. 기존 gate와 결과를 유지한다.
3. **자연 영상쌍의 조건부 판별:** 동일 질문과 선택지에서 영상만 달라지고 정답도 달라지는 자료는 텍스트 prior와 영상 기여를 구분할 가능성이 있다. 기존 bbox 생성·oracle 복사 과제와 다른 실제 답변을 평가할 수 있다. 반면 선행 benchmark의 점수를 다시 보고하는 수준으로 끝날 위험이 있어, 단순 baseline과 가까운 후속 방법의 입력 조건을 먼저 확인한다. 이것이 이번 우선 후보다.

같은 큰 질문의 연장이므로 `language-conditioned-grounding` track을 유지한다. iter_040~053에는 유효 비교와 준비·실행 실패가 섞여 있다. 반복 수를 유효 실험 수나 자동 포기 근거로 사용하지 않지만 누적 기회비용은 반영한다.

# 새 문헌에서 확인한 것

## 일반적인 reasoning·confidence 방향은 그대로 새 기여가 되지 않는다

영상 설명을 먼저 생성하고 진단하는 분해 및 다중 sampling은 이미 제안됐다. 따라서 'describe-then-diagnose'나 추론량 확대 자체를 새 방법으로 선택하지 않는다. [Test-Time-Scaling for Zero-Shot Diagnosis](https://arxiv.org/html/2506.11166v1)

의료 영역에서 token budget, sequential/parallel scaling, 오도 문맥을 비교하는 연구도 있다. 단순히 의료 VLM에 test-time scaling을 적용하는 질문은 차별성이 약하다. [Model and Task-Aware Test-Time Scaling](https://www.jmir.org/2026/1/e90693)

MedLVR는 latent visual state, ROI 감독, 후속 policy optimization을 제안한다. 시각 근거를 반복 보존·정제한다는 설명만으로 선행과 구별되지 않는다. 이번에는 초록과 버전을 확인했으며 구현·실험 전체를 검증한 것은 아니다. [MedLVR v2](https://arxiv.org/abs/2604.09757)

## 새 benchmark도 자료 접근과 과제 구조를 먼저 확인해야 한다

MedLesionVQA 공식 저장소는 전문가 검증 자료를 설명하지만 다운로드에 이름·소속·목적을 포함한 이메일 신청을 요구한다. 현재 접근 승인된 자료로 취급하지 않으며 신청이나 연락을 수행하지 않았다. [공식 저장소](https://github.com/bytedance/MedLesionVQA)

Med-CMR 공식 저장소에서 과제·leaderboard는 확인했지만 실제 평가 자료의 공개 연결은 확인하지 못했다. 표의 Medgemma-4B를 MedGemma 1.5 결과로 옮기지 않는다. MedXpertQA는 공식 카드에 MM schema와 영상 archive를 명시하지만, 접근성이 좋다는 이유만으로 일반 MCQ 평가를 다음 연구로 정하지 않았다. [Med-CMR](https://github.com/LsmnBmnc/Med-CMR), [MedXpertQA 공식 카드](https://huggingface.co/datasets/TsinghuaC3I/MedXpertQA/blob/main/README.md)

## 우선 후보: 자연 영상쌍과 실용 추론 조건의 분리

MediConfusion 공식 설명은 176쌍의 두 영상이 같은 질문·선택지를 공유하면서 정답은 다르다고 명시한다. pair의 두 답을 모두 맞히는 set accuracy와 같은 답을 내는 confusion을 보고한다. 단순 marginal accuracy보다 영상별 판별을 드러내는 구조다. 원문은 embedding 공간에서 혼동되는 쌍을 설명하므로 이를 모두 육안으로 비슷한 영상이라고 단정하지 않는다. [공식 저장소](https://github.com/MShahabSepehri/MediConfusion), [ICLR 2025 논문](https://arxiv.org/abs/2409.15477)

공식 저장소에는 MC·greedy·prefix scoring 등 여러 평가 경로와 원 출처 영상 다운로드 스크립트가 있다. README의 영상 규모는 약26 MB다. 다운로드 스크립트와 answering entry point의 원문 접근까지 확인했지만, 실제 metadata·source-document 연결과 scoring 의존 코드를 아직 대조하지 않았다. [download.py](https://raw.githubusercontent.com/MShahabSepehri/MediConfusion/main/scripts/download.py), [answering.py](https://raw.githubusercontent.com/MShahabSepehri/MediConfusion/main/scripts/answering.py)

가까운 후속 방법 DoubleTake는 ROCO reference triad와 confidence 기반 집계, pair-level adjudicator를 사용한다. 논문 Table 4 설명에서 pair adjudicator 제거 시 set accuracy가 43.75%에서 27.84%로 내려간다. 논문 자체도 confusion-pair 구조가 모든 사용 상황에서 주어지는 것은 아니라고 제한한다. 따라서 전체 방법의 향상을 단일 영상 판별 개선과 동일시하면 안 된다. 반대로 이 사실만으로 선행 결과를 무효라고 단정하지 않는다. [DoubleTake, Sections 3.3·5.4·6](https://arxiv.org/html/2602.02894v1)

이것이 다음 판단을 바꾸는 핵심이다. **상대 평가 영상 없이 작동하는 강한 baseline 이후에도 중요한 실패가 남는지**를 확인할 수 있어야 한다. 서로 다른 정답이라는 benchmark 구성 정보를 이용해 강제로 다른 답을 배정하는 규칙은 실용 해법이나 시각 능력의 증거가 아니다. 또한 낮은 confusion만으로 개선을 주장하지 않고 개별 정확도·set accuracy·coverage를 함께 봐야 한다.

# 다음 라운드의 범위와 종료점

남은 일은 광범위한 문헌 탐색이 아니다. 공식 metadata·scoring 코드를 통해 다음을 결정한다.

- pair/영상/원천 문서의 중복과 독립 분석 단위, 실제 사용 가능한 자료를 확인한다.
- 직접 생성과 공식 prefix scoring이 어떤 실패를 구분하는지 확인한다. text-only·선택지 순서·단순 prior 보정이 필요한 대조인지 정한다.
- DoubleTake의 pair 정보와 외부 reference가 없는 조건에서 연구 질문이 남는지 판단한다. 단일 영상 결과와 pair 정보를 사용하는 진단 결과를 분리한다.
- 유한한 자료에서 판단 가능한 효과·정밀도와 요청량을 산출한다. 기존 짧은 출력 또는 긴 출력 처리량을 새 작업의 실측처럼 쓰지 않는다.

식별 가능한 질문이 남으면 실제 출력 diagnostic의 완성된 계획을 작성한다. 기존 baseline으로 질문이 소진되거나 자료가 구분을 허용하지 않으면 후보를 보류한다. 자료부터 대규모로 확보하는 setup이나 retrieval bank 재구축은 자동 발주하지 않는다. 로컬 실제 출력 근거가 없으므로 현재 limitation_ids는 비우며 method gate를 우회하지 않는다.

# 인계·코드·자원 경계

두 RETRACTION 원문을 읽었다. 후자의 image_redo_01~25 및 redo_26 일부 무효화가 우선한다. iter_051~052에서 처리한 인계를 이번에 반복하지 않으며 무효 감사를 새 근거로 사용하지 않는다. 현재 구현 담당 Claude 복귀는 iter_053 리뷰 기록과 일치한다.

`research/`의 clean status와 tracked file 목록, HEAD `7217b7045f48f95d8dc9b750544634e1c28d4f5c`를 확인했다. iter_053 원본 code_assets에서 parser의 제한 승인과 실행기·gate·재개 비용·평가 봉인의 needs_fix를 확인했다. 아직 사용할 실행 경로를 확정하지 않았으므로 파일 반입이나 재사용 승인을 요청하지 않는다. 다음 구현 계획에서 선택한 모듈의 실제 코드·의존성과 필요한 수정만 확인한다.

후속 GPU 진단을 선택하면 허용된 두 GPU에서 실제 입력의 peak·처리량을 측정하고 batch 확대 또는 GPU당 복수 worker를 비교한다. 연구 질문과 요청량을 먼저 정하며 임의 시간 상한은 두지 않는다.

# 대규모 GPU 필요 후보

다양한 modality의 자연 반사실적 영상쌍과 임상 판별 근거를 사용해 visual encoder·projector·language decoder를 공동 적응하는 방향은 장기 후보로 남긴다. 현재 encoder 병목이나 그 학습의 필요성은 확인되지 않았다. 두 3090에서 가능한 실제 출력 비교와 강한 직접 SFT의 필요성 판단이 먼저다.

이번 문헌은 조사 근거이며 사용자 논문 추천이 아니다. 파일 생성·수정, 자료 다운로드, 모델 추론 및 GPU 실험은 수행하지 않았다.

## 다음에 파고들 질문
- MediConfusion 공식 metadata와 다운로드·평가 코드에서 pair, 영상, 원천 문서의 연결은 어떻게 정의되는가? 중복 cluster와 개발 분리를 반영해 실제로 어떤 규모의 paired 비교가 가능한가?
- 공식 MC·greedy·prefix scoring 및 단순 text-only prior 대조는 시각 판별 부족과 답변 선택 문제를 구분할 수 있는가? 후보가 기존 scoring의 재적용에 그치면 어떤 기준으로 투자를 종료할 것인가?
- DoubleTake의 pair adjudicator·reference bank 조건을 분리했을 때 상대 평가 영상 없이 남는 중요한 실패 조건은 무엇인가? 해당 조건을 평가쌍의 정답 구조를 노출하지 않고 검사할 수 있는가?
- 위 질문이 식별 가능하다면, 어떤 최소 실제 출력 비교·효과 및 정밀도 기준·요청량으로 diagnostic을 끝내고 방법 pilot 검토 또는 투자 보류를 결정할 것인가? 선택할 기존 실행 모듈의 필수 수정 비용까지 포함해 판단한다.
