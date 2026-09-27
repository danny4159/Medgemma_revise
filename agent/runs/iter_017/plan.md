# 요약

- **이번에 할 일:** 같은 영상과 공통 안내문에서 정보 없음·검출 유무·개수·좌표를 비교한다.
- **필요한 이유:** 기존 bbox reader의 개선은 확인됐지만 문구와 전달 정보의 효과가 섞여 있다.
- **확인할 기준:** P180에서 단순 정보 baseline 대비 잔여 효과와 category별 손익을 확인하고, 판단에 필요할 때만 E600과 좌표 교란으로 확대한다.
- **주의·다음:** 새 학습과 reserve 사용은 없다. 이번 진단의 성공은 원인 후보를 좁히는 것이며 신규 contribution이나 임상 reasoning의 증명이 아니다.

# Current Understanding

iter_009의 정상 사용 조건 RSNA grounding 한계와 iter_012의 직접 SFT 개선은 유지한다. iter_014의 현재 GIoU 가중 설계에 대한 투자 중단도 유지한다. iter_016에서는 큰 QA strict 저하의 상당 부분이 형식 차이로 설명됐고, 예측 bbox를 받은 M0 reader의 제한된 이득이 확인됐다.

동일 P180에서 predicted/unavailable/direct M0의 S_scope는 0.7000/0.5722/0.6222다. predicted−direct는 +0.0778이었다. 그러나 기존 evidence 문구는 비어 있는 예측, 비어 있지 않은 예측, unavailable에서 서로 다르다. 또한 비어 있지 않은 bbox는 Q_O의 검출 신호와 개수·좌표를 함께 전달한다.

현재 소스와 결과를 확인했다. P180의 B0 비어 있지 않은 예측은 총 72명이며, E600에서는 236명이다. 빈 예측이 많은 조건에서 전체 평균만 보고 좌표 활용의 부재를 주장하면 안 된다. P180과 E180은 동일 집단이 아니다.

iter_008 사용자 보완 중 정상 사용법 검증은 iter_009에서 수행됐다. 이를 다시 처음부터 반복하지 않는다. 실제 출력·정답·parser 분리, 기존 자산 보존, 새 결과 경로 사용은 계속 지킨다. anatomy 전이와 후속 loss는 자동 재개하지 않는다.

# Strategy Check / 연구 방향 판단

중요한 사용 과제는 전문 localizer의 불완전한 출력을 원본 영상과 함께 읽고, 특정 finding의 검출 여부를 더 넓은 질문에 과도하게 일반화하지 않는 것이다.

확인된 사실은 형식 효과와 P180의 모듈형 개선이다. 미확인 경쟁 설명은 안내 문구의 효과, 검출 유무 전달, 개수 정보, 환자에 맞는 좌표의 활용이다. 시각적 forgetting과 새로운 방법의 필요성도 확정되지 않았다.

1. **현재 방법 개선:** 직접 SFT baseline은 강하고 추가 loss의 이득은 입증되지 않았다. 새 학습 비용에 비해 현재 정보 이득이 낮다.
2. **원인 진단:** 이미 관찰된 +0.0778의 개선을 기존 자산으로 분해할 수 있다. 단순 baseline과 잔여 효과를 구분하면 다음 학습 투자를 바꿀 수 있어 이번에 선택한다.
3. **다른 질문으로 전환:** 연구 범위를 넓힐 가치가 있지만 유효한 정답·데이터·선행 차이를 새로 확인해야 한다. 현재 효과가 단순 정보 전달로 설명되거나 조건부 확대 후에도 가치 있는 잔여 현상이 불명확하면 우선한다.

이번 선택은 iter_015 전략 검토와 iter_016 리뷰의 후속이다. 같은 접근법에서 기존 형식 가설을 반복하지 않고 새로 확인된 evidence 효과를 조사한다. 모든 결과를 다음 loss 탐색으로 연결하지 않는다.

# Hypothesis

