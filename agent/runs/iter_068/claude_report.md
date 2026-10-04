# Work Performed

# 요약

- **핵심 결과:** 두 모델 모두 고정 S1의 p(C) 순위는 환자·ordinal·영상 수를 점검한 뒤에도 남았다. 그러나 D에서 정한 threshold는 E12 판별로 이어지지 않아, 사전 기준 "후속 투자 검토 후보"는 두 모델 모두 불충족이다.
- **근거:** 각 모델의 E12(12명, 81 IVD) 수치는 아래와 같다. 이 CPU 재분석은 새 추론이 없다. 결과는 `results/iter_068/analysis/report.json`에 있다.
  - **MedGemma S1:** AUROC 0.734(환자 CI 0.569–0.866), 잔차 AUROC 0.739(CI 0.576–0.881). threshold BA는 0.579이고 recall0/recall2는 0.943/0.214다.
  - **Qwen S1:** AUROC 0.743(CI 0.617–0.827), 잔차 AUROC 0.753(CI 0.623–0.846). threshold BA는 0.540이고 recall0/recall2는 0.151/0.929다.
- **미검증·주의:** E12를 본 뒤 설계한 사후 분석이며 독립 확인이 아니다. 기여 환자 수가 적다(환자 내 AUROC는 5명, D의 II 행은 3명에 집중). 영상 신호와 답변 보정 가능성을 확정하지 못한다.
- **다음:** 사전 계약상 이 결과는 "순위 신호 있음 + 보정 실패 → 현재 Modic 답변 보정 투자 종료"에 해당한다. 최종 투자 판정은 GPT 리뷰에 맡긴다.

## 구현·실행

- `sp68_analysis.py`를 새로 만들었다. 설정(`config.json`)을 먼저 저장한 뒤 실행하고, 기존 report가 있으면 덮어쓰지 않는다.
- 입력 검증은 다음을 강제한다.
  - protocol(D는 v2, E12)의 requests/labels hash 대조
  - 엄격한 JSONL(torn tail·손상 행 거부)
  - 중복·누락·잉여 rid
  - 비유한 logits, softmax 불일치, request↔record 연결
  - D/E 환자 분리
- 계산 내용은 다음과 같다.
  - 두 모델·6조건(S1/S2/J/RT1/LF/T)의 p(C) AUROC와 환자 cluster bootstrap(10,000회, seed68)
  - 환자 내 AUROC, 같은 ordinal·다른 환자 AUROC, leave-one-patient-out
  - D에서만 적합한 ridge 잔차화(ordinal one-hot + n1/n2)와 D 지지 범위 밖 행 제외 민감도
  - D 고정 threshold와 T·global/ordinal prevalence 대조
  - D 환자 leave-one-out
  - D/E 독립 nested bootstrap(10,000회, seed69)
- `test_sp68.py`로 산술과 변조 거부를 검사했고, `sp68_summary.py`로 요약을 출력하며 AUROC를 쌍비교로 독립 계산했다.

# Files Changed

- 신규: `sp68_analysis.py`, `test_sp68.py`, `sp68_summary.py`
- 결과(`results/iter_068/`): `analysis/config.json`, `analysis/report.json`, `tests/fixtures.json`, `dryrun_nb200/`
- `dryrun_nb200/`은 `--nb 200` 시험 산출물이다. 최종 결과가 아니며 삭제하지 않았다.
- 기존 파일은 수정하지 않았다.

# Commands / Experiments

- `python sp68_analysis.py --out-dir results/iter_068/analysis --nb 200`(시험용 dryrun은 `results/iter_068/dryrun_nb200`): 성공.
- `python sp68_analysis.py --out-dir results/iter_068/analysis`: 성공. CPU만 사용했고 GPU는 쓰지 않았다.
- `python test_sp68.py`: 22/22 통과.
- `python sp68_summary.py results/iter_068/analysis/report.json`: 성공.
- 중간에 구문 오류가 한 번 있었다. dict 키 누락이며 수정 후 정상이다.
- 환경 문제로 sklearn과 scipy가 없었다. 독립 AUROC 교차검사는 쌍비교 직접 계산으로 대체했다.
- 첫 시도의 `cd`가 포함된 확인 명령은 권한상 거부되어 경로 인자 방식으로 다시 실행했다.
- 10,000회 bootstrap의 실제 wall-clock은 측정·기록하지 않았다. 보고서의 `nested_time_100_reps_s`는 100회 시점 측정용인데, 이 값은 사용하지 않았다.

# Results

## 재현 검사

- iter_067 D/E12 원 argmax BA02는 두 모델의 모든 조건에서 오차 1e-9 이내로 재현됐다. 예: MedGemma J 0.0943, Qwen S1 0.5.
- D 선택 B=t1도 두 모델에서 재현됐다.
- S1 AUROC는 쌍비교 직접 계산값과 일치한다(MedGemma 0.7338, Qwen 0.7433).

## 순위 분석 (E12, 고정 S1)

