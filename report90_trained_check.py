"""비영 LoRA 상태의 길이 비간섭 재확인. 학습·표본·판정 문턱은 변경하지 않는다."""
import argparse
import json
import sys
from pathlib import Path
import report90_numeric as N
from report90_stable import apply
from report86_common import save,sha
from rsna_diag import train as T

def main():
    p=argparse.ArgumentParser();p.add_argument('--checkpoint',required=True);p.add_argument('--gpu',required=True);p.add_argument('--name',required=True);p.add_argument('--gradient',action='store_true');a=p.parse_args()
    original=N.M.load
    def load():
        torch,proc,model=original();ck=torch.load(a.checkpoint,map_location='cpu',weights_only=False)
        N.M.lora.load_lora_state(model,ck['adapter']);assert N.M.lora.state_digest(N.M.lora.lora_state_dict(model))==ck['digests']['adapter'];apply(model)
        save(N.OUT/'tech'/a.name/'trained_protocol.json',dict(checkpoint=str(Path(a.checkpoint).resolve()),checkpoint_sha=sha(a.checkpoint),
            source_sha=sha(__file__),adapter_digest=ck['digests']['adapter'],step=ck['step']))
        return torch,proc,model
    N.M.load=load
    if not a.gradient:
        sys.argv=[sys.argv[0],'--gpu',a.gpu,'--name',a.name];N.main()
    else:
        out=N.OUT/'tech'/a.name;out.mkdir(parents=True,exist_ok=False);N.environment(a.gpu)
        torch,proc,model=load();T.set_deterministic(torch);model.train()
        for module in model.modules():
            if isinstance(module,torch.nn.Dropout):module.p=0.
        row=json.loads((N.OUT/'data/D8/manifest.json').read_text())[0];results=[]
        for full in [True,False]:
            model.zero_grad(set_to_none=True);b=N.M.batch([N.M.example(proc,row,full=full)],proc.tokenizer.pad_token_id)
            loss,_=N.M.losses(model,b,0.);loss.backward()
            results.append(dict(loss=float(loss),grad={k:p.grad.detach().cpu().clone() for k,p in N.M.lora.lora_params(model).items()}));del loss,b
        first,second=results
        diff=sum(float((first['grad'][k]-second['grad'][k]).double().square().sum()) for k in first['grad'])**.5
        den=sum(float(g.double().square().sum()) for g in second['grad'].values())**.5
        rel=diff/max(den,1e-30);loss_abs=abs(first['loss']-second['loss'])
        result=dict(passed=rel<=.02 and loss_abs<=.002,relative_l2=rel,loss_abs=loss_abs,technical_optimizer_updates=0)
        save(out/'result.json',result);print(json.dumps(result),flush=True);raise SystemExit(0 if result['passed'] else 2)

if __name__=='__main__':main()
