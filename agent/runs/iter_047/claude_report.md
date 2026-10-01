# 요약

- **핵심 결과:** E96 본실험은 실행하지 못했다. 계획한 층(상태 00/01/10/11 각 24명)을 채울 수 없어서 계획대로 자료 gate에서 종료했다. 정답이 "한 소견은 있고 다른 소견은 없음"인 환자(혼합 층)가 최대 34명뿐이다. 필요한 수는 D8 4명과 E96 48명을 합쳐 52명이다.
- **D8 기술 gate도 미통과:** 정답 상태를 프롬프트에 주는 oracle(O) 조건이 32건 중 29건만 맞았다. 계획은 32/32를 요구한다. 사전 규칙상 E는 이중으로 차단된다.
- **근거:** 최종 D8은 실제 MedGemma 출력 152건이고, 형식 유효율은 모든 조건 100%이다. 2/4 worker 출력은 token 단위로 일치하고, 실제 SIGKILL 후 재개도 일치했다. 변조 거부 검사는 16개 중 전부 통과했다. fixture는 57/57 통과, 독립 verifier는 62개 검사에서 불일치 0이다.
- **미검증·주의:** 교정–보존 가설, 단순 대안의 충분성, 후속 투자 판단에 대해서는 아무것도 말할 수 없다. D8의 8명 수치는 기술 검사용 기술통계다. 이 수치로 prompt를 고르지 않았다.
- **다음:** GPT가 데이터 부족에 맞춘 사전 규모 축소(예: E를 neg2 24 / 혼합 약 29 / pos2 24 명 수준)를 새 계획으로 승인할지, O 실패를 이유로 보류할지 판단한다. 구현은 끝나 있어 승인되면 바로 실행할 수 있다.

# Work Performed

- 반입된 11개 파일의 `git hash-object` 결과가 reuse_manifest의 blob과 모두 일치함을 확인했다. 새 코드는 `pg43_run`의 실행·검증 API를 그대로 쓴다.
- **자료 규칙** (`rr47_data.py`, `rr47_spec.py`)
  - pinned PadChest-GR metadata의 train에서 아홉 소견의 명시적 존재/부재 문장만 규칙으로 분류했다.
  - 시간 비교, hedge, 한정된 부정, side 한정 부정, 다중 소견 양성 문장, 영문·스페인어 불일치, 같은 영상 내 상충 annotation은 제외했다.
  - 검토자는 임상의가 아닌 자동화 에이전트다. 모델 출력을 보기 전에 허용 문장을 직접 읽고 문장 2개를 veto했다. 해당 목록은 `review_private.json`에 있다.
  - H192 환자 192명과 F120 환자 120명은 제외했고, 이 영상은 열지 않았다.
- **빌드** (`rr47_build.py`)
  - 희소 층을 먼저, finding 쌍을 번갈아 뽑는 선택 규칙을 적용했다.
  - 영상은 uint16>>8 규약으로 추출하고 file/pixel hash를 기록했다.
  - 기존 개발 집단과의 중복은 표시만 했다. 8명 중 4명은 이전 개발 집단과 겹친다.
- **요청·실행**
  - D8 요청 152건: 8명 × (R1 4, R2 4, T 4, BJ 1, BI 2, O 4).
  - `rr47_run.py`는 protocol에 코드·자료·평가 소스를 잠그고, adapter 미사용, 모델 revision, 요청 파일, 단계 이름, 요청 수를 completion 검증 때 대조한다.
  - E protocol은 E 자료 gate와 D8 gate를 모두 요구하며, 둘 중 하나라도 실패하면 생성을 거부한다.
- **평가·검증**
  - `rr47_eval.py`: r, h, h_fail, accuracy, clean/robust exact, sensitivity와 환자 단위 층화 paired bootstrap.
  - `rr47_decide.py`: 사전 투자 판단 규칙.
  - `rr47_verify.py`: production parser·점수 함수를 호출하지 않는 독립 재계산.
  - `rr47_gate.py`: D8 기술 gate.
  - `test_rr47.py`, `rr47_gen_test.py`: fixture, 실행 검사.

# Files Changed

