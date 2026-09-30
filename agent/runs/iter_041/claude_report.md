# Work Performed

# 요약

- **핵심 결과:** 두 문장을 한 요청으로 묻는 공동 grounding에서 정확도가 크게 떨어졌다. V96 개발 집합에서 C의 환자 평균 F1@0.3은 독립 I 0.578, 공동 J_AB 0.381, J_BA 0.354다. 그 결과 사전 규칙상 "방법 pilot 우선 후보"로 판정됐다. 이는 확정이 아니고 개발 자료 한 번의 관찰이다.
- **근거:** C의 Δ_AB=0.197(97.5% CI [0.120, 0.273]), Δ_BA=0.224([0.143, 0.301])다. B도 0.168/0.201로 같은 방향이다. 두 경우 모두 valid 응답 100%, truncation 0이다. 독립 재계산은 환자별 점수가 100% 일치했다.
- **비용:** 독립 처리(두 요청)가 J보다 device-seconds 1.33배(J_AB)/1.31배(J_BA), 처리량은 J의 0.756/0.760배(같은 4 worker)다. 환자 p95 지연 비율은 1.07/1.02로 사전 기준 1.20에 못 미쳤다. 비용 기준은 처리량 경로로 충족됐다.
- **주의:** J 출력은 문장당 거의 항상 box 1개다(J 응답 188/192가 1개). GT가 복수 box인 문장은 F1이 I 0.545→J 0.22로 특히 낮다. 단일 box 환자 60명에서도 손실이 남는다(CI 하한 >0). 공동 형식을 학습하지 않은 인터페이스 효과가 배제되지 않았다.
- **다음:** 방법 pilot 여부는 GPT가 결정한다. 후속 pilot을 한다면 공동 형식의 직접 CE 대조군을 먼저 넣어야 한다.

## 상세

- 기존 브랜치 `approach/sentence-evidence-binding`을 유지하고 iter_040의 다섯 파일을 반입했다.
  - 반입 파일: `pg40_run.py`, `pg40_verify.py`, `pg40_gen_test.py`, `rsna_diag/lora.py`, `rsna_diag/queue_lock.py`.
  - 각 blob이 매니페스트의 SHA와 일치함을 직접 계산해 확인했다.
  - 다섯 파일과 새 파일 전체를 import 확인했다.
  - 반입한 `pg40_run.py`는 수정하지 않고, iter_040 출력 검증 전용으로 보존했다.
- 새 runner `pg41_run.py`를 만들었다(`pg40_run.py` 복사 후 수정).
  - 평가 GT manifest·selection lock·`pg41_rules.py`·`pg39_spec.py`를 protocol에 hash로 잠근다.
  - 부분 행 복구 시 잘라낸 원본 바이트를 `.partial.*.bin`으로 보존한다.
  - record에 `t_start`, worker 타이밍 파일을 추가했다.
  - `verify_completion`이 현재 영상 file/pixel hash, record 필드와 요청 행의 일치, config·adapter digest, worker 파일 집합을 재검증한다.
  - launcher가 device-seconds를 기록한다(GPU별 요청 구간의 합집합을 합산해 겹침을 중복 계산하지 않는다).
- 요청 파일을 만들었다.
  - `pg41_build.py`로 D24(96)·D8/B(32)·V96 J_AB(96)·J_BA(96)·I-cost(192)를 생성했다.
  - 기존 요청과 대조해 I-short 256건, J-short(AB) 128건의 prompt·영상 hash가 모두 일치했다.
  - J_BA는 문장 순서만 바꾸고 qA/qB ID와 targets는 유지했다.
- 판정 규칙은 `pg41_rules.py`에 결과를 보기 전에 고정하고 protocol에 잠갔다.
- 도달 단계는 "동작 확인 + V96 가능성 탐색"이다. 학습·신규 환자 확대·H192·F120·test는 사용하지 않았다.

# Files Changed

새 파일만 만들었다(모두 untracked, 기존 파일 수정 없음).

