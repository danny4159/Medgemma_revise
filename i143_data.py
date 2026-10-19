"""iter_143: train-only DWI target 연결, 고정 선정과 선택 ZIP 반입.

자료 조회/ZIP 규약은 i141_preflight/select_download에서 계승한다.
원문에서 ADC와 비DWI 전역 음성 절만 삭제한다. 임상 사실을 보충하지 않는다.
"""
import argparse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import random
import re
import shutil
import struct
import time
import zlib

from i141_common import sha, now, read, save
from i141_preflight import IDS
from i141_select_download import get_range as inherited_get_range

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'results/iter_143'
OLD = ROOT / 'results/iter_141'
SOURCE = OLD / 'official/ISLES22/global_finding.json'
SPLIT = OLD / 'official/train_val_test_split.json'


def get_range(start, end):
    for attempt in range(4):
        try:
            return inherited_get_range(start, end)
        except (AssertionError, ConnectionError) as exc:
            save(OUT/'download_errors'/f'{time.time_ns()}.json',
                 dict(created_at=now(),start=start,end=end,attempt=attempt,error=str(exc)))
            if '429' not in str(exc) or attempt==3:
                raise
            time.sleep(60*(attempt+1))

# 출력/선정 전에 고정한 삭제 규칙. 남은 ADC나 비DWI 절은 자동 수용하지 않는다.
ADC = re.compile(r'(?:mixed high and low signals|low signals?|high signals?|low signal intensity|high signal intensity|hypointense) on (?:the )?(?:Apparent Diffusion Coefficient \(ADC\) sequence|ADC(?: sequence| images)?)(?:,? and |, )|(?:low|high) ADC signals?(?:,? and |, )|ADC low signal, ', re.I)
MIDLINE = re.compile(r'(?:[,;] ?(?:with |and )?(?:no |without )(?:a )?(?:shift|displacement|midline shift)[^.]*|\. (?:There is no|No|Midline structures)[^.]*|, no midline shift[^.]*)\.?$', re.I)


def transform(text):
    if not re.search(r'DWI|Diffusion Weighted Imaging', text):
        return None, [], 'DWI 명시 연결 없음'
    if text.startswith('No obvious abnormal'):
        q = 'No conspicuously abnormal high signal intensity on DWI.'
        if q not in text:
            return None, [], '음성 DWI 절 경계 미확인'
        a = text.index(q)
        return q, [{'start': a, 'end': a + len(q), 'quote': q}], None
    deletions = [(m.start(), m.end()) for m in ADC.finditer(text)]
    m = MIDLINE.search(text)
    if m:
        deletions.append((m.start(), m.end()))
    # 중첩 없는 원문 span을 보존한다. 고신호/저신호 혼합도 그대로 둔다.
    spans, cursor = [], 0
    for a, b in sorted(deletions):
        if a < cursor:
            return None, [], '삭제 경계 중첩'
        if a > cursor:
            spans.append({'start': cursor, 'end': a, 'quote': text[cursor:a]})
        cursor = b
    if cursor < len(text):
        spans.append({'start': cursor, 'end': len(text), 'quote': text[cursor:]})
    target = ''.join(s['quote'] for s in spans).strip()
    if re.search(r'ADC|midline|ventricles.*enlarged|infarct|acute|chronic|restriction', target, re.I):
        return None, spans, '비DWI 절 자동 삭제 불완전: 수동 연결 필요'
    return target, spans, None


def select():
    OUT.mkdir(parents=True, exist_ok=True)
    reports, split = read(SOURCE), read(SPLIT)['train']
    rows, excluded = [], []
    for key in sorted(k for k in split if k.startswith('sub-strokecase') and k.endswith('_dwi')):
        pid = key.split('_')[0]
        if pid in IDS:
            excluded.append({'key': key, 'reason': '기존 개발8명'})
            continue
        text = reports[key.removesuffix('_dwi')]
        target, spans, reason = transform(text)
        if reason:
            excluded.append({'key': key, 'reason': reason, 'original_text': text})
            continue
        # 양측 표기는 양쪽이 명시된 경우만. 나머지는 단측/비명시를 분리한다.
        bilateral = bool(re.search(r'bilateral|\bboth\b', target, re.I) or ('left' in target.lower() and 'right' in target.lower()))
        lat = 'bilateral' if bilateral else ('unilateral' if re.search(r'\bleft\b|\bright\b', target, re.I) else 'unspecified')
        distribution = 'multiple' if re.search(r'scattered|disseminated|multiple', target, re.I) else 'single_or_unspecified'
        signal = 'mixed' if re.search(r'high and low.*DWI|low signal on DWI', target, re.I) and 'high signal on DWI' in target else ('negative' if target.startswith('No ') else 'other')
        rows.append(dict(patient_id=pid, key=key, source_key=key.removesuffix('_dwi'), original_text=text,
                         target=target, retained_spans=spans, stratum=lat+'__'+distribution,
                         rare_signal=signal))
    assert len({r['patient_id'] for r in rows}) == len(rows)
    assert len(rows) >= 48, '계획상 적격48명 부족'
    rng = random.Random(17)
    groups = defaultdict(list)
    for r in rows:
        groups[r['stratum']].append(r)
    for g in groups.values():
        rng.shuffle(g)
    # 비례 할당 대신 층 순환: 드문 단일/비명시 유형을 편의상 버리지 않는다.
    ordered = []
    while any(groups.values()):
        for k in sorted(groups):
            if groups[k]:
                ordered.append(groups[k].pop())
    chosen = ordered[:48]
    # 명시 음성/혼합/저신호도 별도의 희귀 유형으로 앞서 포함한다.
    rare = [r for r in rows if r['rare_signal'] in ('mixed', 'negative') or 'low signal on DWI' in r['target']]
    for r in rare:
        if r not in chosen:
            replaced = next(x for x in reversed(chosen) if x not in rare)
            chosen[chosen.index(replaced)] = r
    rng.shuffle(chosen)
    # 6:2:4 주기를 네 번 사용하여 표본 역할을 고정한다.
    roles = ['T']*6 + ['V']*2 + ['E']*4
    for i, r in enumerate(chosen):
        r['split'] = roles[i % 12]
    result = dict(created_at=now(), seed=17, source_sha256=sha(SOURCE), split_sha256=sha(SPLIT),
                  code_sha256=sha(__file__), rules=dict(ADC=ADC.pattern, midline=MIDLINE.pattern),
                  eligible_n=len(rows), excluded=excluded, eligible=rows, selected=chosen,
                  split_counts=dict(Counter(r['split'] for r in chosen)),
                  note='선정 완료, target/항목의 의미 검토 및 새 영상 연결은 아직 미완료. E 출력 미개방.')
    save(OUT/'selection_candidates.json', result)
    print(json.dumps({k:result[k] for k in ('eligible_n','split_counts')}), flush=True)


