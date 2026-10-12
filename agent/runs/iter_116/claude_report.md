# 요약

- **핵심 결과:** 본 비교(불일치 87명 + 일치 대조 87명, 696요청)는 **실행하지 않았다.** 사전 형식 분기(기술 12명 중 한 조건이라도 resolved가 6명 미만이면 본생성 보류)에서 T(텍스트만, 영상 없음) 조건이 resolved 5/12여서 `run=false`가 됐다. 정확도 평가, 교정·손상 수, 투자 분기 판정은 모두 없다.
- **근거:** T는 12명 중 7명에서 "I am unable to answer…"로 답을 거부했다. E와 R은 각각 9/12 resolved였고, 미해결 3건은 모두 답을 먼저 쓰고 설명에 could 같은 표현이 있어 고정 hedge 규칙에 걸린 것이다. N은 12/12였다. 파서와 prompt는 바꾸지 않았다.
- **미검증·주의:** 교정이 유용한지는 전혀 판단하지 못했다. "한 조건이라도 미달이면 보류"가 영상 없는 대조군 T에도 적용되는지는 계획 문구가 문자 그대로만 정한다. 나는 문자 그대로 따랐고, 이 해석은 GPT 리뷰가 판단해야 한다.
- **다음:** 사용자 승인 후 선택지는 두 가지다. (a) T를 보고용 대조에서 빼고 본비교를 진행한다. (b) 현 분기대로 이 설정을 종료한다. 별도 관찰로 생성 없는 단순 대조 M(K/B/G 다수결)이 불일치 87명에서 이미 54/87을 맞힌다(아래 Results).

# Work Performed

- 반입 파일은 `reuse_manifest`의 상태가 `pending_validation`이었고, required_checks를 실제 호출 경로 기준으로 수행했다.
- `pg43_run.py`를 수정했다.
  - `CODE_FILES`를 adapter 없는 경로의 실제 의존성(5개)으로 줄였다. pg39·lora 등 미사용 파일은 제외했다.
  - 출력 0건 비용 집계가 죽지 않도록 `cost_summary`/`occupancy`를 보완했다.
  - record에 `physical_gpu`를 기록하고, 재개 전후 GPU 귀속은 record 값을 쓰도록 했다.
  - attempt별 `launch_children.a{N}.json`을 보존하고, 이번 attempt 비용(`cost_this_attempt`)과 누적 비용을 분리했다.
- `ed116_link.py`는 `ev111_link`의 결함을 보완한 새 파일이다. `ev111_link.py` 자체는 수정하지 않았다.
  - 원 protocol *내용*에서 `sha256(canon(locked))`를 재계산해 completion digest와 대조한다. 비-코드 잠금 파일의 현재 hash가 다르면 거부한다.
  - worker 파일의 record 수를 `completion.per_file`과 대조한다.
  - decoded pixel hash가 다르면 거부한다.
  - 정답이 없는 `ledger_nogt.json`과 평가 전용 `gt.json`으로 분리해 쓴다.
  - iter_111 ledger와의 내용 회귀 대조는 600행 모두 일치했다.
- `ed116_spec.py`에 선택, 입력 문구, 근거 packet, 정책(K/B/G/M/N/E/R/T/S)을 정의했다.
- `ed116_eval.py`에 평가 지표를 정의했다.
  - 공동 지표, 미해결 변수 전수 열거 범위, 환자 bootstrap, 사전 분기 `decide`, 기술 게이트가 들어 있다.
  - 계획에 없는 사건 수 문턱은 추가하지 않았다.
- 평가 코드 잠금은 TECH 생성 전인 **2026-10-12T06:26:11Z**에 했다. 잠금 파일 26개가 지금도 모두 일치한다.
- `ed116_analyze.py`와 `ed116_verify.py`는 MAIN 분석용이다. 잠금에는 포함했지만 MAIN을 실행하지 않아 실제 데이터로는 한 번도 돌려보지 못했다.

# Files Changed

- 새 파일(연구 코드)
  - `ed116_spec.py`, `ed116_eval.py`, `ed116_link.py`, `ed116_build.py`, `ed116_analyze.py`, `ed116_verify.py`
  - `ed116_verify_selection.py`, `ed116_baselines.py`, `ed116_directcheck.py`
  - `test_ed116.py`, `test_ed116_runtime.py`
- 선별 반입 후 수정: `pg43_run.py`
- 반입, 무수정: `ev109_extract.py`, `ev108_spec.py`, `test_ev109_extract.py`, `ev111_link.py`, `rsna_diag/{__init__,generate,geometry,parse,prompts,qa_spec,metrics}.py`
- 결과는 `results/iter_116/`에만 저장했다: `provenance`, `lock`, `requests`, `protocol`, `gen`, `tech`, `tests`, `eval_partial`.
- 잠금 이후에 추가한 파일(`ed116_baselines.py`, `ed116_directcheck.py`, `ed116_verify_selection.py`, `test_ed116_runtime.py`)은 `RESULT_MANIFEST.json`에 hash를 기록했다.

