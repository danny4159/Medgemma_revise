"""iter_093: 저장된 T512/V64 target, 네 trajectory의 V64 환자별 NLL, 동일 V32 생성·판정의 연결 분석.
신규 학습·생성·GPU 없음. 결과는 results/iter_093/ 새 경로에만 쓴다(기존 파일 덮어쓰기 거부)."""
import hashlib, json, re, sys, time
from collections import Counter, defaultdict
from pathlib import Path
import numpy as np
import report93_fixtures as FX
import report93_sens as SENS

ROOT = Path(__file__).resolve().parent
I90 = ROOT / 'results/iter_090'
REC = I90 / 'recovery'
OUT = ROOT / 'results/iter_093/main'  # results/iter_093/*.json(root)은 개발 중 1회 실행본으로 보존
EPOCHS = (1, 2, 4, 6)
LRS = ('0.0001', '0.0002')
MODES = ('R', 'G')
SEED = 9301
NB = 10000


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def jl(p):
    return json.loads(Path(p).read_text())


def save(name, obj):
    p = OUT / name
    assert not p.exists(), f'refuse overwrite {p}'
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + '.tmp')
    tmp.write_text(json.dumps(obj, indent=1, ensure_ascii=False))
    tmp.rename(p)


# ---------------------------------------------------------------- 1. 입력 고정
def inputs():
    T = jl(I90 / 'data/T512/manifest.json')
    V = jl(I90 / 'data/V64/manifest.json')
    V32 = jl(I90 / 'data/V32/manifest.json')
    traj = {}
    for m in MODES:
        for lr in LRS:
            run = REC / f'train/{m}_lr{lr}'
            cfg = jl(run / 'config.json')
            assert cfg['val_sha'] == sha(I90 / 'data/V64/manifest.json'), 'val_sha mismatch'
            assert cfg['train_sha'] == sha(I90 / 'data/T512/manifest.json'), 'train_sha mismatch'
            assert cfg['patient_ids'] == sorted(r['PatientID'] for r in T), 'train id mismatch'
            assert cfg['mode'] == m and str(cfg['lr']) == str(float(lr)), (cfg['mode'], cfg['lr'])
            vals = {}
            for e in EPOCHS:
                v = jl(run / f'validation_{e:02d}.json')
                assert v['n'] == 64 and len(v['per_patient']) == 64 and v['epoch'] == e and v['state_preserved'] is True
                assert abs(float(np.mean(v['per_patient'])) - v['report_nll']) < 1e-9
                vals[e] = v
            traj[(m, lr)] = dict(cfg=cfg, val=vals)
    return T, V, V32, traj


def input_manifest(T, V, V32, traj):
    files = {}
    def add(p):
        files[str(Path(p).resolve().relative_to(ROOT))] = sha(p)
    for n in ('T512', 'V64', 'V32'):
        add(I90 / f'data/{n}/manifest.json')
    for p in ('semantic/V32_reference_v3.json', 'data/selection_lock.json'):
        add(I90 / p)
    for p in ('stage_decision_rules.json', 'selection/final.json', 'decisions/expand_epoch6.json',
              'decisions/expand_epoch6_semantic_confirmation.json', 'decisions/grounding_evidence_check.json'):
        add(REC / p)
    for (m, lr), t in traj.items():
        run = REC / f'train/{m}_lr{lr}'
        add(run / 'config.json')
        for e in EPOCHS:
            add(run / f'validation_{e:02d}.json')
        add(run / 'complete_06.json')
        add(run / 'verified_06.json')
    for e in (2, 6):
        add(REC / f'semantic/epoch{e}/eval/per_output.json')
        add(REC / f'semantic/epoch{e}/eval/report.json')
        for m in MODES:
            for lr in LRS:
                add(REC / f'validation/epoch{e}/{m}_lr{lr}_report/worker_0.jsonl')
    add(REC / 'validation/epoch2/base_report/worker_0.jsonl')
    for p in ('report90_select.py', 'report90_recovery_train.py', 'report90_train.py', 'report89_model.py', 'report93_fixtures.py', 'report93_sens.py'):
        add(ROOT / p)
    return files