- 반입(수정 없음): `pg43_run.py`, `pg39_data.py`, `pg39_spec.py`, `rsna_diag/{__init__,generate,geometry,metrics,parse,prompts,lora,queue_lock}.py`
- 신규:
  - `rr47_spec.py`, `rr47_data.py`, `rr47_build.py`, `rr47_run.py`
  - `rr47_eval.py`, `rr47_verify.py`, `rr47_decide.py`, `rr47_gate.py`
  - `test_rr47.py`, `rr47_gen_test.py`
- 결과: `results/iter_047/{data,requests,protocol,gen,eval,tests}/` (기존 결과는 수정하지 않았고, 이번 반복 경로에만 저장했다)

# Commands / Experiments (실제 실행한 명령과 성공/실패)

- `python rr47_build.py feasibility`: 성공.
- `python rr47_build.py build D8`: 처음에 images 디렉터리가 없어 실패했다. 디렉터리 생성을 추가해 성공.
- `python rr47_build.py build E`: exit 3. 자료 gate 미충족을 기록했다.
- D8 attempt 1 (`gen/D8_2w`, protocol v1, GPU당 worker 1개): 성공, 512초.
  - text-only 조건 T가 32건 모두 완결된 thinking block을 출력했다. 이 출력은 v1 parser에서 invalid가 된다.
- 형식 수정 1회: 완결된 thinking block 하나를 허용하고 답은 닫힘 뒤에서만 읽는다. protocol v2로 새 attempt를 만들었다. v1 결과는 보존했다.
- D8 v2 2 worker: 성공, 497초. D8 v2 4 worker (GPU당 2개): 성공, 256초.
- 중단·재개, 변조·거부 검사: 성공. fixture: `test_rr47.py` 57/57. 첫 시도 파일은 `fixtures_rr47_try1~4.json`로 남겼다.
  - try1은 내 fixture의 sens 기대값 오류와 R2 프롬프트의 "correct" 문구 때문에 2건 실패했다.
  - try2는 55/55에서 thinking parser 규칙을 추가했고, try3은 구 fixture 1건이 새 규칙과 충돌해 실패했다.
- 평가·검증: `rr47_eval.py`는 처음에 출력 디렉터리 부재로 실패했고, 잠긴 파일을 건드리지 않으려고 디렉터리를 만든 뒤 재실행했다. `rr47_verify.py`는 PASS(62검사)였고, `rr47_gate.py`는 `run=false`였다.
- `rr47_run.py protocol --stage E`: 의도대로 거부됐다.

# Results (수치와 결과 파일 경로)

**자료 가용량** (`data/feasibility.json`, `data/E_data_gate.json`)

| 항목 | 값 |
|---|---|
| 후보 환자 수 | 173명 |
| 층별 가용 환자 (정답 유형) | neg2 45, 혼합 34, pos2 102 |
| 계획이 필요한 환자 | neg2 26, 혼합 52, pos2 26 |

- 혼합 층이 18명 부족하다. 규칙을 느슨하게 해도 해결되지 않는다. 명시적 음성 문장이 있는 영상 중 아홉 소견의 양성 label을 가진 영상이 최대 51개이고, 이 상한이 52에 못 미친다.
- E gate의 상세 부족분은 `E_data_gate.json`에 있다 (선택 가능 24/5/24/24).

**D8 실행** (`gen/D8_v2_2w`, `gen/D8_v2_4w`, `gen/D8_v2_resume`)

| 구성 | wall | GPU당 peak 점유 | worker 간 token 일치 |
|---|---|---|---|
| 2 worker | 497초 | 약 8.8GiB | — |
| 4 worker | 256초 (1.94배) | 약 17.7GiB | 152/152 일치 |

- 4 worker 선택 근거: 처리량이 약 2배이고, GPU 24GiB에서 worker당 여유가 3GiB 이상이다. E를 다시 돌린다면 이 구성을 쓴다.
- worker당 peak reserved는 8.27GiB로 측정됐다.
- 재개 검사: 4 worker로 40건 기록 후 실제 SIGKILL, 같은 디렉터리에서 재실행해 152건 완료. 기준 대비 token 불일치 0 (`tests/resume_result.json`). torn-row 복구 경로는 이번에 발생하지 않아 검사하지 못했다.
- 변조·거부: 16개 전부 거부됐다 (`tests/tamper_result_v2.json`).
  - 파일 hash 검사에 걸린 8건, record 내부 검사에 걸린 7건이 따로 확인됐다. record 내부 검사는 digest, 요청 집합, adapter, prompt hash, text에 image token이 있는 경우를 모두 포함한다.
  - 동시 launcher와 완료된 디렉터리 재실행도 거부됐다.
  - 변조 전 정상 복사본은 통과해야 하는 대조군이고 합격 판정에서는 제외했다.

