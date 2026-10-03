# Work Performed

- **요약 (핵심):** OmniBrainBench의 brain MRI 진단 QA(공개 closed-ended 6,823문항)를 연결하고, MedGemma 1.5로 D6와 E24(24 cluster)를 실제 출력까지 실행했다. E24에서 영상 신호가 text-only(T)를 넘지 못했다.
- **근거:** E24 정확도는 T 0.500, J(전체 영상) 0.4375, S_mean(개별 영상 평균) 0.410, V(개별 답변 plurality vote) 0.4375다. J−T −0.0625 [−0.208, 0.0625], V−T −0.0625 [−0.208, 0.0625]이다. 영상 신호 CI 상한이 10 pp 미만이라 사전 규칙상 E64 확대는 하지 않았다.
- **미검증·주의:** 24 cluster는 확증 표본이 아니다(최악 반폭 약 20 pp). BraTS·ISLES의 질문 본문이 병변 소견을 서술해 T가 유리할 수 있다. PubMedVision은 논문 단위 cluster여서 환자 독립성이 없다. 임상 능력 결론은 내지 않는다.
- **다음:** MedGemma 통합 방법 투자는 보류하고, 같은 고정 자료에서 다른 VLM과 비교할 가치만 GPT가 리뷰에서 판단한다.
- **iter_060·iter_055 범위:** UCSF routing, MSD 추가 적응, OCT 후보는 보류로 유지했다. 기존 결과·reserve는 소비하지 않았다.
- **자료·적격성 (모델 출력 보기 전에 확정):**
  - 공식 revision `899f22f9…`의 JSON과 ZIP(sha256 `471d4e7f…`)을 받아 14,738개 영상 경로가 ZIP basename과 모두 1:1 대응함을 확인했다.
  - 적격 규칙은 Disease Diagnosis Reasoning, MRI 계열 modality만, 질문에 "diagnos" 포함, 선택지 5개 유일, 정답 문자열이 질문에 없음, 영상 존재다. 결과는 1,148 QA → 1,144 component이다.
  - cluster는 case/article ID와 공유 영상 pixel hash를 합친 component로 만들었다. 원천이 PubMedVision이면 환자 독립성은 없다.
- **시각 감사:** 실제 영상 contact sheet를 열어 D·E 후보를 보고 혼합 modality·비뇌·MRS plot·동물·segmentation overlay 등 7개 cluster를 제외했다. 제외 후 D와 E 목록을 다시 고정했다. 전문의 재판독이 아니다.
- **구현:**
  - 모델 loading, env 기록, chat template 입력은 `msd56_run.py`의 `load_model`·`env_info`·`build_inputs`를 재사용했다. 이 파일은 blob `63347081…`로 반입된 것이다.
  - 새 adapter는 QA 요청 구성, 선택지 permutation, parser, 평가, worker·launch·verify 경로다. MSD 전용 부분은 쓰지 않았다.
- **parser 변경 (D 기준):** D6에서 모델이 `ANSWER: X` 대신 `Final Answer: …\boxed{X}`를 자주 써서 strict(v1) 유효율이 38.6%였다. 그래서 `\boxed` 한 줄을 허용하는 v2를 D 관찰만으로 정해 `mri61_parse.py`에 고정했다. E 결과는 보지 않았다.
- **E24 선택 방식:** D와 분리한 뒤 원천×이미지 수(2, 3–4, 5 이상)별로 번갈아 뽑았다. E64 목록도 잠갔지만 확대 조건을 충족하지 못해 실행하지 않았다.

# Files Changed

새로 만든 코드는 `research/` 아래다.
- `mri61_explore.py`: 적격성 탐색
- `mri61_data.py`: 적격성·cluster·D/E 잠금
- `mri61_sheet.py`: 감사용 contact sheet
- `mri61_spec.py`: prompt·permutation·strict parser
- `mri61_parse.py`: parser v2
- `mri61_run.py`: build·lock·worker·launch·verify·tech
- `mri61_eval.py`: 평가
- `mri61_test.py`: 실행 경로 검사
- `msd56_run.py`: 반입 파일, 수정 없음