- 실행·검증: `pg41_run.py`, `pg41_build.py`, `pg41_rules.py`, `pg41_eval.py`, `pg41_verify.py`, `pg41_post.py`, `pg41_d24_config.py`, `pg41_gen_test.py`, `run_iter041.py`
- 테스트: `test_pg41.py`, `test_pg41_eval.py`
- 반입 5개: `pg40_run.py`, `pg40_verify.py`, `pg40_gen_test.py`, `rsna_diag/lora.py`, `rsna_diag/queue_lock.py`
- 결과: `results/iter_041/` 아래(requests, protocol, gen, eval, decisions, tests, summary.json)

# Commands / Experiments (실제 실행한 명령과 성공/실패)

모두 성공했다.

- `python pg41_build.py --out-dir results/iter_041/requests`
- `python test_pg41.py ...`: 29/29 PASS (합성 fixture)
- `python test_pg41_eval.py ...`: 19/19 PASS
- `python pg41_gen_test.py`: 11/11 PASS (GPU, B adapter, D8 32요청)
- `python run_iter041.py --stage d24`: D24 C 96요청을 2 worker와 4 worker로 실행
- `python pg41_d24_config.py`
- `python run_iter041.py --stage v96 --workers 4 --peak-gb 9`: 큐 순서 C:J_AB → C:I-cost → C:J_BA → B:J_AB → B:J_BA
- `python pg41_eval.py --config results/iter_041/eval/config_V96.json ...`
- `python pg41_verify.py ...`
- `python pg41_post.py ...`

GPU 구성 선택은 D24 실측으로만 했다.

| 구성 | wall | 처리량 | peak/GPU | token |
|---|---|---|---|---|
| 2 worker | 376.6초 | 15.3 req/min | 8,963/8,891 MiB | 기준 |
| 4 worker | 226.0초 | 25.5 req/min | 17,836/17,765 MiB | 2w와 불일치 0/96 |

4 worker는 1.67배 빠르고 GPU당 여유가 약 6.7GB라 worker당 2GB 이상을 확보했다. 그래서 4 worker(GPU당 2)를 채택했고 OOM은 없었다.

V96 생성은 총 576요청이고 5개 큐가 모두 종료 코드 0으로 끝났다. 큐 wall은 271~362초다.

# Results (수치와 결과 파일 경로)

**정확도** (V96 96명, F1@0.3 환자 평균, `results/iter_041/eval/report_V96.json`)

| 모델 | I | J_AB | J_BA | Δ_AB (97.5% CI) | Δ_BA (97.5% CI) |
|---|---|---|---|---|---|
| C(주분석) | 0.5780 | 0.3811 | 0.3542 | 0.197 [0.120, 0.273] | 0.224 [0.143, 0.301] |
| B(민감도) | 0.5559 | 0.3880 | 0.3550 | 0.168 [0.098, 0.240] | 0.201 [0.126, 0.275] |

- C의 공통 valid/EOS subset은 96명 전체다(모든 응답이 valid·EOS). B도 같다.
- 기존 iter_040 C/B의 I 수치를 그대로 재현했고, 새 판정은 이 값을 기준점으로 썼다.
- F1@0.5는 C의 I 0.291, J_AB 0.135, J_BA 0.116이다.
- 순서 효과는 J_AB−J_BA 0.027(95% CI [−0.055, 0.107])로 불확정이다.
- C의 문장 단위로는 I가 완전 성공한 101문장 중 J_AB에서 48문장, J_BA에서 52문장을 잃었다. 잃은 원인은 대부분 위치·개수(44/49건)였다. 다른 문장에 배정된 경우는 4/2건이다.
- 그룹 교환 oracle의 이득은 C에서 +0.042/+0.030이다. 배정 오류는 설명의 일부일 뿐이다.
- 사후 분석(`post_hoc_count_V96.json`, 판정에 쓰지 않음):
  - C의 GT 복수 box 문장은 I 0.545, J_AB 0.216, J_BA 0.255다.
  - GT 단일 box 문장은 I 0.589, J_AB 0.434, J_BA 0.386이다.
  - 두 문장 모두 GT 단일 box인 환자 60명의 Δ_AB는 0.147 [0.044, 0.258], Δ_BA는 0.189 [0.092, 0.289]다.

**비용** (같은 4 worker·2 GPU 큐, C, `report_V96.json`의 `cost`)