# ---------------------------------------------------------------- 2. target 구성
GENERIC = [r'no (other )?(significant|relevant) (radiological )?findings', r'no findings( of pathological significance)?', r'within normal limits',
           r'no radiological changes', r'no (other )?findings', r'no other significant radiological findings',
           r'no (other )?relevant radiological (findings|alterations)', r"no pathological findings for the patient's age"]
UNCERT = re.compile(r'\b(possible|probable|probably|suggest\w*|may|might|could|doubtful|cannot be excluded|apparent|suspicious|likely|questionable|compatible)\b', re.I)
NEG = re.compile(r'\b(no|not|without|free|absence)\b', re.I)


def retained_sentences(row):
    ex = set()
    for item in row['excluded_sentences']:
        ex.add(item[0] if isinstance(item, (list, tuple)) else item)
    return [s for s in row['findings'] if s['source_index'] not in ex]


def classify_patient(row):
    sents = retained_sentences(row)
    ab = [s for s in sents if s['abnormal']]
    nm = [s for s in sents if not s['abnormal']]
    if not ab:
        c = 'normal_only'
    elif not nm:
        c = 'abnormal_only'
    else:
        c = 'abnormal_plus_normal'
    return c, sents, ab, nm


def is_generic(s):
    t = s.lower().rstrip('. ').strip()
    return any(re.fullmatch(g, t) for g in GENERIC)


def target_composition(rows):
    out = dict(n=len(rows), patient_class=Counter(), stratum=Counter(), generic_normal_sentence=0, specific_normal_sentence=0,
               abnormal_sentence=0, abnormal_with_uncertain=0, abnormal_with_location=0, abnormal_with_box=0,
               words_abnormal=0, words_normal=0, report_match_fail=0, excluded_sentences=0, patients_with_exclusion=0)
    phr = Counter()
    label_pat = defaultdict(set)
    per = {}
    for r in rows:
        c, sents, ab, nm = classify_patient(r)
        out['patient_class'][c] += 1
        out['stratum'][r['stratum']] += 1
        gen = sum(is_generic(s['sentence_en']) for s in nm)
        out['generic_normal_sentence'] += gen
        out['specific_normal_sentence'] += len(nm) - gen
        out['abnormal_sentence'] += len(ab)
        out['abnormal_with_uncertain'] += sum(bool(UNCERT.search(s['sentence_en'])) for s in ab)
        out['abnormal_with_location'] += sum(bool(s['locations']) for s in ab)
        out['abnormal_with_box'] += sum(bool(s['boxes']) for s in ab)
        out['words_abnormal'] += sum(len(s['sentence_en'].split()) for s in ab)
        out['words_normal'] += sum(len(s['sentence_en'].split()) for s in nm)
        ex = r['excluded_sentences']
        out['excluded_sentences'] += len(ex)
        out['patients_with_exclusion'] += bool(ex)
        if ' '.join(s['sentence_en'] for s in sents).strip() != r['report'].strip():
            out['report_match_fail'] += 1
        for s in nm:
            phr[s['sentence_en'].strip().lower()] += 1
        for s in ab:
            for lab in s['labels']:
                label_pat[lab].add(r['PatientID'])
        per[r['PatientID']] = dict(cls=c, n_abnormal=len(ab), n_normal=len(nm), n_generic=gen)
    out['patient_class'] = dict(out['patient_class'])
    out['stratum'] = dict(out['stratum'])
    out['top_normal_phrases'] = phr.most_common(12)
    out['n_distinct_normal_phrases'] = len(phr)
    lp = sorted(((k, len(v)) for k, v in label_pat.items()), key=lambda x: -x[1])
    out['label_patient_exposure_top15'] = lp[:15]
    out['n_distinct_labels'] = len(lp)
    out['labels_seen_in_le2_patients'] = sum(1 for _, n in lp if n <= 2)
    out['word_share_normal'] = out['words_normal'] / max(1, out['words_normal'] + out['words_abnormal'])
    return out, per


