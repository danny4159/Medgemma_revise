# Work Performed

**요약**
- **핵심 결과:** LR 2e-5 직접 판독 SFT(R)는 사전 가능성 기준을 충족하지 못했다. 그래서 계획대로 G(위치 보조 CE)는 실행하지 않았다.
- **근거:** 384 updates를 정상 완료했다. 조건명을 가린 재판정에서 epoch6 V32 strict recall은 R 0.225, base 0.192, R(LR1e-4) 0.175, R(LR2e-4) 0.200이다. 순증가 환자 수(증가−감소)는 base 0, LR1e-4 2, LR2e-4 1로 모두 기준 3명 미만이다.
- **미검증·주의:** V32는 반복 개발 자료(20명 recall 분모)라 CI가 넓다. 판정은 assistant 해석이고 전문의 검토가 아니다. 수렴 부족은 배제하지 못했다. 이 결과는 위치 학습 전체의 무용성이 아니다.
- **다음:** 현재 LR 재구성 경로는 보류하고, 연구 질문은 유지한다.

**구현·실행 순서**
1. 계획, 기존 trainer·생성·판정 코드, 인계 기록을 확인했다. 새 wrapper `report97_train.py`는 기존 trainer 연산을 그대로 쓰고 결과·cache·gate 경로와 허용 LR(2e-5)만 iter_097로 격리했다. 기존 파일은 수정하지 않았다.
2. 동작 확인(`report97_resume.py`): 연속 실행, 중간 step 재개, epoch 경계 재개를 비교했다. R 모드 1 update와 optimizer LR도 확인했다. 통과 후 `training_gate.json`을 잠갔다. iter_090 recovery gate 증거 21건은 hash로 계승했다.
3. 생성 경로 검사(`report97_gen_test.py`): base V32 32건을 limit 3 후 재개로 생성했다. 요청 파일 변조 시 rc=1로 거부됐고, 완료 후 재실행은 record 수가 불변이었다.
4. V32 reference 사례표를 새 출력 전에 고정했다(`case_table_v2.json`). 확정 양성 원자 35개, 환자 20명이고 lateral 의존 원자는 0이다. strict·type_only·양측·정상문·quote 거부 등 대조 fixture 8건이 통과했다.
5. R 학습을 supervisor(`report97_launch.py`)로 GPU1에서 실행했다. R 학습 중 GPU0에서 epoch2 V32 생성을 했다.
6. epoch6 생성(V32 32건, V16 16건)은 GPU0·GPU1에서 병렬로 실행했다.
7. 판정: 조건명을 가린 epoch6 batch 128건(신규 R, base, R LR1e-4, R LR2e-4)을 새로 판정했다. 비일반 출력은 출력별로 직접 판정했고, 일반 정상문은 iter_090 관례에 따랐다. 판정 규칙은 `report97_judge_epoch6.py` 상단에 있다.
8. 사전 기준을 `report97_decide.py`로 구현해 적용했다. 독립 재집계(`report97_verify.py`)는 통과했다.

# Files Changed

신규 코드(전부 `research/`, 기존 파일 수정 없음):
- `report97_train.py`, `report97_launch.py`, `report97_resume.py`, `report97_gate.py`
- `report97_gen.py`, `report97_genq.py`, `report97_gen_test.py`
- `report97_reference.py`
- `report97_blind.py`, `report97_judge_epoch2.py`, `report97_judge_epoch6.py`
- `report97_decide.py`, `report97_ground_eval.py`, `report97_rejudge_agreement.py`, `report97_verify.py`, `report97_finish.py`

신규 결과: `results/iter_097/`

# Commands / Experiments

| 단계 | 결과 |
|---|---|
| `report97_resume.py --gpu 0` | 성공(rc 0), 6단계 모두 기대 rc |
| `report97_gate.py` | 성공 |
| `report97_launch.py --mode R --epochs 6` | 성공(rc 0), 15,736초, GPU1, peak_reserved 13.51GiB, 약 38–42초/update |
| `report90_recovery_train_verify.py` | PASS |
| `report97_gen_test.py --gpu 0` | 성공 |
| `report97_genq.py` epoch2 V32 | 성공, 98.5초 |
| `report97_genq.py` epoch6 V32 / V16 | 성공(V32는 긴 출력 때문에 오래 걸림) |
| 판정 → `report90_semantic_eval.py` → `report97_decide.py` | 성공 |
| `report97_verify.py` | 성공(`passed` true) |
| `report97_finish.py` | 성공 |