- 독립 I 대 J_AB/J_BA:
  - device-seconds 비율은 1.326/1.311이다.
  - 요청 wall 합 비율의 환자 bootstrap 95% CI는 [1.28, 1.42]/[1.27, 1.42]다.
  - 처리량 비율은 0.756/0.760이다.
  - p95 지연 비율은 1.069/1.024이고 CI는 [1.000, 1.198]/[0.972, 1.147]이다.
- 사전 규칙 결과: accuracy=positive, cost_burden=true(처리량 경로), cost_boundary=false, overall=`positive_method_pilot_candidate`.
- I 재실행 192요청의 token은 저장된 기존 출력과 불일치 0이다.
- 실행 순서는 사전 고정한 J_AB, I, J_BA 한 번뿐이다. 순서 편향은 통제하지 못했고, 반복 측정은 하지 않았다.

**검증**

- `verify_V96.json`: 별도 parser·좌표 변환·augmenting-path matching으로 재계산했다. 환자별 F1은 C/B 모두 최대 차이 0이고, F1@0.5도 일치했다.
- 단, CI의 bootstrap RNG는 기존 평가와 같은 seed 설정을 써서 CI 일치가 RNG 독립 검증은 아니다.
- 저장 위치: `results/iter_041/tests/`에 `fixtures_pg41.json`, `fixtures_pg41_eval.json`, `gen_test.json`. 결정은 `decisions/d24_worker_config.json`, 요약은 `results/iter_041/summary.json`.

# Goal Progress / Reused Assets (목표 진전·미검증 범위, 재사용 출처·검증)

**목표 진전**

- 직접 SFT B/C가 문장별 요청에서는 잘 되지만, 같은 모델을 공동 요청에 그대로 쓰면 크게 떨어진다는 것을 처음으로 확인했다.
- 이 손실은 공동 요청이 학습되지 않은 형식일 가능성이 크다(J가 문장당 box 1개로 수렴). 그래서 공동 형식을 학습한 CE 대조군이 다음에 필요하다.
- 독립 병렬 처리는 정확도를 유지하지만 J보다 처리량이 약 24% 낮고 device-seconds가 약 31~33% 더 든다. 지연(p95)에서는 불리하지 않다.

**미검증·미확인**

- V96은 checkpoint 선택에 일부 쓰인 개발 자료이고, 독립 환자·seed·다른 기관의 확인은 없다.
- 공동 형식을 학습한 대조군(공동 직접 CE)이 없어 결합 결함과 형식 미학습을 구분하지 못했다.
- MedGrounder 등 모듈형 baseline은 이번에 실행하지 않았다.
- vision/prefix caching은 측정하지 않았다. CPU/RAM/I/O 자원은 기록하지 않았다.
- device-seconds 자체의 CI는 없다(요청 wall 합 기반 proxy만 있음).
- 처리량 비율(0.756/0.760)은 기준 0.80에 가까우며 신뢰구간을 계산하지 않았다.
- iter_031의 남은 층별·오검출 비용 분석은 이번 계획 범위 밖이라 하지 않았다.

**재사용 출처·검증**

- 출처 커밋 `18fdae2e`의 다섯 파일이 blob 일치임을 확인했다.
- iter_040 protocol은 수정하지 않았다. iter_040 출력은 그 protocol과 원 코드 hash로 재검증한 뒤 썼고, 현재 영상 file/pixel hash를 추가로 확인했다.
- `pg40_run.verify_completion`은 영상 hash를 검사하지 않아 `pg41_eval.load_verified`에서 따로 확인했다.
- B/C adapter의 파일 hash와 tensor digest는 protocol 생성과 worker 로드 시 확인했다. 독립 로드 경로(trainer 방식)와 6요청(I·J_AB·J_BA 각 2건)의 token이 일치했다.
- B로 기존 V96 I-short 8요청을 새 runner로 재생성한 결과가 저장된 iter_040 출력과 token 일치했다.
- 중단·재개(SIGKILL 후 부분 행 삽입)는 D8 32요청, 2 worker에서 확인했다. 토큰이 기준과 동일했고 원본 바이트가 보존됐다.

# Problems (현재 결론 무효 / 재사용 전 수정 / 추후 개선을 구분)

