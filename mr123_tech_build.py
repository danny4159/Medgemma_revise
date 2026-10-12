"""iter_123: 기술 6명 영상 구성 + QC + montage"""
import json, sys
import mr123_data as D
L = json.load(open(D.RES + 'data/selection_lock.json'))
led = json.load(open(D.RES + 'data/fetch_ledger.json'))
roles = sys.argv[1:]
out = {}
for r in L['manifest']:
    if r['role'] in roles and r['study_uid'] in led:
        info = D.build_case(r, led[r['study_uid']]['path'], D.ROOT + 'png/' + r['study_uid'])
        info.update(label=r['label'], batch_id=r['batch_id'], role=r['role'])
        out[r['study_uid']] = info
        print(r['role'], r['label'], r['study_uid'], info.get('exclude'), info.get('canon_axcodes'), info.get('canon_shape'), info.get('canon_zooms'), info.get('brain_slice_range'), info.get('C_idx'), info.get('W_idx'))
        if info.get('exclude') is None:
            D.montage(info, 'W', D.RES + f'data/montage_W_{r["study_uid"]}.png')
json.dump(out, open(D.RES + 'data/build_' + '_'.join(roles) + '.json', 'w'), indent=1)