- **H_detection:** 공통 문구에서도 검출 유무 전달 B가 정보 미제공 U보다 유용하다.
- **H_count:** 개수 K가 binary B와 다른 효과를 낸다. 차이가 있으면 L−B를 좌표 효과로 해석할 수 없다.
- **H_coordinates:** 개수까지 맞춘 K 대비 L의 잔여 효과가 존재하며, 그 효과가 환자에 맞는 좌표 연결에 의존할 수 있다.
- **H_wording:** 기존 조건과 공통 문구 조건의 차이에서 인터페이스 문구의 영향을 관찰할 수 있다. 여러 표현이 함께 바뀌므로 특정 한 문장이 원인이라고 주장하지 않는다.

각 가설은 양립할 수 있다. 좌표 정보가 이 과제에서 불필요하다는 결과는 모델에 좌표 활용 능력이 없다는 뜻이 아니다.

# Limitation Evidence / Correct Usage Checks

이번 대상 `rsna-evidence-interface-sensitivity`는 observed다. diagnostic으로 수행하며 방법 개발이나 validated 승격을 전제하지 않는다.

- 모델은 MedGemma 1.5 revision `91850547d9f0b2fdd21aa7c5f4f3d1a8a52c243b`다. 기존 processor/chat template, bf16, greedy, 값 보존 RGB 변환, square padding을 유지한다.
- Q_O/Q_A와 plain 출력 지시는 승인된 `qa_spec.py` 그대로 사용한다. 질문은 각각 독립 대화다.
- strict와 `semantic_v1`을 모두 보고한다. Normal/Abnormal 대응은 Q_A에만 허용하고 설명문·bbox·모순을 임의로 구제하지 않는다.
- 생성 cap 1000→2000→4000과 EOS 검사를 유지한다. 처리량을 위해 길이를 줄이지 않는다.
- bbox는 square-padded image 기준 yxyx 정수 0–1000이다. invalid·truncated를 빈 검출로 바꾸지 않는다.
- 정답은 RSNA 판독 규약의 opacity=(yes,yes), Normal=(no,no), NoOpacity/NotNormal=(no,yes)다. 일반적인 임상 정상 판정으로 확대하지 않는다.
- 모든 실용 조건에 동일 원본 영상을 제공한다. GT category는 요청 생성의 evidence 결정에 사용하지 않는다. GT는 표본 층화와 평가에만 사용한다.

# Contribution Path / Baselines / Reuse

## 선행과 기여 경로

