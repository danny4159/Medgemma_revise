"""iter_087 source manifest: iter_086 불변 입력·기준 계획·코드 SHA를 연결한다(읽기 전용, 새 파일만 쓴다).
python report87_manifest.py
기존 iter_086 무결성 검증(report86_merge: 3,456 행 digest·completion)은 입력 SHA가 불변이면 재사용한다. 여기서는 SHA만 대조한다."""
import subprocess

from report86_common import ROOT, R86, save, sha

R87 = ROOT / 'results/iter_087'
AGENT = ROOT.parent / 'agent/runs'
EXPECTED = {'iter_086': '26c54de277676324b2942f1ac52647ef67ac8c04e04e36f1202e5bd7014126d7',
            'iter_085': '5663189557a03e3e30b620dbb2202fd86b754ca9b2eebbe6eeb6fadffc962f2f',
            'iter_084': '42334bc910f7abbb26e27f60696b59b5d2a974d6143fbe2aed153e08c315fefd'}


def main():
    head = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    srcs = {
        'readings': R86 / 'E96/readings.jsonl', 'merge_summary': R86 / 'E96/merge_summary.json', 'E_lock': R86 / 'E96/E_lock.json',
        'E_lock_amendment': R86 / 'E96/E_lock_amendment.json', 'blind_key_private': R86 / 'E96/blind_key_private.json',
        'reference_facts_E_private': R86 / 'E/reference_facts_E_private.json', 'inputs_E96': R86 / 'E/inputs_E96.json',
        'raw_manifest_E96': R86 / 'E/raw_manifest_E96.json', 'judgments_v1': R86 / 'E96/judgments_E96_v2.txt',
        'corrections_v2': R86 / 'E96/corrections_v2.json', 'eval_v1_report': R86 / 'E96/eval/report.json',
        'eval_v2_report': R86 / 'E96/eval_v2/report.json', 'recheck_sample': R86 / 'E96/recheck_sample.json',
        'semantic_protocol_v1': R86 / 'semantic_protocol.md', 'cost': R86 / 'E96/cost.json', 'inheritance_manifest': R86 / 'inheritance_manifest.json',
    }
    plans = {'iter_%03d_plan' % n: AGENT / ('iter_%03d/plan.md' % n) for n in (84, 85, 86, 87)}
    code = {p.name: sha(p) for p in sorted(ROOT.glob('report86_*.py')) + [ROOT / 'test_report86_eval.py', ROOT / 'test_report86.py']}
    out = {'research_head': head,
           'inputs': {k: {'path': str(v.relative_to(ROOT.parent)), 'sha256': sha(v)} for k, v in srcs.items()},
           'plans': {k: {'path': str(v.relative_to(ROOT.parent)), 'sha256': sha(v)} for k, v in plans.items()},
           'iter_086_code_sha256': code, 'expected_plan_sha256': EXPECTED}
    for n, exp in EXPECTED.items():
        assert out['plans'][n + '_plan']['sha256'] == exp, n
    save(R87 / 'source_manifest.json', out)
    print('ok', head, len(srcs), len(code))


if __name__ == '__main__':
    main()
