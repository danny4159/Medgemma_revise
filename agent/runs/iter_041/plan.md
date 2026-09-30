# 요약

- **이번에 할 일:** 기존 직접 SFT B/C에서 독립 grounding과 두 문장 공동 grounding을 비교한다. 독립 요청의 실제 병렬 비용도 측정한다.
- **필요한 이유:** iter_039의 개별 능력 부족은 iter_040의 직접 SFT로 상당 부분 해소됐다. 적응 후 공동 요청의 성능은 아직 평가하지 않았다.
- **확인할 기준:** 공동 요청의 중요한 내용상 손실과 독립 처리의 비용 부담이 함께 남는지다.
- **주의·다음:** V96 개발 비교 한 번으로 종료한다. 양성이어도 작은 방법 pilot의 근거이며, 내부 원인·모듈형 우위·새 contribution은 미확정이다.

# Current Understanding

iter_039는 M0의 I-long/J-long F1@0.3=0.2951/0.2344를 관찰했지만 개별 능력이 낮아 공동 결합 가설을 판정하지 못했다. iter_040은 동일 I-short에서 B=0.5559, C=0.5780을 확보했다. 추가 문장 대조 M은 C보다 좋아지지 않았고 baseline 수렴도 미확인이므로 현재 loss 확대는 보류한다.

기준 원문은 `agent/runs/iter_039/plan.md`, `review.md`, `agent/runs/iter_040/plan.md`, `review.md`, 각 `review.json`이다. plan SHA256은 research_notes에 기록했다. 이번은 과거 E288/H192/F 확대의 재개가 아니라 적응된 모델을 대상으로 하는 새 진단이다. 기존 판정이나 기준을 소급 변경하지 않는다.

**유지:** GOAL, MedGemma 1.5, 기존 RSNA SFT·detector 성과, VinDr 승인 대기, continuation 투자 종료, 원본 데이터·결과·checkpoint를 유지한다.

**변경:** M0의 낮은 절대 성능 아래 비교에서 고정 B/C의 독립·공동 요청과 실제 병렬 비용 비교로 옮긴다.

**보류:** 추가 학습, 문장 대조 계수 탐색, T610, 추가 seed, H192, F120, test 및 MRI reserve 사용을 보류한다. 기존 일회성 영상 변환 검증과 RSNA 분석을 반복하지 않는다.

# Strategy Check / 연구 방향 판단

중요한 사용 과제는 한 영상의 여러 양성 소견 문장에 대응하는 근거 영역을 정확하고 효율적으로 반환하는 것이다. 임상 진단·정상 판정·보고서 생성 성능과 구분한다.

강한 직접 SFT 확보 후이므로 전략을 재검토한다.

1. **현재 방법 개선:** M의 추가 이득 근거가 약하다. baseline이 상승 중이라는 이유만으로 같은 loss를 확대하지 않는다.
2. **원인·능력 전이 진단:** 새 B/C는 이전의 개별 능력 제한을 바꾼다. 공동 요청 손실과 독립 처리 비용을 함께 보면 후속 방법의 필요 여부를 결정할 수 있다. 이번 선택이다.
3. **다른 연구 질문:** 보고서 근거·불확실성 과제는 후보지만 정답과 강한 baseline을 새로 확인해야 한다. 기존 질문에서 얻을 마지막 한정 정보의 비용보다 현재 준비 비용이 크다.

MedGrounder 비교를 먼저 검토했으나 기본 환경과 기존 detector 환경에서 공식 경로의 필수 의존성이 충족되지 않았다. 설치·환경 혼합·후처리 임의 재구현을 이번에 하지 않는다. 미실행을 성능 열세로 취급하지 않는다.

`language-conditioned-grounding` track을 유지한다. 직접 연결된 iter_038은 setup, iter_039는 유효 diagnostic, iter_040은 유효 method pilot이다. RSNA 전이·detector 비교와 실행 복구 이력도 related_iterations로 연결한다. iter_039 주요 생성 wall 합 약4.21시간, iter_040 train2 네 trajectory 약2.54 GPU-hours는 일부 비용이며 track 총비용이 아니다.

해결된 질문은 직접 SFT의 적응 가능성과 현재 대조항의 제한된 추가 효과다. 남은 질문은 적응된 독립 능력의 공동 요청 유지와 실제 비용이다. 이번 결과가 불확정이어도 같은 진단의 자동 확대를 하지 않는다.

