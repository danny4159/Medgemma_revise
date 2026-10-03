# 요약

- **이번에 할 일:** 적격 MRI QA 21개에서 Qwen2.5-VL-7B의 T/J/S_i를 실행하고 기존 MedGemma 출력과 비교한다.
- **필요한 이유:** 직전 결과는 공동 입력 손실을 지지하지 않았다. 같은 과제에서 모델 특이성과 질문 조건을 먼저 구분해야 한다.
- **확인할 기준:** 모델별 영상 추가 효과, 모델 간 효과 차이, 단순 투표 대비 공동 입력 변화다.
- **주의·다음:** 개발 자료의 한정 비교다. 모델 교체 가치와 최소 개입 필요성을 구분하고, 결합 능력이나 신규 기여를 미리 주장하지 않는다.

# Current Understanding

기준 문서는 agent/runs/iter_061/plan.md이며 SHA256은 `e310aa2f05e57d0ea53062b2dffda860b7444223e774259ee3436a9e3ab9afcc`다. 원 계획·출력·음성 판정은 보존한다. 이번 계획은 동일 접근법의 적격성 정정과 타 계열 비교를 추가하는 별도 진단이다.

원 E24에서 T 0.500, J/V 0.4375였다. 영상 추가 효과와 공동 손실은 지지되지 않았다. 질문에 소견이 이미 포함된 경우가 많아 기본 인식 부족, 텍스트 정보 충분성, 부분 관측의 정보 부족을 분리하지 못했다.

**유지:** MRI 우선, 기존 질문·선택지·영상·두 선택지 순서·정답, cluster 연결과 개발 자료 지위, 이전 결과·reserve.

**변경:** 원 제외 규칙을 적용한 E21을 별도 분석하고 Qwen2.5-VL-7B-Instruct 한 모델을 추가한다. 원 E64 확대 규칙을 이번 모델에 자동 승계하지 않는다.

**미완료:** 타 모델 공식 입력 검증, 현재 경로의 provenance·재개 결함 보완, 모델 간 paired 비교다. UCSF routing·MSD 추가 적응·OCT 전환은 계속 보류한다.

# Strategy Check / 연구 방향 판단

상위 질문은 여러 관측에서 필요한 근거를 선택하고 결합하는 능력이다. 직전 결과는 인식·선택·결합 중 어느 실패도 확정하지 못했다. 이번에는 **영상 추가 효과의 부족이 모델에 특이한가** 하나를 좁힌다.

- 관찰: MedGemma의 큰 추가 영상 신호와 공동 손실이 지지되지 않았다.
- 남은 설명: 모델 적합성 차이, 질문의 풍부한 소견, 배포 영상의 정보 부족이다.
- 최소 대조: 같은 E21에서 타 계열 T/J/S_i와 기존 MedGemma를 비교한다.
- 결정 변화: 타 모델만 영상 신호를 보이면 모델 교체를 우선한다. 모두 약하면 현재 key-image 과제의 추가 통합 방법 투자를 종료·보류한다.

현재 방법 개선은 실제 공동 손실 근거가 없어 후순위다. 새 데이터 전환은 모델 특이성을 남긴 채 접근·정답 확인 비용을 다시 지불한다. 따라서 기존 자료의 한정 비교를 선택한다. 타 모델 비교를 method pilot의 새 보편적 hard gate로 만들지는 않는다.

Qwen2.5-VL-7B는 공식 다중 영상 경로와 자원 적합성을 고려한 비교 모델이다. 최신 최고 성능이나 의료 전문성은 가정하지 않는다. 이번 목적은 모델 순위표가 아니다.

mri-volume-evidence-use의 iter_056~061 이력을 유지한다. iter_061 E24 생성 실측은 81.31분이다. 전체 준비·감사·GPU 비용의 지배 항목은 합산 기록이 없어 단정하지 않는다. 이번에는 기존 입력·출력을 재사용하고 새 모델 adapter 및 실제 사용 경로의 결함만 수정한다.

# Hypothesis

H1: Qwen에서 영상 추가 효과가 나타나고 MedGemma보다 크다면, 직전 음성 결과의 모델 특이성이 지지된다.