| 항목 | MedGemma | Qwen |
|---|---|---|
| 전체 AUROC (95% 환자 CI) | 0.734 (0.569–0.866) | 0.743 (0.617–0.827) |
| 환자 내 AUROC (5명, 44쌍) | 0.767 | 0.610 |
| 같은 ordinal·다른 환자 (197쌍) | 0.728 (CI 0.50–0.894) | 0.810 (CI 0.705–0.910) |
| 환자 제외 AUROC 범위 | 0.677–0.778 | 0.719–0.784 |
| 잔차 AUROC (95% CI) | 0.739 (0.576–0.881) | 0.753 (0.623–0.846) |
| nuisance만의 AUROC | 0.451 | 0.420 |
| 지지 범위 내 잔차 AUROC (80행) | 0.732 | 0.750 |

- **MedGemma:** 환자 내 비교는 대상 환자가 5명이라 환자 간 변동이 크다. 같은 ordinal CI 하한이 정확히 0.50이다.
- **Qwen:** 환자 내 AUROC가 상대적으로 약하다.
- **ordinal·영상 수만의 설명:** nuisance 점수는 순위를 거의 만들지 못했다.
- **D 지지 범위 밖 행:** E12의 1행(ordinal 9)이다.

보조 조건은 아래와 같다.

- **MedGemma:** J 0.765, RT1 0.745, S2 0.715, LF 0.732, T 0.471.
- **Qwen:** S2 0.587, J 0.563, RT1 0.561, LF 0.680, T 0.477. 영상을 결합한 입력이 오히려 약해졌다.
- 보조 조건은 primary를 대체하지 않았다.

## D 고정 threshold (E12)

| 항목 | MedGemma | Qwen |
|---|---|---|
| S1 BA | 0.579 (CI 0.444–0.725) | 0.540 (CI 0.456–0.619) |
| S1 recall0 / recall2 | 0.943 / 0.214 | 0.151 / 0.929 |
| T BA | 0.446 | 0.393 |
| prior global BA | 0.5 | 0.5 |
| prior ordinal BA | 0.515 | 0.515 |
| S1−T | +0.133 (CI −0.254 ~ +0.506) | +0.147 (CI −0.012 ~ +0.344) |
| S1−prior global | +0.079 (CI −0.056 ~ +0.225) | +0.040 (CI −0.044 ~ +0.119) |
| S1−prior ordinal | +0.064 (CI −0.153 ~ +0.262) | +0.025 (CI −0.122 ~ +0.131) |

- **threshold 안정성:** D 환자 leave-one-out에서 E12 BA는 MedGemma 0.543–0.579, Qwen 0.509–0.549다. E12 예측 변경 비율의 최대값은 각각 2.5%, 11.1%다.
- **D 적합 한계:** D의 II 행은 환자 4, 61, 217에만 있다. Qwen의 D BA는 0.528로 chance 수준이다.
- **nested bootstrap:** 유효한 replicate는 9,810/10,000이다. S1 BA CI는 MedGemma 0.446–0.714, Qwen 0.478–0.667이다.

## 사전 기준 판정

| 기준 | MedGemma | Qwen |
|---|---|---|
| BA ≥ 0.65 | 불충족 (0.579) | 불충족 (0.540) |
| recall0 ≥ 0.60 | 충족 | 불충족 |
| recall2 ≥ 0.60 | 불충족 | 충족 |
| prior·T 대비 +5pp | 충족 | prior 대비 불충족 |
| 순위·통제 기준 (AUROC·잔차·환자 내·ordinal) | 충족 | 충족 |
| 전체 판정 | all_pass = false | all_pass = false |

# Goal Progress / Reused Assets

- **목표 진전:** p(C) 순위가 환자·ordinal·영상 수 대조 후에도 남는다는 사후 관찰을 얻었다. 이 신호가 단순 threshold 보정으로 이진 판별까지 이어지지는 않았다.
- **재사용:** `sp67_eval.py`의 BA02 산술과 `sp67_select.py`의 D 선택 규칙은 새 진입점에서 독립적으로 재구현·대조했다. 재현 근거는 위 재현 검사와 같다. 이전 모듈을 import하지 않아 GPU 의존성은 없다. 선별 반입은 없었다.
- **원 판정:** iter_067의 확대 중단과 abandon 판정은 변경하지 않았다.
- **미검증:**
  - 독립 환자 재현
  - 패치 없는 공식 경로 동등성
  - 영상 신호의 임상적 의미
  - 전문 Modic classifier·직접 SFT 대비 잔여 가치

# Problems

