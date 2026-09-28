# 요약

- **핵심 결과:** RSNA bbox-only SFT(B0)는 학습하지 않은 "지정 사분면만 선택" 질의에서 base(M0)보다 전체 F1은 높지만(E60, S 차이 +0.221, 95% CI [0.169, 0.271]), 이는 대부분 검출 품질 향상이지 질의별 선택 능력이 아니다. B0 직접 선택 점수는 "항상 전체 bbox를 그대로 반환"하는 Copy baseline과 통계적으로 구별되지 않는다(차이 −0.006, CI [−0.040, 0.027]). 사전 고정한 다중-사분면 환자 22명(E60 primary 부분집합)에서 B0 직접 선택의 "네 질의 모두 정답" 성공은 0/22(95% 정확 CI 상한 15.4%)이고, 같은 B0 예측 bbox에 규칙(사분면 필터)만 적용하면 11/22(50%, CI [28%, 72%])다.
- **근거:** D24(488요청, 동작 확인)와 E60(720요청, 가능성 탐색) 모두 실제 GPU 생성으로 완료했고, 독립 공식 tensor 대조·adapter digest·재생성 결정성 sanity 14/14 통과, provenance·완료 검증을 통과했다. 환자-영상 대응 대조에서 B0는 실제 영상별 반응(real−donor +0.186, CI [0.132, 0.238])을 보여 순수 위치 prior는 아니지만, 질의 배정 대조(C_query)는 M0·B0 모두 CI가 0을 가로질러(M0 CI下 0.0003, B0 CI下 −0.0022) 질의 조건화의 뚜렷한 증거가 없다.
- **주의·미검증:** 이 결과는 E60(개발 자료, n=60)의 관찰이며 사전 등록한 확대 기준(정밀도 보완·모듈형 격차 후보)을 충족해 E200(200명) 확대를 시작했으나, 세션 종료 시점까지 완료하지 못했다(V_M0 560건 중 약 368건 진행, V_B0·RD_M0는 미시작). 조건부 seed(B29/B43) 재현과 독립 확인은 전혀 실행하지 못했다.
- **다음:** E200_extra 생성은 재개 가능한 상태로 남아 있다(요청별 append, resume 지원). 다음 세션에서 이어서 완료하고, 사전 등록한 양성/음성/불확정 기준으로 최종 판정해야 한다.

# Work Performed

