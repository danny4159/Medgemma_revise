"""보존된 학습 adapter에서 LoRA 행 수 통제의 효과만 비교한다."""
import report90_trained_check as C
from report90_stable_v2 import apply
from report86_common import sha,save

original=C.save
def save_link(path,value):
    if str(path).endswith('trained_protocol.json'):
        value=dict(value,numeric_amendment={p:sha(p) for p in ['report90_stable_v2.py',__file__]})
    return original(path,value)
C.apply=apply;C.save=save_link

if __name__=='__main__':C.main()
