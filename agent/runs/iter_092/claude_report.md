# Work Performed

# 요약

- **핵심 결과:** 보존된 R/G 학습을 최신 checkpoint에서 재개해 epoch6까지 끝냈고, E128 평가까지 마쳤다. 위치 보조 CE(G)는 판독 회복을 늘리지 못했다.
- **근거:**
  - 사전 규칙상 epoch12 연장은 하지 않았다(epoch4→6 V64 NLL이 네 조건 모두 증가).
  - 최종 공통 epoch는 NLL 합이 최소인 epoch1(64 updates, LR2e-4)로 봉인했다.
  - E128 비정상 96명의 strict recall은 G−R 0.0053 (95% CI [0, 0.016])이고, 추가 회복은 1명뿐이다.
- **미검증·주의:**
  - 선택된 R/G가 대부분 "No significant radiological findings" 같은 일반 정상문으로 수렴했다. 판독 효과가 아니라 짧게 학습된 모델의 prior일 수 있다.
  - E128 판정 512건 중 약 80%(430건)를 내가 정한 규칙표로 자동 판정했고, 나머지 82건은 수동 판정했다. 이는 전문의 검증이 아니다.
- **다음:** 이번 원 비교는 음성이다. 위치 보조 CE 투자 보류 여부는 GPT 리뷰에서 판단한다.

# Files Changed

새 파일(모두 `research/`, 소스 변경은 기존 경로 수정 없음):

- `report92_judge.py`, `report92_spec_e6.py`: epoch6 V32 판정 도구와 128건 수동 판정.
- `report92_autojudge.py`, `report92_e_judge.py`: E128 반복 문형용 규칙표와 판정 조립기.
- `report92_spec_e.py`, `report92_spec_e2.py`: 규칙표가 못 처리한 82건의 수동 판정.
- `report92_e_definitions.py`: E reference atom 293개 정의(생성 전 작성).
- `report92_e_recheck_notes.py`: 재점검 기록.
- `report92_manifest.py`: 인계 manifest.

결과(`results/iter_092/`): `handoff_manifest.json`, `effects_E128.json`, `effects_E128_verify.json`, `ground_E32/{R,G}_ground_eval.json`, `e_unhandled_list_tmp.txt`(작업 중 목록 잔존 파일).

iter_090 recovery 경로에는 새 attempt·event·checkpoint·산출물을 append-only로 추가했다. 아래 세 개는 내 실수로 만든 중간 산출물이라 삭제하지 않고 이름만 바꿔 보존했다.

- `semantic/epoch6/eval_superseded_relative_paths`
- `semantic/E/judgments_superseded_duplicate_match`
- `semantic/E/judgments_superseded_cardiomegaly_negation`

# Commands / Experiments

모두 성공했다.

1. 실행 직전 확인: 살아 있는 supervisor 없음, GPU 0/1 거의 비어 있음.
2. `python report90_recovery_launch.py --epochs 6`을 background로 실행했다. `experiment_wait.py --pid … --timeout 600`을 반복해 기다렸다. 네 worker 모두 exit 0, wall 14,496초.
3. `report90_recovery_train_verify.py`를 4개 run에 실행해 모두 PASS.
4. `report90_recovery_gen_queue.py --epoch 6`: 8개 job 모두 rc=0, 533초.
5. 보조 grounding 평가 4건, `report90_recovery_blind.py --epoch 6`.
6. epoch6 V32 판독 128건을 가린 채 수동 판정한 뒤 `semantic_eval` → `semantic_verify`(PASS, anchors 529) → `report90_decide.py --epoch 6` → `report90_select.py`.
7. `report90_e_prepare.py`: E128, 교체 0건, 겹침 0.
8. E reference 작성 → `report90_e_reference.py` → `report90_final_queue.py`.
   - R/G/base/CURE 판독 512건과 R/G 보조 grounding 32건씩 생성, 1.03h, rc=0.
   - `report90_final_verify.py` 6건 모두 PASS.
9. `report90_final_blind.py` → E128 512건 판정(`semantic_eval`/`semantic_verify` PASS, anchors 2,770).
10. `report90_e_recheck.py` → `report92_e_recheck_notes.py`(98건) → `report90_e_adjudicate.py` → 조정된 묶음 재평가·검증.
11. `report90_effects.py` → `report90_effects_verify.py`: PASS (264건 독립 재계산).

