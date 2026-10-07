# 요약

- **핵심:** 저장 자료만으로 분석을 마쳤다(CPU 2.4초, 새 학습·생성·GPU 0). 현재 recipe에서 새 loss나 seed를 늘릴 근거는 찾지 못했다. 구체적인 보완은 하나도 지지되지 않았다. 판단을 바꾸는 결측은 하나 남았고, 선택된 epoch1 checkpoint의 V32 생성이다.
- **근거:**
  - 원 선택(R/G 모두 lr2e-4, epoch1)은 그대로 재현됐다.
  - 모든 LR×epoch 중 NLL이 가장 낮은 곳은 lr1e-4 epoch2(R 1.460, G 1.462)였다. 선택값은 1.523/1.526이다.
  - 같은 V32 환자에서 NLL 변화와 recall 변화의 Spearman은 약 0(−0.11~0.19)이어서 NLL은 판독 회복의 대리지표로 지지되지 않는다.
- **주의:** V32는 32명이고 모두 사후 개발 자료다. 의미 판정은 assistant 규칙이며 전문의 검토가 아니다. 의미 규칙에 따라 모순 결론이 불확정이 된다.
- **다음:** 선택된 checkpoint(R/G lr2e-4, epoch1)의 V32 생성 64요청을 별도 계획으로 시험할지 GPT가 판단한다. 이 결측이 투자 판단을 바꾸는지가 기준이다.

# Work Performed

- 입력 57개 파일의 hash를 고정하고 `val_sha`·`train_sha`·`patient_ids`를 manifest와 대조했다.
- T512/V64의 target 구성을 환자·문장 단위로 집계했다.
- 4개 trajectory×epoch 1/2/4/6의 V64 환자별 NLL을 manifest 순서로 연결했다. 환자 평균이 저장된 `report_nll`과 일치함(오차 1e-9 미만)을 확인했다.
- 원 선택 규칙(LR→공통 epoch)을 재현했다. 전체 최소 선택은 사후 민감도로만 보고했고 선택 파일은 건드리지 않았다.
- 동일 V32의 base 32개와 R/G×두 LR×epoch2/6 저장 출력 288개를 연결했다. base는 epoch2에만 있어 한 번만 센다. 환자별 recall 획득·소실, 정상문만 출력한 비율, paired bootstrap 10,000회, leave-one-patient-out을 계산했다.
- 의미 규칙 5군(일반 정상문, other 범위, 급성 부정, 구체적 부정, 위치·속성)의 fixture 18개를 구현 전에 고정했다. 이후 기존 claim 중 해당하는 것에 규칙을 적용했다.
- 독립 verifier로 핵심 수치를 재계산했다.

# Files Changed

- 신규 코드: `report93_fixtures.py`, `report93_sens.py`, `report93_analyze.py`, `report93_verify.py`
- 신규 결과: `results/iter_093/main/` (`RESULTS.md`, `verify.json` 포함)
- `results/iter_093/` 루트의 JSON은 개발 중 1회 실행본이다. 덮어쓰기를 막는 설계라 지우지 않고 보존했으며 `main/`이 최종본이다.
- 기존 코드·결과는 수정하지 않았다.

# Commands / Experiments (실제 실행한 명령과 성공/실패)

- `python report93_analyze.py`: 성공(두 번 실행, 각 약 2.4초).
- `python report93_verify.py`: 성공, 21/21 PASS.
- fixture 실행: 18/18 통과. 사후 규칙 변경은 없다. 실행 전에 fixture 두 건의 `stated_findings` 입력 누락만 고쳤다.
- 학습·생성·GPU 사용은 없다.

# Results (수치와 결과 파일 경로)

모두 `results/iter_093/main/` 기준이다.

