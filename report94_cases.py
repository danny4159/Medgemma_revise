"""iter_094: analysis/summary.json의 검토 대상 사례(명시 모순·strict 변경)를 reference와 함께 출력(읽기 전용)."""
import json
from pathlib import Path

R=Path(__file__).resolve().parent/'results'
s=json.loads((R/'iter_094/analysis/summary.json').read_text())
refs=json.loads((R/'iter_090/semantic/V32_reference_v3.json').read_text())['rows']
def ref_text(i):
    return '; '.join(f"{a['id']}:{a['finding']}|{a['polarity']}|{a['certainty']}|{a['location']}|{a['attributes']}" for a in refs[i]['atoms'])
print('=== CONTRADICTION CASES')
for c in s['contradiction_cases']:
    if c['cond'].startswith('base') or True:
        print(c['cond'],c['index'],'|',repr(c['text']),'\n   contradicted:',c['claims'],'internal:',c['internal'],'\n   REF:',ref_text(c['index']))
print('=== CHANGED STRICT')
for c in s['changed_strict_cases']:
    print(c['comparison'],c['index'],'gained',c['gained'],'lost',c['lost'],'\n   A:',repr(c['text_a'][:300]),'\n   B:',repr(c['text_b'][:300]),'\n   REF:',ref_text(c['index']))