H2: 두 모델의 추가 효과가 모두 약하면 현재 질문·key image 조건에서 모델 교체만으로 연구 가능한 영상 근거 신호를 얻기 어렵다. 이것만으로 텍스트가 충분한지, 영상이 부족한지, 두 모델의 인식이 부족한지는 확정하지 않는다.

S_i는 제한 관측 조건이다. S_i의 오답은 해당 영상에 정답 근거가 충분하다는 증거 없이는 인식 실패로 부르지 않는다. V−J 차이는 공동 입력 유지 문제의 후보이며 복수 근거 결합 실패의 증명이 아니다.

# Limitation Evidence / Correct Usage Checks

iter_061은 valid_experiment=true, blocking_issues=[]지만 새로운 모델 한계를 등록하지 않았다. 관련 LIMITATIONS의 SPIDER 관찰은 별도 과제이므로 이번 method 근거로 사용하지 않는다. `limitation_ids=[]`, diagnostic/none을 유지한다.

Qwen은 [공식 model card](https://huggingface.co/Qwen/Qwen2.5-VL-7B-Instruct)의 Qwen2_5_VLForConditionalGeneration, AutoProcessor, process_vision_info 경로를 따른다. checkpoint·processor revision과 package 버전을 고정한다. bf16, greedy, 기본 processor 해상도를 우선 사용하며 양자화하지 않는다. 모델별 chat template의 차이는 기록한다.

같은 PNG/RGB, 동일 영상 순서·질문·선택지를 사용한다. J에서 영상을 버리거나 montage로 바꾸지 않는다. T에는 영상 token이 없어야 한다. 두 순서의 input_ids, pixel_values, image_grid_thw 및 영상 연결을 공식 직접 호출과 adapter에서 대조한다. 정답·caption·source·파일명은 모델 메시지에 넣지 않는다.

실제 영상 오류가 새로 확인되면 해당 사례를 별도 제외·누락으로 기록하고 공통 집합을 명시한다. 성능 때문에 제외하거나 대체 사례를 채우지 않는다. 모델 오답과 형식 오류는 기술 gate 실패가 아니다.

# Contribution Path / Baselines / Reuse

가장 가까운 선행은 [OmniBrainBench](https://arxiv.org/html/2511.00846v2)의 VLM 평가와 개별 추론 후 late voting이다. 이번 연구 가치는 새로운 점수표가 아니라 다음 기준 모델과 방법 투자 여부를 결정하는 데 있다. 신규 contribution은 미확정이다.

공통 조건은 다음과 같다.

- T: 원 질문과 선택지만 제공한다.
- J: 연결된 모든 영상을 원 순서로 제공한다.
- S_i: 같은 질문에 영상 하나씩 제공한다.
- V: 유효 S_i의 plurality vote. 동률은 원 선택지 문자열 SHA256 순서이며 모두 invalid면 오답이다.
- S_mean: 개별 영상 정확도의 평균이다.

기존 MedGemma E24에서 같은 E21의 232응답을 재사용한다. 재생성하지 않는다. Qwen에도 동일 조건을 모두 실행해 J의 약한 신호가 개별 입력에서도 같은지 확인한다. GT best-single·any-correct는 사후 oracle 기술통계이며 방법이나 성공 기준이 아니다.

Qwen 7B와 MedGemma 4B의 크기·학습·시각 token·해상도 차이를 기록한다. 모델 간 차이를 구조의 인과 효과로 해석하지 않는다. 직접 SFT와 전문 모듈은 이번 미학습 모델 적합성 비교의 필수 조건은 아니지만, 큰 방법 투자 전에는 실제 과제에 맞는 강한 비교가 필요하다.

현재 branch의 HEAD `84f865b7aa2a8e07d2f5f0e10cf6b7c99ec5080b`에 필요한 파일이 모두 있고 작업 트리는 깨끗하다. 동일 approach branch를 유지하므로 reuse_assets는 비운다.

- `mri61_spec.py`, `mri61_parse.py`: 승인된 prompt·순열·역매핑·parser 범위를 재사용한다.
- `mri61_data.py`, `mri61_explore.py`, `mri61_sheet.py`: 기존 source·cluster·영상 연결을 재사용한다. 원본 생성 경로를 다시 돌려 덮어쓰지 말고 이번 선택 manifest를 별도로 만든다.
- `mri61_run.py`, `mri61_eval.py`, `mri61_test.py`: 잠금·완료 검증·재개·비용 경계의 needs_fix를 현재 실행 경로에서 수정한다.
- `msd56_run.py`: 기존 MedGemma 출력 provenance 확인에 필요한 범위만 사용한다. Qwen에 MedGemma 전용 입력 함수를 적용하지 않는다.

# Proposed Experiment

## 1. 한정 적격성 정정

원 E24의 QA 2322, 1419, 2033을 제외한다. 각각 intervention/전후 변화, 수술 후 재발의 longitudinal 관측, 비뇌 부비동 진단에 해당한다. 나머지 21 cluster를 고정하고 대체 표본을 채우지 않는다. 원 E24 수치와 원 리뷰의 민감도 분석은 보존한다.

원 annotation, 기존 labels, 영상 hash, cluster 연결을 대조해 `results/iter_062/`에 원본 참조와 제외 이유를 잠근다. 기존 PNG·원 annotation은 읽기 전용 재사용한다. 이는 MedGemma 결과를 본 뒤의 정정이므로 독립 검증이라고 부르지 않는다.

질문 내용에 따른 보조 분류도 Qwen 출력 전에 잠근다. 소견 미서술군은 QA 1552, 1513, 1475, 1451, 1596, 1416의 6개이고 나머지 15개는 소견 서술군이다. 전체 E21이 주분석이다. 이 분류는 영상 필요성의 정답이나 source 효과의 인과 대조가 아니며, 하위집단만 선택해 성공을 선언하지 않는다.

## 2. 환경과 동작 확인

승인된 격리 환경과 별도 모델 캐시를 사용한다. 기본 medgemma 환경과 hf_cache를 수정하지 않는다. 디스크·CUDA/PyTorch 호환성, 공식 의존성, 모델 이용 조건을 확인하고 환경 Python 절대경로·설치 명령·버전·revision을 보존한다. 실제 학습 데이터 중복이 확인되지 않으면 미확인으로 명시한다.

기존 D의 QA 694, 1518, 1253을 사용한다. 각각 영상 4·4·3개이며 T/J/S_i 두 순서 합계 34요청이다. 이는 성능 선택용이 아니라 입력·형식·메모리·재개 경로 확인용이다. E의 최대 K=5 입력은 잠근 설정으로 첫 실행할 때 peak를 별도 확인한다.

기존 prompt, seed61의 순열과 역순, mri61_parse.parse_v2 및 strict v1 보조 보고를 유지한다. cap512에서 시작하고 EOS 없이 cap 도달 시 동일 입력 cap2048로 한 번 재시도한다. 최종 attempt를 점수화하고 모든 attempt와 비용을 보존한다. D에서 정확도가 낮아도 기술적으로 유효하면 E를 실행한다. 새 parser·prompt 탐색은 하지 않는다.

## 3. 가능성 탐색 E21

고정 21 cluster, 영상 수 합 74개에 신규 Qwen 요청 232건을 실행한다. T/J는 84건, S_i는 148건이다. 추가 학습·seed·선택지 순서·영상 순서 실험은 없다. V/S_mean은 저장 출력에서 계산한다.

기존 MedGemma 232응답과 Qwen 232응답을 동일 선택 manifest로 평가한다. 누락·실패는 전체 분모에서 숨기지 않고 모델별 성공 실행 범위와 공통 paired 집합을 모두 보고한다. 기술 오류 복구 외에 좋은 결과가 나올 때까지 재생성하지 않는다.

## 4. 규모 확대와 독립 확인

이번에는 E64를 열지 않는다. 비교의 목적이 이미 출력된 동일 사례에서 모델 선택의 근거를 얻는 것이므로 고정 E21을 완료하는 것이 본실행이다. 불확정이라는 이유만으로 표본을 추가하지 않는다.

양성 결과가 있어도 model full 또는 confirmatory로 자동 전환하지 않는다. 다음 리뷰에서 효과 크기·불확실성·단순 대안·중요성을 검토하고 필요한 별도 표본·학습을 계획한다. 이번 D/E는 모두 개발 자료이며 기존 reserve를 사용하지 않는다.

## 자원·비용·재개

실행 직전 nvidia-smi로 허용 GPU 0/1의 UUID와 여유 메모리를 확인하고 여유가 큰 장치부터 배정한다. Qwen bf16 weight만 약14~16GB 수준으로 예상하며 activation·KV를 포함한 peak는 미측정이다. D 실측 peak에 worker당 2GiB 여유와 다른 프로세스 점유를 더해 배치한다.

기본 후보는 GPU당 한 Qwen worker다. bf16 모델 두 복제본은 24GB 한 장에 들어가기 어려우므로 GPU당 2 worker를 숫자상 강제하지 않는다. 대신 D에서 batch1과 메모리가 허용되는 batch2를 짧게 비교한다. 처리량·긴 출력 지연·GPU 전체 peak·OOM·출력 정합성을 확인하고 성능 점수가 아닌 처리량으로 선택한다. batch2가 불리하거나 여유가 부족하면 한 worker/batch1 근거를 기록한다. 동일 입력을 감당하지 못하면 영상 축소보다 메모리 효율적인 공식 attention 경로와 두 장 분할 로딩을 먼저 검토하고 비용을 기록한다. 임의 양자화·영상 누락은 하지 않는다.

원 MedGemma E24의 264요청/81.31분을 선형 환산한 E21 참고값은 약71.45분이다. 모델이 달라 Qwen 예측값으로 쓰지 않는다. D 이후 T/J/S별 처리량과 실제 요청량, loading·다운로드·검증 시간을 사용해 예상 wall-clock을 본실행 전에 남긴다. 임의 시간 상한은 없다.

요청 ID와 protocol에는 model/processor revision, 코드·prompt·parser·labels·선택 manifest·원 annotation·영상 hash·generation 설정을 연결한다. 평가 진입과 재개에서도 검증한다. 기존 rid만으로 완료 처리하지 않는다.

동시 launcher를 차단하고 요청 claim을 원자적으로 관리한다. worker별 출력과 완료 digest를 사용하며 worker 수가 바뀌어도 중복/누락이 없어야 한다. 실행 중 강제 중단과 기록 경계의 손상을 기술 요청에서 검사한다. 손상 원본은 보존하고 검증된 미완료 요청만 재개한다.

새 timing은 입력 읽기부터 답변 flush/fsync 완료까지 측정하고 비용 기록을 별도 sidecar에 남긴다. loading, 각 attempt 입력·출력 token, 재시도 비용을 구분한다. 기존 MedGemma timing은 저장 이전 종료라는 한계를 유지하며 새 Qwen 전체 비용과 직접 우위 비율을 만들지 않는다. Qwen 내부 J/V 비용은 같은 경계로 비교할 수 있다.

# Implementation Tasks for Claude

1. 기준 plan·review.json과 현재 SHA를 확인하고 유지/변경/미완료를 보고한다. 결과는 `research/results/iter_062/`에만 작성한다.
2. E21 및 질문 서술군 manifest를 고정하고 기존 MedGemma 원시 출력의 적격성 정정 결과를 별도로 계산한다.
3. 공식 Qwen 환경·checkpoint를 확보하고 선택된 mri61 실행기에 모델 adapter를 연결한다. 자료·평가기 전체를 새로 복제하지 않는다.
4. 실제 실행·평가 경로의 protocol, labels/parser 잠금, 완료 검증, launcher/claim 및 저장 포함 timing을 보완한다.
5. source/image/protocol/labels/parser 변조가 평가·재개에서 차단되는지, 실제 중단 복구 후 중복·누락이 없는지 검사한다. 기존 E24의 불변 provenance와 점수는 회귀 검사로 보존한다.
6. D34 및 처리량 비교를 수행하고 설정을 잠근 뒤 E232를 완료한다. 자료·기술 blocker가 있으면 오류·시도·남은 조건을 기록하고 종료한다.
7. 원시 답변에서 독립 집계 경로로 정확도·paired 차이·투표·CI·invalid·cap·비용을 재계산한다. 형식 오류를 내용 오류와 분리해 보고한다.
8. 모델 선택, 공동 손실 후보, 방법 필요성, 기여를 구분해 다음 투자 하나를 권고한다.

원 D protocol의 코드 불일치는 그대로 기록한다. 원 D 생성을 새 기능 검증 근거로 사용하지 않고 이번 D를 새로 수행하므로 과거 D 재구성을 별도 정비 과제로 확대하지 않는다.

# Evaluation (성공/실패 기준 포함)

주지표는 cluster별 두 순서 정확도의 평균을 다시 cluster 간 평균한 accuracy다. 모델별 T/J/S_mean/V, J−T, V−T, V−J, S_mean−J를 보고한다. seed61·10,000회 paired cluster bootstrap으로 95% CI를 구한다. 동일 bootstrap 표본으로 모델 간 `(J−T)_Qwen−(J−T)_MedGemma`와 `(V−T)_Qwen−(V−T)_MedGemma`도 계산한다. 한 모델만 유의하고 다른 모델이 비유의하다는 사실을 모델 차이로 대신하지 않는다.

기존 10 pp 기준은 작은 집단에서 후속 투자를 고려할 큰 신호의 기준으로 유지한다. 확증 검정이 아니라 개발 탐색이며 모든 비교와 두 순서의 방향을 공개한다.

- **모델 특이성 양성:** Qwen의 J−T 또는 V−T가 10 pp 이상이고 CI 하한>0이며, 대응하는 모델 간 효과 차이도 양수이고 CI 하한>0이면 제한된 모델 특이성 근거로 기록한다. 기준 미달은 효과 없음으로 바꾸지 않는다. Qwen J와 T가 함께 좋아지는 경우는 기본 과제 적합성 향상이며 영상 효과와 구분한다.
- **공동 손실 후보:** 같은 모델에서 V−J 또는 S_mean−J가 10 pp 이상, CI 하한>0, 두 순서에서 방향 일치, 해당 개별 기반 점수가 T보다 높을 때 후보로 기록한다. 모델 정오답으로 단독 충분 집단을 만든 분석은 사후 탐색이다. 선택·결합의 원인 확정이나 method 승인은 아니다.
- **단순 대안:** Qwen V−J가 5 pp 이상이고 동일 경계 비용 증가가 없을 때만 실용적 우위로 표현한다. 비용 증가가 있으면 trade-off로 보고한다. 중요한 잔여 문제가 없으면 새 방법 투자를 종료한다.
- **음성:** 두 모델에서 J−T와 V−T의 CI 상한이 모두 10 pp 미만이면 현재 질문·key-image 조건의 큰 추가 영상 신호에 대한 음성 근거다. 이 과제의 통합 방법 투자를 종료한다.
- **불확정:** 위 분기를 구분하지 못하면 모델 선택과 방법 투자를 보류한다. E64·새 prompt·세 번째 모델을 자동 발주하지 않는다. 추가 연구에는 이번에 빠진 어떤 증거가 결정을 바꾸는지 별도 근거가 필요하다.

소견 서술 15개/미서술 6개의 결과는 보조 기술통계로 모두 공개한다. 작은 하위집단의 결과만으로 모델 교체·방법 개발을 확정하지 않는다. 순서별 accuracy, 원 선택지 답변 불일치, invalid, EOS, cap, source와 K별 결과를 함께 제시한다.

자료·GT·tensor·출력 연결 오류는 해당 비교의 execution_failed다. 유효한 형식 오류나 오답은 성능 관찰이며 원문을 보존한다. 높은 invalid 비율이 차이를 설명하면 시각 능력 해석을 보류하고 이번 반복에서 parser를 유리하게 바꾸지 않는다.

# Risks / Checks

- 기존 E24를 본 뒤 정의한 정정 집합이며 독립 확인이 아니다. 원 결과와 별도 표로 보고한다.
- PubMedVision의 문서 cluster는 환자 독립성을 보장하지 않는다. 사전학습 노출도 미확인이다.
- 소견 서술 여부와 source가 겹치므로 질문 텍스트의 인과 효과를 주장할 수 없다.
- 복수 영상 필요성을 보장하는 주석이 없다. 공동/개별 정확도 차이를 결합 능력으로 이름 붙이지 않는다.
- 모델별 공식 processor 차이와 모델 크기는 공정한 실제 사용 비교의 차이로 공개하며 순수 구조 효과로 해석하지 않는다.
- 과거 검증의 불변 조건은 재사용하되 새 Qwen 입력·출력은 새로 검증한다. 무관한 MSD 경로·과거 전체 runner를 정비하지 않는다.

## 대규모 GPU 필요 후보

MRI의 다중 sequence·volume encoder와 언어 모델을 공동 적응하고 근거 역할을 학습하는 방향은 장기 후보로 남긴다. 대규모 annotation·기관 다양성·전체 모델 학습 비용이 필요할 수 있다. 현재 결과만으로 그 필요성이나 신규성을 주장하지 않으며 이번에는 두 GPU에서 모델 적합성 비교를 마친다.

# 계획의 근거 (GPT 조사 노트)

## 확인한 근거

- agent/GOAL.md, iter_061의 plan.md·review.md·review.json·claude_report.md, CODE_ASSETS.md의 관련 항목, LIMITATIONS.md의 MRI 항목과 실제 mri61 소스를 확인했다.
- 기준 plan SHA256은 e310aa2f05e57d0ea53062b2dffda860b7444223e774259ee3436a9e3ab9afcc다. research HEAD는 84f865b7aa2a8e07d2f5f0e10cf6b7c99ec5080b이고 status/diff는 비어 있었다.
- 원 리뷰의 E24는 T 0.500, J/V 0.4375이며 J−T의 95% CI는 [−0.208333, 0.0625]다. 공동 손실과 중요한 모델 결함은 등록되지 않았다.
- 원 질문 24개를 읽었다. QA 2322는 intervention과 전후 변화, 1419는 수술 및 재발의 시간 경과, 2033은 부비동 진단이므로 이번 brain MRI 진단 비교에서 제외한다. 나머지 21 cluster는 기존 요청 232건, 영상 수 합 74개다. 선택된 영상의 최대 크기는 480×480이다.
- 원문에 영상 소견이 없는 질문은 QA 1552, 1513, 1475, 1451, 1596, 1416의 6개다. 이는 질문 내용에 따른 분류이며 영상이 반드시 필요하다는 정답 주석은 아니다. 전체 21개를 주분석으로 유지한다.
- [Qwen2.5-VL-7B 공식 model card](https://huggingface.co/Qwen/Qwen2.5-VL-7B-Instruct)에서 Apache-2.0, 공식 Transformers·qwen_vl_utils 입력 경로와 다중 영상 지원을 확인했다. 기본 processor를 우선 사용한다. MRI 성능이나 학습 데이터 비중복은 이 자료로 확인되지 않았다.
- [OmniBrainBench 논문](https://arxiv.org/html/2511.00846v2)은 가까운 benchmark 선행이다. 기존 문항별 평가가 이번 동일 사례의 모델 내 T/J/S 비교를 대신하지는 않는다.

## 판단

공동 손실을 전제로 한 학습보다 타 계열 하나의 같은 대조가 정보 가치가 높다. 기존 자료·MedGemma 출력을 사용하므로 새 데이터 접근과 전수 감사 비용을 피할 수 있다. Qwen2.5-VL-7B는 공식 다중 영상 경로와 두 24GB GPU 내 bf16 실행 가능성을 우선한 선택이며 최신 최고 성능 모델이라는 주장은 하지 않는다. 실제 실행 가능성은 D에서 측정한다.

SPIDER reference-interface 관찰은 다른 과제이므로 limitation_ids에 연결하지 않는다. 이번 비교는 diagnostic이며 method gate를 충족했다고 가정하지 않는다.