**target** (`target_composition.json`)
- T512 512명 중 정상 전용 185명(36%), 비정상 201명, 비정상+정상 혼합 126명이다.
- 정상문 단어 비중은 36%다.
- 정상문 377개 중 4개 일반문("no significant findings", "no other relevant findings", "no relevant findings", "within normal limits")이 132개다.
- 소견 label 93종 중 46종은 환자 ≤2명에만 노출됐다.
- 제외 문장은 74개(51명)다. report 재구성 불일치는 0이다.

**NLL·선택** (`nll_trajectories.json`)
- 선택은 재현됐다.
- 모든 trajectory에서 epoch6 NLL이 epoch2보다 높다(R lr1e-4 1.46→2.39 등). abnormal 포함 환자의 NLL 상승이 더 크다.
- 정상 전용 군과 abnormal 포함 군의 최소 NLL epoch은 군별로 다르지만, 선택에는 영향이 없다.

**V32 생성** (`v32_generation.json`, 분모: 전체 32, 비정상 21, recall 적격 20)

| 조건 | strict recall |
|---|---|
| base | 0.167 |
| R/G epoch2 | 0.075–0.167 |
| R/G epoch6 | 0.142–0.200 |

- epoch6 이득은 환자 3명(26580211 pacemaker, 23603534, 22968225 cardiomegaly)의 atom 획득 4건과 소실 2건의 합이다.
- paired CI는 대부분 0을 포함한다. G lr1e-4의 6−2는 +0.067, CI [0.0, 0.183], LOO 최소 0.018이다.
- recall 적격 20명 중 정상문만 출력한 환자는 base 11, R/G는 4–9다.
- 모순이 있는 환자는 base 7, R/G 1–3이다(기존 규칙).

**의미 민감도** (`semantic_sensitivity.json`)
- 중요도 범위를 따르는 규칙에서는 모순 환자가 base 10, R/G 5–10이 된다.
- "R/G가 모순을 줄였다"는 결론은 일반 정상문 해석에 따라 불확정이다.
- 원 E128 결과(+0.532pp, 회복 1명, 기준 미달)와 recall 적격 94명 분모는 그대로 유지한다. 430/512=84.0% 정정은 iter_092 review에서 확인한 값이며, 새 보고서에서 원본을 바꾸지 않았다.

# Goal Progress / Reused Assets

- **진전:** "R/G가 base보다 낮았던 이유"에서 세 가지를 좁혔다.
  - 선택 규칙 위반은 아니다.
  - NLL은 대리지표로 부적합하다.
  - 모순 감소 결론은 의미 규칙에 민감하다.
- **재사용:** 기존 trainer·선택·evaluator 파일은 수정 없이 읽기만 했다. `report92_autojudge.py`는 재사용하지 않았다. 새 규칙 `report93_sens.py`는 fixture 18개 범위의 한정 규칙이며 범용 평가기가 아니다.
- **미검증:** 독립 임상 확인, epoch1·epoch4의 V32 생성, E128의 의미 재평가는 하지 않았다. 의미 판정은 assistant 규칙이고 전문의 검토가 아니다.

# Problems (현재 결론 무효 / 재사용 전 수정 / 추후 개선을 구분)

- **현재 결론 무효:** 없음.
- **재사용 전 수정:** `report93_sens.py`의 other_scope 규칙은 MINOR 소견(척추측만 등)을 제외하지 않는다. 이 때문에 "No other relevant findings."가 일부 환자에서 contradicted로 판정된다. 동결된 fixture의 범위 밖이라 사후에 고치지 않았고 그대로 보고한다.
- **추후 개선:**
  - verifier는 변조 거부 fixture를 따로 갖지 않는다. hash와 anchor 검사가 있을 뿐이다.
  - "정상문만 출력"의 원문 기반 독립 정의는 claim 기반 정의와 90% 이상 일치만 확인했다.

# Recommendation to GPT

