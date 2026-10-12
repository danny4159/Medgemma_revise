# 요약

- **핵심 결과:** 계획한 "같은 target 영상에서 reference만 바꾸는" 쌍이 `bench_task3.parquet`에 없었습니다. 그래서 모델 다운로드와 추론 없이 1단계에서 종료했습니다.
- **근거:** 1148행의 target 영상은 디코딩 pixel hash 기준 1146종입니다. 같은 target을 공유하는 쌍은 2개뿐이고, 둘 다 MRI(ACDC, BraTS2020)입니다. 두 GT의 IoU는 0.82와 1.0이라, 계획의 적격 기준(CT이고 IoU≤0.1)을 충족하는 쌍은 0개입니다.
- **미검증·주의:** 이번 결과는 자료 적합성 실패이고, 모델 가설은 검증되지 않았습니다. 가설을 기각한 것도 아닙니다. 사후 완화나 다른 Task·MRI로 이동하지 않았습니다.
- **다음:** 지금 자료 설계로는 같은 질문을 이어갈 근거가 없습니다. 사용자 승인 후 새 후보 선택이 필요합니다.

# Work Performed

- `bench_task3.parquet` 한 파일만 revision `557aa67d…`로 받았습니다. 전체 benchmark와 모델은 받지 않았습니다.
- 각 행의 reference box와 target 순서를 파싱하고, 디코딩 pixel hash로 target을 묶어 관계를 집계했습니다.
- 처음에는 정규식이 "first image"를 target으로 잘못 읽어 가짜 쌍 109개가 나왔습니다. `locate this object in the (\w+) image`로 고쳐 다시 집계했고, 바이트 hash와 디코딩 pixel hash 결과가 같았습니다. 최종 수치는 수정 후 값입니다.
- 수정 전 109쌍은 reference 영상과 box가 모두 같고 정답만 다른 쌍처럼 보였습니다. 이는 target 오파싱의 산물이어서 쓰지 않았습니다.
- 결정 파일은 실제 시점(2026-10-12T13:35Z)에 잠갔습니다.

# Files Changed

- 새로 만든 코드: `t3_audit.py`, `t3_relation.py`, `t3_decide.py`
- 반입 3파일: `rsna_diag/__init__.py`, `rsna_diag/geometry.py`, `rsna_diag/mi19_baseline.py`. 이미 반입돼 있었고, git blob이 reuse manifest와 일치합니다.
- 결과: `results/iter_120/data/`에 `audit_raw.json`, `relation_scan.json`, `eligibility_decision.json`, `hf/…/bench_task3.parquet`이 있습니다. `relation_scan.json`은 오파싱 상태로 만든 파일이라 폐기 대상이며, 결론에 쓰지 않았습니다.

# Commands / Experiments

- `nvidia-smi`: GPU 0·1이 모두 여유였습니다. 디스크는 `/SSD1_1TB`에 18G 남았습니다.
- `hf_hub_download`와 `t3_audit.py`: 성공했습니다.
- `t3_relation.py`: 오파싱 상태에서 실행한 탐색입니다. 정규식 수정 후에는 다시 돌리지 않았습니다.
- `t3_decide.py`: 성공했습니다. `run_models=false`로 기록했습니다.
- GPU 실험, TECH, MAIN은 실행하지 않았습니다.
- 첫 시도에서 heredoc과 f-string 중괄호가 셸 확장 검사에 막혔습니다. 우회하지 않고 파일로 작성했습니다.

# Results

- parquet 구성: 3-image 995행, 2-image 153행. target이 두 번째 영상인 행 659개, 세 번째인 행 489개.
- target 크기는 336×56이 676행, 336×336이 472행입니다.
- 다음 수치는 모두 `results/iter_120/data/eligibility_decision.json`에 있습니다.
  - 같은 target pixels 쌍 2개
  - CT 쌍 0개
  - 적격 쌍 0개
  - `run_models=false`

# Goal Progress / Reused Assets

- **시험 설정:** 이 Task3 설계는 reference 대조를 만들 수 없어 현재 실행 설계를 보류합니다.
- **연구 관찰:** 새 모델 관찰은 없습니다. iter_021의 좌표 복사와 약한 기본 localization 관찰은 그대로 보존합니다.
- **연구 질문:** 영상 간 대상 대응이 중요한 문제인지는 이번에 판단하지 못했습니다. 이번 결과는 이 공개 파일의 구조 한계입니다.
- **재사용 자산:** 좌표 변환과 NCC 3파일은 blob 일치만 확인했습니다. 모델 비교가 시작되지 않아 필수 검사(비정사각 fixture 등)는 실행하지 않았고, NCC 재사용은 미승인으로 남습니다.

# Problems