1. `plan.md`/`plan.json`(iter_026)을 읽고 RSNA 영역 선택 진단 파이프라인(`rsna_diag/roi26_*`)을 신규 구현했다. roi25/roi23의 승인된 모듈(geometry, parse, metrics, lora, generate, eval_gate, inputs, queue_lock, lock_protocol, roi23_data)을 그대로 재사용하고, 새 spec(V/O/RD 조건, 사분면 direct prompt), 요청 빌더, protocol 잠금, worker/실행기, 평가(S_i/Q4_select/C_query/환자 영상 대응), decide 모듈을 작성했다.
2. GPU 실행 전 sanity(`sanity_iter026.py pre`): 독립 경로(tokenizer.apply_chat_template + processor.__call__, `add_special_tokens=False`로 중복 BOS 수정 확인)로 구성한 tensor가 `generate.build_inputs`와 input_ids/attention_mask/pixel_values/token_type_ids 모두 일치함을 확인했다(6/6). B0 adapter digest가 iter_012 기록과 일치함을 확인했다.
3. GPU 처리량 pilot(`throughput_iter026.py`): 같은 24요청(D V/O 혼합)을 2 worker(1/GPU)와 4 worker(2/GPU)로 비교했다. 2w: 597s(2.41 req/min), peak 8.9GB/GPU. 4w: 619s(2.33 req/min), peak 17.6GB/GPU. 표본이 작고 단일 비EOS 요청(4000-cap 도달, 535s)이 양쪽 결과를 지배해 이 작은 pilot만으로는 4w의 이득이 뚜렷하지 않았다. 안전 여유(24GB 중 17.6GB, worker당 2GB 여유 조건 충족)와 iter_025의 기존 4w 이득 실측(11.9 vs 8.94 req/min)을 근거로 본실험은 4 worker(2GPU×2)로 진행했다.
4. D24(동작 확인) 488요청 생성: V_M0/V_B0(96×2), O_M0/O_B0(96×2), RD_M0(96), text-only M0/B0(4×2). 모두 완료·재검증(`n_expected==n_actual_unique`, `n_missing=0`, `returncodes` 전부 0).
5. GPU 실행 후 sanity(`sanity_iter026.py post`): 처음 실행에서 스크립트 자체 버그(무조건적 `load_adapter` 호출이 M0 재생성 probe를 오염시켜 4건 실패, 이어 B0 재적용 시 `apply_lora` 크래시)를 발견해 수정했다(M0 probe를 adapter 로드 전에 먼저 실행). 수정 후 8건 재생성 결정성 검사 포함 14/14 통과.
6. iter_025 marker 재해석(`analyze_iter025_marker.py`, GPU 없음): thinking marker 이후 최종 yes/no를 추출해 재파싱했다. limitation 기록과 정확히 일치하는 27건(M0 OB_T 24 + OC_T 3) 플립, 정답 20/오답 7을 재현했다. 원본 점수·gate는 변경하지 않았다.
7. D24 평가(`eval_iter026.py D`)·gate 판정(`decide_iter026_d.py`): V_M0 93/96, V_B0 96/96(≥92 기준) 통과 → E60 진입.
8. E60(가능성 탐색) 720요청 생성(V_M0/V_B0/RD_M0 각 240): 전부 완료·재검증. 세션이 한 번 중단(서버/네트워크)된 뒤 재개했으며, 중단 시점까지 완료된 D24 4개 job은 재검증만 하고 건너뛰었고 나머지(RD_M0, text)만 이어서 생성했다(중복 실행 없음, `roi26_run.run_one`의 완료 재검증 로직으로 확인).
9. E60 평가(`eval_iter026.py E60`): 다중-사분면 "진부분집합" 정의를 처음에는 primary+boundary(29명)로 잘못 계산했다가, 계획의 정의(primary 내부, 22명)와 대조해 버그를 발견·수정했다(`multi_quadrant_subset`을 primary_ids에만 적용, boundary는 별도 report). 수정 후 사전 계산값(22명, 상한 15.44%)과 정확히 일치함을 확인했다.
10. E60→E200 확대 판정(`decide_iter026_e60.py`): 계획의 세 조건(기능적 차이/정밀도 보완/모듈형 격차) 중 정밀도 보완과 모듈형 격차가 성립해 확대(`passed=true`).
11. E200_extra(140명, 1,680요청) 요청 생성·protocol 잠금·실행 시작. 세션 종료 시점까지 V_M0(560건 중 약 368건)만 진행 중이고 V_B0·RD_M0는 미시작. 프로세스는 4 worker 모두 정상 실행 중(resume 가능한 append 방식).

# Files Changed

신규(모두 `research/` 안, git 추적):

- `rsna_diag/roi26_spec.py`, `rsna_diag/roi26_data.py`, `rsna_diag/roi26_requests.py`, `rsna_diag/roi26_protocol.py`, `rsna_diag/roi26_gen.py`, `rsna_diag/roi26_run.py`, `rsna_diag/roi26_eval.py`, `rsna_diag/roi26_decide.py`
- `build_iter026_d.py`, `build_iter026_e.py`, `launch_iter026_d.py`, `launch_iter026_e.py`, `eval_iter026.py`, `decide_iter026_d.py`, `decide_iter026_e60.py`, `sanity_iter026.py`, `throughput_iter026.py`, `analyze_iter025_marker.py`

결과(모두 `results/iter_026/`, git 미추적):

- `manifests_d24_build.json`, `manifests_E60_build.json`, `manifests_E200_extra_build.json`
- `protocol_D.json`(및 재생성 전 `protocol_D_v1_superseded.json`), `protocol_E60.json`, `protocol_E200_extra.json`
- `requests/{D,E60,E200_extra}_*.jsonl`
- `gen/{D,E60}_*/`(완료), `gen/E200_extra_V__M0/`(진행 중)
- `sanity/sanity_{pre,post}.json`
- `eval/report_{D,E60}.json`, `decide/{D_decision,E60_to_E200_decision}.json`
- `analysis/iter025_marker_reanalysis.json`
- `throughput/{2w,4w}/`(pilot, 별도 계상)
- `launch_d.log`, `launch_d2.log`, `launch_e60.log`, `launch_e200_extra.log`

# Commands / Experiments (실제 실행한 명령과 성공/실패)

