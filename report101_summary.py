"""iter_101 비용·자료·형식 요약(기존 산출물만 읽는다, 새 모델 호출 없음). 결과: results/iter_101/eval/summary.json"""
import json
from collections import Counter, defaultdict
from pathlib import Path

from report86_common import ROOT, save, sha, read_jsonl_complete

R = ROOT / 'results/iter_101'


def launch_cost(d):
    j = json.loads(next(iter(sorted(Path(d).glob('launch_*.json')))).read_text())
    rs = [json.loads(x) for x in open(next(iter(sorted(Path(d).glob('launch*_resource.jsonl')))))]
    return {'wall_s': j['wall_s'], 'mapping': j['mapping'],
            'peak_mib_by_gpu': {g: max(r['smi'][g][1] for r in rs) for g in rs[0]['smi']}, 'n_resource_samples': len(rs)}


def main():
    out = {}
    en = json.loads((R / 'data/enumeration.json').read_text())
    sel = json.loads((R / 'data/lock/selection.json').read_text())
    ref = json.loads((R / 'data/reference_private.json').read_text())
    rows = json.loads((R / 'data/inputs_S24.json').read_text())
    exp = Counter()
    for r in rows:
        files = ref[r['ImageID']]['earlier_use_files'] or []
        exp['any_earlier_result_file'] += bool(files)
        exp['iter_040_train_T305_manifest'] += any('iter_040/data/manifest_train_private' in f for f in files)
        exp['iter_042_effusion_dev'] += any('iter_042' in f for f in files)
        exp['none'] += not files
    out['data'] = {'n_train_images': en['n_train_images'], 'images_with_status': dict(en['n_images_with_status']), 'patients_by_status': en['n_patients_by_status'],
                   'exclusions': en['exclusions'], 'S24_earlier_use_file_counts': dict(exp), 'selection': {k: sel[k] for k in ('n_conflict_C', 'M', 'POS_conflicts', 'NEG_conflicts', 'ambiguous_patients')}}
    cure = {}
    for name, d in (('D4_w2', R / 'cure/D4_w2'), ('S24', R / 'cure/S24')):
        recs, load, gen = [], [], 0
        for s in range(2):
            recs += read_jsonl_complete(d / f'shard{s}/outputs.jsonl')
            ev = [json.loads(x) for x in (d / f'shard{s}/executions.jsonl').read_text().splitlines() if x]
            load += [e['loading_s'] for e in ev if 'loading_s' in e]
        gen = sum(sum(a['runtime_s'] for a in r['attempts']) for r in recs)
        cure[name] = {'n_requests': len(recs), 'generation_s_total': gen, 'loading_s_per_worker': load, 'final_not_eos': sum(not r['attempts'][-1]['ended_eos'] for r in recs),
                      'n_attempts_gt1': sum(len(r['attempts']) > 1 for r in recs), 'launch': launch_cost(d), 'requests_per_min_wall': len(recs) / launch_cost(d)['wall_s'] * 60}
    out['cure'] = cure
    corr = {}
    for name, d, w in (('D4_w2', R / 'gen/D4_w2', 2), ('D4_w4', R / 'gen/D4_w4', 4), ('main_w4', R / 'gen/main', 4)):
        recs = []
        for s in range(w):
            recs += read_jsonl_complete(d / f'worker_{s}.jsonl')
        bycond = defaultdict(list)
        for r in recs:
            bycond[r['id'].rsplit('|', 1)[1]].append(r)
        corr[name] = {'n_requests': len(recs), 'launch': launch_cost(d), 'requests_per_min_wall': len(recs) / launch_cost(d)['wall_s'] * 60,
                      'generation_s_total': sum(sum(a['runtime_s'] for a in r['attempts']) for r in recs),
                      'by_condition': {c: {'n': len(v), 'final_not_eos': sum(not r['attempts'][-1]['ended_eos'] for r in v), 'n_attempts_gt1': sum(len(r['attempts']) > 1 for r in v),
                                           'generation_s': sum(sum(a['runtime_s'] for a in r['attempts']) for r in v),
                                           'median_tokens_final': sorted(r['attempts'][-1]['n_new'] for r in v)[len(v) // 2],
                                           'input_tokens_median': sorted(len(r['input_ids']) for r in v)[len(v) // 2]} for c, v in sorted(bycond.items())}}
    out['correction'] = corr
    # D4 2 vs 4 worker 정합성
    def toks(d, w):
        t = {}
        for s in range(w):
            for r in read_jsonl_complete(R / f'gen/{d}/worker_{s}.jsonl'):
                t[r['id']] = [a['suffix_ids'] for a in r['attempts']]
        return t
    a, b = toks('D4_w2', 2), toks('D4_w4', 4)
    out['D4_w2_vs_w4'] = {'n': len(a), 'tokens_equal_all': a == b, 'wall_ratio_w2_over_w4': corr['D4_w2']['launch']['wall_s'] / corr['D4_w4']['launch']['wall_s']}
    # 형식 요약(판정표 기준)
    mp = json.loads((R / 'eval/blind/private_mapping.json').read_text())
    jd = json.loads((R / 'eval/judgments.json').read_text())
    fmt = defaultdict(Counter)
    for b_, m in mp.items():
        fmt[m['condition']][jd[b_]['format']] += 1
    out['format_by_condition'] = {c: dict(v) for c, v in sorted(fmt.items())}
    out['unmeasured'] = ['semantic review time (assistant)', 'data enumeration/visual audit time', 'GPU-hours beyond launcher wall clocks']
    save(R / 'eval/summary.json', out)
    print(json.dumps({'cure_S24_wall': cure['S24']['launch']['wall_s'], 'cure_D4_wall': cure['D4_w2']['launch']['wall_s'],
                      'corr_walls': {k: v['launch']['wall_s'] for k, v in corr.items()}, 'D4_w2_vs_w4': out['D4_w2_vs_w4'], 'format': out['format_by_condition']}, indent=1))


if __name__ == '__main__':
    main()
