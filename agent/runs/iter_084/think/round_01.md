# 사고 라운드 1

# 이번 라운드의 핵심

우선 질문은 **누락 감소와 언급 성향의 분리**다. 다만 RSNA 수동 평가를 그대로 확대하고 CURE 단일 prompt를 추가하는 설계는 아직 확정하지 않는다. 정답 의미와 강한 기존 판독 조건이 연구 해석을 바꾼다는 근거를 확인했다.

## 기존 관찰 인계

`agent/GOAL.md`, `agent/runs/iter_083/review.md`, 관련 iter_012/016/017/035/036/046/047/048의 `review.json`, `agent/LIMITATIONS.md`의 관련 항목과 `agent/CODE_ASSETS.md`를 확인했다.

- iter_012: 직접 RSNA LoRA의 grounding 개선은 유효한 자산이다. 실패한 추가 loss와 가중치의 가치를 혼동하지 않는다.
- iter_016/017: 형식 정규화와 검출 정보 전달의 효과를 확인했지만 자유 판독문의 정확성은 검증하지 않았다. 좌표 추가 효과의 부재도 그 yes/no 인터페이스 범위다.
- iter_035/036: detector의 위치 정밀도·속도와 threshold 아래 후보 coverage를 확인했다. 판독문 전이의 반증이나 모든 metric에서의 detector 우위가 아니다. 관련 iter_037 정정도 유지한다.
- iter_046/048: 같은 annotation의 모듈형 적응과 직접 공동 형식 학습이 강한 대안이었다. 문장별·공동 bbox 투자의 보류를 판독문 연구 전체로 확장하지 않는다.
- iter_047: 자료 수와 원 oracle gate 미달로 본평가가 미실행이었다. 보고서 교정 전체의 실패가 아니다.
- iter_083: 실제 영상 연결·학습·평가가 없었다. 이번 사용자 우선순위 때문에 자료 복구를 보류하며 과학적 기각으로 바꾸지 않는다.

## 수동 결과의 한정 검증

다음 원문을 읽었다: `research/results/manual_rsna_report_transfer_20261006/RESULTS.txt`, `protocol.json`, `summary.json`, `paired_assessments.json`, `manual_experiments/rsna_report_transfer/README.md`, `run.py`의 입력·실행 경로.

읽기 전용 재집계에서 각 raw JSONL은 고유 ID 60개였다. paired assessments에서 표적 present+possible은 양성 7→10, 정상 0→1, 다른 이상/표적음영음성 6→7로 재현됐다. present만 세면 각각 7→6, 0→1, 5→3이었다. annotations SHA256은 `22ee65eddfe1221441f86b008be9d8d1a7565dbc27e20e4538cdc8050539d077`로 summary와 일치했다.

protocol의 source hash 4개와 code hash 3개가 현재 파일과 일치했다. 원시 생성 시간 합계는 base 441.7978초, SFT 628.8214초였다. 이는 새로운 GPU 실행이나 전처리 tensor·checkpoint 전체 재검증이 아니다. 원문 bootstrap의 양성 차이 95% CI −5~+35 pp는 이번에 다시 계산하지 않았다. 수동 결과를 approved/validated로 승격하지 않는다.

중요한 의미 경계가 있다. 예를 들어 `con_00000540`은 opacity라는 단어가 있어도 effusion/atelectasis로 기술돼 기존 규약상 unmentioned다. 따라서 단어 탐지나 넓은 radiographic opacity 정의로 평가기를 바꾸면 기존 수치와 다른 과제를 측정한다. RSNA 음성은 모든 이상 부재가 아니며, 이 자료로 다른 소견 보존이나 전체 판독 사실성을 평가할 수 없다. 양성 언급 증가의 상당 부분이 불확실 표현과 연결된다는 관찰은 남지만, 영상 인식 개선·망각 모두 미확정이다.

## 가까운 선행에서 확인한 것