# Hypothesis

- **H_retention:** 문장별 직접 SFT 이후에도 공동 요청에서 근거가 누락되거나 다른 문장에 배정될 수 있다.
- **H_interface:** 차이는 공동 요청 형식 미학습, ID·순서, 형식·출력 길이로 설명될 수 있다. 이번 비교만으로 이 설명을 제거하지 못한다.
- **H_simple:** 독립 요청을 병렬 처리하면 정확도를 유지하면서 추가 방법을 정당화할 정도의 비용 부담도 남지 않는다.

이번 역할은 diagnostic이다. 새 방법이나 학습 loss를 구현하지 않는다. 후속 학습을 택할 경우 공동 형식의 직접 CE를 먼저 강한 대조군으로 포함해야 한다.

# Limitation Evidence / Correct Usage Checks

대상은 observed 상태의 `padchest-sentence-grounding-and-joint-retention`이다. iter_040 review의 valid_experiment=true, blocking_issues=[], evidence·usage_checks를 확인했다. 이 상태를 validated로 올렸다고 가정하지 않는다.

MedGemma revision `91850547d9f0b2fdd21aa7c5f4f3d1a8a52c243b`, bf16, 공식 chat template, 기존 uint16→uint8 값 보존 변환, RGB 복제, 중앙 square padding, yxyx/0–1000 좌표를 유지한다. 새 windowing·flip·crop을 도입하지 않는다.

원본 문장·GT·환자·study·영상 hash와 selection lock을 연결한다. 기존 D24/V96을 다시 선별하지 않는다. B/C 학습 자료의 눈가림 적격성 검토가 규칙 검사로 대체됐다는 과거 한계는 유지하며, 이번 결과에 맞춰 학습 자료나 checkpoint를 변경하지 않는다.

기본 Python은 상속된 medgemma 환경을 사용한다. 시작 시 sys.executable을 기록하고 login shell의 PATH 변경을 피한다. pip install, conda activate, 환경 간 PYTHONPATH 혼합은 하지 않는다.

# Contribution Path / Baselines / Reuse

## 비교군과 필요한 증거

- **C, 주분석:** `results/iter_040/train2/C_s17/epoch_03`. adapter tensor digest는 `419ae81f5ef455d39742b158537373da6e26061b362d13205ab28b4a50905ba8`이다.
- **B, 민감도 분석:** `results/iter_040/train2/B_lr1e-4_s17/epoch_05`. digest는 `4a140948ff79092888d9d753a602f0595b7fec6909265913a091d83a6f839b79`이다.
- **독립 I:** 기존 I-short 두 요청과 결과의 단순 결합이다. 동일 영상을 각 요청에 제공하고 실제 병렬 처리를 허용한다.
- **공동 J_AB/J_BA:** `pg39_spec.prompt_J_short`를 사용한다. 반전은 문장 순서만 바꾸며 각 문장에 붙은 qA/qB ID와 GT는 유지한다.
- **그룹 교환 oracle:** 공동 예측의 qA/qB 전체 그룹을 교환했을 때의 최대 점수다. 오류 분해용이며 실용 방법이 아니다.

