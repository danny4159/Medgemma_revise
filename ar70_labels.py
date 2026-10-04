"""iter_070 label table: RadGenome BraTS_GLI t2f report -> HIGH / MIXED_HIGH_LOW / excluded.

Rules fixed before any model output (plan.md section 1).
 - HIGH: explicit high/hyperintense lesion signal, no low component in the same lesion.
 - MIXED_HIGH_LOW: explicit high AND low (hypo) components of the lesion.
 - excluded: 'mixed'/'heterogeneous' without explicit high+low, reference-only target
   ('aforementioned', 'same lesions/locations'), no signal statement.
VAL_MANUAL is the manual review of every val t2f report (authoritative for the main evaluation);
auto_label() is the regex assistant, used for train (prior B) and as a cross-check on val.
"""
import json
import re
import sys

REV = '0348ba42fad134da57b50e736ba858a8e73eb086'
D = 'results/iter_070/data/radgenome/'

# manual decision per val case: (label, evidence span or exclusion reason)
VAL_MANUAL = {
    'BraTS-GLI-00012-000': ('MIXED_HIGH_LOW', 'Mixed high and low signal intensities of the lesion'),
    'BraTS-GLI-00184-000': ('MIXED_HIGH_LOW', 'the lesion ... demonstrates mixed high and low signal intensity'),
    'BraTS-GLI-00187-000': ('MIXED_HIGH_LOW', 'the lesion demonstrates mixed high and low signals'),
    'BraTS-GLI-00430-000': ('MIXED_HIGH_LOW', 'lesion exhibits mixed high and low signal intensity'),
    'BraTS-GLI-00456-000': ('HIGH', 'the lesion in the right frontal lobe appears hyperintense'),
    'BraTS-GLI-00590-000': ('EXCLUDED', 'only "mixed high signal intensity" (no explicit low component)'),
    'BraTS-GLI-00683-001': ('EXCLUDED', 'only "mixed high signal intensity" (no explicit low component)'),
    'BraTS-GLI-00725-001': ('MIXED_HIGH_LOW', 'mixed high and low signal intensity foci in bilateral frontal lobes and corpus callosum knee'),
    'BraTS-GLI-00772-000': ('MIXED_HIGH_LOW', 'lesion exhibits mixed high and low signal intensity'),
    'BraTS-GLI-00778-000': ('HIGH', 'the lesion in the left temporal lobe is hyperintense'),
    'BraTS-GLI-00801-000': ('MIXED_HIGH_LOW', 'mixed high and low signal intensities'),
    'BraTS-GLI-01063-000': ('EXCLUDED', 'only "mixed signal intensities" (no explicit high+low)'),
    'BraTS-GLI-01077-000': ('HIGH', 'lesion in the right parietal lobe shows hyperintense signal'),
    'BraTS-GLI-01105-000': ('MIXED_HIGH_LOW', 'lesion demonstrates mixed high and low signal intensities'),
    'BraTS-GLI-01106-000': ('EXCLUDED', 'target defined by reference to the T2W description (lesions at the same locations)'),
    'BraTS-GLI-01146-000': ('EXCLUDED', '"High mixed signal intensities" of "the same lesions" (reference target, no explicit low)'),
    'BraTS-GLI-01157-000': ('EXCLUDED', 'target is "the aforementioned lesion" (reference-only target)'),
    'BraTS-GLI-01175-000': ('EXCLUDED', '"hyperintense mixed signals" (no explicit low component)'),
    'BraTS-GLI-01286-000': ('EXCLUDED', 'only "mixed high signal intensity" (no explicit low component)'),
    'BraTS-GLI-01358-000': ('MIXED_HIGH_LOW', 'Mixed high and low signal intensity observed in the lesion'),
    'BraTS-GLI-01440-000': ('MIXED_HIGH_LOW', 'lesion shows mixed hyperintensity and hypointensity'),
    'BraTS-GLI-01456-000': ('HIGH', 'the lesion exhibits high signal intensity'),
    'BraTS-GLI-01524-000': ('MIXED_HIGH_LOW', 'mixed hyperintense and hypointense signal'),
}

REF = re.compile(r'aforementioned|same lesions?|same locations?|mentioned in the', re.I)
HIGH = re.compile(r'hyperintens|high (?:fl?air )?signal|high signal|high and low|high-signal', re.I)
LOW = re.compile(r'hypointens|low signal|and low|high and low|low (?:signal )?intensit', re.I)
MIXED_ONLY = re.compile(r'mixed|heterogene', re.I)


def auto_label(text):
    if REF.search(text):
        return 'EXCLUDED'
    first = re.split(r'(?<=[.])\s', text)[0] if text else ''
    s = first
    h, l = bool(HIGH.search(s)), bool(LOW.search(s))
    mixed_hl = bool(re.search(r'mixed (?:high|hyperintens\w*) and (?:low|hypointens\w*)|mixed hyperintens\w* and hypointens\w*', s, re.I))
    if mixed_hl or (h and l):
        return 'MIXED_HIGH_LOW'
    if h and not MIXED_ONLY.search(s):
        return 'HIGH'
    return 'EXCLUDED'


def load():
    sp = json.load(open(D + 'train_val_test_split.json'))
    mw = json.load(open(D + 'BraTS_GLI/modal_wise_finding.json'))
    return sp, mw


def case_of(k):
    return k.rsplit('-', 1)[0]


def main():
    sp, mw = load()
    out = {'revision': REV, 'val': {}, 'train_counts': {}, 'crosscheck': {}}
    val_t2f = sorted(k for k in sp['val'] if 'GLI' in k and k.endswith('t2f'))
    assert len(val_t2f) == 23 and {case_of(k) for k in val_t2f} == set(VAL_MANUAL)
    for k in val_t2f:
        lab, ev = VAL_MANUAL[case_of(k)]
        out['val'][case_of(k)] = {'key': k, 'label': lab, 'evidence': ev, 'report': mw[k], 'auto': auto_label(mw[k])}
    out['crosscheck'] = {c: v['auto'] for c, v in out['val'].items() if v['auto'] != v['label']}
    tr = sorted(k for k in sp['train'] if 'GLI' in k and k.endswith('t2f'))
    cnt = {'HIGH': 0, 'MIXED_HIGH_LOW': 0, 'EXCLUDED': 0}
    for k in tr:
        cnt[auto_label(mw[k])] += 1
    out['train_counts'] = cnt
    out['train_n'] = len(tr)
    out['prior_B'] = 'MIXED_HIGH_LOW' if cnt['MIXED_HIGH_LOW'] > cnt['HIGH'] else 'HIGH'
    vc = {}
    for v in out['val'].values():
        vc[v['label']] = vc.get(v['label'], 0) + 1
    out['val_counts'] = vc
    out['val_patients'] = sorted({c.split('-')[2] for c in out['val']})
    json.dump(out, open(sys.argv[1], 'w'), indent=1, ensure_ascii=False)
    print(json.dumps({k: out[k] for k in ['val_counts', 'train_counts', 'train_n', 'prior_B', 'crosscheck']}, indent=1))


if __name__ == '__main__':
    main()
