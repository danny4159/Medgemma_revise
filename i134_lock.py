"""단계별 protocol 잠금(technical / technical2048 / main). main은 tests/technical_gate.json(passed=True)을 gates에 포함하며 평가 코드가 먼저 존재해야 한다.
finalize_gate: 기술 gate 결과(technical_gate_<stage>.json)를 main이 읽는 technical_gate.json으로 확정한다(덮어쓰기 금지)."""
import sys, shutil
from pathlib import Path
from i134_common import RES, HERE, DATA, sha, read, save, now
import i134_run as R

CODE = ['i134_common.py', 'i134_spec.py', 'i134_fetch.py', 'i134_data.py', 'i134_run.py', 'i134_lock.py', 'i134_eval.py', 'mr123_data.py']


def finalize_gate(stage):
    g = read(RES / ('tests/technical_gate_%s.json' % stage)); assert g['passed'] is True
    save(RES / 'tests/technical_gate.json', dict(g, source=str(RES / ('tests/technical_gate_%s.json' % stage))))
    print('gate finalized', stage, g['main_max_new_tokens'])


def main(stage):
    code = {str(HERE / c): sha(HERE / c) for c in CODE}
    inputs = {str(p): sha(p) for p in [DATA / 'data_manifest_v2.json', DATA / 'selection_v2.json', DATA / 'order.json', RES / 'requests/technical_v2.json', RES / 'requests/main_v2.json']}
    gates = {}
    if stage == 'main':
        g = RES / 'tests/technical_gate.json'; assert read(g)['passed'] is True; gates[str(g)] = sha(g)
        assert (HERE / 'i134_eval.py').exists()
    mf = {}
    for p in sorted(Path(R.MODEL).iterdir()):
        r = p.resolve(); mf[str(r)] = dict(bytes=r.stat().st_size, sha256=sha(r))
    save(R.protocol_path(stage, new=True), dict(created_at=now(), stage=stage, config=R.config_for(stage), code=code, inputs=inputs, gates=gates, model_files=mf))
    print('locked', stage, len(code), 'code', len(mf), 'model files')


if __name__ == '__main__':
    if sys.argv[1] == 'finalize_gate': finalize_gate(sys.argv[2])
    else: main(sys.argv[1])