# Results

**학습 (epoch4→6 V64 NLL, 낮을수록 좋음):**

| 조건 | epoch1 | epoch2 | epoch4 | epoch6 |
|---|---|---|---|---|
| R LR2e-4 | 1.523 | 1.532 | 1.742 | 2.298 |
| G LR2e-4 | 1.526 | 1.536 | 1.683 | 2.329 |

- 네 조건 모두 epoch4→6에서 NLL이 올랐다. 연장 조건(NLL 2% 감소)은 충족되지 않아 epoch12는 실행하지 않았다.
- LR은 epoch6 NLL 최소인 2e-4로 선택했다. 봉인 결과: `results/iter_090/recovery/selection/final.json`.
- 이번 재개로 추가한 updates는 R1e-4 79, G1e-4 99, R2e-4 256, G2e-4 256으로 합계 690이다.

**epoch6 V32 (보조 지표, 선택에는 쓰지 않음):**

| 조건 | LR | strict recall |
|---|---|---|
| R | 2e-4 | 0.200 |
| G | 2e-4 | 0.167 |

- 비교 기준(epoch2 대비 변화): R은 +3.3pp, G는 0.
- 보조 grounding F1@0.3 (V16): R 0.0 (전부 invalid), G 0.22–0.25.

**E128 비정상 96명 (환자 bootstrap 10,000회, seed89017):**

| 비교 | strict recall 차이 | 95% CI |
|---|---|---|
| G−R | +0.0053 | [0.0, 0.0163] |
| R−base | −0.0668 | [−0.114, −0.027] |
| G−base | −0.0615 | [−0.107, −0.023] |
| CURE−base | +0.0863 | [0.021, 0.154] |

- G−R: 추가 회복 환자 1명, 소실 0명. 명시 모순은 두 조건 모두 0, type_recall은 G−R −0.018.
- 원 기준(strict recall ≥5pp, 회복 ≥5명, 한 명 제거 후 양의 방향) 충족: G−R은 **미충족**, CURE−base는 충족(참고 시스템 비교).
- 절대값 strict recall은 R 0.012, G 0.017, base 0.078, CURE 0.165이다.
- E 보조 grounding(32명): R F1@0.3 0.0 (invalid 32), G 0.25 (invalid 2).
- 파일: `results/iter_092/effects_E128.json`, `effects_E128_verify.json`, `handoff_manifest.json`.

# Goal Progress / Reused Assets

**목표 진전:**
- 같은 판독으로 학습하되 위치 CE만 다르게 한 R/G 통제 비교를 원 설계대로 완료했다.
- 이 설정에서는 G의 판독 이득이 관찰되지 않았다.
- 위치 출력 학습 자체는 보존된다(G만 valid box 30/32).

**미검증:**
- 확정 효과 크기: CI 하한이 0이라 사실상 0 근처이며, 단일 seed이다.
- 낮은 NLL의 epoch1 선택이 관찰을 지배했다. 더 길게 학습한 상태(epoch2~4)의 R/G는 E에서 평가하지 않았다. 사전 규칙 때문이며, 이를 사후에 바꾸지 않았다.
- E는 독립 임상 test가 아니다. CURE 비교는 모델·데이터·학습량이 달라 방법 효과가 아니다.

**재사용한 기존 코드:**
- `report90_recovery_launch/train/train_verify`, `gen_queue`, `ground_eval`, `blind`, `semantic_eval/verify`, `decide`, `select`, `e_prepare/e_reference/final_queue/final_verify/final_blind/e_recheck/e_adjudicate/effects/effects_verify`.
- 모두 수정 없이 사용했다.
- 같은 digest로 resume이 성공했고, 별도 reuse 검증 요구는 없었다(`reuse_assets=[]`).

# Problems

**현재 결론 무효를 부르는 결함:** 확인한 것 없음.

**결론 해석 한계 (재사용·후속 시 주의):**
- 판정 규칙의 문체 노출: 출력 문체(FINDINGS 형식, 좌표 포함)가 조건을 드러낼 수 있어, 모델명 가림이 완전하지 않다.
- 규칙표 판정(`report92_autojudge.py`):
  - 반복 문형을 같은 규칙으로 일괄 처리했다.
  - "Normal chest X-ray"류가 확정 이상과 충돌하면 contradicted로 센다.
  - 그 결과 base의 contradiction 0.34가 높게 나왔을 수 있다. base 비교 수치는 이 규칙의 영향을 크게 받는다.
  - 위치·정도가 모호한 대응은 `ambiguous` 표시로 남겼다.
