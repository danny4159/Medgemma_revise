"""iter_076 비용 보고: results/iter_076/cost/{F,R,C,H}_block{1..4}.json (+blocks_ledger.json)에서 paired block 비율을 계산한다.

- 전체 시간 = 원 T2 읽기부터 답변 저장까지 + 모델/RF 적재 포함(wall_incl_load_s) / 적재 제외(process_s)를 모두 보고. VLM best는 eval report의 held primary가 더 좋은 적응 VLM.
- 원 계획 음성 투자 판단의 비용 조건: 네 block 모두 (C 전체 시간 / best VLM 전체 시간) <= 0.5 (적재 포함 기준을 정식 flag로, 제외 기준은 보조).
- 정합성: 같은 시스템의 block 간 답변 동일 여부, F/R 답변이 V8 생성 출력(같은 adapter)과 일치하는지.
- GPU device-seconds: F/R/C는 GPU 1장 점유(wall x 1), H는 CPU 작업(GPU 0)으로 표기. GT anatomy(mask) 획득 비용은 미측정 oracle 비용.
결과: results/iter_076/cost/cost_report.json (존재하면 중단).
"""
import glob, json, os, sys

import numpy as np

OUT = 'results/iter_076'
COST = f'{OUT}/cost'


def main():
    dst = f'{COST}/cost_report.json'
    if os.path.exists(dst):
        sys.exit('exists')
    blk = {s: {} for s in 'FRCH'}
    for f in sorted(glob.glob(f'{COST}/*_block*.json')):
        d = json.load(open(f))
        if 'system' in d:
            blk[d['system']][d['block']] = d
    nb = sorted(set(blk['F']) & set(blk['R']) & set(blk['C']) & set(blk['H']))
    if len(nb) != 4:
        sys.exit(f'need 4 complete blocks, have {nb}')
    ledger = json.load(open(f'{COST}/blocks_ledger.json'))
    if any(x['rc'] != 0 for x in ledger):
        sys.exit('a cost worker failed')
    rep = json.load(open(f'{OUT}/eval/report.json'))
    held = {n: rep['systems'][n]['held']['class_std_mae'] for n in ('F_adapted', 'R_adapted')}
    best = min(held, key=lambda n: (held[n], n))
    bv = best[0]
    res = {'best_vlm': best, 'held_primary': held, 'blocks': {}, 'n_requests': {s: blk[s][nb[0]]['n_requests'] for s in 'FRCH'}}
    for b in nb:
        r = {}
        for s in 'FRCH':
            d = blk[s][b]
            r[s] = {'wall_incl_load_s': d['wall_incl_load_s'], 'process_s': d['process_s'], 'load_s': d['load_s'], 'per_request_s_mean': d['per_request_s_mean'],
                    'gpu_device_seconds_incl_load': d['wall_incl_load_s'] if s != 'H' else 0.0, 'gpu_device_seconds_excl_load': d['process_s'] if s != 'H' else 0.0}
        for s in 'CH':
            r[f'{s}_over_bestVLM_incl_load'] = r[s]['wall_incl_load_s'] / r[bv]['wall_incl_load_s']
            r[f'{s}_over_bestVLM_excl_load'] = r[s]['process_s'] / r[bv]['process_s']
        res['blocks'][str(b)] = r
    res['flags'] = {'C_le_half_of_bestVLM_all4_blocks_incl_load': all(res['blocks'][str(b)]['C_over_bestVLM_incl_load'] <= 0.5 for b in nb),
                    'C_le_half_of_bestVLM_all4_blocks_excl_load': all(res['blocks'][str(b)]['C_over_bestVLM_excl_load'] <= 0.5 for b in nb),
                    'H_le_half_of_bestVLM_all4_blocks_incl_load': all(res['blocks'][str(b)]['H_over_bestVLM_incl_load'] <= 0.5 for b in nb),
                    'H_le_half_of_bestVLM_all4_blocks_excl_load': all(res['blocks'][str(b)]['H_over_bestVLM_excl_load'] <= 0.5 for b in nb)}
    res['ratio_ranges'] = {k: [min(res['blocks'][str(b)][k] for b in nb), max(res['blocks'][str(b)][k] for b in nb)] for k in
                           ('C_over_bestVLM_incl_load', 'C_over_bestVLM_excl_load', 'H_over_bestVLM_incl_load', 'H_over_bestVLM_excl_load')}
    # 정합성
    res['answers_identical_across_blocks'] = {s: all(blk[s][b]['answers'] == blk[s][nb[0]]['answers'] for b in nb) for s in 'FRCH'}
    sel = json.load(open(f'{OUT}/select_final.json'))['final']
    agree = {}
    for v in 'FR':
        gdir = f"{OUT}/gen/V8/{v}_lr{sel[v]['lr']}_ep{sel[v]['epoch']:02d}"
        recs = {}
        for f in glob.glob(f'{gdir}/gen_worker*.jsonl'):
            for ln in open(f):
                if ln.strip():
                    x = json.loads(ln)
                    recs[x['id']] = x['parsed']
        ans = blk[v][nb[0]]['answers']
        agree[v] = {'n': len(ans), 'n_equal_to_v8_generation_same_adapter': sum(1 for k, a in ans.items() if recs.get(k) == a)}
    res['f_r_answers_vs_v8_generation'] = agree
    res['notes'] = ['GT anatomy(mask) 획득 비용은 모든 시스템에서 미측정(oracle 영역 사용)', 'H는 원 volume의 image+mask read, PyRadiomics, RF predict를 포함하며 RF 학습/적재는 load로 분리',
                    'GPU device-seconds는 점유 GPU 1장 x wall 기준이며 H는 CPU 작업']
    tmp = dst + '.tmp'
    json.dump(res, open(tmp, 'w'), indent=1)
    os.replace(tmp, dst)
    print(json.dumps({'flags': res['flags'], 'ratio_ranges': res['ratio_ranges'], 'agree': agree, 'identical': res['answers_identical_across_blocks']}, indent=1))


if __name__ == '__main__':
    main()
