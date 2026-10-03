# 요약

- **이번에 할 일:** OmniBrainBench의 brain MRI 질환 진단 QA를 연결하고 text-only, 전체 영상, 개별 영상 및 단순 투표를 비교한다.
- **필요한 이유:** UCSF annotation 접근 실패는 모델 실패가 아니다. 실제 접근 근거가 있는 자료에서 MRI 근거 사용 질문을 이어간다.
- **확인할 기준:** 자료·정답 연결, 영상의 기본 신호, 공동 입력의 정확도 변화와 추론 비용이다.
- **주의·다음:** 실제 MRI 사례 연결은 아직 미검증이다. 통과하면 같은 반복에서 출력하고, 결과에 따라 최소 방법 검토·모델 비교 검토·투자 보류를 선택한다.

# Current Understanding

iter_060은 자료 접근 단계의 execution_failed이고 모델 출력은 없다. UCSF의 enhancement/FLAIR extension T/U/R 가설은 미검증으로 보존한다. 이번 계획은 그 실행 복구가 아니라 정답·관측 단위가 달라진 별도 진단이다. 과거 계획의 문턱이나 판정은 변경하지 않는다.

iter_059의 MSD 구간 판정에서는 HD-GLIO+OR가 U8보다 정확하고 저렴했다. 해당 과제의 추가 VLM 적응과 timing 반복은 종료한다. 이 결과가 질환 진단 QA까지 해결했다는 뜻은 아니다.

