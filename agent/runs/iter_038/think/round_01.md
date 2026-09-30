# 사고 라운드 1

## 이번 판단

같은 RSNA 개발800의 분석과 새 loss 투자는 종료한다. 다음 후보는 **소견 문장과 영상 영역의 대응**으로 좁히되, 아직 구현에 넘기지 않는다. 과제 자체의 선행연구가 있고, 실제 대응 정답을 제공하는 자료와 단순 baseline 이후의 식별력이 확정되지 않았다. 추가 조사는 이 두 조건을 판정하는 데 한정한다.

이번 라운드는 파일·Git·문헌의 읽기 전용 조사였다. 코드 수정, 파일 생성, 모델 로딩, GPU 실험, 데이터 다운로드는 하지 않았다.

## 기존 결과에서 유지할 사실

- `agent/GOAL.md`, `agent/GPT_USAGE_POLICY.md`, `agent/REPORTING_STYLE.md`, 직전 `iter_037/review.md`와 `review.json`, 관련 LIMITATIONS·CODE_ASSETS 및 이전 진단 원문을 확인했다.
- iter_037 개발800에서 detector17의 선택점→budget1.0은 SFT-only GT 77→23개, FP/환자 0.295→1.0075였다. detector의 높은 IoU 정밀도와 SFT의 낮은 IoU F1 사이 trade-off를 유지한다. 이는 새 언어 과제의 효용이나 외부 일반화를 증명하지 않는다. 출처: `agent/runs/iter_037/review.md`.
- iter_016의 B0−M0 차이는 strict −0.255에서 semantic −0.0317로 줄었다. 답변 형식 실패를 의미 능력 손실로 해석하면 안 된다. 출처: `agent/runs/iter_016/review.md`.
- iter_017에서는 검출 정보와 개수의 효과가 있었지만 L/K의 환자별 정답 쌍 성패는 600명 모두 같았다. 좌표 추가의 가치나 일반적인 좌표 무사용은 입증되지 않았다. 출처: `agent/runs/iter_017/review.md`.
- iter_018의 CheXpert E48 손실은 6.25 pp, 95% CI [−6.25, 18.75] pp였다. F105는 미실행이다. 단일 finding 질문에서 무관 evidence를 제거하면 direct와 같아지므로, 이 설계의 단순 반복으로 새 방법의 필요성을 증명할 수 없다. 출처: `agent/runs/iter_018/plan.md`, `review.md`.
- iter_025의 bbox oracle은 90% gate를 통과하지 못했다. 사분면 이름 제공의 성공은 좌표 해석·산술 원인을 분리하지 못한다. iter_027의 다중 사분면 직접 선택 0/66 대 bbox+규칙 26/66도 이 한계를 유지한다. 출처: `agent/runs/iter_025/review.md`, `agent/runs/iter_027/review.md`.
- legacy의 회색·노이즈 영상에 대한 전제 순응 관찰과 긍정 편향 반증을 읽었다. 작은 비자연적 입력의 관찰이며, 실제 임상 영상에서 정상 사용을 통제한 새 한계의 근거로 승격하지 않는다. 출처: `legacy/docs/MEDGEMMA_평가_전체정리.txt`의 중대 정정 및 §9-3/9-4.

## Strategy Check / 연구 방향 판단

중요한 사용 과제는 보고서의 소견 문장이 실제로 어느 영상 근거에 연결되는지 확인하는 것이다. 검출 목록이 정확하다는 사실과 문장–영역 대응이 정확하다는 사실은 별개다. 다만 이 구분 자체가 새로운 contribution은 아니다.

세 선택을 비교했다.

