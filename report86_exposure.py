"""CURE 학습 노출 신호 점검(CPU): C-G(공식 GRG) 출력 문장이 reference 문장과 글자 그대로 일치하는 비율.
원문 일치는 암기·학습 노출의 징후일 뿐 증명이 아니다. D8(PadChest-GR train split)과 E(validation split)를 비교한다.
python report86_exposure.py <out.json>
"""
import glob
import json
import re
import sys

from report86_common import R86, R85, STAGES, save, read_jsonl_complete
import report86_facts as F

BBOX = re.compile(r"\s*\[\s*-?[\d.]+\s*,\s*-?[\d.]+\s*,\s*-?[\d.]+\s*,\s*-?[\d.]+\s*\]")


def norm(s):
    return re.sub(r'[^a-z0-9 ]', '', s.lower()).strip()


def sentences(t):
    t = BBOX.sub('. ', t)
    return [norm(x) for x in re.split(r'(?<=[.])\s+|\.\s*$', t) if norm(x)]


def stage_stats(stage):
    rows = json.loads(STAGES[stage]['inputs'].read_text())
    if stage == 'D8':
        refs = {r['ImageID']: r['findings'] for r in json.loads((R85 / 'D8/reference_private.json').read_text())}
        recs = {}
        from report86_inherit import load_verified
        recs.update({k: v for k, v in load_verified('C')[0].items() if k.endswith('|G')})
        for p in glob.glob(str(R86 / 'D8/C/shard*/outputs.jsonl')):
            recs.update({r['id']: r for r in read_jsonl_complete(p) if r['id'].endswith('|G')})
    else:
        refs = {k: v['findings_raw'] for k, v in json.loads((R86 / 'E/reference_facts_E_private.json').read_text()).items()}
        recs = {}
        for p in glob.glob(str(R86 / stage / 'C/shard*/outputs.jsonl')):
            recs.update({r['id']: r for r in read_jsonl_complete(p) if r['id'].endswith('|G')})
    per = []
    for row in rows:
        k = row['ImageID'] + '|C|G'
        if k not in recs:
            continue
        out_s = sentences(recs[k]['text'])
        ref_abn = [norm(f['sentence_en']) for f in refs[row['ImageID']] if f.get('abnormal')]
        ref_all = [norm(f['sentence_en']) for f in refs[row['ImageID']]]
        hit_abn = sum(any(r == o for o in out_s) for r in ref_abn)
        hit_all = sum(any(r == o for o in out_s) for r in ref_all)
        match_out = sum(o in ref_all for o in out_s)
        per.append({'ImageID': row['ImageID'], 'stratum': row.get('stratum', 'D8'), 'n_ref_abn': len(ref_abn), 'abn_exact': hit_abn,
                    'n_ref_all': len(ref_all), 'all_exact': hit_all, 'n_out_sent': len(out_s), 'out_exact_in_ref': match_out})
    return per


def summarize(per):
    out = {}
    for name, sub in [('all', per)] + [(s, [p for p in per if p['stratum'] == s]) for s in sorted({p['stratum'] for p in per})]:
        if not sub:
            continue
        ra = sum(p['n_ref_abn'] for p in sub)
        out[name] = {'n_patients': len(sub), 'ref_abnormal_sentences': ra, 'ref_abnormal_exact_reproduced': sum(p['abn_exact'] for p in sub),
                     'frac_ref_abnormal_exact': sum(p['abn_exact'] for p in sub) / ra if ra else None,
                     'out_sentences': sum(p['n_out_sent'] for p in sub), 'out_sentences_exact_in_ref': sum(p['out_exact_in_ref'] for p in sub),
                     'frac_out_exact_in_ref': sum(p['out_exact_in_ref'] for p in sub) / max(1, sum(p['n_out_sent'] for p in sub))}
    return out


if __name__ == '__main__':
    res = {}
    for stage in ('D8', 'E96'):
        per = stage_stats(stage)
        res[stage] = {'summary': summarize(per), 'per_patient': per}
    save(sys.argv[1], res)
    print(json.dumps({s: v['summary'] for s, v in res.items()}, indent=1))