# ---------------------------------------------------------------- 3. NLL
def nll_tables(V, traj, vpc):
    vid = [r['PatientID'] for r in V]
    grp = np.array([vpc[p]['cls'] == 'normal_only' for p in vid])
    arr = {k: np.array([t['val'][e]['per_patient'] for e in EPOCHS]) for k, t in traj.items()}  # [epoch, patient]
    tab = {}
    for (m, lr), a in arr.items():
        tab[f'{m}_lr{lr}'] = dict(
            overall={str(e): float(a[i].mean()) for i, e in enumerate(EPOCHS)},
            normal_only={str(e): float(a[i][grp].mean()) for i, e in enumerate(EPOCHS)},
            abnormal_containing={str(e): float(a[i][~grp].mean()) for i, e in enumerate(EPOCHS)},
            stored_report_nll={str(e): traj[(m, lr)]['val'][e]['report_nll'] for e in EPOCHS})
    # 선택 재현: 모드별 epoch6 NLL 최소 LR(동률 낮은 LR) -> 공통 epoch NLL 합 최소(동률 이른 epoch)
    sel = {}
    for m in MODES:
        sel[m] = min(LRS, key=lambda lr: (traj[(m, lr)]['val'][6]['report_nll'], float(lr)))
    common = min(EPOCHS, key=lambda e: (sum(traj[(m, sel[m])]['val'][e]['report_nll'] for m in MODES), e))
    final = jl(REC / 'selection/final.json')
    reproduced = dict(lr=sel, common_epoch=common,
                      matches_final=all(str(final['selected'][m]['lr']) == str(float(sel[m])) for m in MODES) and final['common_epoch'] == common)
    # 사후 민감도(선택 파일은 바꾸지 않음): 모든 LR x epoch 중 모드별 NLL 최소, 군별 최소
    alt = {}
    for m in MODES:
        best = min(((lr, e) for lr in LRS for e in EPOCHS), key=lambda x: (traj[(m, x[0])]['val'][x[1]]['report_nll'], x[1], float(x[0])))
        alt[m] = dict(global_min_overall=best)
        for name, mask in (('normal_only', grp), ('abnormal_containing', ~grp)):
            b = min(((lr, e) for lr in LRS for e in EPOCHS), key=lambda x: (arr[(m, x[0])][EPOCHS.index(x[1])][mask].mean(), x[1], float(x[0])))
            alt[m][f'min_{name}'] = b
    # 군 분해: epoch1→6 변화
    dec = {}
    for (m, lr), a in arr.items():
        d = a[3] - a[0]
        dec[f'{m}_lr{lr}'] = dict(delta_6_minus_1_normal_only=float(d[grp].mean()), delta_6_minus_1_abnormal=float(d[~grp].mean()),
                                  n_normal_only=int(grp.sum()), n_abnormal=int((~grp).sum()))
    return tab, reproduced, alt, dec, arr


# ---------------------------------------------------------------- 4. V32 생성
def v32_outputs():
    po = {}
    for e in (2, 6):
        for x in jl(REC / f'semantic/epoch{e}/eval/per_output.json'):
            if x['condition'] == 'base_report' and e == 6:
                raise AssertionError('base at epoch6 unexpected')
            key = ('base' if x['condition'] == 'base_report' else x['condition'].replace('_report', ''), 0 if x['condition'] == 'base_report' else e)
            assert (key, x['image_id']) not in po
            po[(key, x['image_id'])] = x
    return po


def raw_text():
    txt = {}
    spec = [(('base', 0), REC / 'validation/epoch2/base_report')]
    for e in (2, 6):
        for m in MODES:
            for lr in LRS:
                spec.append(((f'{m}_lr{lr}', e), REC / f'validation/epoch{e}/{m}_lr{lr}_report'))
    for key, d in spec:
        for line in (d / 'worker_0.jsonl').read_text().splitlines():
            r = json.loads(line)
            iid = r['id'].split('|')[0]
            assert (key, iid) not in txt
            txt[(key, iid)] = r
    return txt


