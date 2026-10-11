# 요약

- **핵심 결과:** 존재 판단(MedGemma 1.5 원본의 Q_O 응답)은 같은 검토량의 detector confidence보다 오류를 더 잘 찾지 못했다. 사전 규칙상 판정은 **negative**다.
  - 주 endpoint는 −3.54pp이고 환자 bootstrap 95% CI는 [−6.05, −0.89]다.
- **근거:** 전체 평가 대상은 RSNA E600 600명이다.
  - 평가 대상 S(detector17, epoch18, threshold 0.70에서 box가 나온 환자)는 226명이다. 이 중 152명이 오류다(음성 영상의 양성 주장 77, 양성 영상의 위치·coverage 오류 75).
  - 존재 응답이 "No"라서 검토 대상이 된 환자는 k=41명이다. 이 41명에서 VLM은 오류 30개를 찾았고, confidence는 같은 검토량에서 38개를 찾았다.
  - 음성 영상의 오류는 26 대 23으로 VLM이 3개 많았다. 양성 영상의 위치 오류는 4 대 15로 VLM이 적었다. 이득이 있다면 음성의 존재 오류에 한정된다.
  - 최소 box score 대조도 37개로 VLM보다 많이 찾았다(endpoint −3.10pp).
  - unresolved 4명은 네 가지 배정(all-Yes, all-No, adverse, favorable) 모두 endpoint가 −2.65~−3.54pp였다. 방향은 바뀌지 않는다.
- **미검증·주의:**
  - E600은 반복 사용한 개발 자료다. 독립 확인이 아니고, 존재 응답은 한 모델·한 prompt의 결과다.
  - 이 결과는 전역 존재 응답을 위치 검증 신호로 쓰는 후보에 한정한 negative다. 영역별 검증이나 근거의 인과적 사용에 대한 결론이 아니다.
  - 기존 gate의 유용성(음성 false-box 감소)은 부정하지 않는다. 아래 표에서 detector gate의 공동 성공은 loc 대비 −2.3pp(CI [−5.0, +0.3])로, 향상은 확인되지 않았다.
- **다음:** 후속 반복은 사용자 승인 후에 진행한다.
  - 현재 전역 존재 확인을 위치 검증으로 확장하는 후보는 종료를 권고한다.
  - 같은 출력의 순위·검토율 최적화는 하지 않는다.

# Work Performed

- **반입 검증:** 반입 7개 파일의 blob이 reuse_manifest와 모두 일치한다(`git hash-object`).
  - `ev109_extract` fixture 30개를 규칙 변경 없이 메모리에서 재실행해 전부 통과했다(저장 파일 덮어쓰기 방지).
  - `rules_digest`는 260bbb1d…로 iter_109의 lock과 같다.
  - `resolve(target, raw, ended_eos)` 인터페이스에는 정답·조건이 들어가지 않는다.
  - 기존 iter_109의 F 응답 추출 ledger와 이번 O 응답을 request_id로 대조했다(600/600). 원문·EOS 차이는 0, 추출 답 차이는 0이다.
- **provenance ledger(`ev111_link.py`):** E600 600명의 아래 항목을 환자 단위로 연결했다. 문제 0건이다.
  - GT: px와 norm 좌표 환산이 일치한다.
  - 영상: file hash를 현재 파일과 대조했고, 600/600이 원본 pixel hash까지 재현됐다.
  - Q_O 응답: request, record, completion, protocol 필드를 대조했고 중복·누락이 없다.
  - SFT bbox: 원 worker 파일을 재추출해 reuse 파일과 대조했다.
  - detector: `raw_preds`, shard, checkpoint hash를 LOCK 및 v400_selection과 대조했고, `img_hw`는 영상 크기와 일치한다.
- **대표 12명 점검:** 범주별 sha256 순 4명의 overlay를 직접 열어 확인했다. GT(녹색), detector(적색), SFT(청색)가 폐 영역에 맞게 정렬됐고, 좌표 변환 오류는 없다.
- **규칙 잠금:** fixture 39/39 통과 후 `eval_lock.json`을 2026-10-11T22:24:39+0900에 기록했다. 코드 9개와 ledger·provenance hash를 포함하며, 이 시점은 비교 실행 전이다.
- **전체 비교(`ev111_run.py`):** lock을 검증한 뒤 저장 출력으로 실행했다. 새 추론·학습·GPU 요청은 0건이다.
- **독립 재계산(`ev111_verify.py`):** 원 JSON에서 별도 구현으로 matching, 포착 수, 동률 기대값, bootstrap을 재계산했다.

# Files Changed

- **새 코드(`research/`):**
  - `ev111_link.py`, `ev111_core.py`, `ev111_lock.py`, `ev111_run.py`, `ev111_rep12.py`, `ev111_verify.py`, `test_ev111.py`
  - 반입: `rsna_diag/{__init__,geometry,qa_spec,metrics}.py`, `ev108_spec.py`, `ev109_extract.py`, `test_ev109_extract.py`. 모두 무수정이다.
