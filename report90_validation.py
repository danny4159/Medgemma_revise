"""고정 V32/V16 요청과 학습 전 V64 NLL. E 자료는 열지 않는다."""
import argparse
import json
import time
from report90_numeric import OUT,environment
from report90_train import load_model,validate
from report86_common import save,sha
import report89_model as M

def prepare():
    selected=json.loads((OUT/'data/selection.json').read_text());v=json.loads((OUT/'data/V64/manifest.json').read_text());by={r['ImageID']:r for r in v}
    for subset in ('V32','V16'):
        rows=[by[r['ImageID']] for r in selected[subset]];save(OUT/f'data/{subset}/manifest.json',rows)
        requests=[]
        for r in rows:
            prompt=M.CFG['report_prompt'] if subset=='V32' else M.ground_target(r,0)[0]
            requests.append(dict(id=r['ImageID']+('|report' if subset=='V32' else '|ground'),image=r['image'],file_sha256=r['file_sha256'],prompt=prompt))
        save(OUT/f'data/{subset}/requests.json',requests)
    save(OUT/'data/validation_requests_lock.json',dict(sources={f:sha(f) for f in ['report90_validation.py','report89_model.py','results/iter_090/data/V32/requests.json','results/iter_090/data/V16/requests.json']},
        report_input='영상+고정 중립 prompt; 정답 문장/위치 미제공',ground_input='영상+정답 소견 문장 한 개; 독립 첫 user turn의 보조 진단',epoch_ground_target=0))

def nll(gpu):
    mapping=environment(gpu);torch,proc,model=load_model();model.train()
    rows=json.loads((OUT/'data/V64/manifest.json').read_text());opt=torch.optim.AdamW(list(M.lora.lora_params(model).values()),lr=1e-4,betas=(.9,.999),eps=1e-8,weight_decay=.01)
    start=time.monotonic();result=validate(torch,model,proc,rows,opt)
    save(OUT/'validation/base_nll.json',dict(result,mapping=mapping,wall_s=time.monotonic()-start,manifest_sha256=sha(OUT/'data/V64/manifest.json'),source_sha256=sha(__file__)))
    print(json.dumps({k:result[k] for k in ('n','report_nll','state_preserved')}),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('command',choices=['prepare','nll']);p.add_argument('--gpu');a=p.parse_args()
    prepare() if a.command=='prepare' else nll(a.gpu)
