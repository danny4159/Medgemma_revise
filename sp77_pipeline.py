"""iter_077 실행 orchestration: iter_076 sp75_pipeline의 후속(결과는 results/iter_077만).

변경: (1) 모든 자식 작업은 sp77_stage.run_stage(상태 파일 pending/running/completed/failed, 코드·출력 hash, stale 완료 거부)로 실행한다.
(2) GPU 배정은 허용 GPU 중 실제 여유가 큰 순서이며, 메모리 예약: 다른 프로세스 baseline + 이미 배정된 worker들의 예상 peak 합 + 새 worker 예상 peak
    + (worker 수)×2GiB 가 GPU 용량 이하일 때만 시작한다(현재 free 조회·고정 대기로 대체하지 않는다). nvidia-smi 실패는 '여유 있음'으로 해석하지 않는다.
(3) 자식 실패 시 새 작업을 더 시작하지 않고, 이미 살아 있는 독립 자식은 끝까지 관리한 뒤 비정상 종료한다. 종료 후 출력 완전성(verify)까지 확인한다.
단계 CLI: train | gen_v8 | extend | gen_e24 (select/lock/seal/eval 등은 sp76_select.py·sp75_eval.py·sp75_verify.py·sp75_cost.py)
"""
import argparse, json, os, sys, threading, time

import sp77_stage as S

OUT = 'results/iter_077'
STATE = f'{OUT}/state'
LEDGER = f'{OUT}/ledger.jsonl'
TRAIN = f'{OUT}/train'
GEN = f'{OUT}/gen'
LRS = {'F': ('2e-5', '2e-4'), 'R': ('2e-5', '2e-4')}
LOCK = f'{OUT}/eval/eval_lock.json'
MARGIN_MIB = 2048
CODE = ['sp77_pipeline.py', 'sp77_stage.py', 'sp75_train.py', 'sp75_gen.py', 'sp75_vlm.py', 'sp75_data.py', 'rsna_diag/train.py', 'rsna_diag/lora.py', 'rsna_diag/generate.py', 'rsna_diag/queue_lock.py']


def gpus():
    return os.environ.get('CUDA_VISIBLE_DEVICES', '0,1').split(',')


class Reserver:
    """GPU별 예약. used()는 nvidia-smi 전체 점유(MiB). baseline: 내 worker가 없을 때 관측한 다른 프로세스 점유."""

    def __init__(self, used_fn=None):
        self.used_fn = used_fn or S.gpu_used
        self.lock = threading.Lock()
        self.running = {g: [] for g in gpus()}   # [(name, est_mib)]
        self.baseline = {}

    def candidates(self):
        """허용 GPU를 (예약 후) 여유가 큰 순서로 [(gid, free_after_reservation_mib)]."""
        u = self.used_fn()   # 실패하면 예외 전파
        out = []
        for g in gpus():
            if not self.running[g]:
                self.baseline[g] = u[g]['used']
            proj = self.baseline[g] + sum(e for _, e in self.running[g])
            out.append((g, u[g]['total'] - proj, u[g]['total']))
        return sorted(out, key=lambda x: -x[1])

    def try_acquire(self, name, est_mib):
        with self.lock:
            for g, free, total in self.candidates():
                if free - est_mib - MARGIN_MIB * (len(self.running[g]) + 1) >= 0:   # baseline+Σ예상peak+새 peak+worker당 2GiB <= 용량
                    self.running[g].append((name, est_mib))
                    return g
            return None

    def release(self, g, name):
        with self.lock:
            self.running[g] = [x for x in self.running[g] if x[0] != name]


def run_jobs(jobs, tag, reserver=None):
    """jobs: [{'name','cmd'(--gpu 제외),'log','outputs','est_mib','verify'(optional callable)}]. 실패 시 SystemExit(자식은 끝까지 관리)."""
    rs = reserver or Reserver()
    pending, threads, failures, ledger_lock = list(jobs), [], [], threading.Lock()

    def work(j, gid):
        t0 = time.time()
        try:
            st = S.run_stage(STATE, j['name'], j['cmd'] + ['--gpu', gid], j['outputs'], CODE, gpu=gid, log=j['log'], verify=j.get('verify'))
            rec = {'tag': tag, 'name': j['name'], 'gpu': gid, 'rc': st.get('rc'), 'reused_completed_state': bool(st.get('reused')), 'wall_s': time.time() - t0,
                   'peak_gpu_used_mib_sampled': st.get('peak_gpu_used_mib'), 'est_mib': j['est_mib'], 'cmd': j['cmd']}
        except BaseException as e:
            failures.append((j['name'], repr(e)))
            rec = {'tag': tag, 'name': j['name'], 'gpu': gid, 'error': repr(e)[:500], 'wall_s': time.time() - t0}
        finally:
            rs.release(gid, j['name'])
        with ledger_lock:
            os.makedirs(os.path.dirname(LEDGER), exist_ok=True)
            open(LEDGER, 'a').write(json.dumps(rec) + '\n')

    while pending or any(t.is_alive() for t in threads):
        if pending and not failures:
            j = pending[0]
            if S.completed_valid(STATE, j['name'], CODE):
                pending.pop(0)
                st = S.read_state(STATE, j['name'])
                open(LEDGER, 'a').write(json.dumps({'tag': tag, 'name': j['name'], 'reused_completed_state': True, 'rc': st['rc']}) + '\n')
                continue
            g = rs.try_acquire(j['name'], j['est_mib'])
            if g is not None:
                pending.pop(0)
                os.makedirs(os.path.dirname(j['log']), exist_ok=True)
                th = threading.Thread(target=work, args=(j, g))
                th.start()
                threads.append(th)
                time.sleep(20)   # 새 worker의 점유가 올라온 뒤 다음 판단(예약이 주 근거이며 이 대기는 보조)
                continue
        elif pending and failures:
            pending = []   # 실패한 필수 자식 뒤에 새 작업을 시작하지 않는다
        time.sleep(5)
    [t.join() for t in threads]
    if failures:
        raise SystemExit(f'jobs failed: {failures}')