- **현재 결론 무효:** 없음.
- **재사용 전 수정**
  - `pg41_gen_test.py`의 "4 worker" 검사는 `--peak-gb 10`(필요 24,576MiB > 여유 24,489MiB)이라 실제로는 launcher가 거부해서 PASS가 형식적이다. 4 worker의 실검증은 D24 stage(peak-gb 9)에서 했다.
  - 재개 검사는 D8 32요청, 2 worker 한 번뿐이라 4 worker 재개는 미검증이다.
  - 평가 GT manifest는 protocol에 hash로 잠갔지만, `pg41_eval.py` 자체는 잠그지 않고 report에 digest만 남긴다.
- **추후 개선**
  - 비용 측정을 반복(순서 교차)하고, 처리량·device-seconds의 구간 추정을 추가할 수 있다.
  - iter_031 층별·오검출 비용 분석은 미수행이다.

# Recommendation to GPT

- **계속(한정 pilot 검토):** 사전 규칙상 "방법 pilot 우선 후보"다. 다만 손실의 주된 형태가 box 개수 1로의 수렴이고 공동 형식이 학습되지 않았으므로, 후속은 공동 요청 직접 CE 대조군을 먼저 넣은 최소 pilot이어야 한다.
- **확대 주의:** 비용 이득은 device-seconds 약 1.3배, 처리량 약 1.3배로 크지 않다. 처리량 비율이 기준(0.80)에 가까워, 정확도 결과 없이 비용만으로 투자를 정당화하기는 약하다.
- **전환 조건:** 공동 직접 CE가 I와 비슷한 정확도(손실 <0.05)를 회복하면 독립 병렬 baseline을 유지하고 방법 투자는 보류한다.
- **VinDr:** 승인 통지 전이라 다운로드나 외부 평가는 하지 않았다.

SELF_CHECK: PASS
SUMMARY: C·B 직접 SFT의 공동 두 문장 grounding은 V96에서 F1@0.3이 독립 0.578→0.381/0.354(C, Δ 0.197/0.224, 97.5% CI 하한 >0.12)로 크게 하락했고, 독립 병렬 처리는 device-seconds 1.31~1.33배·처리량 0.76배라 사전 규칙상 방법 pilot 후보다. 다만 공동 형식 미학습(문장당 box 1개)과 개발 자료 한 번이라는 한계가 있고 공동 직접 CE 대조군은 미검증이다.

# [orchestrator] 권한 거부된 도구 호출
- Bash: python - <<'EOF'
import json
def rd(p): return [json.loads(l) for l in open(p)]
tr=rd('results/iter_040/data/manifest_train_private.jsonl'); ev=rd('results/iter_040/data/manifest_eval_private.jsonl'); m39=rd('results/iter_039/data/manifest_private.jsonl')
from collections import Counter
print(Counter((r['set'],r['subset']) for r in m39))
print(Counter((r.get('set'),r.get('subset'),r.get('eval_set')) for r in ev))
print(Counter((r.get('set'),r.get('subset')) for r in tr))
d24={r['PatientID'] for r in m39 if r['subset']=='D24'}
print(len(d24), len(d24&{r['PatientID'] for r in tr}), len(d24&{r['PatientID'] for r in ev}))
print(list(ev[0].keys()))
EOF
- Bash: nvidia-smi --query-gpu=index,memory.used,memory.total --format=csv; echo $CUDA_VISIBLE_DEVICES; which python; git ls-files | head -50
- Bash: sed -i 's/"--peak-gb", type=float, default=10.0/"--peak-gb", type=float, default=9.0/' run_iter041.py; grep -n "peak-gb" run_iter041.py | head -3; cut -c1-300 results/iter_041/tests/gen_test.log
- Bash: timeout 100 tail -f /dev/null; cut -c1-300 results/iter_041/tests/gen_test.log
- Bash: python - <<'PYEOF'
import json,glob,collections,os
import pg41_run as R
import pg39_spec as S
res={}
toks={}
for w in (2,4):
    d=f'results/iter_041/gen/D24_C_{w}w'
    comp=json.load(open(d+'/completion.json'))
    recs=R.verify_completion(d,'results/iter_041/requests/requests_D24_C.jsonl','results/iter_041/protocol/protocol_D24_C.json')
    toks[w]={r['request_id']:r['suffix_ids'] for r in recs}
    mx={}
    for l in open(d+'/resource_log.jsonl'):
        for g in json.loads(l)['gpu']:
            i,u,_=[x.strip() for x in g.split(',')]; mx[i]=max(mx.get(i,0),int(u))
    c=comp['cost']
    res[w]={'launcher_wall_s':comp['wall_s'],'req_per_min_incl_load':96/comp['wall_s']*60,'first_start_to_last_end_s':c['first_request_start_to_last_end_s'],
      'req_per_min_gen_only':96/c['first_request_start_to_last_end_s']*60,'devsec_generate':c['device_seconds_generate_union'],'devsec_incl_load':c['device_seconds_incl_loading_union'],
      'peak_gpu_mib':mx,'max_peak_alloc_gb_per_req':max(r['peak_mem_alloc_gb_max'] for r in recs),'max_out_tokens':max(r['n_output_tokens'] for r in recs),
      'n_retry':c['n_records_with_retry'],'sum_request_wall_s':c['sum_request_wall_s'],'n_valid_eos':sum(r['ended_eos'] for r in recs)}
    st=collections.Counter((r['cond'],S.parse_ids(r['suffix_text_raw'],r['ended_eos'],set(r['targets']))['status']) for r in recs)
    res[w]['status']={f'{k[0]}|{k[1]}':v for k,v in st.items()}
