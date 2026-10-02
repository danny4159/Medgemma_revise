# 요약

- **이번에 할 일:** 기존 CheXpert의 두 소견에 정확하거나 틀린 초안을 제공하고, 직접 교정과 초안 없는 판독의 수정·보존 성능을 비교한다.
- **필요한 이유:** 판독 오류와 초안의 영향을 분리해야 교정 특화 학습에 투자할지 결정할 수 있다. 새 자료 감사는 필요하지 않다.
- **확인할 기준:** 기존 oracle 오류의 새 회귀 검사, 동일 지시문에서의 영상 기여, 수정률 15 pp·보존 실패율 5 pp의 trade-off와 단순 대안의 충분성을 확인한다.
- **주의·다음:** D16 후 E48을 평가하고 사전 조건을 충족할 때만 F105를 사용한다. 신규 기여는 미확정이며, 허용 범위 이후 불확정이면 현재 교정 설계의 투자를 보류한다.

# Current Understanding

iter_052의 CT 본평가는 자료·기술 gate 실패로 미실행이다. E263으로 축소하거나 다른 modality 감사로 이어가지 않는다. iter_048의 공동 SFT 회복과 모듈형 비교 결과도 유지한다.

iter_047은 PadChest 혼합 상태 자료 부족과 oracle 29/32 때문에 실패했다. 이번 원문 확인에서 세 oracle 오류는 정상 JSON의 잘못된 cardiomegaly 상태였다. parser 수정으로 정정할 수 없다. image와 verified status가 함께 제공된 조건이므로 정보 출처 우선순위 혼동은 경쟁 설명이지만 원인으로 확정하지 않는다.

CheXpert 자산에는 169명의 단일 frontal 영상과 명시적 cardiomegaly/pleural_effusion reference가 있다. 원천 parquet·CSV digest를 이번 계획 단계에서 재확인했다. 기존 E48의 PE 직접 정확도 34/48은 판독이 완전하다고 가정하면 안 된다는 근거다.

이번은 자료·대조·확대 규칙이 달라지는 별도 진단이다. 과거 계획은 비교 기준으로 보존한다.

- iter_047 기준: `agent/runs/iter_047/plan.md`, SHA256 `e9263d4144dd4c6d929704fd3954d1a1859b1eb5dec77504c2934be19978b2f0`.
- 자료 출처: `agent/runs/iter_018/plan.md`, SHA256 `f9c33921cfeab3932404997388048c7380aa2350e7d1f4f3d03aa027d5ad7e8f`와 해당 review.json.
- 유지: 교정–보존 질문, 네 초안, 직접 판독 대조, 기존 실패 판정·원본.
- 변경: CheXpert 고정 두 finding, 동일 지시문 modality 대조, 출처 우선순위 oracle 검사, 조건부 F105 사용.
- 미완료: 새 oracle의 실제 통과, 새 교정 출력과 trade-off 검증.

iter_050의 담당 전환 인계는 완료된 일회성 작업이다. 이번에 반복하지 않으며 현재 구현 담당 Claude가 진행한다.

# Strategy Check / 연구 방향 판단

**중요한 능력:** 영상에 근거해 틀린 소견을 고치면서 맞는 내용을 유지하는 검토 능력이다. 완전한 보고서 생성이나 임상 reasoning 전체를 뜻하지 않는다.

**해결된 질문:** RSNA 직접 SFT는 실제 grounding을 개선했다. 현재 기하 가중의 추가 효과는 없었고, detector와의 차이는 위치 정밀도·threshold·FP 비용에 상당 부분 연결됐다. PadChest 공동 손실은 직접 형식 학습으로 상당 부분 회복됐다.

**남은 핵심 불확실성:** 교정 상황에서 발생하는 손실이 기본 판독 오류인지, 초안 의존인지, 단순 재판독으로 해결되는지다. 기존 D8은 이를 판단할 유효 본실험이 아니다.

