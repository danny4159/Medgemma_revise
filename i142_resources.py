"""자기 supervisor와 자식의 CPU·RAM·I/O를 프로그램이 주기적으로 기록한다."""
import argparse
import time
import psutil
from i142_common import *

def main(a):
    parents=[p for p in psutil.process_iter(['pid','cmdline'])
             if any(Path(arg).name==a.program for arg in (p.info['cmdline'] or [])) and p.pid!=os.getpid()]
    assert len(parents)==1, [(p.pid,p.cmdline()) for p in parents]
    parent=parents[0]
    rows=[]
    while parent.is_running() and parent.status()!=psutil.STATUS_ZOMBIE:
        processes=[]
        for p in [parent]+parent.children(recursive=True):
            try:
                io=p.io_counters()
                mem=p.memory_info()
                cpu=p.cpu_times()
                processes.append({'pid':p.pid,'rss':mem.rss,'vms':mem.vms,'cpu_s':cpu.user+cpu.system,
                    'read_bytes':io.read_bytes,'write_bytes':io.write_bytes,'threads':p.num_threads()})
            except psutil.Error:
                continue
        rows.append({'created_at':now(),'processes':processes,'available_ram':psutil.virtual_memory().available,
                     'loadavg':os.getloadavg()})
        time.sleep(2)
    save(Path(a.out),{'supervisor_pid':parent.pid,'samples':rows})
    print({'samples':len(rows),'path':a.out})

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--program',required=True)
    p.add_argument('--out',required=True)
    main(p.parse_args())
