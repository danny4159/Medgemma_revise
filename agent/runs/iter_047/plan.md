# 요약

- **이번에 할 일:** 두 소견 초안의 상태를 네 조합으로 바꾸고, 오류 수정과 올바른 상태 보존을 실제 MedGemma 출력으로 비교한다.
- **필요한 이유:** 기존 grounding 점수 개선은 보고서 검토 능력의 증거가 아니다. 초안을 보지 않는 소견 판단과 결정론적 편집으로 충분한지도 함께 확인한다.
- **확인할 기준:** 영상 정보의 기여, 수정률·훼손률, 중요한 교정–보존 trade-off, 단순 대안의 충분성을 사전 규칙으로 판단한다.
- **주의·다음:** 완전한 보고서 교정이나 새 기여를 입증하는 실험은 아니다. D8/E96 한정 진단 이후 최소 방법 시험 검토 또는 투자 보류로 종료한다.

# Current Understanding

iter_046은 같은 annotation으로 MedGrounder를 적응시키면 기존 문장별 C 정확도 격차의 점추정치가 해소됨을 보였다. 비열등성은 불확정이지만 CI 문턱만 넘기기 위한 추가 투자는 보류한다. iter_041의 공동 요청 저하와 비용 blocker, iter_042의 presence gate 이후 잔여 문제 미확정, iter_043의 영상 구별 불확정은 그대로 유지한다.

이번은 기존 plan의 실행 복구 amendment가 아니다. round_01의 조사와 이번 metadata·선행 확인을 근거로 새 제한 과제를 선택한다. GOAL, RSNA checkpoint, VinDr 승인 대기, H192/F120/test/MRI reserve는 유지한다.

두 소견의 존재/부재 상태를 검토하는 과제다. 자유형 문장의 모든 내용, 누락된 새 질환의 발견, 위치·중증도·시간 변화, 임상 reasoning은 평가하지 않는다. 최종 출력은 실제 생성된 상태 JSON과 그 상태를 반영한 결정론적 두 문장이다.

# Strategy Check / 연구 방향 판단

**재검토 이유:** 강한 적응 모듈형 baseline을 확보했고 기존 문장별 비교의 다음 정보 가치가 낮아졌다. round_01에서 보고서 교정의 선행 중복과 정답 문제를 확인했으므로 이번에는 실행 가능한 실패 조건을 좁혀야 한다.

**선택 비교:** 문장별 loss 개선은 우선하지 않는다. joint SFT는 형식 미학습을 시험할 수 있지만 독립 처리·적응 MedGrounder보다 필요한 효용이 구체적이지 않다. 선택한 진단은 초안 검토라는 사용 목적에서 수정과 보존을 분리하며, 기존 생성기를 사용해 학습 없이 경쟁 설명을 구분할 수 있다. 자유형 보고서 benchmark 구축보다 작은 범위로 판단 가능하다.

**기여에 대한 제한:** CorBenchX MSRL과 phrase-grounded fact-checking/APO는 이미 교정을 다룬다. APO에는 올바른 내용을 유지하는 규칙도 있다. 이번 과제나 polarity perturbation을 새 기여로 부르지 않는다. 선행을 넘어설 주장은 아직 없다.

**track 연속성:** 같은 language-conditioned-grounding track에 기록한다. bbox 출력에서 임상 소견의 검토로 평가 단위를 바꾸지만 영상 근거와 언어 출력의 연결이라는 큰 질문과 iter_015~046의 교훈을 이어받는다. 진단·setup 연속 기록을 초기화하지 않는다. 과거 비용은 집계 범위가 달라 임의로 합산하지 않는다.

**끝난 뒤 결정:** 단순 대안이 충분하면 이 과제의 방법 투자를 보류한다. 중요한 잔여 trade-off가 엄격한 기준으로 관찰되면 직접 SFT를 포함하는 최소 방법 pilot의 가치만 다음 리뷰에서 검토한다. 정밀도·자료·구현 때문에 불확정이면 E96를 늘리거나 주변 과제를 붙이지 않는다.

