"""보존된 본실행 worker에 검증된 checkpoint/log 분리 경로를 연결하는 새 진입점."""
import argparse
from i142_common import RES,MODELS,ROOT,sha,save,now
from i142_safe_loader import config
import i142_worker as worker

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--patient',required=True)
    p.add_argument('--protocol',required=True)
    p.add_argument('--out',required=True)
    p.add_argument('--max-length',type=int,default=300)
    p.add_argument('--direct',action='store_true')
    p.add_argument('--equivalence',action='store_true')
    a=p.parse_args()
    cfg=config(a.out)
    worker.MODELS=RES/'model_view'
    assert str(worker.MODELS/'autorg')==cfg['seg_folder']
    assert str(worker.MODELS/'autorg/RG_v2')==cfg['llm_folder']
    assert (worker.MODELS/'gpt2pm').resolve()==(MODELS/'gpt2pm').resolve()
    worker.run(a)

if __name__=='__main__':
    main()
