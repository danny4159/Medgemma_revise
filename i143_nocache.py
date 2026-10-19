"""전체 prefix 재계산을 유지하는 token checkpoint/재개. KV cache를 쓰지 않는다."""
import torch
from i143_model import hidden


@torch.no_grad()
def generate(model,embedding,roles,images,condition,cap,initial_tokens=None,progress=None):
    tokens=list(initial_tokens or [])
    assert len(tokens)<=cap
    eos=model.generation_config.eos_token_id
    eos={eos} if isinstance(eos,int) else set(eos)
    if tokens and tokens[-1] in eos: return tokens,True
    seq=embedding
    if tokens:
        extra=model.model.get_input_embeddings()(torch.tensor([tokens],device=embedding.device))
        seq=torch.cat([seq,extra],1)
        roles=torch.cat([roles,roles.new_full((len(tokens),),-2)])
        images=torch.cat([images,images.new_full((len(tokens),),-1)])
    for step in range(len(tokens),cap):
        h=hidden(model,seq,roles,images,condition)
        logits=model.lm_head(h[:,-1]).float()
        token=int(logits.argmax(-1)); tokens.append(token)
        if progress is not None and (len(tokens)%64==0 or token in eos or len(tokens)==cap): progress(tokens)
        if token in eos: break
        e=model.model.get_input_embeddings()(torch.tensor([[token]],device=embedding.device))
        seq=torch.cat([seq,e],1)
        roles=torch.cat([roles,roles.new_tensor([-2])]); images=torch.cat([images,images.new_tensor([-1])])
    return tokens,bool(tokens and tokens[-1] in eos)
