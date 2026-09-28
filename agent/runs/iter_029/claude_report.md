# 요약

- **핵심 결과:** iter_028의 Presence 부호 오류(No−Yes를 잘못 적용)를 원시 logits에서 교정했다. E800 빈 출력 398명 중 미검출 70명에서 token 계열(entropy/token_nll)이 사전 목표(AUROC≥0.75, CI 하한≥0.65, Capture@20%≥0.50)를 이미 충족하고, 교정된 영상 재질의(presence_b0)는 추가 정보 이득 기준(V−T AUROC 차이≥0.10, CI 하한>0)을 충족하지 못했다(C에서 point −0.027, CI 하한 −0.066).
- **근거:** 새 교정 코드로 재계산한 E entropy AUROC=0.8224738676, presence_b0 AUROC=0.8153745645/Capture@20%=0.5755102는 iter_028 리뷰의 독립 재계산치와 정확히 일치했다(부동소수점 오차 없음). C 대표 선택도 리뷰 예측대로 presence_b0(AUROC 0.7493183)로 확정됐다.
- **미검증·주의:** 이번 결과는 개발 자료(C400/E800)에 대한 평가 교정이며 새 GPU 생성·독립 확인 환자 집단은 없다. C의 실제 생성이 전체 400명(주분석 995건 외 1,005건 잉여)이었고, C→E 사이에 protocol.json이 한 번 재잠금됐다는 사실을 `claude_stream.jsonl`에서 복원해 원인(빈 출력 필터 한 줄 수정, 주분석 대상 채점 방식에는 영향 없음)을 확인·기록했지만, 재잠금 이전 protocol.json 원본 bytes 자체는 복원할 수 없다.
- **다음:** 계획대로 confidence head/loss 신규 개발은 이번 결과 근거로 보류하고, 잔여 미검출 진단이나 다른 연구 질문의 정보 이득을 다음 전략 판단에서 비교해야 한다(이번 반복 범위 밖).

# Work Performed

1. iter_028의 raw C/E JSONL·source_manifest·protocol.json·worker env를 읽기 전용으로 감사(`run_iter029_audit.py`)해 완전성·중복·adapter/protocol 연결·pixel hash 일치를 검증했다.
2. `claude_stream.jsonl`을 대조해 C/E 간 protocol_digest 차이의 원인을 복원했다(668~712행): C는 risk28.py의 필터 버그로 400명 전체를 채점했고, 이후 빈 출력 199명만 채점하도록 한 줄 수정한 뒤 protocol을 재잠금해 E(398명)를 생성했다. 이 수정은 개별 환자 채점 방식을 바꾸지 않아 주분석(빈 출력 population) 해석에 영향이 없음을 확인·기록했다.
3. Presence/P(True) 부호를 교정한 새 `build_table`(`run_iter029_eval_c.py`)을 작성했다. Presence=logit_yes−logit_no, P(True)=logit_no−logit_yes(저장값 그대로)로 구분했다.
4. C에서 대표 T/V 재선택·Platt calibration·확대 결정(`run_iter029_eval_c.py`), E에서 고정 대표·calibration 적용 재집계(`run_iter029_eval_e.py`)를 완료했다.
5. c_table/e_table에 의존하지 않는 독립 검증(`run_iter029_verify.py`)을 raw logit에서부터 재구현해 rank AUROC·경계 동점 포착률·대표 선택을 대조했다.
6. 계획의 Evaluation 기준을 기계 판독 decision(`run_iter029_decide.py`)으로 계산했다.
7. fixture 테스트(`test_rsna_iter029.py`) 18건을 작성·통과시켰다(부호 검증, 대표 선택 동점, calibration 경계, 완전성 검사).

# Files Changed

모두 `research/` 신규 파일이며 기존 `results/iter_028/*` 원본은 전혀 수정하지 않았다(`protocol.json`에 잠긴 파일 hash 전부 불일치 0으로 확인).