- `python sanity_iter026.py pre` → 6/6 PASS.
- `python throughput_iter026.py 2w` / `4w` → 둘 다 rc=0, 표본 작아 결정적이지 않음(본문 참조).
- `python launch_iter026_d.py` (workers=4, gpus=0,1, peak_gb=9) → 세션 중단으로 1차 실행은 부분 완료(V_M0/V_B0/O_M0/O_B0), protocol 재생성 후 재실행(`launch_d2.log`)으로 나머지(RD_M0, TEXT×2) 완료. 최종 7개 job 모두 `status: complete|verified_complete`, `returncodes` 전부 0.
- `python sanity_iter026.py post` → 최초 실행에서 버그로 4건 FAIL + crash, 수정 후 재실행 14/14 PASS.
- `python analyze_iter025_marker.py` → 성공, limitation 기록과 일치.
- `python eval_iter026.py D` / `python decide_iter026_d.py` → 성공, `passed=true`.
- `python build_iter026_e.py E60` → 성공(V/RD 240×3=720요청).
- `python -m rsna_diag.roi26_protocol --out results/iter_026/protocol_E60.json ...` → 성공.
- `python launch_iter026_e.py E60` (workers=4) → 성공, 720/720, rc 전부 0, wall 1107+423+584=2114s.
- `python eval_iter026.py E60`(1차, 진부분집합 정의 오류) → 수정 후 재실행, 성공.
- `python decide_iter026_e60.py` → `passed=true`(precision_supplement, modular_gap_candidate).
- `python build_iter026_e.py E200_extra` → 성공(1,680요청 예정).
- `python -m rsna_diag.roi26_protocol --out .../protocol_E200_extra.json ...` → 성공.
- `python launch_iter026_e.py E200_extra` → **미완료**: V_M0 진행 중(약 368/560), V_B0·RD_M0 미시작. 프로세스는 세션 종료 시점에도 정상 실행 중이었다(rc 미확인, 크래시 없음).

# Results (수치와 결과 파일 경로)

## D24 (동작 확인, `results/iter_026/eval/report_D.json`)

| 조건 | valid/96 | mean S | mean Q4 |
|---|---:|---:|---:|
| V_M0 | 93 | 0.1161 | 0 |
| V_B0 | 96 | 0.2551 | 0 |
| O_M0 | 96 | 0.4329 | 0.0417 |
| O_B0 | 96 | 0.4034 | 0.0417 |
| RD_M0 | 92 | 0.1738 | 0 |

text-only: M0는 4문항 중 3개 valid(그중 하나는 실제로 bbox를 반환 — 영상 없이도 위치를 "추측"하는 경향), B0는 4개 모두 valid_empty(항상 빈 목록). D gate(V_M0·V_B0 각 ≥92/96 valid) 통과 → `results/iter_026/decide/D_decision.json`.

## E60 (가능성 탐색, `results/iter_026/eval/report_E60.json`, n=60)

- valid_rate: V_M0 0.983, V_B0 1.0, RD_M0 0.979 (모두 ≥0.95 gate 통과).
- `V_B0 − V_M0`(S): +0.221, 95% CI [0.169, 0.271] (n=60, 환자 bootstrap).
- `V_B0 − Copy_B0`(S): −0.006, CI [−0.040, 0.027] — **B0 직접 선택은 전체 bbox 복사와 통계적으로 구별되지 않는다.**
- `Rule_B0 − V_B0(direct)`(S): +0.400, CI [0.316, 0.477] — 같은 B0 bbox에 규칙만 적용하면 압도적으로 낫다.
- C_query(질의 배정 대조): M0 +0.0197(CI [0.0003, 0.0412]), B0 +0.0139(CI [−0.0022, 0.0323]) — 둘 다 작고 B0는 CI가 0을 가로지른다.
- 환자 영상 대응(donor) 대조: M0 real−donor −0.009(CI [−0.042, 0.025], 0 포함), B0 +0.186(CI [0.132, 0.238], 0 미포함) — B0는 실제 영상에 반응하지만, 그 반응이 질의별로 달라지지는 않는다.
- **primary 진부분집합(n=22, 사전 계산값과 정확히 일치)**: B0 직접 Q4_select 0/22(정확 CI [0, 15.4%]), B0 규칙 Q4_select 11/22=50%(CI [28.2%, 71.8%]), M0 직접 0/22. boundary 진부분집합(n=7)은 B0 직접 0/7, B0 규칙 5/7(참고 자료).
- baseline: M0 rule/copy/empty S = 0.106/0.048/0.0. B0 rule/copy/empty S = 0.661/0.268/0.0.

