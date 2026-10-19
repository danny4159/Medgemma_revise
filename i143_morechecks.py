"""6장 실제 입력으로 그룹 경계·target causality·S/A loss gradient 검사."""
import copy
from pathlib import Path
import torch
from i143_model import load,inputs,embeds,hidden,target_loss
from i143_data import OUT
from i141_common import read,save,sha,now


def main():
    proc,m=load(); original=next(r for r in read(OUT/'data_manifest.json')['rows'] if r['split']=='T')
    row=copy.deepcopy(original); row['images']=row['images'][:6]
    b,ro,ii,p=inputs(proc,row); e=embeds(m,b); result={}
    with torch.no_grad():
        altered=e.clone(); altered[:,ii==0]+=torch.randn_like(altered[:,ii==0])*.5
        h=hidden(m,e,ro,ii,'A'); changed=hidden(m,altered,ro,ii,'A')
        result['A_other_group_max']=float((h[:,ro==5]-changed[:,ro==5]).abs().max())
        result['A_same_group_max']=float((h[:,ro==1]-changed[:,ro==1]).abs().max())
        result['report_max']=float((h[:,ro==-2]-changed[:,ro==-2]).abs().max())
        assert result['A_other_group_max']==0 and result['A_same_group_max']>0 and result['report_max']>0
        tail=m.model.get_input_embeddings()(torch.tensor([[100,101,102]],device='cuda'))
        all_e=torch.cat([e,tail],1); all_ro=torch.cat([ro,ro.new_tensor([-2,-2,-2])]); all_ii=torch.cat([ii,ii.new_tensor([-1,-1,-1])])
        alt=all_e.clone(); alt[:,-1]+=1
        for cond in ['S','A','N']:
            ha=hidden(m,all_e,all_ro,all_ii,cond); hb=hidden(m,alt,all_ro,all_ii,cond)
            diff=float((ha[:,:-1]-hb[:,:-1]).abs().max()); assert diff==0
            result['future_target_'+cond]=diff
    del e,b,h,changed,altered,all_e,alt,ha,hb
    refs={r['patient_id']:r['target'] for r in read(OUT/'reference_locked.json')['rows']}
    b,ro,ii,p=inputs(proc,original,refs[original['patient_id']]); e=embeds(m,b)
    m.gradient_checkpointing_enable(gradient_checkpointing_kwargs={'use_reentrant':False}); m.train()
    for cond in ['S','A']:
        m.zero_grad(set_to_none=True); leaf=e.detach().requires_grad_(True)
        loss=target_loss(m,leaf,ro,ii,cond,b['input_ids'],p); loss.backward()
        norms=[float(leaf.grad[:,ro==j].norm()) for j in range(original['n_slices'])]
        assert all(x>0 and x<float('inf') for x in norms)
        result['all_slice_gradient_'+cond]=norms
    save(OUT/'tests/additional_graph_checks.json',dict(created_at=now(),passed=True,results=result,
         source_sha256=sha(__file__),model_source_sha256=sha(Path(__file__).with_name('i143_model.py'))))

if __name__=='__main__': main()
