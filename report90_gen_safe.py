"""report90_gen의 생성 수식은 유지하고 봉인 검증·소유권 있는 tail 복구를 보강한다."""
import argparse
import fcntl
import json
from pathlib import Path
import signal
import report90_gen as C
from report86_common import sha

original_protocol=C.protocol
original_verify=C.verify

def protocol(requests,checkpoint):
    value=original_protocol(requests,checkpoint);value['code']['report90_gen_safe.py']=sha(__file__)
    return value

def verify(out,requests,proto,workers):
    records,expected=original_verify(out,requests,proto,workers)
    cp=Path(out)/'completion.json'
    if cp.exists():
        completion=json.loads(cp.read_text());assert len(records)==len(expected)==completion['n']
        assert completion['protocol_digest']==C.sha_obj(proto)
        assert completion['files']=={str(Path(out)/f'worker_{s}.jsonl'):sha(Path(out)/f'worker_{s}.jsonl') for s in range(workers)}
    return records,expected

C.protocol=protocol;C.verify=verify;C.__file__=__file__

def launch(a):
    out=Path(a.out).resolve();out.relative_to(C.OUT);out.mkdir(parents=True,exist_ok=True)
    with (out/'launcher.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'completion.json').exists():verify(out,a.requests,protocol(a.requests,a.checkpoint),a.workers)
        else:
            from pg43_run import repair_tail
            for s in range(a.workers):
                with (out/f'worker_{s}.lock').open('a') as worker_lock:
                    fcntl.flock(worker_lock,fcntl.LOCK_EX|fcntl.LOCK_NB);repair_tail(str(out/f'worker_{s}.jsonl'))
    def stop(*args):raise KeyboardInterrupt('supervisor stopped; terminating owned children')
    signal.signal(signal.SIGTERM,stop)
    return C.launch(a)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('command',choices=['worker','launch']);p.add_argument('--requests',required=True);p.add_argument('--out',required=True)
    p.add_argument('--checkpoint');p.add_argument('--workers',type=int,default=2);p.add_argument('--shard',type=int,default=0);p.add_argument('--gpu');p.add_argument('--limit',type=int,default=0);p.add_argument('--peak-mib',type=int,default=10000)
    a=p.parse_args();raise SystemExit(C.worker(a) if a.command=='worker' else launch(a))
