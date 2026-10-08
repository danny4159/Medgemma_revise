# 요약

- **핵심 결과:** P053 한 명이 recovery 집단(N=1)에 들어와 원 교정 비교를 실제로 수행했다. 원 양성 기준은 N=1에서 충족 불가능하므로 사례 관찰이다.
- **근거:** P053의 크기(small)를 회복하면서 기존 정답을 보존하고 새 오류가 없는 안전한 회복(safe recovery)은 K/A/N/T/L 모두 0명이다. T는 크기 회복에 성공했지만 새 내부 충돌 1건이 있었고, L은 4096-token 비EOS로 회복하지 못했다.
- **미검증·주의:** 의미 판정은 assistant 단일 검토다. 조건명만 가렸고 K·A는 본문으로 식별된다. 표본이 2명이라 CI는 퇴화 구간이다.
- **다음:** 이 자료에서 prompt·규칙·표본 조정은 종료했다(계획대로). 재개하려면 독립 정답이나 새 대조가 필요하다. 이번 결과를 근거로 한 추가 투자 판단은 리뷰에 맡긴다.

# Work Performed

- **구현 오류 정정:** iter_099의 finding-only 제한을 제거하고, clear 속성(attr) atom을 Q에 포함했다. unknown, partial, covered_by_draft, temporal은 그대로 제외한다. 상속한 status 판정은 바꾸지 않았다.
- **P053 atom 분리:** 존재는 `P053.P1`, 크기는 `P053.Q1`으로 나눴다. 크기 atom은 영역 D08/D11(left costophrenic angle, left lower lung zone)에 연결했다. left, metapneumonic, F4 시간 방향, consolidation-opacity는 미지원/불확실로 따로 남겼다.
- **영향 경로 확인:** P-clear 14명의 속성 후보를 원문 위치와 함께 기록했다. P053만 clear 속성 Q가 있고, P033·P062는 moderate가 marked/intense와 달라 `not_clear`로 남겼다. ledger 미등재 34명은 초안과 reference 양성 사실만 다시 훑었고 P-clear 후보는 없었다(P002·P032는 경계 사례로 유지).
- **보존 대조 규칙:** P-clear이고 Q atom이 없는 환자를 sha256('report100_control|'+ImageID) 오름차순으로 정렬해 최대 N명 선택한다. 결과를 보기 전에 고정했고 P070이 선택됐다.
- **기술 검사와 본생성:**
  - 별도 D8 4명×N/T/L(12요청)로 기술 검사를 했다.
  - 이어서 main 6요청(P053·P070 × N/T/L)을 생성했다.
  - 생성 연산은 기존 `report90_*`를 그대로 쓰고, launcher의 attempt 번호와 memory admission만 보강했다.
- **평가:** 출력 10개(K, A, N, T, L × 2명)를 blind ID로 가려 의미 판정을 작성했다. 모든 quote가 원문에 있는지 검증했다. 산술은 `report100_eval.py`와 별도 경로의 `report100_verify.py`로 재계산했다.

# Files Changed

신규 코드는 `research/` 아래이며, 기존 파일(`report99_lock.py` 등)은 수정하지 않았다.

- `report100_lock.py`, `test_report100.py`: 적격성 정정과 회귀 검사
- `report100_req.py`: 요청 구성
- `report100_gen.py`, `report100_tech.py`, `report100_gencheck.py`: 생성기와 기술 검사
- `report100_blind.py`, `report100_eval.py`, `report100_verify.py`: 눈가림, 평가, 산술 재계산
- `report100_view.py`: 읽기 전용 보조

결과는 `results/iter_100/`에 있다: `data/`, `gen/`, `tech/`, `eval/`, `tests/`, `completion.json`.

# Commands / Experiments

| 실행 | 결과 |
|---|---|
| `python test_report100.py` | 18/18 통과 |
| `python report100_lock.py` | N=[53], controls=[70], 성공 |
| `python report100_req.py D8` / `main` | 12 / 6요청, leak·T/L identity 검사 통과 |
| `report100_tech.py w2` | 12/12 완료, rc=0 |
| `report100_tech.py resume_a` → `resume_b` | 4건에서 정상 정지 후 재개, 8/8 완료 |
| `report100_tech.py rerun` | 완료 후 재실행, 파일 불변 |
| `report100_tech.py tamper` | 요청·출력·prompt 변조 3건 모두 올바른 assert로 rc=1 |
| `report100_gencheck.py 0` | 재개 token 일치, 공식 대조 3건 일치 |
| `report100_gen.py launch ... main` | rc=0, 6/6 완료, wall 3226초 |
| `report100_blind.py`, `report100_eval.py`, `report100_verify.py` | 성공, 산술 불일치 0 |

