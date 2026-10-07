"""새 수치 경로의 원 기술 검사를 원본 변경 없이 실행한다."""
import report90_tech as C
from report90_stable_v2 import apply
from report86_common import sha
C.apply=apply
original_save=C.save
def save(path,data):
    if path.name=='protocol.json':
        data['source'].update({p:sha(p) for p in ['report90_stable_v2.py','report90_recovery_tech.py']})
    original_save(path,data)
C.save=save
if __name__=='__main__':C.main()