- **선택:** 판단을 바꾸는 결측 하나를 한정 측정하는 쪽을 권고한다. 선택된 R/G lr2e-4 epoch1 checkpoint의 V32 생성 64요청이며, 새 학습은 없다.
- **이유:** 저장 자료만으로는 선택된 checkpoint가 epoch2/6보다 recall이 낮은지 알 수 없다. 낮다면 NLL 중심 선택이 baseline을 약하게 만든 구체적 결함이 되어, 생성 기반 checkpoint 선택이라는 보완 하나를 시험할 근거가 생긴다. 같거나 높다면 현재 recipe의 추가 seed·epoch·위치 loss 투자는 보류한다.
- **참고:** epoch6 이득은 3명 환자에 집중돼 있어 확대 근거로 쓰지 않는다.

SELF_CHECK: PASS
SUMMARY: 저장 target·NLL·V32 생성을 연결한 CPU 진단에서 원 선택은 재현됐고 NLL은 회복의 대리지표가 아니며(Spearman≈0), 모순 감소 결론은 의미 규칙에 따라 불확정이다. 선택 epoch1 V32 생성 한정 측정 또는 투자 보류를 권고한다.

# [orchestrator] 권한 거부된 도구 호출
- Bash: cd /SSD1_1TB/home/milab/daniel/08_medgemma/research/results/iter_090; python - <<'E'
import json
l=json.loads(open('recovery/validation/epoch2/R_lr0.0001_report/worker_0.jsonl').readline())
print({k:(str(v)[:200] if k!='input_ids' else len(v)) for k,v in l.items()})
ref=json.load(open('semantic/V32_reference_v3.json'));rows=ref['rows'] 
print(type(rows)); 
if isinstance(rows,str): rows=json.loads(rows.replace("'",'"')) if False else None
print(type(ref['rows']),len(ref['rows']))
r=ref['rows'][0]; print(json.dumps(r,ensure_ascii=False)[:2500])
E
- Bash: cd /SSD1_1TB/home/milab/daniel/08_medgemma/research; python - <<'E'
import json
from collections import Counter
R='results/iter_090/recovery/semantic/'
for ep in (2,6):
    po=json.load(open(R+f'epoch{ep}/eval/per_output.json'))
    print(ep,Counter(x['condition'] for x in po))
    c=Counter()
    for x in po:
        for cl in x['claims']:
            c[(cl['polarity'],cl['status'])]+=1
            if cl['status']=='contradicted': print(ep,x['condition'],x['image_id'][:8],cl['finding'],'|',cl['quote'],'|',cl['refs'],cl.get('note'))
    print(c)
x=po[0]; print({k:v for k,v in x.items() if k not in('claims',)})
print([ (x['condition'],x['matches']) for x in po if x['matches']][:2])
E
ls results/iter_090/recovery/validation/epoch6/ | grep -i base; cat results/iter_090/recovery/validation/base_coverage.json | head -c 600
- Bash: cd /SSD1_1TB/home/milab/daniel/08_medgemma/research/results/iter_093; python -c "
import json
from collections import Counter
s=json.load(open('semantic_sensitivity.json'))
print(s['fixtures_by_group'],sum(x['ok'] for x in s['fixtures']),len(s['fixtures']),s['anchor_failures'])
for k,v in s['claim_summary'].items(): print(k,v)
print(s['patient_level_contradiction_original_vs_conservative'])
print(Counter((r['group'],r['original'],r['conservative']) for r in s['claim_review']))
for r in s['claim_review']:
    if r['changed']: print(r['cond'],r['image_id'][:8],r['group'],r['finding'],'|',r['quote'],r['original'],'->',r['conservative'])
v=json.load(open('v32_patient_view.json'))
# who gains
base=v['base@0']
for k in ['R_lr0.0001@6','G_lr0.0001@6','R_lr0.0002@6']:
    prev=v[k.replace('@6','@2')]
    for a,b in zip(prev,v[k]):
        if set(b['strict_atoms'])!=set(a['strict_atoms']): print(k,a['image_id'][:8],a['strict_atoms'],'->',b['strict_atoms'])
"