# Hypothesis

동일한 영상을 이해할 수 있어도 초안을 수정하라는 조건에서 잘못된 상태를 유지하거나 올바른 상태를 바꿀 수 있다. 보존 지시만으로 해결되는지, 초안 없는 공동·독립 판단으로 해결되는지 확인한다.

대안 설명은 다음과 같다.

- 초안 없는 판단부터 틀리면 시각 판별 또는 annotation 문제다.
- R1만 나쁘고 R2가 충분하면 합리적인 prompt 수정으로 해결되는 문제다.
- BJ/BI와 결정론적 편집이 충분하면 별도 편집 학습의 필요성이 약하다.
- text-only가 비슷하면 질환 조합·언어 prior나 자료 구성의 영향을 먼저 의심한다.
- oracle에서도 실패하면 schema·지시·평가기 문제를 우선한다.

# Limitation Evidence / Correct Usage Checks

연결하는 기존 observed id는 padchest-sentence-grounding-and-joint-retention과 padchest-presence-grounding-interface다. 전자는 새 사용 과제를 선택한 배경이고 후자는 초안 없는 presence 판단을 강한 대안으로 넣는 근거다. 둘 다 이번 교정 실패의 실증 근거는 아니다.

따라서 experiment_role=diagnostic, method_stage=none이다. 학습·새 방법·pilot gate 우회를 하지 않는다. iter_041 blocker와 기존 limitation 상태를 변경하지 않는다.

MedGemma 1.5 revision 91850547d9f0b2fdd21aa7c5f4f3d1a8a52c243b의 M0만 사용한다. adapter는 로드하지 않는다. 공식 chat template과 기존 값 보존 전처리를 유지하고 D8에서 processor tensor, 영상 token, image/text modality, 출력 cap·EOS를 확인한다. text-only에는 영상 tensor/token이 없어야 한다.

# Contribution Path / Baselines / Reuse

## 가까운 방법과 주장 범위