E60→E200 확대 판정(`results/iter_026/decide/E60_to_E200_decision.json`): `functional_diff_candidate=false`(C_query CI가 0.05 기준 미달), `precision_supplement=true`, `modular_gap_candidate=true` → `passed=true`.

## E200 (규모 확대, 미완료)

`results/iter_026/requests/E200_extra_*.jsonl`(1,680요청) 생성·protocol 잠금 완료. `gen/E200_extra_V__M0/`만 부분 진행(세션 종료 시 약 368/560, worker 4개 정상 실행 중, 크래시 없음). V_B0·RD_M0는 시작 전. 평가·decide·조건부 seed·독립 확인은 전부 미실행.

# Goal Progress / Reused Assets (목표 진전·미검증 범위, 재사용 출처·검증)

**재사용:** `rsna_diag/{geometry,parse,metrics,lora,generate,prompts,inputs,eval_gate,queue_lock,lock_protocol,roi23_spec,roi23_data,qa_spec}.py`를 CODE_ASSETS의 approved 범위 안에서 그대로 가져와 새 protocol(`roi26_protocol.py`)에 재잠금했다. 실행기(`roi25_run.py`)의 GPU 배치·완료 재검증·claim 회수 패턴을 계승했지만, 이번 버전(`roi26_run.py`)은 새로 작성한 코드이므로 별도 검증이 필요하다(아래 Problems 참조).

**목표 진전:** 사용자 보완 지시의 핵심 질문("RSNA 위치 학습 개선이 학습한 지시의 좌표 출력에 머무는가, 아니면 새로운 질의에도 전이되는가")에 대해 E60(n=60, 720 실제 요청) 수준에서 **일관된 음성 방향 증거**를 얻었다: B0의 전체 F1 향상은 대부분 검출 품질 향상이며, "지정 사분면만 반환"이라는 새 지시에 맞춘 선택 정책은 관찰되지 않는다(Copy와 구별 불가, 진부분집합 Q4_select 0/22, C_query CI가 0을 가로지름). 반면 B0의 반응은 실제 영상에 특이적이다(donor 대조 유의). 이는 계획의 "결과별 다음 행동" 2번(좌표 출력만 개선, 다른 판단으로 전이 안 됨)에 해당하는 패턴이며, format/실행 오류로 설명되지 않는다(valid rate ≥95%, oracle에서는 문제없이 목록을 다룸).

**미검증:** (1) 이 패턴이 E200(n=200)에서도 유지되는지 — 특히 22명 subset의 0/22이라는 작은 표본의 상한(15.4%)이 66명으로 늘면 5.4%로 좁혀져 "10% 수준 신뢰할 만한 선택 가능성"에 대한 결론이 더 단단해질 수 있는데, 이 확인을 완료하지 못했다. (2) 조건부 seed(B29/B43) 재현 — 실행 조건(E200 양성 조건 또는 규칙 대비 명확한 격차)은 이미 충족될 가능성이 높지만 미실행. (3) 독립 확인 집단 — 계획대로 이번에는 열지 않았다(정상).

# Problems (현재 결론 무효 / 재사용 전 수정 / 추후 개선을 구분)

**현재 결론에 영향 없음 — 발견·수정 완료:**

- `sanity_iter026.py`의 최초 버전이 M0 재생성 probe 전에 B0 adapter를 무조건 로드해 4건 오탐(FAIL)과 crash를 일으켰다. 원인은 스크립트 자체의 순서 버그이며 실제 D24 본생성(`roi26_gen.py`, 독립 subprocess마다 fresh model 로드)에는 영향이 없다. 수정 후 14/14 통과로 확인했다.
- `eval_iter026.py`의 최초 버전이 "진부분집합"을 primary+boundary(29명)로 계산해 계획의 정의(primary 내부 22명)와 달랐다. 수정 후 사전 계산값(22명, 상한 15.44%)과 정확히 일치함을 확인했다. E60→E200 decide는 이미 수정 후 값으로 재실행했으므로 이번 보고서의 판정은 유효하다.

**재사용 전 확인이 필요함(다음 세션에서 E200/seed를 이어갈 때):**