실패·복구 내역:
- 첫 `report97_reference.py` 실행의 `case_table.json`에 lateral 플래그 버그가 있었다("bilateral"이 "lateral"로 잡힘). write-once 저장이라 `case_table_v2.json`으로 새로 저장했고 v1은 남아 있다.
- epoch6 판정 파일 첫 저장본이 strict 규칙 assertion에 걸려, 직접 생성한 `semantic/epoch6/judgments` 폴더를 두 번 지우고 다시 생성했다. 저장 전 `score()` 검증을 추가했다. 지운 것은 이번 반복에서 몇 분 전에 만든 결함 파일뿐이다.
- `decisions/verify.json.663264.tmp` 잔여 파일이 있다(`json` 직렬화 오류 중단분). 삭제 권한이 없어 남겼고, 최종 `verify.json`과는 별개다.
- 첫 background 실행이 `results/iter_097` 디렉터리 부재로 즉시 실패했다. 디렉터리 생성 후 재실행했다.

# Results

경로는 모두 `results/iter_097/` 기준이다.

**학습**(`train/R_lr2e-05/`): 384 updates 연속 고유, 모두 유한, `loss`=`report_nll`. V64 NLL(epoch 1/2/4/6):

| 조건 | NLL |
|---|---|
| R LR2e-5 | 1.790 / 1.600 / 1.471 / 1.545 |
| R LR1e-4(기존) | 1.532 / 1.460 / 1.595 / 2.392 |
| R LR2e-4(기존) | 1.523 / 1.532 / 1.742 / 2.298 |
| base | 5.320 |

LR2e-5의 NLL 4→6은 +5.0%(소폭 상승)이고, 기존 고LR의 큰 상승(2.30–2.39)은 나타나지 않았다.

**V32 epoch6 (조건명 가림, 20명 recall 분모)**: `semantic/epoch6/eval/report.json`

| 조건 | strict | type_only 포함 | 모호 제외 strict | 반박 환자(32명) |
|---|---|---|---|---|
| R LR2e-5 | 0.225 | 0.342 | 0.175 | 1 |
| base | 0.192 | 0.321 | 0.167 | 8 |
| R LR1e-4 | 0.175 | 0.317 | 0.175 | 1 |
| R LR2e-4 | 0.200 | 0.342 | 0.175 | 3 |

R LR2e-5의 epoch2 strict는 0.075이고 epoch6은 0.225다(생성 2→6은 상승).

**가능성 기준**(`decisions/R_vs_comparators_epoch6.json`): 신규 R−비교군 strict 차이, 환자 bootstrap 95% CI(seed 97017, 10,000회), 증가/감소 환자 수는 다음과 같다.

| 비교군 | 차이 | 95% CI | 증가/감소 | 순증가 |
|---|---|---|---|---|
| base | +3.3pp | [−7.5, 17.5] | 2/2 | 0 |
| R LR1e-4 | +5.0pp | [−10, 20] | 3/1 | 2 |
| R LR2e-4 | +2.5pp | [−12.5, 17.5] | 2/1 | 1 |

- 세 비교 모두 순증가≥3과 보수적 판정(모호 회복 제외)에서 미달이다. 반박 환자 증가≤1은 충족했다.
- 판정: `r_passes_possibility_criterion=false`, G 미실행.
- 민감도: 비교군을 iter_090 상속 판정으로 바꿔도(base 0.167 기준 +5.8pp) 순증가 기준에서 모두 미달이다(`..._sensitivity_inherited.json`).

**재판정 일치도**(`decisions/rejudge_agreement.json`): R LR2e-4는 0명, R LR1e-4는 1명이 상속 판정과 달랐다. base는 5명이 달랐다(주로 반박 판정, 1명은 strict 0→0.5). base의 이 차이(약 2.5pp)가 비교 결과를 바꾸지는 않는다.

**V16 보조 grounding**: F1@0.3은 R LR2e-5 0.0625(invalid 14/16), base 0.0625(invalid 3/16), R LR1e-4와 R LR2e-4는 0.0(invalid 16/16)이다.

**검증**: `decisions/verify.json`의 recall·반박·분기·학습·생성 완료 검사 전부 통과. 요약은 `decisions/branch_decision.json`에 있다.

**자원**: 두 GPU를 사용했다. R 학습은 GPU1에서만 실행했다. 의존성(R→G)과 24GiB 한계(학습 13.5GiB+worker 여유, 추론 10.6GiB 이상) 때문에 같은 GPU 복수 worker는 쓰지 않았다. 학습은 약 4.4시간, 생성·검증은 약 수 시간이다.

