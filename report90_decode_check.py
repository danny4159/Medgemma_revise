"""긴 생성의 실제 cache·token 진행 확인. 내용 평가·cap 선택에 사용하지 않는다."""
import json
import time
from report90_numeric import OUT,environment
from report90_train import load_model
from report86_common import save,sha
from rsna_diag import generate as G

if __name__=='__main__':
    environment('0');torch,proc,model=load_model();model.eval()
    row=json.loads((OUT/'tech/requests_D8.json').read_text())[0]
    image,_,_=G.load_image(row['image']);inp=G.build_inputs(proc,image,row['prompt']);calls=[]
    def hook(module,args,kwargs):
        calls.append(dict(time=time.monotonic(),input_shape=list(kwargs['input_ids'].shape),use_cache=kwargs.get('use_cache'),past_type=type(kwargs.get('past_key_values')).__name__))
    handle=model.register_forward_pre_hook(hook,with_kwargs=True)
    start=time.monotonic();result=G.generate(torch,proc,model,inp,8,[1,106]);handle.remove()
    save(OUT/'tech/decode_check.json',dict(result=result,calls=calls,text=proc.decode(result['suffix_ids']),wall_s=time.monotonic()-start,
        config_use_cache=model.config.use_cache,generation_use_cache=model.generation_config.use_cache,source_sha=sha(__file__),scope='8-token technical progress only; not scored report'))
    print(json.dumps(dict(calls=calls,text=proc.decode(result['suffix_ids']))),flush=True)
