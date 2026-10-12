# 요약

- 이번에 할 일: MedRegA의 공식 영역 식별 입력을 이용해 예측 box의 오류 검토 신호를 측정한다.
- 필요한 이유: iter_111의 전역 존재 규칙은 confidence보다 오류를 적게 찾았다. 직접 영역 입력의 가치는 아직 검증하지 않았다.
- 확인할 기준: 같은 box·검토량에서 confidence와 전체 영역 대조보다 공개 주석 불일치를 더 포착하는지 본다.
- 주의·다음: 40B 모델의 실행 적합성과 scoring 경로를 먼저 확인한다. 성립하지 않으면 생성 확대 없이 종료하며, 양성이어도 독립 확인은 다음 승인 대상이다.

## 알림 맥락

- 연구: 위치 근거의 오류 검토
- 데이터: 흉부 X-ray RSNA, 기존 confirm800 중 E600 밖 개발 환자
- 모델: MedRegA frozen, detector17 저장 출력; 신규 학습 없음
- 과제: 영상과 예측 영역을 받아 고정 소견의 likelihood를 계산하고 검토 우선순위를 비교
- 가설: 영역 조건화가 전역 존재 판단과 confidence에 없는 위치 오류 정보를 제공할 수 있음
- 질문: 모델이 제시된 영역을 읽으면 검출기의 확신도만 볼 때 놓치는 오류를 더 찾을 수 있는가?
- 변경: 구체화
- 연결: 전역 존재 규칙의 음성을 받아들이고 실제 영역 입력을 사용하는 별도 후보로 이동
- 작업: 입력·실행 적합성 확인 후 고정된 작은 개발 비교로 후속 투자 여부 판단

# Current Understanding

iter_111의 41명 검토에서 오류 포착 30 대 confidence 38이라는 음성 결과를 유지한다. unresolved 배정에도 방향이 유지됐다. 같은 E600의 threshold·검토율·순위 최적화는 종료한다.

이번 자료는 confirm800에서 E600을 제외한 200명이다. 저장 detector 출력상 152명이 threshold0.70 이상 예측을 가지며 box는 258개다. 과거 분석에 사용된 개발 자료로 명시한다. 새 환자 집합이라는 이유로 독립 도메인이나 미노출 test로 부르지 않는다.

# Strategy Check / 연구 방향 판단

직전 선택과 사용자 승인을 유지하므로 전체 후보를 다시 조사하지 않는다. 공식 영역 식별과 독립 재-grounding 중 전자를 선택한다. 후자는 경계 일치 대조로 의미가 있지만 현재 내용 신호의 존재 여부부터 확인하는 비용이 더 작다.

기술 질문 → 소견은 존재해도 예측 box가 공개 주석과 어긋나는 조건 → 같은 예측 box의 confidence·영역 likelihood·전체 영역 likelihood 검토 순위 → 해당 모델·자료·고정 신호의 오류 검토 가치로 주장 범위를 한정한다.

시험 설정은 MedRegA frozen의 고정 문자열 scoring이다. 연구 관찰은 iter_111 음성 유지이며 새 영역 효과는 미확인이다. 연구 질문은 내용 식별 신호가 위치 검토에 추가 정보를 주는가다. 새로운 학습·loss·모델 순위 자체는 기여가 아니다.

지배 비용은 40B 모델 확보·적재와 inference일 가능성이 있으나 아직 미측정이다. MedP-CLIP은 공식 실행 자산을 확인하지 못해 이번 비교에서 보류한다. 이를 모델 부적합의 과학적 근거로 쓰지 않는다.

# Hypothesis

공식 Region-to-Text Identification 문맥에서 예측 영역에 대한 `lung opacity`의 likelihood가 낮을수록 annotation 불일치 위험이 높을 수 있다. 같은 영상의 전체 영역 likelihood보다 유용해야 영역 조건화의 추가 가치가 남는다.

소견 식별과 경계 정확성은 다르다. 주석과 IoU가 낮아도 실제 소견 일부를 포함할 수 있으며, 이때 높은 likelihood는 임상 오류로 판정하지 않는다.

# Limitation Evidence / Correct Usage Checks

연결 한계는 `rsna-global-presence-location-verification`이다. 원 근거는 iter_111 review.json이며 유효한 음성 진단이다. 이번 모델의 한계를 validated로 가정하지 않는다.