[CorBenchX](https://arxiv.org/html/2505.12057v1)는 단계적 오류 교정을, [phrase-grounded fact-checking](https://arxiv.org/html/2509.21356v1)은 진위와 위치 검증을 다룬다. [APO](https://openaccess.thecvf.com/content/CVPR2026/papers/Mahmood_Phrase-grounded_APO_for_Improving_Chest_X-ray_Report_Generation_CVPR_2026_paper.pdf)는 검증에 따른 선택적 교정과 정렬을 다룬다. 이번은 이들보다 우수한 방법의 평가가 아니다. 공개 checkpoint·전체 실행 경로를 확보하지 않은 방법을 재현했다고 표현하지 않는다.

최소 방법 시험을 후속으로 선택하려면 현재 진단의 유효한 실제 출력 근거와 함께 같은 annotation의 강한 직접 교정 SFT를 대조해야 한다. 단순 판단 후 편집을 이기지 못하는 새 loss는 자동 확대하지 않는다.

## 비교 조건

모든 조건에서 finding 이름과 qA/qB를 동일하게 유지한다. 출력은 두 ID 각각 present/absent/uncertain 중 하나다. unknown·uncertain을 정답으로 인정하지 않는다.

- **K:** 초안 그대로 반환. 수정률 0인 보존 기준점이다.
- **R1:** 영상과 두 문장 초안을 주고 최종 상태를 판단한다. 오류 존재를 단정하지 않는다.
- **R2:** 같은 입력에 '초안은 모두 맞을 수도 있으며, 영상이 수정을 지지하지 않으면 올바른 내용을 유지하라'는 보존 지시를 추가한다. 주 직접 교정 조건이다.
- **T:** R2와 같은 소견·초안·출력 지시를 제공하되 영상은 제공하지 않는다. 상태의 불확실성을 허용한다.
- **BJ:** 영상과 두 finding 이름만 제공한다. 초안 없이 두 상태를 한 번에 판단하고 규칙으로 문장을 생성한다.
- **BI:** 같은 영상에서 finding 하나씩 독립 판단한다. 두 호출을 결합한다.
- **O:** D8에서만 정답 상태를 명시적으로 제공하여 같은 출력 schema와 편집 연결을 검사한다. 실용 baseline에서 제외한다.

기존 C/MedGrounder는 위치 출력에 적응된 모델이다. box의 유무를 소견 진위로 해석해 이번 비교군을 만들지 않는다. 과거 빠른 모듈형 대안의 존재는 보존하지만 이번 과제의 충분성을 대신 판정하지 않는다.

## 재사용

새 branch는 재사용 호환 승인 iter_006의 68117cfd08429ffc3cb9b77e14fb1db3221d86ab를 기반으로 한다. 이 선택은 오래된 NIH 코드의 새 승인이나 사용을 뜻하지 않는다. 필요한 pg43_run·pg39_data와 9개 의존 파일은 reuse_assets의 iter_043 전체 SHA에서 반입한다. 기준점에 경로가 없음을 확인했다.

현재 HEAD와 반입 원본의 11개 blob은 같다. pg43_run은 실행기로 재사용하고 기존 CLI 전체를 새 schema 평가기로 간주하지 않는다. 새 parser·평가·자료 구성만 추가한다. 사용하지 않는 MG 학습기·launcher·과거 bbox 평가기의 needs_fix는 이번 범위에서 고치지 않는다.

# Proposed Experiment

## 1. 자료와 평가 단위 고정

기존 PadChest-GR raw의 grounded_reports_20240819.json과 master_table.csv.zip을 사용하고 pg39_data의 pinned hash·연결 검사를 유지한다. 공식 train만 사용한다. H192는 기존 manifest의 E192 환자 ID로 제외하고 F120·공식 validation/test 및 MRI reserve는 열지 않는다.

고정 finding 사전은 cardiomegaly, pleural effusion, consolidation, pneumothorax, pulmonary nodule, atelectasis, scoliosis, aortic elongation, pacemaker다. 양성은 명시적 label과 양언어 문장의 일치로, 음성은 해당 finding의 명시적 부정으로 정의한다. normal heart size 또는 normal cardiothoracic index처럼 cardiomegaly 부재를 직접 표현하는 문구는 의미 검토 후 허용한다. 일반적인 정상·무소견, clear costophrenic angle, bbox 부재, 다른 질환의 부재에서 target 음성을 추론하지 않는다. alveolar pattern을 consolidation으로 자동 치환하지 않는다.

시간 비교, uncertain/possible/cannot exclude, significant처럼 부정 범위를 제한하는 표현, 부분 위치의 부재를 전체 부재로 바꿔야 하는 문장, 양언어 불일치, 같은 finding의 상충 annotation은 제외한다. 양성에 box가 없다는 이유만으로 음성 처리하지 않는다.

모델 출력을 보기 전에 후보별 sentence_en/sentence_es, label, finding 이름, 최종 상태, 제외 이유를 private 의미 검토표에 보존한다. 이것은 문장의 의미 연결 검사이며 전문가의 새 영상 판독이 아니다. 현재 metadata에는 전체 원 보고서가 없다는 한계를 기록한다.

한 환자에서 한 영상·서로 다른 두 finding만 선택한다. 후보 pair와 환자 선택은 seed4701의 hash 순서와 희소 층 우선 배정으로 고정한다. D8은 상태00/01/10/11 각2명, E96은 각24명이다. 같은 환자·study·영상·pixel이 D/E에 중복되지 않게 한다. 혼합 상태의 qA/qB 배치는 균형화하고 ID·파일명·prompt에 정답이나 corruption 여부를 넣지 않는다.

기존 개발 집단과의 중복은 표시하되 독립 확인이라고 부르지 않는다. M0만 사용하므로 T305 적응 checkpoint의 학습 누수와는 구분한다. 사전학습 노출은 미확정이다. 최종 의미 검토 후 요구 층을 채울 수 없으면 broad negative를 추가하거나 reserve를 열지 않고 자료 gate 미달로 종료한다.

각 영상에서 두 canonical finding의 상태를 present/absent 네 조합으로 만들어 초안00/01/10/11을 모두 평가한다. 이에 따라 환자마다 무오류 초안1개, 단일 오류2개, 이중 오류1개가 생긴다. 생성 문구는 소견별 고정 canonical 문장으로 하여 수식어·중증도·위치 의미를 추가하지 않는다. 합성 오류의 실제 임상 빈도는 주장하지 않는다.

## 2. 동작 확인: D8

D8에서 본실험의 15요청/환자와 O 4요청/환자를 실행한다. 기본152요청이다. parser는 두 ID·허용 상태·중복·누락·상충 출력·비EOS를 강제 검사한다. 코드펜스 같은 허용 wrapper는 D 단계에서 규칙을 고정한다. 상충하는 여러 답 중 하나를 고르는 parser는 금지한다.

O 32요청의 상태·ID와 결정론적 문장 생성은 모두 맞아야 한다. 영상/텍스트 조건의 입력 정합성과 재개·완료 검증도 통과해야 한다. D에서만 필요한 형식 수정 한 번을 허용하며 이전 prompt·출력은 보존한다. 수정할 경우 D 전체 관련 조건을 새 attempt로 다시 확인한다. 두 번째에도 기술 gate가 실패하면 E를 실행하지 않는다. D 임상 정확도로 prompt를 선택하지 않는다.

## 3. 가능성 탐색: E96

기술·자료 gate와 평가 lock이 확정되면 E96을 한 번 실행한다. 학습 seed·checkpoint·threshold 탐색은 없다. R1/R2/T 각각384요청, BJ96요청, BI192요청으로 총1,440요청이다. K는 생성하지 않는다. BJ/BI 결과는 동일 환자의 네 초안에 공통 적용한다.

E96은 큰 교정 손실을 판별하기 위한 개발 진단이다. paired binary 차이의 불일치 비율을0.25로 가정하면 95% 구간 반폭의 근사값은 약0.10이다. 이는 실측 분산이 아니며 작은 차이나5% 수준 비열등성을 확정하기에는 부족할 수 있다. 따라서 작은 E 일부에서 결과를 보고 표본을 정하지 않고 고정96명을 완료한다.

## 4. 규모 확대와 독립 확인

이번 E96이 가능성 탐색의 종료점이다. method pilot·다중 seed·다기관·자유형 보고서로 자동 확대하지 않는다. 양성 기준을 충족한 경우에만 다음 full 리뷰에서 강한 직접 SFT를 포함한 최소 방법 시험을 별도 계획한다. 독립 확인 집단은 이번에 사용하지 않는다.

## 자원·시간·재개

실행 직전 nvidia-smi와 상속된 CUDA_VISIBLE_DEVICES의 논리/물리 대응을 확인한다. 두 GPU 중 여유가 큰 장치부터 배정한다. D에서 GPU당1 worker와2 worker 구성을 같은 요청으로 비교한다. 추가 비교는 독립 요청이 충분하고 예상 절약이 측정 비용보다 클 때만 한다. 각 worker의 실제 peak와 다른 점유에 최소2GiB 여유를 더해 GPU 용량을 넘지 않아야 한다.

처리량·긴 출력 latency·OOM·CPU/RAM/I/O 경합과 출력 정합성을 기준으로 구성을 선택한다. 기존 약8.35GiB/worker는 참고값이며 새 작업의 메모리 보장을 대신하지 않는다. GPU당1 worker를 유지하면 구체적인 실측 이유를 기록한다.

greedy, bf16과 충분한 cap ladder 1000→2000→4000을 사용한다. 비EOS 재시도는 모두 보존하고 마지막에도 비EOS이면 invalid로 점수에 포함한다. 의미가 틀렸다는 이유로 재생성하지 않는다.

본생성 참고 wall 범위는 과거 작업 처리량 환산으로 약1.6–4.8시간이다. D 실측 후 실제 E 요청량·loading·재시도를 반영한 ETA를 기록한다. 임의 시간 상한으로 중단하지 않는다. 요청 단위 claim, worker별 파일, 원본 partial 보존, 동일 config 재개를 유지한다. 기존 실행 중인 큐와 다른 사용자 프로세스는 건드리지 않는다.

# Implementation Tasks for Claude

1. 기준 원문은 이번 plan과 iter_043 review.json의 해당 code_assets다. 반입 SHA·import 의존성과 기존 결과 위치를 확인한다. 새 결과는 research/results/iter_047/ 아래에만 저장한다.
2. rr47_spec.py에 finding 사전, 문장 mapping, prompt R1/R2/T/BJ/BI/O, 상태 parser, 요청량과 판정 규칙을 구현한다. 사전 의미 검토를 keyword 결과와 분리한다.
3. rr47_data.py에서 pinned metadata 연결, 보호 ID 제외, 양언어 검토표, 환자 단위 층화 선택, 이미지 변환·hash, 네 초안 생성을 구현한다. build 중단 시 원본을 덮어쓰지 않는다.
4. rr47_run.py는 pg43_run의 실행·검증 API를 사용한다. protocol과 호출 인자 대조, 전 의존성 잠금, D gate의 실제 E 진입 강제, 완료 결과 재검증을 구현한다. 연구 가설과 무관한 runner 재작성은 하지 않는다.
5. rr47_eval.py와 별도 rr47_verify.py에서 아래 지표·환자 bootstrap·판정을 각각 구현한다. verifier는 production 점수 함수를 그대로 호출하지 않는다. 모든 조건을 검증하고 불일치 조건을 제외한 채 PASS를 만들지 않는다.
6. 손계산 fixture로 K, 완전 정답, 항상 present, 항상 flip, 한쪽 누락, uncertain, 상충 JSON의 수정률·훼손률·paired 분모를 검사한다. D에서 중단·재개와 실제 변조·중복·누락·wrong config 거부를 확인한다.
7. 최종 report/raw/manifest/protocol/source/verifier 결과의 digest를 연결한 뒤 completion을 마지막에 확정한다. 종료 코드와1,440개 E 요청의 완결성을 확인하고 실제 비용·미완료·보류 이유를 보고한다. 완료 전 보고서를 최종 결과로 내지 않는다.

# Evaluation (성공/실패 기준 포함)

## 점수

각 환자는 두 finding×네 초안으로8개 상태 평가를 가진다. 그중4개는 원래 맞는 상태,4개는 틀린 상태다.

- **수정률 r:** 원래 틀린4개 상태 중 최종 정답 상태로 바꾼 비율.
- **훼손률 h:** 원래 맞는4개 상태를 반대 상태로 바꾼 비율.
- **보존 실패율 h_fail:** 원래 맞는 상태를 반대 상태·uncertain·invalid로 만든 비율. 투자 기준에는 보수적인 h_fail을 쓴다.
- **최종 상태 정확도:**8개 상태의 정답률. uncertain/invalid는0점이다.
- **clean exact:** 무오류 초안에서 두 상태를 모두 보존한 환자 비율.
- **robust exact:** 네 초안 모두에서 두 상태가 맞은 환자 비율.
- **초안 민감도:** 같은 영상·finding에서 초안에 따라 최종 상태가 달라지는 비율. 변화만으로 결함을 판정하지 않는다.

K는 r=0, h_fail=0이다. BJ/BI는 실제 상태 예측을 네 초안에 적용한다. 반복 초안을 독립 환자로 세지 않는다. 병원 배포의 오류 prevalence를 가정한 단일 utility 점수는 만들지 않는다.

환자 단위 층화 paired bootstrap10,000회, seed4702를 사용한다. 환자 내 네 초안·두 finding은 함께 resample한다. 주비교 R2 대 BJ의 r 차이와 h_fail 차이는 각각97.5% CI로 제시한다. 나머지는95% CI와 탐색 표기로 보고한다. finding별·원 상태별 표는 기술적 분석이며 유리한 층으로 주판정을 교체하지 않는다.

## 사전 투자 판단

사용 목적상 탐색 목표는 잘못된 상태의80% 이상 수정과 올바른 상태의5% 이하 보존 실패다. 이는 임상 배포 안전 기준이 아니라 후속 연구 후보를 거르는 기준이다. 성공을 주장하려면 r의 CI 하한≥0.80, h_fail의 CI 상한≤0.05를 함께 요구한다.

**단순 대안 충분:** R1/R2/BJ/BI 중 하나라도 위 두 조건을 충족하면 이 제한 과제에서 새 방법 투자를 보류한다. 다른 조건의 손실 관찰은 보존하되 자동 학습으로 연결하지 않는다.

**최소 방법 시험을 검토할 양성 근거:** 다음을 모두 요구한다.

1. 자료·정상 사용·실행·독립 재계산이 유효하다.
2. BJ의 최종 상태 정확도가 T보다0.10 이상 높고 paired95% CI 하한이0보다 크다. 영상 정보가 실제 판단에 기여해야 한다.
3. 주비교에서 BJ−R2 수정률 차이가0.15 이상이고97.5% CI 하한>0이며, 동시에 BJ−R2 보존 실패율 차이가0.05 이상이고97.5% CI 하한>0이다. 즉 초안 없는 재판단은 더 고치지만 더 훼손하는 trade-off가 있어야 한다.
4. R1/R2/BJ/BI 각각에서 r의95% CI 상한<0.80 또는 h_fail의95% CI 하한>0.05 중 적어도 하나가 성립한다. 단순히 복합 성공 기준을 통과하지 못했다는 이유만으로 baseline 부족을 확정하지 않는다.

이 기준을 충족해도 새로운 방법이나 선행 대비 차별성은 미확정이다. 다음 리뷰는 직접 교정 SFT를 먼저 포함하는 최소 개입의 가치를 판단한다. 강한 baseline이 해결할 가능성을 남기며 full 확대는 별도 결정한다.

**음성 또는 투자 가치 부족:** 단순 대안 충분, R2로 손실 해소, text-only와 유사한 성능, 초안 없는 시각 판단부터 낮은 경우를 구분한다. 각각 이번 교정 후보의 투자 보류 근거이며 의료 VLM 전체의 기각은 아니다.

**불확정:** CI가 목표·trade-off 경계를 가로지르거나 annotation·유효 출력 부족이 남으면 그 항목을 명시한다. 추가 표본·질환·prompt·seed로 경계를 넘기려 하지 않는다. 이미 저장된 출력의 한정 재분석 이외의 자동 보완은 없다.

## 비용

요청별 전처리 시작부터 상태 파싱·문장 렌더링 종료까지 latency를 기록하고 loading 포함 wall, GPU별 점유 구간, peak VRAM, tokens, 실패·재시도를 별도로 보고한다. BJ/BI의 반복 초안 공통 출력을 재사용한 실험 비용과 실제 한 검토당 필요한 호출 비용을 구분한다. request latency bootstrap을 device 시간 CI로 사용하지 않는다. 이번에는 단회 실행 비용의 점추정치를 보고하며 비용 우위나 비열등성의 확증을 주장하지 않는다.

# Risks / Checks

- PadChest 음성 문장의 검증 수준은 양성 box annotation과 같지 않다. 명시적 의미만 사용하고 진단 정답을 annotation 상대의 상태로 한정한다.
- rough 후보65/74/159는 겹침·qualified negation을 제거하기 전 값이다. 표본 부족 시 규칙을 완화하지 않는다.
- canonical 두 문장은 자유형 보고서의 대용물이 아니다. 원본 문장에 없는 위치·중증도·진단을 생성하거나 그 정확도를 주장하지 않는다.
- 네 초안의 균등 구성은 오류 밀도 효과를 분리하기 위한 설계다. 자연 발생 보고서의 유병률·오류율 추정에 사용하지 않는다.
- finding 조합 prior가 남을 수 있다. T와 영상 조건의 차이를 양성 판단의 필수 조건으로 사용한다.
- E96은 개발 자료이며 선행 평가 자료와의 중복·MedGemma 사전학습 노출을 모두 독립성으로 포장하지 않는다.
- 새 schema에 bbox parser를 적용하지 않는다. invalid·uncertain을 보존 성공으로 계산하지 않는다.
- 기존 iter_041 비용 blocker, iter_046 실행기 reuse_issues와 원 판정은 변경하지 않는다.

## 대규모 GPU 필요 후보

다기관 영상과 전문가 수정 이력을 사용하여 verifier·editor를 공동 학습하고 실제 오류 밀도에서 수정–보존 trade-off를 최적화하는 방향은 장기 후보로 남긴다. 현재 자료와 두 GPU의 한정 진단에서 그 필요성·효과·신규성이 확인된 것은 아니다.

# 계획의 근거 (GPT 조사 노트)

## 이번 라운드의 결론

완전한 자유형 보고서 교정은 이번 범위에서 제외한다. 명시적 annotation이 있는 두 소견의 상태를 수정·보존하는 제한된 실제 출력 diagnostic을 선택한다. 이는 새 기여가 확인된 방향이 아니라, 단순 대안 이후에도 방법 투자 가치가 남는지 판단하는 실험이다.

## 직전 질문에 대한 답

1. **가까운 방법은 보존을 고려하는가?** 고려한다. CorBenchX 본문은 오류가 주입된 보고서의 탐지·교정과 MSRL을 평가한다. 확인한 평가 설명에서는 별도 무오류 입력의 불필요한 수정률이 주지표로 제시되지 않았다. 그러나 이를 선행 전체의 부재로 일반화하지 않는다. [CorBenchX 본문](https://arxiv.org/html/2505.12057v1)

APO의 공식 PDF 검색 색인에서 Table 1의 올바른 finding/location에 대한 유지 규칙, Table 3의 1,000문장 교정 검사, Table 4의 집계 보고서 품질 비교를 확인했다. 따라서 ‘올바른 내용을 보존하는 교정’ 자체는 차별점이 아니다. PDF 직접 열기는 계속 실패했으며 부록 전체를 읽었다고 주장하지 않는다. [APO 공식 논문](https://openaccess.thecvf.com/content/CVPR2026/papers/Mahmood_Phrase-grounded_APO_for_Improving_Chest_X-ray_Report_Generation_CVPR_2026_paper.pdf)

Phrase-grounded fact-checking은 finding 진위와 위치를 함께 예측하며 polarity 반전 등의 합성 perturbation을 이미 사용한다. 단순 polarity 반전 과제를 새 benchmark 기여로 주장할 수 없다. [공식 본문](https://arxiv.org/html/2509.21356v1)

2. **접근 가능한 자료로 정답을 정의할 수 있는가?** 두 소견의 명시적 상태로 범위를 제한하면 가능성이 있다. PadChest-GR의 양성 소견은 영상과 함께 검토됐지만 음성 문장은 추출 과정과 검증 수준이 다르다. bbox 부재는 음성 근거가 아니며, broad normal 문구에서 개별 질환 부재를 만들지 않는다. 논문의 annotation 설명과 로컬 schema를 대조했다. [PadChest-GR annotation](https://arxiv.org/html/2411.05085v2)

로컬 pinned metadata의 train 3,185영상만 대상으로 읽기 전용 집계를 했다. H192를 환자 ID로 제외하고, 고정 아홉 소견의 명시적 양성 label 및 음성 문구를 거칠게 검색했을 때 두 상태 조합의 환자 후보는 모두 음성65명, 혼합74명, 모두 양성159명이었다. 이 집단들은 서로 겹칠 수 있으며 최종 적격 표본 수가 아니다. keyword 결과에는 qualified negation·문장 범위 오류가 들어갈 수 있으므로 출력 눈가림 의미 검토가 필요하다. D8/E96은 이 후보 용량과 큰 차이를 구분하는 진단 정밀도를 근거로 정한다. 보호 집단 영상이나 모델 출력은 열지 않았다.

전체 원 보고서 문자열은 현재 master_table에 없고 sentence_en/sentence_es가 있다. 따라서 원 전체 보고서를 독립 감사했다고 표현하지 않는다. 최종 판단은 양언어 소견 annotation과 label이 명확히 지지하는 존재/부재에 한정한다.

3. **어떤 단순 대안이 실제 실행 가능한가?** 같은 M0를 사용한 직접 교정, 보존 지시 교정, text-only, 초안 없는 공동·독립 소견 판단과 결정론적 편집을 실행할 수 있다. 이는 모델 계열·학습량 차이 없이 편집 조건을 구분한다. CorBenchX 공식 저장소는 MIMIC-CXR credentialed license를 명시하며, 확인한 README에는 MSRL checkpoint 실행 경로가 없었다. 접근 권한을 가정하거나 완전 재현을 했다고 하지 않는다. [공식 저장소](https://github.com/Liqq1/CorBenchX)

## 기존 결과와 선택의 연결

round_01 원문, GOAL, GPT_USAGE_POLICY, REPORTING_STYLE, iter_046 리뷰와 관련 code_assets, iter_042 리뷰, LIMITATIONS의 관련 항목을 확인했다. 문장별 적응 비교의 보류와 iter_041 공동 요청 관찰·비용 blocker는 유지한다. 이번은 그 blocker의 복구나 method gate 우회가 아니다. iter_042의 높은 presence 성능은 초안 없는 판단을 강한 대안으로 반드시 넣어야 하는 이유다.

기존 접근법 개선은 적응 MedGrounder 확보 이후 추가 정보 가치가 낮다. joint SFT는 형식 미학습을 시험할 수 있지만 빠른 모듈형 대안 대비 필요한 실용 이득이 아직 불명확하다. 이번 후보는 bbox 점수를 더 올리는 대신 검토 과정에서 올바른 임상 내용을 보존하는 능력을 다룬다. 다만 완전한 보고서, omission 발견, 임상 reasoning을 평가하지 않는다.

## 코드·비용 근거

현재 HEAD는 bab147379dde1bcd68550e298cc596ee15091e99이며 작업 트리는 깨끗했다. pg43_run.py와 명시한 10개 의존 파일은 iter_043 SHA의 blob과 모두 같았다. iter_043 code_assets의 제한적 승인 범위를 확인했다. 새 branch의 자동 기준점은 과거 호환 승인 iter_006이며, 실제 SHA 68117cfd08429ffc3cb9b77e14fb1db3221d86ab와 해당 리뷰를 확인했다. 이 기준점에는 필요한 경로가 없어 선별 반입을 명시한다.

iter_042의 E 414요청 launcher wall 합은 약1,702.9초이고, iter_043 MAIN_M0는 234요청에 약2,787.8초다. 서로 다른 출력 과제의 값이므로 참고 범위로만 사용한다. iter_043의 worker당 peak reserved는 약8.35GiB였다. 새 입력에서 D8 처리량과 실제 peak를 측정해 운영 구성을 확정한다.

## 대규모 GPU 필요 후보

전문가 수정 이력과 다양한 오류 밀도를 가진 다기관 자료로 시각 verifier와 편집기를 공동 학습하는 방향은 장기 후보로 보존한다. annotation·학습 비용이 크며 현재 두 소견 진단의 성공으로 필요성이나 신규성이 입증되는 것은 아니다.

파일 생성·수정·실험 실행은 하지 않았다.

이전 사고 라운드 노트: agent/runs/iter_047/think/