**D8 gate** (`eval/D8_gate.json`): 7개 검사 중 oracle만 실패했다.

| 항목 | 결과 |
|---|---|
| oracle(O) 정답 | 32건 중 29건 (3건 실패) |
| 최종 EOS 종료 | 전부 EOS |
| 조건별 형식 유효율 | 모두 100% |
| 독립 verifier | PASS |
| worker 간 일치 | token 불일치 0 |
| 재개 | token 불일치 0 |
| 변조 거부 | 전부 거부 |

- oracle 실패 3건은 모두 정답 상태가 `cardiomegaly=present`인 환자다. 모델이 프롬프트의 "Verified final status"를 따르지 않고 `absent`를 답했다. 파서·형식 오류가 아니라 지시 이행 실패다.
- 예기치 않은 관찰: text-only T는 32건 모두 thinking block(약 330 token)을 먼저 출력했다. 이것이 T의 비용을 키우고, 질문 없이 `uncertain`이 56/64로 나왔다.

**D8 기술통계** (8명, 탐색용·결정에 사용하지 않음; `eval/D8_report.json`)

| 조건 | 수정률 r | 보존 실패율 h_fail |
|---|---|---|
| R1 | 0.625 | 0.188 |
| R2 | 0.625 | 0.188 |
| BJ | 0.750 | 0.250 |
| BI | 0.812 | 0.188 |
| T | 0.0 | 0.844 |

# Goal Progress / Reused Assets (목표 진전·미검증 범위, 재사용 출처·검증)

- **목표 진전:** 교정·보존 진단을 실행할 도구는 갖췄고 작동을 확인했다. 그러나 이 진단의 연구 질문에는 새로 답한 것이 없다.
- **자료 범위의 새 사실:** PadChest-GR train에서 명시적 부정 문장과 명시적 양성이 같은 영상에 있는 혼합 환자는 많아야 약 34명이다. 현재 metadata(영상별 문장 단위)로는 계획한 균형 설계가 불가능하다.
- **재사용 검증 상태:**
  - 11개 blob이 출처와 일치한다.
  - import 완결성과 protocol CODE_FILES 의존성을 실제로 확인했다.
  - 생성·검증 경로는 D8 152건에서 실제 입력으로 검증했다.
  - 변조·wrong config·요청 중복/누락·동시 실행 거부를 확인했다.
  - 최종 verifier의 digest를 report와 연결했다 (`eval/D8_verify.json`).
- **required_checks 중 미완료**
  - 공식 notebook 대비 processor tensor의 새 입력 직접 대조는 하지 못했다. chat template은 `generate.py`의 공식 `apply_chat_template` 경로를 그대로 썼고, 모델 revision·chat template hash는 config digest로 잠겨 있다.
  - E 요청 전체(1,440건)와 E 완료 검증은 실행하지 못했다.
  - 파일 hash 검사에 걸린 변조 중 일부는 내부 검사 변형으로 보완했지만, 이미지 파일 자체를 바꾸는 변조는 실행하지 못했다.

# Problems (현재 결론 무효 / 재사용 전 수정 / 추후 개선을 구분)

- **현재 결론을 막는 것**
  - 자료 gate 미충족: 혼합 층 34 < 52.
  - D8 oracle 3/32 실패. 계획상 형식 수정 1회는 thinking parser에 이미 사용했다.
- **재사용 전 수정**
  - `rr47_eval.py` main은 출력 디렉터리를 만들지 않는다. protocol에 이 파일이 잠겨 있어 수정하지 않고 디렉터리를 먼저 만들었다. 다음 protocol에서 고친다.
  - `rr47_build.py`의 요청 ID는 `rr47_spec.VERSION`을 포함한다. 요청 파일은 v1 시기에 만들었고, 이후 VERSION이 `rr47_v2`가 됐다. 재생성하면 ID가 달라진다.
  - torn-row 복구는 이번에 발생하지 않아 새 검사가 없다.
  - 독립 verifier는 같은 bootstrap 규약(seed, 층 순서)을 공유한다. 두 구현이 같은 오류를 가질 가능성은 남는다.