# Commands / Experiments

| 단계 | 결과 |
|---|---|
| `ed116_link.py` | 성공. 600행, pixel hash 재현 600/600, 문제 0건 |
| `test_ed116.py` | 32/32. 비정사각 좌표 fixture, 열거식 독립 matching(600건), 미해결 범위 전수 교차곱 일치, ev109 fixture 유지 포함 |
| `ed116_build.py` select, requests, weights, lock, protocol | 성공. 가중치 12파일은 iter_108 lock과 차이 0 |
| TECH 2 worker(48요청) | 성공. wall 105.4초 |
| TECH 4 worker(48요청) | 성공. wall 60.3초 |
| RESUME8 | 1 worker 3건 후 중단(exit 1), 꼬리 부분 행을 일부러 붙여 2 worker로 재개해 완료 |
| `test_ed116_runtime.py` | v1은 27/28이었다. 실패 1건은 내 기대식 오류였다(R−T 길이 차이에 영상 표식 토큰 3개가 더해짐). v2에서 28/28. v1 결과 파일도 보존했다 |
| `ed116_directcheck.py` | 4건 모두 일치. 공식 방식 입력 token, 독립 padding pixel hash, 생성 token이 같았고 text-only에는 영상 입력이 없었다 |
| `ed116_verify_selection.py` | 원시 출력에서 분모와 표본이 잠금과 일치 |
| `ed116_baselines.py` | 성공. 생성 없는 K/B/G/M 기술 |

- 병렬 구성 선택: 4 worker를 채택 후보로 기록했다.
  - 2 worker 대비 wall이 105초에서 60초로 줄었다.
  - 48요청의 출력 token이 모두 일치했다.
  - GPU당 peak 17.7GB로 2GiB 여유 조건을 만족했다.
  - MAIN은 보류라 실제 적용하지는 않았다.
- 실행 전후 GPU는 모두 비어 있었다(87/15 MiB).

# Results

- 분모 재계산(원시 출력 기준)
  - E600 600명 중 unresolved 8, 불일치 87, 일치 505.
  - 불일치 87명에서 K 정답 47, B 정답 40.
  - 일치 505명에서 둘 다 정답 427, 둘 다 오답 78.
  - 불일치 87명의 category 구성: opacity 36, normal 9, not_normal_no_opacity 42.
  - 일치 대조 87명의 구성: opacity 26, normal 30, not_normal_no_opacity 31. K 정답은 76.
  - 기술 12명과 대조 87명은 서로 겹치지 않는다.
- 기술 게이트(`results/iter_116/tech/tech_gate.json`): `run=false`.

| 조건 | resolved(12명 중) |
|---|---|
| N | 12 |
| E | 9 |
| R | 9 |
| T | **5** |

  - MAIN protocol 생성은 게이트가 막는다. 실제로 시도해 거부됐고 파일은 만들어지지 않았다.
- 응답 형식 관찰(기술 12명, 내용 정확도 아님)
  - 모두 EOS로 끝났고 재시도는 0건이다.
  - 최대 peak reserved는 8.27GiB였다.
  - T의 resolved 5건은 모두 "Yes"였고, 7건은 답 거부였다.
- 생성 없는 단순 대조(`eval_partial/baselines_no_generation.json`, 저장 출력 기반)

| 불일치 87명 | K | B | G | M |
|---|---|---|---|---|
| 정답 수 | 47 | 40 | 54 | 54 |
| 교정(K 오답 40명 중) | 0 | 40 | 20 | 20 |
| 손상(K 정답 47명 중) | 0 | 47 | 13 | 13 |

  - 불일치에서는 K≠B라서 M이 G와 같아진다(54).
  - 이 표는 계획한 비교에 필요한 단순 대조의 일부다. 분기 판정에는 쓰지 않았다.
- 비용: TECH 2 worker는 GPU 점유 185.8 device-초(적재 포함), 4 worker는 104.4, RESUME8은 60.3이었다. 직접 대조 1회는 모델 적재와 생성 4건이다.

# Goal Progress / Reused Assets

