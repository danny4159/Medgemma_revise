"""기존 검증 자산의 관련 범위만 읽고 A/T/X 요청과 별도 평가 GT를 고정한다."""
import json
import subprocess
from pathlib import Path
import numpy as np
import a81_common as C
import rf78_vlm as R
import sp75_vlm as V
import sp75_gen as G


def prepare():
    assert C.sha('../agent/runs/iter_080/plan.md') == 'a5f5ad6689d7d9d19dddaa265c1e5bcb47d8b5d57f3e409fbcf0c7cc5293d4d3'
    old = C.read('../agent/runs/iter_080/reuse_manifest.json')
    # 수정 전 반입 상태는 git HEAD의 blob으로 확인한다.
    origin = 'b5426526827d986e9962f5439d5191bfbd064634'
    blobs = {}
    for p in ['rf78_gen.py', 'rf78_vlm.py', 'rf78_launch.py', 'sp75_gen.py', 'sp75_vlm.py', 'sp75_metrics.py',
              'sp75_data.py', 'g71_data.py', 'sp67_data.py', 'rsna_diag/__init__.py', 'rsna_diag/generate.py',
              'rsna_diag/lora.py', 'rsna_diag/queue_lock.py', 'rsna_diag/geometry.py', 'rsna_diag/prompts.py',
              'rsna_diag/mi19_mha.py', 'rsna_diag/mi19_render.py']:
        a = subprocess.check_output(['git', 'rev-parse', 'HEAD:' + p], text=True).strip()
        b = subprocess.check_output(['git', 'rev-parse', origin + ':' + p], text=True).strip()
        assert a == b, p
        blobs[p] = a
    man_path = 'results/iter_075/data/manifest.json'
    feat_path = 'results/iter_078/features.json'
    man, feat = C.read(man_path), C.read(feat_path)
    assert feat['manifest_sha256'] == C.sha(man_path)
    assert C.sha(feat['checkpoint']) == feat['checkpoint_sha256']
    src = {p: C.sha(p) for p in [man_path, feat_path, feat['checkpoint'], C.ADAPTER + '/adapter.pt',
                                '../agent/runs/iter_080/plan.md', '../agent/runs/iter_081/plan.md']}
    counts = {}
    patient_sets = {}
    for split, n in [('V8', 24), ('E24', 47)]:
        refpath = f'results/iter_078/data/refs_{split}.json'
        lp = f'results/iter_078/data/labels_{split}.json'
        refs = C.read(refpath)
        assert refs['manifest_sha256'] == C.sha(man_path)
        assert refs['features_sha256'] == C.sha(feat_path)
        src.update({p: C.sha(p) for p in [refpath, lp]})
        queries = refs['requests']
        assert len(queries) == n and len({r['id'] for r in queries}) == n
        queries.sort(key=lambda r: (int(r['patient']), r['ordinal']))
        ids = {r['id'] for r in queries}
        # 허용한 ID 외 grade는 조회/출력하지 않는다.
        mr = {r['id']: r for r in man['rows'] if r['id'] in ids}
        labels = C.read(lp)['labels']
        assert set(labels) == ids
        qpath = ('results/iter_077/gen/V8/R_lr2e-4_ep16' if split == 'V8' else 'results/iter_077/gen/E24/R_adapted')
        rawpath = qpath + '/gen_worker0.jsonl'
        envpath = qpath + '/gen_worker0.env.json'
        env = C.read(envpath)
        assert env['adapter_digest'] == C.ADAPTER_DIGEST
        assert env['env']['model_revision'] == C.CONFIG['model_revision']
        assert env['config']['max_new_tokens'] == 32
        raw = [r for r in G.read_jsonl(rawpath) if r['id'] in ids]
        assert len(raw) == n and {r['id'] for r in raw} == ids
        qmap = {r['id']: r for r in raw}
        src.update({p: C.sha(p) for p in [rawpath, envpath]})
        donors = {}
        for ordinal in sorted({r['ordinal'] for r in queries}):
            group = [r for r in queries if r['ordinal'] == ordinal]
            assert len(group) >= 2
            for i, r in enumerate(group):
                donors[r['id']] = group[(i + 1) % len(group)]
        requests, baseline = [], []
        for q in queries:
            rid = q['id']; row = mr[rid]; f = feat['items'][rid]; qr = qmap[rid]
            assert not row['excluded'] and row['split'] == split
            assert row['position_set'] == ('supervised' if split == 'V8' else 'held')
            assert labels[rid] == {k: row[k] for k in ('grade', 'patient', 'ordinal')}
            assert all(f[k] == q[k] == row[k] for k in ('patient', 'ordinal', 'split'))
            imgs = [{k: e[k] for k in ('path', 'file_sha256', 'pixel_sha256_padded')} for e in row['inputs']['R']]
            assert imgs == q['query_images']
            assert f['input_file_sha256'] == [e['file_sha256'] for e in imgs]
            assert qr['input_pixel_sha256'] == [e['pixel_sha256_padded'] for e in imgs]
            assert qr['input_file_sha256'] == [e['file_sha256'] for e in imgs]
            assert qr['adapter_digest'] == C.ADAPTER_DIGEST and qr['config_digest'] == env['config_digest']
            assert qr['request_id'] == G.request_id(C.ADAPTER_DIGEST, 'R', rid, G.sha(V.PROMPT_R), env['config_digest'])
            assert qr['parsed'] == (V.parse(qr['text']) if qr['ended_eos'] else None)
            assert len(f['probs']) == 5 and np.isfinite(f['probs']).all() and abs(sum(f['probs']) - 1) < 1e-5
            assert f['pred'] == int(np.argmax(f['probs']) + 1)
            V.load_images(imgs)
            baseline.append({'id': rid, **labels[rid], 'probs': f['probs'], 'C': f['pred'], 'Q': qr['parsed'],
                             'Q_suffix_ids': qr['suffix_ids'], 'Q_source': rawpath, 'Q_request_id': qr['request_id']})
            for cond in ('Q', 'A', 'T', 'X'):
                donor = donors[rid]
                images = [] if cond == 'T' else (donor['query_images'] if cond == 'X' else imgs)
                r = {k: q[k] for k in ('id', 'patient', 'ordinal', 'split')}
                r.update(cond=cond, automated_grade=f['pred'], donor=donor['id'] if cond == 'X' else None,
                         images=images, prompt=V.PROMPT_R if cond == 'Q' else R.audit_prompt(cond, f['pred']))
                C.check_request(r)
                requests.append(r)
        C.save(C.ROOT / f'data/requests_{split}.json', requests)
        C.save(C.ROOT / f'data/baseline_{split}.json', baseline)
        patient_sets[split] = sorted({r['patient'] for r in queries}, key=int)
        counts[split] = {'items': n, 'patients': len(patient_sets[split]), 'unavailable_donors': 0}
    assert not set(patient_sets['V8']) & set(patient_sets['E24'])
    C.save(C.ROOT / 'data/tech_ids.json', [r['id'] for r in C.read(C.ROOT / 'data/baseline_V8.json')[:4]])
    C.save(C.ROOT / 'data/source_audit.json', {'passed': True, 'source_files': src, 'inherited_blobs': blobs,
                                            'counts': counts, 'patient_sets': patient_sets,
                                            'note': '기존 고정 자료의 연결 재검사; 새 독립 평가 아님. 범위 밖 grade 미조회.'})
    print(counts)


if __name__ == '__main__':
    prepare()