1. **언어–영상 대응 진단 설계:** 이전 oracle 실패를 피하면서 검출 이후의 역할을 평가할 가능성이 있다. 자연어와 영역 정답을 연결할 수 있는지, 단순 클래스 선택을 넘어서는 사례가 충분한지가 현재 핵심 불확실성이다. 이를 확인하는 조사 가치가 가장 높다.
2. **기존 checkpoint의 범위·형식 전이 진단 연장:** 자산은 있으나 iter_016–018·023–027에서 주요 경쟁 설명과 인터페이스 한계가 이미 드러났다. 문구나 질문 개수만 바꾸는 재실험의 정보 이득은 낮다. 현재는 보류한다.
3. **bbox loss·calibration·ensemble 개선:** 실제 trade-off는 남지만 큰 후보 coverage 차이라는 설명은 약화됐다. 현재 자료에서 새 학습을 시작할 근거가 부족하다. VinDr 승인 후 외부 결과가 달라지면 다시 비교한다.

직전 접근법의 유효 실험 3회 이상은 재평가의 계기이며 자동 포기 사유가 아니다. 이번 전환은 필수 비교가 완료됐고 같은 개발 집단에서 추가로 구분할 설명이 줄었다는 근거에 따른다.

## 새로 확인한 선행연구와 설계에 미치는 영향