[MedGrounder](https://github.com/aehrc/MedGrounder)와 [해당 논문](https://arxiv.org/html/2512.01085v1)은 가까운 문장별 grounding 대안이다. 실행하지 못한 상태에서는 모듈형 대비 우위나 전체 최선의 비용을 주장하지 않는다. RSNA opacity detector를 다소견 문장 조건부 비교군으로 대신 사용하지 않는다.

정확도 차이 0.05는 현재 C F1 약0.58의 약9%에 해당하는 절대 손실로, 개발 단계의 투자 판단 기준이다. 임상적 허용 한계로 해석하지 않는다. 비용 기준은 device-seconds 25%와 실제 지연 또는 처리량 20%다. 작은 비용 차이만으로 별도 학습 방법을 개발할 가치는 낮다는 판단에 따른다.

## 코드 재사용

기존 `approach/sentence-evidence-binding`을 이어간다. HEAD `ca8be7658402eadbc0c501e877d76b1024ed2683`의 pg39 prompt·data·metric 구성요소를 사용한다. JSON reuse_assets의 다섯 파일만 iter_040에서 반입한다. 출처 blob과 현재 파일의 일치 및 대상 브랜치에서의 충돌 부재를 확인했다.

기존 pg39 evaluator의 순수 점수 계산을 재사용하고 이번 조건·입력 잠금·비용 비교를 위한 얇은 실행·평가 경로를 추가한다. pg40_train/decide, downloader, 과거 RSNA trainer와 미사용 pipeline은 정비하지 않는다.

새 결과는 모두 `research/results/iter_041/` 아래에 저장한다. 과거 protocol을 수정하지 않고, 저장 출력 검증 시 원본 SHA의 소스와 연결한다. 브랜치·커밋 관리는 orchestrator가 수행한다.

# Proposed Experiment

## 1. 분할·모델·규약 고정

기존 D24는 동작·자원 검사, 기존 E96=V96은 개발 비교로 사용한다. 환자당 기존 두 문장과 모든 box를 유지한다. share-group×multi-box 층과 작은 영역을 포함하며 결과를 보고 사례를 제외하지 않는다.

B/C checkpoint, D/V manifest, 원본 GT, source SHA, generation config, prompt 함수, parser, metric과 판정식을 실행 전에 잠근다. C를 주분석으로 선택한 것은 이미 알려진 개발 성능을 활용한 결정이므로 선택 편향을 명시한다. B를 함께 보고하고 유리한 checkpoint로 대표를 바꾸지 않는다.

## 2. 동작 확인

D24의 C에서 I_A/I_B/J_AB/J_BA를 구성한다. I는 기존 caps 1000/2000/4000, J는 2000/4000/8000을 유지하고 EOS까지 허용된 재시도를 수행한다. cap 소진은 invalid에 포함하며 임의 출력 단축으로 비용을 줄이지 않는다.

D24 중 층을 포함한 hash 순서의 D8에서 B의 같은 네 조건을 확인한다. 이 표본은 성능 선택용이 아니다. 같은 adapter의 독립 로드, template·tensor, 문장 순서와 ID, GT 좌표 왕복 및 JSON parser를 확인한다. prompt 보정 후보를 탐색하지 않는다. 명백한 구현 오류만 고친 뒤 protocol을 새 버전으로 잠근다.

학습된 단일 요청은 기존 경로와 결과를 대조한다. adapter·입력 연결이 틀리거나 평가 변경의 영향을 격리하지 못하면 본비교를 중단하고 실행 문제로 보고한다.

## 3. GPU 구성과 실제 비용 측정

실행 직전 nvidia-smi로 허용된 0,1의 물리/논리 대응과 여유를 확인한다. 여유가 큰 장치부터 배정하며 다른 사용자의 프로세스는 건드리지 않는다.

D24의 C 96요청을 총2 worker와 총4 worker로 각각 실행한다. 같은 GPU의 두 worker는 현재 전체 점유와 긴 출력 peak에 worker당 최소2GiB를 더해도 용량 안에 들어갈 때만 허용한다. 기존 17,836MiB 관찰을 공동 출력의 안전성으로 자동 전용하지 않는다.

구성 선택은 D의 처리량·메모리·오류와 token 정합성으로만 한다. V96 점수로 구성을 고르지 않는다. 4 worker가 느리거나 안전 여유가 없으면 2 worker를 사용하고 이유를 기록한다. token 차이는 입력·배치·수치 경로를 조사하고 정합성이 확보된 구성으로 고정한다.

C의 주비교에서는 독립 두 요청을 같은 환자 작업으로 묶어 실제 dispatch부터 둘 다 완료할 때까지 측정한다. J도 같은 환자 단위로 측정한다. 동일 총 GPU·worker 구성의 I/J 큐를 분리해 전체 처리량을 비교하고, 고정된 교차 순서로 실행 순서 편향을 줄인다.

loading 포함/제외 wall, 환자당 device-seconds, 전체 환자 처리량, median/p95 완료 지연, 재시도 포함 token, GPU별 allocated/reserved/전체 점유 및 CPU/RAM/I/O를 기록한다. 요청 wall 합이나 두 요청 wall의 max를 실제 병렬 지연으로 대체하지 않는다. device-seconds는 정해진 큐가 장치를 점유한 시간을 합산하며 worker가 겹친 시간을 중복 합산하지 않는다. 정밀한 커널 연산량과는 구분한다.

## 4. 가능성 탐색: 고정 V96 비교

- B/C 각각 J_AB와 J_BA를 V96 전체에서 생성한다: 384요청.
- 기존 B/C의 독립 I-short 384요청은 provenance 확인 후 정확도 기준점으로 재사용한다.
- C의 I-short 192요청만 비용 계측을 위해 다시 실행한다. 새로운 성능 후보로 선택하지 않고 기존 token과 대조한다. 불일치가 있으면 원인을 보고하며 기존·신규 수치를 선택적으로 섞지 않는다.
- 기존 M0 결과는 맥락 설명에만 사용한다. M/C_compute나 long prompt를 추가 생성하지 않는다.

기본 신규 생성은 D192+B 동작32+V576=800요청이다. 중단 복구 검사와 재시도 비용은 별도로 기록한다. 모든 기본 비교를 끝내기 전에 결과가 좋아 보인다는 이유로 종료하지 않는다.

## 5. 규모 확대·독립 확인

이번에는 학습 확대와 신규 환자 확대를 하지 않는다. 이미 생성·검증된 V96과 paired 설계를 사용해 적응 후 공동 처리 문제의 투자 가치를 확인한다. iter_039 short 차이의 CI 반폭은 약0.042였지만 적응된 모델의 분산을 보장하지 않으므로 정밀도 추정으로만 참고한다.

V96에서 결정되지 않으면 이번 질문의 투자를 보류한다. H192·F120을 자동 소모하지 않는다. 양성일 때도 다음 별도 계획에서 공동 직접 CE와 최소 보존 개입의 pilot 필요성을 판단한다. 독립 확인과 full 방법 개발은 이번 실행에 포함되지 않는다.

## 6. 예상 비용·재개

과거 C 독립192요청은 4 worker wall376.64초, 평균 generate6.37초/요청이었다. 공동 출력·검사·loading을 고려해 GPU 실행 초기 ETA를 약0.5–2시간으로 둔다. 긴 비EOS 출력이 많으면 더 길 수 있으며 D 실측으로 갱신한다. 이는 임의 timeout이나 중단 상한이 아니다.

요청마다 완료 record를 원자적으로 보존하고 worker별 파일·claim을 사용한다. 중단 시 기존 부분 행의 바이트를 별도 보존한 뒤 해당 worker 소유 파일만 복구한다. 현재 입력·코드·config가 바뀌면 기존 결과에 이어 쓰지 않는다. launcher는 child 종료와 전체 예상 요청 집합을 확인한 뒤에만 완료를 기록한다.

# Implementation Tasks for Claude

1. 기준 plan/review와 reuse_manifest를 읽고 기존 브랜치·반입 자산·B/C adapter hash를 확인한다. source SHA와 필수 의존성의 연결을 기록한다.
2. 기존 D24/V96을 읽어 이번 요청·평가 manifest와 protocol을 생성한다. H192/F 요청은 생성하지 않는다.
3. 실제 사용할 runner의 completion 검증, 현재 영상 재검증, GT·평가 소스 digest, 단일 소유권과 부분 행 보존을 보완한다. 과거 산출물은 수정하지 않는다.
4. 기존 생성 회귀검사를 이번 경로·상속 GPU에 맞게 적용한다. 합성 fixture로 GT/영상/config/adapter 변조, 중복·누락, ID 반전, 부분 행·동시 claim을 검사한다. 실제 작은 요청으로 중단·재개 결과 정합성을 확인한다.
5. D의 adapter·입력·병렬 검사를 수행한 뒤 고정 V96 비교를 완료한다. GPU당 worker 수는 실측으로 확정한다.
6. 환자별 원시 점수·CI·오류 분해·실제 비용을 저장하고 별도 parser/좌표/matching 구현으로 재계산한다. pg40_verify의 기존 승인 범위를 공동 출력 전체로 자동 확대하지 않는다.
7. 사전 판정과 적용 범위를 report에 기록한다. 결과가 불확정이면 원인과 보류 결정을 명시하고 추가 실험을 시작하지 않는다.

# Evaluation (성공/실패 기준 포함)

## 지표

주지표는 문장별 최대 cardinality 일대일 matching F1@IoU0.3을 환자 안에서 평균한 뒤 환자 간 평균한 값이다. C의 Δ_AB=I−J_AB, Δ_BA=I−J_BA를 두 주대조로 정한다. 환자 paired bootstrap10,000회, seed20260930, 각97.5% CI를 사용한다. B는 별도 민감도 분석이다.

F1@0.5, recall, FP/문장, 빈 예측, invalid, 최종 truncation, 독립 성공 문장의 공동 손실·반대 회복을 함께 보고한다. 누락된 qA/qB 그룹은 해당 문장의 빈 출력으로 평가한다. invalid 공동 요청은 두 문장 모두 주점수0으로 포함한다.

작은 영역, 복수 box, share-group, cross-IoU<0.1 층을 기존 정의로 보고한다. 그룹 교환 oracle의 이득은 배정 오류 설명의 상한이지 해법 성능이 아니다. 모든 조건에서 valid·EOS인 동일 환자 subset의 민감도 분석을 추가하되 주분모를 대체하지 않는다.

## 양성: 최소 방법 시험 후보

C의 두 Δ가 각각0.05 이상이며97.5% CI 하한>0, B의 두 Δ도 양수이고, 공통 valid/EOS subset에서도 두 손실이 양수여야 한다. 형식·truncation 비중과 순서 효과를 별도로 공개한다.

추가로 독립 처리의 device-seconds/J 비율≥1.25이고, p95 환자 지연/I 대 J≥1.20 또는 독립 처리량/J≤0.80이어야 정확도·비용 방법 pilot의 우선 후보가 된다. 비용 비율의 환자 또는 고정 block resampling 구간도 보고하며 경계에 걸리면 확정하지 않는다.

후속 pilot은 공동 요청 직접 CE와 독립답변 보존 개입을 비교하는 범위로 검토한다. 공동 형식 미학습이라는 설명을 통제하기 전 내부 결합 결함을 주장하지 않는다. MedGrounder 미실행 상태에서 모듈형 우위나 full 진입을 선언하지 않는다.

## 음성·실용 대안 충분

C의 두 Δ CI 상한이0.05 미만이면 중요한 공동 손실을 현재 조건에서 지지하지 못한다. 두 순서에서 손실 상한이0.02 이하면 제한된 정확도 유지의 더 강한 근거로 별도 표시한다.

공동 손실이 있어도 독립 병렬 처리의 비용 부담이 사전 기준보다 작으면 독립 처리 baseline을 보존하고 현재 공동 처리 방법 투자를 보류한다. 일반적인 문장 grounding·학습 가능성의 기각으로 확대하지 않는다.

## 불확정·종료

CI가 기준을 가로지르거나 checkpoint·순서·내용상 분석이 불일치하면 불확정이다. 비용 계측이 경계 수준이거나 안정적 비교를 제공하지 못해도 투자 근거는 미확정이다. 이번에는 추가 표본·prompt·seed로 연장하지 않는다. 기존 자산을 보존하고 다른 연구 질문을 다음 전략 판단의 우선 후보로 둔다.

실행 오류는 execution_failed 범위로 구분한다. 준비·테스트만 완료한 경우 valid_experiment=true로 보고하지 않는다. 이번 진단의 종료는 연구 목표 달성이 아니다.

# Risks / Checks

- B/C는 문장별 요청으로 학습됐으므로 공동 요청 손실은 인터페이스 전이의 관찰이다. 내부 시각 능력의 결함으로 일반화하지 않는다.
- V96은 이미 모델 선택에 쓰인 개발 자료다. 새 조건 생성만으로 독립 test가 되지 않는다.
- 정확도는 기존 출력 재사용, 비용은 실제 재계측이라는 역할 차이를 명시한다. 과거 wall과 새로운 wall을 다른 실행 조건인 채 직접 비교하지 않는다.
- 두 문장의 양성 grounding을 전체 보고서, 정상 소견, 임상 reasoning 성능으로 확대하지 않는다.
- 독립 요청의 vision/prefix caching을 측정하지 않았다면 절감 가능량은 미측정으로 남긴다. 현재 병렬 baseline을 최적화의 절대 하한으로 부르지 않는다.
- MedGrounder 미실행·사전학습 노출·단일 기관·단일 seed의 한계를 유지한다. 새로운 데이터 권한이나 package 설치를 묵시적으로 허용하지 않는다.
- test 노출 인계의 과거 결함은 test를 사용하지 않는 이번 진단의 선행 정비로 만들지 않는다. F120 및 다른 reserve를 열지 않는다.

## 대규모 GPU 필요 후보

다중 소견·보고서 공동 post-training에서 개별 질의의 근거를 보존하도록 vision encoder와 언어 모델을 함께 적응하는 후보를 남긴다. 현재 필요성은 미입증이다. 독립 처리, 공동 직접 SFT와 실행 가능한 모듈형 baseline 이후에도 중요한 잔여 문제가 재현될 때 대규모 학습을 검토한다.

# 계획의 근거 (GPT 조사 노트)

## 새로 확인한 사실

- `agent/GOAL.md`, `agent/GPT_USAGE_POLICY.md`, `agent/INDEX.md`, `agent/LIMITATIONS.md`의 관련 항목, `agent/CODE_ASSETS.md`, iter_039·040의 plan/review와 review.json/code_assets를 확인했다. RSNA 방향의 기회비용 판단에는 iter_037 review 원문을 사용했다.
- iter_040의 유효한 결과는 B/C/C_compute/M F1@0.3=0.555903/0.577951/0.564931/0.572743이다. M−C=-0.005208이며 baseline 상승 때문에 리뷰 판정은 inconclusive다. 보고서·summary의 negative를 후속 판정 근거로 복사하지 않는다.
- B와 C adapter의 실제 파일 SHA256이 각 protocol과 일치했다. 경로는 `results/iter_040/train2/B_lr1e-4_s17/epoch_05`와 `results/iter_040/train2/C_s17/epoch_03`이다.
- `results/iter_040/gen/C/completion.json`은 독립 192요청을 4 worker로 376.64초에 완료했음을 기록한다. `tests/gen_throughput.json`의 24요청 비교는 2→4 worker에서 135.56→75.31초, token 일치, 최대 GPU 점유 17,836MiB다. 공동 요청은 길이가 달라 안전성과 처리량을 다시 확인해야 한다.
- [MedGrounder 공식 저장소](https://github.com/aehrc/MedGrounder)는 Chest ImaGenome 사전학습 checkpoint와 PadChest 적응 checkpoint를 구분한다. [공식 추론 notebook](https://raw.githubusercontent.com/aehrc/MedGrounder/main/inference.ipynb)은 OmegaConf·torchvision·ensemble_boxes 등을 사용한다. 지난 feasibility.json의 누락을 현재 기본 medgemma 환경의 module 탐색으로 재확인했다. 기존 detector용 natten_py310에도 albumentations·ensemble_boxes·opt_einsum·nltk가 없다. 설치·환경 혼합 없이 바로 실행 가능한 공식 경로를 확보하지 못했다. 모듈 존재 확인은 실제 import·모델 실행 검증과 다르다.
- 첫 shell 조회에서는 login shell이 Python 경로를 바꿨다. login=false에서는 상속된 `/home/test/.conda/envs/medgemma/bin/python`을 확인했다. Claude는 실행 시작 시 sys.executable을 기록하고 상속 PATH를 보존해야 한다.
- [Generalised Medical Phrase Grounding](https://arxiv.org/html/2512.01085v1)은 문장별 0개·1개·복수 영역과 모듈형 보고서 grounding을 다룬다. 따라서 문장 분리·복수 box·모듈 결합 자체는 새로운 기여가 아니다.

## 선택과 한계

현재 문장 대조 loss 확대는 새 근거가 약하다. MedGrounder 비교는 현 환경에서 바로 성립하지 않는다. 반면 적응 후 공동 요청은 새 checkpoint 때문에 과거와 다른 식별력을 가지며, 기존 출력 재사용으로 적은 추가 생성만 필요하다. 이 한정 비교를 선택하되, 공동 형식 미학습이라는 경쟁 설명을 유지한다. V96은 개발 자료이고 이번 결과를 독립 재현이나 전체 의료 VLM 결함으로 표현하지 않는다.

## 원본과 재사용

iter_039 plan SHA256은 `bff448aa81ae912fb1b2591e60dc07f6080591b8fbe6286c09c2913a351c4260`, iter_040 plan은 `1e37d04e0c26b5fabcc6803bdfd41fd7c71cc2829a75a81e0c756ba3592bfc21`이다. 이번은 두 계획의 미완료 확대를 실행하는 amendment가 아니라 모델 조건과 투자 기준을 명시한 새 진단이다. 기존 sentence-evidence-binding 브랜치 HEAD는 `ca8be7658402eadbc0c501e877d76b1024ed2683`이며 필요한 추가 다섯 파일의 출처·충돌 부재를 확인했다. 파일 수정·생성·모델 실험은 수행하지 않았다.