def patient_view(po, txt, ref_rows, V32):
    ids = [r['ImageID'] for r in V32]
    ref = {r['id']: r for r in ref_rows}
    keys = sorted({k for k, _ in po})
    out = {}
    for k in keys:
        rows = []
        for iid in ids:
            x = po[(k, iid)]
            r = ref[iid]
            pos_def = [a['id'] for a in r['atoms'] if a['polarity'] == 'positive' and a['certainty'] == 'definite']
            strict = sorted({m['ref'] for m in x['matches'] if m['status'] == 'strict'})
            typeo = sorted({m['ref'] for m in x['matches'] if m['status'] in ('strict', 'type_only')})
            pos_claims = [c for c in x['claims'] if c['polarity'] == 'positive']
            t = txt[(k, iid)]
            rows.append(dict(image_id=iid, patient=x['patient'], abnormal=x['abnormal'], positive_n=x['positive_n'], pos_def_ref=pos_def,
                             strict_atoms=strict, type_atoms=typeo, strict_recall=x['strict_recall'], type_recall=x['type_recall'],
                             n_pos_claims=len(pos_claims), n_neg_claims=len(x['claims']) - len(pos_claims),
                             normal_only_output=(len(pos_claims) == 0), non_eos=x['non_eos'], contradiction=x['contradiction'],
                             ended_eos=bool(t['attempts'][-1]['ended_eos']) if isinstance(t['attempts'], list) else None,
                             text_words=len(t['text'].split())))
        out[k] = rows
    return out


def recall_of(rows):
    el = [r for r in rows if r['positive_n']]
    return float(np.mean([r['strict_recall'] for r in el])) if el else float('nan')


def boot(d, rng):
    d = np.asarray(d, float)
    n = len(d)
    bs = np.array([d[rng.integers(0, n, n)].mean() for _ in range(NB)])
    loo = [float(np.delete(d, i).mean()) for i in range(n)]
    return dict(mean=float(d.mean()), ci95=[float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5))], n=n,
                loo_min=min(loo), loo_max=max(loo), n_up=int((d > 0).sum()), n_down=int((d < 0).sum()), n_zero=int((d == 0).sum()))


def rank(x):
    x = np.asarray(x, float)
    o = np.argsort(x, kind='mergesort')
    r = np.empty(len(x))
    i = 0
    while i < len(x):
        j = i
        while j + 1 < len(x) and x[o[j + 1]] == x[o[i]]:
            j += 1
        r[o[i:j + 1]] = (i + j) / 2 + 1
        i = j + 1
    return r


def spearman(a, b):
    if len(a) < 3 or np.std(a) == 0 or np.std(b) == 0:
        return None
    return float(np.corrcoef(rank(a), rank(b))[0, 1])