- 재점검 98건 중 수정은 1건뿐이고, 나머지는 같은 assistant가 같은 규약으로 유지했다. 독립 평가자 합의가 아니다.
- 한 출력(R/G/base 중 하나가 아닌 CURE 1건)이 반복 루프로 비EOS 종료했다. format_failure로 표기했다.

**추후 개선:**
- 작업 중 만든 중복 match 처리와 상대경로 문제는 이번 경로에서 수정·보존했다. 일반화는 하지 않았다.
- 구현 응답이 pending 동안 종료되는 운영 문제는 이번에 해결했다(같은 세션에서 `experiment_wait.py` 반복). 별도 소스 변경은 없었다.

# Recommendation to GPT

- **판정:** 원 계획의 G−R 기준은 미충족이다(strict recall +0.5pp, 회복 1명). 현재 위치 보조 CE 설정의 투자는 보류 쪽이다.
  - 보류 범위는 "epoch1 선택·단일 seed·이 판독 supervision 조건"이다. 위치 학습과 판독의 일반 관계는 기각이 아니다.
  - 남는 관찰: R/G가 모두 일반 정상문으로 수렴하는 현상과 G만 valid box를 내는 점이다. 이는 판독 이득과 분리해서 보존한다.
- **다음(택일, 새 근거가 필요):**
  - (a) 선택 epoch 의존성을 줄인 한정 확인: 사전 고정한 두 번째 seed 또는 epoch2~4에서의 같은 E128 비교.
  - (b) 이 묶음을 보류하고 다른 질문으로 전환.
  - (a)를 택하면 judge 규칙표의 contradicted 정의를 사전에 독립 검토하길 권한다.
- NLL이 epoch1 이후 상승한 점은 학습 설정(LR·데이터량)이 판독 학습에 부적합했다는 신호일 수 있다. 위치 보조 CE의 효과와 분리해서 보라.

SELF_CHECK: FAIL
SUMMARY: 보존된 R/G를 epoch6까지 재개·완료하고 E128 평가까지 마쳤다. epoch4→6 NLL 상승으로 epoch12는 실행하지 않았고, G−R strict recall은 +0.5pp(CI [0,1.6], 추가 회복 1명)로 원 기준 미충족이다. 다만 E 판정 512건 중 약 80%가 내 규칙표 자동 판정이고 선택 epoch1의 R/G가 일반 정상문으로 수렴해, 독립 평가자 검증은 없다.

# [orchestrator] 권한 거부된 도구 호출
- Bash: echo CVD=$CUDA_VISIBLE_DEVICES; which python; python --version; ls ../experiment_wait.py; cat results/iter_090/recovery/decisions/expand_epoch6.json | head -c 800; ls results/iter_090/recovery/train/G_lr0.0001 | tail -8
- Bash: ps -o pid,ppid,etime,cmd -p 400253,400255,400386,400290,400291
- Bash: for f in report90_e_prepare report90_e_reference report90_final_queue report90_final_verify report90_final_blind report90_e_adjudicate report90_e_recheck report90_effects report90_effects_verify report90_cure report90_cure_prepare; do echo "=== $f"; head -3 $f.py; grep -n "add_argument\|^def main\|^if __name__" $f.py | cut -c1-260; done
- Bash: python -c "
import json
rows=json.load(open('results/iter_090/recovery/data/E128/manifest.json'))
for i,r in enumerate(rows):
    print(i,r['stratum'],'ABN' if r['retained_abnormal'] else 'nor')
    for j,f in enumerate(r['findings']):print('   ',j,'*' if f['abnormal'] else ' ',f['sentence_en'].strip(),'|box' if f.get('boxes') else '')
" > /tmp/e128_sentences.txt; wc -l /tmp/e128_sentences.txt; head -c 200 /tmp/e128_sentences.txt
- Bash: python report92_e_judge.py --list > /tmp/e_unhandled.txt; tail -1 /tmp/e_unhandled.txt