# Commands / Experiments

- **자료:** HF 파일 JSON·README·ZIP 다운로드(성공), `mri61_data.py` 실행 3회(제외 목록 반영, 성공).
- **tech 검사:** D88 요청과 E24 264 요청에서 공식 processor 경로(`apply_chat_template` → processor, `add_special_tokens=False`)와 wrapper의 `input_ids`·`pixel_values`·영상 수를 대조했다. D는 44건+32건, E24는 132건+84건에서 불일치 0이다. 첫 시도는 BOS 중복이 원인인 대조 코드 오류로 실패했고 수정 후 통과했다.
- **D 생성:** 88요청을 2 worker(GPU 0·1 각 1개)로 실행했다. wall 1700초, peak 11.3/11.0 GB, 종료 코드 [0,0], verify 문제 0이다.
- **E24 생성:** 264요청을 같은 구성으로 실행했다. 종료 코드 [0,0], verify 문제 0이다.
  - 처리량은 D 기준으로 약 85분 추정했으나 실제 수치는 `gen_E24/launch_*.json`에 있다.
  - E24는 worker 간 부하 불균형으로 말미에 한 장만 사용한 구간이 있다.
- **worker 수 결정:** GPU당 worker 2개는 시도하지 않았다. peak 11.3 GB에 worker당 2 GiB 여유를 더하면 24 GB를 넘기 때문이다. 이 이유로 1 worker/GPU를 유지했다.
- **실행 경로 검사 (`mri61_test.py`):** 6요청으로 아래를 확인했고 전부 통과했다.
  - 중단 후 재개: 3건 처리 후 중단, 손상된 tail 추가, 재개 시 미완료만 처리, torn line 제거
  - 재개 출력의 token이 D 출력과 6/6 동일
  - requests 변조 차단
  - 누락 detect(verify가 실패 코드 반환)
  - tech gate 실패 시 launch가 exit 2로 중단되고 출력 디렉터리 미생성

# Results

- 보고 파일: `results/iter_061/D_report_v2.json`, `E24_report.json`, 원시 출력 `gen_D_2w/`, `gen_E24/`, 선택 잠금 `data/selection_lock.json`.

D6은 기술 검증용이며 성능 추정이 아니다. E24는 24 cluster(다중 영상 24)이고 파일명·정답·source는 입력에서 제외했다.

| 조건 | E24 정확도 |
|---|---|
| T (text-only) | 0.500 |
| J (전체 영상) | 0.4375 |
| S_mean (개별 영상 평균) | 0.410 |
| V (S_i plurality vote) | 0.4375 |
| prior (가장 빈번한 정답 문자열) | 0.25 |
| any-S (사후 oracle, 실용 baseline 아님) | 0.479 |

- **paired 차이 (seed61, 10,000회 cluster bootstrap):**
  - J−T −0.0625, 95% CI [−0.208, 0.0625]
  - V−T −0.0625, 95% CI [−0.208, 0.0625]
  - J−V 0.000, 95% CI [−0.104, 0.125]
  - J−S_mean +0.028, 95% CI [−0.066, 0.135]
- **선택지 순서:** F와 R에서 T는 0.50/0.50, J는 0.417/0.458이다.
- **J와 T가 다른 cluster:** 8개다.
- **원천별(소표본):**
  - NOVA 7: T 0.50, J 0.50, S_mean 0.56
  - PubMedVision 7: T 0.43, J 0.50
  - BraTS-GLI 2: 모두 1.0
  - ISLES 3: T 0.67, J 0.17