- **시험 설정:** 현 frozen MedGemma 1.5 + 이 고정 prompt/parser 조합은 T에서 형식 게이트를 통과하지 못해 본비교로 진행하지 못했다. 교정·보존 능력의 음성 결과가 아니다.
- **연구 관찰:** 영상 없이 초안과 근거만 주면 모델이 7/12 거부한다. R의 미해결 3건은 hedge 규칙 때문이고, 답 자체는 문두에 있었다. 이 부분은 가설 검증이 아니라 형식 관찰이다.
- **연구 질문:** "틀릴 수 있는 자동 근거 아래 선택적 교정"은 미검증이다. 새로 알게 된 사실은 불일치 87명에서 K/B/G 다수결 M(54/87, 교정 20, 손상 13)이 이미 단순 대조로 존재한다는 것이다. 이는 더 강한 비교 기준을 뜻하며, 질문을 기각하는 근거는 아니다.
- **운영 복구와 과학적 증거 구분:** 이번에 한 일은 대부분 실행 경로 정비다(고정 의존성 목록, 0건·재개 비용, provenance 강화).
- 반입 required_checks 수행 현황
  - 호출 의존성·source manifest: 완료.
  - 0건 비용·재개 GPU 귀속: 완료.
  - 공식 tensor와 직접 generate 4건: 완료.
  - 부분 재개·변조 거부: 완료(아래 한계 참고).
  - 2/4 worker 처리량·peak VRAM·정합성: 완료.
  - ev111_link의 protocol/pixel 강제는 새 파일 `ed116_link.py`에서 수행했다. 원 파일은 미수정이다.
  - 비정사각 좌표 fixture와 독립 matching: 완료.
  - gate 적용 후 box 기준 공동 지표: 구현과 fixture는 검증했지만, 실제 MAIN 데이터에서는 미실행이다.

# Problems

- **현재 결론에 영향:**
  - MAIN이 보류되어 교정·손상·공동 지표 결과가 없다.
  - 게이트 규칙 해석 미정: T는 비교 지표가 아닌 영상 제거 대조인데, 규칙은 "네 조건 중 하나라도"로 적혀 있다. 나는 임의로 완화하지 않았다.
  - 표본 변동에 따른 "불확정" 판정은 계획에 수치 기준이 없다. 그래서 `decide`는 CI를 쓰지 않고, 미해결 배정 범위만 쓴다. MAIN이 실행되면 CI는 서술로 보고해야 한다.
- **재사용 전 수정:**
  - `ed116_analyze.py`와 `ed116_verify.py`는 실제 MAIN 출력으로 돌려보지 못했다. 잠금 후 오류가 발견되면 amendment로 기록해야 하며 새 과학 기준 변경이 아니다.
  - 변조 거부 검사는 `verify_completion`을 대상으로 한다. 실행 중 worker 경로의 동시 소유권(flock)은 별도로 시험하지 않았다.
  - 강제 SIGKILL 재개는 시험하지 않았다. 꼬리 부분 행을 인위적으로 붙여 정상 종료 후 재개하는 검사로 대체했고, 실제 프로세스 강제 종료 시나리오는 미검증이다.
- **추후 개선:** `results/iter_116/tests_resume_before_sha.txt`는 `tests/` 밖에 만든 임시 파일이다. 내용은 재개 검사의 기준 hash 하나다.

# Recommendation to GPT

1. 게이트 해석을 먼저 판단해야 한다. T 부분 미달을 "본생성 보류"로 확정할지, 영상 없는 대조 T를 보고용으로만 두고 N/E/R 본비교를 진행할지 정해야 한다. 후자라면 파서·prompt·기준은 현 상태 그대로 두는 것이 좋다.
2. 본비교를 진행한다면, M이 이미 54/87을 맞히므로 성공 기준 "각 대조보다 5명 이상 많이"가 실질적으로 R ≥ 59/87을 요구한다는 점을 계획에 명시해 판단 근거로 삼는 편이 좋다. 이 값은 이미 정해진 기준에서 산출되는 것이고 기준을 바꾼 것은 아니다.
3. 4 worker가 처리량과 정합성 면에서 유리하다. 본실험 시 약 696요청에 약 10분 안팎으로 추정된다(추정치이며 TECH 48요청 60초 기준).
4. 현 설정을 종료한다면 iter_115의 CURE 특화 투자 보류로 복귀하는 것이 계획에 이미 정해져 있다. 그 경우 오류 검토 묶음의 남은 후보는 없다.

SELF_CHECK: FAIL
SUMMARY: 불일치 87명 vs 일치 대조 87명 교정·보존 비교의 본생성(696요청)은 사전 기술 게이트에서 T 조건 resolved 5/12로 보류됐고, 연결·잠금·재개·공식 대조 검증은 완료했으며 정확도 판정은 없다.

