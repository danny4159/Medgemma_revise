# 요약

- **이번에 할 일:** 자동 분석의 새 병변 판정을 이전·현재 MRI로 다시 검토할 가치가 있는지 선별한다.
- **필요한 이유:** SPIDER 단일 판독과 참고영상에서는 강한 단순 대안 이후의 VLM 추가 가치를 확보하지 못했다. 실제 두 검사를 비교하는 조건으로 질문을 좁힌다.
- **확인할 기준:** 원 정답·비교 검사 연결, 자동 규칙 이후의 오류, 영상에 의한 교정과 맞는 판정의 보존이다.
- **주의·다음:** LUMIERE 원 CSV와 영상은 아직 직접 확인하지 못했다. 자료 점검 통과 시에만 실제 출력으로 진행하며, 이번은 방법 개발이나 신규 기여 입증이 아니다.

## 알림 맥락

- 연구: MRI 근거 선택·사용
- 데이터: 척추 SPIDER → longitudinal 뇌종양 MRI LUMIERE 후보
- 모델: MedGemma 1.5와 기존 Qwen2.5-VL-7B, 신규 학습 없음
- 과제: 이전·현재 MRI와 자동 판정을 받아 새 병변 유무에 답한다
- 가설: 영상 재검토가 실제 자동 판정 오류를 교정하면서 맞는 판정도 보존할 수 있다
- 질문: 자동 분석이 새 병변이라고 판단했을 때 모델은 MRI를 확인하는가, 그 판정을 따라가는가?
- 변경: 방향 전환
- 연결: SPIDER 참고영상의 추가 가치가 미확보되어, 같은 근거 사용 질문을 실제 검사 간 변화와 자동 도구 검증으로 좁힌다
- 작업: 명시적 정답과 검사쌍을 확인한 뒤 자동 규칙·영상만·자동 판정만·둘을 함께 제공한 답변을 비교해 투자 여부를 정한다

# Current Understanding

iter_078의 유효한 불확정 결과와 현재 참고영상 투자 보류를 유지한다. iter_077의 F/R 입력 차이와 iter_064의 모델 특이 context 손실도 관찰로 보존한다. 세 결과를 같은 내부 원인으로 합치지 않는다.

이번 후보는 새 병변 유무라는 검사 간 관계다. 다른 환자의 참고 사례를 추가하는 이전 과제와 다르다. 다만 두 검사가 있다는 사실만으로 결합 능력 평가가 성립하지 않는다. 전문의 정답이 실제 어떤 이전 검사와 비교한 것인지 확인해야 한다.

**유지:** 최종 GOAL, MRI 우선, 두 GPU 활용, 기존 결과·checkpoint·reserve와 원 판정.

**보류:** SPIDER 추가 epoch·seed·참고 수·검색기·prompt 탐색, OAI 확보, MR-RATE 접근 대기.

**변경:** 신규 판독기를 만드는 문제보다 자동 도구의 근거를 영상으로 검증할 실제 가치가 있는지 먼저 본다. 결과는 `research/results/iter_079/`에만 저장한다.

# Strategy Check / 연구 방향 판단

**상위 질문 → 관찰:** 질문에 필요한 관측을 사용하는가라는 질문은 유지한다. 기존 실험은 적응 후 영상 대응 신호를 확인했지만, 충분한 인식 이후의 선택·결합 실패와 방법 필요성을 확정하지 못했다.

**남은 설명:** 자동 도구가 이미 충분할 수 있다. 오류가 있어도 mask 정합·작은 component 제거로 해결될 수 있다. VLM의 변경은 영상 교정이 아니라 자동 판정 복사나 답변 prior일 수 있다.

**최소 비교:** 자동 규칙 M, MRI-only J, tool-only T, MRI+tool A, 단순 confidence gate G다. 같은 사례에서 두 모델 계열을 비교한다.

**바뀔 결정 하나:** 자동 도구의 출력을 영상으로 검증하는 적응 연구에 투자할 가치가 있는가?

