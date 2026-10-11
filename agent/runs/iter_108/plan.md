# 요약

- **이번에 할 일:** 원본 흉부 X-ray에 예측 영역 영상을 더 주었을 때, 표적 음영 판단과 전체 비정상 판단이 어떻게 달라지는지 비교한다.
- **필요한 이유:** 기존 텍스트 근거의 이득은 질문 범위와 인터페이스에 의존했다. 실제 영상 영역 제공의 효과는 그 실험으로 판단하지 못했다.
- **확인할 기준:** 원본 복제·같은 크기의 중앙 crop 및 질문별 고정 입력 선택 이후에도 중요한 차이가 남는지 본다.
- **주의·다음:** frozen 진단이며 새 방법이 아니다. 단순 대안이 충분하면 방법 투자는 보류한다. 리뷰 뒤 다음 반복은 사용자 승인을 기다린다.

## 알림 맥락

- 연구: 위치 근거와 판독 판단의 연결
- 데이터: 흉부 X-ray, 기존 RSNA 개발 P180/E600
- 모델: MedGemma 1.5 frozen reader와 저장된 RSNA grounding SFT 예측
- 과제: 원본과 보조 영역 영상을 보고 표적 음영 유무·전체 비정상 여부에 각각 답한다
- 가설: 국소 근거의 이득과 손상은 질문 범위에 따라 다르며 단순 입력 선택으로 설명될 수 있다
- 질문: 특정 음영을 찾은 영역을 더 보여 주면 그 판단을 돕고 다른 이상 판단도 보존하는가?
- 변경: 방향 전환
- 연결: PadChest-GR의 자연 다중 영역은 CURE가 보존했다. 같은 누락 가설을 연장하지 않고 RSNA의 명확한 두 판단 정답으로 외부 영상 근거의 효과를 비교한다
- 작업: 저장 예측을 재사용해 원본·복제·예측 영역·중앙 영역을 비교하고 추가 방법이 필요한지 결정한다

# Current Understanding

iter_107의 핵심 10명에서 CURE 두 영역 보존 10/10, 부분 누락 0을 받아들인다. 비핵심 재분류·threshold 변경·환자 교체와 iter_105/106 확장 입력 재시도는 하지 않는다.

iter_017에서는 같은 RSNA 원본을 제공해도 텍스트 근거의 효과가 질문과 문구에 의존했다. 좌표 L과 개수 K의 정답 쌍은 600명 모두 같았고, NoOpacity/NotNormal 집단의 정답 쌍은 direct 40/200에서 L 4/200으로 낮아졌다. 이것은 시각적 crop 제공의 결과가 아니다.

이번 자료의 정답은 원본 영상에 대한 RSNA category다. opacity=(O=yes,A=yes), normal=(no,no), not_normal_no_opacity=(no,yes)다. 영역의 임상 진위나 자유 판독 전체를 평가하지 않는다. bbox가 비었다고 정상으로 간주하지 않는다.

# Strategy Check / 연구 방향 판단

**기술 질문 → 실패 조건 → 공개 정답 비교 → 주장 범위:** 불완전한 표적 근거를 시각적으로 제공할 때, 원본이 남아 있어도 질문 범위별 손익이 생기는가 → 표적 판단 이득과 전체 비정상 판단 손상이 함께 나타나는 조건 → 동일 환자의 O/A 정답으로 복제·크기 일치 crop·고정 입력 선택을 비교 → 현재 frozen 모델·예측 영역·RSNA 개발 자료의 입력 정책 효과로 한정한다.

후보는 두 개만 비교한다.

1. **국소 근거의 판단 가치 — 선택.** 실제 사용 문제는 localizer의 선택된 영역을 reader에 제공할 때의 이득과 손상이다. 근거 prompting·전체 영상+grounding·crop VQA는 선행 범위다. 이번에 구분할 설명은 영상 수, 확대, 위치 선택, localizer 오류와 질문 범위다. 공개된 두 label과 기존 저장 예측으로 평가가 성립한다. 고정 입력 선택이 충분하면 복잡한 결합 방법에 투자하지 않는다.
2. **위치 학습의 판단 전이 — 보류.** 위치 출력과 판독 출력의 차이는 남아 있지만 report-only baseline·선택 조건·의미 평가 혼선이 해결되지 않았다. 형식 rehearsal과 공동 학습 성공도 선행에 있다. 새 LR·seed를 추가할 정보 가치는 현재 더 낮다. 동일 정보·정답·학습 대조로 기존 설명을 줄일 새 근거가 있을 때 재검토한다.

