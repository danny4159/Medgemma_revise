"""iter_134 평가기: 출력 생성 전에 잠근다. strict BA(UNKNOWN·invalid는 해당 class 오답), 개별 OR vs 공동 입력 paired 환자 bootstrap(10,000회, seed134),
사전 판정 분기(positive / negative / inconclusive). 정답은 annotation-defined이며 임상 진단이 아니다.
입력: completion이 검증된 main job 디렉터리(verify_job). 이 모듈은 요청 완전성·provenance를 i134_run.verify_job에 맡긴다."""
import json, sys
from pathlib import Path
import numpy as np
from i134_common import RES, read, save, sha, digest, now, SEED
from i134_spec import parse, audit, repetition, CONDS

POS_SINGLE, NEG_SINGLE = ['P'], ['N1', 'N2']
POS_JOINT, NEG_JOINT = ['PN1', 'N1P'], ['N1N2', 'N2N1']
TRUTH = dict(P='PRESENT', PN1='PRESENT', N1P='PRESENT', PP='PRESENT', N1='ABSENT', N2='ABSENT', N1N2='ABSENT', N2N1='ABSENT', N1N1='ABSENT')


def states_of(records):
    st = {}
    for r in records:
        s = parse(r['text'], r['eos']); st[r['id']] = dict(state=s, eos=r['eos'], n_tokens=r['n_tokens'], wall_s=r['wall_s'], audit=audit(r['text'], s), rep=repetition(r['text']), text=r['text'])
    return st


def OR(states):
    """개별 OR: invalid 포함 → INVALID, 하나라도 PRESENT → PRESENT, 모두 ABSENT → ABSENT, 나머지 UNKNOWN."""
    if any(s is None for s in states): return 'INVALID'
    if any(s == 'PRESENT' for s in states): return 'PRESENT'
    if all(s == 'ABSENT' for s in states): return 'ABSENT'
    return 'UNKNOWN'


def patient_table(st, pids):
    T = {}
    for p in pids:
        g = lambda c: st[p + '__' + c]['state']
        ok = lambda c: float(g(c) == TRUTH[c])
        orp = OR([g('P'), g('N1')]); orn = OR([g('N1'), g('N2')])
        T[p] = dict(or_pos=orp, or_neg=orn, or_pos_ok=float(orp == 'PRESENT'), or_neg_ok=float(orn == 'ABSENT'),
                    joint_pos_ok=float(np.mean([ok(c) for c in POS_JOINT])), joint_neg_ok=float(np.mean([ok(c) for c in NEG_JOINT])),
                    **{('ok_' + c): ok(c) for c in TRUTH})
    return T


def mean(T, k): return float(np.mean([v[k] for v in T.values()]))
def ba(T, pos, neg): return (mean(T, pos) + mean(T, neg)) / 2


def boot(T, f, n=10000, seed=SEED):
    pids = sorted(T); rng = np.random.default_rng(seed); arr = np.array([f(T[p]) for p in pids]); idx = rng.integers(0, len(pids), (n, len(pids)))
    b = arr[idx].mean(1); return float(arr.mean()), [float(np.percentile(b, 2.5)), float(np.percentile(b, 97.5))]


def transitions(T, a_key, b_key):
    """a 정답→b 오답 / a 오답→b 정답 환자 수 (연속값은 0.5 단위가 있어 소수 포함: 합계로 기록)."""
    lost = float(sum(max(0.0, v[a_key] - v[b_key]) for v in T.values())); gain = float(sum(max(0.0, v[b_key] - v[a_key]) for v in T.values()))
    return dict(a_right_b_wrong=lost, a_wrong_b_right=gain)


