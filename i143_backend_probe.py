"""모델 적재 없이 SDPA backend의 동일 key/query 재계산 수치를 확인한다."""
import torch
from torch.nn.attention import sdpa_kernel,SDPBackend
from i143_runtime import save
from i141_common import now
from i143_data import OUT


def main():
    torch.cuda.set_per_process_memory_fraction(.025); torch.manual_seed(17)
    out=[]
    for n in [2048,2049]:
        q=torch.randn(1,8,n,256,device='cuda',dtype=torch.bfloat16)
        k=torch.randn_like(q); v=torch.randn_like(q)
        width=((n+7)//8)*8
        bias=torch.full((1,1,n,width),-torch.inf,device='cuda',dtype=torch.bfloat16)
        mask=torch.arange(n,device='cuda')[None,:]<=torch.arange(n,device='cuda')[:,None]
        bias=bias[...,:n]; bias.masked_fill_(mask,0)
        for backend in [SDPBackend.FLASH_ATTENTION,SDPBackend.EFFICIENT_ATTENTION]:
            try:
                with sdpa_kernel(backend):
                    full=torch.nn.functional.scaled_dot_product_attention(q,k,v,attn_mask=bias)
                    cached=torch.nn.functional.scaled_dot_product_attention(q[:,:,-1:],k,v,attn_mask=bias[:,:,-1:])
                out.append(dict(n=n,backend=str(backend),max_difference=float((full[:,:,-1:]-cached).abs().max())))
            except RuntimeError as exc: out.append(dict(n=n,backend=str(backend),error=str(exc)))
        del q,k,v,bias,mask
    save(OUT/'tests/backend_probe.json',dict(created_at=now(),rows=out,peak_reserved_mib=torch.cuda.max_memory_reserved()/1024**2,
         scope='합성 attention 연산만 검사. 모델 native/cache 동등성은 별도 실제 입력 검사 필요.'))
    print(out)


if __name__=='__main__':main()