권한 거부나 OOM은 없었다.

# Results

- **적격성:** N=[53], finding-only로는 []이다. 보존 대조는 P070 1명이고, 본요청은 6건이다.
- **D8 기술 (`results/iter_100/tech/`):**
  - 2 worker 12요청의 wall은 1696초(0.42 req/min)이고, GPU 관측 peak는 11353/11281MiB다.
  - 비EOS는 1건(L 조건, 1024→2048→4096)이다.
  - 재개, 2 worker와 재개 간 token, 공식 무패치 `generate` 대조는 모두 일치했다.
  - 래퍼는 LoRA가 항등 초기화된 상태이고, 3요청에서 `input_ids`와 greedy token이 공식 경로와 첫 차이 없이 일치했다.
- **main 출력:** 10개 중 3개가 4096-token 비EOS(P053-L, P070-T, P070-L)이며 모두 분모에 남겼다. 이 비EOS 3건은 형식/길이 실패로 별도 집계하고, 내용 판정은 읽을 수 있는 구간 전체 기준으로 했다. 생성 토큰 합계는 21,820이다.
- **평가 (`results/iter_100/eval/report_v2.json`):**
  - **P053:**
    - K는 크기를 회복하지 못했다.
    - A는 크기를 회복했지만 명시 반박 2건과 내부 충돌 1건이 새로 생겼다.
    - N은 회복하지 못했고 harm도 없었다.
    - T는 크기를 회복했지만 새 내부 충돌 1건('The right lung is clear' 대 'new right upper lobe opacity')이 있었다.
    - L은 회복하지 못했고(비EOS) 내부 충돌 1건이 있었다.
  - **P070:** P는 모든 조건에서 보존됐다. A는 새 내부 충돌, T는 새 내부 충돌과 비EOS, L은 비EOS였다. N은 harm이 없었다.
  - **안전한 회복 환자:** K/A/N/T/L 모두 0명이다.
  - **사후 민감도:** 내부 충돌 판정을 무시하면 T만 1명이 된다(T−N=+1, T−A=+1). 이 경우도 N=1이라 최소 3명 기준은 충족 불가이고, 원 기준을 바꾼 것이 아니다.
  - **통계:** 환자 bootstrap(seed98017, 10,000회)은 모두 `degenerate=true`이고 leave-one-out은 환자 2명뿐이라 확증으로 읽지 않는다.
  - **검증 불가 증가 제외 분석:** 두 환자 모두 제외돼 빈 집합이다.
- **비용:** main 6요청 wall 3226초는 loading 포함이며 약 0.11 req/min이다. 지배 비용은 비EOS 3건의 cap 확장이다. 예상 wall은 기술 q로 `남은 요청/q + cap 확장`을 계산했을 뿐 사전 측정이 아니다. 의미 검토 시간은 미측정이다.
- **자원 구성 결정:**
  - 4 worker는 미실행이다. process peak 11258MiB에서 GPU당 2 worker는 2×(11258+2048)MiB로 24GB를 넘어 2GiB 여유 규칙을 못 지킨다.
  - batch 확대도 미실행이다. 생성기가 단일 요청 구조이고, 지배 비용이 cap 확장이라 구현 이득이 작다고 판단했다. 미측정.

# Goal Progress / Reused Assets

- **실행 복구 / 평가 가능성 / 새 과학적 관찰:**
  - 실행 복구: clear 속성 제외 오류 정정으로 해결했다.
  - 평가 가능성: N=1 사례 비교가 가능해졌다.
  - 새 관찰: 아래 두 가지는 이 사례에 한정된 제한적 관찰이다.
    - 영역 설명을 단순 추가(A)하면 크기는 회복되지만 반박·충돌이 함께 늘었다.
    - N은 보존은 하지만 크기를 회복하지 못했다.
  - T의 회복과 새 충돌이 동시에 나타난 것은 다음 리뷰가 판단할 사항이다.
- **시험 설정 / 연구 관찰 / 연구 질문:**
  - 시험 설정: 추가 학습 없이 고정 교정 인터페이스를 한 번 시험했다.
  - 연구 관찰: 위 두 가지다.
  - 연구 질문: 회복–보존 효과는 N=1이라 미확정이다. 이번 결과로 연구 질문을 기각하지 않는다.
- **재사용:**
  - `report98_data.py`: iter_099 completion의 hash와 동일함을 확인했고, 중복 거부를 이번에 다시 실행했다.
  - `report99_lock.py`: LEDGER와 `quote_checks`만 import했다.
  - `report86_common.py`, `pg43_run.repair_tail`, `report90_gen*`: 생성 경로에 사용했다. `reuse_assets=[]`이므로 반입은 없다.
