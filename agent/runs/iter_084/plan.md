# 요약

- **이번에 할 일:** PadChest-GR에서 기존 RSNA 위치 학습 adapter와 CURE의 판독을 비교한다. 누락 회복, 불확실 표현, 명시적 정답과의 모순을 분리한다.
- **필요한 이유:** 수동 결과의 양성 언급은 7/20→10/20이지만 확정 표현은 7/20→6/20이었다. 언급 증가를 판독 개선으로 해석할 근거가 부족하다.
- **확인할 기준:** 간단한 판독 prompt와 CURE의 영역 결합 이후에도 중요한 정확성 문제가 남는지 본다. 신규 학습은 하지 않는다.
- **주의·다음:** 개발 자료의 assistant 의미 평가다. 임상 gold·독립 확인·새 contribution으로 부르지 않으며, full review에서 다음 방법 투자를 판단한다.

## 알림 맥락

- 연구: 위치 학습과 판독 정확성
- 데이터: 흉부 X-ray RSNA 수동 관찰 → 문장 정답이 있는 PadChest-GR
- 모델: MedGemma 1.5와 기존 RSNA adapter, MedGemma 1과 공개 CURE adapter; 신규 학습 없음
- 과제: 흉부 X-ray에서 소견·판독문 또는 영역별 설명을 생성한다
- 가설: 위치 학습 뒤 증가한 언급은 실제 누락 회복 또는 불확실·잘못된 언급 증가일 수 있다
- 질문: 더 많이 말하는 것이 더 정확히 읽는 것인가?
- 변경: 방향 전환
- 연결: iter_083 MRI 자료 복구는 사용자 결정으로 보류하고, 기존 grounding 개선과 수동 판독 관찰을 이어받는다
- 작업: 공식 모델 실행과 문장별 비교로 기존 해결책의 충분성 및 다음 개입의 대상을 판단한다

# Current Understanding

iter_012의 RSNA LoRA grounding 개선은 검증된 자산이다. iter_016/017은 yes/no·검출 정보 전달 결과이며 자유 판독을 검증하지 않았다. iter_035/036 및 iter_037 정정은 detector의 위치·운영점 trade-off에 관한 것으로 판독문 전이의 반증이 아니다. iter_046/048은 적응 MedGrounder와 직접 공동 SFT의 강한 대안을 확인했다. 해당 bbox 투자의 보류를 판독 전체로 확대하지 않는다. iter_047은 제한된 교정 설계의 실행 실패다.

수동 60명 결과와 protocol·source hash에 대한 round_01 점검은 계승한다. present+possible과 present-only의 결과가 다르고, 정답 의미도 폐렴성 opacity 관련 범위로 제한된다. 원본 수치·평가기·파일을 수정하거나 자동 validated로 승격하지 않는다.

iter_083의 실제 영상 연결·모델 가설은 미실행이다. 직전 리뷰의 MRI 복구 권고를 바꾸는 근거는 새로운 실패 판정이 아니라 사용자 보완 `20261006_234642_25245390`이다. GOAL과 iter 번호·모든 원본을 보존한다. 옛 MRI 우선·iter_080 이후 지시는 현재 RESEARCH_FOCUS로 대체한다.

# Strategy Check / 연구 방향 판단

**이어받는 관찰 → 남은 설명 → 이번 비교 → 바뀔 결정:** 위치 출력은 학습으로 개선됐지만 자유 판독의 언급 변화는 불확정이다 → 정답 회복, 불확실 표현, 언급 성향, 평가 의미 차이가 남는다 → 같은 base–adapter와 단순 prompt, CURE 단일·영역 결합 판독을 명시적 문장 정답에서 비교한다 → 기존 방식 채택·방법 투자 보류 또는 구체적인 최소 개입 후보를 선택한다.

초기 질문은 다음과 같이 정리한다.

1. **누락 감소 vs 언급 성향 — 선택:** 실제 수동 관찰과 직접 연결되며 checkpoint를 재사용할 수 있다. RSNA만의 target 의미 한계를 피하기 위해 PadChest-GR로 구체화한다.
2. **위치–문장 연결 — 후속 후보:** 이번에 생성되는 영역 설명과 전체 판독에서 어떤 소견·극성·위치가 갈리는지 보조 분석한다. 별도 모든 위치 과제로 확대하지 않는다.
3. **학습 범위 밖 전이·보존 — 이번 주장 제외:** RSNA adapter의 PadChest 출력은 전이 탐색이지만 학습 노출과 모델별 분포가 다르므로 보편적 보존·망각을 입증하지 못한다.