**선택 비교:** grounding 학습 효율·일반화는 중요한 후보지만 anatomy pretraining이나 source warm-start를 지금 택할 개입 근거가 약하다. 교정은 기존 자료·평가기에서 동일 영상 대조를 구성할 수 있어 판단 비용이 작다. CT 후속은 정상 출력 보완만으로 자료 gate가 해결되지 않는다. 따라서 교정의 한정 진단을 우선한다.

**가까운 선행 이후의 가치:** CorBenchX와 phrase-grounded fact-checking/APO가 이미 교정·보존을 다룬다. 이번의 가치는 새 benchmark 이름이나 polarity 반전이 아니라 후속 학습의 필요성을 결정하는 데 있다. 단순 대안이 충분하거나 실제 판독부터 부족하면 교정 특화 방법 투자를 보류한다.

같은 `language-conditioned-grounding` track과 iter_047 접근법을 유지한다. 준비·실행 실패의 누적 비용과 유효 실험 수는 구분한다. 새 자료나 branch 이름으로 진단 이력을 초기화하지 않는다.

# Hypothesis

같은 영상·finding에서도 초안을 제공하면, 초안 없는 판독보다 잘못된 상태를 덜 수정하는 대신 원래 맞는 상태를 더 보존할 수 있다. 보존 지시 이후에도 중요한 trade-off가 남고 단순 대안이 목적을 충족하지 못할 때만 교정 특화 학습을 검토한다.

경쟁 설명은 기본 판독 오류, 언어 prior, 출력 형식, 출처 우선순위 혼동이다. 영상 없는 조건의 지시문을 바꾸어 이 설명들을 섞지 않는다.

# Limitation Evidence / Correct Usage Checks

연결 id `padchest-presence-grounding-interface`는 초안 없는 presence 판단을 강한 대안으로 넣는 배경이다. iter_042의 valid_experiment=true, blocking_issues=[] 및 evidence·usage_checks를 확인했다. 이 관찰은 CheXpert 교정 실패의 증거가 아니다. 따라서 `diagnostic`, `method_stage=none`이며 학습은 하지 않는다.

MedGemma 1.5 revision `91850547d9f0b2fdd21aa7c5f4f3d1a8a52c243b`, bf16, eval, greedy, adapter 없음으로 고정한다. 공식 chat template을 사용하고 실제 CheXpert 입력에서 token·pixel tensor를 공식 processor 경로와 직접 대조한다. 영상 없는 요청은 image token과 pixel tensor가 없어야 한다.

기존 값 보존 RGB·square padding 경로를 사용하되 원본 JPEG와 변환 hash를 연결한다. cap은 1000→2000→4000이며 비EOS만 재시도한다. 의미 오류를 이유로 재생성하지 않는다. 모든 attempt를 보존한다.

# Contribution Path / Baselines / Reuse

## 선행과 비교군

