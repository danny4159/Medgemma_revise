# 사고 라운드 1

## 새로 확인한 것

부분 evidence의 질문 범위 진단을 잠정 1순위로 두지만, 아직 구현할 실험은 확정하지 않는다. 원시 출력에서 새로운 구분점을 얻었고, 선행 연구와 데이터 접근 조건이 설계를 바꾼다. 다음 라운드는 이 후보를 실제로 검증할 최소 대조와 정답 자료를 결정하는 데 사용한다.

이번에는 문서·코드·기존 결과를 읽고 저장 출력을 재집계했다. 파일 변경, 모델 로딩, 새 실험은 수행하지 않았다.

### 1. 기존 결과의 의미를 좁히는 재집계

`agent/GOAL.md`, `agent/LIMITATIONS.md`, `agent/CODE_ASSETS.md`, iter_017 원본 계획·리뷰, iter_015 조사 기록, legacy 중대 정정을 확인했다. iter_009의 정상 사용 조건 grounding 한계와 iter_012 직접 SFT 개선은 유지한다. iter_014의 GIoU 설계와 iter_017의 좌표 추가 효과에 대한 투자 중단도 유지한다. iter_008 사용자 보완의 일회성 사용법 검증을 다시 시작하지 않는다.

iter_017 리뷰의 E600 결과는 U/B/K/L S_scope=0.5533/0.6067/0.6217/0.6217, direct M0=0.6100이다. U 자체가 direct보다 낮으므로 B−U 개선만으로 실용 시스템 개선을 주장할 수 없다.

이번에는 다음 원시 파일을 읽고 질문별 답변과 전이를 별도로 집계했다.

- `research/results/iter_016/gen/{e180_plain,e600x_plain}__M0/gen_worker*.jsonl`
- `research/results/iter_017/gen/{p180_ev17,e600x_ev17}__M0/gen_worker*.jsonl`
- 정답 연결: `research/results/iter_015/manifests/labels.json`

NoOpacity/NotNormal 200명에서 확인한 정답 수는 다음과 같다. Q_O의 정답은 no, Q_A의 정답은 yes다.

| 조건 | Q_O 정답 | Q_A 정답 | 두 질문 모두 정답 |
| --- | ---: | ---: | ---: |
| direct M0 | 127/200 | 107/200 | 40/200 |
| U | 71/200 | 58/200 | 1/200 |
| B | 98/200 | 94/200 | 4/200 |
| K | 98/200 | 98/200 | 4/200 |

Q_A에서 direct의 정답 107개 중 U가 오답으로 바꾼 것은 49개다. B와 K에서는 각각 18개다. 따라서 넓은 질문의 손실을 검출값의 과도한 신뢰 하나로 설명할 수 없다. 정보 없는 안내문·packet도 큰 영향을 주고, 검출값은 그 일부를 회복시킨다.

답변 쌍도 분리해야 한다. 같은 200명에서 U의 `(Q_O=yes,Q_A=no)`는 72명, B는 12명, K는 8명이다. 반면 정답 쌍 `(no,yes)`는 U 1명, B/K 각 4명이다. 질문은 독립 대화로 실행됐으므로 이를 대화 중 자기모순이라고 부르지 않는다. 질문별 정확도, 판독 규약상 양립할 수 없는 답변 쌍, 실제 정답 쌍을 함께 보고해야 한다. 정답 쌍 저하만을 전반적인 의미 능력 상실로 해석하면 안 된다.

이 재집계는 기존 개발 자료의 탐색 분석이다. 새 독립 근거나 한계의 validated 승격이 아니다.

### 2. 기존 prompt에 이미 있는 통제

`rsna_diag/qa_spec.py`의 Q_A는 abnormal이 pneumonia opacity를 반드시 포함하지 않는다고 명시한다. `ev17_spec.py`의 공통 문구도 localizer가 pulmonary opacity만 다룬다고 설명한다. 따라서 다음 진단을 단순히 '범위 설명을 처음 추가한다'고 설계하면 사실과 다르다.

