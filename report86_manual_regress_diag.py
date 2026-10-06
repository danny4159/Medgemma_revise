"""수동 token 회귀에서 달라진 행의 최초 차이 위치와 원 환경 기록을 비교한다(CPU, 읽기 전용). 결과: manual_regress/diff_diagnosis.json"""
import json

from report86_common import ROOT, R86, save

MAN = ROOT / 'results/manual_rsna_report_transfer_20261006'
OUT = R86 / 'manual_regress'


def main():
    res = {}
    for m in ('base', 'sft'):
        orig = {r['id']: r for r in map(json.loads, (MAN / f'{m}.jsonl').read_text().splitlines())}
        new = json.loads((OUT / f'{m}_result.json').read_text())
        cfg = json.loads((MAN / f'{m}_config.json').read_text())
        env = cfg.get('env', {})
        res[m] = {'orig_env': {k: env.get(k) for k in env if k in ('torch', 'transformers', 'cuda', 'gpu', 'device', 'dtype', 'attn', 'torch_version', 'transformers_version')} or str(env)[:400],
                  'new_torch': new['torch'], 'diffs': []}
        for it in new['items']:
            if not it['tokens_equal']:
                o = orig[it['id']]['suffix_ids']
                res[m]['diffs'].append({'id': it['id'], 'n_old': it['n_new_old'], 'n_new': it['n_new_new']})
    save(OUT / 'diff_diagnosis_env.json', res)
    print(json.dumps(res, indent=1)[:3000])


if __name__ == '__main__':
    main()