def generation_stats(view, arr, V, V32):
    vidx = {r['ImageID']: i for i, r in enumerate(V)}
    ids = [r['ImageID'] for r in V32]
    pi = [vidx[i] for i in ids]
    rng = np.random.default_rng(SEED)
    conds = {}
    for k, rows in view.items():
        el = [r for r in rows if r['positive_n']]
        conds[f'{k[0]}@{k[1]}'] = dict(n=len(rows), abnormal_n=sum(r['abnormal'] for r in rows), recall_eligible_n=len(el),
                                        strict_recall=recall_of(rows), type_recall=float(np.mean([r['type_recall'] for r in el])),
                                        normal_only_output=sum(r['normal_only_output'] for r in rows),
                                        normal_only_output_in_abnormal=sum(r['normal_only_output'] for r in rows if r['abnormal']),
                                        non_eos=sum(r['non_eos'] for r in rows), patient_contradiction=sum(r['contradiction'] for r in rows),
                                        mean_words=float(np.mean([r['text_words'] for r in rows])))
    # paired contrasts on recall-eligible patients (patient-level strict_recall)
    def vec(k):
        return np.array([r['strict_recall'] if r['positive_n'] else np.nan for r in view[k]])
    contr = {}
    def contrast(name, a, b):
        da, db = vec(a), vec(b)
        m = ~np.isnan(da)
        contr[name] = boot((da - db)[m], rng)
        e_a = np.array([r['strict_atoms'] for r in view[a]], dtype=object)
        e_b = np.array([r['strict_atoms'] for r in view[b]], dtype=object)
        gained = sum(len(set(x) - set(y)) for x, y in zip(e_a, e_b))
        lost = sum(len(set(y) - set(x)) for x, y in zip(e_a, e_b))
        contr[name]['strict_atoms_gained'] = gained
        contr[name]['strict_atoms_lost'] = lost
        contr[name]['patients_with_gain'] = sum(bool(set(x) - set(y)) for x, y in zip(e_a, e_b))
        contr[name]['patients_with_loss'] = sum(bool(set(y) - set(x)) for x, y in zip(e_a, e_b))
    for lr in LRS:
        for e in (2, 6):
            contrast(f'G-R lr{lr} epoch{e}', (f'G_lr{lr}', e), (f'R_lr{lr}', e))
        for m in MODES:
            contrast(f'{m} lr{lr} epoch6-epoch2', (f'{m}_lr{lr}', 6), (f'{m}_lr{lr}', 2))
            contrast(f'{m} lr{lr} epoch2-base', (f'{m}_lr{lr}', 2), ('base', 0))
            contrast(f'{m} lr{lr} epoch6-base(epoch2 base)', (f'{m}_lr{lr}', 6), ('base', 0))
    # NLL 변화와 생성 변화 연결 (epoch2 -> epoch6)
    link = {}
    for m in MODES:
        for lr in LRS:
            a = arr[(m, lr)]  # [epoch, patient]
            dn = a[3][pi] - a[1][pi]  # epoch6 - epoch2 NLL, V32 환자
            ds = vec((f'{m}_lr{lr}', 6)) - vec((f'{m}_lr{lr}', 2))
            msk = ~np.isnan(ds)
            link[f'{m}_lr{lr}'] = dict(n=int(msk.sum()), spearman_dNLL_vs_dRecall=spearman(dn[msk], ds[msk]),
                                       mean_dNLL_eligible=float(dn[msk].mean()), mean_dRecall=float(ds[msk].mean()),
                                       frac_nll_up=float((dn[msk] > 0).mean()), frac_recall_up=float((ds[msk] > 0).mean()),
                                       frac_recall_down=float((ds[msk] < 0).mean()),
                                       nll_mean_V32_epoch1=float(a[0][pi].mean()), nll_mean_V32_epoch2=float(a[1][pi].mean()),
                                       nll_mean_V32_epoch6=float(a[3][pi].mean()))
    # NLL 순서 vs 회복 순서: 한 trajectory의 epoch2 대 epoch6
    order = {}
    for m in MODES:
        for lr in LRS:
            n2 = float(arr[(m, lr)][1].mean()); n6 = float(arr[(m, lr)][3].mean())
            order[f'{m}_lr{lr}'] = dict(nll_epoch2=n2, nll_epoch6=n6, lower_nll_epoch=2 if n2 < n6 else 6,
                                        recall_epoch2=recall_of(view[(f'{m}_lr{lr}', 2)]), recall_epoch6=recall_of(view[(f'{m}_lr{lr}', 6)]),
                                        higher_recall_epoch=(2 if recall_of(view[(f'{m}_lr{lr}', 2)]) > recall_of(view[(f'{m}_lr{lr}', 6)])
                                                             else 6 if recall_of(view[(f'{m}_lr{lr}', 2)]) < recall_of(view[(f'{m}_lr{lr}', 6)]) else 'tie'))
    return conds, contr, link, order


# ---------------------------------------------------------------- 5. 의미 민감도
GROUP_OF = {'chest abnormality': 'generic_normal', 'pulmonary opacity': 'generic_normal', 'mediastinal abnormality': 'generic_normal',
            'osseous abnormality': 'generic_normal', 'significant abnormality': 'generic_normal',
            'acute cardiopulmonary process': 'acute_negation', 'pleural effusion': 'specific_negation', 'pneumothorax': 'specific_negation',
            'infiltrate/consolidation': 'specific_negation', 'consolidation': 'specific_negation', 'pulmonary nodule/mass': 'specific_negation',
            'jugular catheter route': 'location_attribute', 'pacemaker type': 'location_attribute', 'humeral prosthesis laterality': 'location_attribute'}