- **추후 개선**
  - T가 thinking으로 길어진다. 계획의 비용 보고에 영향이 있다.
  - 혼합 층 부족 시 사전 정할 대체 규모(D8 4명 제외 후 E는 혼합 약 29~30명 이하).

# Recommendation to GPT

- E 진행 여부는 새 계획이 정하는 것이 맞다. 규모 변경은 이번 모델 출력을 본 뒤가 아니라 사전 기준으로 정해야 한다.
- 선택지는 두 가지다.
  - **(a) 보류:** 이 과제의 자료 한계(혼합 약 34명)와 oracle 지시 이행 실패(3/32)를 근거로 보류하고 다른 질문으로 전환한다.
  - **(b) 한정 보완:** 사전 규모를 줄여 새 계획을 세운다. 예: E = neg2 24 / 혼합 약 29 / pos2 24. 다만 이 경우 oracle 실패 원인, 곧 모델이 검증된 상태를 무시한 이유를 먼저 분리해야 한다.
- (b)를 택하면 구현은 준비되어 있다. 4 worker 구성에서 E 추정 시간은 다음과 같다.
  - T 요청이 thinking으로 약 21초씩 걸린다. D8의 T 32건 합계는 약 686초였다.
  - 이를 환산하면 E96 규모에서 4 worker로 약 1.5~2.5시간 (추정치이며 실측 아님).
- 이 결과는 교정–보존 trade-off, 단순 대안의 충분성, 후속 투자 판단 중 어느 것에도 증거가 되지 않는다.

SELF_CHECK: FAIL
SUMMARY: 반입 코드·parser·평가·독립 verifier·D8 실행 검증(2/4 worker 일치, SIGKILL 재개, 변조 거부 16/16)은 완료했으나, 혼합 층이 34/52로 부족해 E96 자료 gate가 미통과이고 D8 oracle이 29/32로 기술 gate도 실패해 E는 실행하지 못했다.

# [orchestrator] 권한 거부된 도구 호출
- Bash: ls results/datasets/padchest_gr results/datasets/padchest_gr/raw results/iter_043 results/iter_042 results/iter_042/data; ls results/datasets/padchest_gr/images | head -3; nvidia-smi --query-gpu=index,memory.used,memory.total --format=csv; echo $CUDA_VISIBLE_DEVICES
- Bash: git show b50aa230a86c6d5b6c6b280fe718170ce4ecf220 --stat --format=%H -- . | head -5; git ls-tree -r --name-only b50aa230a86c6d5b6c6b280fe718170ce4ecf220 | grep -E "pg4[23]|pg39"
- Bash: git ls-tree -r --name-only b50aa230a86c6d5b6c6b280fe718170ce4ecf220
- Bash: git ls-tree --name-only b50aa230a86c6d5b6c6b280fe718170ce4ecf220
- Bash: python - <<'EOF'
import pg39_data as D, json, collections, re
rep,m,l=D.load_inputs()
ev=[json.loads(x) for x in open('results/iter_040/data/manifest_eval_private.jsonl')]
print(collections.Counter(x['eval_set'] for x in ev))
tr=m[m.split=='train']
trimg=set(tr.ImageID)
neg=collections.Counter()
KW={'cardiomegaly':r'cardiomegal|cardiac (size|silhouette)|heart size|cardiothoracic|cardiac index|\bheart\b',
'pleural effusion':r'effusion','consolidation':r'consolidat','pneumothorax':r'pneumothorax','pulmonary nodule':r'nodul','atelectasis':r'atelecta','scoliosis':r'scolio','aortic elongation':r'aort','pacemaker':r'pacemaker'}
ex={k:collections.Counter() for k in KW}
for r in rep:
    if r['ImageID'] not in trimg: continue
    for f in r['findings']:
        if f.get('abnormal') is False:
            s=f['sentence_en']
            for k,p in KW.items():
                if re.search(p,s,re.I): ex[k][s]+=1
for k in ex: print(k, sum(ex[k].values()), ex[k].most_common(12))
EOF
- Bash: cat >> rr47_eval.py <<'EOF'


