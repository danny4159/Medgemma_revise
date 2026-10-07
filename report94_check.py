"""iter_094: 신규 epoch1 생성 64건의 완결성·입력 연결 확인과 inputs manifest 기록."""
import json
from pathlib import Path
from report86_common import sha,sha_obj,record_digest,save

ROOT=Path(__file__).resolve().parent
R=ROOT/'results'
OUT=R/'iter_094'
REQ=R/'iter_090/data/V32/requests.json'

def rows(p):
    return [json.loads(l) for l in Path(p).read_text().splitlines()]

def main():
    req={r['id']:r for r in json.loads(REQ.read_text())}
    old={r['id']:r for r in rows(R/'iter_090/recovery/validation/epoch6/R_lr0.0002_report/worker_0.jsonl')}
    final=json.loads((R/'iter_090/recovery/selection/final.json').read_text())
    report={}
    for m in 'RG':
        stage=OUT/f'gen/{m}_epoch1';new=rows(stage/'worker_0.jsonl');proto=json.loads((stage/'protocol.json').read_text())
        comp=json.loads((stage/'completion.json').read_text())
        sel=final['selected'][m]
        assert proto['checkpoint_sha']==sel['checkpoint_sha']==sha(sel['checkpoint']) and proto['checkpoint']==sel['checkpoint']
        assert comp['n']==32 and comp['protocol_digest']==sha_obj(proto)
        assert all(sha(f)==h for f,h in comp['files'].items())
        assert len({r['id'] for r in new})==32 and {r['id'] for r in new}==set(req)
        for r in new:
            assert r['request_digest']==sha_obj(req[r['id']]) and r['protocol_digest']==sha_obj(proto) and r['record_digest']==record_digest(r)
            assert r['image_sha256']==req[r['id']]['file_sha256']==sha(req[r['id']]['image'])
            assert r['input_ids']==old[r['id']]['input_ids']
        report[m]=dict(n=len(new),checkpoint=sel['checkpoint'],checkpoint_sha=sel['checkpoint_sha'],eos=sum(bool(r['attempts'][-1]['ended_eos']) for r in new),
            cap_extended=sum(len(r['attempts'])>1 for r in new),empty=sum(not r['text'].strip() for r in new),
            mean_words=sum(len(r['text'].split()) for r in new)/len(new),gpus=sorted({r['gpu'] for r in new}),
            wall_s=json.loads((stage/'launch_000.json').read_text())['wall_s'],protocol_digest=sha_obj(proto),
            unique_outputs=len({r['text'] for r in new}))
    files={str(p.relative_to(ROOT)):sha(p) for p in [REQ,R/'iter_090/data/V32/manifest.json',R/'iter_090/semantic/V32_reference_v3.json',R/'iter_090/recovery/selection/final.json',
        R/'iter_090/recovery/train/R_lr0.0002/validation_01.json',R/'iter_090/recovery/train/G_lr0.0002/validation_01.json',
        R/'iter_090/recovery/train/R_lr0.0002/config.json',R/'iter_090/recovery/train/G_lr0.0002/config.json',
        R/'iter_090/recovery/train/R_lr0.0002/complete_06.json',R/'iter_090/recovery/train/G_lr0.0002/complete_06.json',
        R/'iter_090/recovery/train/R_lr0.0002/verified_06.json',R/'iter_090/recovery/train/G_lr0.0002/verified_06.json',
        R/'iter_090/recovery/semantic/epoch2/eval/per_output.json',R/'iter_090/recovery/semantic/epoch6/eval/per_output.json',
        R/'iter_090/recovery/semantic/epoch2/blinded.json',R/'iter_090/recovery/semantic/epoch6/blinded.json',
        R/'iter_090/recovery/semantic/epoch2/private_mapping.json',R/'iter_090/recovery/semantic/epoch6/private_mapping.json',
        R/'iter_090/recovery/stage_decision_rules.json']}
    save(OUT/'input_manifest.json',dict(files=files,generation=report,note='checkpoint 바이트 hash는 선택 파일의 기록과 재계산 일치'))
    print(json.dumps(report,indent=1))

if __name__=='__main__':
    main()