- MedVH는 이미 잘못된 영상·임상 전제·false-confidence justification을 평가한다. 단순히 유도 질문에 잘못 동의하는 현상을 MedGemma에서 찾는 것만으로 차별화되지 않는다. [MedVH 원문](https://pmc.ncbi.nlm.nih.gov/articles/PMC12363988/).
- EchoBench는 의료 VLM의 사용자 정보 추종을 평가한다. VIPER는 사회적 압력 등을 걸러내고 영상에 근거해 답하도록 하는 prompt baseline을 제시한다. 따라서 일반적인 오답 유도와 '영상만 보라'는 보정을 새 방향의 핵심으로 선택하지 않았다. [EchoBench](https://arxiv.org/html/2509.20146v1), [VIPER §4.9](https://arxiv.org/html/2509.21979v1).
- 이전에 인용한 Chen et al. 논문을 다시 읽은 이유는 새 후보와 겹치는 정확한 입력·학습 조건을 확인하기 위해서다. 이 논문은 crop 기반 grounding과 VQA, answer-only SFT의 출력 형식 손실, grounding supervision 혼합을 이미 비교한다. 원본 영상과 제안 영역을 함께 쓰는 대응 진단과 구분해야 하며, 단순 혼합 SFT를 신규 기여로 주장할 수 없다. [Why Does Grounding Hurt Medical VQA? §§III-D–E, IV](https://arxiv.org/html/2604.27720v2).
- uMedGround는 보고서에서 진단 phrase를 찾아 영역에 연결하는 과제를 이미 제시하며 BOX token·별도 decoder·불확실성 예측을 사용한다. 그러므로 '보고서 문장에 bbox를 붙인다'는 과제명이나 decoder 추가 자체는 차별점이 아니다. [uMedGround 원문](https://arxiv.org/html/2404.06798v3), [공식 저장소](https://github.com/Cocofeat/uMedGround).
- 같은 논문의 §IV-A1·IV-C에서 MRG-ChestX-ray8의 984개 보고서는 원래 임상 보고서가 아니라 짧은 phrase를 GPT-4로 확장한 것임을 확인했다. 공개됐다는 이유만으로 실제 다중 소견의 문장–영역 결합 정답으로 채택하면 안 된다. 이 자료는 합성 문맥에 대한 제한적 진단 후보일 뿐이다. [자료 구성 근거](https://arxiv.org/html/2404.06798v3#S4.SS1.SSS1).

위 문헌은 조사 근거다. 이번 방향의 실제 긍정적 실험 근거가 없어 사용자 논문 추천으로 처리하지 않는다.

## 자료 후보를 좁힌 결과

- **ChestX-Det:** 공식 저장소는 NIH 유래 3,578영상, 13개 category, box·polygon 주석을 설명한다. 공개 schema의 `syms/boxes/polygons`는 확인했지만 자연어 보고서–영역 대응 주석은 제시하지 않는다. 클래스명과 위치로 만든 QA를 자연어 임상 추론의 증거로 바꾸면 안 된다. NIH 기반이므로 기존 NIH·RSNA와의 원천 중복도 검사해야 한다. 저장소의 Apache-2.0 표시를 모든 원천 영상의 접근 조건 확인으로 대신하지 않는다. [공식 ChestX-Det](https://github.com/Deepwise-AILab/ChestX-Det-Dataset).
- **PadChest-GR:** 4,555 study에 소견 문장과 양성 소견의 영역을 제공해 과제와 더 잘 맞는다. 논문은 요청을 통한 배포를 명시한다. 현재 이용 권한·로컬 파일은 확인되지 않았다. 새 접근 신청을 대신 수행하거나 즉시 사용 가능한 자료로 간주하지 않는다. [PadChest-GR 논문](https://arxiv.org/abs/2411.05085), [공식 배포 페이지](https://bimcv.cipf.es/bimcv-projects/padchest-gr/).
- **MS-CXR:** 문장–영역 대응 후보이나 MIMIC 원천 연결과 현재 접근 권한이 확보됐다는 근거가 없다. 공식 페이지의 세부 구간 재조회도 도구 오류가 있어 접근 조건 전체를 확인했다고 보고하지 않는다. [공식 MS-CXR](https://physionet.org/content/ms-cxr/1.1.0/).
- **uMedGround 배포본:** 공식 README의 배포 안내와 논문을 확인했다. `ln_data` 하위 목록 조회와 readme raw 조회는 실패했다. 이는 자료가 없다는 증거가 아니다. 실제 주석의 문장 수·대응 cardinality·환자 분할·라이선스는 아직 검증하지 못했다.
- `legacy/eval_samples`와 `research/results`의 파일명 검색에서는 새 PadChest/MS-CXR/ChestX-Det 자산을 찾지 못했고 기존 SLAKE 소표본만 확인했다. 검색 범위 밖의 서버 자료나 사용자 권한 부재를 뜻하지 않는다. CheXpert의 기존 D16/E48/F 분할도 확인했으며 F는 그대로 보존한다.

## 다음 조사에서 판정할 후보의 구체적 조건

검토할 것은 같은 영상에서 서로 다른 소견 문장이 서로 다른 근거 영역을 요구하는 경우다. 특히 단순 category 분류만으로 대응이 끝나는 사례와, 동일 category의 여러 영역 또는 문장 내 위치·속성이 대응을 바꾸는 사례를 구분해야 한다.

좌표 산술 실패를 반복하지 않도록 검출·영역 인식·문장 대응을 별도로 측정할 수 있는 인터페이스가 필요하다. 예를 들어 원본 영상과 번호가 붙은 후보 영역을 제공해 영역 ID를 선택하게 하는 방식은 후보지만, 표시 자체의 교란과 oracle 해석 가능성을 개발 자료에서 검증해야 한다. 이 인터페이스의 성능은 아직 확인하지 않았다.

문장별 독립 실행, 클래스·위치 규칙, image–text 유사도와 전역 matching이 강한 단순 비교군이다. 이들로 충분히 해결된다면 복잡한 결합 방법의 필요성이 약해진다. 반대로 개별 인식은 유지되는데 실제 대응 오류가 반복되면 그때 validated 한계를 확보하는 출력 진단을 설계한다. 자료가 단일 phrase·단일 box 위주이거나 합성 문장에만 의존하면 현재 후보의 우선순위를 낮춘다.

## 코드·자산 확인과 보존

현재 연구 HEAD는 `755ec06e17606936422f1595f7bf62dc53085e59`이며 status와 diff 출력은 비어 있었다. 현재 파일 목록과 `rsna_diag/generate.py`의 공식 chat template 호출·고정 revision·EOS/cap 처리를 확인했다.

- `iter_037/review.json`은 geometry·parser·metrics·sft_eval의 현재 RSNA 범위 승인을 유지한다. 새 데이터나 전체 실행기 승인이 아니다.
- `iter_035/review.json`의 detector 보조 함수 승인과 실행기·selection·latency의 needs_fix 범위를 확인했다. 새 과제에서 실제 사용할 때만 해당 결함을 수정한다.
- `4e453bbba4b0e798c0deeb6a940644dd62707fa3`의 `rsna_diag/cx18_spec.py`, `qa_spec.py`가 보존돼 있음을 `git show`로 확인하고 내용을 읽었다. whole-string parser와 기존 finding 규약의 제한 승인이다. 현재 브랜치에 없다는 이유로 재구현하지 않는다.
- 현재는 실행 과제·반입 범위를 확정하지 않았으므로 `reuse_assets=[]`다. 다음 implement 계획에서 필요한 파일과 전체 의존성을 선정하고 실제 SHA·필수 검사를 명시한다.

## 추가 라운드가 필요한 이유와 종료 조건

남은 문제는 문헌 목록을 더 늘리는 일이 아니다. **검출 이후의 문장–영역 대응을 구분할 실제 주석이 있는지, 그리고 그 과제가 강한 모듈형 비교 이후에도 연구 투자 가치가 있는지**가 미해결이다. 답에 따라 데이터 선택·연구 질문·실험 역할이 달라진다. 데이터의 의미를 확인하지 않은 채 Claude에게 benchmark 구축과 방법 판단을 넘기지 않는다.

다음 라운드는 uMedGround의 실제 자료 구조와 PadChest-GR/MS-CXR의 주석 정의, 단순 matching 대조의 식별력에 집중한다. 적격 자료·접근·비교군을 확보하면 표본 정밀도에 따른 단계적 GPU diagnostic으로 확정한다. 확보하지 못하면 같은 소견 대응 후보를 자동 연장하지 않고 다른 질문과 필요한 접근 요청의 가치를 비교한다. 광범위한 데이터 수집이나 새 학습은 시작하지 않는다.

구현 진입 시에는 두 GPU에서 같은 development 요청의 batch 확대 또는 GPU당 복수 worker를 비교하고, 실제 peak와 worker당 2GB 여유·처리량·출력 정합성으로 배치를 선택한다. 본실험 시간은 요청 수와 실측 처리량으로 정하며 임의 시간 상한을 두지 않는다. 현재는 표본·과제 미확정이므로 wall-clock을 확정 수치로 제시하지 않는다.

VinDr 승인 전 다운로드·평가·반복 승인 질문을 하지 않는다. continuation 추가 투자 종료, MRI F139, CheXpert F105와 기존 reserve, 모든 checkpoint·원본 결과를 보존한다.

## 대규모 GPU 필요 후보

자연어 소견·영역·전체 보고서를 함께 학습하는 vision encoder–언어 모델 공동 post-training과 일반 능력 보존 혼합 학습을 후보로 남긴다. 현재 그 필요성은 입증되지 않았다. 정상 사용·직접 SFT·모듈형 baseline 이후의 재현되는 잔여 오류가 확인될 때 경량 적응과 비용을 비교한다.

## 다음에 파고들 질문
- uMedGround의 ln_data 배포본과 §IV-A1의 원자료 정의에서, 영상 하나에 구별되는 여러 문장–영역 대응이 실제로 존재하는가? 단일 phrase 확장뿐이면 이 자료를 결합 오류 진단에서 제외하고, 대응 cardinality·환자 분할·원천 중복을 확인한다.
- PadChest-GR·MS-CXR의 주석 정의와 공개 예시에서 클래스명만으로 해결되지 않는 문장–영역 대응을 어떻게 정답으로 보장할 수 있는가? 양측성·동일 category 다중 영역·문장별 복수 box와 판독자 차이를 평가 가능한 형태로 구분하지 못하면 후보를 보류한다.
- 문장별 독립 처리, detector+VLM, 클래스·위치 규칙 및 image–text matching을 함께 두었을 때 어떤 결과가 새 post-training 투자와 단순 모듈형 해결을 구분하는가? uMedGround·MedRPG·MAIRA-2의 입력·학습·평가 조건과 대조해 최소 실제 출력 실험 또는 후보 중단으로 결론낸다.
