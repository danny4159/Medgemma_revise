"""iter_077 단계 실행 상태 관리 (pending/running/completed/failed, 원자적 기록, stale 완료 거부, 자식 반환값 전파).

state 파일: <state_dir>/<stage>.json  {status, cmd, rc, code_sha, outputs{path: sha256}, pid, pid_start, ts_start, ts_end, gpu, peak_gpu_used_mib, wall_s}
- completed 재사용 조건: 기록된 code_sha가 현재 코드와 같고 모든 outputs 파일의 sha256가 기록과 같다. 하나라도 다르면 stale로 보고 재실행한다(기존 파일 덮어쓰기 금지는 호출자가 새 경로 사용).
- running 상태 기록이 있고 그 pid(+시작 tick)가 살아 있으면 중복 시작하지 않고 예외를 낸다. 죽었으면 failed(stale-running)로 기록 후 재실행한다.
- 자식 rc != 0 이면 StageFailed를 일으킨다. 호출 측은 이를 잡아 부모 프로세스를 비정상 종료시킨다.
"""
import hashlib, json, os, subprocess, threading, time


class StageFailed(RuntimeError):
    pass


def sha_file(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(1 << 22), b''):
            h.update(b)
    return h.hexdigest()


def code_sha(files):
    return {f: sha_file(f) for f in files}


def _atomic(obj, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + f'.tmp{os.getpid()}'
    json.dump(obj, open(tmp, 'w'), indent=1, default=str)
    os.replace(tmp, path)


def _pid_start(pid):
    try:
        return open(f'/proc/{pid}/stat').read().split()[21]
    except Exception:
        return None


def read_state(state_dir, name):
    p = os.path.join(state_dir, name + '.json')
    return json.load(open(p)) if os.path.exists(p) else None


def completed_valid(state_dir, name, code_files):
    st = read_state(state_dir, name)
    if not st or st.get('status') != 'completed' or st.get('rc') != st.get('expect_rc', 0):
        return False
    if st.get('code_sha') != code_sha(code_files):
        return False
    for p, h in st.get('outputs', {}).items():
        if not os.path.exists(p) or sha_file(p) != h:
            return False
    return bool(st.get('outputs'))


_gpu_lock = threading.Lock()


def gpu_used():
    out = subprocess.check_output(['nvidia-smi', '--query-gpu=index,uuid,memory.used,memory.total', '--format=csv,noheader,nounits']).decode().strip().splitlines()
    res = {}
    for ln in out:
        i, u, used, tot = [x.strip() for x in ln.split(',')]
        res[i] = {'used': int(used), 'total': int(tot), 'uuid': u}
    return res


def run_stage(state_dir, name, cmd, outputs, code_files, gpu=None, log=None, expect_rc=0, extra=None, verify=None):
    """cmd 실행. outputs: 완료로 인정하려면 존재해야 하는 파일 목록. expect_rc: 의도적 중단 시험은 비0 코드를 기대할 수 있다.
    반환: state dict. 실패 시 StageFailed."""
    if completed_valid(state_dir, name, code_files):
        st = read_state(state_dir, name)
        st['reused'] = True
        return st
    old = read_state(state_dir, name)
    if old and old.get('status') == 'running':
        pid, ps = old.get('pid'), old.get('pid_start')
        if pid and _pid_start(pid) == ps and ps is not None:
            raise StageFailed(f'stage {name} owned by live pid {pid}')
        old['status'], old['note'] = 'failed', 'stale-running (owner not alive)'
        _atomic(old, os.path.join(state_dir, name + '.stale.json'))
    st = {'stage': name, 'status': 'running', 'cmd': cmd, 'gpu': gpu, 'code_sha': code_sha(code_files), 'ts_start': time.time(), 'pid': os.getpid(), 'pid_start': _pid_start(os.getpid()),
          'expect_rc': expect_rc, **(extra or {})}
    _atomic(st, os.path.join(state_dir, name + '.json'))
    os.makedirs(os.path.dirname(log), exist_ok=True) if log else None
    p = subprocess.Popen(cmd, stdout=open(log, 'a') if log else None, stderr=subprocess.STDOUT)
    peak = 0
    while p.poll() is None:
        try:
            u = gpu_used()
            if gpu is not None:
                peak = max(peak, max(v['used'] for k, v in u.items() if v['uuid'] == gpu or k == gpu))
        except Exception:
            pass
        time.sleep(5)
    st.update({'rc': p.returncode, 'ts_end': time.time(), 'wall_s': time.time() - st['ts_start'], 'peak_gpu_used_mib': peak})
    missing = [o for o in outputs if not os.path.exists(o)]
    vprob = None
    if p.returncode == expect_rc and not missing and verify is not None:
        try:
            verify()
        except BaseException as e:
            vprob = repr(e)[:400]
            st['verify_error'] = vprob
    if p.returncode == expect_rc and not missing and vprob is None:
        st['status'] = 'completed'
        st['outputs'] = {o: sha_file(o) for o in outputs}
        if expect_rc != 0:
            st['rc_matches_expected_nonzero'] = True
            st['rc'] = p.returncode
    else:
        st['status'] = 'failed'
        st['missing_outputs'] = missing
    _atomic(st, os.path.join(state_dir, name + '.json'))
    if st['status'] != 'completed':
        raise StageFailed(f'stage {name} rc={p.returncode} (expected {expect_rc}) missing={missing} verify_error={vprob}')
    return st