[Visual Evidence Prompting, ACL 2025](https://aclanthology.org/2025.acl-long.205/)는 전문 시각 모델 출력을 prompt로 전달한다. [Why Does Grounding Hurt Medical VQA? v2](https://arxiv.org/html/2604.27720v2)는 crop 인터페이스와 형식·공간 supervision을 구분한다. 따라서 형식 복구, bbox text 추가, 단순 혼합 SFT 자체를 신규 contribution으로 삼지 않는다.

이번 진단의 가치는 단순 검출 전달을 넘는 효과 또는 질문 범위에 따른 재현 가능한 실패 조건이 남는지 확인하는 데 있다. 양성이어도 여러 데이터·독립 환자·강한 baseline을 통한 후속 검증이 필요하다.

## 비교군

- **Direct M0:** 기존 iter_016 plain 응답을 정확히 같은 환자에서 재사용한다.
- **Direct B0/C:** 같은 환자의 기존 QA를 배경 비교로 보고한다. B0는 직접 grounding SFT이며 C는 추가 SFT 단일 경로다. C를 독립 seed나 선택된 최적 모델로 부르지 않는다.
- **U/B/K/L:** 같은 M0 reader와 같은 B0 localizer 출력으로 구성한다.
- **기존 predicted/unavailable:** P180의 문구 변경 전 참조다. 공통 문구 조건과의 차이를 특정 문장의 단독 인과 효과로 해석하지 않는다.
- **B0 bbox+규칙:** 비어 있지 않은 유효 예측은 (yes,yes), 유효 빈 예측은 Q_O=no·Q_A=판단 불가다. 판단 불가는 전체 분모에서 실패이며 coverage를 별도로 보고한다. 고정 답 쌍 baseline도 유지한다.
- 기존 GT oracle는 참고 자료로만 보존하고 새 실용 비교나 순위에 포함하지 않는다.

학습 환자 수·presentations·checkpoint 선택 이력은 원본 학습 manifest와 리뷰에서 가져와 표로 남긴다. 이번 신규 조건끼리는 학습량 차이가 없다. direct와 모듈형 구성의 호출 수·입력 token 수·wall-clock을 구분하고, 모듈형 실용 비용에 localizer 추론을 포함한다. 후속 방법 개발에서 detector/encoder+head와 충분한 직접·다과제 SFT 비교를 생략하는 근거로 이번 진단을 사용하지 않는다.

## 재사용 범위

현재 `approach/target-scope-diagnostic`, HEAD `6a4fb41d490305061028de9cab863c0b5e9747ad`를 이어간다. 필요한 파일이 현재 브랜치에 있어 `reuse_assets=[]`다.

- 승인 범위 재사용: `qa_spec.py`의 질문·strict/semantic parser, `geometry.py`, `parse.py`, `metrics.py`, `sft_eval.py`, `lora.py`의 기존 역할.
- 필요한 수정: `qa_eval.py`, `qa_requests.py`, `qa_reuse.py`, `qa_protocol.py`와 이들을 사용하는 `qa_run.py`, `qa_gen.py`, 분석 코드.
- 실행 경로 의존성: `generate.py`, `inputs.py`, `eval_gate.py`, `queue_lock.py`, `lock_protocol.py`, `on_gpu.py` 등 기존 protocol에 명시된 파일을 보존하고 잠금 목록에 연결한다.
- 재사용 결과: iter_016의 manifests·direct QA·P180 evidence, iter_015의 B0 concise 추출 결과, 그 원본인 iter_012 confirm_sft_seed17 응답과 provenance.

원본 hash, 요청·영상·adapter 연결을 재검증하고 이번 `results/iter_017/reuse/`에 검증 근거를 남긴다. 과거 protocol을 현재 코드로 재잠금하지 않는다. 현재 실험에서 사용하지 않는 geo 학습 경로의 수치 결함은 선행 작업으로 넣지 않는다.

# Proposed Experiment

## 1. 동작 확인과 입력 고정

새 산출물은 모두 `results/iter_017/` 아래에 저장한다. 기존 D36/D12/P180/E600 목록을 그대로 사용하고 재추출하지 않는다. 환자·pixel hash 중복과 P180⊂E600, D와 평가 집단의 분리를 검사한다. E600은 기존 개발 자료이며 reserve는 접근하지 않는다.

B0의 기존 유효 bbox에서 k와 좌표를 계산한다. 현재 계획에서 정한 공통 evidence template을 별도 버전으로 구현하고 기존 문구를 덮어쓰지 않는다.

공통 header는 기존 EVIDENCE_HEAD를 사용한다. 공통 설명은 다음으로 고정한다:
`The localization output may be incorrect or incomplete and concerns only pulmonary opacity. Assess the original image for the question. Fields marked not_provided contain no supplied information. Box coordinates, when supplied, are yxyx integers in [0,1000] relative to the entire square-padded image.`

이후 고정 key 순서의 packet과 기존 질문·plain 지시를 붙인다. packet은 `detection`, `count`, `boxes` 세 필드다.

| 조건 | 비어 있지 않은 유효 예측 | 유효 빈 예측 |
| --- | --- | --- |
| U | 세 필드 모두 not_provided | 세 필드 모두 not_provided |
| B | detection=present, 나머지 not_provided | detection=none, count=0, boxes=[] |
| K | detection=present, count=k, boxes=not_provided | detection=none, count=0, boxes=[] |
| L | detection=present, count=k, boxes=예측 좌표 | detection=none, count=0, boxes=[] |

invalid/truncated localizer 출력은 B/K/L에서도 세 필드를 모두 not_provided로 표시하고 원래 실패 상태를 별도 metadata에 남긴다. source row 자체의 누락은 검출 실패가 아니라 입력 오류이므로 중단한다. 빈 예측에서는 B/K/L prompt가 완전히 같아야 한다. 이를 단위 검사와 GPU 출력 정합성 검사에 사용한다.

D12 12명×4조건×2질문=96 논리 요청으로 형식·영상 연결·prompt·출력·메모리를 확인한다. D12에 없는 empty/nonempty/multiple/invalid 사례는 CPU fixture로 검사한다. 개발 정확도를 보고 문구를 고르지 않는다. condition×target의 semantic valid가 95% 미만이면 형식 문제를 조사하고 본평가를 보류한다. parser 허용 범위를 확대하지 않는다.

정확히 동일한 prompt·영상·모델·generation config의 요청을 재사용할 경우 source request와 대상 condition의 명시적 alias를 잠그고 논리 요청 수와 실제 생성 수를 구분한다. 검증된 alias 경로가 없으면 임의 deduplication하지 않는다.

## 2. 가능성 탐색: P180

기존 category별 60명, 총 180명에 U/B/K/L과 두 질문을 적용한다. 신규 논리 요청은 1,440건이다. 기존 direct M0/B0/C와 predicted/unavailable 응답은 같은 ID만 추출해 재사용한다.

새 학습은 없으며 localizer는 B0 seed17로 고정한다. 이 단계의 모든 요청이 완료된 뒤 한 번 평가한다. 주 비교는 B−U와 L−K다. K−B, L−B, 각 조건−direct M0 및 기존 문구 조건과의 차이를 함께 보고한다.

비어 있지 않은 예측 72명과 빈 예측 108명의 효과를 분리한다. nonempty subset은 모델 예측으로 정의된 조건부 분석이며 전체 환자 효과를 대체하지 않는다. category별 분모가 작으면 그 불확실성을 그대로 남긴다.

## 3. 조건부 규모 확대: E600

이번 진단의 투자 판단 경계는 S_scope 절댓값 0.05, category별 정답 쌍 정확도 절댓값 0.10으로 사전에 정한다. 이는 iter_016의 기존 판정 기준을 수정하는 것이 아니다.

다음 중 하나이고 입력·형식 gate가 통과했을 때 E600으로 확대한다.

- B−U 또는 L−K의 점추정 절댓값이 0.05 이상이며, 확대가 효과의 방향·실용성·category 손익 판단을 바꿀 수 있다.
- 해당 비교의 category별 차이 절댓값이 0.10 이상이며, 더 많은 해당 category 환자가 판단에 필요하다.
- 중요 효과의 존재와 실질적 무효과를 CI가 모두 포함하고, 현재 paired 차이 분산으로 계산한 E600 예상 CI 반폭이 S_scope 0.05 이하 또는 해당 category 0.10 이하가 되어 판단 개선이 예상된다.

이미 차이가 정밀하게 배제되거나, 추가 환자로 해결할 수 없는 형식·정답·정보 조작 문제가 있으면 확대하지 않는다. 효과가 명확하더라도 추가 표본이 다음 행동을 바꾸지 않는다면 진단을 종료할 수 있으며 이유를 기록한다.

확대는 기존 E600에서 P180을 제외한 category별 140명, 총 420명을 추가한다. 추가 논리 요청은 3,360건, 누적은 4,800건이다. 네 조건을 모두 같은 집단에서 평가하며 유리한 조건만 확대하지 않는다. P180, 추가 420명, 누적 600명의 결과를 구분한다. 추가 420명도 새 독립 test가 아니다.

확대 판단용 분산은 category 내 환자별 paired 차이에서 계산한다. macro 평균 분산은 category 평균 분산의 합을 9로 나눈다. nonempty 분석은 실제 추가 가능 표본 수와 category 구성을 사용한다. E600도 필요한 정밀도에 못 미치면 reserve를 자동 사용하지 않는다.

## 4. 조건부 좌표 연결 교란 X

도달한 표본에서 L−K의 절댓값이 0.05 이상이거나 category별 절댓값이 0.10 이상이고, 좌표 내용에 대한 반응을 확인하는 것이 다음 투자를 바꿀 때 실행한다. CI가 중요 효과를 포함하며 X 비교가 판단에 충분한 정밀도를 제공할 것으로 예상되는 경우도 허용한다. 단순 L−B 차이만으로 실행하지 않는다.

같은 nonempty box 개수 k를 가진 환자끼리, patient ID의 고정 hash 순서와 seed17로 정한 순환 이동을 사용해 좌표 목록을 다른 환자에게 배정한다. category·정답·영상 유사도는 donor 선택에 사용하지 않는다. reader는 원래 환자의 영상을 계속 받는다. detection, k, 문구, 좌표 serialization 형식은 L과 같다. 각 k 그룹의 좌표 목록 분포는 보존된다.

donor 규칙과 P180/E600 각각의 mapping은 본평가 전에 잠근다. 그룹 크기가 1이거나 좌표가 우연히 같으면 그대로 기록하고 사후 유리한 donor로 바꾸지 않는다. mapping이 달라지는 P180용 X와 E600용 X를 같은 조건처럼 합치지 않는다.

X는 도달한 N명×2질문으로 최대 2N 논리 요청이다. 빈 예측과 invalid의 packet은 L과 동일하다. 실제로 좌표가 바뀐 환자 수와 변위·기존 GT에 대한 정합성 변화를 사후 진단 표로 보고하되, GT로 교란을 선택하지 않는다.

L−X는 환자–좌표 연결의 효과다. 모든 교란이 틀린 영역이라는 보장은 없으므로 음성 결과를 좌표 무사용의 증명으로 삼지 않는다. L−X가 양성이어도 이것만으로 임상 reasoning이나 공간 grounding 능력을 확정하지 않는다.

## 5. 독립 확인

이번 반복에서는 새로운 학습, 다른 B0 seed, reserve, 외부 데이터 평가를 수행하지 않는다. 기존 개발 자료에서 경쟁 설명을 좁히는 단계다. 가치 있는 잔여 효과 또는 실패 조건이 남으면 후속 계획에서 질문·방법·강한 baseline을 고정하고 새 환자 및 원천이 다른 데이터의 확인을 설계한다.

## 6. GPU 배치·비용·재개

실행 직전에 nvidia-smi로 상속 허용 집합 0,1의 UUID·논리 index·남은 메모리를 확인한다. 다른 사용자의 프로세스는 변경하지 않는다.

D12 동일 96요청에서 GPU당 1 worker와 2 worker를 짧게 비교한다. 요청 집합·greedy token·parser 결과가 같고 전체 wall-clock 처리량이 개선되며 메모리 조건을 만족하면 총 4 worker를 사용한다. batch 확대까지 전수 탐색하지 않는다. 두 GPU에 독립 요청 shard를 배치한다.

메모리 판단은 다른 점유에 각 worker의 실제 peak와 worker당 최소 2GiB 여유를 합산한다. 기존 evidence 두 worker/GPU의 전체 점유 약 17.2GiB는 참고값이다. 새 prompt와 development 긴 출력 사례의 KV cache·reserved memory·최대 요청 지연을 측정한다. 안전 여유 부족이나 OOM·경합이 있으면 worker 수를 줄인다.

기존 evidence 처리량은 약 267–305 req/min이었다. 새 조건의 초기 추정은 150–300 req/min으로 두며, P180 1,440건은 생성 약 5–10분, E600 누적 4,800건은 약 16–32분이다. X까지 포함하면 최대 6,000건으로 약 20–40분이다. 로딩·pilot·검증·긴 출력·GPU 대기를 포함한 총 실행은 약 1–2시간을 초기 추정으로 기록하고 실제 처리량으로 갱신한다. 이는 timeout이나 실행 상한이 아니다.

새 학습 checkpoint는 없다. protocol, 요청 manifest, worker별 JSONL, 원자적 claim, 시도별 종료 코드, completion, 단계별 분석을 재개 지점으로 사용한다. 완료 요청도 현재 입력·출처를 검증한 뒤 재사용한다. 활성 claim을 삭제하지 않으며 부모 중단 시 자기 자식만 정상 회수한다. 진행량·처리량·peak·오류를 로그로 남긴다.

# Implementation Tasks for Claude

1. 현재 git 상태와 실행 중인 소유 작업을 확인한다. 기존 기록·결과·checkpoint를 보존하고 새 출력 root를 `results/iter_017`로 고정한다.
2. `qa_eval.load_stage`에서 completion 내용, protocol/request digest, 예상·실제 고유 요청 집합, 누락·중복·잉여, 자식 종료 코드를 검증한다. 생성 재개와 평가에 같은 검증을 연결한다.
3. bbox를 읽을 때 reuse manifest의 원본 hash와 source request·adapter·영상 연결을 확인한다. 신규 bbox stage를 읽는 경로에는 완료 내용 검증도 적용한다. 누락이나 충돌을 임의 출처 선택으로 해결하지 않는다.
4. 파일명만으로 허용하는 ALLOW_CHANGED 우회를 이번 경로에서 제거한다. 새 실행·분석 코드를 결과 열람 전에 잠근다. 불가피한 분석 수정은 정확한 before/after hash·사유·영향 범위를 별도 기록하고 허용 목록을 명시적으로 검증한다.
5. 별도 버전의 U/B/K/L 및 조건부 X 요청·분석을 구현한다. 기존 질문·parser·evidence 문구는 보존한다. common prompt, packet, source hash, 좌표 mapping을 request ID와 protocol에 연결한다.
6. malformed completion, 비정상 종료 코드, missing/extra/duplicate 요청, 변경된 bbox 원본, 잘못된 adapter·영상 hash, 무허가 코드 변경을 거부하는 회귀 검사를 실행한다. 정상 재사용과 중단·재개 검사가 실제 원문 token 및 요청 집합을 대조하도록 한다.
7. D12 동작 확인과 자원 비교 후 P180을 실행한다. 확대 및 X 여부는 사전 규칙으로 결정해 실행 전에 decision artifact를 저장한다. 원래 결과를 덮어쓰지 않는다.
8. 각 단계의 원시 답변·환자별 차이·category별 손익·CI·실제 요청 수·자원 사용량·미실행 조건을 보고한다. 기존 direct와 old evidence 참조는 정확한 환자·질문·출처를 명시한다.

# Evaluation (성공/실패 기준 포함)

## 지표와 불확실성

주지표는 기존 semantic S_scope, 즉 두 질문을 모두 맞힌 환자의 비율을 category별 계산한 뒤 균등 평균한 값이다. strict S_scope, 질문별 정확도·validity, category별 정답 쌍 정확도, (yes,yes)/(no,no)/(no,yes)/(yes,no)/invalid 분포를 함께 보고한다. invalid는 전체 분모에서 실패다.

두 주 비교 B−U와 L−K에는 category 내 환자 paired bootstrap 10,000회, seed 20260927, 개별 97.5% CI를 사용한다. 나머지는 95% 탐색 CI로 구분한다. 모든 질문·조건을 환자 단위로 함께 재표집한다. 단계적 확대와 기존 개발 자료 사용 때문에 이 CI를 독립 confirmatory 검정으로 표현하지 않는다.

빈 예측에서 동일 prompt 조건의 출력이 다르면 정보 효과보다 실행 정합성을 먼저 검사한다. 형식 차이의 가능한 영향이 결론을 뒤집으면 의미 효과 판정을 보류한다. 정답률을 보고 parser를 수정하지 않는다.

## 양성

B−U에서 실질적 양의 효과가 확인되면 검출 정보 전달의 가치를 인정한다. L−K와 필요시 L−X에서도 양의 잔여 효과가 있고 direct M0 대비 실용 이득이 유지되면 환자에 맞는 좌표 정보의 가치가 있다는 제한된 근거로 기록한다. category별 중요한 손실을 함께 표시한다. 이 경우에만 후속 데이터·방법 비교의 투자 가치를 검토하며 신규성은 별도로 확인한다.

## 음성

L−K의 CI가 ±0.05 안에 있고 category별 ±0.10 규모의 손익도 배제되면, 이번 과제에서는 좌표의 중요한 추가 효과가 지지되지 않는다고 판단한다. 단순 B/K가 기존 이득을 재현하면 강한 모듈형 baseline으로 보존한다. 공통 문구에서 이득이 사라져도 이전 결과를 무효화하지 않고 인터페이스 의존성을 기록한다. 새 loss를 예약하지 않고 다른 중요한 연구 질문을 우선 검토한다.

좌표가 일관되게 성능을 낮추는 결과도 정보 이득이다. 단순 부정 결과로 버리지 않고 어떤 질문·category에서 손실이 생기는지 보고한다. 반복 가능한 실패 조건의 중요성이 충분할 때만 추가 연구를 검토한다.

## 불확정

CI가 중요 효과와 무효과를 함께 포함하면 유의하지 않다는 이유로 동등성을 선언하지 않는다. 추가 표본이 정밀도를 개선할 때만 E600으로 확대한다. E600 또는 X 이후에도 식별력이 부족하면 적용 범위와 필요한 표본·대조를 기록하고 이번 투자를 보류한다. reserve·새 seed·새 학습을 자동 추가하지 않는다.

## 실행 판정

진단 success는 실제 통제 비교를 유효하게 완료해 다음 선택을 구분한 경우다. 성능 향상·가설 지지·신규 기여·최종 목표 달성은 별도 판단이다. 입력·출처·완료 검증 오류로 유효한 비교를 못 하면 execution_failed이며 과학적 가설의 기각이 아니다.

# Risks / Checks

- 새 packet 형식 자체가 응답에 영향을 줄 수 있다. D12에서 측정 가능성을 확인하고 문구 차이를 단일 문장의 인과 효과로 과장하지 않는다.
- 좌표는 개수 정보를 포함하므로 K를 생략하지 않는다. 빈 예측에서 B/K/L이 같아야 하며 nonempty subset의 작은 분모를 숨기지 않는다.
- 특정 opacity의 음성을 전체 정상으로 바꾸지 않는다. RSNA category와 질문 정의의 범위를 유지한다.
- X는 정보 연결 교란이며 모든 donor 좌표가 임상적으로 틀린 것은 아니다. 효과 부재를 시각 정보 미사용으로 일반화하지 않는다.
- P180/E600은 개발 자료다. 기존 confirm의 역사적 유효성은 유지하지만 이번 결과를 새 독립 확인으로 부르지 않는다.
- 모듈형 reader의 비용에서 localizer 학습·추론을 제외하지 않는다. 내부 SFT와 모듈형 대안의 우열을 이번 한 비교로 확정하지 않는다.
- source 보존·hash 검증·완료 판정에 필요한 수정만 수행한다. 연구 질문과 무관한 리팩터링은 미룬다.

## 대규모 GPU 필요 후보

다양한 modality·finding·질문 범위를 함께 다루는 vision encoder–language model 공동 post-training과 근거 supervision을 후보로 보존한다. 현재 결과는 그 필요성을 입증하지 않는다. 두 GPU에서 가능한 기존 자산 진단과 이후의 경량 적응·모듈형 비교를 먼저 수행한다.

# 계획의 근거 (GPT 조사 노트)

## 새로 확인한 것

- `agent/GOAL.md`, `agent/LIMITATIONS.md`, iter_015 조사 기록, iter_016 계획·리뷰·보고서, `agent/CODE_ASSETS.md`와 실제 QA 코드를 확인했다. 현재 연구 HEAD는 `6a4fb41d490305061028de9cab863c0b5e9747ad`이며 `git status --short`와 `git diff --stat`는 비어 있다. 필요한 qa_* 파일과 iter_016 테스트가 현재 브랜치에 있어 선별 반입이 필요하지 않다. 전체 코드의 재사용 승인을 뜻하지 않는다.
- iter_016 리뷰에서 P180 predicted/unavailable/direct M0의 S_scope는 각각 0.7000/0.5722/0.6222다. predicted−direct는 +0.0778, 95% CI [0.0278, 0.1333]이었다. category별 정답 수가 크게 달라 단순 총점만으로 해석할 수 없다.
- `rsna_diag/qa_spec.py`에서 predicted_nonempty에는 proposal 오류 가능성을, predicted_empty와 unavailable에는 Normal을 의미하지 않는다는 설명을 넣는 것을 확인했다. 조건별 문구와 전달 정보가 함께 달라 기존 차이를 좌표 효과나 특정 문장 효과로 분해할 수 없다.
- `results/iter_015/reuse/bbox_B0_concise.jsonl`의 저장 응답을 읽기 전용 JSON 집계로 확인했다. P180의 비어 있지 않은 예측은 opacity 54/60, Normal 1/60, NoOpacity/NotNormal 17/60으로 총 72/180이다. E600에서는 각각 164/200, 5/200, 67/200으로 총 236/600이다. P180 양성 54명 중 27명은 box 2개이므로, 좌표 조건과 binary 조건의 차이에는 개수 정보도 섞일 수 있다. 이 집계는 정식 bbox parser 재검증을 대체하지 않는다.
- `sets.json`에서 P180은 E600의 부분집합임을 확인했다. P180과 E180은 크기가 같아도 서로 다른 목록이므로 혼용하면 안 된다.
- `qa_eval.load_stage`는 completion의 존재만 검사한다. `qa_requests.bbox_records`는 원본 hash를 읽을 때마다 대조하지 않는다. `qa_protocol.verify`의 allow_changed는 파일명 기준 예외다. 이번에 사용하는 경로에서 이 세 결함을 먼저 보완해야 한다.
- `throughput_summary.json`에서 기존 evidence 생성은 360건/81.0초 및 720건/141.8초, 약 267–305 req/min이었다. 당시 두 worker/GPU의 전체 점유는 약 17.2–17.4 GiB였다. 새 prompt의 처리량·긴 출력 메모리는 별도 실측이 필요하다.

## 선행과 의미

기존 조사에서 초록만 확인한 모듈형 선행과 후속 문구 대조의 관계를 확인하기 위해 공식 페이지를 재조회했다. [Visual Evidence Prompting, ACL 2025](https://aclanthology.org/2025.acl-long.205/)는 전문 시각 모델의 출력을 prompt로 전달한다. 따라서 이번 모듈형 구성 자체를 새 방법이라고 주장할 수 없다.

[Why Does Grounding Hurt Medical VQA? v2](https://arxiv.org/html/2604.27720v2)의 원문은 crop 인터페이스의 문제와 형식 rehearsal·실제 grounding supervision의 차이를 다룬다. 이번 원본 영상+bbox text 조건과 동일한 실험은 아니다. 기존 논문의 결론을 우리 조건에 그대로 적용하지 않는다. 이 논문은 이미 `agent/PAPERS.md`에 추천됐으므로 중복 추천하지 않는다.

## 방향 판단

현재 grounding loss 개선은 새 원인 근거가 부족하다. 다른 의료 VLM 질문으로의 전환은 여전히 대안이지만, 실제 모듈형 이득이 있는 현재 자산으로 정보 전달 효과를 구분하는 비용과 정보 이득이 더 유리하다. 네 정보 수준의 공통 문구 대조를 먼저 수행하고, 좌표 효과가 남을 때만 환자–좌표 연결 교란을 추가한다. 이 진단은 공간 reasoning이나 임상 추론의 증명이 아니며, 추가 표본도 기존 개발 집단 안에서만 조건부로 사용한다.

## 대규모 GPU 필요 후보

여러 modality·finding·질문 범위를 함께 학습하는 vision encoder–language model 공동 post-training과 다과제 근거 supervision은 보존 후보다. 일반화와 능력 보존을 비교할 수 있지만, 현재 결과만으로 대규모 학습 투자 근거가 생긴 것은 아니다.
