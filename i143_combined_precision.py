"""전체 key layout과 정밀 누산을 함께 쓰는 마지막 cache 기술 후보."""
import sys
import torch
from i143_data import OUT
from i143_runtime import save
from i141_common import sha,now


def main():
    torch.backends.cuda.matmul.allow_bf16_reduced_precision_reduction=False
    save(OUT/'tests/fullkeys_precise_config.json',dict(created_at=now(),model_sha256=sha('i143_model.py'),
         allow_bf16_reduced_precision_reduction=False,acceptance='원 tolerance .125와 greedy 일치 유지'))
    import i143_generation_checks
    sys.argv=['i143_generation_checks.py','--name','fullkeys_precise_a1','--cache-only']
    i143_generation_checks.main()


if __name__=='__main__':main()
