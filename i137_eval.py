"""iter_137 평가기: 출력 생성 전에 잠근다. strict 상태(UNKNOWN·invalid·절단은 오답, 분모 유지), annotation-defined BA, B−A 환자 paired bootstrap(10,000회, seed137, percentile 95%),
사전 판정 분기(positive / negative / inconclusive / invalid_output_conditions). 정답은 annotation-defined이며 임상 진단이 아니다.
입력: completion이 검증된 main job(verify_job: 요청 완전성·protocol·provenance 재검증). 자유 설명의 임상 정확성은 채점하지 않는다."""
import glob, json, sys
from pathlib import Path
import numpy as np
from i137_common import RES, OLD136, BOOT_SEED, read, save, now, sha
from i137_spec import parse, audit, repetition, first_line, extra_text, TRUTH, IFACES

N_BOOT = 10000
THR = dict(ba=0.75, sens=0.65, spec=0.65, diff=0.15, valid=0.95, neg_ba=0.60)


def states_of(records):
    st = {}
    for r in records:
        s = parse(r['final_text'], r['eos'], r['boundary_status'])
        st[r['id']] = dict(state=s, eos=r['eos'], n_tokens=r['n_tokens'], wall_s=r['wall_s'], boundary=r['boundary_status'], text=r['text'], audit=audit(r['final_text'], s),
                           rep=repetition(r['final_text']), extra=extra_text(r['final_text']), peak_reserved_mib=r['peak_reserved_mib'], n_image_tokens=r['n_image_tokens'], input_len=r['input_len'])
    return st


def patient_table(st, pids):
    T = {}
    for p in pids:
        row = {}
        for i in IFACES:
            for c, truth in TRUTH.items():
                row['ok_%s_%s' % (c, i)] = float(st['%s__%s__%s' % (p, c, i)]['state'] == truth)
            row['ba_%s' % i] = (row['ok_P_%s' % i] + row['ok_N1_%s' % i]) / 2
            row['both_%s' % i] = float(row['ok_P_%s' % i] == 1.0 and row['ok_N1_%s' % i] == 1.0)
        row['diff_ba'] = row['ba_B'] - row['ba_A']
        T[p] = row
    return T


def mean(T, k): return float(np.mean([v[k] for v in T.values()]))


def boot(T, f, n=N_BOOT, seed=BOOT_SEED):
    pids = sorted(T); rng = np.random.default_rng(seed); arr = np.array([f(T[p]) for p in pids]); idx = rng.integers(0, len(pids), (n, len(pids)))
    b = arr[idx].mean(1); return float(arr.mean()), [float(np.percentile(b, 2.5)), float(np.percentile(b, 97.5))]


def decide(rep):
    """사전 규칙(plan Evaluation). 출력 조건이 valid하지 않으면 과학적 양성/음성으로 쓰지 않는다."""
    v = rep['output_validity']; ok_valid = all(v[i]['eos_rate'] >= THR['valid'] and v[i]['boundary_valid_rate'] >= THR['valid'] and v[i]['first_line_valid_rate'] >= THR['valid'] for i in IFACES)
    if not ok_valid: return 'invalid_output_conditions'
    B, d, ci = rep['B'], rep['diff_B_minus_A'], rep['diff_ci95']
    if B['BA'] >= THR['ba'] and B['sensitivity'] >= THR['sens'] and B['specificity'] >= THR['spec'] and d >= THR['diff'] and ci[0] > 0: return 'positive_limited_recovery'
    if B['BA'] <= THR['neg_ba'] or ci[1] < THR['diff']: return 'negative_no_recovery'
    return 'inconclusive'


def repro_vs_iter136(rec):
    """A 재실행 대 iter_136 저장 출력(같은 prompt·pixels·설정): 재현성 점검용이며 주판정에 쓰지 않는다."""
    old = {}
    for f in sorted(glob.glob(str(OLD136 / 'jobs/main/worker*.jsonl'))):
        for l in open(f):
            r = json.loads(l); old[r['id']] = r
    n = same = same_state = 0; cmp_ = []
    for r in rec:
        if not r['id'].endswith('__A'): continue
        o = old.get(r['id'][:-3])
        if o is None: continue
        n += 1; same += int(o['tokens'] == r['tokens'])
        so = parse(o['final_text'], o['eos'], o['boundary_status']); sn = parse(r['final_text'], r['eos'], r['boundary_status']); same_state += int(so == sn)
        if o['tokens'] != r['tokens']: cmp_.append(r['id'])
    return dict(n_compared=n, identical_tokens=same, identical_state=same_state, differing_ids=cmp_)