대체 자료는 [OmniBrainBench 공식 배포](https://huggingface.co/datasets/FrankPN/OmniBrainBench/tree/main)다. annotation JSON과 영상 ZIP의 존재는 확인했지만 실제 MRI 진단 행·영상·사례 연결은 구현 단계에서 확인해야 한다. 원본 volume이 아니라 배포된 2D key image를 사용한다. 실제 임상 전체 study 판독으로 일반화하지 않는다.

유지: 최종 GOAL, MRI 우선순위, 기존 결과·checkpoint·reserve. 보류: UCSF routing, MSD 추가 적응, OCT 전환. 변경: 특정 sequence 배분에서 같은 사례의 공동/개별 영상 답변 비교로 좁힌다.

# Strategy Check / 연구 방향 판단

- **관찰:** 기존 구간 판정은 전문 대안이 충분했다. 새 QA에서는 기본 신호조차 아직 관찰하지 못했다.
- **남은 설명:** 기본 인식 부족, 공동 입력의 정보 활용 문제, 질문 prior, 선택지 효과, 정답 모호성이다.
- **최소 비교:** 같은 질문·영상 집합에서 공동 J와 개별 S_i/투표 V를 비교하고 T를 둔다.
- **바뀔 결정:** 영상 신호가 없으면 모델 적합성을 먼저 검토한다. 개별 신호가 공동 입력에서 손실되면 최소 개입 후보가 생긴다. 단순 투표가 충분하면 추가 방법 필요성이 줄어든다.

현재 방법 개선은 실제 오류 근거가 없어 이르다. 동일 MRI 질문의 한정 자료 보완은 원인 구분에 직접 도움이 된다. MRI 밖 전환은 준비 비용을 다시 지불하면서 이번 접근 실패를 설명하지 못하므로 후순위다.

mri-volume-evidence-use track과 iter_056~060의 비용·교훈을 유지한다. iter_060의 지배 비용은 자료 접근 확인이며 GPU 실험은 없었다. 이번에도 범용 benchmark 구축이나 전수 시각 감사를 만들지 않는다. iter_049~052의 다중 영상 준비·gate 실패를 연결하되 CT 결과를 MRI 능력의 근거로 옮기지 않는다.

# Hypothesis

동일 사례의 개별 영상에서 진단 신호가 나타나더라도 공동 입력은 그 신호를 항상 유지하지 못할 수 있다. 반대로 공동 입력이 상보적 근거를 활용해 더 정확할 수도 있다. 방향을 미리 가정하지 않는다.

개별 영상은 정답에 필요한 정보가 부족할 수 있다. 따라서 S_i의 오답을 곧바로 판독 결함으로 해석하지 않는다. 같은 정답에 대한 제한 관측 조건의 성능으로 보고한다. 공동 입력 저하 역시 입력 길이·형식·시각 처리 변화가 섞인 결과이며 내부 통합 기전의 확정 증거가 아니다.

# Limitation Evidence / Correct Usage Checks

이번 MRI 진단 QA의 observed/validated 근거가 없어 limitation_ids=[]이며 diagnostic/none으로 진행한다. 기존 SPIDER reference-interface 관찰은 과제가 다르므로 method 진입 근거로 사용하지 않는다.

MedGemma 1.5 revision 91850547d9f0b2fdd21aa7c5f4f3d1a8a52c243b, bf16, 공식 processor/chat template, greedy decoding을 사용한다. 배포 RGB 영상은 보존하고 추가 min-max·회전·crop·montage를 하지 않는다. volume의 axial 정렬 가정을 PNG에 적용하지 않는다.

실제 D 입력에서 공식 processor 구성과 wrapper의 input_ids, pixel_values 및 영상 순서를 대조한다. J는 원 annotation의 영상 순서를 유지한다. 파일명·source·정답·caption·보고서를 모델 입력에서 제외한다. 영상 누락 시 text-only로 묵시 전환하지 않는다. 모델의 오답 또는 oracle 불일치는 기술 gate 실패가 아니다.

# Contribution Path / Baselines / Reuse

가장 가까운 선행은 [OmniBrainBench 다중 영상 평가](https://arxiv.org/html/2511.00846v2)와 개별 추론 후 late voting이다. 이번 paired 진단은 문항 난이도가 다른 영상 개수별 집계와 구분된다. 새로운 contribution은 아직 없다.

비교군:

- T: 같은 질문·선택지, 영상 없음.
- J: 해당 QA에 연결된 모든 영상.
- S_i: 해당 집합의 i번째 영상 하나. 영상 순서대로 모두 평가한다.
- V: S_i의 유효 답변을 원본 선택지 ID로 복원한 뒤 plurality vote. 동률은 원본 선택지 문자열의 SHA256 순서로 결정한다. 전부 invalid면 invalid다. GT와 제시 위치는 동률 해소에 사용하지 않는다.
- S_mean: 모든 S_i 정확도의 평균. 무작위 한 영상 선택의 기대값이며 학습된 selector가 아니다.
- prior: 1/5 무작위 기대값과 D에서 정한 가장 빈번한 정답 문자열 선택 규칙. 문자열이 선택지에 없으면 고정 hash 규칙을 사용하고 적용 빈도를 표시한다. E 정답 빈도로 prior를 맞추지 않는다.

J와 V는 같은 고유 영상을 보지만 V는 K회 질문·생성을 수행한다. 이미지 token, text token, 요청 수, GPU 시간 차이를 함께 제시한다. any-correct와 GT best-single은 선택 가능성을 살피는 사후 oracle이며 실용 baseline·성공 기준으로 사용하지 않는다.

전문 segmentation+OR는 이번 질환 진단의 직접 비교군이 아니다. 이를 이유로 전문 모델의 불가능성을 주장하지 않는다. 후속 방법 투자에는 별도 학습 자료의 직접 SFT와 적절한 encoder+질문별 head, 단순 집계의 공정한 비교가 필요하다.

재사용은 iter_060 SHA adfbb52dd9cd838e203e9baa14a3c8cc184e4153의 msd56_run.py 중 load_model, env_info, build_inputs, generate 범위다. 파일은 현재 브랜치에 있으나 새 branch 반입을 위해 reuse_assets에 지정했다. source blob은 확인했다. MSD 전용 parser, request builder, launcher는 사용하지 않는다. generate의 기존 time.time 값에 의존하지 말고 이번 adapter의 monotonic 전체 경계를 기록한다. 원 리뷰의 미사용 모듈 문제를 전부 정비하지 않는다.

# Proposed Experiment

## 1. 한정 자료 연결

공식 배포 revision을 고정하고 closed-ended-qa_6823.json, 필요한 metadata 및 closed-ended-qa_6823.zip만 확보한다. open-ended archive는 받지 않는다. 먼저 JSON을 읽고 실제 schema와 후보 수를 확인한다. 선택 영상의 개별 취득이 불가능하면 약 734 MB ZIP을 받되 디스크·압축 해제 크기와 안전한 archive 경로를 점검한다. hf_cache는 수정하지 않는다.

자료 card의 CC BY-SA 3.0과 논문의 4.0 차이를 기록한다. 로컬 연구 사용에 적용할 배포 조건과 선택 원천의 이용 조건을 확인하고 원본 출처를 보존한다. 재배포나 외부 연락은 이번 범위가 아니다. 실제로 추가 권한이 필요한 source만 제외 또는 중단한다.

대상 과제는 **brain MRI에 근거한 질환 또는 병변 종류의 진단 선택** 하나다. 포함 여부는 질문·선택지·modality/source metadata로 정하고 모델 출력을 보지 않는다. 촬영 sequence 식별, 단순 병변 존재·개수·좌표, 치료·예후·분자형, 시간 변화, 질문에 정답이 명시된 문항은 제외한다. MRI와 CT/병리 등이 섞인 사례는 제외한다. 원문 임상 문맥이 있으면 모든 조건에서 그대로 유지하되 영상 외 추가 사실을 보충하지 않는다. 정답을 새로 만들거나 바꾸지 않는다.

원본 options의 유일성, answer의 단일 대응, label 문자열과의 일치, 실제 영상 파일을 확인한다. metadata가 없다고 filename만으로 서로 다른 영상을 같은 환자의 sequence로 합치지 않는다. 다중 영상은 원 QA의 image_path 목록만 사용한다. 같은 사례를 나타낸다는 근거가 부족한 목록은 공동 입력 해석 대상에서 제외하고 사유를 보존한다.

독립 단위는 확인 가능한 patient/case다. 동일 환자·study·원천 문서와 공유 영상 hash를 이용해 연결 component를 만들고 component당 QA 하나를 hash 순서로 선택한다. source_file이라는 큰 파일명 자체를 환자 ID로 해석하지 않는다. 환자 연결이 없으면 확인 가능한 원천 사례/문서 cluster를 사용하고 환자 독립성을 주장하지 않는다. 그 연결도 불가능하면 결과는 항목 수준 기술통계로 제한하며 CI에 근거한 확대·method 투자 판단을 하지 않는다.

적격 목록과 제외 이유를 출력 전에 잠근다. D에서 실제 이미지를 표시해 MRI 여부, 손상·중복·답변을 직접 노출하는 overlay, 영상–질문 대응을 확인한다. 선택된 E 영상도 동일한 비성능 기준으로 점검하고 출력 전에 제외를 고정한다. 시각 검사 기록에 실제 표시한 파일과 근거를 남긴다. 이것을 전문의 정답 재판독으로 부르지 않는다.

## 2. 동작 확인 D6

서로 다른 사례 cluster 최대 6개를 사용한다. 다중 영상이 있으면 이미지 수와 원천이 다른 사례를 우선 포함하고 가장 긴 적격 입력도 기술 검사에 포함한다. 6개는 정확도 추정용이 아니라 입력 유형·순열·재개·메모리 경로 점검용이다. 작은 적격 집단이면 D를 최대 2개로 줄여 E를 남기며 변경은 출력 전에 기록한다. 적격 사례가 하나뿐이면 그 사례의 기술·탐색 출력만 얻고 집단 비교를 종료한다.

질문과 원본 다섯 선택지를 그대로 사용한다. QA ID와 seed61로 정한 permutation 및 그 역순을 모든 조건에 적용한다. prompt는 제공된 영상과 임상 문맥을 바탕으로 선택하고 마지막 단독 줄을 ANSWER: A|B|C|D|E로 쓰도록 한다. 부분 영상 조건에서도 질문 본문을 다시 작성하지 않는다.

parser는 마지막 비공백 줄의 해당 형식만 허용한다. invalid는 오답 처리하고 비율을 별도 보고한다. cap512에서 시작하며 EOS 없이 cap에 도달한 요청만 동일 입력 cap2048로 한 번 재시도한다. 두 attempt와 비용을 보존한다. D 후 prompt/parser를 잠그며 E 결과로 변경하지 않는다.

GT 역매핑, 입력 tensor, T의 영상 token 부재, J/S_i 집합, 요청 hash, 실제 중단·재개를 검사한다. 기술 gate는 정확도와 독립적이다. 큰 입력의 메모리가 부족하면 batch/worker를 먼저 낮춘다. 일부 영상을 조용히 버리거나 montage로 바꾸지 않는다. 불가피한 미실행은 해당 사례와 비교의 누락으로 보고하고 성공 주장을 제한한다.

## 3. 가능성 탐색 E24

D와 분리한 사례 cluster를 SHA256(seed61, cluster_id)로 정렬한다. 다중 영상 사례가 있으면 그것을 주 분석 집단으로 선택한다. 이미지 수 구간 2, 3–4, 5 이상과 source에 따라 후보를 번갈아 추출해 쉬운 짧은 입력만 선택하지 않는다. 동일 규칙으로 E24와 누적 E64 목록을 출력 전에 함께 잠근다. cluster당 질문 하나를 사용한다.

E24는 큰 실패 유형과 paired 차이를 관찰하는 개발 집단이다. 24 cluster의 이진 정확도는 최악 조건에서 95% 반폭이 약20 pp이므로 작은 효과를 확정할 수 없다. 적격 집단이 부족해도 가용 E를 수행하며 확증 표본 문턱으로 막지 않는다.

다중 영상 적격 사례가 전혀 없지만 단일 영상 진단 사례가 있으면 **T/I 기본 능력 분기**로 E24까지만 수행한다. 이 분기는 영상 신호만 관찰하고 공동 입력 가설은 미검증으로 끝낸다. 질환 QA가 없으면 sequence 식별이나 segmentation+규칙 과제로 자동 전환하지 않는다.

## 4. 조건부 E64 확대

신뢰할 cluster 연결이 있고 기술적으로 유효한 다중 영상 E24를 마친 경우에만 적용한다. V−T 또는 J−T의 점추정치가 0.10 이상이거나, 그 CI 상한이 0.10 이상이고 영상/T 정오가 다른 cluster가 6개 이상이면 E64까지 한 번 확대한다. 또는 V−J나 S_mean−J가 0.10 이상이고 해당 개별 영상 기반 점수가 T보다 높으면 확대한다.

이는 10 pp 규모의 실용적으로 큰 신호·손실을 더 구체화하기 위한 탐색 분기다. 선택지 순서만으로 방향이 뒤집히거나 자료 모호성이 비교를 지배하면 표본 확대하지 않는다. E64의 최악 정확도 반폭도 약12 pp이므로 작은 차이 확증을 보장하지 않는다. 모든 중간·최종 결과와 확대 이유를 함께 보고한다. E64 이후 표본·seed·prompt를 자동 추가하지 않는다.

## 5. 독립 확인

이번 반복은 학습과 독립 확증을 하지 않는다. 배포 split 이름이 test여도 이번 D/E는 연구개발에 사용한 자료로 기록한다. 선택되지 않은 사례는 생성하지 않는다. 후속 설정 선택 후에는 별도 사례·원천의 확인이 필요하며, 기존 MSD/SPIDER/CT reserve를 소비하지 않는다.

## 자원·예상 비용·재개

학습은 없다. 다중 영상 QA의 K개 입력에 대해 두 순서의 요청은 2(K+2)개다. E24/E64와 D의 실제 K를 metadata에서 합산해 본실행 전에 기록한다. V·S_mean·oracle 분석은 저장된 출력만 사용한다. 기술·처리량 반복과 cap 재시도는 별도 집계한다.

실행 직전 nvidia-smi로 GPU 0/1의 실제 UUID·여유를 확인하고 여유가 큰 장치부터 배치한다. 허용 CUDA_VISIBLE_DEVICES 안에서 논리/물리 대응을 확인한다. MedGemma의 기존 8–10 GB는 참고값이며 이번 최대 이미지·출력 길이의 peak를 D에서 측정한다.

두 GPU에 독립 shard를 배정한다. 각 1 worker와 메모리가 허용하는 GPU당 2 worker 또는 batch 확대 중 유망한 구성 하나를 같은 D 요청으로 비교한다. 전체 요청/분, GPU별 실제 점유·peak, 긴 출력 지연, 오류·OOM·CPU/I/O 경합, 출력 정합성을 기록한다. 동시 worker peak와 다른 점유에 worker당 2 GiB 여유를 더해 용량 내일 때만 증설한다. 1 worker 유지 시 실측 근거를 남긴다.

현재 이 자료의 처리량은 미측정이므로 근거 없는 숫자 시간 상한을 두지 않는다. D 후 예상 wall-clock을 다운로드 바이트/전송률 + loading + 조건별 요청량/실측 처리량 + 검증 시간으로 산출하고 E 전에 기록한다. 실제 GPU 시간·token·출력 수와 함께 추정/실측을 구분한다.

요청 ID에는 cluster/QA, 조건, 영상 집합·순서 hash, 선택지 순열, prompt/model/config digest를 포함한다. worker별 append 결과와 원자적 claim/완료 기록을 사용한다. 완료 결과의 source/input/protocol/output hash를 검증하고 미완료만 재개한다. 실패·부분 attempt는 보존한다. 평가에서도 같은 잠금을 검사한다.

# Implementation Tasks for Claude

1. agent/runs/iter_060의 원 계획·리뷰와 이번 계획을 읽고 유지·보류·변경 범위를 보고서에 남긴다. 새 결과는 research/results/iter_061에 저장한다.
2. 공식 annotation과 선택 영상, provenance·이용 조건, 적격/제외 목록과 cluster 연결을 확인한다. 실제 사례 몇 개로 성립 여부를 먼저 판단한다.
3. 지정 msd56_run.py의 선택 함수만 재사용한다. 새 QA adapter·parser·평가가 필요한 이유를 명시하고 보관된 기존 함수를 새로 복제하지 않는다.
4. 영상 누락·GT 순열 오류·중복 cluster·source/request/protocol 변조·기술 gate 실패·중단 재개를 실제 실행 경로에서 검사한다. 무관한 범용 리팩터링은 하지 않는다.
5. D의 실제 표시·tensor·출력·메모리·처리량을 확인한 뒤 설정과 E 목록을 잠근다. E24 및 사전 조건에 따른 E64를 실행한다.
6. 원시 답변에서 별도 집계로 T/J/S_mean/V와 paired 차이를 재계산한다. 누락·중복·invalid·cap·비용을 포함한다.
7. 보고서에서 자료 준비, 실행 유효성, 모델 관찰, 방법 필요성, 신규 기여를 구분한다. 자료 실패 시 실제 오류와 재개에 필요한 새 근거를 남기고 다른 데이터셋 조회로 연장하지 않는다.

# Evaluation (성공/실패 기준 포함)

주지표는 cluster당 선택된 QA의 두 순서 정확도를 평균한 뒤 cluster 간 평균한 accuracy다. S_mean은 각 순서에서 모든 S_i 정확도를 평균한다. J−T, V−T, J−V, J−S_mean을 모두 보고한다. cluster 연결이 확인되면 seed61, 10,000회 paired cluster bootstrap 95% CI를 계산한다. 순서별 정확도·정답 문자열 불일치, source·이미지 수별 기술통계, invalid/EOS 비율을 함께 제시한다. 다중 비교와 조건부 확대를 포함한 개발 탐색이지 확증 검정이 아니다.

- **영상 기본 신호:** J−T 또는 V−T가 10 pp 이상이고 해당 CI 하한이 0보다 크면 큰 영상 신호의 제한적 양성 관찰로 본다. 두 비교를 모두 공개한다.
- **공동 입력 손실:** V−J 또는 S_mean−J가 10 pp 이상, CI 하한>0, 두 선택지 순서에서 방향이 같고 해당 개별 기반 점수가 T보다 높으면 공동 입력 손실 후보로 기록한다. 이 기준은 내부 원인이나 method 승인을 자동 확정하지 않는다.
- **공동 입력 이득:** J−V가 10 pp 이상, CI 하한>0이고 영상 기본 신호도 있으면 단순 집계 이상의 이득으로 보존한다. 남은 중요한 실패가 없으면 추가 손실 탐색은 종료한다.
- **단순 대안:** V가 J보다 충분히 정확해도 K회 비용을 함께 평가한다. V−J가 최소 5 pp이며 비용 증가가 없을 때만 실용적 우위로 표현한다. 비용 증가가 있으면 정확도–비용 trade-off다. J−V의 CI 상한이 5 pp 미만이면 큰 공동 정확도 이점이 지지되지 않는다고 보고하되 V의 비용 충분성과 혼동하지 않는다.
- **음성:** 영상 신호의 CI 상한이 10 pp 미만이면 현재 과제·입력에서 큰 추가 영상 신호가 약하다는 근거다. 모델 무능력 전체나 영상 무사용으로 확대하지 않는다. MedGemma 통합 방법 투자는 보류하고 같은 고정 자료의 다른 모델 비교 가치를 다음 리뷰에서 판단한다.
- **불확정:** E64 또는 가용 집단 소진 뒤에도 기준을 구분하지 못하면 현재 후보의 투자를 보류한다. 추가 표본·prompt·seed는 자동 승인하지 않는다. 정답/cluster 불확실성은 그 한계를 기록하며 CI 수치로 덮지 않는다.

비용은 입력 읽기→processor→생성→답변 저장의 monotonic wall과 GPU별 실행 시간, token·호출 수로 계산하고 loading을 분리한다. V는 모든 S_i 비용을 합산한다. 병렬 wall을 device 시간으로 오표기하지 않는다. 별도 timing 캠페인은 만들지 않는다.

자료/GT/tensor/누수 오류는 해당 비교의 execution_failed다. 올바른 입력에서 오답·형식 오류는 성능 관찰로 남긴다. 사후 annotation 문제는 원점수를 보존하고 별도 민감도 분석으로만 제시한다. 자료 준비와 테스트 통과만으로 valid_experiment=true를 부여하지 않는다.

# Risks / Checks

- 공개 benchmark의 정답은 독립 임상 gold와 같지 않다. 질환 진단의 모호성·교육용 key image 선택을 기록한다.
- 환자/문서 연결과 pretrained exposure는 완전히 확인되지 않을 수 있다. 확인 범위보다 넓은 독립성·일반화를 주장하지 않는다.
- MRI metadata 목록이 영상별 sequence를 보장하지 않는다. 이번에는 확인되지 않은 sequence routing을 만들지 않는다.
- 질문에 다중 패널 참조가 있으면 S_i의 부분 관측으로 표시한다. 없는 panel을 조작하거나 질문을 유리하게 다시 쓰지 않는다.
- 입력 영상 수, token, 반복 질문 비용이 다르므로 J/S/V 차이를 순수한 융합 기전으로 해석하지 않는다.
- 공식 loader의 누락 영상 fallback을 사용하지 않는다. 전체 모델·평가기 설치도 필요 없이 선택된 경로만 구성한다.
- 격리 환경이 필요하면 설치 경로·버전·checkpoint 출처와 작은 실제 입력 검증을 기록한다. 기본 medgemma 환경과 hf_cache는 변경하지 않는다.

## 대규모 GPU 필요 후보

다중 sequence/3D 시각 encoder와 언어 모델의 공동 사전학습, 다양한 질환·기관의 근거 정합성 학습은 장기 후보로 보존한다. 현재 관찰 전에는 필요성·신규성을 주장하지 않는다. 이번 두 GPU에서는 먼저 정상 사용의 실제 신호와 단순 대안 이후의 잔여 문제를 확인한다.

# 계획의 근거 (GPT 조사 노트)

## 새로 확인한 것

- iter_060의 plan.md, review.md/review.json, claude_report.md를 읽었다. QA 미확보로 D/E 및 GPU 출력이 전혀 없었으며, 모델·routing 가설은 미판정이다. iter_059 review.md의 전문 대안 채택과 구간 판정 투자 보류를 유지한다.
- UCSF-PDGM-VQA 검색에서 원 annotation 접근을 회복할 새로운 공식 배포 근거를 확보하지 못했다. 기존 실패 endpoint는 반복 조회하지 않았다. 검색에 나온 3-study VQA demo 영상은 원 QA 대체 근거로 채택하지 않았다.
- [OmniBrainBench 공식 저장소](https://github.com/CUHK-AIM-Group/OmniBrainBench)는 공식 Hugging Face 배포를 연결한다. [파일 목록](https://huggingface.co/datasets/FrankPN/OmniBrainBench/tree/main)에서 closed-ended-qa_6823.json 약 4.98 MB, closed-ended-qa_6823.zip 약 734 MB를 확인했다. 이는 실제 압축 해제·영상 연결 검증 완료를 뜻하지 않는다.
- [공식 viewer](https://huggingface.co/datasets/FrankPN/OmniBrainBench)의 실제 행에는 id/question/image_path/options/answer/source_file/modality_type이 있고, sub-/ses- 이름을 사용하는 예시가 있다. 그 예시만으로 다른 source의 환자 연결을 보장하지 않는다. 공개 JSON 본문과 영상은 이번 계획에서 열지 못했다. 로컬 읽기 전용 HTTP 조회는 DNS 오류였고 web의 raw 접근도 실패했다.
- [공식 loader](https://raw.githubusercontent.com/CUHK-AIM-Group/OmniBrainBench/master/utils/OmniBrainBench/OmniBrainBench.py)는 image_path 문자열·목록과 5-choice QA를 지원한다. 영상 읽기 실패를 건너뛰거나 text-only로 바꾸는 경로가 있어 그대로 사용하면 안 된다.
- [논문 §4.5 및 Appendix A](https://arxiv.org/html/2511.00846v2)는 영상 개수별 평가와 CC BY-SA 4.0을 기술하지만 배포 card는 CC BY-SA 3.0이다. 두 공개 조건의 차이를 기록하고 원천별 조건도 확인한다. 논문 집계는 이번 paired 개입의 결과가 아니다.

## 기존 자산과 판단

GOAL, LIMITATIONS의 MRI 항목, CODE_ASSETS의 iter_059/060 항목과 실제 msd56_run.py를 확인했다. research HEAD는 adfbb52dd9cd838e203e9baa14a3c8cc184e4153이며 status/diff 출력은 비어 있었다. loader·generate 함수는 자체적인 외부 패키지 의존성을 사용하지만 전체 runner는 MSD 경로에 고정돼 있다. 새 adapter만 연결하고 그 경로의 필수 검사만 보완한다.

현재 MRI QA에 연결할 observed/validated limitation은 없다. SPIDER의 reference 좌표 관찰은 이번 질환 QA의 한계 근거로 사용하지 않는다. 실제 출력 diagnostic이 먼저다.

## 의미·한계

자료와 정답이 달라지므로 iter_060의 T/U/R 기준을 조용히 변경하는 복구가 아니다. UCSF sequence 배분은 보류하고 동일 track 안에서 공동 영상 근거 사용을 별도 비교한다. 원시 annotation·사례 연결의 미확인은 구현 단계 한정 검사로 남기며, 통과하면 같은 호출에서 실제 출력을 얻는다. 논문 추천 대상이 되는 긍정적 실험 근거는 아직 없다.
