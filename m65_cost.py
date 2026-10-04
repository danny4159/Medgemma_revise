"""iter_065 D6 비용: 기존 순서의 2 case씩 3 block. block 워크로드 = 2 case x 6 구간 x 2 질문 = 24 답변.
VLM 정책 비용(loading 제외) = 해당 block 요청들의 read->saved(원본 PNG 읽기·processor·생성·저장 fsync) 합. loading 포함 = + 모델 load_s(attempt 파일 평균, block마다 1회).
HD 비용 = m65_hd.py summary의 pipeline_start->pipeline_end(원본 NIfTI 읽기~답변 저장), loading 포함은 proc_start->pipeline_end, 제외는 load_model 구간을 뺀 값.
주의: VLM 요청은 block별 독립 프로세스가 아니라 D 생성 중 연속 측정값이다(두 GPU 동시 실행, 서로 다른 GPU). HD block은 단독 프로세스.
사용: python m65_cost.py OUT.json"""
import glob, json, os, sys
import numpy as np

R = 'results/iter_065'
CASES = ['BRATS_053', 'BRATS_199', 'BRATS_368', 'BRATS_380', 'BRATS_037', 'BRATS_455']
POL = {'F/F': ('F', 'F'), 'F/T': ('F', 'T'), 'T/F': ('T', 'F'), 'T/T': ('T', 'T'), 'J/J': ('J', 'J')}


def vlm(model):
    gd = f'{R}/gen/D_{model}'
    cost, lab = {}, json.load(open(f'{R}/data/labels_D.json'))
    for f in glob.glob(f'{gd}/worker*.cost'):
        for l in open(f):
            r = json.loads(l); cost[r['rid']] = r['read_to_saved_s']
    loads = [json.load(open(f))['load_s'] for f in glob.glob(f'{gd}/worker*.attempt_*.json')]
    out = {'load_s_mean': float(np.mean(loads))}
    for p, (cw, ce) in POL.items():
        blocks = []
        for b in range(3):
            cs = CASES[2 * b:2 * b + 2]
            t = sum(v for rid, v in cost.items() if lab[rid]['case'] in cs and ((lab[rid]['q'] == 'W' and lab[rid]['cond'] == cw) or (lab[rid]['q'] == 'E' and lab[rid]['cond'] == ce)))
            blocks.append(t)
        out[p] = {'excl_load_s': blocks, 'incl_load_s': [x + out['load_s_mean'] for x in blocks]}
    return out


def hd():
    res = []
    for d in (f'{R}/hd/D_b0_a1', f'{R}/hd/D_b1_a0', f'{R}/hd/D_b2_a0'):
        s = json.load(open(f'{d}/summary.json'))
        ev = {e['event']: e for e in s['events']}
        t_ps = [e for e in s['events'] if e['event'] == 'proc_start'][0]['t_proc_start']
        t0, t1 = ev['pipeline_start']['t'], [e for e in s['events'] if e['event'] == 'pipeline_end'][0]['t']
        ld = ev['load_model_end']['t'] - ev['load_model_start']['t']
        res.append({'incl_load_s': t1 - t_ps, 'pipeline_s': t1 - t0, 'excl_load_s': t1 - t0 - ld, 'load_model_s': ld})
    return res


def main(out):
    assert not os.path.exists(out)
    h = hd()
    rep = {'HD_blocks': h, 'HD_mean_incl_load_s': float(np.mean([x['incl_load_s'] for x in h])),
           'HD_mean_excl_load_s': float(np.mean([x['excl_load_s'] for x in h]))}
    for m in ('medgemma', 'qwen'):
        v = vlm(m)
        rep[m] = v
        for p in ('F/T', 'F/F', 'J/J'):
            for k in ('excl_load_s', 'incl_load_s'):
                v[p][k + '_mean'] = float(np.mean(v[p][k]))
        rep[m]['ratio_Q_FT_over_J'] = {k: v['F/T'][k + '_mean'] / v['J/J'][k + '_mean'] for k in ('excl_load_s', 'incl_load_s')}
        rep[m]['ratio_Q_FT_over_HD'] = {'excl_load_s': v['F/T']['excl_load_s_mean'] / rep['HD_mean_excl_load_s'],
                                        'incl_load_s': v['F/T']['incl_load_s_mean'] / rep['HD_mean_incl_load_s']}
    json.dump(rep, open(out, 'w'), indent=1)
    print(json.dumps({k: rep[k] for k in rep if k.startswith('HD_')}), {m: rep[m]['ratio_Q_FT_over_J'] for m in ('medgemma', 'qwen')},
          {m: rep[m]['ratio_Q_FT_over_HD'] for m in ('medgemma', 'qwen')})


if __name__ == '__main__':
    main(sys.argv[1])