- `run_iter029_audit.py` — 신규: 읽기 전용 provenance 감사 + protocol digest 재구성 기록.
- `run_iter029_eval_c.py` — 신규: 방향 교정 build_table, C 대표 선택·calibration·확대 결정.
- `run_iter029_eval_e.py` — 신규: E 재집계(대표/calibration을 C에서 고정 적용).
- `run_iter029_verify.py` — 신규: raw logits 직접 재구현 독립 검증.
- `run_iter029_decide.py` — 신규: 계획 Evaluation 기준의 기계 판독 decision.
- `test_rsna_iter029.py` — 신규: CPU fixture 18건.
- `results/iter_029/**` — 신규 결과(감사·평가·검증·decision·fixture json).

# Commands / Experiments (실제 실행한 명령과 성공/실패)

- `python run_iter029_audit.py` — 성공. `ok=True n_problems=0`.
- `python test_rsna_iter029.py` — 성공(1차 시도에서 테스트 자체의 기대값 부호 실수 1건 발견·수정 후) 최종 `18/18 PASS`.
- `python run_iter029_eval_c.py` — 1차 시도는 completion 검사가 C의 실제 생성 모집단(전체 400명)을 몰라 "extra" 오탐으로 실패했고, provenance 조사 결과를 반영해 completion 검사 로직을 수정한 뒤 성공. `n=199 n_events=36 rep_T=entropy rep_V=presence_b0 enter_E=True`.
- `python run_iter029_eval_e.py` — 성공(백그라운드로 완료, bootstrap 계산 때문에 120초 제한 초과). `n=398 n_events=70`.
- `python run_iter029_verify.py` — 성공. `ok=True n_problems=0`(raw logits 직접 재계산이 저장 표·AUROC·Capture@20·대표 선택과 완전히 일치).
- `python run_iter029_decide.py` — 성공. decision.json 생성.
- 원본 iter_028 protocol locked file hash 재검증 — 성공, 불일치 0.

# Results (수치와 결과 파일 경로)

- `results/iter_029/audit/audit.json`: `ok=true`, `n_problems=0`. C(전체 400명 생성, 주분석 199명)·E(398명) 완전성, adapter/protocol 연결, pixel hash 일치, C/E 환자·pixel 교집합 0, protocol_digest 차이의 코드 diff 복원 기록 포함.
- `results/iter_029/C_eval/c_eval.json`: n=199, n_events=36, rep_T=entropy, rep_V=presence_b0(AUROC 0.7493183 > ptrue_b0 0.7060327), enter_E=True.
- `results/iter_029/E_eval/e_eval.json`: n=398, n_events=70.
  - entropy AUROC=0.8224738676(CI [0.7592101,0.8795061]), Capture@20%=0.6142857.
  - presence_b0 AUROC=0.8153745645(CI [0.7507369,~]), Capture@20%=0.5755102. presence_m0 AUROC=0.7879791, Capture@20%=0.4761905.
  - diff_V_minus_T_auroc_975(E) = −0.0070993, 97.5% CI [−0.0304403, 0.0151615]; diff_V_minus_seed = 0.2011760, CI [0.1251737, 0.2729738].
  - 세 category(opacity/normal/not_normal_no_opacity)가 모두 단일 class여서 category별 AUROC는 정의 불가로 명시.
- `results/iter_029/decide/independent_verify.json`: `ok=true` — raw logits 직접 재계산이 저장 표·AUROC·Capture20·대표 선택과 완전 일치(최대 절대차 0).
- `results/iter_029/decide/decision.json`: `overall="simple_baseline_positive_new_confidence_head_deferred"`. token_or_seed 기준 충족=True(entropy/token_nll이 사전 목표 충족), requery(영상 재질의) 추가 이득 기준 충족=False.
- `results/iter_029/tests/fixtures_iter029.json`: 18/18 PASS.

모든 수치는 agent/runs/iter_028/review.md가 사전 예측한 독립 재계산치와 소수점 단위까지 정확히 일치한다.