- **현재 결론 무효:** 없음. 입력 변조·중복·누락 거부 검사를 통과했고 원 BA02가 재현됐다.
- **재사용 전 수정:** 단일 분석 진입점은 iter_067 protocol의 code hash를 강제하지 않는다. 일치 여부는 manifest에 정보로만 기록했다.
- **추후 개선:**
  - 환자 12명·D의 II 보유 환자 3명이라 CI가 넓다.
  - nuisance 점수의 AUROC CI도 넓어, 영상 수나 ordinal이 순위에 기여할 가능성을 완전히 배제하지 못한다.
  - T가 J 문구에만 대응해 완전한 영상 제거 대조가 아니다.
  - nested bootstrap의 D 재표집은 II 행이 없는 환자도 포함해 class 소실이 190회 있었다.
  - 사후 분석이라 다중 비교와 선택 편향이 남는다.

# Recommendation to GPT

- 사전 계약상 이 결과는 순위 신호는 남지만 보정이 단순 대조를 넘지 못하는 경우다. 현재 Modic 답변 보정 투자를 종료하는 쪽을 권고한다.
- 유효한 관찰(순위 신호)은 보존하되, 이를 별도 투자 대상으로 삼을지는 다음 계획에서 판단해야 한다. D의 양성 환자 3명이라는 한계 때문에 같은 자료의 추가 변환·threshold 탐색은 정보 이득이 작다.
- 계속하려면 독립 환자 자료와 강한 단순 baseline(전문 classifier, 직접 SFT)을 갖춘 별도 계획이 필요하다.

SELF_CHECK: PASS
SUMMARY: SPIDER D/E12 저장 점수 재분석에서 두 모델의 S1 p(C) 순위(AUROC 0.73–0.74, 잔차 0.74–0.75)는 환자·ordinal·영상 수 점검 후에도 남았으나, D 고정 threshold의 E12 BA는 0.54–0.58이라 사전 후속 검토 기준에 미달해 Modic 답변 보정 투자 종료를 권고한다.

# [orchestrator] 권한 거부된 도구 호출
- Bash: cd results/iter_067/data; sha256sum pairs_D.json pairs_E12.json requests_D.jsonl requests_E12.jsonl; python -c "
import json
for f in ['protocol_D_v2','protocol_E12']:
    p=json.load(open(f+'.json'));print(f,p['requests'],p['labels'],p['code'])
"; ls ../eval ../eval/* | head -30; cd ../../..; git status --short | head; python -c "
import json,collections
for s,f in [('D','pairs_D'),('E','pairs_E12')]:
    c=collections.Counter(i['modic'] for p in json.load(open('results/iter_067/data/%s.json'%f)) for i in p['ivd']);print(s,c)
import m65_run" 
- Bash: python - <<'EOF'
import json,numpy as np
from sklearn.metrics import roc_auc_score
r=json.load(open('results/iter_068/analysis/report.json'))
for m in ['medgemma','qwen']:
    rows=[json.loads(l) for l in open(f'results/iter_067/gen_E12/{m}/worker0.jsonl')]
    lab={(p['patient'],i['k']):i['modic'] for p in json.load(open('results/iter_067/data/pairs_E12.json')) for i in p['ivd']}
    s=[x for x in rows if x['cond']=='S1']
    y=[lab[(x['patient'],x['ivd'])]==2 for x in s]; sc=[x['cand_probs'][2] for x in s]
    v=r['models'][m]
    print(m,roc_auc_score(y,sc),v['rank']['S1']['auc_all'])
    print(' S1',v['rank']['S1']['auc_all_ci95'],'within',v['rank']['S1']['within_patient']['mean_equal_weight'],v['rank']['S1']['within_patient']['n_patients_used'],v['rank']['S1']['within_patient']['n_pairs'],'so',v['rank']['S1']['same_ordinal_diffpatient'],v['rank']['S1']['same_ordinal_ci95'],'lopo',v['rank']['S1']['lopo_auc']['min'],v['rank']['S1']['lopo_auc']['max'])
    c=v['control']['S1'];print(' resid',c['auc_resid'],c['auc_resid_ci95'],'nuis',c['auc_nuisance'],c['auc_nuisance_ci95'],'sup',c['support_only']['auc_resid'],c['support_only']['auc_resid_ci95'])
    print(' aux',{k:(round(x['auc_all'],3),[round(t,2) for t in x['auc_all_ci95']],round(v['control'][k]['auc_resid'],3) if k in v['control'] else None) for k,x in v['rank'].items()})
    print(' thr',{k:(x['threshold'],round(x['D_BA'],3),round(x['E12_BA'],3),round(x['recall0'],3),round(x['recall2'],3),x['E12_BA_ci95']) for k,x in v['threshold'].items()})
    print(' pair',v['threshold_paired']); print(' lopo',v['threshold_D_lopo']['E12_BA_range'],v['threshold_D_lopo']['max_frac_changed'],{p:x['threshold'] for p,x in v['threshold_D_lopo']['per_left_out_D_patient'].items()})
    print(' nested',v['nested_bootstrap']['valid'],{k:x['ci95'] for k,x in v['nested_bootstrap'].items() if isinstance(x,dict)})
    print(' time100',v.get('nested_time_100_reps_s'),v['D']['II_rows_per_patient'])
    print(v['criteria_S1'])
EOF