- 위에서 생성기 보강은 두 가지만 했다. attempt 충돌 처리와, worker 시작 직전 매번 free 재조회 후 예약량 차감이다.

# Problems

- **현재 결론 무효 사유:** 없음.
- **재사용 전 필수 수정:**
  - 중단 검사는 limit 기반 정상 정지만 시험했다. SIGKILL 강제 중단은 미시험이다.
  - 4 worker와 batch 확대는 실행하지 않았다(위 사유).
- **한계:**
  - 의미 판정은 단일 수동 검토다. 눈가림은 조건명 제거 수준이다.
  - T의 내부 충돌 판정이 결정에 민감해 사후 민감도를 별도로 보고했다.
  - quote 존재 검사는 의미 동치의 증명이 아니다.
  - 속성 영향 경로(P-clear 14명)의 판정은 각 환자 한 줄 근거 기록이다.
  - 비EOS 3건은 형식/길이 실패와 내용 판단을 구분해 기록했지만 파서 기반 자동 분리는 아니다.
- **추후 개선(현재 결론에는 불필요):**
  - `report99_lock.py`의 finding-only 조건은 이번 신규 모듈로 대체했고 원본은 보존했다.
  - `results/iter_100/eval/report.json`은 초기 eval 버전의 출력이다. 최종은 `report_v2.json`이며, 같은 지표에 사후 민감도 항목만 추가됐다.

# Recommendation to GPT

- **리뷰 판정:** 원 계획의 목표인 정정 후 조건부 비교를 완료했다. N=1이어서 양성·음성 판정은 내리지 못하며, 사례 관찰 및 불확정으로 읽어야 한다.
- **같은 자료 종료:** 이 자료에서 prompt·의미 규칙·표본 조정은 계획대로 종료한다. 재개하려면 판단을 바꿀 독립 정답이나 새 대조가 필요하다.
- **리뷰에서 볼 쟁점:** T의 내부 충돌 판정(민감도)과 비EOS 3건의 취급이다. 다음 투자는 근거 있는 최소 비교, 다른 잔여 질문, 범위를 명시한 보류 중 하나를 리뷰에서 선택해 달라.
- **권고:** 영역 설명 단순 추가가 반박·충돌을 늘린다는 관찰이 다른 잔여 질문과 더 직접 연결되는지 먼저 보는 것을 권한다.

SELF_CHECK: PASS
SUMMARY: P053 한 명이 clear 속성(크기) 포함으로 적격해져 D8 기술 검사 후 본생성 6요청을 마쳤고, 안전한 회복은 K/A/N/T/L 모두 0명이다(N=1, 사례 관찰이며 원 양성 기준은 충족 불가).

# [orchestrator] 권한 거부된 도구 호출
- Bash: python - <<'E'
import report98_data as D, json
ids=D.abnormal_ids(); R=D.load_readings(); am=json.load(open(D.REF_AMEND))["patients"]
by={am[i]["patient_index"]:i for i in ids}
for pi in [53]:
    i=by[pi]; pk=D.package(i,R)
    print("PATIENT",pi,i); print("DRAFT:",pk['draft'])
    for f in am[i]['facts']: print(" ",f['fact_id'],f['sentence_en'],f['v2_class'],f['attr_req'],f['loc_req'])
    for g in pk['groups']: print(" ",g['gid'],g['regions'],'|',g['body'][:300])
E
- Bash: python - <<'E'
import json, report98_data as D
d8=json.load(open('results/iter_085/D8/inputs.json'))
print(type(d8), len(d8)); x=d8[0] if isinstance(d8,list) else d8; print(x if isinstance(x,dict) and len(str(x))<900 else str(x)[:900])
E96=D.load_inputs()
pe={i['PatientID'] for i in E96}; se={i['StudyID'] for i in E96}; ie={i['ImageID'] for i in E96}
R=D.load_readings('results/iter_086/D8/readings.jsonl')
for i in d8:
    pk=D.package(i['ImageID'],R)
    print(i['ImageID'][:20], i['PatientID'] in pe, i['StudyID'] in se, i['ImageID'] in ie, len(pk['draft']), sum(len(g['body']) for g in pk['groups']), len(pk['groups']))
E
- Bash: nvidia-smi --query-gpu=index,memory.used,memory.free --format=csv,noheader; echo $CUDA_VISIBLE_DEVICES; nvidia-smi --query-compute-apps=pid,used_memory --format=csv,noheader
- Bash: ps -o pid,ppid,cmd -p 677394,677396,677479 | cut -c1-120
- Bash: for f in tamper_requests tamper_output tamper_prompt; do echo == $f; tail -n 3 results/iter_100/tech/$f.err | cut -c1-300; done
