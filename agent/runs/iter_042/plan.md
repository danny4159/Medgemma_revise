# 요약

- **이번에 할 일:** 기존 M0와 직접 SFT C가 흉수 양성 영상에서는 위치를 찾고, 명시적 음성 영상에서는 빈 결과를 반환하는지 비교한다.
- **필요한 이유:** 지금까지의 PadChest grounding 평가는 양성 소견 중심이었다. 위치 출력의 개선이 부재 거부까지 보존한다는 근거는 없다.
- **확인할 기준:** 중립 질의와 두 presence gate 이후에도 큰 음성 오출력 또는 양성 손실이 남는지 판단한다.
- **주의·다음:** 최종 후보 전수 비교 한 번으로 종료한다. 양성이면 최소 방법 시험의 후보이며, 불확정이면 추가 진단을 자동 확대하지 않는다.

# Current Understanding

iter_040에서 직접 SFT C의 V96 F1@0.3은 0.57795였지만 문장 대조의 추가 효과는 불확정이었다. iter_041에서는 공동 요청의 정확도 손실을 확인했으나 비용 불확실성 검사가 완결되지 않았다. 공동 방법 투자는 보류한다.

이번은 공동 요청 계획의 복구나 비용 CI 재실험이 아니다. 양성 문장만 사용한 적응 이후 실제 부재 소견에 대한 출력 행동을 묻는 별도 diagnostic이다. 기존 observed 한계는 자산과 이력을 연결하는 근거이며, 새 specificity 결함의 증거로 대신 쓰지 않는다.

유지할 것은 GOAL, MedGemma 1.5, RSNA SFT·detector 결과, continuation 투자 종료, VinDr 승인 대기와 기존 reserve다. 바꿀 것은 평가할 사용 조건뿐이다. 학습·checkpoint 선택·과거 판정은 바꾸지 않는다.

# Strategy Check / 연구 방향 판단

중요한 사용 과제는 요청한 finding이 실제 영상에 있을 때만 근거 영역을 제공하는 것이다. 존재하지 않는 소견에도 box를 반환하면 grounding을 검증 가능한 근거로 활용하기 어렵다. 다만 일반적인 hallucination이나 zero-box 처리는 이미 연구된 문제다.

강한 직접 SFT 확보와 공동 방법 보류 이후이므로 전략을 재검토한다.

1. 현재 방법 개선은 공동 직접 CE 및 비용 근거가 부족해 우선하지 않는다.
2. 전문 모듈형 비교는 가치가 있지만 MedGrounder의 공식 실행 의존성이 해결되지 않았다. 미실행을 성능 열세로 해석하거나 RSNA opacity detector로 대체하지 않는다.
3. 이번 specificity 진단은 승인된 원본과 기존 checkpoint로 실행 가능하다. 동일 질의·실제 양성/음성 영상과 간단한 presence gate로 다음 방법 시험의 필요성을 한 번 판단한다.
4. 새 보고서·다른 데이터 과제는 정답과 baseline 확보 비용이 더 크다. 이번 판단 이후에도 근거가 없으면 방향 전환 후보로 검토한다.

`language-conditioned-grounding` track을 유지한다. iter_038 setup, iter_039 diagnostic, iter_040 method pilot, iter_041 diagnostic과 과거 RSNA 전이·모듈형 비교를 연결한다. 해결된 질문은 양성 grounding의 적응 가능성과 현재 공동 요청 손실이다. 남은 질문은 실제 부재 거부와 단순 대안의 충분성이다.

iter_039 주요 생성 wall 약4.21시간, iter_040 네 학습 trajectory 약2.54 GPU-hours, iter_041 일부 큐 loading 포함 약1.123 GPU-hours는 서로 포함 범위·단위가 달라 합산하지 않는다. 이미 여러 준비·진단을 수행했으므로 이번은 유한한 후보 전수 비교로 종료한다.

# Hypothesis

- **H_specificity:** C는 양성 위치 출력의 이득을 얻었지만 부재 영상에서도 box를 반환한다.
- **H_adaptation:** C의 음성 오출력은 M0보다 커졌다. 이 차이는 측정 대상이며 사전 사실이 아니다.
- **H_prompt:** 존재를 전제하는 요청 문구가 차이를 설명하며 중립 질의로 해소된다.
- **H_modular:** 단순 presence 확인 후 C의 box를 반환하면 충분하다.
- **H_competence:** canonical 질의에서 양성 grounding 자체가 낮다면 specificity 보존 문제를 분리해 해석하기 어렵다.