def report(job, stage='main'):
    import i137_run as R
    rec = R.verify_job(job, stage); st = states_of(rec)
    pids = sorted(set(r['id'].split('__')[0] for r in rec)); assert len(rec) == 4 * len(pids)
    T = patient_table(st, pids)
    diff, ci = boot(T, lambda v: v['diff_ba'])
    out = dict(created_at=now(), stage=stage, n_patients=len(pids), always_PRESENT_BA=0.5, thresholds=THR)
    per = {}; validity = {}; confusion = {}
    for i in IFACES:
        sens, spec = mean(T, 'ok_P_%s' % i), mean(T, 'ok_N1_%s' % i)
        bm, bci = boot(T, lambda v, i=i: v['ba_%s' % i])
        out[i] = dict(BA=(sens + spec) / 2, BA_ci95=bci, sensitivity=sens, specificity=spec, both_correct_rate=mean(T, 'both_%s' % i))
        rows = {c: [st['%s__%s__%s' % (p, c, i)] for p in pids] for c in TRUTH}
        allr = rows['P'] + rows['N1']
        validity[i] = dict(n=len(allr), eos_rate=float(np.mean([r['eos'] for r in allr])), non_eos=sum(not r['eos'] for r in allr), boundary_valid_rate=float(np.mean([r['boundary'] != 'invalid_boundary' for r in allr])),
                           first_line_valid_rate=float(np.mean([r['state'] is not None for r in allr])), invalid=sum(r['state'] is None for r in allr), truncated_non_eos=sum(not r['eos'] for r in allr),
                           unknown=sum(r['state'] == 'UNKNOWN' for r in allr), repetition=sum(r['rep'] for r in allr), extra_explanation=sum(r['extra'] for r in allr),
                           audit_contradiction=sum(r['audit'] == 'contradiction' for r in allr), audit_unresolved=sum(r['audit'] == 'unresolved' for r in allr))
        confusion[i] = {c: {k: sum(r['state'] == k for r in rows[c]) for k in ('PRESENT', 'ABSENT', 'UNKNOWN')} | dict(invalid=sum(r['state'] is None for r in rows[c])) for c in TRUTH}
        per[i] = dict(mean_tokens=float(np.mean([r['n_tokens'] for r in allr])), sum_tokens=int(sum(r['n_tokens'] for r in allr)), mean_request_wall_s=float(np.mean([r['wall_s'] for r in allr])), sum_request_wall_s=float(sum(r['wall_s'] for r in allr)),
                      max_peak_reserved_mib=float(max(r['peak_reserved_mib'] for r in allr)), n_image_tokens=sorted({r['n_image_tokens'] for r in allr}), input_len=sorted({r['input_len'] for r in allr}))
    out.update(diff_B_minus_A=diff, diff_ci95=ci, output_validity=validity, confusion=confusion, cost=per,
               cost_ratio_B_over_A=dict(tokens=per['B']['sum_tokens'] / per['A']['sum_tokens'], request_wall=per['B']['sum_request_wall_s'] / per['A']['sum_request_wall_s']),
               transitions=dict(A_right_B_wrong=float(sum(max(0, v['ba_A'] - v['ba_B']) for v in T.values())), A_wrong_B_right=float(sum(max(0, v['ba_B'] - v['ba_A']) for v in T.values()))),
               sec_both_correct_diff=dict(zip(('mean', 'ci95'), boot(T, lambda v: v['both_B'] - v['both_A']))),
               repro_vs_iter136_A=repro_vs_iter136(rec), bootstrap=dict(n=N_BOOT, seed=BOOT_SEED, unit='patient', ci='percentile95'), job=str(job),
               note='annotation-defined 정답이며 임상 진단이 아니다. 반복 개발 E45. 설명의 임상 정확성은 채점하지 않는다. audit_*는 보조 정규식 감사.')
    out['decision'] = decide(out)
    return out, T


if __name__ == '__main__':
    job = Path(sys.argv[1]).resolve(); outp = Path(sys.argv[2]).resolve(); assert str(outp).startswith(str(RES) + '/')
    o, T = report(job, sys.argv[3] if len(sys.argv) > 3 else 'main')
    save(outp, o); save(outp.with_name(outp.stem + '_per_patient.json'), T)
    print(json.dumps({k: o[k] for k in ('A', 'B', 'diff_B_minus_A', 'diff_ci95', 'decision')}, indent=1))
