"""E 생성 전 잠금: 표본·reference 사실·규약·평가기·생성 코드·모델/adapter digest·과학적 protocol digest를 hash로 기록한다. (새 파일, 덮어쓰기 거부)
python report86_lock_E.py <stage>   # E96 또는 E192x
"""
import json
import sys

from report86_common import ROOT, R86, SYSTEMS, STAGES, sha, sha_obj, save, scientific_protocol, expected_ids

FILES = ['report86_gen.py', 'report86_common.py', 'report86_launch.py', 'report86_merge.py', 'report86_inherit.py', 'report86_view.py',
         'report86_eval.py', 'report86_facts.py', 'report86_select.py', 'report86_build_E.py', 'report86_lock_v2.py', 'pg43_run.py',
         'rsna_diag/generate.py', 'rsna_diag/lora.py', 'rsna_diag/geometry.py']
DATA = ['E/selection_lock.json', 'E/selection_lock_v2.json', 'E/enumeration.json', 'E/extract_meta.json', 'E/visual_audit_E.json',
        'E/reference_facts_E_private.json', 'semantic_protocol.md', 'D8/judgments_D8.txt', 'D8/throughput_comparison.json',
        'inheritance_manifest.json', 'environment_state.json', 'tests/regression.json', 'tests/eval_fixtures.json']


def main():
    stage = sys.argv[1]
    rows = json.loads(STAGES[stage]['inputs'].read_text())
    sci = {s: scientific_protocol(s, stage) for s in SYSTEMS}
    lock = {'stage': stage, 'n_patients': len(rows), 'n_requests_expected': sum(len(expected_ids(rows, s)) for s in SYSTEMS),
            'code_sha256': {f: sha(ROOT / f) for f in FILES}, 'data_sha256': {f: sha(R86 / f) for f in DATA},
            'inputs_sha256': sha(STAGES[stage]['inputs']), 'raw_manifest_sha256': sha(STAGES[stage]['raw']),
            'scientific_protocol_digests': {s: sha_obj(v) for s, v in sci.items()},
            'adapters': {'B0': sci['B0']['adapter_digest'], 'C': sci['C']['adapter_digest']},
            'seed': 17, 'caps': [1024, 2048, 4096], 'hybrid_rule': 'region outputs (sorted official locations) concatenated, then GRG',
            'rule': 'E 생성 후에는 이 목록의 파일을 변경하지 않는다. 구현 오류 수정은 전 조건 동일 적용·원 파일 보존·별도 기록.'}
    save(R86 / stage / 'E_lock.json', lock)
    print(json.dumps({k: v for k, v in lock.items() if k in ('stage', 'n_patients', 'n_requests_expected', 'scientific_protocol_digests')}, indent=1))


if __name__ == '__main__':
    main()