def traj_dir(v, lr):
    return f'{TRAIN}/{v}_lr{lr}'


def check_trained(v, lr, milestones):
    d = traj_dir(v, lr)
    for e in milestones:
        for f in (f'{d}/epoch_{e:02d}/val_ce.json', f'{d}/epoch_{e:02d}/adapter.pt'):
            if not os.path.exists(f):
                raise RuntimeError(f'{f} missing after training')
    if not os.path.exists(f'{d}/freeze_end.json'):
        raise RuntimeError(f'{d}: freeze_end.json missing (training did not complete)')
    n = json.load(open(f'{d}/freeze_end.json'))
    if not n.get('equals_start'):
        raise RuntimeError(f'{d}: non-LoRA digest changed')


def train_job(v, lr, epochs, est_mib, tag=''):
    d = traj_dir(v, lr)
    ms = [e for e in (8, 16, 32) if e <= epochs]
    return {'name': f'train_{v}_{lr}_to{epochs}', 'log': f'{OUT}/logs/train_{v}_{lr}{tag}.log', 'est_mib': est_mib,
            'cmd': [sys.executable, 'sp75_train.py', '--run-dir', d, '--variant', v, '--lr', lr, '--epochs', str(epochs), '--workers', '2'],
            'outputs': [f'{d}/freeze_end.json'] + [f'{d}/epoch_{e:02d}/val_ce.json' for e in ms], 'verify': lambda: check_trained(v, lr, ms)}


def gen_cmd(v, split, positions, adapter, out, worker=0, lock=None):
    c = [sys.executable, 'sp75_gen.py', '--variant', v, '--split', split, '--positions', positions, '--adapter', adapter, '--out-dir', out, '--worker', str(worker)]
    return c + (['--lock', lock] if lock else [])


def expected_count(split):
    import sp75_data as D
    return sum(1 for r in D.load_manifest()['rows'] if r['split'] == split and not r['excluded'] and (split != 'V8' or r['position_set'] == 'supervised'))


def count_out(d):
    n, ids = 0, set()
    for f in os.listdir(d) if os.path.isdir(d) else []:
        if f.startswith('gen_worker') and f.endswith('.jsonl'):
            for ln in open(f'{d}/{f}'):
                if ln.strip():
                    ids.add(json.loads(ln)['id'])
                    n += 1
    return n, len(ids)


def gen_job(name, v, split, positions, adapter, out, est_mib, lock=None):
    n = expected_count(split)

    def verify():
        tot, uniq = count_out(out)
        if tot != n or uniq != n:
            raise RuntimeError(f'{out}: {tot} records / {uniq} unique, expected {n}')
    return {'name': name, 'log': f'{OUT}/logs/{name}.log', 'est_mib': est_mib, 'cmd': gen_cmd(v, split, positions, adapter, out, lock=lock), 'outputs': [f'{out}/gen_worker0.jsonl'], 'verify': verify}


def cmd_train(a):
    jobs = [train_job(v, lr, a.epochs, a.est_mib) for v in a.variants.split(',') for lr in LRS[v]]
    run_jobs(jobs, 'train')


def cmd_gen_v8(a):
    jobs = []
    sel = json.load(open(f'{OUT}/select_v8.json')) if a.only_selected else None
    for v in a.variants.split(','):
        for lr in ((sel['selected'][v],) if sel else LRS[v]):
            for ep in a.epochs.split(','):
                out = f'{GEN}/V8/{v}_lr{lr}_ep{int(ep):02d}'
                jobs.append(gen_job(f'genV8_{v}_{lr}_{ep}', v, 'V8', 'supervised', f'{traj_dir(v, lr)}/epoch_{int(ep):02d}', out, a.est_mib))
    run_jobs(jobs, 'gen_v8')


def cmd_extend(a):
    sel = json.load(open(f'{OUT}/select_v8.json'))
    jobs = [train_job(v, sel['selected'][v], 32, a.est_mib, tag='_ext') for v in ('F', 'R') if sel['extend'][v]['extend_to_32']]
    if jobs:
        run_jobs(jobs, 'extend')


def cmd_gen_e24(a):
    lock = json.load(open(LOCK))
    jobs = [gen_job(f'genE24_{name}', v['variant'], 'E24', 'all', v.get('adapter_dir') or 'none', v['dir'], a.est_mib, lock=LOCK) for name, v in lock['vlm'].items()]
    run_jobs(jobs, 'gen_e24')


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest='c', required=True)
    t = sp.add_parser('train'); t.add_argument('--epochs', type=int, default=16); t.add_argument('--variants', default='F,R'); t.add_argument('--est-mib', type=int, default=12000)
    g = sp.add_parser('gen_v8'); g.add_argument('--epochs', default='8,16'); g.add_argument('--variants', default='F,R'); g.add_argument('--est-mib', type=int, default=11000); g.add_argument('--only-selected', action='store_true')
    e = sp.add_parser('extend'); e.add_argument('--est-mib', type=int, default=12000)
    ge = sp.add_parser('gen_e24'); ge.add_argument('--est-mib', type=int, default=11000)
    a = ap.parse_args()
    os.makedirs(f'{OUT}/logs', exist_ok=True)
    {'train': cmd_train, 'gen_v8': cmd_gen_v8, 'extend': cmd_extend, 'gen_e24': cmd_gen_e24}[a.c](a)


if __name__ == '__main__':
    main()