[CorBenchX](https://arxiv.org/html/2505.12057v1), [phrase-grounded fact-checking](https://arxiv.org/html/2509.21356v1), [APO](https://openaccess.thecvf.com/content/CVPR2026/papers/Mahmood_Phrase-grounded_APO_for_Improving_Chest_X-ray_Report_Generation_CVPR_2026_paper.pdf)의 교정·보존 범위를 앞선 조사에서 확인했다. 이들보다 우수하다는 실험은 아니다. checkpoint·전체 실행 경로를 확인하지 못한 방법을 재현된 비교군으로 표기하지 않는다.

환자마다 qA=cardiomegaly, qB=pleural effusion으로 고정한다. canonical 문장은 iter_047의 두 finding 문장을 사용한다. 초안 00/01/10/11을 모두 제공하므로 환자별 무오류 1개, 단일 오류 2개, 이중 오류 1개가 생긴다.

- K: 초안을 그대로 반환한다.
- R1: 기존 직접 교정 prompt.
- R2: 기존 보존 지시를 추가한 교정 prompt. 주 교정 조건이다.
- T: R2의 텍스트를 byte-identical하게 유지하고 영상만 제거한다. 영상 부재 안내나 uncertain 유도 문구를 추가하지 않는다.
- BJ: 초안 없이 두 finding을 공동 판독하고 결정론적으로 문장을 만든다.
- BI: 초안 없이 finding별 독립 판독 두 번 후 결정론적으로 문장을 만든다.
- BT: BJ 텍스트를 그대로 유지하고 영상만 제거한다. BJ−BT가 영상 기여 대조다.

R1/R2/T는 각 4요청, BJ/BT는 각 1요청, BI는 2요청으로 환자당 16요청이다. 출력 상태는 present/absent/uncertain이며 uncertain·invalid는 정답이 아니다. oracle은 추가 정답을 받는 기술 검사로 분리한다.

후속 방법은 직접 교정 SFT 및 BJ/BI와 공정하게 비교해야 한다. 같은 비용에서 수정률을 높이면서 보존 실패를 늘리지 않거나, 같은 정확도·보존 수준에서 비용을 줄이는 것이 필요한 기여다. 이번 진단만으로 방법이나 novelty를 승인하지 않는다.

## 코드 재사용

기존 `approach/controlled-report-revision`을 잇는다. 확인한 tip은 `5d34c5cd69de08603b7ad02fbb43a78691c6e7c7`이다. branch 전환과 commit은 orchestrator가 담당한다.

- `rr47_spec.py`, `rr47_eval.py`, `test_rr47.py`, `rsna_diag/parse.py`: 승인 범위는 상태 parser·환자별 점수 계산이다. 이를 확장하고 기존 D8 점수를 회귀 재현한다.
- `rr47_run.py`, `rr47_gate.py`, `rr47_verify.py`, `rr47_gen_test.py`, `pg43_run.py`: stage별 예상 요청 집합, 실제 gate 근거 digest, 공식 processor 검사, 최종 평가 봉인, 재개 비용 집계를 보완한다.
- runner 의존 파일은 해당 branch의 `pg39_data.py`, `pg39_spec.py`, `rsna_diag/{__init__,generate,geometry,metrics,parse,prompts,lora,queue_lock}.py`를 사용한다. 무관한 PadChest build·MG·RSNA 학습 경로는 수정하지 않는다.
- CheXpert 연결 함수 세 파일은 reuse_assets의 iter_018 SHA에서 반입한다. 원래 build를 실행하지 않고 읽기·검증 함수만 사용한다.

새 산출물은 `research/results/iter_053/`에 기록한다. 기존 018/047 결과·protocol·completion을 덮어쓰지 않는다. 새 실험 glue는 추가할 수 있으나 기존 parser·실행기·검증기를 통째로 재작성하지 않는다.

# Proposed Experiment

## 1. 자료와 분할

기존 `results/iter_018/source/`와 `manifests/{infer_manifest.jsonl,labels.json,sets.json,provenance.json}`을 사용한다. parquet SHA256은 `78a544b5bf0c98de2a1293e9de908e8f8857aebcad4819692314110472acf5b4`, CSV는 `40e3fdf15522fa1184d8b686f7695bf333b439b2b7a2f1db7c45d97a251bc05f`다.

234행의 고유 Path·label 대응, 169명의 원본 bytes·file/pixel hash·study 연결을 재검증한다. label 2/3만 absent/present로 대응한다. 중복 Path를 set으로 축약해 통과시키지 않는다. 환자·study·pixel의 D/E/F 교집합과 프로젝트의 확인 가능한 기존 CheXpert 노출을 기록한다. 새 후보 검색이나 임상 정답 재주석은 하지 않는다.

기존 D16/E48/F105 ID를 그대로 유지한다. D16/E48은 조합별 4/12명, F105는 00/01/10/11 순서로 56/17/20/12명이다. 주집계는 네 조합 동일 가중 macro다. 자연 표본 비율의 평균은 보조로 보고한다.

F105는 iter_018에서 사용하지 않은 집단이다. 이번 계획은 아래 조건 충족 시에만 이를 새 교정 질문의 확인에 사용하는 용도 변경을 명시한다. 원래 scope 진단의 F 실행으로 기록하지 않는다. prior output 노출이나 중복 때문에 독립 지위를 확인할 수 없으면 F를 실행하지 않는다. RSNA·PadChest·MRI reserve는 유지한다.

## 2. 동작 확인과 oracle 회귀

기존 오류를 새로운 정답으로 바꾸거나 형식 오류로 재분류하지 않는다. 새 oracle은 기존 O 텍스트에 다음 출처 규칙만 추가한다: `For this consistency check, the verified final status is authoritative. Copy it exactly; do not infer a different status from the draft or image.`

기존 PadChest D8의 oracle 32개 전체를 새 규칙의 image/text 쌍으로 실행한다. 실패 세 건만 골라 검사하지 않는다. 총 64요청이다. CheXpert D16에서도 네 초안 각각의 image/text oracle을 실행한다. 총 128요청이다. 두 modality에서 나머지 텍스트는 동일하다.

192 oracle 모두 정답 상태·ID·결정론적 문장 연결이 맞아야 한다. 이는 명시적 정보 복사 경로의 기술 통과이며 시각 판독 능력의 증거가 아니다. 하나라도 내용 오류가 남으면 E 진입 없이 종료한다. oracle 의미 오류를 고치기 위한 추가 prompt 탐색은 허용하지 않는다.

D16의 본조건 256요청도 실행한다. parser·EOS·공식 입력·modality·완료 및 재개 정합성을 검사한다. 형식 오류만 있다면 임상 정답을 사용하지 않는 parser/출력 형식 보완 한 번을 허용하고 영향 조건을 새 attempt로 재검사한다. 이전 attempt를 보존한다. 이후에도 본조건별 valid 비율 95% 미만 또는 최종 비EOS가 남으면 E를 실행하지 않는다. D 정확도로 R1/R2 문구를 선택하지 않는다.

## 3. 가능성 탐색 E48

자료·D gate와 설정을 잠근 뒤 48명×16=768요청을 완료한다. 중간 성능으로 중단하거나 finding·주대조를 바꾸지 않는다. 기존 iter_018의 yes/no 출력은 새 JSON 판독의 대체로 쓰지 않는다.

E48은 이미 개발 자료다. 여기서 나타난 차이를 독립 재현이라고 부르지 않는다. 수정–보존 trade-off가 작거나 기본 판독 오류가 지배하면 현재 교정 특화 투자를 보류한다.

## 4. 조건부 F105

다음 조건을 모두 충족할 때만 F105로 진행한다.

1. E의 입력·완료·독립 재계산이 유효하고 본조건별 valid≥95%, 최종 비EOS=0이다.
2. BJ−BT 상태 정확도 점추정≥0.10이고 95% CI 하한>0이다.
3. BJ−R2의 수정률 차이≥0.15, 보존 실패율 차이≥0.05다. 두 차이는 모두 valid인 상태만 살핀 보조 분석에서도 같은 방향이어야 한다.
4. R1/R2/BJ/BI 각각은 점추정상 수정률<0.80 또는 보존 실패율>0.05다. 단순 대안의 충분성을 확인하기 위해 F를 소비하지 않는다.
5. 환자별 차이의 E 층내 표본분산을 s²_h, F 층별 수를 n_h라 할 때 예상 97.5% CI 반폭 `2.242×sqrt(sum(s²_h/n_h)/16)`이 수정률 차이에서는 0.10 이하, 보존 실패율 차이에서는 0.05 이하다. 어느 차이든 층내 분산이 모두 0이면 이 근사를 정밀도 증거로 쓰지 않고 F 확대를 보류한다.

이는 F에서 유의할 것이라는 보장이 아니라, 확인 비용이 투자 결정을 바꿀 수 있는지 판단하는 규칙이다. F의 불균형 때문에 동일 분산 가정의 유효 표본 수는 약 76.19명임을 보고한다.

진입하면 105명×16=1,680요청을 같은 설정으로 한 번 평가한다. E/F를 합쳐 독립 확인 점수를 만들지 않는다. F 결과를 보고 prompt·parser·판정 기준을 변경하지 않는다. 이번 반복의 학습량은 0이며 method/full·추가 seed·외부 확인으로 자동 확대하지 않는다.

## 5. 자원·시간·재개

기본 요청은 D 및 과거 oracle 회귀 448건, E 768건으로 1,216건이다. F를 포함하면 2,896건이다. 처리량 비교·재개 검사·cap 재시도·허용된 형식 보완은 별도 장부에 실제 수를 남긴다.

iter_047의 152요청당 4-worker 256.2초, 2-worker 497.4초를 참고하면 기본 생성은 약 0.6–1.1시간, F 포함 약 1.4–2.7시간이다. 다른 자료·prompt이므로 추정이며 loading·검증·재시도는 별도다. D 실측 후 남은 요청량으로 ETA를 갱신한다.

실행 직전 nvidia-smi와 상속된 장치 범위를 확인한다. D의 oracle·영상·text-only가 포함된 동일 요청 묶음에서 총 2 worker와 총 4 worker를 비교한다. 이미 확보한 동등한 실측을 재사용할 때는 입력·설정 차이와 비교 비용을 설명한다. GPU당 동시 worker peak 합과 기존 점유에 worker당 최소 2GiB 여유를 더해 용량 안에 들어야 한다.

처리량·peak VRAM·긴 출력 지연·OOM·CPU/RAM/I/O 경합·greedy 출력 정합성으로 배치를 선택한다. 1 worker/GPU를 유지하면 실측 근거를 남긴다. 안전한 독립 요청을 두 GPU에 배정한다.

요청별 고유 ID와 claim, worker별 append 결과, 원본 partial 보존, config 일치 재개를 사용한다. 재개 비용은 모든 attempt/launch를 포함해 집계한다. 동시 worker의 요청 시간을 합한 값을 device 시간으로 표기하지 않는다.

# Implementation Tasks for Claude

1. 기존 branch·SHA와 반입 파일을 확인한다. iter_018·047 review.json의 재사용 문제를 읽고 이번 실행 경로에 필요한 수정만 한다.
2. 기존 CheXpert 자료를 검증하고 새 private GT·inference manifest·분할 용도 기록을 작성한다. 과거 builder로 데이터를 재생성하지 않는다.
3. rr47의 상태 parser·환자별 계산을 재사용하며 BT와 동일 지시문 T, 새 oracle, macro 집계, E→F 규칙을 추가한다. 과거 D8 점수 29/32와 보고된 상태 점수를 회귀 재현한다.
4. E/F의 예상 ID×조건×초안×modality 집합을 manifest에서 구성하고 정확히 한 번씩 완료됐는지 강제한다. 관측 출력 ID를 기대 집합으로 사용하지 않는다.
5. 자료·D·E decision의 실제 raw/report/verifier/protocol/source digest를 재검증한 뒤 후속 protocol을 만든다. run=true만 있는 JSON으로 gate를 통과시키지 않는다.
6. 공식 processor tensor, M0 revision·bf16·eval·adapter 없음, image/text 입력, parser 거부 사례를 검사한다. 새 GT 상태가 oracle 이외 prompt에 섞이지 않게 한다. 네 초안은 GT에 독립적으로 생성한다.
7. 변조·누락·중복·잘못된 stage·잘못된 split·stale decision·중단/재개와 원본 보존을 의미 있는 fixture 및 D 실제 실행으로 확인한다. 이전 결과를 삭제해 검사를 통과시키지 않는다.
8. production 계산과 별도 구현으로 수정·훼손·macro·CI·F gate를 재계산한다. 모든 worker 종료와 최종 평가 봉인 후 보고한다.

# Evaluation (성공/실패 기준 포함)

## 지표와 통계

환자별 두 finding×네 초안의 8개 상태를 평가한다. 원래 틀린 상태 4개 중 정답으로 바꾼 비율이 수정률 r, 원래 맞는 상태 4개를 반대로 바꾼 비율이 h, uncertain/invalid까지 포함한 보존 실패율이 h_fail이다. 상태 정확도, clean exact, robust exact, 초안 민감도도 보고한다. BJ/BI/BT는 같은 판독을 네 초안에 적용한다. 반복 초안을 독립 환자로 세지 않는다.

네 truth 조합의 환자 평균을 동일 가중한다. E/F 각각 층화 paired patient bootstrap 10,000회, seed5302를 사용하고 환자 내 모든 조건을 함께 재표집한다. 주대조 BJ−R2의 r와 h_fail은 각각 97.5% CI, 영상 기여 BJ−BT는 95% CI로 보고한다. 나머지는 보조 분석이다.

퇴화 bootstrap을 [0,0] 또는 [1,1] 확증으로 해석하지 않는다. 사건이 0인 경우 환자별 any-failure의 exact binomial 상한과 층별 Bonferroni 결합을 이용한 보수적 경계를 함께 제공한다. 충분성·부족함을 여러 baseline 중 선택해 선언할 때는 네 조건×두 endpoint의 동시 보정을 적용한다. 독립 verifier가 같은 보정 규칙을 검사해야 한다.

## 양성: 최소 방법 시험 검토 근거

F105에서 다음을 모두 충족해야 한다.

- 자료·정상 사용·실제 출력·독립 계산이 유효하다.
- BJ−BT 정확도≥0.10, 95% CI 하한>0이다.
- BJ−R2 수정률 차이≥0.15 및 97.5% CI 하한>0이다.
- BJ−R2 보존 실패율 차이≥0.05 및 97.5% CI 하한>0이다.
- 주차이가 invalid 유입만으로 설명되지 않고 공통 valid 분석의 방향이 유지된다.
- R1/R2/BJ/BI 각각에서 동시 보정한 r 상한<0.80 또는 h_fail 하한>0.05가 성립한다.

이는 초안 없는 판독이 더 고치지만 더 훼손하는 중요한 trade-off와 단순 대안의 부족함에 관한 제한적 근거다. 후속은 직접 교정 SFT를 포함하는 최소 method pilot의 가치 판단이다. 선행 대비 신규성·다기관 일반화·자유형 보고서 효과는 미확인이다.

## 단순 대안 충분 또는 음성

R1/R2/BJ/BI 중 하나가 동시 보정한 r 하한≥0.80과 h_fail 상한≤0.05를 충족하면 이 제한 과제의 새 방법 투자를 보류한다. 이 수치는 임상 배포 안전 기준이 아니다.

주효과 CI 상한이 사전 중요 효과보다 작으면 해당 크기의 trade-off 가설을 약화한다. 영상 기여가 부족하거나 BJ/BI 판독 자체가 낮으면 교정 특화 원인을 확정하지 않는다. 이 경우도 이번 편집 방법 투자 보류의 근거이며 기본 시각 능력 전체의 기각은 아니다.

## 불확정과 종료

E 확대 조건 미충족은 효과 부재와 구분한다. F를 보존하고 현재 설계의 투자를 보류한다. F 이후에도 CI가 판단 경계를 가로지르면 정밀도 부족으로 기록하고 추가 표본·prompt·질환을 자동 실행하지 않는다.

oracle·자료·입력 gate 실패는 execution_failed이며 본가설의 음성 결과가 아니다. 통과한 실제 E 비교는 결과가 불확정이어도 유효한 진단일 수 있다. 과거 blocking_issues를 지우거나 소급 승격하지 않는다.

## 비용

실험 총비용과 한 검토당 배포 비용을 나눠 보고한다. BJ는 영상 판독 1회, BI는 2회이고 결정론적 편집 비용도 포함한다. loading 포함 wall, GPU별 점유 구간, 요청 latency, tokens, 재시도·실패 비용을 구분한다. 단회 실행 비용으로 비용 비열등성 CI를 만들지 않는다.

# Risks / Checks

- CheXpert reference는 제공 annotation에 대한 정답이다. 이번에 전문가 영상 재판독을 했다고 주장하지 않는다.
- 대부분 AP인 단일 frontal 집단이며 MedGemma 사전학습 노출은 미확인이다.
- 네 초안의 균등 구성은 자연 오류 prevalence가 아니다. 임상 보고서의 실제 오류율을 추정하지 않는다.
- 새 oracle은 정보 복사 검사다. 통과하더라도 실제 판독·교정의 인과 원인을 증명하지 않는다. 실패하면 내용을 무시하거나 parser를 느슨하게 만들어 통과시키지 않는다.
- F105의 용도 변경은 명시적으로 기록하고, 기존 과제의 확인 완료로 표기하지 않는다. 중복·선행 출력 노출이 확인되면 독립 확인 경로를 중단한다.
- 자료 gate 실패 시 새 데이터 다운로드·다른 finding 선택·표본 문턱 완화로 전환하지 않는다.
- 기존 hf_cache, 원본 결과, RETRACTION과 과거 실패 기록을 수정·삭제하지 않는다.

## 대규모 GPU 필요 후보

다기관 전문가 수정 이력으로 verifier와 editor를 공동 학습하거나 vision encoder까지 포함해 근거–편집 연결을 적응시키는 방향을 장기 후보로 보존한다. 현재 두 GPU의 한정 진단이 그 필요성·효과·신규성을 입증한 것은 아니다.

# 계획의 근거 (GPT 조사 노트)

## 이번 선택

기존 CheXpert 자산을 이용한 한정 교정 진단을 선택한다. 외부 교정 benchmark 확보, CT E280, 공동 grounding 추가 loss의 보류는 유지한다. 이는 iter_047의 성공 판정 변경이나 같은 PadChest E96의 축소 실행이 아니다.

## 직전 질문에 대한 답

1. **판독 오류와 초안의 영향을 구분할 수 있는가?** 같은 환자의 두 소견에 네 초안을 모두 제공하고 BJ/BI의 초안 없는 판독을 공유하면 구분할 수 있다. 다만 기존 E48의 직접 PE 정확도 34/48은 새 과제의 결과가 아니며 시각 판독이 충분하다는 가정도 허용하지 않는다. BJ와 동일 지시문인 BT를 추가하여 영상 기여를 따로 검사한다. BJ−T를 영상 효과로 해석했던 iter_047의 confound를 수정한다.
2. **grounding 학습·일반화에서 무엇이 남는가?** iter_008은 실제 생성이 아닌 frozen head anatomy 전이 계획이었고 사용자 전환으로 미실행됐다. iter_012는 직접 SFT의 실제 개선을 확인했지만 iter_014의 기하 가중은 추가 효과를 보이지 않았다. iter_035~037에서는 detector의 위치 정밀도·속도와 SFT의 IoU0.3 trade-off가 남았으나 SFT-only의 상당 부분은 detector threshold 아래 후보로 설명됐다. 저표본 전이·외부 일반화는 미검증이지만, 어떤 새 개입을 택할지 결정할 증거는 아직 없다. 이 사실을 모든 학습의 실패로 확대하지 않는다.
3. **어느 쪽에 투자하는가?** 교정 경로는 확보된 영상·명시적 정답과 재사용 가능한 상태 평가기로 한 번의 유한 비교가 가능하다. 현재 grounding warm-start나 anatomy 전이를 고르는 것은 추가 학습량·과제 적응과 구별할 개입 근거가 더 약하다. 따라서 교정의 제한된 의사결정 가치를 우선한다. 학습을 피하기 위한 선택은 아니며, 진단이 양성이면 직접 SFT를 포함하는 최소 방법 시험을 별도로 판단한다.

## 새로 확인한 원본 근거

- round_01/02 원문, iter_008 계획, iter_012·014·018·035~037·047·052 리뷰와 관련 code_assets를 확인했다.
- `research/results/iter_018/source/chexpert_validation.parquet`는 12,045,148 bytes이며 이번 읽기 전용 SHA256 계산값은 `78a544b5bf0c98de2a1293e9de908e8f8857aebcad4819692314110472acf5b4`다. MedAug CSV는 38,637 bytes, SHA256 `40e3fdf15522fa1184d8b686f7695bf333b439b2b7a2f1db7c45d97a251bc05f`로 기존 provenance와 일치한다. 169개 영상의 전체 hash 재검증은 구현 단계에 남긴다.
- 기존 D16/E48은 조합별 4/12명이다. F105는 56/17/20/12명으로 불균형하다. 네 조합을 동일 가중할 때 동일 분산 가정의 유효 표본 수는 약 76.19명이므로 F105를 균형 105명처럼 취급하지 않는다.
- `results/iter_047/gen/D8_v2_resume/gen_worker*.jsonl`에서 oracle 실패 세 건의 요청과 원문을 직접 확인했다. 정답 qA=present에 qA=absent를 반환한 실제 내용 오류다. image가 제공됐고 JSON은 정상이다. 출처 간 경쟁은 가능한 설명이지만 확인된 원인은 아니다. 새 oracle 검사의 통과를 미리 가정하지 않는다.
- 현재 HEAD는 `3f9bff15a0cd2d198171580f783919eb9d84c9d9`, 작업 트리는 깨끗하다. 기존 `approach/controlled-report-revision` tip은 `5d34c5cd69de08603b7ad02fbb43a78691c6e7c7`다. 그 branch의 rr47_spec/eval/run/verify와 pg43_run 의존성을 확인했다. 현재 작업 폴더에 없다는 이유로 이 자산을 재구현하지 않는다.

## 선행과 주장 범위

앞선 라운드에서 확인한 [CorBenchX](https://arxiv.org/html/2505.12057v1), [phrase-grounded fact-checking](https://arxiv.org/html/2509.21356v1), APO의 교정·보존 중복 판단을 유지한다. 공개 checkpoint 미확인을 논문의 무효나 설치 불가능으로 해석하지 않는다.

이번에는 학습 경로 비교를 위해 [PFMVG 초록](https://arxiv.org/abs/2410.23822)과 [Generate to Ground 공식 페이지](https://proceedings.mlr.press/v301/nutzel26a.html)를 추가 확인했다. 의료 grounding의 경량 적응과 생성모델 기반 grounding도 이미 연구되고 있으므로 일반적인 전이 학습·LoRA 사용 자체는 차별점이 아니다. 두 방법을 로컬에서 재현하거나 상세 비교한 것은 아니다.

## 보존과 비용

iter_050→051 인계 완료 판단과 RETRACTION의 무효 감사 제외를 유지한다. 현재 담당은 Claude이며 담당 전환을 반복하지 않는다. CT 완료 생성 466건과 iter_049~052 준비 비용은 보존하되 유효 가설 실험 횟수로 세지 않는다. 이번 라운드의 파일 변경·모델 생성·학습은 0이다.

## 대규모 GPU 필요 후보

다기관 전문가 수정 이력을 이용한 verifier/editor 공동 post-training, 영상 encoder까지 포함하는 교정–보존 학습은 장기 후보로 남긴다. 현재 진단으로 필요성이나 신규성이 입증된 것은 아니다.

이전 사고 라운드 노트: agent/runs/iter_053/think/
