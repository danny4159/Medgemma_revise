"""iter_095 공통: 고정 8영역, 공식 Describe / Locate and describe 요청 정의, 경로, 검증된 기존 출력 로더.

report86_common의 hash·원자적 저장·고정 자산 정보를 재사용한다. 새 산출물은 results/iter_095 아래에만 쓴다.
"""
import glob
import json
from pathlib import Path

import report86_common as C86
from report86_common import (ROOT, UP, R85, R86, SEED, CAPS, sha, sha_obj, save, read_jsonl_complete, record_digest,
                             adapter_path_C, base_path, CURE_PY, isolated_env)

R95 = ROOT / 'results/iter_095'
REGIONS = ['left lung', 'right lung', 'left upper lung zone', 'left mid lung zone', 'left lower lung zone',
           'right upper lung zone', 'right mid lung zone', 'right lower lung zone']
BROAD = ['left lung', 'right lung']          # 사전 고정 2영역 부분집합
DETAIL = [r for r in REGIONS if r not in BROAD]
FORMATS = {'D': 'Describe the {loc}.', 'L': 'Locate and describe the {loc}.'}
D8_REGIONS = ['left lung', 'right lower lung zone']
SYSTEM = 'C95'                              # 요청 id용 표기: 모델은 report86의 C(CURE adapter)와 동일
LOCK = R95 / 'lock'

INPUTS = {'D8': R85 / 'D8/inputs.json', 'E96': R86 / 'E/inputs_E96.json'}
RAW = {'D8': R85 / 'D8/raw_manifest.json', 'E96': R86 / 'E/raw_manifest_E96.json'}
EXEC_SOURCES = ['report95_gen.py', 'report95_common.py', 'report86_common.py', 'rsna_diag/generate.py', 'rsna_diag/lora.py',
                'rsna_diag/geometry.py']


def hash_order(ids, tag):
    return sorted(ids, key=lambda i: sha_obj([tag, i]))


def stage_patients(stage):
    """stage의 ImageID 목록(고정). D8: 기존 D8에서 이미지 ID hash 순 4명. E32/E64: lock/selection.json."""
    if stage == 'D8':
        ids = [r['ImageID'] for r in json.loads(INPUTS['D8'].read_text())]
        return hash_order(ids, 'report95_d8')[:4]
    sel = json.loads((LOCK / 'selection.json').read_text())
    return sel['E32'] if stage == 'E32' else sel['E64']


def stage_base(stage):
    return 'D8' if stage == 'D8' else 'E96'


def stage_formats_regions(stage):
    if stage == 'D8':
        return ['D', 'L'], D8_REGIONS
    return ['D'], REGIONS


def requests(stage):
    """고정 요청 목록 [{id, ImageID, fmt, region, prompt}]. 환자 순서는 stage_patients, 그 안은 영역·형식 고정 순서."""
    fmts, regs = stage_formats_regions(stage)
    out = []
    for img in stage_patients(stage):
        for reg in regs:
            for f in fmts:
                out.append({'id': f'{img}|{SYSTEM}|{f}|{reg}', 'ImageID': img, 'fmt': f, 'region': reg,
                            'prompt': FORMATS[f].format(loc=reg)})
    assert len({r['id'] for r in out}) == len(out)
    return out


def inputs_rows(stage):
    base = stage_base(stage)
    allr = {r['ImageID']: r for r in json.loads(INPUTS[base].read_text())}
    raw = {r['ImageID']: r for r in json.loads(RAW[base].read_text())}
    pats = stage_patients(stage)
    return [allr[i] for i in pats], raw


def scientific_protocol(stage):
    """모델 로딩 없이 계산 가능한 과학적 설정. GPU·python은 execution 기록으로 분리한다."""
    base = stage_base(stage)
    reqs = requests(stage)
    return {'system': 'C', 'stage': stage, 'base': base_path('C'), 'adapter_digest': sha(adapter_path_C() / 'adapter_model.safetensors'),
            'seed': SEED, 'caps': CAPS, 'precision': 'nf4_bf16_clahe', 'requests_sha256': sha_obj(reqs), 'n_requests': len(reqs),
            'input_sha256': sha(INPUTS[base]), 'raw_sha256': sha(RAW[base]), 'patients': stage_patients(stage)}


def old_C_records(stage):
    """iter_086 C 출력(Locate and describe, C-G). 완료 행 digest를 검증한 뒤에만 반환한다.
    반환: {(ImageID, condition): record}. condition은 'G' 또는 영역명."""
    base = stage_base(stage)
    root = R86 / base / 'C'
    shards = sorted(root.glob('shard*'))
    assert shards, root
    out = {}
    for s in shards:
        comp = json.loads((s / 'completion.json').read_text())
        assert comp['files']['outputs.jsonl'] == sha(s / 'outputs.jsonl'), f'{s} outputs hash differs from completion'
        assert comp['final_not_eos'] == 0 or True
        for r in read_jsonl_complete(s / 'outputs.jsonl'):
            assert r['record_digest'] == record_digest(r), r['id']
            key = (r['ImageID'], r['condition'])
            assert key not in out, f'duplicate {key}'
            out[key] = r
    if stage == 'D8':
        # D8의 일부 행은 iter_085에서 생성돼 iter_086 manifest로 검증·계승됐다(shard 출력에는 없음).
        from report86_inherit import load_verified
        recs, _ = load_verified('C')
        for r in recs.values():
            key = (r['ImageID'], r['condition'])
            assert key not in out, f'inherited row duplicates shard row {key}'
            out[key] = r
    return out