def report(job, stage='main'):
    import i134_run as R
    rec = R.verify_job(job, stage); st = states_of(rec)
    pids = sorted(set(r['id'].split('__')[0] for r in rec)); assert len(rec) == 10 * len(pids)
    T = patient_table(st, pids)
    d_main = lambda v: (v['or_pos_ok'] + v['or_neg_ok']) / 2 - (v['joint_pos_ok'] + v['joint_neg_ok']) / 2
    diff, ci = boot(T, d_main)
    single_ba = (mean(T, 'ok_P') + (mean(T, 'ok_N1') + mean(T, 'ok_N2')) / 2) / 2
    per_cond = {}
    for c in CONDS:
        rows = [st[p + '__' + c] for p in pids]
        per_cond[c] = dict(n=len(rows), valid=sum(r['state'] is not None for r in rows), invalid=sum(r['state'] is None for r in rows),
                           non_eos=sum(not r['eos'] for r in rows), PRESENT=sum(r['state'] == 'PRESENT' for r in rows), ABSENT=sum(r['state'] == 'ABSENT' for r in rows),
                           UNKNOWN=sum(r['state'] == 'UNKNOWN' for r in rows), contradiction=sum(r['audit'] == 'contradiction' for r in rows),
                           unresolved=sum(r['audit'] == 'unresolved' for r in rows), repetition=sum(r['rep'] for r in rows),
                           mean_tokens=float(np.mean([r['n_tokens'] for r in rows])), sum_wall_s=float(sum(r['wall_s'] for r in rows)))
        if c in TRUTH:
            expl = [r for r in rows if r['state'] in ('PRESENT', 'ABSENT')]
            per_cond[c]['acc_strict'] = float(np.mean([r['state'] == TRUTH[c] for r in rows])); per_cond[c]['explicit_n'] = len(expl)
            per_cond[c]['acc_explicit_only'] = float(np.mean([r['state'] == TRUTH[c] for r in expl])) if expl else None
    imgreq = [st[p + '__' + c] for p in pids for c in CONDS if c != 'NONE']
    valid_rate = float(np.mean([r['state'] is not None for r in imgreq])); valid_rate_all = float(np.mean([r['state'] is not None for r in st.values()]))
    or_ba = (mean(T, 'or_pos_ok') + mean(T, 'or_neg_ok')) / 2; joint_ba = (mean(T, 'joint_pos_ok') + mean(T, 'joint_neg_ok')) / 2
    sec = {}
    for name, f in dict(PP_minus_P=lambda v: v['ok_PP'] - v['ok_P'], N1N1_minus_N1=lambda v: v['ok_N1N1'] - v['ok_N1'],
                        joint_PN1_minus_or=lambda v: v['ok_PN1'] - v['or_pos_ok'], joint_N1P_minus_or=lambda v: v['ok_N1P'] - v['or_pos_ok'],
                        joint_N1N2_minus_or=lambda v: v['ok_N1N2'] - v['or_neg_ok'], joint_N2N1_minus_or=lambda v: v['ok_N2N1'] - v['or_neg_ok'],
                        pos_or_minus_joint=lambda v: v['or_pos_ok'] - v['joint_pos_ok'], neg_or_minus_joint=lambda v: v['or_neg_ok'] - v['joint_neg_ok'],
                        Pjoint_minus_P=lambda v: v['joint_pos_ok'] - v['ok_P']).items():
        m_, c_ = boot(T, f); sec[name] = dict(mean=m_, ci95=c_)
    trans = dict(pos_or_to_joint=transitions(T, 'or_pos_ok', 'joint_pos_ok'), neg_or_to_joint=transitions(T, 'or_neg_ok', 'joint_neg_ok'))
    # 비용: 환자당 동일 집합의 두 단독 요청 대 한 공동 요청 (요청 wall 합, 모델 시간 기준; 로딩 제외)
    wall = lambda cs: float(np.mean([sum(st[p + '__' + c]['wall_s'] for c in cs) for p in pids]))
    cost = dict(pos_individual_two_singles_s=wall(['P', 'N1']), pos_joint_one_request_s=wall(['PN1', 'N1P']) / 2, neg_individual_two_singles_s=wall(['N1', 'N2']), neg_joint_one_request_s=wall(['N1N2', 'N2N1']) / 2,
                note='요청 처리 시간 합(생성 구간, 모델 로딩·렌더링 제외). 재사용(같은 단독 응답을 다른 집합에 재사용)과 전체 workload 비용은 별도 집계 필요.')
    dec = decide(or_ba, joint_ba, diff, ci, valid_rate)
    out = dict(created_at=now(), stage=stage, n_patients=len(pids), or_BA=or_ba, joint_BA=joint_ba, single_BA=single_ba, or_pos_acc=mean(T, 'or_pos_ok'), or_neg_acc=mean(T, 'or_neg_ok'),
               joint_pos_acc=mean(T, 'joint_pos_ok'), joint_neg_acc=mean(T, 'joint_neg_ok'), main_diff_or_minus_joint=diff, main_diff_ci95=ci, secondary=sec, transitions=trans, per_condition=per_cond,
               valid_rate_image_requests=valid_rate, valid_rate_all=valid_rate_all, or_state_counts=dict(pos={k: sum(v['or_pos'] == k for v in T.values()) for k in ('PRESENT', 'ABSENT', 'UNKNOWN', 'INVALID')},
                                                                                                     neg={k: sum(v['or_neg'] == k for v in T.values()) for k in ('PRESENT', 'ABSENT', 'UNKNOWN', 'INVALID')}),
               cost=cost, decision=dec, bootstrap=dict(n=10000, seed=SEED, unit='patient'), job=str(job))
    return out, T


def decide(or_ba, joint_ba, diff, ci, valid_rate):
    if or_ba >= 0.75 and diff >= 0.15 and ci[0] > 0 and valid_rate >= 0.95: return 'positive_limited_joint_loss'
    if or_ba >= 0.75 and joint_ba >= 0.75 and ci[1] < 0.15: return 'negative_joint_loss_candidate_hold'
    if or_ba <= 0.60: return 'negative_basic_reading_insufficient'
    return 'inconclusive'


if __name__ == '__main__':
    job = Path(sys.argv[1]).resolve(); outp = Path(sys.argv[2]).resolve(); assert str(outp).startswith(str(RES) + '/')
    o, T = report(job, sys.argv[3] if len(sys.argv) > 3 else 'main')
    save(outp, o); save(outp.with_name(outp.stem + '_per_patient.json'), T); print(json.dumps({k: o[k] for k in ('or_BA', 'joint_BA', 'single_BA', 'main_diff_or_minus_joint', 'main_diff_ci95', 'valid_rate_image_requests', 'decision')}, indent=1))