LOC_FINDING = {'jugular catheter route': 'central venous catheter', 'pacemaker type': 'pacemaker', 'humeral prosthesis laterality': 'humeral prosthesis'}


def sens_claims(po, ref_rows):
    ref = {r['id']: r for r in ref_rows}
    rows = []
    for (k, iid), x in po.items():
        atoms = [dict(finding=a['finding'], polarity=a['polarity'], certainty=a['certainty'], location=a['location'], attributes=a['attributes'], id=a['id'])
                 for a in ref[iid]['atoms']]
        stated = [c['finding'] for c in x['claims'] if c['polarity'] == 'positive']
        for c in x['claims']:
            g = GROUP_OF.get(c['finding'])
            if not g:
                continue
            # 보수 규칙은 negative 일반/구체 문장과 위치·속성 claim에만 적용; 'other' 문장은 other_scope
            grp = 'other_scope' if (g == 'generic_normal' and 'other' in c['quote'].lower()) else g
            if g == 'location_attribute' and c['polarity'] != 'positive':
                continue
            if g != 'location_attribute' and c['polarity'] != 'negative':
                continue
            f = LOC_FINDING.get(c['finding'], c['finding'])
            if g == 'specific_negation' and f == 'consolidation':
                f = 'infiltrate/consolidation'
            new = SENS.judge(grp, c['quote'], f, atoms, stated)
            new = dict(supported='supported', contradicted='contradicted', undecidable='unknown')[new]
            rows.append(dict(cond=f'{k[0]}@{k[1]}', image_id=iid, patient=x['patient'], group=grp, finding=c['finding'], quote=c['quote'],
                             original=c['status'], conservative=new, changed=(c['status'] != new),
                             ref_atoms=[f"{a['id']}:{a['finding']}:{a['polarity']}:{a['certainty']}:{a['location']}" for a in atoms], original_refs=c['refs'],
                             anchor_ok=(c['quote'] == c['anchor']['quote'])))
    return rows


def sens_summary(rows, po):
    cond = defaultdict(lambda: dict(claims=0, changed=0, orig_contra_claims=0, cons_contra_claims=0, orig_contra_patients=set(), cons_contra_patients=set()))
    for r in rows:
        d = cond[r['cond']]
        d['claims'] += 1
        d['changed'] += r['changed']
        if r['original'] == 'contradicted':
            d['orig_contra_claims'] += 1; d['orig_contra_patients'].add(r['image_id'])
        if r['conservative'] == 'contradicted':
            d['cons_contra_claims'] += 1; d['cons_contra_patients'].add(r['image_id'])
    out = {}
    for c, d in cond.items():
        out[c] = dict(reevaluated_claims=d['claims'], status_changed=d['changed'], original_contradicted_claims=d['orig_contra_claims'],
                      conservative_contradicted_claims=d['cons_contra_claims'], original_contradicted_patients=len(d['orig_contra_patients']),
                      conservative_contradicted_patients=len(d['cons_contra_patients']))
    # 원 per_output 환자 수준 contradiction과 대조(재평가 범위 밖 claim은 원 판정 유지)
    full = {}
    for (k, iid), x in po.items():
        c = f'{k[0]}@{k[1]}'
        full.setdefault(c, dict(orig=0, cons=0))
        orig_c = any(cl['status'] == 'contradicted' for cl in x['claims'])
        full[c]['orig'] += orig_c
        re_rows = [r for r in rows if r['cond'] == c and r['image_id'] == iid]
        changed = {(r['quote'], r['finding'], r['original']): r['conservative'] for r in re_rows}
        cons = False
        for cl in x['claims']:
            st = changed.get((cl['quote'], cl['finding'], cl['status']), cl['status'])
            cons |= (st == 'contradicted')
        full[c]['cons'] += cons
    return out, full