현재 SPIDER 방법 개선은 정확도 불확실성을 줄일 수 있어도 추가 가치 문제를 해결하지 못한다. 기존 context 진단은 명시적 routing으로 피할 수 있는 조건이다. 새 후보는 실제 자동 도구의 오류라는 사용 조건과 가까운 기존 해법을 함께 비교할 수 있어 우선한다. 단, 정답 의미가 성립하지 않으면 준비를 연장하지 않는다.

[Time-Aware Multi-View MRI](https://arxiv.org/html/2608.13309v1)는 이미 longitudinal MRI 평가를 다룬다. [Med-StepBench](https://arxiv.org/abs/2605.10002)는 중간 설명에 의한 판단 오류를 다룬다. 따라서 시간 비교·근거 검증이라는 이름은 신규성이 아니다. 이번 진단의 가치는 실제 자동 오류와 강한 단순 대안 이후의 잔여 문제를 구분하는 데 있다.

이전에는 자료 연결·실행 복구 비용이 컸다. 이번에는 metadata 의미 확인 전에 새 학습기나 범용 benchmark를 만들지 않는다. 누적 비용 비율은 측정되지 않았으므로 절감률을 주장하지 않는다.

# Hypothesis

- **H1 — 영상 교정 가능:** J 또는 A가 자동 규칙의 실제 오류를 교정하며, 영상 없는 T보다 좋다.
- **H2 — 단순 대안 충분:** mask 후처리나 G가 필요한 교정과 보존을 달성한다. 새로운 VLM 방법 투자는 불필요하다.
- **H3 — 도구 의존의 잔여 문제:** J와 M에는 상보성이 있지만 A가 틀린 도구 판정을 따르고 G도 이를 충분히 구분하지 못한다. 제한적인 근거 선택 적응 후보가 된다.
- **H4 — 기본 적합성 또는 자료 부족:** 정답 연결이 안 되거나 현재 영상 입력에서 교정 신호가 없다. 현재 후보를 보류하며 MRI 일반 능력의 반증으로 사용하지 않는다.

# Limitation Evidence / Correct Usage Checks

이번 새 병변 과제에 대한 observed limitation은 아직 없다. `limitation_ids=[]`, diagnostic/none으로 진행한다. 기존 두 MRI limitation은 전략의 배경이며 새 과제의 방법 gate 근거가 아니다.

[LUMIERE 공식 expert CSV](https://springernature.figshare.com/articles/dataset/LUMIERE_dataset_-_Expert_RANO_rating/21195556)는 전문의 판정과 근거를 제공한다고 명시한다. 그러나 명시적 새 병변 음성, 비교 검사 식별자, 사용 가능한 적격 수는 아직 미확인이다. 다음 자료 gate를 구현에서 먼저 수행한다.

1. 원 readme와 CSV의 실제 column·code·결측 의미를 확인한다. 원문 인용 위치와 원 행을 보존한다.
2. 질문은 **명시된 이전 검사 대비 새로 나타난 조영증강 병변 유무**로 고정한다. 양성·음성은 명시적 전문가 항목 또는 의미가 명확한 원 판정 근거에서만 얻는다.
3. PD를 새 병변 양성으로, SD를 음성으로 자동 변환하지 않는다. 미언급·결측·자동 mask flag도 음성 정답이 아니다.
4. 비교 검사를 단순히 직전 방문이라고 가정하지 않는다. 공식 설명이나 해당 원 행으로 기준 검사를 특정할 수 있어야 한다. 미래 검사 정보를 입력에 넣지 않는다.
5. scan-level 정답을 개별 자동 component의 정답으로 복제하지 않는다. 평가 단위는 검사쌍이며, 자동 mask는 예측 근거다.
6. literal한 정답 연결을 확인할 수 없으면 임상 추론으로 보충하지 않고 자료 부적합으로 종료한다. 대규모 재주석이나 다른 RANO 과제로의 임의 전환은 하지 않는다.

이 gate는 모델 정답률 gate가 아니다. 정상 입력에서 모델이 틀리는 것은 관찰로 남기며 100% oracle 정답을 요구하지 않는다.

# Contribution Path / Baselines / Reuse

## 가까운 해법과 주장 범위

[TRACE Appendix A.4](https://arxiv.org/html/2606.30313v1)는 시간 간 segmentation component 대응으로 새 병변 신호를 계산한다. 이번에는 그 신호를 독립 정답으로 취급하지 않고 전문의 근거와 비교한다. TRACE 전체 모델의 재현이나 RANO 분류 점수 경쟁은 이번 범위가 아니다.

후속 기여 후보는 실제 도구 오류에서 시각적 근거를 선택적으로 다시 확인하는 학습 원리다. 현재 필요성도 효과도 미확인이다. 기존 A/G가 충분하면 새로운 방법 없이 종료한다. 후속 pilot을 택하더라도 직접 SFT·단순 학습 gate·도구 후처리와 비교해야 한다.

## 비교군

- **M0:** 배포된 자동 mask의 조영증강 label에서, follow-up component가 정합된 reference mask와 겹치지 않으면 새 병변으로 판정하는 규칙.
- **M:** 두 배포 segmentation 출처 각각에 대해 최소 component volume `{0, 0.1, 0.5} cm³`, reference mask dilation `{0, 2, 5} mm`를 비교한다. 총 18개 사전 고정 후보이며 D에서만 선택한다. 이는 임상 RANO 기준이 아니라 작은 artifact와 정합 오차에 대한 민감도 대조다. D BA 최대, specificity 최대, 낮은 변경 복잡도, 고정 출처명 순으로 동률을 처리한다.
- **J:** 영상만 보고 새 병변 유무 답변.
- **T:** M의 자동 판정과 동일한 검사 역할 정보만 받고 답변. 전문의 근거는 제공하지 않는다.
- **A:** J와 동일한 영상 및 T와 동일한 자동 판정을 함께 받고 답변.
- **G:** J가 유효하고 그 답변의 A/B 조건부 confidence가 threshold 이상이면 J, 아니면 M을 사용한다. threshold는 `{0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 1.01}`이며 항상 M·항상 J endpoint도 포함한다. D BA 최대, specificity 최대, M 보존 우선으로 고정한다.

J confidence는 공식 forward의 A/B 후보 likelihood로 계산한다. 후보가 한 token인지 확인하고, 여러 token이면 두 canonical 답변의 전체 조건부 likelihood를 계산한다. 이 점수를 실제 생성 정답률과 혼동하지 않는다. G는 실제 J 생성이 invalid이면 M으로 돌아간다.

최종 실용 기준선 B는 M/J/G 중 D에서 같은 규칙으로 선택한다. E에서 선택하지 않으며 개별 비교 결과도 모두 남긴다. 두 모델은 모델별 G/B를 고정한다.

## 재사용

JSON reuse_assets의 세 파일은 SHA와 실제 함수를 확인했다. 모델 로딩·공식 processor 연결·vision chunk 함수만 사용한다. 과거 MSD/SPIDER용 CLI·protocol·평가기·자료 선택을 호출하지 않는다.

iter_067의 알려진 결함은 patch 전후의 독립 대조 부족, 동시 재개·출력 봉인·설정 연결 부족이다. 이번 경로에서만 해결한다. 현재 rf78의 SPIDER 전용 생성기와 launcher 전체를 반입하거나 그 평가 결함을 무관하게 수정하지 않는다.

모델은 MedGemma revision `91850547d9f0b2fdd21aa7c5f4f3d1a8a52c243b`, Qwen revision `cc594898137f460bfe9f0759e9844b3ce807cfb5`를 사용한다. 기존 cache는 읽기 전용으로 재사용한다. 필요한 추가 패키지는 전용 격리 환경에 구성한다.

# Proposed Experiment

## 1. 한정 자료 확인

공식 collection의 readme, expert CSV, completeness, MRI/segmentation 파일 목록만 먼저 확보한다. [저자 저장소](https://github.com/ysuter/gbm-data-longitudinal)와 항목별 라이선스·버전을 함께 기록한다. CSV의 literal 정답 연결을 점검한 뒤 두 검사쌍의 실제 NIfTI·mask·affine·sequence를 확인한다.

대량 영상 확보 전에 파일 목록에서 필요한 환자·방문만 선택한다. ZIP의 공식 HTTP Range와 central directory 접근이 지원되면 필요한 member만 받으며 Content-Range·CRC·원 checksum을 검사한다. 부분 응답 요청에 전체 archive가 반환되면 그대로 소비하지 않는다. 선택 확보가 불가능하고 전체 archive가 필요하면 실제 용량·전송 추정·디스크 여유를 기록하고 이번 한정 점검에서 중단한다. OAI와 같은 자료 확보 대기를 자동 재개하지 않는다.

확인하지 못한 접근 조건을 자료 부재로 쓰지 않는다. 실제 계정 동의가 필요한 경우에만 그 항목을 분리해 보고한다.

## 2. 표본과 노출 관리

적격 기준은 명시적 양성/음성, 특정된 비교 검사, 두 검사 모두 필요한 네 sequence와 대응 자동 mask가 존재하는 경우다. 환자별로 가장 이른 적격 검사쌍 하나를 택해 중복을 막는다. 그 뒤 seed7901로 class별 환자 순서를 고정한다.

D는 각 class 최대 3명, E는 남은 각 class 최대 16명이다. 총 최대 38명이다. 이 규모는 약 10 pp 개선이 수 건의 순교정으로 드러나는 큰 효과 탐색을 위한 것이며, 정밀한 확증 표본이 아니다. 부족하면 남은 적격 환자만 사용하고 불균형·정밀도 한계를 보고한다. 한 class 자체가 없으면 교정과 보존의 비교가 성립하지 않으므로 본 비교를 종료한다.

E는 이번 설정 선택에 사용하지 않는 탐색 집단이다. 사전학습 노출이 미확인이고 작은 표본이므로 독립 일반화 입증으로 부르지 않는다. 나머지 환자의 영상과 정답은 후속 실행에 자동 사용하지 않는다. 기존 프로젝트 reserve도 열지 않는다.

## 3. 입력 구성

두 검사의 T1 pre-contrast, T1 post-contrast, T2, FLAIR를 사용한다. 정답이나 자동 병변 위치로 slice를 고르지 않는다.

- reference T1 post-contrast를 기준으로 필요한 rigid 정합을 수행한다. 이미 정합된 파일이면 공식 transform과 affine을 확인해 중복 변환을 피한다.
- 변형 정합으로 병변 변화를 지우지 않는다. mask에는 nearest-neighbor, 영상에는 고정된 연속 보간을 사용한다.
- 공통 물리좌표의 brain 범위에서 sequence당 20개 axial plane을 등간격 선택한다. 검사당 80장, 검사쌍당 160장이다. 각 영상의 물리 z, 역할, sequence, source hash를 보존한다.
- volume별 min-max·동일 RGB 채널과 고정된 256×256 aspect-preserving canvas를 사용한다. 모델별 공식 processor의 추가 resize와 token 수를 기록한다.
- reference의 네 sequence, current의 네 sequence 순으로 고정한다. 생성 prompt에 각 block의 영상 index 범위와 실제 역할을 명시한다.

이는 전체 volume을 대체하는 확정된 임상 입력이 아니다. 등간격 표집으로 작은 병변이 빠질 수 있다. 낮은 점수를 충분한 인식 이후의 결합 실패로 해석하지 않는다. 반대로 scan-level 정답을 crop에 무리하게 붙이는 설계도 사용하지 않는다.

정합은 결과를 보기 전에 affine·방향·brain coverage와 대표 overlay로 검사한다. 기술적으로 잘못된 정합은 모델 오류와 분리한다. 정답에 따라 정합·slice를 바꾸거나 유리한 사례로 교체하지 않는다.

## 4. 동작 확인과 D 실제 출력

자료 gate를 통과한 뒤에만 새 worker·평가 경로를 연결한다. 먼저 D의 두 검사쌍으로 공식 입력 대조, patch 전후 대조, 전체 160영상의 메모리와 생성 완료를 검사한다.

bf16·batch1·greedy를 사용한다. 답변은 `A` 또는 `B` 한 글자로 요청한다. 512 new tokens에서 비EOS이면 같은 요청을 2048 cap으로 한 번 재실행하고 두 attempt를 보존한다. 최종 whole-string A/B와 선택적 마침표만 valid로 인정한다. 정답률 때문에 parser를 바꾸지 않는다.

D 최대 6명에서 두 모델의 J/T/A 최대 36건을 생성하고 J confidence를 계산한다. M/G/B 선택과 prompt·parser·전처리·실행 설정을 잠근다. 어느 모델의 영상 조건에서도 유효 응답이 전혀 없으면 그 모델의 현재 인터페이스 부적합으로 중단한다. 작은 D 정확도나 CI를 확증 gate로 사용하지 않는다.

## 5. 조건부 E 탐색

정답·입력·실행이 유효하면 E 최대 32명에서 모델별 J/T/A를 한 번씩 실행한다. 최대 192건이다. 두 모델을 모두 동일한 E에 적용하며 MedGemma 오답 사례만 Qwen에 전달하지 않는다.

모델 하나가 고정 입력을 가용 메모리 안에서 처리하지 못하면 원인과 실제 peak를 남긴다. 같은 정보를 유지하는 chunk·batch 조정만 허용한다. 입력 영상 수를 몰래 줄이지 않는다. 다른 모델의 유효 비교는 보존하되 타 계열 재현을 완료했다고 하지 않는다.

추가 학습·세 번째 모델·E 사후 prompt 조정·추가 seed는 이번 범위에 없다.

## 6. 자원·예상 비용·재개

처음에는 두 GPU에 모델별 worker를 배정하되 시작 직전 여유가 큰 허용 GPU부터 선택한다. Qwen의 기존 가중치는 약 15 GB 수준이고 긴 입력의 KV/activation이 추가된다. MedGemma도 기존 짧은 요청의 8–10 GB를 이번 peak로 간주하지 않는다. 두 모델 모두 실제 peak+worker당 2 GiB 여유로 admission한다.

D의 같은 고정 workload에서 batch 확대 또는 동일 GPU 두 worker 중 메모리상 유망한 구성을 하나만 비교한다. 합산 peak 때문에 둘 다 admission되지 않으면 그 수치로 한 worker 유지 이유를 기록한다. 처리량 비교를 하지 못한 경우 속도 우위를 주장하지 않는다. 전체 workload wall-clock, GPU별 peak, 긴 요청 지연, 오류·I/O 경합과 결과 정합성을 비교한다.

현재 160영상 경로의 시간은 미측정이다. 계획용 가정으로 영상 요청당 30–180초라면 모델당 영상 요청 최대 76건은 약 0.6–3.8시간이며, loading·text 요청·scoring·등록 비용은 별도다. 이는 예측 보장이 아니다. D 실측으로 `N_image×t_image + N_text×t_text + N_score×t_score`를 계산해 E 시작 전 갱신한다. 시간만으로 재승인을 요구하거나 임의 timeout을 두지 않는다.

request ID에 모델·입력·prompt·설정 hash를 포함한다. worker별 파일, 원자적 claim, fsync 이후 완료, 종료 코드와 전체 ID 집합을 확인한다. 기존 claim을 지우지 않는다. 재개는 동일 protocol의 완료 요청만 건너뛰며 변경된 설정은 새 경로를 쓴다.

# Implementation Tasks for Claude

1. 원 자료의 의미·접근·소수 실제 영상 연결부터 확인하고 실행 가능 여부를 명확히 기록한다. 실패하면 나머지 파이프라인을 만들지 않는다.
2. 환자·비교 검사·정답 원문 연결표와 D/E manifest를 고정한다. 모델 요청에서는 전문의 정답과 rationale을 분리한다.
3. 물리좌표 기반 정합·고정 slice 렌더와 두 출처의 자동 mask 규칙을 구현한다. 단위는 mm·cm³로 검사한다.
4. 세 backend 파일의 필요한 함수만 연결하고 공식 unpatched 경로 대조를 수행한다. 과거 데이터 전용 CLI는 호출하지 않는다.
5. J/T/A 생성, confidence 계산, M/G/B 선택, protocol 잠금과 재개를 구현한다. 새 입력 연결과 변조 거부를 검증한다.
6. D와 조건부 E를 실제 완료한 뒤 원시 출력에서 별도 계산으로 metric·교정/손상 사건을 대조한다. production 평가기를 다시 호출한 것을 독립 검증으로 부르지 않는다.
7. 자료 부적합·기술 실패·유효한 음성·불확정을 구분해 보고한다. 전체 snapshot을 승인하지 말고 실제 검증한 재사용 범위를 적는다.

# Evaluation (성공/실패 기준 포함)

## 지표

primary는 scan-pair balanced accuracy다. sensitivity, specificity, invalid 비율과 confusion counts를 함께 보고한다. invalid는 해당 class의 오답으로 계산한다. abstention이나 형식 실패를 정상 음성으로 바꾸지 않는다.

주요 paired 차이는 A−B, A−T, A−J, J−M이다. 환자 단위 stratified paired bootstrap 10,000회·seed7901의 95% CI를 보고한다. 표본이 작으면 사건 수와 불확실성을 우선 설명한다.

M이 틀린 경우의 교정 수, M이 맞았는데 바뀐 손상 수, J와 M 중 하나만 맞는 상보 사례를 사전 정의해 집계한다. 두 예측 중 정답을 고르는 oracle routing의 점수는 기회 상한일 뿐 실용 baseline이 아니다.

## 결과별 결정

**기존 해법의 양성:** A 또는 G가 B의 다른 구성보다 BA 0.10 이상 개선하고, M의 오류를 최소 3건 교정하면서 새 손상을 1건 이하로 유지하면 시각적 재검토의 탐색 신호로 보존한다. A의 경우 A−T도 0.10 이상이어야 영상 없는 설명만으로 충분하다는 해석을 약화할 수 있다. 기존 구성으로 충분하면 신규 방법 투자는 하지 않는다.

**최소 방법 pilot 검토 후보:** M/J 각각만 맞는 사례가 최소 3건씩 있고, oracle routing−고정 B가 BA 0.15 이상이며, A/G가 그 기회를 회수하지 못한 경우다. 이때 실제 영상 교정 사례와 자연적인 도구 오류가 확인되어야 한다. 이는 후속 소규모 적응의 정보 가치 기준이지 새로운 내부 원인이나 방법 필요성의 증명이 아니다. 다음 리뷰에서 단순 학습 gate·직접 SFT 대비 가치와 비용을 판단한다.

**단순 대안 충분:** M 또는 G가 BA 0.90 이상이고 sensitivity·specificity가 각각 0.85 이상이며 VLM의 추가 교정이 위 기준에 미달하면 현재 탐색 범위의 새 방법 투자를 종료한다. 작은 표본의 대안 충분성을 임상 배포 인증으로 쓰지 않는다.

**음성:** 유효한 입력에서도 J/A가 영상 없는 T나 M 이후의 교정 신호를 제공하지 못하면 현재 frozen 후보를 보류한다. 출력·관측 부족과 기본 인식의 원인은 미분리로 남기며 새 loss를 발주하지 않는다.

**불확정:** 위 분기 어디에도 충분히 연결되지 않으면 고정 E에서 종료한다. 효과 부호만 보고 환자·prompt·규칙을 추가하지 않는다. CI가 0을 포함한다는 이유만으로 실제 관찰을 지우지도 않는다.

이 문턱은 탐색의 투자 선별 기준이다. 유의성 문턱을 모든 실행의 선행 조건으로 요구하지 않는다. 모델별로 판정하며 한 계열만의 현상을 공통 VLM 한계로 확대하지 않는다.

## 비용과 확대 경계

자동 mask가 이미 있는 상황의 추가 판정·재검토 latency와 GPU-seconds를 비교한다. 과거 segmentation 생성 비용은 미측정으로 표시한다. 정확도 개선과 추가 비용을 함께 보고하며 비용 우위나 임상적 비용 효과를 미리 주장하지 않는다.

이번에는 학습 규모 확대와 독립 확인을 실행하지 않는다. 후속 최소 방법 pilot은 유효 리뷰와 중요한 잔여 문제가 있어야 별도 계획한다. full 개발은 validated 근거와 독립 평가 설계가 필요하다.

# Risks / Checks

- 가장 큰 위험은 expert RANO 근거가 이번 새 병변 질문의 명시적 양성·음성 및 비교 검사 연결을 제공하지 않는 경우다. 이때 CPU 자료 확인에서 종료하며 모델 능력을 판정하지 않는다.
- 자동 segmentation의 오류를 GT로 삼지 않는다. 서로 다른 두 도구의 합의도 전문의 정답을 대신하지 않는다.
- 부분 slice 입력의 누락, 정합 오차, 수술 후 변화가 결과에 영향을 줄 수 있다. 충분한 인식 이후의 순수 결합 실패라고 부르지 않는다.
- 원 정답표를 보고 규칙을 확정하는 D와 E를 분리한다. E에서 유리한 segmentation 출처·threshold·모델을 골라 primary를 교체하지 않는다.
- 공개 자료와 모델의 사전학습 중복은 미확인이다. source cohort·기간·모델 공개 학습 설명을 기록하고 독립 일반화 주장을 제한한다.
- 기존 승인 cache·환경과 다른 사용자 프로세스를 변경하지 않는다. 필요한 구성은 결과 하위 격리 환경에 한정한다.
- 출력·label·provenance·실제 자식 종료와 비용 저장 경계를 확인한다. 코드 테스트 통과를 유효한 모델 실험으로 보고하지 않는다.

## 대규모 GPU 필요 후보

longitudinal volume encoder와 언어 모델을 공동 학습해 실제 자동 도구 오류의 검증·보존을 학습하는 방향은 장기 후보로 보존한다. 현재 필요성과 신규성은 미확인이다. 두 RTX 3090에서 가능한 직접 SFT·경량 gate·LoRA 및 기존 도구 후처리 이후에도 가치가 남을 때만 검토한다.

# 계획의 근거 (GPT 조사 노트)

## 확인한 사실과 판단

- `agent/GOAL.md`, iter_077/078 원 리뷰, iter_078 계획, 관련 LIMITATIONS/CODE_ASSETS 및 iter_064 원 리뷰를 확인했다. iter_078에서 I−M MAE는 +0.05000, 95% CI [-0.07301, 0.15569]였다. 현재 참고영상 후보의 추가 학습을 지지하지 않는다.
- iter_077의 F−R 0.29357과 iter_064의 MedGemma context 손실은 유지한다. 각각 별도 적응·입력 차이와 기본 인식 문제를 포함하므로 새 병변 검증의 한계 증거로 옮기지 않는다.
- iter_022와 iter_055 계획 노트를 읽었다. 시간순 정렬만으로 보장되는 일관성을 방법 효과로 삼지 않으며, 원 정답 code나 미언급을 임의의 음성 정답으로 바꾸지 않는다.

## 새 후보의 근거

[LUMIERE 원 논문](https://pmc.ncbi.nlm.nih.gov/articles/PMC9755255/)은 longitudinal MRI, 전문의 RANO 판정 근거와 자동 segmentation을 제공한다. 자동 mask는 수동 병변 정답이 아니다. [공식 expert CSV 페이지](https://springernature.figshare.com/articles/dataset/LUMIERE_dataset_-_Expert_RANO_rating/21195556)는 30.4 kB 파일과 병변 측정·판정 근거의 포함을 명시한다. 새 병변의 명시적 양성·음성 및 비교 검사 필드는 아직 직접 확인하지 못했다.

[공식 collection](https://springernature.figshare.com/collections/The_LUMIERE_Dataset_Longitudinal_Glioblastoma_MRI_with_Expert_RANO_Evaluation/5904905/1)의 readme·completeness·MRI/segmentation 항목을 확인했다. [저자 저장소](https://github.com/ysuter/gbm-data-longitudinal)는 비상업적 사용을 안내하지만 일부 Figshare 항목은 CC0로 표시된다. 구현에서 항목별 원 라이선스를 보존하고 이번 학술 연구 범위에 맞춰 확인한다.

이번 read-only 환경의 urllib은 DNS 오류였고, web 도구의 CSV 다운로드는 403 또는 fetch 실패였다. 실제 영상 archive와 CSV는 읽지 못했다. 이는 연구 서버에서 자료 이용이 불가능하거나 추가 계정 승인이 필요하다는 증거가 아니다. 같은 웹 조회를 반복하는 대신 승인된 구현 단계에서 공식 경로의 한정 점검과 통과 시 실제 출력을 묶는다.

## 가까운 선행과 차별성의 한계

[Time-Aware Multi-View MRI](https://arxiv.org/html/2608.13309v1)는 이미 longitudinal MRI의 변화 판단을 평가한다. [공식 저장소](https://github.com/wafaAlghallabi/Time-Aware-MRI)는 Hugging Face 배포를 coming soon으로 표시해, 해당 benchmark를 확보했다고 가정하지 않는다.

[TRACE §3.4.5와 Appendix A.4](https://arxiv.org/html/2606.30313v1)는 mask connected component의 시간 간 대응으로 새 병변 flag를 계산해 입력한다. 이 flag 자체를 전문의 새 병변 정답으로 사용할 수 없다. [공식 실행 안내](https://raw.githubusercontent.com/yusufafify/TRACE-Temporal-Causal-Reasoning-with-Acyclic-Concept-Explanation/main/trace-bottleneck/submission/README_SUBMISSION.md)는 외부 LUMIERE 경로를 요구한다. 이번에는 TRACE 전체 재학습보다 해당 도구 입력의 정확성과 시각적 교정 가능성을 먼저 검사한다.

[Med-StepBench](https://arxiv.org/abs/2605.10002)는 중간 설명에 의해 영상 판단이 흔들리는 현상을 이미 다룬다. 따라서 오답 설명의 영향이나 영상 검증이라는 이름 자체는 신규성이 아니다. 실제 자동 도구 오류에서 단순 후처리·confidence gate 이후의 선택 문제가 남는지가 이번 결정 대상이다.

## 자산 확인

현재 research HEAD는 `b5426526827d986e9962f5439d5191bfbd064634`이며 status와 diff는 깨끗했다. 현재 파일 목록과 rf78 생성·launcher 구현, iter_067/064/078의 code_assets를 확인했다. 새 접근법에는 세 backend 파일만 선별 반입한다. 해당 원본 SHA256은 sp67_run.py=`5b60404677e3982591e9152ecc5cad496578753569406d787b8b4ee01b3a4100`, m65_run.py=`29e3e6fc7d57b598c1f14924392416568e39bf61eb0eb575d3d3e4663126bac6`, msd56_run.py=`84f59921cc11f5af5db46ce1204c48e9cb351fddeeba3c67ed539e0a95755bf9`다. 전체 snapshot 승인은 아니다.

기존 Qwen fetch 기록에서 revision `cc594898137f460bfe9f0759e9844b3ce807cfb5`와 격리 cache 경로를 확인했다. [공식 Qwen 입력 안내](https://huggingface.co/Qwen/Qwen2.5-VL-7B-Instruct)와 [MedGemma 기술 보고서](https://arxiv.org/html/2604.05081v1)를 대조했다. 새 긴 입력의 메모리·정합성은 미측정이다.

파일 수정·생성, 모델 로딩, 실험은 수행하지 않았다. 논문 추천은 아직 하지 않는다.