현재 방법의 개선은 유효한 판독 실패가 정해지기 전이므로 보류한다. 원인·능력 전이 진단을 우선하며 MRI나 다른 modality 순회는 하지 않는다. 새 데이터 사용 자체가 새 research_track을 뜻하지 않는다. 반면 기존 bbox 현상을 동일한 판독 현상으로 확인했다고 쓰지도 않는다.

CURE는 이미 영역별 출력 결합의 이득과 trade-off를 다룬다. 따라서 단순 recall 증가, 오답 발견 또는 모델 순위만 남으면 신규 방법 투자를 정당화하지 않는다. 문헌상 알려진 범위는 받아들이고, 이 자료에서 다음 개입이 구별할 실패 조건이 있는지를 본다.

지배 비용은 CURE의 영역별 생성과 의미 평가가 될 것으로 예상한다. 이는 추정이며 D8에서 실제 시간을 기록한다. 과거 GPU·감사 시간을 서로 다른 범위인 채 합산하지 않는다. 이번 계획은 원문 재독해나 범용 verifier 개발보다 실제 출력 비교를 우선한다.

# Hypothesis

- **H_recovery:** 추가 언급이 명시적 정답 소견을 확정적이고 모순 없이 회복한다.
- **H_propensity:** 추가 언급이 불확실 표현·명시적 음성과의 충돌·정답으로 판정할 수 없는 추가 주장에 치우친다.
- **H_prompt:** adapter에서 보인 변화의 상당 부분을 base의 간단한 체계적 판독 prompt가 제공한다.
- **H_existing:** CURE의 강한 영역 결합 방식으로 중요한 누락이 이미 해소된다.
- **H_residual:** 영역 설명에는 정답 소견이 나타나지만 결합 결과에 상충하는 소견이나 극성이 함께 남아 실제 판독의 신뢰성을 제한한다.

이 가설들은 출력 수준의 설명이다. 문장 recall 증가만으로 내부 인식의 개선을 주장하지 않는다. H_residual도 기존 문헌에 없는 새 현상이라고 가정하지 않는다.

# Limitation Evidence / Correct Usage Checks

`lesion-grounding-generalization`, `qa-format-compliance-after-grounding-sft`, `rsna-evidence-interface-sensitivity`는 기존 자산과 해석 경계를 연결한다. 새로운 판독 문제의 validated 근거를 대신하지 않는다. 역할은 diagnostic, method_stage는 none이다.

MedGemma 1.5는 revision `91850547d9f0b2fdd21aa7c5f4f3d1a8a52c243b`와 iter_012 seed17 adapter를 사용한다. adapter 경로는 `results/iter_012/train/lr2e-4_s17/epoch_05`, 수동 protocol의 예상 digest는 `e13f3c4461b826a060c90dfe4e4ee4c2ebac36a08f84be1a45a37495816cec11`이다. 기존 정상 사용 증거는 불변 조건에서 재사용하되 새로운 PadChest tensor 연결은 실제 확인한다.

CURE는 `pamessina/medgemma-4b-it-cure`와 정확한 `google/medgemma-4b-it`를 사용한다. 구현 전에 official repository·base·adapter·processor의 실제 revision과 라이선스·접근 조건을 잠근다. config의 base revision이 null이라는 사실을 동일 revision 보장으로 해석하지 않는다. NF4, double quantization, bf16 compute/storage와 공식 PEFT 로딩 및 modules_to_save를 확인한다. custom RSNA LoRA loader를 적용하지 않는다.

CURE 공식 영상 변환과 448×448·deterministic CLAHE를 사용한다. M1 NF4 paired 대조도 같은 변환을 받는다. M1 bf16 일반 판독은 공식 base 경로를 따르고 입력 차이를 기록한다. 1.5 쌍은 같은 값 보존 변환과 processor를 사용한다. 서로 다른 pipeline을 같다고 보고하지 않는다.

공식 notebook의 소수 입력과 wrapper에서 tensor·token 연결을 확인한다. 생성 결과의 정답 여부를 기술 gate로 사용하지 않는다. 내용 오답과 형식 오류를 별도 측정한다. bbox 파싱 실패만으로 읽을 수 있는 소견 문장을 삭제하지 않는다.

# Contribution Path / Baselines / Reuse