# Goal Progress / Reused Assets

**진전**
- **시험 설정:** LR2e-5는 V32에서 base 및 기존 고LR R 대비 명확한 회복 개선을 보이지 못했다. 기존 고LR의 후반 NLL 상승은 완화됐다. 현재 LR 재구성 설정은 보류한다.
- **연구 관찰:** 낮은 LR에서도 R이 base를 뚜렷이 넘지 못했다. 이는 "높은 LR이 판독 저하의 주원인"이라는 설명을 약화시킨다. 다만 20명 recall 분모, 단일 seed, 고정 384 updates라는 제한이 있다. 수렴 부족, prompt/target 형식 차이, 제한된 supervision은 미분리다.
- **연구 질문:** 작동하는 직접 판독 baseline 이후 위치 supervision의 효과는 판단하지 못했다. 이번 결과는 위치 학습 전체나 신규 기여에 대한 판단이 아니다.

**재사용**
- iter_090 `training_gate` 증거 21건을 hash로 계승했다.
- 재사용한 코드는 `report90_train/stable_v2/numeric/gen/gen_safe/recovery_gen`, `report89_model`, `rsna_diag/*`, `report90_semantic_eval`, `report90_recovery_train_verify`, `report90_recovery_ground_eval`이다.
- 새 trainer·생성 경로는 이번에 직접 검증했다. 학습은 재개 비교로, 생성은 base 32건의 token 단위 일치로 확인했다.
- 비교군 base·R LR1e-4·R LR2e-4 출력은 상속분을 재사용했고, 가림 재판정과 일치도로 확인했다.

# Problems

- **현재 결론 무효:** 없음.
- **재사용 전 수정 필요**
  - 판정은 assistant 해석이다. 모호 reference(V16/V17/V27/V28)와 base의 5명 drift에서 최대 약 2.5pp의 해석 불확실성이 있다.
  - 이번에 새로 만든 judge 코드는 이 iter의 고정 V32 전용이다.
  - `report97_gen_test`의 `all_eos=false`는 상속된 base 출력의 비EOS(32건 중 1건)다. 평가 분모에는 유지했다.
- **추후 개선**
  - G 미실행이라 위치 보조 CE의 효과는 이번에 측정하지 않았다.
  - 4→6 NLL 소폭 상승이 있어 epoch4 선택 등은 사전 계획 밖이므로 처방하지 않았다.
  - 유일한 잔여물은 tmp 파일 1개다.

# Recommendation to GPT

- **투자 판단:** 현재 LR 재구성 경로는 "시험 설정 보류"로 한정한다. 연구 질문 보류는 아니다.
- **유지할 관찰:** 위치 출력과 판독의 차이, NLL과 소견 회복의 차이는 유지한다. LR2e-5가 고LR의 후반 NLL 상승을 완화한 사실도 유지한다.
- **다음 후보(중요성·정보 가치 순):**
  1. 강한 기존 모델(CURE 등)의 저장 출력과 직접 비교하는 최소 비교. 새 학습은 하지 않는다.
  2. 더 큰 독립 판독 자료로 재측정. 자료 정의가 먼저다.
  3. 보류한다면 재개 조건은 "분모 확대 또는 독립 자료 확보"로 명시한다.
- **하지 말 것:** 같은 V32에서 LR·epoch·seed를 더 돌리거나 규칙 판정기를 반복 보완하는 것.

SELF_CHECK: PASS
SUMMARY: LR2e-5 R(384 updates)을 정상 완료했으나 V32 epoch6 strict recall 0.225가 base 0.192·고LR R 대비 순증가 3명 미만이라 사전 기준 미달, G는 미실행하고 현재 LR 재구성 설정만 보류(연구 질문은 유지, 단일 seed·20명 분모·assistant 판정 한계)

# [orchestrator] 권한 거부된 도구 호출
- Bash: cd /SSD1_1TB/home/milab/daniel/08_medgemma/research; python - <<'E'
import json,collections
p='results/iter_090/recovery/semantic/epoch2/'
m=json.load(open(p+'private_mapping.json'));print(collections.Counter(v['stage'].split('/')[-1] for v in m.values()))
r=json.load(open(p+'eval/report.json'))
for k,v in r['conditions'].items():print(k,{a:(round(b,3) if isinstance(b,float) else b) for a,b in v.items() if a in('strict_recall','type_recall','contradiction_abnormal','recall_n')})
E
ls results/iter_090/recovery/final_generation/base_report; cat results/iter_090/recovery/final_generation/contract.json | head -c 1500; cat results/iter_090/recovery/stage_decision_rules.json | head -c 2500
- Bash: cd /SSD1_1TB/home/milab/daniel/08_medgemma/research; mkdir -p results/iter_097; cat > report97_train.py <<'E'
"""iter_097: LR 2e-5 직접 판독(R)/조건부 위치 보조(G) 학습. 기존 report90 trainer의 연산은 그대로 두고
결과·cache·gate 경로와 허용 LR만 iter_097로 격리한다. 기존 trainer/config/결과는 수정하지 않는다."""
import argparse
import os
import report89_model as M
import report90_train as C
import report90_numeric as N
from report90_stable_v2 import apply
from report86_common import sha  # noqa: F401  (SOURCES hash 대상 일관성)

