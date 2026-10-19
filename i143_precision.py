"""동일 bf16 weights/activations에서 누산 정밀도만 보강하는 기술 후보."""
import argparse
import sys
import torch
from i143_data import OUT
from i143_runtime import save
from i141_common import sha,now


def main():
    p=argparse.ArgumentParser(); p.add_argument('--phase',choices=['cache','tech','train'],required=True); a=p.parse_args()
    torch.backends.cuda.matmul.allow_bf16_reduced_precision_reduction=False
    name='precise_'+a.phase+'_a1'
    save(OUT/'tests'/(name+'_config.json'),dict(created_at=now(),allow_bf16_reduced_precision_reduction=False,
         source_sha256=sha(__file__),model_source_sha256=sha('i143_model.py'),
         acceptance='기존 native/cache tolerance .125 및 greedy token 일치 유지. 변경 없음.'))
    if a.phase=='cache':
        import i143_generation_checks
        sys.argv=['i143_generation_checks.py','--name',name,'--cache-only']; i143_generation_checks.main()
    elif a.phase=='tech':
        import i143_tech
        i143_tech.run(argparse.Namespace(name=name))
    else:
        import i143_training_checks
        sys.argv=['i143_training_checks.py','--name',name]; i143_training_checks.main()


if __name__=='__main__':main()