def budget():
    chosen = read(OUT/'selection_candidates.json')['selected']
    ids = {r['patient_id'] for r in chosen}
    catalog = read(OLD/'range_catalog.json')
    picked = [x for x in catalog['entries'] if ids.intersection(Path(x['name']).parts)
              and x['name'].endswith(('_dwi.nii.gz','_dwi.json','_msk.nii.gz'))]
    assert len([x for x in picked if x['name'].endswith('_dwi.nii.gz')]) == 48
    # q/k/v/o rank16 FP32 adapter+Adam states, 3*16 epoch, no feature disk cache.
    params = 34*16*((2560+2048)+2*(2560+1024)+(2048+2560))
    checkpoint_bytes = params * 12 * 3 * 16
    raw_bytes = sum(x['bytes'] for x in picked)
    free = shutil.disk_usage(OUT).free
    result = dict(created_at=now(), free_bytes=free, selected_compressed_bytes=sum(x['compressed_bytes'] for x in picked),
                  selected_uncompressed_bytes=raw_bytes, lora_parameters_formula=params,
                  checkpoint_upper_bytes=checkpoint_bytes, disk_feature_cache=False,
                  png_and_logs_reserve_bytes=2*1024**3, safety_reserve_bytes=1024**3,
                  required_estimated_bytes=raw_bytes+checkpoint_bytes+3*1024**3,
                  feasible=free>raw_bytes+checkpoint_bytes+3*1024**3, entries=picked,
                  catalog_sha256=sha(OLD/'range_catalog.json'))
    save(OUT/'storage_budget.json', result)
    print(json.dumps({k:v for k,v in result.items() if k!='entries'}), flush=True)


def download():
    b = read(OUT/'storage_budget.json')
    assert b['feasible'], '저장 공간 계획 미충족'
    assert sha(OLD/'range_catalog.json') == b['catalog_sha256']
    start = time.monotonic()
    dest = OUT/'data_selected'
    def one(x):
        path = dest/x['name']
        record = OUT/'download_records'/(hashlib.sha256(x['name'].encode()).hexdigest()+'.json')
        if record.exists():
            r=read(record); assert sha(path)==r['sha256']; return r
        assert not path.exists(), '출처 미기록 부분 파일 보존: '+str(path)
        header, hr = get_range(x['header_offset'], x['header_offset']+29)
        h=struct.unpack('<4s5H3L2H',header)
        assert h[0]==b'PK\x03\x04' and not h[2]&1 and h[3]==x['compression']
        fn, ex=h[-2:]
        payload,pr=get_range(x['header_offset']+30,x['header_offset']+29+fn+ex+x['compressed_bytes'])
        assert payload[:fn].decode('utf-8' if h[2]&2048 else 'cp437')==x['name']
        data=zlib.decompress(payload[fn+ex:],-15) if x['compression']==8 else payload[fn+ex:]
        assert len(data)==x['bytes'] and zlib.crc32(data)==x['crc32']
        assert path.resolve().is_relative_to(dest.resolve())
        path.parent.mkdir(parents=True,exist_ok=True)
        with path.open('xb') as f: f.write(data)
        r=dict(member=x['name'],path=str(path),sha256=sha(path),crc32_verified=True,requests=[hr,pr])
        save(record,r)
        return r
    with ThreadPoolExecutor(max_workers=1) as pool:
        rows=list(pool.map(one,b['entries']))
    save(OUT/'download_complete.json',dict(created_at=now(),files=rows,elapsed_s=time.monotonic()-start,
         budget_sha256=sha(OUT/'storage_budget.json'),selected_crc_only=True))
    print('다운로드 완료',len(rows),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('command',choices=['select','budget','download'])
    globals()[p.parse_args().command]()
