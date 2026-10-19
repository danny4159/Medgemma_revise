"""잠긴 E16 요청을 환자별 두 shard로 나눈다. 모델·평가·표본 규칙은 그대로다."""
import argparse
import copy
import fcntl
import os
from pathlib import Path
import torch
from i143_data import OUT
from i143_model import load,set_adapter
from i143_train import predict,bound
from i143_runtime import save
from i143_decision import swap_condition
from i141_common import read,sha,digest


def partition(manifest,swap,shard):
    assert shard in (0,1)
    rows=copy.deepcopy(sorted((r for r in manifest if r['split']=='E'),key=lambda r:r['patient_id']))
    assert len(rows)==len({r['patient_id'] for r in rows})==16
    originals=copy.deepcopy(rows)
    if swap:
        for i,row in enumerate(rows):
            donor=originals[(i+1)%16]
            row.update(images=donor['images'],n_slices=donor['n_slices'],image_source_patient=donor['patient_id'])
    return rows[shard::2]


def runtime_bound():
    protocol=read(OUT/'confirm_runtime_protocol.json')
    assert protocol['passed'] and protocol['shards']==2
    for path,h in protocol['files'].items(): assert sha(path)==h,path
    return protocol


def main():
    p=argparse.ArgumentParser(); p.add_argument('--condition',choices=['S','A','N'],required=True)
    p.add_argument('--shard',type=int,choices=[0,1],required=True)
    p.add_argument('--base',action='store_true'); p.add_argument('--swap',action='store_true'); a=p.parse_args()
    runtime_bound(); gate=read(OUT/'training_gate.json'); bound(gate)
    selection=read(OUT/'selection.json'); assert selection['passed']
    assert selection['gate_sha256']==sha(OUT/'training_gate.json') and selection['evidence_files']
    for path,h in selection['evidence_files'].items(): assert sha(path)==h
    assert selection['swap_condition']==swap_condition(selection['validation_metrics'])
    assert selection['epoch']==(16 if read(OUT/'extension_decision.json')['extend'] else 8)
    assert not(a.base and a.swap)
    if a.swap: assert a.condition==selection['swap_condition']
    epoch=0 if a.base else selection['epoch']
    stage=f'{a.condition}_epoch{epoch:02d}'+('_swap' if a.swap else '')
    dest=OUT/'confirm_sharded'/stage/f'shard{a.shard}'
    dest.mkdir(parents=True,exist_ok=True)
    fd=os.open(dest/'owner.lock',os.O_CREAT|os.O_RDWR,0o600); fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
    rows=partition(read(OUT/'data_manifest.json')['rows'],a.swap,a.shard)
    refs={r['patient_id']:r for r in read(OUT/'reference_locked.json')['rows'] if r['split']=='E'}
    request=dict(selection_sha256=sha(OUT/'selection.json'),runtime_sha256=sha(OUT/'confirm_runtime_protocol.json'),
                 condition=a.condition,epoch=epoch,swap=a.swap,shard=a.shard,
                 rows=[dict(patient_id=r['patient_id'],image_source_patient=r.get('image_source_patient',r['patient_id']),
                            image_hashes=[im['sha256'] for im in r['images']]) for r in rows])
    if (dest/'request.json').exists(): assert read(dest/'request.json')==request
    else: save(dest/'request.json',request)
    proc,m=load()
    if epoch:
        cp=OUT/'train'/a.condition/f'epoch{epoch:02d}.pt'
        assert sha(cp)==selection['checkpoints'][a.condition]['sha256']
        state=torch.load(cp,map_location='cpu',weights_only=False)
        assert state['epoch']==epoch and state['config']['condition']==a.condition
        set_adapter(m,state['adapter']); del state
    records=predict(proc,m,rows,refs,a.condition,epoch,dest/'outputs',gate['cap'],gate['cache_enabled'])
    paths=sorted((dest/'outputs').glob('*.json'))
    assert {q.name for q in paths}=={r['patient_id']+'.json' for r in rows}
    assert len(records)==len({r['patient_id'] for r in records})==8
    completion=dict(request_digest=digest(request),files={str(q):sha(q) for q in paths},n=8)
    if (dest/'completion.json').exists(): assert read(dest/'completion.json')==completion
    else: save(dest/'completion.json',completion)
    os.close(fd)


if __name__=='__main__': main()