# ---------------------------------------------------------------- main
def main():
    t0 = time.time()
    assert not (OUT / 'summary.json').exists(), 'iter_093 summary already exists'
    T, V, V32, traj = inputs()
    files = input_manifest(T, V, V32, traj)
    save('input_manifest.json', dict(files=files, n_files=len(files), v32_in_v64=all(r['ImageID'] in {v['ImageID'] for v in V} for r in V32)))
    tcomp, tper = target_composition(T)
    vcomp, vper = target_composition(V)
    v32comp, _ = target_composition(V32)
    # T512/V64 환자 중복 없음 확인
    assert not ({r['PatientID'] for r in T} & {r['PatientID'] for r in V})
    save('target_composition.json', dict(T512=tcomp, V64=vcomp, V32=v32comp))
    tab, repro, alt, dec, arr = nll_tables(V, traj, vper)
    save('nll_trajectories.json', dict(per_trajectory=tab, selection_reproduction=repro, post_hoc_sensitivity=alt, group_decomposition=dec,
                                      note='sequence-mean NLL per patient; token-level contributions not stored'))
    save('nll_per_patient.json', dict(order='V64 manifest order', patient_ids=[r['PatientID'] for r in V], image_ids=[r['ImageID'] for r in V],
                                      patient_class=[vper[r['PatientID']]['cls'] for r in V],
                                      values={f'{m}_lr{lr}': {str(e): list(map(float, traj[(m, lr)]['val'][e]['per_patient'])) for e in EPOCHS}
                                              for (m, lr) in traj}))
    ref_rows = jl(I90 / 'semantic/V32_reference_v3.json')['rows']
    po = v32_outputs()
    txt = raw_text()
    assert len(po) == 32 * 9 and len(txt) == 32 * 9
    view = patient_view(po, txt, ref_rows, V32)
    # 평가기 recall 재현: 저장 report.json
    for e in (2, 6):
        rep = jl(REC / f'semantic/epoch{e}/eval/report.json')['conditions']
        for cond, d in rep.items():
            key = ('base', 0) if cond == 'base_report' else (cond.replace('_report', ''), e)
            assert abs(recall_of(view[key]) - d['strict_recall']) < 1e-9, (key, recall_of(view[key]), d['strict_recall'])
    conds, contr, link, order = generation_stats(view, arr, V, V32)
    save('v32_generation.json', dict(conditions=conds, paired_contrasts=contr, nll_vs_generation=link, nll_order_vs_recall_order=order,
                                     epoch1_v32_generation='missing (not generated; not filled)',
                                     denominators=dict(all=32, abnormal=21, recall_eligible=20)))
    save('v32_patient_view.json', {f'{k[0]}@{k[1]}': rows for k, rows in view.items()})
    # 의미 민감도: fixture 먼저
    fx = []
    for f in FX.FIXTURES:
        got = SENS.judge(f['group'], f['quote'], f['finding'], f['refs'], f.get('stated_findings', ()))
        fx.append(dict(id=f['id'], group=f['group'], quote=f['quote'], expected=f['expected'], got=got, ok=got == f['expected'], why=f['why']))
    assert all(x['ok'] for x in fx), [x for x in fx if not x['ok']]
    srows = sens_claims(po, ref_rows)
    ssum, sfull = sens_summary(srows, po)
    save('semantic_sensitivity.json', dict(fixtures=fx, fixtures_sha=sha(ROOT / 'report93_fixtures.py'),
                                           fixtures_by_group=dict(Counter(x['group'] for x in fx)),
                                           claim_review=srows, claim_summary=ssum, patient_level_contradiction_original_vs_conservative=sfull,
                                           anchor_failures=sum(not r['anchor_ok'] for r in srows)))
    save('summary.json', dict(seconds=time.time() - t0, n_input_files=len(files), selection_reproduced=repro, gpu_use=0, new_generation_requests=0))
    print(json.dumps(dict(seconds=time.time() - t0, repro=repro), default=str))


if __name__ == '__main__':
    main()
