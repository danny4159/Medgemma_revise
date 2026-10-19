"""진행 중 기술 출력 뒤 사전 512→1024 분기만 자동 실행한다."""
import os
import subprocess
import sys
import time
from i143_data import OUT
from i141_common import read,now
from i143_runtime import save


def main():
    for name in ['cap_S_512','cap_A_512']:
        result=OUT/'launch'/name/'result.json'
        while not result.exists(): time.sleep(15)
        assert read(result)['returncode']==0,name
    first=[read(OUT/'tests'/f'cap_{c}_512.json') for c in ['S','A']]
    cap=1024 if any(not r['eos'] for r in first) else 512
    # N이 최초 cap에 도달한 경우도 한 번만 공통 cap을 늘린다.
    pending=['S','A','N'] if cap==1024 else ['N']; active=[]
    try:
        while pending or active:
            for entry in list(active):
                rc=entry[1].poll()
                if rc is not None:
                    assert rc==0,(entry[0],rc); active.remove(entry)
            while pending and len(active)<2:
                cond=pending.pop(0); name=f'cap_{cond}_{cap}'
                cp=subprocess.Popen([sys.executable,'i143_launch.py','--name',name,'i143_cap.py','--condition',cond,'--cap',str(cap)])
                active.append((cond,cp)); time.sleep(15)
            time.sleep(15)
        if cap==512 and not read(OUT/'tests/cap_N_512.json')['eos']:
            cap=1024
            for group in [['S','A'],['N']]:
                active=[]
                for cond in group:
                    cp=subprocess.Popen([sys.executable,'i143_launch.py','--name',f'cap_{cond}_{cap}',
                                         'i143_cap.py','--condition',cond,'--cap',str(cap)])
                    active.append((cond,cp)); time.sleep(15)
                for cond,cp in active: assert cp.wait()==0,cond
                active=[]
        save(OUT/'tests/cap_completion.json',dict(created_at=now(),cap=cap,conditions=['S','A','N'],passed=True))
    finally:
        for _,cp in active:
            if cp.poll() is None: cp.terminate()
        for _,cp in active: cp.wait()


if __name__=='__main__':main()
