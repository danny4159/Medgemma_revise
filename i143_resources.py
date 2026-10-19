"""소유 감독기와 직접 자식의 OS 자원 기록. 실험 실행/판정에는 관여하지 않는다."""
import argparse
import json
import os
from pathlib import Path
import time
from i141_common import now,sha
from i143_runtime import save
from i143_data import OUT


def stat(pid):
    p=Path('/proc')/str(pid)
    raw=(p/'stat').read_text().rsplit(')',1)[1].split()
    fields={}
    for line in (p/'status').read_text().splitlines():
        key,_,value=line.partition(':')
        if key in ('VmRSS','VmHWM','VmSize','Threads'): fields[key]=value.strip()
    io={k:int(v) for k,v in (line.split(':',1) for line in (p/'io').read_text().splitlines())}
    return dict(pid=pid,start_ticks=int(raw[19]),cpu_user_ticks=int(raw[11]),
                cpu_system_ticks=int(raw[12]),status=fields,io=io)


def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--pid',type=int,required=True)
    ap.add_argument('--output-name',default='host_resources'); a=ap.parse_args()
    assert Path(a.output_name).name==a.output_name and a.output_name not in ('.','..')
    parent=Path('/proc')/str(a.pid)
    command=(parent/'cmdline').read_bytes().split(b'\0')
    assert any(Path(os.fsdecode(x)).name in ('i143_schedule.py','i143_confirm_schedule.py') for x in command)
    initial=stat(a.pid); d=OUT/a.output_name; d.mkdir(exist_ok=False)
    save(d/'start.json',dict(created_at=now(),source_sha256=sha(__file__),supervisor=initial,
         clock_ticks_per_second=os.sysconf('SC_CLK_TCK'),
         note='실행 도중 시작한 읽기 전용 감시. VmHWM과 I/O는 커널의 해당 프로세스 생애 누적값이며 과거 시계열을 복원한 것이 아님.'))
    samples=0
    with (d/'samples.jsonl').open('x') as f:
        while parent.exists():
            try:
                current=stat(a.pid)
                if current['start_ticks']!=initial['start_ticks']: break
                children=[int(x) for x in (parent/'task'/str(a.pid)/'children').read_text().split()]
                processes=[current]
                for pid in children:
                    try: processes.append(stat(pid))
                    except (FileNotFoundError,ProcessLookupError): pass
                mem={k:v.strip() for k,v in (s.split(':',1) for s in Path('/proc/meminfo').read_text().splitlines())
                     if k in ('MemAvailable','MemTotal','SwapTotal','SwapFree')}
                f.write(json.dumps(dict(created_at=now(),processes=processes,memory=mem,
                                       loadavg=Path('/proc/loadavg').read_text().strip()))+'\n'); f.flush(); samples+=1
            except (FileNotFoundError,ProcessLookupError): break
            time.sleep(15)
    save(d/'completion.json',dict(created_at=now(),samples=samples,
         samples_sha256=sha(d/'samples.jsonl'),meaning='감시 종료이며 실험 성공 판정이 아님'))


if __name__=='__main__': main()
