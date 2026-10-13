"""iter_133 평가: main 45요청의 첫 줄 범주 집계. 임상 정확도 평가가 아니라 보고서에 명시된 기술의 재현 집계.
사전 판정 규칙(plan.md Evaluation)을 그대로 구현한다. AutoRG 기존 출력은 별도 기술 집계로만 병기한다."""
import sys
import numpy as np
from i133_common import RES, SRC, sha, read, save, now
from i133_spec import parse, CATS
import i133_run as R

COND = ['U', 'L', 'M']
HIGHISH = ('HIGH', 'MIXED_HIGH_LOW')


def load(job):
    rec = R.verify_job(job, RES / 'requests/main.json', 'main')
    man = read(RES / 'data_manifest.json'); lab = {a['pid']: a['report_label'] for a in man['audit']}
    out = {}
    for r in rec:
        pid, cond = r['id'].split('__'); out[(pid, cond)] = dict(cat=parse(r['text'], r['eos']), eos=r['eos'], n_tokens=r['n_tokens'], first_line=(r['text'].strip().splitlines() or [''])[0][:80])
    assert len(out) == 45 and set(lab.values()) == {'HIGH', 'MIXED_HIGH_LOW'}
    return out, lab


def table(out, lab):
    pids = sorted(lab); mixed = [p for p in pids if lab[p] == 'MIXED_HIGH_LOW']; high = [p for p in pids if lab[p] == 'HIGH']
    res = {}
    for c in COND:
        cats = [out[(p, c)]['cat'] for p in pids]
        res[c] = dict(valid=sum(x is not None for x in cats), invalid=sum(x is None for x in cats), non_eos=sum(not out[(p, c)]['eos'] for p in pids),
                      dist={k: sum(x == k for x in cats) for k in CATS}, mixed_reproduced=sum(out[(p, c)]['cat'] == 'MIXED_HIGH_LOW' for p in mixed),
                      high_preserved=sum(out[(p, c)]['cat'] in HIGHISH for p in high), high_exact=sum(out[(p, c)]['cat'] == 'HIGH' for p in high),
                      exact_agreement=sum(out[(p, c)]['cat'] == lab[p] for p in pids))
    return pids, mixed, high, res


def transitions(out, pids, a, b):
    t = {}
    for p in pids:
        k = f"{out[(p, a)]['cat']}->{out[(p, b)]['cat']}"; t[k] = t.get(k, 0) + 1
    return t


def boot(out, mixed, a, b, n=10000, seed=133):
    x = np.array([[out[(p, c)]['cat'] == 'MIXED_HIGH_LOW' for c in (a, b)] for p in mixed], float); d = x[:, 0] - x[:, 1]
    rng = np.random.default_rng(seed); ms = [d[rng.integers(0, len(d), len(d))].sum() for _ in range(n)]
    return dict(net_cases=int(d.sum()), gained=int(((x[:, 0] == 1) & (x[:, 1] == 0)).sum()), lost=int(((x[:, 0] == 0) & (x[:, 1] == 1)).sum()), ci95_net=[float(np.percentile(ms, 2.5)), float(np.percentile(ms, 97.5))])


def decide(res, net_LU, net_LM):
    valid_ok = all(res[c]['valid'] >= 14 for c in COND); high_ok = res['L']['high_preserved'] >= 3
    flags = dict(L_minus_U_net=net_LU, L_minus_M_net=net_LM, high_preserved_L=res['L']['high_preserved'], valid_each_ge14=valid_ok)
    if net_LU <= 0: v = 'negative_hold_marking_investment'
    elif net_LM <= 0: v = 'negative_no_image_use_claim'
    elif net_LU >= 3 and net_LM >= 3 and high_ok and valid_ok: v = 'positive_investment_signal'
    else: v = 'inconclusive'
    return dict(verdict=v, flags=flags, L_vs_M_indistinct=net_LM <= 0, note='임상 성능 gate가 아니라 후속 확인의 최소 정보 가치 문턱. 양성이어도 정확한 영역 의미·독립 환자·단순 대안 이후 가치는 미확인.')


def autorg(lab):
    """iter_070 저장 라벨(원 parser 결과)을 같은 집계 틀로 재배열만 한다. 입력 정보·모델이 달라 순위 비교가 아니다."""
    pc = read(SRC.parent / 'eval/report_all15.json')['per_case']; mixed = [p for p in lab if lab[p] == 'MIXED_HIGH_LOW']; high = [p for p in lab if lab[p] == 'HIGH']; res = {}
    for c in ['P', 'G']:
        lb = {p: pc[p][c]['label'] for p in lab}
        res[c] = dict(dist={k: sum(v == k for v in lb.values()) for k in sorted(set(lb.values()))}, mixed_reproduced=sum(lb[p] == 'MIXED_HIGH_LOW' for p in mixed), high_preserved=sum(lb[p] in HIGHISH for p in high))
    return res


def main(job):
    out, lab = load(job); pids, mixed, high, res = table(out, lab)
    tr = dict(U_to_L=transitions(out, pids, 'U', 'L'), M_to_L=transitions(out, pids, 'M', 'L'), U_to_M=transitions(out, pids, 'U', 'M'))
    bs = dict(L_minus_U=boot(out, mixed, 'L', 'U'), L_minus_M=boot(out, mixed, 'L', 'M'), U_minus_M=boot(out, mixed, 'U', 'M'))
    dec = decide(res, bs['L_minus_U']['net_cases'], bs['L_minus_M']['net_cases'])
    simple = dict(always_MIXED_HIGH_LOW=dict(mixed_reproduced=len(mixed), high_preserved=len(high), note='train majority 및 무조건 high+low 기술; 유효 판독기 아님'))
    ar = autorg(lab)
    per = [dict(pid=p, report=lab[p], **{c: out[(p, c)]['cat'] for c in COND}, first_lines={c: out[(p, c)]['first_line'] for c in COND}, n_tokens={c: out[(p, c)]['n_tokens'] for c in COND}) for p in pids]
    save(RES / 'eval/report.json', dict(created_at=now(), job=str(job), n_mixed=len(mixed), n_high_only=len(high), per_condition=res, transitions=tr, bootstrap_mixed_cases_seed133_10000=bs,
                                        decision=dec, simple_baselines=simple, autorg_iter070_labels_regrouped=ar, per_patient=per,
                                        eval_code_sha256=sha(__file__)))
    print(res); print(tr); print(bs); print(dec)


if __name__ == '__main__':
    main(sys.argv[1])
