"""실패한 native 대조의 feature/backend 오차를 분리한다. gate 문턱 변경 없음."""
import json
import copy
import torch
from i143_model import load,inputs,embeds,hidden
from i143_data import OUT
from i141_common import read,save,now


def main():
    proc,m=load(); row=copy.deepcopy(next(r for r in read(OUT/'data_manifest.json')['rows'] if r['split']=='T'))
    row['images']=row['images'][:2]; b,r,i,p=inputs(proc,row)
    b={k:v.to('cuda',dtype=torch.bfloat16) if v.is_floating_point() else v.to('cuda') for k,v in b.items()}
    records={}
    with torch.no_grad():
        e=embeds(m,b)
        full=m.model.get_image_features(b['pixel_values'],return_dict=True).pooler_output
        raw=m.model.get_input_embeddings()(b['input_ids']); mask=m.model.get_placeholder_mask(b['input_ids'],raw,full)
        official_emb=raw.masked_scatter(mask,full)
        records['embedding_max']=float((e-official_emb).abs().max())
        m.model.language_model.config._attn_implementation='sdpa'
        oh=m.model(**b,use_cache=False,return_dict=True).last_hidden_state
        cached=m.model(inputs_embeds=e,token_type_ids=b['token_type_ids'],attention_mask=b['attention_mask'],use_cache=False,return_dict=True).last_hidden_state
        hs={'official':oh,'cached_sdpa':cached,
            'chunk256_fullfeatures':hidden(m,official_emb,r,i,'N',chunk=256),
            'chunk620_fullfeatures':hidden(m,official_emb,r,i,'N',chunk=len(r)),
            'chunk256_singlefeatures':hidden(m,e,r,i,'N',chunk=256)}
        logits={k:m.lm_head(v[:,-8:]).float() for k,v in hs.items()}
        for k,v in logits.items():
            records[k]=dict(logit_max=float((v-logits['official']).abs().max()),argmax_equal=bool(torch.equal(v.argmax(-1),logits['official'].argmax(-1))))
        records['created_at']=now(); save(OUT/'tests/numeric_a1.json',records); print(json.dumps(records))

if __name__=='__main__': main()
