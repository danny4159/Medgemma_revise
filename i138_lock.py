"""단계별 protocol 잠금(technical / main). main은 tests/technical_gate.json(passed=True, i138_gate.py가 단일 경로로 생성)을 gates에 포함하며 gate·평가 코드가 먼저 존재해야 한다."""
import sys, shutil
from pathlib import Path
from i138_common import RES, HERE, DATA, sha, read, save, now
import i138_run as R

CODE = ['i138_common.py', 'i138_spec.py', 'i134_spec.py', 'i138_data.py', 'i138_run.py', 'i138_lock.py', 'i138_eval.py', 'i138_tech.py', 'i138_gate.py', 'msd56_data.py',
        'i137_common.py', 'i137_spec.py', 'i137_data.py', 'i137_run.py']   # i137_*: 재사용 D24 증거 검증(verify_job)과 자료 재연결 의존성


def main(stage):
    code = {str(HERE / c): sha(HERE / c) for c in CODE}
    inputs = {str(p): sha(p) for p in [DATA / 'manifest.json', RES / 'requests/technical.json', RES / 'requests/main.json', RES / 'tests/boundary_check.json', RES / 'tests/cpu_tests.json',
                                       RES / 'tests/tensor_check_technical.json', RES / 'tests/tensor_check_main.json']}
    gates = {}
    if stage == 'main':
        g = RES / 'tests/technical_gate.json'; assert read(g)['passed'] is True, 'technical gate not passed'; gates[str(g)] = sha(g)
        assert (HERE / 'i138_eval.py').exists() and (HERE / 'i138_tech.py').exists() and (HERE / 'i138_gate.py').exists()
    mf = {}
    for p in sorted(Path(R.MODEL).iterdir()):
        r = p.resolve(); mf[str(r)] = dict(bytes=r.stat().st_size, sha256=sha(r))
    save(R.protocol_path(stage, new=True), dict(created_at=now(), stage=stage, config=R.config_for(stage), code=code, inputs=inputs, gates=gates, model_files=mf))
    print('locked', stage, len(code), 'code', len(mf), 'model files')


if __name__ == '__main__':
    main(sys.argv[1])
