"""단계별 protocol 잠금 (technical / main). main은 technical_gate.json(passed=True)을 gates에 포함해야 한다."""
import sys
from pathlib import Path
from i133_common import RES, HERE, sha, read, save, now
from i133_spec import CONFIG
from i133_run import MODEL, protocol_path

CODE = ['i133_common.py', 'i133_spec.py', 'i133_data.py', 'i133_run.py', 'i133_lock.py', 'mr123_data.py', 'i133_eval.py', 'i133_tech.py']


def main(stage):
    code = {str(HERE / c): sha(HERE / c) for c in CODE if (HERE / c).exists()}
    inputs = {str(RES / 'data_manifest.json'): sha(RES / 'data_manifest.json')}
    for s in ['technical', 'main']:
        inputs[str(RES / f'requests/{s}.json')] = sha(RES / f'requests/{s}.json')
    gates = {}
    if stage == 'main':
        g = RES / 'tests/technical_gate.json'
        assert read(g)['passed'] is True; gates[str(g)] = sha(g)
        assert (HERE / 'i133_eval.py').exists(), 'eval code must be locked before main generation'
    mf = {}
    for p in sorted(Path(MODEL).iterdir()):
        r = p.resolve(); mf[str(r)] = dict(bytes=r.stat().st_size, sha256=sha(r))
    save(protocol_path(stage), dict(created_at=now(), stage=stage, config=CONFIG, code=code, inputs=inputs, gates=gates, model_files=mf))
    print('locked', stage, len(code), 'code', len(mf), 'model files')


if __name__ == '__main__':
    main(sys.argv[1])
