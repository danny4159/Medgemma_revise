"""D24 전체의 공식 tensor 및 영상 순서·단일 F index 대조."""
import json
import torch
from transformers import AutoProcessor
from mt52_prepare import OUT,save,sha256_file
from mt52_sanity import images,build
from mt52_spec import prompt,MODEL_REVISION

def main():
    torch.set_num_threads(2)
    proc=AutoProcessor.from_pretrained('google/medgemma-1.5-4b-it',revision=MODEL_REVISION,local_files_only=True)
    cs=json.loads((OUT/'data/D_inference.json').read_text())
    manifest={r['case_key']:r for r in json.loads((OUT/'data/D_images.json').read_text())};checks=[]
    for c in cs:
        ims=images(c,manifest)
        for stage,idx in [('T',[]),('D',list(range(len(ims)))),('F',[len(ims)-1])]:
            text=prompt(c,stage,index=idx[0] if stage=='F' else None)
            selected=[ims[i] for i in idx];a=build(proc,selected,text,idx)
            content=[{'type':'text','text':text}]
            for i in idx:content.extend([{'type':'text','text':f'Image {i+1}:'},{'type':'image'}])
            rendered=proc.apply_chat_template([{'role':'user','content':content}],tokenize=False,add_generation_prompt=True)
            b=proc(text=rendered,images=selected or None,return_tensors='pt',add_special_tokens=False)
            assert set(a)==set(b)
            assert all(a[k].shape==b[k].shape and a[k].dtype==b[k].dtype and torch.equal(a[k],b[k]) for k in a)
            if stage=='F':assert f'Image index: {idx[0]+1}' in rendered and f'Image {idx[0]+1}:' in rendered
            checks.append({'case':c['case_key'],'stage':stage,'indices':idx,'all_tensors_equal':True,
                'input_tokens':a['input_ids'].shape[1],'keys':{k:{'shape':list(v.shape),'dtype':str(v.dtype)} for k,v in a.items()}})
        a=build(proc,ims[:2],prompt(c,'D'));b=build(proc,list(reversed(ims[:2])),prompt(c,'D'))
        assert torch.equal(a['input_ids'],b['input_ids'])
        assert torch.equal(a['pixel_values'][0],b['pixel_values'][1]) and torch.equal(a['pixel_values'][1],b['pixel_values'][0])
        checks.append({'case':c['case_key'],'stage':'swap_two','ordered_pixels_equal':True})
    save(OUT/'tests/input_tensor_final.json',{'status':'PASS','cases':len(cs),'checks':checks,
        'source':sha256_file(__file__),'inference_sha256':sha256_file(OUT/'data/D_inference.json')})
    print('PASS',len(cs),len(checks))

if __name__=='__main__':main()
