"""iter_088 인계: 과거 결과는 읽고 새 경로에만 검증 기록을 쓴다."""
import datetime
import json
import subprocess
from pathlib import Path

import report87_eval as E
from report86_common import ROOT, R86, save, sha
from report86_view import load

OUT = ROOT / 'results/iter_088'
OLD = ROOT / 'results/iter_087'


def write_new(path, value):
    p = Path(path).resolve()
    if not p.is_relative_to(OUT.resolve()):
        raise ValueError('iter_088 밖 쓰기 거부')
    save(p, value)


def inputs():
    rows, reads, refs = load('E96')
    v1 = E.E1.parse_judgments((R86 / 'E96/judgments_E96_v2.txt').read_text(), rows, refs)
    return rows, reads, E.load_amend(), v1


def main():
    source = json.loads((OLD / 'source_manifest.json').read_text())
    checks = {}
    for group in ('inputs', 'plans'):
        for key, ent in source[group].items():
            checks[group + ':' + key] = sha(ROOT.parent / ent['path']) == ent['sha256']
    assert all(checks.values()), checks
    lock = json.loads((OLD / 'protocol_lock.json').read_text())
    drift = {p: {'locked': h, 'current': sha(ROOT / p)} for p, h in lock['files'].items() if sha(ROOT / p) != h}
    assert set(drift) == {'report87_eval.py'}, drift
    paths = sorted((OLD / 'judgments_parts').glob('*.txt'))
    rows, reads, amend, v1 = inputs()
    jud = E.parse_v3('\n'.join(p.read_text() for p in paths), rows, amend, reads, v1, subset=True)
    assert set(jud) == {r['ImageID'] for r in rows[:76]}
    logs = ROOT.parent / 'agent/runs/iter_087/claude_stream.jsonl'
    edits, nonjson = [], []
    for lineno, line in enumerate(logs.open(), 1):
        try:
            o = json.loads(line)
        except json.JSONDecodeError:
            nonjson.append({'line': lineno, 'prefix': line[:160]})
            continue
        if not isinstance(o, dict):
            continue
        msg = o.get('message', {})
        if not isinstance(msg, dict):
            continue
        content = msg.get('content', [])
        if not isinstance(content, list):
            continue
        for c in content:
            if not isinstance(c, dict) or c.get('type') != 'tool_use':
                continue
            z = c.get('input', {})
            p = z.get('file_path', '')
            if c.get('name') in ('Edit', 'Write') and (p.endswith('report87_eval.py') or 'amendment_02' in p):
                edits.append({'file': p, 'old': z.get('old_string'), 'new': z.get('new_string'), 'content': z.get('content')})
    assets = list(OLD.rglob('*')) + list(ROOT.glob('report87_*.py')) + [ROOT / 'test_report87_eval.py', logs]
    assets += [ROOT / p for p in ('report86_common.py', 'report86_eval.py', 'report86_view.py')]
    assets += [ROOT.parent / f'agent/runs/iter_{n}/plan.md' for n in ('086', '087', '088')]
    assets += [ROOT.parent / 'agent/runs/iter_087/checkpoint.json', ROOT.parent / 'agent/runs/iter_088/reuse_manifest.json']
    preserved = {str(p.relative_to(ROOT.parent)): sha(p) for p in assets if p.is_file()}
    write_new(OUT / 'handoff.json', {
        'time_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
        'status': '구조·출처 검사 통과; 의미 판정과 전체 검증은 미완료',
        'checks': checks, 'protocol_drift': drift, 'preserved': preserved,
        'partial_patients': len(jud), 'partial_outputs': sum(len(v) for v in jud.values()),
        'part_paths': [str(p.relative_to(ROOT)) for p in paths],
        'missing_indices': list(range(76, 96)), 'amendment_edits': edits, 'log_nonjson_lines': nonjson,
        'raters': {'inherited': 'Claude iter_087, unreviewed', 'new': 'Codex iter_088'},
        'new_gpu_requests': 0,
    })
    print('인계 출처 검사', len(checks), '부분 판정', len(jud), '명; 새 의미 판정 미실행')


if __name__ == '__main__':
    main()