학습하지 않은 문구와 양성-only 학습 분포는 경쟁 설명으로 남긴다. 내부 시각 표현의 손상이나 임상적 환각 원인을 단정하지 않는다.

# Limitation Evidence / Correct Usage Checks

연결할 기존 id는 `padchest-sentence-grounding-and-joint-retention`이다. iter_039–041 원본 리뷰의 정상 입력·좌표·실제 출력 검증을 재사용한다. iter_041 비용 판정의 blocking issue는 유지하며 이번 gate에 사용하지 않는다. 새 specificity 주장은 아직 candidate 수준이다.

모델 revision `91850547d9f0b2fdd21aa7c5f4f3d1a8a52c243b`, bf16, 공식 chat template, uint16 값 보존 변환, RGB 복제, 중앙 square padding과 yxyx/0–1000 좌표를 유지한다. 과거 변환 논쟁을 다시 실험하지 않고 새 영상의 연결·hash·좌표를 검사한다.

음성은 label 부재, 빈 bbox, 정상으로 보이는 crop으로 만들지 않는다. 원본 abnormal=false 문장에서 현재 영상의 pleural effusion 부재가 명시된 경우만 허용한다. 한쪽 흉수만 부정한 경우, 불확실성, 과거/변화 비교, 번역 불일치와 대상 범위가 모호한 경우는 제외한다. 영문·스페인어 원문과 주변 findings를 출력 눈가림 상태에서 검토하고 이유를 비공개 기록에 남긴다. 이는 새 임상 재판독이 아니며 제공된 report reference에 대한 평가다.

# Contribution Path / Baselines / Reuse