- **현재 결론 무효:** 없습니다. 수정 전 정규식 결과는 폐기했고 최종 수치는 수정 후 값입니다.
- **재사용 전 수정:** 없습니다. 다만 `t3_decide.py`의 CT 데이터셋 목록은 하드코딩이어서 재사용 전에 일반화해야 합니다.
- **추후 개선:** `t3_audit.py`의 `unparsed_source` 162행(원천명 정규식 미적용)은 이번 결론에 쓰지 않아 정리하지 않았습니다.
- **디스크 주의:** 남은 공간이 18G입니다. 후속에서 MedSeq-Grounder(약 16GB)를 받으면 거의 소진됩니다.

# Recommendation to GPT

- Task3는 행마다 reference와 target이 고유한 슬라이스입니다. 평균 bbox 점수는 구할 수 있어도 "reference만 바꾸는" 식별은 불가능합니다. 같은 질문을 이어가려면 이 파일 안에서 설계를 바꾸지 말고, 새 근거(공개 Task3의 case·view 내 다중 대상 관계)로 후보를 다시 비교해야 합니다.
- 사전 분기대로 다른 Task로 자동 이동하지 않았습니다. 후속 후보 선택은 사용자 승인 후에 하는 것을 권합니다.

SELF_CHECK: PASS
SUMMARY: Task3 parquet에서 동일 target pixels·다른 reference의 CT 쌍이 0개(전체 2쌍, 모두 MRI·GT 중첩)로 확인돼 모델 실행 없이 자료 적합성 실패로 종료함; 모델 가설은 미검증.

# [orchestrator] 권한 거부된 도구 호출
- Bash: python - <<'EOF'
import pyarrow.parquet as pq, json, collections, hashlib, re
p='results/iter_120/data/hf/datasets--MedSG-Bench--MedSG-Bench-parquet/snapshots/557aa67d13c4cbfe458ca9d1d02f42dfee185d1a/bench_task3.parquet'
t=pq.read_table(p).to_pylist()
rows=[]
for i,r in enumerate(t):
    n=r['num_images']
    h=[hashlib.sha256(r[f'image_bytes_{k}']).hexdigest()[:12] for k in range(1,n+1)]
    paths=json.loads(r['images_json'])
    m=re.search(r'in the (\w+) image',r['question'])
    ref=re.search(r'\(\((\d+),(\d+)\),\((\d+),(\d+)\)',r['question'].replace('<|box_start|>','(').replace('<|box_end|>',')')) 
    rows.append(dict(i=i,n=n,h=h,paths=[x.split('/')[-1] for x in paths],tv=m.group(1) if m else None,ans=r['answer_xyxy'],size=r['extra_json'],q=r['question']))
src=collections.Counter(re.sub(r'_npy.*','',x['paths'][0].split('_CT_')[0]+'_'+x['paths'][0].split('_CT_')[1].split('_npy')[0]) for x in rows)
print(src.most_common(40))
# group by (target pixel hash)
def tgt(x):
    k={'first':0,'second':1,'third':2}.get(x['tv']); return x['h'][k] if k is not None and k<x['n'] else None
g=collections.defaultdict(list)
for x in rows: g[tgt(x)].append(x)
print(len(g), collections.Counter(len(v) for v in g.values()))
for k,v in list(g.items())[:0]: pass
multi=[v for v in g.values() if len(v)>1]
print(len(multi))
for v in multi[:3]:
    for x in v: print(x['i'],x['paths'][0],x['tv'],x['ans'],x['q'][:150])
    print()
print(collections.Counter(x['tv'] for x in rows), collections.Counter(x['size'] for x in rows).most_common(8))
EOF
- Bash: python - <<'EOF'
import json
r=json.load(open('results/iter_120/data/audit_raw.json'))
print(len(r['pairs_sample']))
EOF
python - <<'EOF'
import sys
sys.path.insert(0,'.')
import t3_audit as a, collections, itertools
rows=a.load()
for r in rows:
    k=a.ORD[r['tv']]; r['tsha']=r['sha'][k]
g=collections.defaultdict(list)
for r in rows: g[r['tsha']].append(r)
c=collections.Counter()
for v in g.values():
    for x,y in itertools.combinations(v,2):
        c[(x['ref']==y['ref'], x['sha'][0]==y['sha'][0], x['ans']==y['ans'], x['tv']==y['tv'])]+=1
print(c)
# 같은 case 내 reference가 다른 행 (target 영상 hash 무관): 같은 case/target view, 다른 reference box/organ
g2=collections.defaultdict(list)
for r in rows:
    s=r['src'][0]
    if s: g2[(s['dataset'],s['case'],r['src'][a.ORD[r['tv']]]['view'] if r['src'][a.ORD[r['tv']]] else None)].append(r)
print(collections.Counter(len(v) for v in g2.values()))
n=0
for k,v in g2.items():
    if len(v)>1 and len({x['src'][0]['organ'] for x in v})>1 and n<5:
        n+=1
        for x in v: print(k,x['i'],x['src'][0]['organ'],x['src'][0]['view'],x['ref'],x['ans'],x['tsha'][:8],x['tv'],x['sizes'])
EOF
