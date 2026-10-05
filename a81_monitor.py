"""a81 실행 자식의 CPU/RAM/I/O 표본과 종료를 보존하는 단순 wrapper."""
import argparse
import os
import subprocess
import sys
import time
import psutil
import a81_common as C


def run(dest, command):
    p=subprocess.Popen(command)
    samples=[]
    try:
        while p.poll() is None:
            rows=[]
            try: children=[psutil.Process(p.pid)]+psutil.Process(p.pid).children(recursive=True)
            except psutil.Error: children=[]
            for proc in children:
                try:
                    rows.append({'pid':proc.pid,'rss_bytes':proc.memory_info().rss,
                                 'cpu_s':sum(proc.cpu_times()[:2]),'io':proc.io_counters()._asdict()})
                except psutil.Error: pass
            samples.append({'time':time.time(),'host_cpu_percent':psutil.cpu_percent(),
                            'available_ram_bytes':psutil.virtual_memory().available,'children':rows})
            time.sleep(1)
        rc=p.wait()
        C.save(dest,{'command':command,'returncode':rc,'samples':samples,
                    'peak_total_rss_bytes':max((sum(r['rss_bytes'] for r in s['children']) for s in samples),default=0),
                    'note':'1초 표본; page cache와 I/O 누적량은 경합의 인과 증명이 아님.'})
        return rc
    finally:
        if p.poll() is None:
            p.terminate()
            try: p.wait(timeout=40)
            except subprocess.TimeoutExpired: p.kill(); p.wait()


if __name__=='__main__':
    ap=argparse.ArgumentParser(); ap.add_argument('--dest',required=True); ap.add_argument('command',nargs=argparse.REMAINDER)
    a=ap.parse_args(); cmd=a.command[1:] if a.command[:1]==['--'] else a.command
    sys.exit(run(a.dest,cmd))