가까운 방법은 [CURE](https://arxiv.org/abs/2601.15408), [MAIRA-2](https://arxiv.org/abs/2406.04449), [PadChest-GR grounding 기반 판독 연구](https://proceedings.mlr.press/v315/aas-alas26a.html)다. CURE의 GRG·hybrid 범위를 확인했으며, 마지막 연구의 상세 추론 영역 제공 조건은 아직 미확인이다. Phrase-grounded APO 원문 접근도 미완료다. 이 때문에 이번 결과로 신규성을 승인하지 않는다.

**고정 비교 조건:**

| 조건 | 모델·입력 | 환자당 생성 |
|---|---|---:|
| M15-R | MedGemma 1.5 bf16, 중립 판독 | 1 |
| M15-S | 같은 base, 체계적 판독 | 1 |
| B0-R | iter_012 RSNA adapter, 중립 판독 | 1 |
| B0-S | 같은 adapter, 체계적 판독 | 1 |
| M1-R | MedGemma 1 bf16, 공식 일반 판독 | 1 |
| M1-G | pristine MedGemma 1 NF4, CURE와 같은 GRG 입력 | 1 |
| C-G | CURE NF4, 공식 GRG | 1 |
| C-H | 같은 CURE, AGRG-29와 C-G 결합 | 추가 29 |

총 36회 생성으로 8개 판독 조건을 얻는다. C-G를 C-H에서 다시 생성하지 않는다. C-G−M1-G가 정밀도·prompt를 맞춘 adapter 비교다. C-H−C-G는 같은 checkpoint의 추가 질의 효과다. C-H와 M1-R의 차이는 시스템 비교이며 위치 학습 효과가 아니다. adapter disable만으로 M1-G를 만들지 말고 pristine base의 저장 모듈까지 보장한다.

C-H는 공식 29개 위치를 고정 순서로 전부 사용한다. 환자 정답·GT box로 질의 위치를 고르지 않는다. 원문과 문장별 출처를 보존하고 공식 결합 방식을 확인한다. 의미 있는 문장을 사후 제거하거나 LLM으로 유리하게 요약하지 않는다. 동일 사실 중복은 평가에서 한 번만 세되 반대 극성은 유지한다.

중립 판독은 수동 protocol의 영어 prompt를 그대로 사용한다. 체계적 판독은 여기에 `Systematically review the lungs, pleura, cardiomediastinal silhouette, bones, and visible devices. Mention an abnormality only when supported by this image, and distinguish definite from uncertain findings.`를 추가한다. M1-R은 공식 일반 판독 prompt `Describe this X-ray`를 사용한다. M1-G/C-G는 `Generate a grounded report.`를 사용한다.

이번에는 MAIRA-2와 신규 detector+reporter 학습을 추가하지 않는다. 먼저 base 쌍·단순 prompt·강한 CURE 조건이 다음 선택을 구분한다. 이는 타 계열과 모듈형 대안의 충분성을 확인했다는 뜻이 아니다. 최소 방법 pilot을 선택할 때는 해당 잔여 문제에 맞는 report-only/joint SFT 또는 실용 grounder+reporter와 가까운 preference 방법을 비교 계획에 포함한다.

새 기반은 재사용 승인 iter_082다. `reuse_assets`의 iter_043 11개 파일은 SHA·blob·의존성을 확인했다. 승인 범위는 helper와 제한된 runner 경로다. 새로운 `report84_*` 실행 경로에서 이를 연결하고, 기존 evaluator를 판독 평가기로 전용하지 않는다. 상위 `manual_experiments/rsna_report_transfer/`는 읽기 전용 참고이며 수정·이동·자동 커밋하지 않는다.

# Proposed Experiment

## 1. 자료 적합성과 사전 잠금

로컬 `results/datasets/padchest_gr/raw/grounded_reports_20240819.json`과 `master_table.csv.zip`, 기존 분할 ZIP을 사용한다. round_02의 후보 집계는 327영상·323환자이며 최종 적격 수가 아니다.

보고서 내용 접근 전에 master의 split·환자 ID와 기존 보호 manifest를 연결한다. H192/F120/test를 제외한다. 기존 다른 manifest와 환자·study·영상·pixel 중복도 확인하고 노출 이력을 기록한다. 공식 validation은 CURE 선택에 사용됐을 수 있으므로 새 독립 test 또는 모든 모델에 미노출인 자료라고 부르지 않는다. CURE 공개 코드의 split 연결과 학습 목록을 확인할 수 있는 범위까지 기록한다. 실제 train 노출이 확인된 환자는 주분석에서 제외하고 부족하면 탐색 범위를 줄인다.

환자당 하나의 현재 frontal image를 `sha256(84017|PatientID|ImageID)` 순으로 선택한다. 과거 영상이 없으면 판정할 수 없는 변화·비교 문장은 평가 대상에서 제외하되 현재 상태가 분리되는 문장은 보존한다. crop이나 bbox 제거로 음성 정답을 만들지 않는다.

출력 전에 원문에서 평가 가능한 사실을 작성한다. 단위는 소견, 위치·범위, 극성, 확실성 및 명시된 속성이다. 영어·스페인어 불일치와 모호한 범위는 표시한다. generic 정상 문장을 질환 목록의 음성으로 확장하지 않는다. 비정상 문장이 없는 층은 표본 층화일 뿐 정상 임상 gold가 아니다.

D8은 기존 D24에서 고정 hash 순으로 선택하고 개발 평가와 분리한다. E96은 평가 가능한 현재 비정상 소견을 포함한 48명과 비정상 표기가 없는 48명을 목표로 고정한다. E192의 다음 48+48명도 출력 전에 잠근다. 한 층이 부족하면 존재하는 적격 인원을 모두 사용하고, 그 부족과 해석 범위를 생성 전에 기록한다. 새로운 표본원을 임의로 섞지 않는다.

96명은 환자 단위 비율의 최악 조건에서 대략 ±10 pp, 각 48명 층은 ±14 pp 수준인 탐색 규모다. 이는 paired 차이의 power 보장이 아니다. 192명은 표준오차를 대략 0.71배로 줄일 수 있어 판단 경계를 좁힐 가치가 있을 때만 사용한다.

## 2. 동작 확인과 평가 규약 고정

D8에서 8개 조건을 실제 생성한다. 입력·ID·GT 분리, tensor·token, EOS와 출력 길이, adapter 연결, 메모리·처리량, 중단 재개를 확인한다. 공식 예제와의 입력 동등성을 기록하되 모델 정답률 100%는 요구하지 않는다.

greedy·seed17을 사용한다. 최초 cap은 1,024이며 EOS 없이 cap에 도달한 요청만 같은 입력으로 2,048→4,096까지 재생성한다. 모든 시도·비용을 보존하고 최종 비EOS는 실패 유형으로 포함한다. 이는 공식 평가 스크립트의 짧은 기본 cap과 다른 길이 보호 조건임을 명시한다. 출력이 마음에 들지 않는다는 이유로 재시도하지 않는다.

D8에서 의미 판정 규약과 fixture를 확정한다. 모델명·학습 여부를 숨긴 출력 ID를 사용하고, 판정 근거가 된 원문 구간과 reference ID를 저장한다. 문체로 모델을 추측할 수 있어 완전한 눈가림은 아니라는 점도 기록한다. 구현 담당 assistant의 의미 판정은 전문의 판독이 아니다.

규약은 E 생성 전에 hash로 잠근다. 이후 발견한 구현 오류는 전 조건에 같은 수정으로 적용하고 이전 판정표도 보존한다. 유리한 parser·동의어·불확실성 기준을 결과별로 선택하지 않는다.

## 3. 가능성 탐색 E96

모든 적격 환자에 고정 8조건을 적용한다. 과제·모델별 batch/worker 구성은 D8에서 고정하고 결과를 보고 선택하지 않는다.

문장 평가에서는 다음을 구분한다.

- reference의 확정 소견이 확정적으로 기술됐는가;
- possible 표현으로만 언급됐는가;
- 위치·극성·명시적 속성이 reference와 충돌하는가;
- 생성한 추가 사실을 reference가 지지하는가, 반박하는가, 판단할 정보가 없는가;
- 같은 판독 안에 양성·음성 또는 양립 불가능한 위치·속성이 함께 있는가;
- 거부·형식 실패·비EOS로 평가할 정보가 부족한가.

전체 표본에 같은 구조화 판정을 적용한다. 기존 구현 세션의 assistant 검토를 사용하며 평가를 위해 새로운 유료 API나 별도 judge 모델 호출을 추가하지 않는다. 정상 문장·반복 문장은 정확히 같은 내용만 묶어 처리하고, 임상적 동의어를 자동 동일시해 근거를 삭제하지 않는다. 평가 시간도 비용 ledger에 기록한다.

모델별·층별 고정 hash 표본 24명에 대해 모든 조건의 근거 문구를 다시 점검한다. 모호한 판정과 투자 결정을 좌우하는 모순·회복 사례도 확인한다. 이는 독립 전문가 합의가 아니다. full review가 원시 근거와 일부 의미 판정을 별도로 확인한다.

## 4. 조건부 규모 확대

E96에서 기술·평가 경로가 유효하고, 모호한 판정을 가장 불리하게 처리해도 같은 방향의 차이가 남으며, 환자 표본 변동만이 다음 투자 판단을 막을 때 E192로 확대한다. 추가 표본으로 줄일 불확실성, 현재 CI와 예상 정밀도, 실측 실행 비용을 실행 전에 기록한다.

차이가 한 환자에 의존하거나, reference 의미·모델 학습 노출·평가자 해석 때문에 판단이 바뀌면 표본 확대를 하지 않는다. 허용된 의미 재검토는 현재 사례의 근거 확인이며 prompt·학습·평가 목표 변경이 아니다. E192를 열고 조건을 다시 조정하지 않는다.

## 5. 독립 확인

이번에는 독립 test·다중 seed·신규 학습을 실행하지 않는다. 유망한 잔여 문제가 있으면 현재 자료를 개발 자료로 고정한 채 별도 계획에서 독립 환자와 강한 비교군을 정한다. 이번 탐색과 조건부 확대를 confirmatory로 이름 붙이지 않는다.

# Implementation Tasks for Claude

현재 구현 담당은 Codex이며 이 섹션명은 공통 형식이다.

1. 승인 기반·선별 반입을 확인하고 `results/iter_084/`에 새 protocol·manifest·requests·raw outputs·assessments·metrics·completion을 작성한다. 기존 수동 파일과 결과를 덮어쓰지 않는다.
2. CURE 공식 source와 checkpoint를 별도 결과 경로에 고정한다. 추가 설치가 필요하면 사용자에게 먼저 알리고, 승인된 범위의 격리 환경을 구성한다. 알림을 불필요한 재승인 대기로 바꾸지 않는다. 기본 medgemma 환경과 `hf_cache/`는 변경하지 않는다.
3. metadata reader와 보호 집단 제외를 연결하고 소수 실제 영상·문장부터 검사한다. 전체 archive 재다운로드나 무관한 전수 감사를 시작하지 않는다.
4. 1.5 custom adapter 경로와 CURE PEFT 경로를 분리한다. 각 processor·변환·token·revision·정밀도·adapter digest를 출력에 연결한다. 공식 CURE loader의 base/adapter 정밀도 차이는 계획의 두 M1 조건으로 명시한다.
5. `pg43_run`의 검증된 claim·재개·완료 연결을 새 report runner에 재사용한다. 요청 ID는 환자·모델·prompt·위치·protocol을 포함한다. worker 수와 GPU 수를 분리하고 동일 GPU의 복수 worker를 지원한다.
6. 실행 직전 `nvidia-smi`로 허용 GPU 0,1의 여유를 확인한다. D8에서 GPU당 1 worker와 유망한 batch 확대 또는 GPU당 2 worker 중 하나를 우선 비교한다. 처리량·peak VRAM·긴 출력 p95·OOM·CPU/RAM/I/O 경합과 출력 정합성을 기록한다. worker별 peak와 최소 2 GiB 여유를 합산해 배치한다. 느려지거나 메모리가 부족하면 줄이고 근거를 남긴다.
7. 독립 모델·영상 shard를 두 GPU에 배정한다. 1.5 bf16의 과거 8–10 GiB는 참고이며 새 입력 peak를 측정한다. CURE NF4도 embeddings·KV cache·긴 출력을 포함해 실측한다. `device_map=auto`가 의도치 않게 다른 worker의 GPU까지 점유하지 않게 허용 집합과 장치 매핑을 확인한다.
8. 중립·체계적 prompt, CURE 29개 위치와 결합 규칙, 평가 코드와 판정 규약을 생성 전에 잠근다. 원본 생성을 보존하고 판독 text와 bbox metric을 분리한다.
9. 원시 판정표에서 주수치와 bootstrap을 별도 구현으로 재계산한다. 누락·중복·조건별 분모·미판정 항목·현 입력 hash와 완료 상태를 검증한다. 보고서는 `SELF_CHECK: PASS/FAIL`, `SUMMARY:` 형식을 유지한다.

**시간·자원 계획:** 수동 RSNA의 요청당 생성 시간은 base 약7.36초, SFT 약10.48초였으며 다른 입력·CURE의 실측이 아니다. 이를 단순 산술 참고로만 적용하면 E96의 3,456요청은 약7.1–10.1 worker-hours, 두 worker의 이상적인 wall은 약3.5–5.0시간이다. 모델 로딩·평가·CURE의 다른 출력 길이·NF4 성능은 포함하지 않는다. D8 후 `요청 수×과제별 실측 시간/유효 동시성`으로 다시 산출한다. E192는 추가 3,456요청이며 무조건 실행하지 않는다. 구현·설치·의미 평가 시간은 따로 기록한다. 시간 경과만으로 중단하거나 재승인을 요구하지 않는다.

학습 checkpoint는 새로 만들지 않는다. inference는 요청별 원자적 결과와 protocol digest로 재개한다. 프로세스가 끝나기 전에 완료 보고서를 쓰지 않는다. 코드 보존 커밋·branch 관리는 orchestrator가 담당한다.

# Evaluation (성공/실패 기준 포함)

## 주평가

1. **확정 소견 recall:** 평가 가능한 확정 reference 사실 중 올바른 소견·극성으로 회복된 비율을 환자별 계산 후 평균한다. 위치·명시 속성까지 맞는 엄격한 recall을 함께 보고한다. reference에 양성 사실이 없는 환자는 이 분모에 넣지 않는다.
2. **명시적 모순:** reference가 판단 가능한 범위에서 반박하는 주장의 환자 비율과 환자당 건수다. 미표기 사실은 FP로 세지 않는다. 명시적 부정이 있는 환자·사실의 별도 분모와 coverage를 보고한다.
3. **불확실성·미판정:** definite/possible/negated/unmentioned 및 reference로 판정 불가한 추가 주장 수를 분리한다. possible을 회복으로 포함한 민감도 분석을 주분석과 나란히 제시한다.
4. **내부 모순·효율:** 같은 판독 안의 상충 사실, 중복을 제외한 사실 수, 생성 token, 환자당 요청량·wall·device 시간·peak VRAM을 기록한다.

생성 사실의 supported/contradicted/unverifiable 비율을 보고한다. `unverifiable`을 모두 틀림 또는 모두 맞음으로 둔 precision 범위를 함께 제시하며 이를 임상 precision이라고 부르지 않는다. 명시적 양성·음성이 모두 정의되는 사실 부분집합에서는 definite-only와 definite+possible의 운영점을 비교한다. 같은 FP 수준을 실제로 구성할 수 없으면 보간해 만들지 않고 matched-FP 결론을 보류한다.

주 paired 비교는 B0-R−M15-R, M15-S−M15-R, B0-S−M15-S, C-G−M1-G, C-H−C-G다. M1-R과 다른 조건의 비교는 시스템 성능 참고다. 환자 단위 paired bootstrap 10,000회·seed84017의 95% CI를 보고한다. 두 층은 따로 집계하며 50:50 평균을 모집단 prevalence 성능으로 해석하지 않는다. 29개 영역 출력을 독립 환자처럼 세지 않는다. 순차 확대 뒤의 CI는 탐색적이며 확증 검정으로 사용하지 않는다.

bbox는 CURE 출력의 보조 근거로만 평가한다. reference와 의미가 대응되고 공식 box가 있는 사실에 한해 cxcywh→원본 xyxy 변환 후 IoU를 계산한다. 미언급 사실·invalid box·box 없는 reference를 각각 보고한다. bbox 점수가 detector보다 높아야 판독 비교가 통과하는 조건은 두지 않는다.

## 사전 투자 기준과 결과별 행동

최소 가치의 작업 기준은 **확정 소견 recall 10 pp 증가에 모순 환자 비율의 증가가 5 pp 이내인가**다. 이는 임상 허용 오차나 모든 실험의 보편 문턱이 아니라, 열 명 중 한 명 수준의 소견 회복을 위해 추가 생성·평가 비용을 감수할지 판단하는 이번 개발 기준이다. 원시 수·CI·정답 coverage·평가 민감도를 함께 검토하며 점추정치 하나로 통과시키지 않는다.

- **회복 근거:** 위 수준의 회복이 불확실 표현 포함 여부에 견디고 여러 환자에서 나타나면 해당 baseline을 보존한다. B0의 변화가 base의 체계적 prompt로 같은 비용 수준에서 재현되면 특수한 위치 학습 효과 주장을 좁힌다.
- **기존 방식의 충분성:** CURE hybrid가 중요한 누락을 회복하고 평가 가능한 범위에서 모순 비용이 작으면 그 성공을 받아들인다. 동일 조건의 새로운 누락 감소 방법 투자는 보류한다. 미판정 주장·학습 노출 때문에 일반적 충분성을 선언하지 않는다.
- **구체적 잔여 문제:** CURE의 영역 출력이 회복한 확정 소견과 함께 명시적 모순이 여러 환자·소견군에 남고 단순 prompt로 해소되지 않으면, 후속 후보를 해당 출력의 선택·통합으로 제한한다. full review가 observed 근거·사용법·blocker를 확인한 뒤에만 최소 method pilot을 제안한다. 단순 trade-off 재현이면 이 분기를 선택하지 않는다.
- **음성:** 추가 언급이 possible·모순·미판정 증가이고 확정 회복이 없으면 현재 adapter의 판독 개선 경로를 보류한다. grounding 자체의 성과는 유지한다.
- **불확정:** CI만이 결정을 막고 예상 정밀도 개선이 실질적이면 E192로 한정 확대한다. 의미 평가나 정답 coverage가 지배하면 관련 원문 판정만 보완한다. 이후에도 판단이 남으면 방법 투자를 보류하고 재개에 필요한 독립 정답·노출 확인 또는 강한 대조를 명시한다. 다른 modality로 자동 전환하지 않는다.

기술적으로 유효한 전체 대조와 투자 결정이 이번 diagnostic의 완료 조건이다. 코드 통과·CURE 로딩·전체 요청 완료를 가설 지지나 연구 목표 달성이라고 보고하지 않는다.

# Risks / Checks

- PadChest reference는 완전한 임상 gold가 아니다. 일반 정상 문구·번역·시간 비교·희귀 소견의 의미를 과도하게 확장하지 않는다.
- 공개 모델의 학습·validation 노출을 기록한다. 이번 자료는 개발 평가이며 독립 일반화·임상 성능을 주장하지 않는다.
- CURE hybrid의 PadChest 적용은 확장 검증이다. 실패해도 논문 benchmark 재현 실패라고 부르지 않는다.
- CURE의 긴 결합 출력에서 중복을 여러 TP로 세거나 상충 문장을 임의로 제거하지 않는다. 원문·출처·모호성을 보존한다.
- 단일 seed·고정 prompt·assistant 판정의 한계를 보고한다. 평가자 합의나 자동 metric을 임상 사실의 확정으로 쓰지 않는다.
- 추가 환경은 알림 후 격리하며 기본 환경·기존 캐시·다른 사용자 GPU 프로세스를 변경하지 않는다. 접근 동의가 실제 blocker라면 필요한 자산과 조건만 특정한다.
- 새 방법과 차별성을 주장하기 전에 MIDL grounding 연구 및 Phrase-grounded APO의 미확인 본문 조건을 확인한다. 이번에는 문헌을 추가로 순회하며 실제 출력을 미루지 않는다.

## 대규모 GPU 필요 후보

동일 영상·문장 노출량 아래 report-only, box-only, joint, curriculum 학습을 여러 모델·기관에서 비교하는 factorial 실험을 장기 후보로 보존한다. 현재 두 GPU에서는 이번 실제 출력으로 필요한 비교를 좁히고, 유효한 잔여 문제가 확인된 뒤 경량 적응부터 검토한다.

# 계획의 근거 (GPT 조사 노트)

# 이번 라운드의 결정

RSNA 수동 결과를 그대로 확대하지 않고 **PadChest-GR에서 누락 감소와 언급 성향을 구분하는 실제 출력 진단**을 수행한다. 기존 RSNA adapter는 전이 비교 자산으로 유지한다. 새 학습은 하지 않는다.

## 직전 세 질문에 대한 답

1. **자료·평가 단위:** RSNA 표적 정의는 폐렴성 opacity 관련 언급과 effusion/atelectasis 기술을 구분한다. 이를 전체 판독 정확성으로 넓힐 수 없다. PadChest-GR 원본에는 `sentence_en`, `sentence_es`, `abnormal`, 양성 소견의 `labels/locations/boxes`가 있어 명시된 사실 단위의 누락·모순을 비교할 수 있다. 다만 미언급 사실은 음성이 아니며, 일반적인 정상 문구도 모든 질환의 부정을 뜻하지 않는다.
2. **CURE 강한 대조:** 공식 GRG와 AGRG-29+GRG를 모두 사용한다. 전자는 PadChest-GR의 공개 과제 인터페이스이고, 후자는 MIMIC-CXR에서 사용한 방식을 PadChest-GR에 적용하는 확장 조건이다. 둘의 성능·요청량을 분리한다. 단일 GRG만으로 CURE 전체의 부족함을 선언하지 않는다.
3. **가까운 연구의 입력 조건:** MIDL 2026 연구의 공개 초록은 full image+grounding mask 및 region-to-text를 명시한다. 그러나 이번에도 PDF는 content-type 오류 또는 OpenReview browser challenge로 본문 확인을 완료하지 못했다. 따라서 추론 시 GT 영역 사용 여부·split·예산 대조는 미확인이다. 이 연구가 training-only supervision 효과를 입증했거나 입증하지 못했다고 단정하지 않는다. 이 미확인은 신규성 주장과 방법 설계의 남은 확인 사항이며, 이번 비학습 출력 진단을 막는 이유로 삼지 않는다. [논문 페이지](https://proceedings.mlr.press/v315/aas-alas26a.html)

## 새로 확인한 실행 근거

- `agent/runs/iter_084/think/round_01.json` 원문을 읽고 이전 근거를 계승했다. 관련 리뷰의 실제 판정·failure_scope와 LIMITATIONS/CODE_ASSETS의 관련 항목을 확인했다.
- PadChest-GR 원본은 4,555영상이며 master table 기준 train 3,185, validation 455, test 915다. 기존 iter_039 manifest의 보호 환자를 제외한 validation 후보는 327영상·323환자다. 이 후보에서 비정상 문장이 있는 영상 192개, 없는 영상 135개, `abnormal=false` 문장이 있는 영상 238개를 읽기 전용으로 집계했다. 이는 최종 적격 표본 수가 아니다. 현재 영상 연결·시간 비교 문장·환자 대표 선택은 구현에서 검사한다. test 보고서 내용은 이번 점검 대상으로 열지 않았다.
- 후보 문장에는 특정 소견의 명시적 부정과 `No other relevant findings` 같은 범위가 제한된 문장이 섞여 있었다. 전체 정상·질환별 음성으로 일괄 변환하지 않는 평가가 필요하다.
- CURE 공식 실행기는 AGRG-29의 위치에서 `Locate and describe the {location}.`을 사용한다. 전체 29개 위치는 `SUPPORTED_LOCATE_AND_DESCRIBE_LOCATIONS`에 있다. hybrid는 각 출력과 GRG를 결합하는 방식이며, PadChest 적용을 원 benchmark 재현으로 부르지 않는다. [공식 실행 코드](https://raw.githubusercontent.com/PabloMessina/CURE/main/scripts/eval_report_generation.py), [위치 목록](https://raw.githubusercontent.com/PabloMessina/CURE/main/vlm_research_kit/data/datasets/chest_imagenome_dataset.py)
- 공식 loader는 adapter에 NF4를 사용하지만 adapter 없는 base는 bf16으로 로드한다. 그러므로 공개 시스템 비교와 정밀도를 맞춘 base→adapter 비교를 분리해야 한다. CURE의 `modules_to_save` 때문에 adapter disable만으로 pristine base를 복원했다고 가정하지 않는다. [공식 loader](https://raw.githubusercontent.com/PabloMessina/CURE/main/vlm_research_kit/utils/model_utils.py)
- 현재 research HEAD는 `60b471e524aa59709473c8663db6d8f1c36d8870`, 작업 트리는 깨끗했다. 새 기반은 전체 재사용 승인 iter_082로 명시하고, iter_043의 승인 helper 11개를 선별 반입한다. 실제 source SHA·blob·import와 기반의 파일 부재를 확인했다.

## 문헌 해석과 남은 한계

CURE는 이미 영역 결합에 따른 recall 증가와 precision 비용을 보고한다. 따라서 같은 trade-off의 존재는 새 기여가 아니다. 이번 비교는 기존 방식이 충분한 범위와 후속 개입이 필요한 구체적인 출력 실패를 선택하기 위한 것이다. [CURE §9.2.4](https://arxiv.org/html/2601.15408v1#S9.SS2.SSS4)

MAIRA-2는 가까운 공동 grounding/reporting 방법으로 유지한다. 첫 실행에서는 정확한 base 쌍과 CURE의 강한 조건을 우선한다. 다른 계열 재현을 이번 diagnostic의 hard gate로 만들지 않으며, 새 방법의 일반성·우위 주장 전에는 포함한다. [MAIRA-2](https://arxiv.org/abs/2406.04449)

Phrase-grounded APO의 원문은 여전히 403으로 확인하지 못했다. 이를 실행한 baseline이나 반박한 방법으로 쓰지 않는다. 방법 개발을 결정한다면 해당 preference·교정 방식과의 중복을 먼저 확인한다.

신규 모델 실행·설치·파일 수정은 수행하지 않았다. 로컬 Python의 외부 조회는 DNS 오류였지만 web 도구로 공식 실행 소스를 확인했다. 구현 단계의 승인된 네트워크·격리 설치 가능 여부와 혼동하지 않는다.

## 대규모 GPU 필요 후보

report-only/box-only/joint/curriculum을 동일 영상·문장 노출량으로 여러 모델과 기관에서 비교하는 factorial 학습은 장기 후보로 보존한다. 현재는 기존 checkpoint의 실제 판독 비교로 필요한 경량 적응 실험을 좁힌다.

이전 사고 라운드 노트: agent/runs/iter_084/think/