ORIGINAL=N.OUT
OUT=M.ROOT/'results/iter_097'
LR=2e-5

def environment(gpu):
    allowed=os.environ['CUDA_VISIBLE_DEVICES'].split(',');assert gpu in allowed
    # report90_numeric.environment는 M.OUT을 iter_090으로 되돌리므로 cache 격리를 iter_097로 직접 지정한다.
    import subprocess
    smi=subprocess.check_output(['nvidia-smi','--query-gpu=index,uuid,memory.total,memory.used,memory.free','--format=csv,noheader,nounits'],text=True)
    row=next(x.split(', ') for x in smi.splitlines() if x.split(', ')[0]==gpu)
    assert float(row[-1])>=14.19*1024+2048+1024
    M.OUT=OUT
    mapping=M.environment(gpu);mapping.update(peak_basis_gib=14.19,worker_margin_mib=2048,context_margin_mib=1024)
    return mapping

C.OUT=OUT
C.environment=environment
C.apply=apply
C.SOURCES=C.SOURCES+['report90_stable_v2.py','report97_train.py']

def main():
    p=argparse.ArgumentParser();p.add_argument('--gpu',required=True);p.add_argument('--run-dir',required=True)
    p.add_argument('--train',default=str(ORIGINAL/'data/T512/manifest.json'));p.add_argument('--validation',default=str(ORIGINAL/'data/V64/manifest.json'))
    p.add_argument('--mode',choices=['R','G'],required=True);p.add_argument('--lr',type=float,choices=[LR],required=True)
    p.add_argument('--mb',type=int,choices=[1],default=1);p.add_argument('--epochs',type=int,required=True)
    p.add_argument('--test-patients',type=int,default=0);p.add_argument('--stop-step',type=int,default=-1)
    return C.run(p.parse_args())

if __name__=='__main__':raise SystemExit(main())
E
python -c "
import report97_train as t, report90_train as C
print(C.OUT, C.SOURCES)"; ls results/iter_090/data/T512 results/iter_090/data/D8 | head; nvidia-smi --query-compute-apps=pid,used_memory --format=csv
- Bash: cd /SSD1_1TB/home/milab/daniel/08_medgemma/research; python report97_resume.py --gpu 0 > results/iter_097/tests_resume.stdout.log 2> results/iter_097/tests_resume.stderr.log; echo rc=$?; tail -c 600 results/iter_097/tests_resume.stdout.log
- Bash: sed -i "s#reference/case_table.json#reference/case_table_v2.json#" report97_reference.py; python report97_reference.py; python -c "
import json;d=json.load(open('results/iter_097/reference/case_table_v2.json'));print(d['n_abnormal_without_definite_positive'],d['lateral_view_dependent_recall_targets'],d['n_recall_patients'])"
- Bash: python report97_decide.py --per-output results/iter_097/semantic/epoch6/eval/per_output.json --new R_lr2e-05_report --comparators base_V32 R_lr0.0001_report R_lr0.0002_report --output results/iter_097/decisions/R_vs_comparators_epoch6.json; python - <<'E'
import json
new={x['image_id']:x for x in json.load(open('results/iter_097/semantic/epoch6/eval/per_output.json')) if x['condition']=='base_V32'}
old={x['image_id']:x for x in json.load(open('results/iter_090/recovery/semantic/epoch2/eval/per_output.json')) if x['condition']=='base_report'}
refs={r['id']:i for i,r in enumerate(json.load(open('results/iter_090/semantic/V32_reference_v3.json'))['rows'])}
for k in new:
    a,b=new[k]['strict_recall'],old[k]['strict_recall']
    if a!=b or new[k]['contradiction']!=old[k]['contradiction']:print(refs[k],'strict',a,b,'contra',new[k]['contradiction'],old[k]['contradiction'])
E