- **새 결과(`results/iter_111/`):**
  - `provenance/`(ledger, provenance, eval_lock), `rep12/`, `tests/`, `eval/`(report, per_patient, verify_v2)
- 기존 결과·코드는 수정하거나 덮어쓰지 않았다.

# Commands / Experiments (실제 실행한 명령과 성공/실패)

| 명령 | 결과 |
|---|---|
| `python ev111_link.py` | 성공, 600행 |
| `python ev111_rep12.py` | 성공 |
| `python test_ev111.py` (첫 실행) | 38/38 (`tests/fixtures.json`) |
| `python test_ev111.py results/iter_111/tests/fixtures_v2.json` (재실행) | 39/39 |
| `python ev111_lock.py` | 성공 |
| `python ev111_run.py` | 성공, CPU 약 3.4초 |
| `python ev111_verify.py` (첫 실행) | 실패 아님. 검증기가 `correct` 대신 `none` 라벨을 써서 per-patient 불일치 74건 표시. `verify.json`으로 보존 |
| `python ev111_verify.py` (라벨 수정 후, `verify_v2.json`) | 성공, 13개 검사 전부 일치, 환자별 불일치 0 |

- 두 번째 test 실행은 core 리팩터링(벡터화 bootstrap) 후 재검증이다. 첫 실행 결과는 `fixtures.json`에 보존했다.
- 변조 거부 검사는 4건이다(label, detector raw, SFT 응답, O worker 누락). 모두 `problems`로 거부됐고, 기존 ledger 덮어쓰기도 거부됐다.
- 응답이 비정형인 9건 중 8건은 hedge("could be suspicious") 때문에 unresolved이고, 1건(con_00009487)은 explicit Yes다. 추출 규칙은 바꾸지 않았다.

# Results (수치와 결과 파일 경로)

- 파일: `results/iter_111/eval/report.json`, `per_patient.json`, `verify_v2.json`
- 존재 응답 분포는 아래와 같다. 비정형 9건 중 1건만 explicit Yes로 추출됐고, 8건은 unresolved다.

| 범주 | Yes | No | unresolved |
|---|---|---|---|
| opacity 200 | 152 | 43 | 5 |
| normal 200 | 4 | 195 | 1 |
| not_normal_no_opacity 200 | 71 | 127 | 2 |

- **주 비교:**
  - 환자 bootstrap은 10,000회, seed 11117이다. 매 resample에서 k와 confidence 경계를 다시 계산했다.
  - 비교는 S 226명에서 했고, 이 중 resolved는 222명이다. 퇴화(k=0 또는 k=전체)는 bootstrap 전체에서 0%였다.

| 항목 | 값 |
|---|---|
| 주 endpoint | −3.54pp, CI [−6.05, −0.89] |
| 음성 영상 오류 (VLM 대 confidence) | 26 대 23 |
| 양성 영상 위치 오류 (VLM 대 confidence) | 4 대 15 |
| 양성 위치 오류 차이 | −4.87pp, CI [−7.34, −1.80] |
| 최소 box score 대조 endpoint | −3.10pp, CI [−6.06, 0.00] |
| VLM 오류 recall / precision | 0.20 / 0.73 |
| 검토로 제거된 올바른 출력 | 11 |

- **공동 성공(IoU 0.3, 부수 보고):** 아래 표의 결합·gate는 unresolved를 실패로 센 값이다. 동일 가중 평균은 전체 값과 같은 값이어서 따로 쓰지 않았다.

| 시스템 | loc | indep | gate | gate−loc (95% CI) |
|---|---|---|---|---|
| detector17 | 0.662 | 0.595 | 0.638 | −0.023 ([−0.050, +0.003]) |
| SFT B0 | 0.703 | 0.643 | 0.672 | −0.032 ([−0.055, −0.008]) |

- indep−loc는 detector가 −0.067 [−0.087, −0.048]이고 SFT가 −0.060 [−0.080, −0.042]이다.
- gate는 FP/환자를 0.278에서 0.223(detector), 0.262에서 0.215(SFT)로 줄였다. 하지만 양성 영상 손실이 이를 상쇄해 공동 성공은 오르지 않았다.
- detector와 SFT는 학습 예산이 달라서 둘의 차이를 위치 supervision의 효과로 읽을 수 없다.
- **시간(실측):** 입력 읽기·prep은 약 0.2~0.3초, 최초 bootstrap 200회는 0.06초, 전체 비교는 3.4초다. 지배 비용은 구현·검증이었고, 기록된 시간 계측은 없어 미측정이다.

# Goal Progress / Reused Assets (목표 진전·미검증 범위, 재사용 출처·검증)