다만 iter_016의 빈 예측 문구에는 빈 proposal이 Normal을 뜻하지 않는다는 직접 설명이 있고, iter_017에서는 공통 설명과 구조화 packet으로 바뀌었다. 기존 predicted와 새 L의 차이는 여러 문구가 함께 바뀐 결과다. 이를 특정 한 문장의 효과라고 단정할 수 없다. 다음 대조는 정보값·질문·출력 형식을 유지하면서 바꾸는 문구를 명확히 한정해야 한다.

## Strategy Check / 연구 방향 판단

중요한 능력은 전문 도구의 제한된 정보를 활용하면서 원본 영상에서 다른 소견을 계속 판단하는 것이다. 확인된 사실은 RSNA 개발 집단의 인터페이스 의존성과 category별 손익이다. 미확인 설명은 안내문의 답변 편향, RSNA 판독 규약 해석, finding 간 범위 혼동, localizer 오류다.

1. **부분 evidence의 질문 범위 진단:** 기존 실제 출력과 실행기를 활용할 수 있고, 추가 학습 전에 경쟁 설명을 구분할 수 있다. 잠정 1순위다. 다만 정확한 부분 정보, 단순 문구 대조, 다른 finding의 정답이 없으면 기존 RSNA 진단의 반복에 그친다. 질문에 무관한 evidence를 제외하는 단순 규칙이 해결하면 그것을 강한 baseline으로 보존하고 새 방법의 필요성을 낮춰야 한다.
2. **다른 질문으로 전환—시간에 따른 변화 판단:** 이전·현재 영상에서 변화 방향을 구별하는 능력은 중요한 별도 후보다. 정보 순서와 실제 변화의 구분, 단일 영상 shortcut 통제가 필요하다. MS-CXR-T는 5 findings의 Improving/Stable/Worsening을 다루는 1,326개 주석을 제공한다. 현재 로컬 자료·접근 권한·관련 방법의 차별성을 확인하지 않아 즉시 구현 후보로 확정하지 않는다. [MS-CXR-T 공식 설명](https://physionet.org/content/ms-cxr-t/1.0.0/)
3. **현재 grounding 개선:** 직접 SFT baseline과 잔여 위치 오류는 유효하다. 그러나 추가 loss의 이득과 좌표 전달의 추가 성능 이득이 입증되지 않았다. 새 원인·일반화·데이터 효율 근거 없이 학습을 늘리는 정보 이득은 현재 낮다. grounding 전체를 기각하는 판단은 아니다.

일반적인 영상–텍스트 충돌이나 의료 sycophancy로 이름만 바꾸는 전환도 우선하지 않는다. 아래 선행과 이미 많이 겹친다.

## 선행 연구가 바꾸는 기여 기준

- [Visual Evidence Prompting, ACL 2025](https://aclanthology.org/2025.acl-long.205/)은 전문 시각 모델 출력을 prompt로 제공한다. 이는 iter_015에서 확인한 선행이며 이번에는 후속 실패 조건과의 관계를 확인하기 위해 다시 열었다. 도구 출력의 언어화 자체는 기여가 아니다.
- [Medical Context Distorts Decisions in Clinical Vision Language Models, v1](https://arxiv.org/html/2605.17436v1)은 MedGemma 1.5를 포함해 영상–텍스트 충돌, 무관한 과거 기록, 문구 변화와 negative flips를 조사한다. MIMIC-CXR 1,000개 정상/비정상 자료를 사용하며, 양성은 선택한 5개 병변 중 하나만 있는 경우로 제한한다. 일반적 context 민감성 관찰은 이미 겹친다. 같은 영상에 대한 참인 부분 정보와 다른 finding의 공존을 다루는 조건은 구별 후보지만, 그것만으로 신규성이 확정되지는 않는다.
- [Benchmarking and Mitigating Sycophancy in Medical Vision Language Models, v7](https://arxiv.org/abs/2509.21979v7)은 권위·사회적 단서와 VIPER를 다룬다. 단순한 잘못된 사용자 주장 저항 실험을 새 방향으로 제시하기 어렵다. 이번에는 공식 초록·버전까지 확인했으며 구현과 전체 비교 실험은 추가 확인 대상이다.
- CORAL과 grounding→QA 형식 대조는 `agent/runs/iter_015/think/round_01.md`의 기존 조사 근거를 이어받는다. 같은 문헌을 새 발견으로 세지 않는다.

위 논문은 조사 자료다. 이번 계획 단계에서 새 사용자 추천을 생성하지 않는다.

## 정답 자료와 접근 가능성

기존 자료의 제한은 iter_015 기록과 일치한다. NIH bbox 160명에서 미주석 finding은 unknown이며, 이를 음성으로 바꿀 수 없다. RSNA와 NIH는 원천이 겹치므로 데이터셋 이름이 달라도 외부 기관 일반화가 아니다. 로컬 VinDr 10영상은 이미 사용한 개발 자료다. CheXpert legacy metadata에는 absent, uncertain, unlabeled가 구분돼 있으며 unlabeled를 no로 바꾸면 안 된다.

이번에 확인한 추가 정보는 다음과 같다.

- VinDr 공식 배포는 bbox와 별도의 `image_labels_test.csv`를 제공하며, test는 판독자 합의 주석이다. finding별 0/1 label은 bbox 부재보다 적절한 정답 출처 후보다. 그러나 공식 파일은 credential·교육·DUA가 필요한 자료다. 기존 mirror 다운로드 이력만으로 새 전체 자료의 접근 권한과 정답 출처가 확인됐다고 볼 수 없다. 익명 image ID만으로 환자 독립성도 보장하지 않는다. [VinDr 공식 데이터 설명·접근 조건](https://physionet.org/content/vindr-cxr/1.0.0/)
- 기존 다운로드 코드는 `legacy/scripts/01_data/download_vindr_cxr_samples.py`이며 `sunday-hao/vindr-cxr-testset`의 test.csv와 PNG를 사용했다. HF cache에 관련 항목은 있지만 공식 image-level label과의 대응은 아직 확인하지 않았다.
- NIH의 별도 전문가 주석에는 4 findings의 adjudicated YES/NO 4,374영상과, 14 findings·normal/abnormal을 포함한 810영상 자료가 있다. 이는 기존 bbox와 다른 정답 자산 후보다. 공식 페이지는 label 접근용 form과 Google Cloud 영상의 Requester Pays를 명시한다. 현재 확보 여부를 먼저 확인하고, 추가 유료 접근이나 신청을 자동 수행하지 않는다. 같은 원천의 환자 제외도 필요하다. [NIH 전문가 주석 공식 설명](https://docs.cloud.google.com/healthcare-api/docs/resources/public-datasets/nih-chest)

다음 라운드에서 가장 중요한 확인은 '이미 허용된 경로에서 finding별 양성·음성 정답과 환자 식별을 확보할 수 있는가'다. 정답·권한 문제는 표본 수를 늘려 해결할 수 없다.

## 코드 재사용과 자원

현재 research HEAD는 `d12ef5ccea60d05b9163519980cdb1624b3fa682`이며 `git status --short`와 diff는 비어 있다. `qa_spec.py`, `ev17_spec.py`, `qa_data.py`, `qa_protocol.py`, `ev17_reuse.py` 및 tracked 파일 목록을 확인했다.

승인된 질문·parser·packet 모듈은 기존 RSNA 범위에서 재사용할 수 있다. 새 finding에 Normal/Abnormal mapping을 그대로 적용할 수는 없다. 실제 사용할 실행 경로에는 다음 수정·검증이 필요하다.

- labels·sets·reuse manifest를 protocol에 잠그고 읽을 때 hash 검증을 강제한다.
- 신규 bbox 경로에서 실제 요청·record·completion·adapter·영상 연결을 검증한다.
- 확대 판단은 같은 estimand의 효과 크기와 정밀도를 연결한다.
- 현재 실행기에서 missing/extra/duplicate 거부와 실제 중단·재개 정합성을 확인한다.

새 접근법 브랜치를 택하면 자동 승인 기반에 현재 RSNA 코드가 모두 있다고 가정하면 안 된다. 최종 구현 계획에서 필요한 개별 파일과 의존성을 이 SHA에서 선별하는 manifest를 작성해야 한다. 이번 `reuse_assets=[]`는 조사 중 미확정 상태이며 반입 승인이나 전체 스냅샷 승인이 아니다.

iter_017의 두 GPU·총 4 worker 실측은 96요청의 token 일치, GPU별 peak 17,608/17,537 MiB, 4,800건 본평가 wall-clock 합 약 901초다. 이는 짧은 QA 출력의 참고값이다. 새 입력에서는 GPU당 1/2 worker 또는 유망한 batch 확대를 development에서 비교하고, worker당 2GiB 여유와 긴 출력 peak를 포함해야 한다. 요청 행렬과 자료를 정한 뒤 처리량으로 비용을 산출한다. 임의 시간 상한은 두지 않는다.

## 결과별 투자 판단의 초안

- **양성:** 직접 질문·단순 범위 문구·질문별 evidence 선택을 통제해도 다른 finding과 독립 환자에서 중요한 손실이 남으면, 적용 범위를 명시한 한계 검증과 방법 비교로 진입한다. 내부 원인의 완전한 증명은 기다리지 않는다.
- **음성:** 문구 보정으로 해소되거나 RSNA 규약에 국한되면 그 baseline과 음성 결과를 보존하고 다른 질문으로 이동한다.
- **불확정:** paired 전이 수와 정밀도 부족이면 판단을 바꿀 표본 확대를 검토한다. 정답 부재·권한·불완전 주석·식별 불가능한 대조는 추가 생성으로 해결하지 않는다.

## 대규모 GPU 필요 후보

여러 전문 도구의 범위·신뢰도와 다중 finding을 함께 학습하는 vision encoder–언어 모델 공동 post-training, 다기관 longitudinal 영상의 변화 표현 학습은 보존 후보다. 넓은 데이터 정합성과 학습 비용이 필요하다. 현재 두 GPU에서 가능한 inference 진단·LoRA·모듈형 대조와 비교한 뒤 필요성을 판단한다.

## 한 라운드 더 조사하는 이유

이번 추가 조사는 막연한 주제 탐색이 아니다. 원시 재집계가 '검출값의 과신'이라는 단일 설명을 약화시켰고, 가까운 선행이 일반적 context 충돌을 이미 다룬다. 정답 자료와 최소 대조의 확보 여부가 구현할 질문 자체를 바꾼다. 이를 해결한 뒤 GPU 진단을 구체화하거나 별도 능력 질문으로 전환한다.

## 다음에 파고들 질문
- 기존 cache·다운로드 provenance·공식 배포 정보를 기준으로, 새 권한이나 비용 없이 다른 finding의 명시적 양성·음성 정답과 환자 식별을 확보할 수 있는 자료는 무엇인가? VinDr image-level labels 또는 NIH 전문가 주석의 실제 확보·연결 상태와 RSNA/legacy 중복 제외 가능성을 확인한다.
- U 자체의 손실, 실제 검출값의 영향, 질문 범위 혼동을 구분하는 최소 대조는 무엇인가? 기존 D36에서만 문구·parser를 정하고, direct M0·B/K·명시적 범위 문구·단순 질문별 evidence 선택을 어떤 고정 행렬로 비교할지 결정한다.
- 참인 부분 evidence의 교차 finding 효과는 Medical Context Distorts Decisions·VEP의 범위와 어떻게 구별되는가? 단순 evidence 제외 규칙을 넘어 방법 개발이 필요한 실패 조건이 성립하지 않으면, 시간 변화 판단 후보가 중요성·자료·선행 차별성에서 더 나은가?
- 선택한 질문의 핵심 paired 효과와 전이 빈도를 어느 정밀도로 판단해야 하는가? 단계별 표본·요청 수·확대 기준, 새 브랜치의 정확한 파일 반입 목록, 필요한 실행기 수정과 두 GPU 처리량 비교를 함께 확정한다.