- **형식:** strict v1 유효율은 전체 70%다. v2 기준 invalid는 T 6.25%, J 0%, S 0%다. T는 retry 46%였고 cap에서 EOS 없이 끝난 요청이 1건 있다.
- **비용:** T는 입력 token이 가장 적지만 출력이 길다(wall 합 3377초). J wall 합은 1184초, S 합은 3395초다. V 비용은 S 전체 합이며 J보다 요청이 많다.
- **독립 재계산:** 별도 정규식으로 T 0.500, J 0.4375를 다시 얻었다.
- **E64 확대 조건:** J−T와 V−T 점추정이 0.10 이상이 아니고 CI 상한도 0.10 미만이다. V−J, S_mean−J도 0.10 미만이어서 확대하지 않았다.
- **판정:** 사전 기준의 음성(영상 신호 CI 상한 10 pp 미만)에 해당한다. 현재 과제·입력에서 큰 추가 영상 신호가 약하다는 근거일 뿐, 모델 무능력이나 영상 무사용으로 확대하지 않는다.

# Goal Progress / Reused Assets

- **구분:**
  - 자료 준비는 통과했다.
  - 실행 유효성은 verify 문제 0건, tech 불일치 0건으로 통과했다.
  - 모델 관찰은 J−T −0.0625로 영상 신호가 text-only를 넘지 못한 것이다.
  - 방법 필요성(공동 입력 손실)은 V−J, S_mean−J 모두 문턱 미달이라 지지되지 않았다.
  - 신규 기여는 없다.
- **재사용:** `msd56_run.py`의 `load_model`, `env_info`, `build_inputs`, `generate`를 썼다. 필수 검사는 아래와 같이 수행했다.
  - 반입 blob 일치: 확인
  - 공식 processor와 입력 대조: 수행(D·E24)
  - T의 영상 token 부재: verify가 `n_image_tokens==0`으로 검사
  - J/S_i 영상 집합 연결: S_i가 J의 i번째 영상 slice와 같음을 검사
  - 독립 점수 계산: 수행
  - 변조·재개: 수행
  - tech gate 실패 시 nonzero 종료: 수행
  - 비용: `time.perf_counter` 기반 wall을 기록
- **미검증 범위:**
  - 24 cluster는 확증용이 아니다.
  - 동일 질문에 임상 소견이 포함된 BraTS·ISLES는 text-only가 유리하다.
  - 실제 모델 호출 시 `msd56_run.generate` 내부는 time.time을 쓴다. 비용 집계는 monotonic wall을 쓴다.
  - 다른 모델 비교, 직접 SFT, encoder+head 비교는 실행하지 않았다.

# Problems

**현재 결론 무효:** 없음.

**재사용 전 수정:**
- D protocol은 `mri61_run.py` 수정 전에 잠갔다. 파일이 바뀌어 이후 `D_protocol.json` verify는 digest 불일치가 난다. D 결과 verify는 수정 전에 통과했다. E24는 수정 후 코드로 새로 잠가 일관하다.
- 평가 코드(`mri61_eval.py`)와 `mri61_parse.py`는 protocol 잠금 대상이 아니다. 평가 입력 provenance 잠금을 보강해야 한다.
- 영상은 원 QA에서 선택했으며, PubMedVision cluster는 논문 단위다. 환자 독립성이 없다.

**추후 개선:** worker 간 부하 불균형(정적 shard)으로 마지막 구간에 한 GPU가 놀았다. 동적 claim 방식으로 바꾸면 처리량이 개선될 것이다.

# Recommendation to GPT

- 이 과제에서 MedGemma의 영상 신호가 약하게 관찰됐으므로 MedGemma 전용 통합 방법 투자는 보류를 권한다.
- 다음 후보로 같은 고정 자료(NOVA 다중 영상 중심)에서 다른 VLM과 같은 T/J/S_i/V 조건 비교를 검토한다. 이때 BraTS·ISLES 같은 소견 서술형 문항은 text 유출 때문에 분리해서 봐야 한다.
- 자료 한계(정답 key 영상 선택·pretrained exposure)와 24 cluster의 정밀도를 리뷰에서 같이 판단해 달라.

SELF_CHECK: PASS
SUMMARY: OmniBrainBench brain MRI 진단 QA(E24, 24 cluster)에서 MedGemma 1.5의 J−T는 −0.0625 [−0.208, 0.0625]로 영상 신호가 text-only를 넘지 못해 E64 확대와 통합 방법 투자는 보류했다. 작은 개발 표본이고 소견 서술 문항은 text가 유리할 수 있다.