[MedGrounder/GMPG](https://arxiv.org/html/2512.01085v1)는 non-groundable 문장과 zero/multiple boxes를 이미 다룬다. 이번에는 음성 문구가 답을 알려주는 평가를 피하고, 같은 target 질의에 영상이 달라질 때의 반응을 측정한다. [Counterfactual grounding verifier](https://arxiv.org/html/2606.28520v1)와 [CORAL](https://arxiv.org/abs/2607.03647) 때문에 grounding 기반 사실 검증·영상 대조 자체도 신규성으로 주장하지 않는다.

비교 모델은 미적응 M0와 `results/iter_040/train2/C_s17/epoch_03`이다. C adapter tensor digest는 `419ae81f5ef455d39742b158537373da6e26061b362d13205ab28b4a50905ba8`이다. 새 seed·B/M checkpoint 선택을 추가하지 않는다.

실용 대안은 M0-presence→C-grounding과 C-presence→C-grounding이다. 동일 원본 영상과 target을 허용한다. positive-only annotation으로 학습된 C와 추가 학습 없는 M0의 차이를 명시한다. 향후 method pilot에는 같은 positive annotation budget의 positive+negative 직접 CE와 이 두 단계 대안을 필수로 포함해야 한다.

새 approach branch는 orchestrator가 관리한다. 자동 기반과 JSON reuse_assets의 12개 파일을 사용한다. 소스 SHA와 실제 blob은 확인했다. 입력·순수 metric 승인 범위는 iter_039 review.json, runner 결함과 보조 검증 범위는 iter_041 review.json을 따른다. 전체 snapshot 승인이 아니다.

# Proposed Experiment

## 1. 출력 보기 전 자료 확정

원본은 `results/datasets/padchest_gr/raw/grounded_reports_20240819.json`과 `master_table.csv.zip`이다. 기존 pinned SHA를 검증하고 official train만 사용한다.

E 후보에서 iter_039 전체 manifest의 D24/E288/F120 및 iter_040 train/eval manifest의 환자를 모두 제외한다. 환자·study·영상 ID와 decoded pixel 중복도 확인한다. 기존 H192·F120·test의 findings나 출력을 새로 열지 않는다.

- 음성 후보: abnormal=false이고 effusion을 명시한 현재 부재 문장. metadata상 41영상이며 위 의미 검토를 통과해야 한다.
- 양성 후보: 모든 pleural-effusion target 문장이 해당 label 하나만 포함하고 유효한 공식 boxes를 가지며 progression=None이고 기존 temporal regex에 걸리지 않는 영상. metadata상 30영상이다. 추가 혼합 target 문장이 있으면 영상 전체를 제외한다. target의 모든 공식 box를 모으고 동일 좌표 중복만 제거한다.
- 환자당 한 영상은 `sha256('iter042-v1|' + PatientID + '|' + ImageID)` 순서로 고른다. 결과에 따른 교체는 금지한다.

최종 적격 후보 전원을 E로 사용한다. 이 집단은 프로젝트 학습·기존 평가 환자와 분리한 새 개발 진단이며 독립 confirmatory test로 부르지 않는다. 사전학습 노출은 미확인이다.

양성 24명·음성 32명 이상일 때 실행한다. 이는 bounded 지표의 최악 95% 반폭이 각각 약0.20·0.17인 큰 효과 진단의 최소 정밀도다. 기대 후보 30/41명도 작은 차이를 판별하기에는 부족하다. 미달이면 사례를 추가 정의하거나 reserve를 열지 않고 자료 제약으로 종료한다.

## 2. 요청 조건

모든 E 영상에 같은 target `pleural effusion`을 사용한다. 원본 보고서·부재 표현·GT·집단명은 추론 입력에 넣지 않는다. 각 모델에서 다음 세 조건을 독립 대화로 생성한다.

- **G_short:** 기존 `prompt_I_short('Pleural effusion.', 'qA')`를 그대로 사용한다.
- **G_neutral:** `Identify all visible regions of pleural effusion in this chest radiograph. Pleural effusion may be present or absent. If it is absent, return []. Otherwise, return one entry per separate visible region.` 뒤에 기존 `_SHORT_TAIL`과 `Use qA as the label of every entry.`를 붙인다.
- **P:** `Is pleural effusion present in this chest radiograph? Answer only yes or no.`

M0/C×세 조건으로 환자당 6요청이다. greedy와 기존 EOS 재시도 caps 1000/2000/4000을 유지한다. P도 길이를 임의 축소해 invalid를 만들지 않는다. JSON 및 yes/no parser는 E 출력 전에 고정한다. P는 공백·대소문자·종결부호만 정규화하고 설명문·상충 답변을 임의 추론하지 않는다.

두 단계 출력은 P가 yes이면 해당 영상의 C G_neutral, no이면 []로 정의한다. P가 invalid이면 최종 결과도 invalid다. P0-gate와 PC-gate를 모두 보고하며 E에서 유리한 쪽만 선택하지 않는다. 이는 baseline 출력의 결정적 조합 평가다. 실제 조건부 pipeline latency를 측정한 것으로 표현하지 않는다.

## 3. 동작 확인

기존 T305/D24 중 출력 눈가림 적격성 검토를 통과한 양성 3명·음성 최대3명을 D로 고른다. 현재 후보는 양성20·음성3영상이다. D는 train 노출 가능성이 있는 구현 검사이며 효과 추정에 합치지 않는다. 적격 음성이 줄면 모두 사용하고 최소1명이 없으면 자료 경로를 보류한다.

template·adapter·영상 tensor 연결, empty/nonempty/invalid 분류, 좌표 왕복, target ID와 원본 GT 연결을 검사한다. 명백한 구현 오류만 수정한다. D 성능을 보고 prompt 후보를 탐색하지 않는다.

## 4. 가능성 탐색과 규모 확대

동작·자료 gate 통과 후 고정 E 전수를 한 번 실행한다. 작은 E를 먼저 보고 유리한 경우 나머지를 여는 절차는 쓰지 않는다. 전체 후보가 최대71명이고 큰 효과만 판별할 수 있어 추가 중간 평가의 선택 편향보다 전수 비교의 가치가 높다.

이번 diagnostic의 본실험은 이 E 비교다. 학습·epoch·validation milestone은 해당하지 않는다. 다른 질환·추가 환자·H192·F120·추가 seed로 확대하지 않는다.

## 5. GPU 배치·비용·재개

실행 직전 nvidia-smi로 상속된 허용 장치와 실제 여유를 확인한다. 논리/물리 대응을 기록하고 여유가 큰 장치부터 배정한다.

D에서 총2 worker와 총4 worker를 같은 요청으로 비교한다. 각 모델 큐를 두 GPU에 나누며 4 worker이면 GPU당2개다. 과거 약17.8GB 점유는 참고값이며 새 M0 출력의 KV cache·긴 출력 peak와 다른 점유까지 확인한다. 예상 동시 peak와 worker당2GiB 여유가 용량을 넘으면 4 worker를 시작하지 않는다.

D의 처리량·긴 출력 지연·전체 GPU peak·OOM·CPU/RAM/I/O·token 정합성으로만 구성을 선택한다. E 정확도는 구성 선택에 사용하지 않는다. 4 worker가 안전하거나 빠르지 않으면 2 worker를 쓰고 이유를 기록한다. worker 수와 GPU 수를 분리하고 배정 변경으로 prompt·caps·metric을 바꾸지 않는다.

기본 신규 생성은 `6×N_E + 12×N_D`, 현재 후보 기준 최대498건이다. 과거 iter_039의 864요청/9,628초와 iter_041의 더 빠른 짧은 출력 처리량을 고려한 GPU 실행 예상은 약0.5–2시간이다. 입력 준비·재시도·회귀검사를 분리 집계하고 D 실측으로 ETA를 갱신한다. 시간 상한은 두지 않는다.

새 결과는 `research/results/iter_042/` 아래에 저장한다. request ID·worker별 JSONL·원자적 claim·부분 행 원본·protocol·완료 digest를 보존한다. 중단 뒤 완료 요청도 현재 모델·입력·설정과 대조하며 살아 있는 작업을 중복 실행하지 않는다.

## 6. 독립 확인

이번에는 수행하지 않는다. 진단 양성도 method pilot 후보일 뿐이다. 방법과 강한 mixed-CE baseline을 정한 별도 계획에서 annotation budget·수렴·독립 집단을 결정한다.

# Implementation Tasks for Claude

1. 관련 원문과 reuse_manifest를 읽고 선택한 모듈만 반입·검증한다. 과거 trainer·downloader·비용 판정기를 정비하지 않는다.
2. 별도 iter042 builder에서 제외 목록, 의미 적격성, 환자 선택과 실제 영상 hash를 잠근다. 원문·식별자·공유 링크는 Git/공개 로그에 넣지 않는다.
3. 기존 pg41 runner helper를 사용하되 새 driver는 completion 존재만으로 skip하지 않는다. 호출자가 요구한 모델·adapter·요청과 protocol을 먼저 대조한다. 사용하지 않는 과거 generate CLI는 호출하지 않는다.
4. 평가 GT·source·metric·selection lock·output digest를 연결하고 결과를 원자적으로 기록한다. []와 invalid를 분리한다. unknown ID·잘못된 좌표를 정상 empty로 바꾸지 않는다.
5. empty GT, nonempty GT, invalid, gate invalid, 복수 box matching과 bootstrap의 fixture를 만든다. pg41_verify의 empty-GT F1 관례를 음성 정확도에 그대로 쓰지 않는다. 양성 matching만 제한 재사용한다.
6. D에서 실제 중단·재개와 변조 거부, 2/4 worker 정합성을 검사한 뒤 E를 실행한다. 검사 요청과 폐기 attempt 비용도 기록한다.
7. 보고서에 실행 유효성, 성능 비교, 가설 지지, 신규성 미확인을 구분한다. iter_041의 비용 pilot 판정은 원 리뷰대로 보류임을 출처와 함께 명시하고 과거 파일을 수정하지 않는다.

# Evaluation (성공/실패 기준 포함)

## 지표와 불확실성

- 양성: 환자 평균 F1@0.3, 보조 F1@0.5·recall·FP/환자·valid/EOS.
- 음성: false-box rate=valid nonempty/전체 음성, valid-empty rate, invalid rate를 별도로 보고한다. invalid는 성공적 거부가 아니다. 보수적 실패율 `(nonempty+invalid)/N`도 병기한다.
- presence: sensitivity·specificity·invalid와 두 단계 결과.
- C−M0: 같은 환자의 양성 F1 차이와 음성 false-box rate 차이를 주비교로 보고한다. 각각 환자 paired bootstrap 10,000회, seed20261001, 97.5% CI를 사용한다. 단일 비율은 Wilson 95% CI를 함께 보고해 0/1 경계의 퇴화 bootstrap을 피한다.
- prompt 및 gate 비교는 95% paired CI와 원시 성공/실패 수를 보고한다. 결과 기반 threshold 선택은 없다.

최소 가치 있는 단순 개선은 음성 false-box rate 15 pp 감소와 양성 F1 손실 5 pp 이내다. 이는 탐색 투자 기준이며 임상 허용 기준이 아니다. 성능을 합친 하나의 점수로 양성·음성 trade-off를 숨기지 않는다.

## 다음 행동

**단순 해결책 지지:** G_neutral 또는 사전 고정 gate에서 C G_short 대비 false-box rate가 15 pp 이상 감소하고 감소 CI 하한이 0보다 크며, 양성 F1 차이의 CI 하한이 −0.05 이상이면 유효한 단순 개선으로 기록한다. 음성 오류율 Wilson 상한까지 0.20 이하이면 현재 큰 specificity 문제의 방법 투자를 보류하고 baseline을 보존한다. 실제 latency 이득은 주장하지 않는다.

**최소 방법 pilot 후보:** C G_neutral의 양성 F1@0.3≥0.40, grounding invalid≤5%, 음성 false-box rate≥0.25 및 Wilson 하한>0.10이 모두 필요하다. 두 gate 각각에서도 (a) false-box rate≥0.25 및 Wilson 하한>0.10, 또는 (b) C G_neutral 대비 양성 F1 손실≥0.10이고 손실 CI 하한>0 중 하나가 확인돼야 한다. 그러면 단순 대안의 구체적 부족함을 기록하고 positive+negative 직접 CE를 강한 대조군으로 하는 작은 method pilot을 다음 계획에서 검토한다. 방법 신규성이나 full 확대를 확정하지 않는다.

**적응 악화 해석:** C−M0 음성 false-box 차이가 15 pp 이상이고 97.5% CI 하한>0이면 현재 적응 조건의 악화 관찰을 지지한다. 이 조건이 없으면 문제를 SFT가 만든 것으로 부르지 않는다. 잔여 specificity 문제와 적응 악화는 별도 결론이다.

**음성·불확정:** 중립 질의에서 중요한 오출력이 남지 않거나, 양성 competence가 낮거나, gate 효과·손실의 CI가 경계를 가로지르면 현재 설계 투자를 보류한다. 기존 후보 전수를 이미 사용했으므로 같은 진단에 환자·prompt를 추가하지 않는다. 정확도 비교가 유효한 불확정과 입력/실행 실패를 구분한다.

# Risks / Checks

- `abnormal=false`는 모든 질환의 부재를 뜻하지 않는다. target-specific 현재 부재만 인정한다. 영어 keyword 집계는 적격성 검토의 대체물이 아니다.
- compound positive 문장의 box를 흉수만의 정답으로 쓰지 않는다. 모든 target 문장의 범위·box 완결성을 출력 전에 확인한다.
- canonical 질의는 C의 학습 문장과 분포가 다를 수 있다. 양성 competence와 두 문구의 결과를 함께 보고하며 낮은 성능을 specificity 손상으로 오해하지 않는다.
- C는 positive-only T305에서 학습됐다. 실패가 확인돼도 간단한 negative 포함 CE로 해결될 가능성이 높고, 그 baseline 없는 새 loss 주장은 허용하지 않는다.
- 단일 target·작은 개발 집단·단일 SFT seed다. 모델 내부 원인, 다른 질환·기관·모델 일반화와 임상 안전성은 판단하지 않는다.
- MedGrounder 미실행과 두 단계 pipeline의 실제 latency 미측정 범위를 유지한다. 요청 시간 합으로 device-seconds CI나 사용자 완료 지연을 대체하지 않는다.
- 환경 설치·hf_cache 변경·VinDr 다운로드·기존 결과 덮어쓰기와 reserve 개방은 하지 않는다.

## 대규모 GPU 필요 후보

다기관의 실제 positive/explicit-negative 영상–질의–영역 자료로 모델 전체를 적응하고, 여러 모델·seed에서 localization과 부재 거부의 공동 보존을 검증하는 연구는 후보로 보존한다. 폭넓은 학습·주석 비용이 필요하며 이번 진단이나 두 3090의 LoRA 가능성 전체를 대신 기각하는 근거로 쓰지 않는다.

# 계획의 근거 (GPT 조사 노트)

## 새로 확인한 것

- GOAL, GPT_USAGE_POLICY, REPORTING_STYLE, INDEX, LIMITATIONS의 관련 항목, CODE_ASSETS와 iter_039–041 원본 리뷰·관련 계획을 확인했다. iter_041의 정확도 관찰은 유효하지만 비용 CI 오류로 방법 pilot 진입은 보류다. 이 판정을 유지한다.
- iter_041 plan SHA256: `e9786ff168532ae432a03be8aa9d64e84308bc69ff08d8cd03e3002fd28eb87f`. iter_040 plan SHA256: `1e37d04e0c26b5fabcc6803bdfd41fd7c71cc2829a75a81e0c756ba3592bfc21`. 이번은 두 계획의 실행 복구가 아니라 별도 질문이다.
- 원본 PadChest-GR metadata를 읽기 전용으로 집계했다. train의 abnormal=false 문장은 2,401개다. effusion을 명시한 음성 후보는 50영상이고, 기존 iter_039 전체 432명과 iter_040 T305·평가 manifest 환자를 제외하면 41영상이다. 이 50영상에 양성 pleural-effusion label이 함께 있는 사례는 0이었다. abnormal=false 항목에는 문장과 abnormal 필드만 있으므로 부재 범위의 별도 검토가 필요하다.
- 같은 제외 후 양성 pleural-effusion 영상은 71개다. 해당 target 문장의 labels가 pleural effusion 하나이고 boxes가 있으며 progression=None인 후보는 31개였다. 모든 target 문장에 기존 temporal regex까지 적용한 보수적 후보는 30개다. 이는 자료 가능성 집계이며 최종 적격성·환자/영상 중복·임상 reference 검증은 아니다.
- 기존 T305/D24 안에는 동작 확인용 양성 후보 20영상·음성 후보 3영상이 있다. H192·F120을 동작 확인에 사용하지 않는다.
- research HEAD는 `85320c89689b70f05b6e8c06c01ec8c4c7af2710`이며 작업 트리는 깨끗하다. 선별 반입할 12개 파일의 실제 blob 일치를 확인했다. 자동 기반 후보 iter_006에는 해당 파일들이 없다. 모듈 승인 범위와 needs_fix는 iter_039/040/041 review.json의 code_assets를 확인했다.

## 선행연구와 대안의 의미

- [MedGrounder 공식 코드](https://github.com/aehrc/MedGrounder)와 [GMPG 논문](https://arxiv.org/html/2512.01085v1)은 zero/one/multiple-region grounding과 non-groundable 문장을 이미 다룬다. 단순 빈 출력 학습은 새 기여가 아니다. 공식 코드에는 PadChest 적응 checkpoint도 있으므로 향후 비교 시 train 중복을 확인해야 한다. 현재 실행 제약은 `research/results/iter_040/medgrounder/feasibility.json`에 보존돼 있다. 이번에는 설치·환경 혼합으로 이를 우회하지 않는다.
- [Counterfactual Visual Grounding Uncertainty](https://arxiv.org/html/2606.28520v1)는 grounding verifier와 entity perturbation으로 hallucination을 평가한다. 따라서 grounding을 사실 검증에 쓰는 아이디어 자체도 신규성이 아니다. 이번 진단의 가치는 우리 실제 SFT 자산이 부재 거부를 보존하는지와 단순 presence gate의 충분성을 결정하는 데 있다.
- [CORAL 연구](https://arxiv.org/abs/2607.03647)는 영상 교체 대조 평가와 hard-negative LoRA 학습을 다룬다. 일반적인 영상 의존성 검사나 contrastive loss로 기여를 주장하지 않는다.
- [PadChest-GR 제공자 설명](https://www.microsoft.com/en-us/research/blog/padchest-gr-a-bilingual-grounded-radiology-reporting-benchmark-for-chest-x-rays/)은 양성·음성 문장 구성과 양성 finding의 box annotation 절차를 설명한다. 음성 문장 원문은 reference 확인에만 쓰고 추론 입력에는 넣지 않는다.

## 선택과 남은 한계

공동 방법 개선은 원 계획의 보류 조건을 유지한다. 모듈형 전문 grounder 비교는 실행 경로가 막혀 있다. 새 데이터 수집보다 현재 승인된 영상과 직접 SFT를 활용해 specificity를 한 번 확인하는 편이 판단 비용이 작다. iter_018의 부분 evidence에 따른 QA 손상과는 개입·질문이 다르며 그 불확정 결과를 재시도하지 않는다. 이번 선택은 새 한계의 확증이나 방법 개발 승인이 아니다. 신규성, 외부 일반화, 다른 질환 및 mixed positive/negative SFT 대비 효용은 남는다.

코드 수정·파일 생성·모델 실행은 하지 않았다.