def main():
    import argparse
    import hashlib
    import os
    import sys
    import rr47_run
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--protocol", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    if os.path.exists(a.out):
        sys.exit(f"refuse to overwrite {a.out}")
    recs = rr47_run.verify(a.out_dir, a.stage, a.protocol)  # completion·요청 집합·hash 재검증 후에만 점수 계산
    req_path = f"results/iter_047/requests/requests_{a.stage}.jsonl"
    rows = [json.loads(l) for l in open(req_path)]
    manifest = json.load(open(f"results/iter_047/data/manifest_{a.stage}.json"))
    table, parsed = build_table(manifest, rows, recs)
    rep = summarize(table)
    rep["stage"] = a.stage
    rep["format_status_counts"] = format_counts(parsed)
    rep["answer_counts_ok_only"] = uncertain_counts(parsed)
    rep["n_valid_requests_nonoracle"] = sum(p["status"] == "ok" for pid, byc in parsed.items() for c, p in byc.items() if not c.startswith("O_"))
    rep["n_requests_nonoracle"] = sum(1 for pid, byc in parsed.items() for c in byc if not c.startswith("O_"))
    rep["n_non_eos_final"] = sum(1 for pid, byc in parsed.items() for c, p in byc.items() if not p["ended_eos"])
    rep["oracle"] = oracle_check(manifest, parsed)
    rep["per_patient_metrics"] = {pid: dict(stratum=t["stratum"], truth=t["truth"], metrics=t["metrics"]) for pid, t in table.items()}
    rep["by_truth_stratum"] = {k: {c: {m: float(np.mean([table[p]["metrics"][c][m] for p in v])) for m in METRICS} for c in CONDS}
                               for k, v in strata(table).items()}
    h = hashlib.sha256()
    for f in sorted(os.listdir(a.out_dir)):
        if f.startswith("gen_worker") and f.endswith(".jsonl"):
            h.update(open(os.path.join(a.out_dir, f), "rb").read())
    rep["source"] = dict(protocol=a.protocol, out_dir=a.out_dir, worker_files_digest=h.hexdigest(), spec=S.VERSION, boot_seed=S.BOOT_SEED, boot_b=S.BOOT_B)
    tmp = a.out + ".tmp"
    json.dump(rep, open(tmp, "w"), indent=1, default=str)
    os.replace(tmp, a.out)
    print("report written", a.out)


if __name__ == "__main__":
    main()
EOF
python -c "import rr47_eval, rr47_verify"
- Bash: CUDA_VISIBLE_DEVICES=0,1 python pg43_run.py launch --requests results/iter_047/requests/requests_D8.jsonl --protocol results/iter_047/protocol/protocol_D8_v1.json --out-dir results/iter_047/gen/D8_2w --workers 2 --peak-gb 10
- Bash: python - <<'EOF'
import json,glob,collections
recs=[]
for f in glob.glob('results/iter_047/gen/D8_2w/gen_worker*.jsonl'):
    recs+=[json.loads(l) for l in open(f)]
rq={json.loads(l)['request_id']:json.loads(l) for l in open('results/iter_047/requests/requests_D8.jsonl')}
c=collections.Counter()
for r in recs:
    c[(rq[r['request_id']]['cond'].split('_d')[0], r['ended_eos'], r['final_cap'])]+=1
print(c)
for cond in ['R1_d01','R2_d00','T_d10','BJ','BI_qA','O_d11']:
    for r in recs:
        if rq[r['request_id']]['cond']==cond:
            print(cond, repr(r['suffix_text_raw'][:200]), r['n_output_tokens'], round(r['wall_s'],2)); break
c=json.load(open('results/iter_047/gen/D8_2w/completion.json'))['cost']; print(c)
import statistics
print(statistics.mean(r['wall_s'] for r in recs), max(r['peak_mem_reserved_gb_max'] for r in recs))
EOF
- Bash: python - <<'EOF'
import json
d=json.load(open('results/iter_047/eval/D8_report.json'))
print(d['format_status_counts']); print(d['answer_counts_ok_only']); print(d['oracle']['n'], d['oracle']['ok'], d['n_non_eos_final'], d['n_valid_requests_nonoracle'], d['n_requests_nonoracle'])
for c,m in d['conds'].items(): print(c, {k:round(v['mean'],3) for k,v in m.items()})
print(d['strata_sizes'] if 'strata_sizes' in d else d['strata_sizes'])
EOF
