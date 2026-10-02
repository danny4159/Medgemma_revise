"""D 입력의 공식 processor tensor 대조와 실제 긴 다중 영상 생성 실측."""
import json
import os
import time
import traceback
from PIL import Image
from mt52_prepare import ROOT,OUT,save,safe,sha256_file
from mt52_spec import prompt,MODEL_REVISION

def images(c,manifest):
    rows=manifest[c['case_key']]['images'];out=[]
    assert [r['id'] for r in rows]==[r['id'] for r in c['images']]
    for r in rows:
        p=safe(ROOT/r['path']);assert sha256_file(p)==r['sha256']
        with Image.open(p) as im:
            if im.mode=='RGBA':assert im.getchannel('A').getextrema()==(255,255)
            im=im.convert('RGB')
            import hashlib
            assert hashlib.sha256(str(im.size).encode()+im.tobytes()).hexdigest()==r['rgb_sha256']
            out.append(im.copy())
    return out

def build(proc,ims,text,indices=None):
    indices=list(range(len(ims))) if indices is None else indices
    assert len(indices)==len(ims)
    content=[{'type':'text','text':text}]
    for i,im in zip(indices,ims):
        content.extend([{'type':'text','text':f'Image {i+1}:'},{'type':'image','image':im}])
    return proc.apply_chat_template([{'role':'user','content':content}],tokenize=True,
        add_generation_prompt=True,return_dict=True,return_tensors='pt')

def main():
    allowed=os.environ.get('CUDA_VISIBLE_DEVICES','').split(',')
    assert '1' in allowed
    os.environ['CUDA_VISIBLE_DEVICES']='1'
    from rsna_diag.generate import load_model,env_info
    torch,proc,model=load_model();torch.manual_seed(5201)
    cs=json.loads((OUT/'data/D_inference.json').read_text())
    manifest={r['case_key']:r for r in json.loads((OUT/'data/D_images.json').read_text())}
    save(OUT/'sanity/environment.json',env_info(torch,proc,model))
    checks=[]
    short=min(cs,key=lambda c:len(c['images']));long=max(cs,key=lambda c:len(c['images']))
    for name,c,n in [('text',short,0),('single',short,1),('two',short,2),('longest',long,len(long['images']))]:
        ims=images(c,manifest)[:n];text=prompt(c,'D')
        a=build(proc,ims,text)
        # 공식 two-step 경로: template 문자열을 먼저 만든 뒤 processor 호출.
        content=[{'type':'text','text':text}]
        for i in range(n):content.extend([{'type':'text','text':f'Image {i+1}:'},{'type':'image'}])
        rendered=proc.apply_chat_template([{'role':'user','content':content}],tokenize=False,add_generation_prompt=True)
        b=proc(text=rendered,images=ims if ims else None,return_tensors='pt',add_special_tokens=False)
        ok=set(a)==set(b) and all(a[k].shape==b[k].shape and a[k].dtype==b[k].dtype and torch.equal(a[k],b[k]) for k in a)
        checks.append({'name':name,'n_images':n,'equal':ok,'keys':{k:{'shape':list(v.shape),'dtype':str(v.dtype)} for k,v in a.items()},'input_tokens':a['input_ids'].shape[1]})
        save(OUT/'sanity'/f'tensors_v2_{name}.json',checks[-1]);assert ok
        if name not in ('two','longest'):continue
        cap=1024;torch.cuda.empty_cache();torch.cuda.reset_peak_memory_stats();start=time.time()
        try:
            x={k:v.to('cuda',dtype=torch.bfloat16) if v.is_floating_point() else v.to('cuda') for k,v in a.items()}
            torch.cuda.synchronize();t=time.time()
            with torch.inference_mode():y=model.generate(**x,max_new_tokens=cap,do_sample=False)
            torch.cuda.synchronize();end=time.time();ids=y[0,a['input_ids'].shape[1]:].tolist()
            eos=model.generation_config.eos_token_id;eos=eos if isinstance(eos,list) else [eos]
            result={'status':'PASS','case_key':c['case_key'],'stage':'D','cap':cap,'tokens':ids,'text':proc.decode(ids,skip_special_tokens=True),
                'eos':bool(ids and ids[-1] in eos),'runtime':end-t,'total':end-start,
                'peak_alloc_GiB':torch.cuda.max_memory_allocated()/2**30,'peak_reserved_GiB':torch.cuda.max_memory_reserved()/2**30}
            del x,y
        except Exception as e:
            result={'status':'FAIL','error':repr(e),'traceback':traceback.format_exc(),'total':time.time()-start,
                'peak_alloc_GiB':torch.cuda.max_memory_allocated()/2**30,'peak_reserved_GiB':torch.cuda.max_memory_reserved()/2**30}
        save(OUT/'sanity'/f'generate_{name}.json',result)
        print(name,result['status'],result.get('runtime'),flush=True)
        if result['status']=='FAIL':raise RuntimeError(result['error'])

if __name__=='__main__':main()