# Goal Progress / Reused Assets (목표 진전·미검증 범위, 재사용 출처·검증)

- 목표 진전: iter_028의 blocking_issue(Presence 부호 오류로 인한 대표 선택·calibration·주비교 무효)를 계획대로 해소했다. H1(동일 빈 출력 간 위험 순위 정보 존재)은 재확인됐고, H2(교정된 영상 재질의의 추가 정보 이득)는 이번 개발 자료에서 지지되지 않았다(음성). 계획의 "단순 baseline 양성 → confidence head/loss 개발 보류"라는 조건부 다음 행동이 그대로 성립한다.
- 재사용 출처: `rsna_diag/risk28.py`, `risk28_eval.py`, `risk28_source.py`(iter_028 needs_fix 모듈)를 코드 자체는 수정하지 않고 그대로 import해 재사용했다(계획의 reuse_assets가 비어 있던 것과 일치). `risk28_eval.py`(approved 모듈)의 AUROC/Platt/bootstrap 함수를 그대로 사용했다.
- 미검증 범위: (1) C/E는 여전히 개발 자료이며 독립 확인 환자 집단은 미실행(계획대로 이번 범위 밖). (2) protocol_digest 차이의 원인은 코드 diff로 완전히 재구성했지만 재잠금 이전 protocol.json 원본 bytes 자체는 복원 불가(바이트 수준 재현은 아님). (3) `rsna_diag/risk28.py`의 실행기(run_worker/existing_done 등) 자체의 needs_fix 항목(동시 실행 lock, tail 복구 등)은 이번에 GPU를 재사용하지 않았으므로 그대로 미해결로 남는다.

# Problems (현재 결론 무효 / 재사용 전 수정 / 추후 개선을 구분)

- **현재 결론 무효 요인:** 없음. 감사·독립 검증이 모두 0 problems로 통과했다.
- **재사용 전 필수 수정(다음에 GPU를 다시 쓸 때):** `rsna_diag/risk28.py`의 generate/run_worker 계열은 CODE_ASSETS에 기록된 대로 여전히 동시 실행 lock·완료 재검증이 불완전하다. 이번엔 CPU 재집계만 했으므로 영향 없음.
- **추후 개선(선택):** `run_iter029_eval_c.py`의 completion 검사가 C에 대해 "전체 400명 생성이 실제 모집단"이라는 사실을 하드코드로 안다(감사에서 복원한 provenance에 근거). 향후 다른 split을 추가한다면 이 가정을 다시 명시적으로 검증해야 한다.

# Recommendation to GPT

계획대로 이번 반복에서는 새 confidence head/loss 개발을 시작하지 않았다. 다음 판단은 사용자 보완 지시(RSNA LoRA 능력 전이 진단 우선순위)와 GOAL의 전략 재검토 기준에 따라, (a) 잔여 미검출 조건의 진단이 이 결과 이후에도 여전히 가치가 있는지, 아니면 (b) 사용자 지시가 우선한 '지정 영역과 병변 겹침 판단' 등 능력 전이 진단으로 전환할지를 비교해 정해야 한다. iter_026-027의 rsna-region-selection-transfer 관찰(부분적 질의 반응은 있으나 전체 선택은 실패)이 이 우선순위와 가장 가깝게 연결되어 있다.

SELF_CHECK: PASS
SUMMARY: iter_028 Presence 부호 오류를 원시 logits로 교정해 재계산한 결과, entropy/token_nll이 E에서 사전 목표(AUROC≥0.75 등)를 충족하고 교정된 영상 재질의(presence_b0)는 추가 정보 이득 기준을 충족하지 못해 신규 confidence head 개발은 보류하며, 독립 검증·감사 모두 0 problems로 통과했다.

# [orchestrator] 권한 거부된 도구 호출
- Bash: rm results/iter_029/decide/decision.json && python run_iter029_decide.py > /tmp/decide_out.txt 2>&1 ; tail -5 /tmp/decide_out.txt