res['token_identical_2w_vs_4w']=toks[2]==toks[4]
res['n_token_mismatch']=sum(toks[2][k]!=toks[4][k] for k in toks[2])
res['speedup_wall_incl_load']=res[2]['launcher_wall_s']/res[4]['launcher_wall_s']
res['speedup_gen_only']=res[2]['first_start_to_last_end_s']/res[4]['first_start_to_last_end_s']
res['free_before_mib']={w:json.load(open(f'results/iter_041/gen/D24_C_{w}w/launch_children.json'))['free_mib_before'] for w in (2,4)}
res['note']='D24 C 96요청(I qA/qB, J-AB, J-BA). 구성 선택은 이 D 처리량·메모리·오류·token 정합성으로만 함(V96 점수 미사용).'
os.makedirs('results/iter_041/decisions',exist_ok=True)
json.dump(res,open('results/iter_041/decisions/d24_worker_config.json','x'),indent=1)
print(json.dumps(res,indent=1))
PYEOF
- Bash: python - <<'PYEOF'
import json,os
R='results/iter_041'
def src(gen,req,proto,ver): return {'gen':gen,'req':req,'proto':proto,'verifier':ver}
oldreq='results/iter_040/requests/requests_V96.jsonl'
cfg={'subset':'V96','manifest':'results/iter_040/data/manifest_eval_private.jsonl','selection_lock':'results/iter_040/data/selection_lock.json',
 'queue_order':['V96_C_JAB','V96_C_Icost','V96_C_JBA','V96_B_JAB','V96_B_JBA'],
 'models':{}}
for m in 'CB':
    d={'I':src(f'results/iter_040/gen/{m}',oldreq,f'results/iter_040/protocol/protocol_{m}.json','pg40'),
       'JAB':src(f'{R}/gen/V96_{m}_JAB',f'{R}/requests/requests_V96_JAB.jsonl',f'{R}/protocol/protocol_V96_{m}_JAB.json','pg41'),
       'JBA':src(f'{R}/gen/V96_{m}_JBA',f'{R}/requests/requests_V96_JBA.jsonl',f'{R}/protocol/protocol_V96_{m}_JBA.json','pg41')}
    if m=='C': d['Icost']=src(f'{R}/gen/V96_C_Icost',f'{R}/requests/requests_V96_Icost.jsonl',f'{R}/protocol/protocol_V96_C_Icost.json','pg41')
    cfg['models'][m]=d
os.makedirs(f'{R}/eval',exist_ok=True)
json.dump(cfg,open(f'{R}/eval/config_V96.json','x'),indent=1)
PYEOF
ls results/iter_041/eval
- Bash: git hash-object pg40_run.py pg40_verify.py pg40_gen_test.py rsna_diag/lora.py rsna_diag/queue_lock.py