# [orchestrator] 권한 거부된 도구 호출
- Bash: git ls-tree -r --name-only c2602f4b237ec9a90b7e04c99474ea7a0003bfb0 | grep -E "^(ev108|pg43|pg39|rsna_diag|test_ev108)"
- Bash: git ls-tree -r --name-only c2602f4b237ec9a90b7e04c99474ea7a0003bfb0 -- ev108_run.py ev108_build.py pg39_spec.py pg39_data.py rsna_diag
- Bash: python - <<'EOF'
import json
L=json.load(open('results/iter_111/provenance/ledger.json'))['rows']
r=L[0]; print({k:(v if k not in('O','SFT','det') else '...') for k,v in r.items()})
print(r['O'].keys(), r['SFT'].keys(), r['det'])
print(sum(x['id']==x['patient'] for x in L), set(tuple(x['size_hw']) for x in L))
print(L[0]['O']['raw'][:100], L[0]['SFT']['raw'][:200])
EOF
nvidia-smi --query-gpu=index,memory.used,memory.total --format=csv,noheader
echo $CUDA_VISIBLE_DEVICES
- Bash: python - <<'EOF'
import json
L=json.load(open('results/iter_111/provenance/ledger.json'))['rows']
print([(x['id'],x['patient']) for x in L[:3]])
P=json.load(open('results/iter_111/eval/per_patient.json'))
import collections
# regression: det_nonempty from scores>=0.7
n=0;bad=0
byid={x['id']:x for x in L}
for p in P:
    d=byid[p['id']]['det']
    ne=any(s>=0.70 for s in d['scores'])
    n+=1; bad+= (ne!=p['det_nonempty'])
print(n,bad)
print(collections.Counter(p['ans_source'] for p in P), collections.Counter(p['ans'] for p in P))
EOF
- Bash: python - <<'EOF'
import json,hashlib
c=json.load(open('results/iter_012/confirm_sft_seed17/completion.json'))
print({k:(v if not isinstance(v,(dict,list)) else '...') for k,v in c.items()}.keys() if False else list(c.keys()))
p=json.load(open('results/iter_012/protocols/main_protocol.json'))
print(list(p.keys()))
t=c['protocol_digest']
def cands(o):
    yield 'sk', json.dumps(o,sort_keys=True)
    yield 'ska', json.dumps(o,sort_keys=True,ensure_ascii=False,default=str)
    yield 'skc', json.dumps(o,sort_keys=True,separators=(',',':'))
for name,o in [('all',p)]+[(k,p[k]) for k in p]:
    for n,s in cands(o):
        if hashlib.sha256(s.encode()).hexdigest()==t: print('MATCH',name,n)
print(hashlib.sha256(open('results/iter_012/protocols/main_protocol.json','rb').read()).hexdigest()==t, t)
print(c.get('n_expected'), c.get('per_file'))
EOF
- Bash: echo "CVD=$CUDA_VISIBLE_DEVICES"; python pg43_run.py launch --requests results/iter_116/requests/TECH.jsonl --protocol results/iter_116/protocol/protocol_TECH.json --out-dir results/iter_116/gen/TECH_w2 --workers 2 --peak-gb 12
- Bash: CUDA_VISIBLE_DEVICES=0 python ed116_directcheck.py results/iter_116/gen/TECH_w2 results/iter_116/tests/direct_check.json
- Bash: python - <<'EOF'
import json, os
import ed116_eval as EV, ed116_spec as ES
rows=dict((r['id'],r) for r in json.load(open('results/iter_116/provenance/ledger_nogt.json'))['rows'])
gt=json.load(open('results/iter_116/provenance/gt.json'))
sel=json.load(open('results/iter_116/lock/selection.json'))
out={}
for g,ids in (('mismatch',sel['mismatch']),('control',sel['control'])):
    ps=[EV.make_patient(rows[i],gt[i],{}) for i in ids]
    pt=[EV.point_scalars(p) for p in ps]
    d={}
    d['n']=len(ps)
    d['correct']={q:sum(x['correct_'+q] for x in pt) for q in ('K','B','G','M')}
    d['correction']={q:sum(x['correction_'+q] for x in pt) for q in ('K','B','G','M')}
    d['harm']={q:sum(x['harm_'+q] for x in pt) for q in ('K','B','G','M')}
    d['joint03']={q:sum(x['joint03_'+q] for x in pt) for q in ('K','B')}
    d['joint05']={q:sum(x['joint05_'+q] for x in pt) for q in ('K','B')}
    d['by_category_correct']={}
    for c in ('opacity','normal','not_normal_no_opacity'):
        idx=[k for k,p in enumerate(ps) if p['cat']==c]
        d['by_category_correct'][c]=dict(n=len(idx),**{q:sum(pt[k]['correct_'+q] for k in idx) for q in ('K','B','G','M')})
    out[g]=d
os.makedirs('results/iter_116/eval_partial',exist_ok=True)
json.dump(dict(note='생성 없는 저장 출력 기반 단순 대조(K/B/G/M). 평가 잠금 코드 사용. N/E/R/T/S는 MAIN 미생성으로 없음.',**out),open('results/iter_116/eval_partial/baselines_no_generation.json','x'),indent=1)
print(json.dumps(out,indent=1))
EOF