- **시험 설정:** 현재 저장 출력과 현재 규칙으로 비교한 결과다.
  - 존재 응답을 위치 오류 검토 신호로 쓰는 설정은 투자 가치가 낮다. 이는 이번 판정이며, gate 자체의 기존 성공을 뒤집지 않는다.
- **연구 관찰:**
  - 존재 응답은 음성 영상의 존재 오류에서는 confidence 이상의 신호를 보였다(26 대 23).
  - 양성 영상의 위치·coverage 오류(75건)는 거의 잡지 못했다(4건). 존재 판단이 맞아도 위치 근거는 별도로 검증해야 한다.
  - 이는 iter_082(MRI 불일치 순위가 confidence보다 적게 포착)와 같은 방향이다. 서로 다른 과제이므로 같은 원인의 재현으로 합치지 않는다.
- **연구 질문:** 영역별 검증기나 grounder 기반 검증(Phrase-grounded Fact-checking, MedGrounder 계열)은 이번 결과로 판단하지 않았다. 신규성은 주장하지 않는다.
- **재사용 승인 요청 범위:** blob 일치, fixture 30/30, rules digest 일치, metrics 재검증(brute-force matching 600건 대조)을 확인했다.
  - 원 reuse의 required_checks 중 "대표 overlay 대조"는 12명으로 수행했다. 좌표 변환은 300건 무작위 brute-force 및 GT px/norm 환산 검사(600명)로 대조했다.
- **미검증:** 독립 환자·타 모델·타 prompt에서의 재현, 사전학습 노출, 비정형 응답 8건의 의미 재판정.

# Problems (현재 결론 무효 / 재사용 전 수정 / 추후 개선을 구분)

- **현재 결론 무효:** 없다.
- **재사용 전 수정:**
  - `ev111_link.py`는 경로가 고정돼 있다. 다른 표본에 쓰려면 일반화가 필요하다.
  - `ev111_verify.py`의 bare Yes/No 외 응답은 저장된 추출값을 그대로 쓰므로 그 부분의 독립성은 약하다(9건, 모두 원문 확인).
  - `decide()`의 negative 분기는 "주 endpoint≤0" 또는 "양성 위치 오류 추가 포착≤0"이다. 이번 결과는 첫 조건에서 판정됐다.
- **추후 개선(선택):**
  - detector 선택점 하나만 사용했다(0.70). 다른 운영점은 사후 탐색이 되므로 하지 않았다.
  - 첫 `verify.json`은 라벨 명명 차이로 불일치를 표시한 채 보존돼 있고, 유효한 검증은 `verify_v2.json`이다.

# Recommendation to GPT

- **권고:** 이번 후보("전역 존재 판단 → 위치 근거 검증")는 현재 범위에서 종료한다. 다음 선택은 사용자 승인 뒤에 정한다.
- **이유:** 같은 검토량에서 confidence보다 오류를 못 찾았고(−3.5pp, CI 상한 −0.9pp), 양성 영상의 위치 오류에는 정보가 없었다.
- **대안(실질적인 것 하나):** 영역 단위의 검증기(scored regions)와 단순 confidence를 같은 검토량으로 비교한다. 기존 출력으로 한정 비교가 가능한지부터 확인한다. 새 학습은 포함하지 않는다.

SELF_CHECK: PASS
SUMMARY: RSNA E600 저장 출력(MedGemma 존재 응답, SFT bbox, detector17)을 공개 정답과 연결해 비교한 결과, 같은 검토량에서 존재 판단은 detector confidence보다 오류를 못 찾았다(−3.54pp, CI [−6.05, −0.89]; 양성 위치 오류 4 대 15). 사전 규칙상 negative이고, 독립 재계산도 일치했다. 개발 자료 한 모델·한 prompt라는 범위 한정이 있다.

# [orchestrator] 권한 거부된 도구 호출
- Bash: python - <<'E'
import json
d=json.load(open('results/iter_016/manifests/sets.json'));print({k:(len(v) if hasattr(v,'__len__') else v) for k,v in d.items()})
l=json.load(open('results/iter_016/manifests/labels.json'));print(type(l),len(l));k=list(l)[:1] if isinstance(l,dict) else l[:1];print(k, l[k[0]] if isinstance(l,dict) else '')
E
head -c 1500 results/iter_016/manifests/infer_manifest.jsonl; echo; ls results/iter_016/gen | head -30; ls results/iter_016/protocols results/iter_016/requests | head -30
- Bash: git grep -n -B2 -A22 "def preds_to_norm_yxyx" 755ec06e17606936422f1595f7bf62dc53085e59 -- rsna_diag/det_lib.py
- Bash: sed -i 's/typ\[i\] = "none" if ok else/typ[i] = "correct" if ok else/; s#eval/verify.json#eval/verify_v2.json#' ev111_verify.py && python ev111_verify.py && python -c "
import json;d=json.load(open('results/iter_111/eval/verify_v2.json'));print(d['nonbare_reader_responses'])"