MedRegA 공식 demo의 영역 식별 prompt와 `<ref>/<box>` 형식을 보존한다. modality만 chest X-ray로 바꾸고 좌표는 원 영상 xyxy를 0–999로 변환한다. GT나 detector confidence는 prompt에 넣지 않는다. `lung opacity`는 모든 요청에 동일하게 scoring할 후보 문자열이며 환자별 정답 제공이 아니다.

공식 생성 능력을 사용하는 것과 teacher-forced likelihood 확장은 구분한다. 모델이 직접 box 정확성 확률을 출력한다고 서술하지 않는다. [공식 입력 예제](https://raw.githubusercontent.com/xmed-lab/MedRegA/main/demo_data/data_file.jsonl), [공식 실행 코드](https://raw.githubusercontent.com/xmed-lab/MedRegA/main/src/demo.py)를 고정 revision으로 확보한다.

# Contribution Path / Baselines / Reuse

필수 비교는 detector confidence, 영역 likelihood, 전체 영역 likelihood다. 직접 위치 재생성이 없으므로 재-grounding을 필수 추가하지 않는다. 구현 중 생성 좌표를 위험 점수로 전환하지 않는다.

영역 조건은 후보 좌표를 제공받는 정보 차이가 있다. 전체 영역 대조는 동일 prompt에서 box만 [0,0,999,999]로 바꾼다. 후보 영역 밖 정보를 제거하지 않으므로 crop 실험과 다르다. likelihood는 문자열 token 수로 나눈 평균 log-probability이며 EOS는 점수에서 제외한다. 문자열·tokenizer·template를 고정하고 동의어 ensemble이나 결과 후 문자열 선택은 금지한다.

순수 geometry·metrics 함수는 reuse_assets의 SHA에서 사용한다. `ev111_link.py`는 출처 구조를 읽는 참고이며 그대로 실행하지 않는다. 새 집단 연결은 원 manifest·checkpoint·completion·pixel 내용을 검증한다. ev111 gate F1·판정·verify를 호출하지 않으므로 그 결함을 이번에 전수 수정하지 않는다.

# Proposed Experiment

## 1. 자료·환경 적합성

`results/iter_035/confirm800/det17/completion.json`이 가리키는 `results/iter_010/manifests/confirm_ids.json`, 원 영상·GT, detector 선택 LOCK·checkpoint를 연결한다. E600 제외는 patient ID와 원본 연결로 확인한다. 학습·validation 선택 manifest와 중복 여부를 기록한다. GT 양성 여부와 box 정의를 확인하고 누락 annotation을 음성으로 만들지 않는다. 연결 불명확 환자를 임의 대체하지 않으며 영향과 실제 N을 보고한다.

공개 MedRegA 카드상 40B BF16이므로 가중치만 약 80GB다. config·가중치 index·license·공식 의존성과 로컬 RAM·디스크를 먼저 확인한다. 격리 환경과 별도 캐시를 사용한다. 공식 8-bit 로딩을 우선하고 두 GPU layer 분산 또는 필요한 CPU offload의 호환성을 확인한다. 4-bit 모델 교체·새 checkpoint·학습을 임의 도입하지 않는다. 지원 경로를 유지한 적재가 불가능하면 구체적 오류와 메모리 추정·시도를 보고하고 모델 실험 미실행으로 종료한다.

## 2. 동작 확인

적격 nonempty 환자를 SHA256('iter112:'+patient_id) 순으로 정렬해 처음 12명을 기술 집단으로 분리한다. 각 환자의 최고 confidence box 하나에서 공식 영역 식별 생성을 수행한다. 생성 조건은 공식 template, greedy, max_new_tokens400으로 고정한다. 100% 정답을 gate로 요구하지 않는다. 생성 결과는 인터페이스와 잘림·무관 출력의 진단용이며 자유 문장을 임상 판정하지 않는다.

후보 box와 전체 영역에서 고정 문자열 likelihood를 계산한다. 생성 첫 token logits와 teacher-forced 첫 token 확률, 수동 shift·mask 계산을 대조한다. 이미지 token·prompt token이 loss 평균에 들어가지 않는지 확인한다. 비정사각 fixture·좌표 반올림·실제 overlay를 확인한다. 누락 영상을 무작위 영상으로 대체하는 공식 demo 예외 경로는 반드시 오류 중단으로 바꾼다.

자료 오류·비유한 score·token alignment 불일치·지원 입력 연결 실패가 있으면 본 비교를 중단한다. 낮은 소견 정답률만으로 보편적 gate를 만들지 않는다. 모든 영역 score가 동일해 순위 신호가 없는 경우도 유효한 퇴화 관찰로 기록하되 대량 반복 생성은 하지 않는다.

## 3. 가능성 탐색

12명 기술 집단을 제외한 나머지 적격 환자의 threshold0.70 이상 모든 box를 평가한다. checkpoint epoch18과 threshold를 유지한다. box별 영역 scoring 한 번, 환자별 전체 영역 scoring 한 번이다. 같은 환자의 box에 전체 영역 score를 복제한다. 새로운 detector 생성은 필요 없다.

전체 대상 상한은 기존 152명·258box로 정해진 자산 범위이며 임의 시간 상한이 아니다. 기술 집단 제외 후 실제 N과 환자 수를 생성 전 manifest에 고정한다. 이번 작은 비교는 효과에 따라 표본을 선택하지 않고 한 번 완료한다.

## 4. 확대와 독립 확인

이번 반복은 위 개발 비교까지다. 추가 표본·새 seed·학습·다른 모델은 자동 실행하지 않는다. 양성일 때 효과·discordance·실측 비용으로 독립 확인 규모를 제안한다. 이는 method full 전환이 아니다.

# Implementation Tasks for Claude

1. 이번 계획·원 리뷰·선별 코드의 provenance를 확인하고 결과 경로 `results/iter_112/`에 입력 manifest와 규칙 lock을 기록한다.
2. 공식 MedRegA revision·환경·가중치 이용조건·학습 원천을 기록한다. 기본 환경과 hf_cache를 변경하지 않는다.
3. 공식 입력을 유지한 생성·likelihood 경로를 연결하고 소수 입력 및 독립 logits 계산으로 검증한다.
4. 자료·score·순위·오류 표를 분리해 GT가 모델 입력이나 순위 계산에 들어가지 않도록 한다.
5. 요청 ID, worker별 출력, 원자적 완료 기록, 실패 요청과 재개 상태를 보존한다. config/hash가 같을 때만 완료 요청을 재사용한다.
6. 판정과 핵심 수치를 별도 계산으로 검증한다. 같은 평가 함수를 재호출한 결과만으로 독립 검증이라 하지 않는다.

# Evaluation (성공/실패 기준 포함)

검토 단위는 예측 box다. 주 오류는 해당 box와 환자의 공개 GT boxes 간 최대 IoU가 0.3 미만인 사건이다. 일대일 matching·coverage·누락·중복 검출은 이 endpoint에 섞지 않는다. IoU0.5는 사전 지정 보조 지표이며 주 결정을 바꾸지 않는다. 이는 주석 불일치이며 임상적 소견 부재가 아니다.

각 순위의 검토량은 K=ceil(0.25N)이다. 낮은 confidence 또는 낮은 likelihood부터 검토한다. likelihood 동률은 낮은 confidence, patient ID, 원 box index로 해소한다. GT를 동률 처리에 사용하지 않는다. 전체 영역 대조도 같은 규칙을 사용한다.

주 차이는 (영역 순위가 포착한 오류 수−confidence 순위가 포착한 오류 수)/N이다. 전체 영역 대비 차이도 같은 방식으로 계산한다. 상위 K 집합의 공통·추가·손실 오류와 환자 수를 보고한다. 환자 cluster bootstrap 10,000회에서 순위와 K를 재계산해 95% CI를 제공한다. 기술 집단은 주 평가에 합치지 않는다.

양성 탐색은 두 대조 각각보다 5pp 이상 추가 포착하고, confidence 대비 순증가에 기여한 환자가 3명 이상일 때다. 5pp는 25% 검토 예산에서 검토 precision 약20pp 개선에 해당하는 투자 기준이다. CI 하한 양성을 탐색 진입 gate로 요구하지 않지만 CI와 leave-one-patient-out 결과를 보고해 불확실성을 유지한다.

confidence 대비 차이≤0이면 현재 고정 scoring 경로는 음성이다. 양의 차이가 작거나 전체 영역 대조를 넘지 못하면 영역 조건화 가치는 불확정/미지지로 구분한다. 무효 score를 임의 최하위나 정상으로 배정하지 않는다. 기술 복구 후에도 누락이 있으면 동일 전체 집합의 주 판정을 보류한다.

# Risks / Checks

40B 8-bit는 대략 40GB 수준의 가중치에 비양자화 모듈·activation이 더해지므로 두 24GB에서 가능하다고 보장하지 않는다. 실행 직전 nvidia-smi로 허용 GPU의 실제 여유를 확인하고 장치별 최소 2GB 안전 여유를 둔다. 한 모델을 두 GPU에 분산하면 복수 worker를 강제하지 않는다. 이 경우 모델 크기와 실측 peak가 단일 worker의 근거다. 독립 복제 여유가 없으면 microbatch 확대 가능성만 짧게 확인하며 공식 batch1 제한을 무검증 변경하지 않는다.

기술 입력에서 적재 시간·요청당 wall-clock·GPU별 peak·오류·CPU offload 비용을 측정한다. 예상 본 비교 시간은 남은 영역/전체 요청 수와 실측 처리량으로 산출한다. 기존 score 재사용과 이미지 feature 재사용은 동일 tensor·동일 logits가 검증된 경우만 허용한다. 추가 검토 오류 한 건당 추론 비용도 보고한다.

고정 문자열의 낮은 likelihood는 동의어 선호나 언어 prior 때문일 수 있다. 결과 후 문자열·parser를 교체해 구제하지 않는다. MedRegA 학습 원천과 RSNA의 완전한 비중복은 미확인으로 남긴다. 공식 task를 사용해도 자연 예측 box와 likelihood 순위는 확장 조건이다.

대규모 GPU 필요 후보: 영역–텍스트 정합과 경계 품질을 공동 학습하는 사전학습은 장기 후보로 보존한다. 이번 진단 전에는 신규 학습을 발주하지 않는다.

종료 보고는 실행 복구·입력 적합성·유효 비교·가설 지지를 구분한다. full 리뷰 후 다음 반복은 --confirm-each-iter 사용자 승인을 기다린다.

# 계획의 근거 (GPT 조사 노트)

## 확인 결과

라운드 01 원문 `agent/runs/iter_112/think/round_01.json`, GOAL, iter_111 리뷰와 code_assets를 확인했다. iter_111의 음성 결과와 재사용 결함은 유지한다.

MedRegA 공식 demo_data의 영역 식별 예제는 `<ref>this</ref><box>[[x1,y1,x2,y2]]</box>`와 원 영상 기준 0–999 좌표를 사용한다. 공식 입력 경로가 확인됐으므로 임의 yes/no 좌표 질의를 만들 필요가 없다. [공식 예제](https://raw.githubusercontent.com/xmed-lab/MedRegA/main/demo_data/data_file.jsonl)

공개 모델 카드는 40B BF16과 InternVL-Chat-V1-2 기반을 표시한다. 따라서 4B 추론 메모리 가정을 적용할 수 없다. config 직접 조회는 web Internal Error였고 shell 조회는 DNS 오류였다. 부재나 권한 부재로 해석하지 않는다. 구현 단계에서 metadata와 공식 8-bit 경로를 확인한 뒤 다운로드·적재 여부를 결정한다. [모델 카드](https://huggingface.co/Luxuriant16/medrega)

MedRegA는 영역 이름 식별을 학습했고 VinDr 계열 등을 사용한다. RSNA 문자열이 논문에서 검색되지 않았다는 사실은 미노출 증명이 아니다. SA-Med2D 등 상위 원천 중복도 남는다. [논문](https://arxiv.org/html/2410.18387v2)

MedP-CLIP은 더 직접적인 영역–텍스트 모델 후보이나, 이번 공식 논문·공개 검색에서 사용할 checkpoint와 공식 추론 경로를 확인하지 못했다. 공개 자산이 없다고 단정하지 않지만 이번 실행 비교군으로 확정하지 않는다. [논문](https://arxiv.org/abs/2604.11197v3)

`results/iter_035/confirm800/det17/raw_preds.json`과 `results/iter_016/manifests/sets.json`을 읽어 E600 밖 200명, nonempty 152명, threshold0.70 이상 box 258개를 확인했다. 이는 새로운 독립 test가 아니다. 과거 confirm800 분석에 포함된 개발 자료이며 환자·학습/선택 노출의 세부 연결은 실행 전 검증한다.

공식 영역 식별 문맥에서 고정 문자열 `lung opacity`의 평균 token log-likelihood를 쓰는 확장 진단을 선택했다. 자유 문장 의미 판정과 동의어 사후 선택을 피할 수 있지만, calibration된 오류 확률이나 공식 평가 방식은 아니다. 전체 영역 입력 대조로 전역 소견 인식 설명을 함께 검토한다.

파일 변경·설치·모델 실행은 수행하지 않았다.

이전 사고 라운드 노트: agent/runs/iter_112/think/