- `roi26_run.py`/`roi26_gen.py`는 iter_025 needs_fix 결함(완료 요청의 입력 재검증, 자식 소유권 회수, tail 복구)을 상속했을 수 있다. 이번 세션에서 실제 중단(서버 장애)과 재개가 한 번 발생했고, 재검증(`verify_job`/`verify_completion`)이 정상 작동해 중복·손상 없이 이어졌음을 확인했지만(D24의 4개 job이 "verified_complete"로 안전하게 스킵됨), 의도적인 kill-and-resume 테스트나 변조 거부 테스트(계획 Implementation Task 7·8)는 별도로 수행하지 못했다.
- E200_extra 실행이 이번 보고서 작성 시점에도 계속되고 있다. 다음 세션은 재개 전에 `find results/iter_026/gen -name "*.lock"`으로 살아있는 프로세스 여부를 반드시 확인해야 한다(살아있으면 강제 종료하지 않고 대기해야 한다).

**추후 개선(현재 결론을 막지 않음):**

- V/O 직접 prompt에서 M0가 자주 4000-token 상한까지 비EOS로 생성해(관찰된 예: 단일 요청 535–600초) 처리량이 크게 느려졌다(초기 pilot 측정 2.3–2.4 req/min, 이는 특정 non-EOS 요청이 지배한 값이며 job 전체 평균은 7–32 req/min으로 더 높았다). 이 현상 자체가 M0의 새 prompt 형식에 대한 안정성 문제일 수 있어 별도로 기록할 가치가 있으나, 이번 진단의 핵심 결론(선택 능력 부재)에는 영향을 주지 않는다(D24/E60 형식 valid rate는 모두 gate 기준을 통과했다).
- `throughput_iter026.py`의 2w/4w pilot이 단일 non-EOS 요청에 지배되어 결정적이지 않았다. iter_025의 기존 4w 이득 실측(peak 17.6GB/GPU, 안전 여유 확인됨)을 근거로 4 worker를 채택했으나, 더 큰 표본에서 재비교하면 다른 결론이 나올 수 있다.

# Recommendation to GPT

1. **다음 세션에서 우선할 일**은 E200_extra(V_M0/V_B0/RD_M0)를 완료하고, `eval_iter026.py E200` → 조건부 seed decide → (조건 충족 시) B29/B43 평가까지 계획대로 이어가는 것이다. 코드는 이미 작성·검증됐고 재개 가능하다.
2. E60의 결과 패턴(직접 선택 ≈ 전체 복사, 규칙이 압도적으로 우수, C_query 미미)은 이미 상당히 명확하다. E200에서도 재현되면(특히 66명 subset에서 0/66 또는 낮은 비율 지속) 계획의 "음성 결과와 다음 행동"에 따라 **B0 예측 bbox + 외부 규칙(모듈형 baseline)**을 보존하고, 내부 직접 선택 능력을 위한 추가 loss 투자보다 강한 직접 질의 SFT 또는 다른 연구 질문으로의 전환을 검토하는 것이 합리적으로 보인다. 다만 이는 E200 완료 후 확정할 판단이며, 이번 결과만으로 미리 단정하지 않는다.
3. M0의 비정상적으로 높은 non-EOS 비율(이 새 prompt 형식에서)은 별도로 기록해둘 가치가 있는 관찰이다. 필요하면 다음 계획에서 진단 항목으로 명시할 수 있다.

SELF_CHECK: FAIL
SUMMARY: D24(488건)·E60(720건) 실제 GPU 생성·검증을 완료해 "RSNA bbox SFT는 지정 사분면 선택에 전이되지 않고 전체 bbox 복사와 구별되지 않는다"는 일관된 관찰을 얻었고 E200 확대 조건을 충족했으나, E200(1,680건) 생성이 세션 종료 시점까지 미완료(약 368/1,680)여서 계획의 규모 확대·조건부 seed·최종 판정 단계는 다음 세션으로 넘어간다.

# [orchestrator] 권한 거부된 도구 호출
- Bash: find results/iter_026/gen -maxdepth 1 -type d 2>/dev/null
echo ---
for d in results/iter_026/gen/*/; do
  if [ -f "${d}completion.json" ]; then echo "COMPLETE: $d"; else echo "INCOMPLETE: $d"; fi
done
- Bash: cat agent/../../agent/runs/iter_026/review.md 2>/dev/null | head -100
- Bash: cat results/iter_026/launch_e60.log | tail -10
find results/iter_026/gen -name completion.json -path "*E60*" | xargs -I{} python -c "
import json,sys
c=json.load(open('{}'))
print('{}', c.get('n_expected'), c.get('n_actual_unique'), c.get('n_missing'), c.get('returncodes'))
"
- Bash: rm results/iter_026/eval/report_E60.json && python eval_iter026.py E60 2>&1 | tail -10