[CURE 논문](https://arxiv.org/html/2601.15408v1)은 정상 영역을 포함한 학습과 curriculum을 제안하며, MIMIC-CXR·PadChest-GR 등의 과제 및 외부 평가를 구분한다. 논문 §9.2.4에서는 단일 GRG의 낮은 recall과 영역별 출력 결합의 이점을 직접 논의한다. 따라서 단일 GRG 실패를 CURE 전체의 판독 실패로 해석하면 안 된다. 본문에 precision–recall trade-off가 이미 있으므로 그 존재만으로 새 기여를 주장할 수 없다.

[CURE model card](https://huggingface.co/pamessina/medgemma-4b-it-cure)와 [adapter config](https://huggingface.co/pamessina/medgemma-4b-it-cure/blob/main/adapter_config.json) 모두 base가 `google/medgemma-4b-it`임을 확인했다. config는 rank16, alpha32이며 `lm_head`·`embed_tokens`도 저장한다. RSNA의 언어층 adapter 로더와 동일시하지 않는다. base revision 필드는 null이므로 실행 전 실제 revision 고정이 필요하다.

[공식 README](https://raw.githubusercontent.com/PabloMessina/CURE/main/README.md)와 [공식 notebook](https://raw.githubusercontent.com/PabloMessina/CURE/main/notebooks/inference/Load%20and%20run%20CURE%20from%20Hugging%20Face.ipynb)은 NF4 quantization, 전용 영상 변환, 448×448 및 고정 CLAHE 설정을 제공한다. 좌표는 normalized cxcywh다. RSNA의 값 보존 전처리를 그대로 적용한 결과를 공식 재현이라고 부를 수 없다. RSNA 적용 자체도 원 논문 benchmark 재현과 구분할 확장 실험이다.

[MAIRA-2](https://arxiv.org/html/2406.04449v2)는 grounding 유무와 실제 reporting context를 고려하며, 문장별 correctness와 completeness를 평가한다. grounding 점수와 판독 완전성을 분리해야 한다는 설계 근거다. 이번 라운드에서 MAIRA-2 checkpoint 실행 경로까지 검증한 것은 아니다.

추가로 [Does Grounding Improve Radiology Report Generation?](https://proceedings.mlr.press/v315/aas-alas26a.html)을 확인했다. 공개 초록은 PadChest-GR에서 전체 영상과 grounding mask 및 region-to-text 조건을 비교하고 임상·언어 지표 개선을 보고한다. 단순 'grounding이 판독을 개선하는가'는 이미 직접 다룬 질문이다. 다만 PDF 조회가 실패해 추론 시 영역 제공 조건·정답 노출·분할·예산 대조는 아직 확인하지 못했다.

[Phrase-grounded APO](https://openaccess.thecvf.com/content/CVPR2026/html/Mahmood_Phrase-grounded_APO_for_Improving_Chest_X-ray_Report_Generation_CVPR_2026_paper.html)는 공식 검색 결과에서 위치와 소견을 함께 다루는 preference 학습 연구로 발견했다. 본문 접근은 403이어서 성능·공정성·우리 질문 해결 여부를 판정하지 않는다. 이 논문들 확인은 조사 기록이며 사용자 논문 추천이 아니다.

## Strategy Check / 연구 방향 판단

이어받는 관찰 → grounding 개선은 검증됐지만 자유 판독의 언급 변화는 불확정이다.

남은 경쟁 설명 → 영상에 따른 구별 개선, 긍정 언급 성향 이동, 불확실 표현 증가, 평가 target 의미 차이.

이번에 좁힌 비교 → 정확한 base→adapter 비교와 CURE의 강한 공식 판독 조건을 사용해 누락·잘못된 언급을 분리한다. 조건이 다른 시스템 순위를 방법 효과로 바꾸지 않는다.

세 초기 질문의 우선순위는 다음과 같다.

1. 누락 감소 vs 언급 성향: 실제 수동 관찰과 직접 연결되고 기존 자산이 있어 우선한다. 다만 RSNA만으로 인식 기전이나 전체 판독 정확성을 입증하지 못한다.
2. 위치–문장 연결: 명시적 문장 정답이 필요하며 PadChest-GR 재사용 가치가 있다. CURE 이후 남는 문제가 무엇인지 먼저 좁혀야 한다.
3. 학습 범위 밖 전이·보존: 중요하지만 현재 RSNA 라벨로 다른 소견 손상을 측정할 수 없다. 첫 실험의 포괄적 결론으로 넣지 않는다.

현재 방법 개선은 아직 발주하지 않는다. 새 loss보다 관찰 의미와 기존 해결책 충분성을 구분할 가치가 크다. MRI나 다른 modality로의 새 후보 탐색도 이번에는 선택하지 않는다. 다만 문헌상 이미 알려진 trade-off를 RSNA에서 재발견하는 것만으로 장기 투자를 정당화하지 않는다.

다음 판단은 단순 문헌 추가가 아니다. RSNA의 좁은 target 평가를 첫 실험으로 사용할지, 문장 정답이 있는 자료에서 동일 질문을 구체화할지를 결정해야 한다. 이는 후속 방법의 주장과 대조군을 바꾸므로 high로 남은 전략 판단만 수행한다.

## 코드와 실행 자산

현재 연구 브랜치는 `approach/mri-local-context-evidence`이며 `git status --short` 출력은 비어 있었다. 자동 기반 후보 iter_082의 `ee8078ab0acba94f0d84d3ab2997e76eeb117bb9`에는 `rsna_diag/`가 없다. 현재 작업 폴더에 보이는 파일이 새 기반에도 있다고 가정하면 안 된다.

iter_043의 `b50aa230a86c6d5b6c6b280fe718170ce4ecf220`에서 `rsna_diag/generate.py`, `geometry.py`, `lora.py`, `prompts.py`, `queue_lock.py`, `__init__.py`의 blob 존재와 import를 확인했다. 원 review는 제한된 생성 helper와 LoRA 경로를 승인하지만 옛 CLI 전체를 승인하지 않는다. 수동 protocol이 잠근 현재 generate/lora와 이 과거 blob의 hash도 다르다. 최종 구현 계획에서는 사용할 버전을 선택하고 개별 반입·회귀 검사를 명시해야 한다. 아직 재사용 manifest를 확정하지 않았다.

수동 run.py는 결과 경로가 고정돼 있고 GPU ID를 직접 설정한다. 그대로 재실행하지 않고 원본을 보존해야 한다. 최종 실행기는 상속된 GPU 집합, worker별 출력, 현재 입력 hash 검증, 중단 재개를 갖춰야 한다. 새 학습은 아직 없다.

## 대규모 GPU 필요 후보

정상·비정상 anatomy와 report-only/joint supervision을 여러 모델·데이터에서 같은 노출량으로 비교하는 대규모 factorial 학습은 장기 후보로 보존한다. 현재 두 GPU에서는 공개 checkpoint와 기존 adapter의 실제 출력으로 필요한 비교를 좁힌 뒤 경량 적응을 검토한다.

## 다음에 확인할 범위

새 modality 탐색과 전체 이력 재독해는 하지 않는다. CURE의 공식 hybrid 평가 경로, 위 PadChest-GR 연구의 실제 입력 조건, 로컬 PadChest-GR 문장 정답과 기존 split만 확인한다. 자료 점검에서 성립하는 평가 단위를 정하면 같은 계획에 공식 모델 소규모 출력과 조건부 확대를 묶는다. 계획/리뷰는 계속 read-only이며 설치·실험은 수행하지 않았다.

## 다음에 파고들 질문
- RSNA의 기존 표적 정의를 유지한 평가로 언급 성향과 정답 구별의 차이를 충분히 측정할 수 있는가? paired_assessments의 모호한 사례와 로컬 PadChest-GR 문장 정답을 대조해 첫 자료·주평가 단위를 하나로 확정한다.
- CURE의 단일 GRG와 공식 AGRG+GRG 중 어떤 조건이 첫 연구 질문의 필수 강한 대조인가? 공식 평가 코드와 논문 §9.2.4를 연결해 base→adapter 비교 및 시스템 비교의 범위와 요청량을 정한다.
- PadChest-GR의 최신 grounding 연구는 추론 시 정답 영역을 제공하는가, 학습 supervision만 추가하는가? 원문 조건을 확인해 기존 방법이 이미 답한 부분을 제외하고, 첫 실제 비교의 양성·음성·불확정 결과가 최소 방법 시험 또는 투자 보류로 연결되도록 확정한다.
