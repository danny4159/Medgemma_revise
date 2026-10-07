"""iter_095 D8 기술 검사: 4 worker vs 2 worker 정합성·처리량·peak, 기존 Locate and describe와의 token/입력 회귀, EOS, Describe의 좌표 출력 여부.
결과: results/iter_095/tests/d8_check.json (새 파일). 오답 여부는 보지 않는다."""
import json
import re

import report95_common as C
from report95_common import R95, save, read_jsonl_complete, sha


def load(root):
    d = {}
    for s in sorted(root.glob('shard*')):
        c = json.loads((s / 'completion.json').read_text())
        assert c['files']['outputs.jsonl'] == sha(s / 'outputs.jsonl')
        for r in read_jsonl_complete(s / 'outputs.jsonl'):
            assert r['id'] not in d
            d[r['id']] = r
    return d


def resource_peak(launch_glob):
    mx = {}
    for f in launch_glob:
        for l in (f / 'resource.jsonl').read_text().splitlines():
            for g, (u, t) in json.loads(l)['smi'].items():
                mx[g] = max(mx.get(g, 0), u)
    return mx


def main():
    reqs = {r['id']: r for r in C.requests('D8')}
    w4, w2 = load(R95 / 'D8/w4'), load(R95 / 'D8/w2')
    old = C.old_C_records('D8')
    res = {'n_expected': len(reqs), 'w4_ids_ok': set(w4) == set(reqs), 'w2_ids_ok': set(w2) == set(reqs)}
    res['w4_vs_w2_token_mismatch'] = [i for i in reqs if w4[i]['attempts'][-1]['suffix_ids'] != w2[i]['attempts'][-1]['suffix_ids']
                                      or w4[i]['input_ids'] != w2[i]['input_ids'] or w4[i]['pixel_sha256'] != w2[i]['pixel_sha256']]
    reg = []
    for i, q in reqs.items():
        if q['fmt'] != 'L':
            continue
        o = old[(q['ImageID'], q['region'])]
        r = w4[i]
        reg.append({'id': i, 'tokens_equal': r['attempts'][-1]['suffix_ids'] == o['attempts'][-1]['suffix_ids'],
                    'input_ids_equal': r['input_ids'] == o['input_ids'], 'pixel_equal': r['pixel_sha256'] == o['pixel_sha256'],
                    'text_equal': r['text'] == o['text']})
    res['regress_LD_vs_old'] = {'n': len(reg), 'n_all_equal': sum(x['tokens_equal'] and x['input_ids_equal'] and x['pixel_equal'] for x in reg), 'items': reg}
    dl = []
    for i, q in reqs.items():
        if q['fmt'] != 'D':
            continue
        l = w4[i.replace('|D|', '|L|')]
        d = w4[i]
        dl.append({'pixel_equal': d['pixel_sha256'] == l['pixel_sha256'], 'prompt_differs_only': d['input_ids'] != l['input_ids'],
                   'len_diff': len(d['input_ids']) - len(l['input_ids'])})
    res['D_vs_L_same_image_diff_prompt'] = {'n': len(dl), 'pixel_equal_all': all(x['pixel_equal'] for x in dl),
                                            'input_differs_all': all(x['prompt_differs_only'] for x in dl)}
    res['eos'] = {'w4_final_not_eos': sum(not r['attempts'][-1]['ended_eos'] for r in w4.values()),
                  'w2_final_not_eos': sum(not r['attempts'][-1]['ended_eos'] for r in w2.values()),
                  'max_attempts': max(len(r['attempts']) for r in list(w4.values()) + list(w2.values()))}
    res['describe_has_bbox_coordinates'] = sum(bool(re.search(r'\[\s*0?\.\d+\s*,', r['text'])) for r in w4.values() if r['fmt'] == 'D')
    res['describe_prefix_ok'] = all(r['text'].startswith(f"Description of the {r['region']}:") for r in w4.values() if r['fmt'] == 'D')
    for tag in ('w4', 'w2'):
        ld = sorted((R95 / 'launches').glob(f'd8_{tag}_*'))
        assert len(ld) == 1
        lr = json.loads((ld[0] / 'launch_result.json').read_text())
        gen_s = sum(json.loads(c['executions'] if False else '0') for c in []) if False else None
        ev = [json.loads(l) for s in (R95 / f'D8/{tag}').glob('shard*') for l in (s / 'executions.jsonl').read_text().splitlines()]
        starts = [e for e in ev if e['event'] == 'start' and 'loading_s' in e]
        ends = [e for e in ev if e['event'] == 'end']
        saves = [e for e in ev if e['event'] == 'request_saved']
        t_first = min(e['time'] for e in ev if e['event'] == 'request_start')
        t_last = max(e['time'] for e in saves)
        res[tag] = {'launch_wall_s': lr['wall_s'], 'rcs': lr['returncodes'], 'generation_window_s': t_last - t_first,
                    'n_requests': len(saves), 'req_per_min_generation_window': len(saves) / (t_last - t_first) * 60,
                    'req_per_min_launch_wall': len(saves) / lr['wall_s'] * 60,
                    'max_peak_reserved_gib': max(e['peak_reserved_gib_max'] for e in ends), 'loading_s': [round(e['loading_s'], 1) for e in starts],
                    'smi_max_used_mib_per_gpu': resource_peak(ld), 'admission': lr['admission'],
                    'tokens_total': sum(e['n_new'] for e in saves), 'seconds_p95': sorted(e['seconds'] for e in saves)[int(.95 * (len(saves) - 1))]}
    res['all_pass'] = (res['w4_ids_ok'] and res['w2_ids_ok'] and not res['w4_vs_w2_token_mismatch']
                       and res['regress_LD_vs_old']['n_all_equal'] == res['regress_LD_vs_old']['n']
                       and res['eos']['w4_final_not_eos'] == 0 and res['eos']['w2_final_not_eos'] == 0 and res['describe_prefix_ok']
                       and res['D_vs_L_same_image_diff_prompt']['pixel_equal_all'])
    save(R95 / 'tests/d8_check.json', res)
    print(json.dumps({k: v for k, v in res.items() if k not in ('regress_LD_vs_old',)}, indent=1)[:4000])
    print(res['regress_LD_vs_old']['n_all_equal'], '/', res['regress_LD_vs_old']['n'])


if __name__ == '__main__':
    main()
