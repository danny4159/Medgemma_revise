"""동일 token/position의 S/A/N attention. 공식 Gemma3 연산과 교집합 mask만 변경.

각 query chunk의 정확한 SDPA를 계산한다. sliding KV eviction은 사용하지 않는다.
report loss까지 언어층 계산 그래프를 유지하며 vision/projector만 동결한다.
"""
import dataclasses
import math
from pathlib import Path
import torch
from torch import nn
import torch.nn.functional as F
from PIL import Image

MODEL=Path(__file__).resolve().parent.parent/'hf_cache/models--google--medgemma-1.5-4b-it/snapshots/91850547d9f0b2fdd21aa7c5f4f3d1a8a52c243b'
PREFIX='These are all axial DWI slices from one MRI sequence, ordered by physical position.\n'
REPORT='\nDescribe the DWI findings for this entire sequence, including supported locations, signal, shape and distribution. Do not infer ADC findings, cause or timing. Write one concise findings report.\n'


@dataclasses.dataclass
class Mask:
    roles: torch.Tensor  # prefix=-1, report=-2, local=slice index
    images: torch.Tensor  # image block, nonimage=-1
    condition: str
    offset: int=0
    window: int|None=None
    chunk: int=131072

    def materialize(self, qs, qe, ks, ke):
        q=torch.arange(qs,qe,device=self.roles.device)
        k=torch.arange(ks,ke,device=self.roles.device)
        qr=self.roles[q]; kr=self.roles[k]
        qi=self.images[q]; ki=self.images[k]
        native=(k[None,:]<=q[:,None])|((qi[:,None]==ki[None,:])&(qi[:,None]>=0))
        if self.window is not None:
            native &= k[None,:]>q[:,None]-self.window
        if self.condition!='N':
            g=1 if self.condition=='S' else 5
            same=(qr[:,None]>=0)&(kr[None,:]>=0)&(qr[:,None]//g==kr[None,:]//g)
            permitted=(qr[:,None]==-2)|(kr[None,:]==-1)|same
            # prefix cannot read local or report, including via bidirectional blocks.
            permitted &= (qr[:,None]!=-1)|(kr[None,:]==-1)
            native &= permitted
        return native[None,None]


def chunk_attention(module,query,key,value,attention_mask,dropout=0.,scaling=None,**kwargs):
    assert dropout==0 and isinstance(attention_mask,Mask)
    spec=attention_mask; nq=query.shape[-2]; nk=key.shape[-2]
    assert nk==spec.offset+nq, '명시적 untrimmed cache만 지원'
    key=key.repeat_interleave(query.shape[1]//key.shape[1],dim=1)
    value=value.repeat_interleave(query.shape[1]//value.shape[1],dim=1)
    chunks=[]
    for a in range(0,nq,spec.chunk):
        b=min(nq,a+spec.chunk); qs=spec.offset+a; qe=spec.offset+b
        # 동일한 masked key layout을 유지한다. cached sliding query만 key를
        # 잘라내면 bf16 SDPA의 수치 경로가 full-prefix 기준과 달라진다.
        ks=0
        # image block 내부의 미래 key를 포함한다. 전체 key mask가 정확히 차단한다.
        ke=nk
        if spec.window is not None:
            image=spec.images[qs:qe]
            future=qe
            if (image>=0).any():
                last=int(image.max()); positions=torch.where(spec.images[:nk]==last)[0]
                future=max(future,int(positions[-1])+1)
            ke=min(nk,future)
        mask=spec.materialize(qs,qe,ks,ke)
        out=F.scaled_dot_product_attention(query[:,:,a:b],key[:,:,ks:ke],value[:,:,ks:ke],
                                           attn_mask=mask,dropout_p=0.,scale=scaling,is_causal=False)
        chunks.append(out)
    return torch.cat(chunks,dim=2).transpose(1,2).contiguous(),None


class LoRA(nn.Module):
    def __init__(self,base):
        super().__init__(); self.base=base
        self.A=nn.Parameter(torch.empty(16,base.in_features,device=base.weight.device,dtype=torch.float32))
        self.B=nn.Parameter(torch.zeros(base.out_features,16,device=base.weight.device,dtype=torch.float32))
        nn.init.kaiming_uniform_(self.A,a=math.sqrt(5))
    def forward(self,x):
        return self.base(x)+(F.linear(F.linear(x.float(),self.A),self.B)*2).to(x.dtype)


def load(adapters=True):
    from transformers import AutoProcessor,AutoModelForImageTextToText
    from transformers.modeling_utils import ALL_ATTENTION_FUNCTIONS
    torch.set_num_threads(4); torch.manual_seed(17)
    free,total=torch.cuda.mem_get_info()
    # driver/외부 점유를 포함한 현재 free에서 worker 여유 2GiB를 별도 보존한다.
    assert free>10*1024**3
    torch.cuda.set_per_process_memory_fraction((free-2*1024**3)/total)
    proc=AutoProcessor.from_pretrained(MODEL,local_files_only=True)
    model=AutoModelForImageTextToText.from_pretrained(MODEL,local_files_only=True,dtype=torch.bfloat16,
                                                   device_map={'':'cuda:0'},attn_implementation='sdpa')
    model.requires_grad_(False)
    if adapters:
        for layer in model.model.language_model.layers:
            for name in ('q_proj','k_proj','v_proj','o_proj'):
                setattr(layer.self_attn,name,LoRA(getattr(layer.self_attn,name)))
    ALL_ATTENTION_FUNCTIONS.register('i143_chunk',chunk_attention)
    model.eval()
    return proc,model


def adapter_state(model):
    return {k:v.detach().cpu().clone() for k,v in model.named_parameters() if v.requires_grad}


def set_adapter(model,state):
    params={k:v for k,v in model.named_parameters() if v.requires_grad}
    assert params.keys()==state.keys()
    with torch.no_grad():
        for k,p in params.items():
            assert p.shape==state[k].shape
            p.copy_(state[k])


def inputs(proc,row,target=None):
    content=[dict(type='text',text=PREFIX)]
    for i,im in enumerate(row['images']):
        label=f"\nSlice {i+1}; original z={im['z']}; RAS superior={im['physical_RAS_mm'][2]:.3f} mm.\n"
        content.extend([dict(type='text',text=label),dict(type='image',image=Image.open(im['path']).convert('RGB'))])
    content.append(dict(type='text',text=REPORT))
    messages=[dict(role='user',content=content)]
    batch=proc.apply_chat_template(messages,tokenize=True,add_generation_prompt=True,return_dict=True,return_tensors='pt')
    ids=batch['input_ids'][0]; roles=torch.full_like(ids,-1); images=torch.full_like(ids,-1)
    # 명시 label의 token subsequence를 찾는다. special image delimiter까지 local로 포함한다.
    def locate(s):
        needle=proc.tokenizer.encode(s,add_special_tokens=False)
        matches=[j for j in range(len(ids)-len(needle)+1) if ids[j:j+len(needle)].tolist()==needle]
        assert len(matches)==1,(s,matches)
        return matches[0]
    starts=[locate(f'Slice {i+1};') for i in range(len(row['images']))]
    report_start=locate('Describe the DWI findings')
    # 앞 newline도 같은 local에 귀속: 이전 local→다음 local의 중계 허용은 없다.
    for i,start in enumerate(starts):
        end=starts[i+1] if i+1<len(starts) else report_start
        roles[start:end]=i
    roles[report_start:]=-2
    image_id=proc.tokenizer.convert_tokens_to_ids('<image_soft_token>')
    positions=torch.where(ids==image_id)[0]
    assert len(positions)==256*len(row['images']), 'crop/image token 계약 변경'
    for i in range(len(row['images'])):
        pos=positions[i*256:(i+1)*256]; assert len(pos)==256 and torch.all(roles[pos]==i)
        images[pos]=i
    prefix_len=len(ids)
    if target is not None:
        target_ids=proc.tokenizer.encode(target+'<end_of_turn>',add_special_tokens=False)
        batch['input_ids']=torch.cat([batch['input_ids'],torch.tensor([target_ids])],dim=1)
        batch['attention_mask']=torch.ones_like(batch['input_ids'])
        batch['token_type_ids']=torch.cat([batch['token_type_ids'],torch.zeros(1,len(target_ids),dtype=torch.long)],dim=1)
        roles=torch.cat([roles,torch.full((len(target_ids),),-2,dtype=torch.long)])
        images=torch.cat([images,torch.full((len(target_ids),),-1,dtype=torch.long)])
    return batch,roles,images,prefix_len


def embeds(model,batch):
    device=model.device
    with torch.no_grad():
        ids=batch['input_ids'].to(device)
        emb=model.model.get_input_embeddings()(ids)
        # bf16 batch/query 분할은 수학적으로 같아도 native logits 회귀에서 실패했다.
        # 공식 경로와 같은 전체 image batch를 우선하며 임의 분할하지 않는다.
        features=model.model.get_image_features(batch['pixel_values'].to(device,dtype=torch.bfloat16),return_dict=True).pooler_output.to(emb.dtype)
        mask=model.model.get_placeholder_mask(ids,emb,features)
        emb=emb.masked_scatter(mask,features)
    return emb


def hidden(model,embedding,roles,images,condition,cache=None,offset=0,chunk=131072):
    lm=model.model.language_model
    lm.config._attn_implementation='i143_chunk'
    roles=roles.to(embedding.device); images=images.to(embedding.device)
    masks={k:Mask(roles,images,condition,offset,1024 if k=='sliding_attention' else None,chunk)
           for k in ('full_attention','sliding_attention')}
    positions=torch.arange(offset,offset+embedding.shape[1],device=embedding.device)[None]
    return lm(inputs_embeds=embedding,attention_mask=masks,position_ids=positions,
              past_key_values=cache,use_cache=cache is not None,return_dict=True).last_hidden_state


def target_loss(model,embedding,roles,images,condition,ids,prefix):
    h=hidden(model,embedding,roles,images,condition)
    logits=model.lm_head(h[:,prefix-1:-1]).float()
    if model.config.text_config.final_logit_softcapping is not None:
        cap=model.config.text_config.final_logit_softcapping; logits=torch.tanh(logits/cap)*cap
    return F.cross_entropy(logits.reshape(-1,logits.shape[-1]),ids[:,prefix:].to(logits.device).reshape(-1))


@torch.no_grad()
def generate(model,embedding,roles,images,condition,cap,cache_enabled=True):
    from transformers.cache_utils import DynamicCache
    cache=DynamicCache() if cache_enabled else None # no sliding eviction, masks enforce native window
    seq=embedding; tokens=[]; eos=model.generation_config.eos_token_id
    eos={eos} if isinstance(eos,int) else set(eos)
    for step in range(cap):
        offset=0 if step==0 or not cache_enabled else len(roles)-1
        h=hidden(model,seq,roles,images,condition,cache=cache,offset=offset)
        logits=model.lm_head(h[:,-1]).float()
        token=int(logits.argmax(-1)); tokens.append(token)
        if token in eos: break
        e=model.model.get_input_embeddings()(torch.tensor([[token]],device=embedding.device))
        seq=e if cache_enabled else torch.cat([seq,e],dim=1)
        roles=torch.cat([roles,roles.new_tensor([-2])]); images=torch.cat([images,images.new_tensor([-1])])
    return tokens,bool(tokens[-1] in eos)