**시험 설정:** 기존 LoRA recipe를 구제하지 않는다. 이번에는 frozen reader와 저장된 localizer 결과만 사용한다.

**연구 관찰:** 107의 성공과 17의 텍스트 인터페이스 의존을 함께 유지한다. 이번 비교는 같은 누락 현상의 재현이 아니라 외부 영상 근거라는 새 개입이다.

**연구 질문:** 작은 입력 효과 자체가 contribution은 아니다. 단순 routing으로 이득·보존이 해결되는지를 먼저 받아들인다. 현재 질문 범위는 이미 알려져 있으므로 routing 성공을 새로운 능력으로 포장하지 않는다.

지배 비용은 새 다중 영상 생성과 변경 경로 검증으로 예상한다. 실제 비율은 미측정이다. 과거 전체 이력·불변 코드를 다시 감사하지 않는다.

# Hypothesis

- H1: 예측 영역 T는 원본 복제 D보다 O 판단을 개선할 수 있다.
- H2: 같은 T가 A 판단, 특히 not_normal_no_opacity에서 손상을 만들 수 있다.
- H3: T와 중앙 영역 C가 비슷하면 위치 선택보다 확대·보조 영상의 일반 효과가 주요 설명이다.
- H4: O에는 유용한 입력, A에는 원본을 쓰는 고정 정책으로 이득과 보존이 함께 달성되면 현재 결합 방법의 추가 필요성은 작다.

기본 판단이 낮거나 localizer가 틀린 경우를 충분한 인식 이후의 결합 실패로 해석하지 않는다. 새로운 내부 원인을 증명하는 실험이 아니다.

# Limitation Evidence / Correct Usage Checks

대상은 observed `rsna-evidence-interface-sensitivity`이며 원본은 iter_017 review.json과 LIMITATIONS.md다. 이번 역할은 diagnostic이다.

reader는 MedGemma 1.5 revision `91850547d9f0b2fdd21aa7c5f4f3d1a8a52c243b`, bf16, greedy다. B0는 이번에 로드·학습하지 않고 저장 bbox만 쓴다. 원본 입력은 기존 값 보존 RGB·square padding을 유지한다.

공식 processor는 다중 영상 입력을 구성할 수 있지만 전체+crop이 공식 검증된 임상 과제라는 뜻은 아니다. 모델 카드의 다중 patch/longitudinal 설명과 일반 다중 영상 평가 제한 문구를 함께 기록한다. 이번은 확장 사용의 통제 진단이다.

Q_O/Q_A, plain 지시, strict 및 semantic_v1을 원본 qa_spec.py에서 가져온다. semantic_v1을 주평가로 사용하고 strict를 함께 보고한다. 설명문을 정답에 맞춰 사후 구제하지 않는다. cap은 기존 QA와 같은 1000→2000→4000, 비EOS는 별도 실패다.

# Contribution Path / Baselines / Reuse

## 선행과 구별 범위

