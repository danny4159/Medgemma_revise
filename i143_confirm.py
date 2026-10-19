"""V 선택을 봉인한 뒤 보존 E16의 고정 요청만 생성한다."""
import argparse
import copy
import fcntl
import os
import torch
from i143_data import OUT
from i143_model import load,set_adapter
from i143_train import predict,bound
from i143_runtime import save
from i143_decision import swap_condition
from i141_common import read,sha,now,digest


def main():
    p=argparse.ArgumentParser(); p.add_argument('--condition',required=True,choices=['S','A','N'])
    p.add_argument('--base',action='store_true'); p.add_argument('--swap',action='store_true'); a=p.parse_args()
    gate=read(OUT/'training_gate.json'); bound(gate)
    selection=read(OUT/'selection.json'); assert selection['passed'] is True
    assert selection['gate_sha256']==sha(OUT/'training_gate.json')
    assert selection['evidence_files']
    for path,h in selection['evidence_files'].items(): assert sha(path)==h
    assert selection['swap_condition']==swap_condition(selection['validation_metrics'])
    extension=read(OUT/'extension_decision.json')
    assert selection['epoch']==(16 if extension['extend'] else 8)
    assert not(a.base and a.swap)
    if a.swap: assert a.condition==selection['swap_condition']
    epoch=0 if a.base else selection['epoch']; assert epoch in [0,8,16]
    stage=f'{a.condition}_epoch{epoch:02d}'+('_swap' if a.swap else '')
    dest=OUT/'confirm'/stage; dest.mkdir(parents=True,exist_ok=True)
    fd=os.open(dest/'owner.lock',os.O_CREAT|os.O_RDWR,0o600); fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
    rows=[r for r in read(OUT/'data_manifest.json')['rows'] if r['split']=='E']; assert len(rows)==16
    rows.sort(key=lambda r:r['patient_id']); originals=copy.deepcopy(rows)
    if a.swap:
        for i,row in enumerate(rows):
            donor=originals[(i+1)%len(rows)]
            row['images']=donor['images']; row['n_slices']=donor['n_slices']
            row['image_source_patient']=donor['patient_id']
    references={r['patient_id']:r for r in read(OUT/'reference_locked.json')['rows'] if r['split']=='E'}
    request=dict(selection_sha256=sha(OUT/'selection.json'),condition=a.condition,epoch=epoch,swap=a.swap,
                 rows=[dict(patient_id=r['patient_id'],image_source_patient=r.get('image_source_patient',r['patient_id']),
                            image_hashes=[im['sha256'] for im in r['images']]) for r in rows])
    if (dest/'request.json').exists(): assert read(dest/'request.json')==request
    else: save(dest/'request.json',request)
    proc,m=load()
    if epoch:
        cp=OUT/'train'/a.condition/f'epoch{epoch:02d}.pt'
        assert sha(cp)==selection['checkpoints'][a.condition]['sha256']
        state=torch.load(cp,map_location='cpu',weights_only=False); assert state['epoch']==epoch
        set_adapter(m,state['adapter']); del state
    records=predict(proc,m,rows,references,a.condition,epoch,dest/'outputs',gate['cap'],gate['cache_enabled'])
    expected={r['patient_id']+'.json' for r in rows}
    assert {p.name for p in (dest/'outputs').glob('*.json')}==expected
    assert len(records)==len({r['patient_id'] for r in records})==16
    completion=dict(request_digest=digest(request),files={str(p):sha(p) for p in (dest/'outputs').glob('*.json')},
                    n=16,condition=a.condition,epoch=epoch,swap=a.swap)
    if (dest/'completion.json').exists(): assert read(dest/'completion.json')==completion
    else: save(dest/'completion.json',completion)
    os.close(fd)


if __name__=='__main__':main()
