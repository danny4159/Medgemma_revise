"""stage 산출물 병합·완전성 검사·C-H hybrid 조립. 원본(계승 파일)은 읽기만 하고 병합본은 새 파일로 쓴다.

python report86_merge.py <stage>
- 예상 요청 ID 전체(환자 x 36)가 정확히 한 번씩 있는지, 모든 행의 protocol_digest가 현재 과학적 protocol과 같은지(계승 행은
  manifest 검증), record_digest, 최종 EOS 여부를 확인한다. 위반이 있으면 병합본을 쓰지 않고 종료한다(exit 2).
- 8조건 판독 산출물 results/iter_086/<stage>/readings.jsonl: 환자 x 조건 {text, segments, source}.
  C-H = 공식 README의 hybrid('Concatenate AGRG outputs with the GRG output'): 29개 영역 출력을 고정(sorted) 순서로 잇고
  GRG 출력을 뒤에 붙인다. 문장 제거·요약은 하지 않는다.
"""
import json
import sys

from report86_common import (R86, STAGES, SYSTEMS, sha, sha_obj, save, read_jsonl_complete, record_digest,
                             scientific_protocol, expected_ids, prompts_for)


def collect(stage, system):
    """returns {id: (record, source)}, problems"""
    d = R86 / stage / system
    rows = json.loads(STAGES[stage]['inputs'].read_text())
    sci = scientific_protocol(system, stage)
    dig = sha_obj(sci)
    got, problems = {}, []
    if stage == 'D8':
        from report86_inherit import load_verified
        inh, _ = load_verified(system)
        for k, r in inh.items():
            got[k] = (r, 'inherited:iter_085')
    for sd in sorted(d.glob('shard*')) if d.exists() else []:
        for r in read_jsonl_complete(sd / 'outputs.jsonl'):
            if r['id'] in got:
                problems.append(f"duplicate {r['id']} ({sd.name} vs {got[r['id']][1]})")
                continue
            if r['protocol_digest'] != dig:
                problems.append(f"protocol digest mismatch {r['id']}")
            if r['record_digest'] != record_digest(r):
                problems.append(f"record digest mismatch {r['id']}")
            got[r['id']] = (r, f'iter_086:{stage}/{system}/{sd.name}')
    exp = expected_ids(rows, system)
    if set(got) != exp:
        problems.append(f'id set mismatch: missing {len(exp - set(got))}, extra {len(set(got) - exp)}')
    img = {r['ImageID']: r['file_sha256'] for r in rows}
    for k, (r, s) in got.items():
        if r.get('image_sha256') != img.get(r['ImageID']):
            problems.append(f'image sha mismatch {k}')
    return got, problems, rows


def main():
    stage = sys.argv[1]
    allrec, allprob = {}, []
    for s in SYSTEMS:
        got, prob, rows = collect(stage, s)
        allrec[s] = got
        allprob += [f'{s}: {p}' for p in prob]
    nonEOS = [k for s in SYSTEMS for k, (r, _) in allrec[s].items() if not r['attempts'][-1]['ended_eos']]
    if allprob:
        print(json.dumps({'problems': allprob[:20], 'n_problems': len(allprob)}, indent=1))
        sys.exit(2)
    out = []
    locs = [n for n, _ in prompts_for('C') if n != 'G']
    for row in rows:
        img = row['ImageID']
        def txt(system, name):
            r, src = allrec[system][f'{img}|{system}|{name}']
            return r['text'].strip(), src, r
        for cond, (system, name) in {'M15-R': ('M15', 'R'), 'M15-S': ('M15', 'S'), 'B0-R': ('B0', 'R'), 'B0-S': ('B0', 'S'),
                                     'M1-R': ('M1', 'R'), 'M1-G': ('M1G', 'G'), 'C-G': ('C', 'G')}.items():
            t, src, r = txt(system, name)
            out.append({'ImageID': img, 'condition': cond, 'text': t, 'segments': [{'source': f'{system}|{name}', 'text': t}], 'request_ids': [r['id']],
                        'record_sources': [src], 'final_eos': [r['attempts'][-1]['ended_eos']],
                        'n_tokens': r['attempts'][-1]['n_new'], 'n_attempts': len(r['attempts'])})
        segs, rids, srcs, eos, ntok, natt = [], [], [], [], 0, 0
        for loc in locs:
            t, src, r = txt('C', loc)
            segs.append({'source': f'C|{loc}', 'text': t}); rids.append(r['id']); srcs.append(src)
            eos.append(r['attempts'][-1]['ended_eos']); ntok += r['attempts'][-1]['n_new']; natt += len(r['attempts'])
        t, src, r = txt('C', 'G')
        segs.append({'source': 'C|G', 'text': t}); rids.append(r['id']); srcs.append(src)
        eos.append(r['attempts'][-1]['ended_eos']); ntok += r['attempts'][-1]['n_new']; natt += len(r['attempts'])
        out.append({'ImageID': img, 'condition': 'C-H', 'text': '\n'.join(s['text'] for s in segs), 'segments': segs, 'request_ids': rids,
                    'record_sources': srcs, 'final_eos': eos, 'n_tokens': ntok, 'n_attempts': natt})
    assert len(out) == 8 * len(rows) and len({(o['ImageID'], o['condition']) for o in out}) == len(out)
    p = R86 / stage / 'readings.jsonl'
    with p.open('x') as f:
        for o in out:
            f.write(json.dumps(o, ensure_ascii=False) + '\n')
    summary = {'stage': stage, 'n_patients': len(rows), 'n_readings': len(out), 'n_requests': sum(len(v) for v in allrec.values()),
               'n_final_non_eos_requests': len(nonEOS), 'non_eos_ids': nonEOS, 'readings_sha256': sha(p),
               'inputs_sha256': sha(STAGES[stage]['inputs']),
               'inherited': sum(1 for s in SYSTEMS for k, (r, src) in allrec[s].items() if src.startswith('inherited')),
               'hybrid_rule': 'region outputs (sorted official location order) concatenated, then GRG output; no deletion or summarization',
               'retried_requests': sum(1 for s in SYSTEMS for k, (r, _) in allrec[s].items() if len(r['attempts']) > 1)}
    save(R86 / stage / 'merge_summary.json', summary)
    print(json.dumps(summary, indent=1))


if __name__ == '__main__':
    main()