[Visual Evidence Prompting](https://aclanthology.org/2025.acl-long.205/)은 전문 모델 근거를 전달하는 접근이다. [PadChest grounding 연구](https://proceedings.mlr.press/v315/aas-alas26a.html)는 전체 영상과 국소 근거의 이득을 보고한다. [Grounding과 Medical VQA 연구](https://arxiv.org/html/2604.27720v2)는 crop 및 학습 형식 대조를 다룬다. 따라서 이번 구성 자체의 신규성은 주장하지 않는다.

PadChest 논문 PDF 본문은 이번 도구 경로에서 확보하지 못했다. 확인하지 못한 대조가 없다고 가정하지 않는다. 최소 탐색의 목적은 프로젝트에서 후속 방법 투자가 필요한지를 판단하는 것이며, 방법 전환 전에 선행의 상세 중복을 추가 확인해야 한다.

## 강한 단순 대안

- F: 기존 원본 직접 답변.
- R: O에는 T, A에는 F. 빈 예측이면 두 질문 모두 F.
- R_L: O에는 L, A에는 F. 빈 예측이면 F.
- R_B: O는 유효 bbox의 유무 규칙, A는 F. localizer 오류도 전체 분모에 포함한다.
- 기존 iter_017 B/K/L: 같은 환자의 역사적 참조. 새 시각 조건과 안내문이 달라 순수 전달 방식 효과로 해석하지 않는다.

R의 A 보존은 정의상 성립한다. 이를 발견으로 부르지 않고 T의 표적 이득을 단순 정책으로 사용할 수 있는지 판단한다. R_L/R_B의 성공도 받아들인다. 비용은 policy가 실제로 필요로 하는 호출만 계산하며 실험 전체 조건 비용을 배포 비용으로 사용하지 않는다.

## 코드와 결과 재사용

새 브랜치 기반은 재사용 승인 iter_082다. 그 MRI 분석 모듈을 이번 평가기로 사용하지 않는다. 필요한 107 실행 소스와 17 qa_spec은 reuse_assets의 SHA·파일 목록대로 반입한다. 현재 브랜치에 있는 파일이라도 새 기반에는 없음을 확인했다.

`lk105_run.py`의 M15 로딩·보존 패턴, `report86_common.py`의 hash/원자적 저장, `rsna_diag/generate.py`의 load_image/generate, geometry·parser를 한정 재사용한다. 새 wrapper는 결과 root와 요청 생성·다중 영상 연결만 분리하고 기존 실행기를 무관하게 범용화하지 않는다. 구 QA 실행기의 잠금·확대 결함을 계승하지 않는다.

결과 입력은 다음을 잠근다.

- `results/iter_016/manifests/{sets.json,labels.json,infer_manifest.jsonl,checkpoints.json}`
- `results/iter_015/reuse/bbox_B0_concise.jsonl` 및 그 원본 source/protocol 연결
- iter_016의 해당 F 원시 응답·요청·completion
- 역사적 참조에 사용하는 iter_017 응답·요청·completion

출력 재사용 전에 환자·질문·prompt·revision·영상·generation 설정·정확한 요청 집합을 대조한다. 현재 파일 크기만으로 가중치 불변성을 승인하지 않는다.

# Proposed Experiment

## 1. 한정 자료 점검과 동작 확인

기존 P180은 category별 60명, E600은 각 200명이다. 두 집단은 개발 자료이며 P180⊂E600이다. 순서와 구성은 변경하지 않는다.

저장 bbox의 비어 있지 않은 환자는 P180에서 54/1/17명, E600에서 164/5/67명이다. 각각 opacity/normal/not_normal_no_opacity 순이다. 빈 예측의 정책은 F 유지로 고정한다. 새 box를 만들거나 빈 예측 환자를 다른 사람으로 교체하지 않는다.

정식 parser와 source 연결 검사 결과가 위 집계와 다르면 원인을 먼저 보고한다. invalid/truncated를 빈 예측으로 바꾸지 않는다. 입력 결함이 해결되지 않으면 모델 비교를 실행하지 않는다.

기술 표본은 P180 nonempty에서 환자 ID 정렬 기준 opacity 첫 3명, normal 첫 1명, not_normal_no_opacity 첫 2명으로 고정한다. 정답은 연결 확인·층화에만 쓰고 crop 선택에는 쓰지 않는다. 원본·crop overlay, 실제 processor tensor, 질문 연결을 확인한다. 모델의 100% 정답을 요구하지 않는다.

## 2. 영상과 조건 고정

F는 기존 원본 출력이다. 예측 crop은 유효 B0 box 전체의 최소 enclosing rectangle을 square-padded 원본 canvas에서 자른다. yxyx/1000을 pixel로 바꾸고 시작은 floor, 끝은 ceil, 경계는 canvas에 clip한다. 추가 margin·GT 기반 선택·box 개수 제한은 없다. crop은 값 보존 후 square padding하며 별도 수동 확대는 하지 않는다. 실제 resize는 고정 processor가 수행한다.

중앙 crop은 예측 crop과 정확히 같은 pixel 높이·너비를 원본 중앙에서 자른다. 이는 비표적·정상 영역이라는 뜻이 아니다. 위치 선택을 제거한 대조다. T와 C가 동일한 경우도 그대로 보존한다.

신규 조건은 다음과 같다.

- D: 원본 + 동일 원본. O/A 각각 1요청.
- T: 원본 + 예측 crop. O/A 각각 1요청.
- C: 원본 + 크기 일치 중앙 crop. O/A 각각 1요청.
- L: 예측 crop 단독. O만 1요청. 원본 label을 제한된 관측으로 추정하는 정보 제한 대조이며 crop의 임상 음성 판정이 아니다.

D/T/C의 공통 안내문은 다음으로 고정한다: `Image 1 is the complete source chest radiograph. Image 2 is an auxiliary view of the same radiograph and may be a full image or a crop. It is not an independent examination or proof of an abnormality. Answer the question about Image 1 using the available evidence.` 뒤에 기존 질문과 plain 지시를 붙인다. 조건명·정답·box 개수·localizer의 positive 선언은 입력하지 않는다.

L에는 `This is an auxiliary crop from a source chest radiograph. Answer the following question about the source radiograph using this limited view.`와 Q_O/plain을 붙인다. F와 문구·정보량이 다른 제한 대조임을 명시한다.

D/T/C의 첫 영상 tensor가 F의 원본 tensor와 일치해야 한다. processor 자동 crop 수·영상 token·해상도를 저장한다. pixel tensor가 같아도 전체 문맥의 표현이 같다는 주장은 하지 않는다.

## 3. 가능성 탐색: P180

nonempty 72명에 7요청씩 총 504건이다. 기술 표본의 설정 불변 출력은 재사용한다. 빈 예측 108명은 정책상 F를 그대로 사용하며 신규 요청처럼 집계하지 않는다.

주요 비교는 T−D의 O 정확도와 T−D의 not_normal_no_opacity A 정확도다. T−C는 위치 선택의 설명을, D−F는 추가 영상·안내문 영향을 구분한다. R/R_L/R_B 및 F와의 정답 쌍 정확도도 함께 계산한다.

## 4. 조건부 확대: E600

효과를 보기 전에 아래 분기를 코드로 잠근다. P180에서 다음 중 하나이면 E600의 나머지 nonempty 164명으로 확대한다.

- 위 두 주요 비교 또는 T−C의 O 비교에서 절대 차이가 10pp 이상이고, 양쪽 답변이 모두 semantic-valid이면서 답이 달라진 환자가 해당 비교에서 3명 이상이다.
- 위 비교 중 환자 4명 이상에서 semantic-valid 답변이 달라졌고, paired 95% CI가 0과 +10pp 또는 −10pp를 함께 포함하며, 해당 endpoint의 P/E 실제 분모로 `현재 CI 반폭 × sqrt(n_P/n_E)`를 계산했을 때 예상 반폭이 15pp 이하가 된다. 이는 정밀도 계획용 근사이며 결과 CI가 아니다.

10pp는 소수 문구 차이를 넘어 후속 투자에 고려할 탐색 효과, 15pp는 이번 개발 진단의 거친 방향 판단 정밀도다. 통계적 확증 기준이 아니다. 내용상 변화 없이 invalid 처리만으로 조건을 만족한 경우는 확대하지 않는다. 기술 오류는 고쳐 동일 조건을 재개할 수 있지만 parser·질문·표본을 바꾸지 않는다.

확대하면 누적 신규 과학 요청은 236×7=1,652건이다. P180을 포함한 E600은 독립 확인으로 부르지 않는다. 조건을 충족하지 않으면 P180 결과와 탐색 한계를 보고하고 종료한다. 작은 표본의 무변화를 동등성으로 선언하지 않는다.

## 5. 독립 확인과 학습

이번에는 수행하지 않는다. 새 seed·adapter·detector·외부 환자·reserve를 자동 추가하지 않는다. 다른 계열 모델은 첫 실패의 필수 gate가 아니며, 단순 대안 이후 중요한 잔여 관찰이 남았을 때 그 범위를 확인하는 다음 선택으로만 검토한다.

## 6. GPU·비용·재개

시작 직전 nvidia-smi로 허용 장치 0,1의 실제 메모리·UUID를 확인하고 여유가 큰 GPU부터 배정한다. 두 GPU에 독립 환자 shard를 둔다. 다른 프로세스는 변경하지 않는다.

기술 6명의 동일 요청에서 두 GPU 각 1 worker와, 실측 peak 합계에 worker당 2GiB 여유를 더해 수용 가능한 GPU당 2 worker 구성을 짧게 비교한다. admission이 불가능하면 그 수치와 이유를 남긴다. 추가 worker 대신 batch 확대가 더 유망하면 한 가지를 선택하되 전수 탐색하지 않는다. token·parser 결과 정합성, 전체 처리량, 긴 출력 peak·지연, 오류와 CPU/I/O 경합으로 선택한다.

과거 단일 영상 QA 처리량 150–300 req/min을 단순 적용하면 504건은 약 2–4분, 1,652건은 약 6–12분이지만 이번 두 영상 처리량은 미측정이다. 이 수치를 완료 시간 약속이나 상한으로 쓰지 않는다. 기술 실측 요청/분과 loading 시간을 이용해 P/E wall-clock을 다시 산출해 본생성 전에 저장한다. 검증·출처 연결 시간은 별도 기록한다.

새 학습 checkpoint는 없다. 요청별 원시 token·시도·pixel hash, worker별 결과, protocol, 원자적 completion을 재개 지점으로 쓴다. 완료 요청도 현재 입력·소스 연결을 검증한다. 활성 claim을 지우지 않는다. OOM은 batch/동시성을 낮추고 같은 과학 조건으로 재개한다.

# Implementation Tasks for Claude

1. 승인 기반과 reuse manifest를 확인하고 새 결과 root를 `research/results/iter_108`로 고정한다. 기존 결과·checkpoint·정책은 변경하지 않는다.
2. 한정 source/환자/정답/예측 연결과 기술 6명의 영상 검사를 완료한다. 별도 자료 감사 반복을 만들지 않는다.
3. crop·prompt·요청 목록·parser·metric·확대 및 종료 분기를 구현하고 fixture와 독립 계산 예제를 준비한다. 모든 분기 코드와 입력 hash를 본생성 전에 잠근다. 구현자가 추가 수치 문턱을 만들지 않는다.
4. 기존 M15 실행 패턴을 이용해 새 다중 영상 wrapper를 연결한다. 구 실행기 전체를 개편하지 않는다. 파일 크기 기반 가중치 계승, admission 실패 기록 누락, 완료 입력 검사 문제는 이번 경로에서 해소한다.
5. 기술 6명에서 F 재현 12건, 공식 processor tensor 대조, 중단·재개·변조 거부, worker 구성 정합성을 검사한다. F가 재현되지 않으면 원인을 확인한다. provenance가 같은데 실행 환경 차이로 token이 달라지면 저장 F를 주대조로 혼용하지 말고 이번 동일 환경에서 해당 단계 F를 새로 생성한다. 이 경우 추가 비용은 2×180 또는 2×600건이며 실행 전에 이유와 새 예산을 기록한다.
6. P180 및 승인된 조건부 E600을 실행한다. 단계 결정은 해당 endpoint의 결과와 코드 잠금 hash를 연결한다.
7. full-denominator 결과, 조건별 형식 실패, paired 손익, 단순 정책 및 비용을 보고한다. production 함수와 독립적으로 주요 정확도·전이 수·CI를 재계산한다.

# Evaluation (성공/실패 기준 포함)

## 지표

- 주요 endpoint: nonempty 환자에서 T−D의 O 정확도; nonempty not_normal_no_opacity에서 T−D의 A 정확도.
- 위치 대조: T−C의 O 및 A 차이. D−F는 추가 영상과 공통 안내문의 합성 효과다.
- 전체 정책 지표: P180/E600의 category별 정답 쌍 정확도와 균등 평균 S_scope, O의 sensitivity/specificity, A의 category별 정확도.
- 보존 지표: 두 답변 모두 semantic-valid인 correct→wrong 및 wrong→correct 환자 수. invalid로 생긴 전이는 별도 표시한다.
- crop 특성: 면적비, T=C 여부, 유효 box 수, 양성 환자의 GT와 예측 영역 대응을 사전 정의한 기술통계로 보고한다. 이를 결과를 좋게 만드는 후속 subset 선택에 쓰지 않는다.

invalid는 전체 분모에서 실패로 계산한다. 동시에 paired 비교에서 invalid 답을 모두 유리/불리하게 배정한 정확도 차이 범위를 보고한다. 내용 효과의 방향이 이 범위에 따라 바뀌면 형식 영향과 분리되지 않았다고 판정한다. valid-only 성능을 주결과로 대체하지 않는다.

category 내 환자 paired bootstrap 10,000회, seed 10817로 95% 탐색 CI를 계산한다. 모든 조건·질문을 환자 단위로 함께 재표집한다. normal nonempty는 최대 5명이므로 해당 조건의 안정성·동등성 주장을 하지 않는다. 변화 0건에서는 퇴화 bootstrap만 제시하지 않고 사건율의 exact binomial 구간도 보고한다.

## 양성 관찰과 후속

최종 수행 단계에서 주요 차이의 절댓값이 10pp 이상이고 CI가 0을 제외하며, 최소 3명의 semantic-valid 변화와 형식 민감도 검사로 방향이 유지되면 해당 입력 정책 효과의 제한된 양성 근거로 기록한다. T−C·D−F·localizer 오류에 따라 설명 범위를 좁힌다.

T의 O 이득을 R이 그대로 사용하면서 A 손상을 피하고 R_L/R_B가 비슷하거나 더 나으면 단순 대안의 충분성을 받아들이고 새 방법 투자는 보류한다. R의 정의상 보존을 새 발견으로 보고하지 않는다. 대안보다 남는 10pp 규모의 정확도 기회 또는 실측된 비용 부담이 있어야 최소 개입을 후속 후보로 제안하며, 신규성은 별도 검토한다.

## 음성

T가 D/C보다 의미 있는 표적 이득을 보이지 않거나 손상이 추가 영상·단순 확대·잘못된 localizer로 설명되면 현재 시각적 근거 제공 후보의 방법 투자를 보류한다. crop-only보다 원본 보존이 좋다는 결과만으로 새로운 결합 문제를 주장하지 않는다. 유효한 음성 관찰은 보존한다.

## 불확정

작은 차이·넓은 CI·형식 의존·기본 판단 부족은 각각 구분한다. 허용한 E600 이후 추가 생성·학습·crop 조정은 하지 않는다. 재개에는 동일 불확실성을 줄일 구체적인 자료·대조 또는 새로운 잔여 가치 근거가 필요하다. 단순히 CI가 넓다는 이유로 다음 실험을 예약하지 않는다.

실행 유효성, 성능 변화, 가설 지지, contribution을 별도로 보고한다. 입력·정답·provenance 결함으로 비교가 무효면 execution_failed이며 가설의 음성이 아니다.

# Risks / Checks

- 예측 box는 정답 근거가 아니다. nonempty 선택 자체의 편향과 localizer 오탐을 보존한다.
- 중앙 crop은 정상 대조가 아니며, GT를 보고 비표적 영역으로 이동시키지 않는다.
- enclosing crop은 여러 box 사이의 context를 포함한다. 완전한 병변 격리나 동일 정보량을 주장하지 않는다.
- 원본을 보존해도 모델 내부 표현 보존은 보장되지 않는다. tensor 확인과 인과 해석을 구분한다.
- 기존 Q_A의 기본 정확도가 낮다는 점을 유지한다. 새 손상만으로 충분한 인식 이후의 일반 결합 결함을 선언하지 않는다.
- R/R_L/R_B는 사전에 고정한 정책이다. 결과를 보고 환자별 최선 답을 고르는 oracle ensemble을 실용 비교군으로 사용하지 않는다.
- 데이터는 반복 개발 자료이며 base의 사전학습 노출도 완전히 배제되지 않는다. 독립 일반화·임상 성능 주장을 하지 않는다.
- 기본 환경과 hf_cache는 변경하지 않는다. 필요 패키지는 사전 알림 후 승인된 격리 환경에 설치하고 실제 입력으로 검증한다.
- full review와 --confirm-each-iter를 유지한다. 이번 계획의 조건부 확대만 승인 범위이며 다음 반복은 별도 사용자 승인이 필요하다.

## 대규모 GPU 필요 후보

동일 자료·노출량에서 위치 supervision, 답변 supervision, vision encoder 적응을 분리하는 다중 seed 공동 학습은 장기 후보로 남긴다. 현재 관찰이 그 투자를 요구한다는 근거는 없으며 이번에는 수행하지 않는다.

# 계획의 근거 (GPT 조사 노트)

## 이번 라운드의 결론

국소 영상 근거의 판단 가치를 선택한다. PadChest-GR에서 임의의 속성·음성 정답을 만드는 설계는 채택하지 않는다. 기존 RSNA의 두 질문을 함께 사용하면 같은 영상에서 표적 판단과 더 넓은 판단의 손익을 구분할 수 있다. 이는 iter_017의 텍스트 전달 실험과 다른 개입이며, 신규성이 확인된 방법은 아니다.

## 직전 질문에 대한 답

1. **PadChest-GR 정답 적합성:** 실제 JSON의 첫 항목에서 양성 문장·labels·locations·boxes/extra_boxes를 확인했다. 양성 문장인데 box가 없는 경우도 있다. 이 자료만으로 임의 속성 정답이나 미표기 소견의 음성을 만들 수 없다. 후보 1의 자료를 RSNA로 구체화한다. 질문은 영역 자체의 임상 진위가 아니라 공개된 원본 영상의 두 label 판단이다.
2. **가까운 선행의 범위:** [PadChest grounding 연구](https://proceedings.mlr.press/v315/aas-alas26a.html)는 전체 영상+grounding과 부분·노이즈 근거의 이득을 보고한다. PDF는 web 도구의 content-type 오류, 로컬 읽기 요청은 DNS 실패로 본문을 확보하지 못했다. 세부 대조 부재를 주장하지 않으며, 단순 전체+영역 효과는 이미 선행 범위라고 보수적으로 취급한다. [Grounding과 Medical VQA 연구](https://arxiv.org/html/2604.27720v2)의 crop 조건 및 학습 대조도 확인했다. 이번 원본 보존·질문 범위별 손익 진단의 신규성을 보장하지 않는다. [Visual Evidence Prompting](https://aclanthology.org/2025.acl-long.205/)도 전문 모델의 정보를 전달하는 가까운 대안이다.
3. **위치 학습 전이 후보:** 기존 출력으로 형식 차이는 분석할 수 있지만, 낮은 report-only baseline·선택 조건·판독 의미 평가의 경쟁 설명을 해소할 새 근거는 없다. 추가 학습 없이 후보 1보다 분명한 정보 이득을 제공하지 못하므로 이번에는 보류한다. 학습 recipe의 실패를 질문 전체의 기각으로 읽지 않는다.

## 원본과 로컬 확인

- round_01.json 원문, GOAL, iter_107 review를 읽었다. 10/10 두 영역 보존과 부분 누락 0을 유지한다.
- iter_016/017/037의 review.json, iter_017 plan, LIMITATIONS의 rsna-evidence-interface-sensitivity, 관련 CODE_ASSETS 항목을 확인했다. iter_017의 좌표 추가 효과 부재와 NoOpacity/NotNormal 손실은 현재 범위로 보존한다.
- `results/iter_016/manifests/sets.json`, `labels.json`, `infer_manifest.jsonl`과 `results/iter_015/reuse/bbox_B0_concise.jsonl`을 읽었다. P180의 비어 있지 않은 출력은 opacity 54, normal 1, not_normal_no_opacity 17명이다. E600은 각각 164, 5, 67명이다. 해당 목록에서 누락·간단 JSON 파싱 실패는 0이었다. 정식 source·좌표 검증을 대신하지 않는다.
- 기존 D12는 위 bbox 재사용 파일에 없었다. 따라서 새로운 D12 bbox 생성을 발주하지 않고 P180 안의 고정 6명으로 기술 검사를 구성한다.
- 현재 research HEAD는 e2a66795876215937e1eda5b2c6e70d30474298d이며 status/diff는 비어 있다. 필요한 qa_spec은 현재 브랜치에 없어 실제 이전 blob을 확인했다. 새 기반으로 사용할 iter_082의 reusable_code=true와 제한 승인 범위, tree를 확인했다.
- [MedGemma 1.5 공식 카드](https://huggingface.co/google/medgemma-1.5-4b-it)는 다중 patch·longitudinal 입력을 설명하지만 일반 다중 영상 평가에 관한 제한 문구도 남아 있다. 따라서 전체+crop은 지원 processor를 사용하는 확장 사용 진단이며 공식 검증 과제의 재현이라고 부르지 않는다.
- 파일 변경·환경 설치·모델 실행은 하지 않았다. 새로운 과학적 관찰은 없다.

## 대규모 GPU 필요 후보

위치·답변 supervision과 vision encoder 적응을 동일 노출량으로 분리하는 다중 seed 공동 학습은 장기 후보로 보존한다. 현재 실험은 그 필요성을 입증하지 않으며 이번에 발주하지 않는다.

이전 사고 라운드 노트: agent/runs/iter_108/think/
