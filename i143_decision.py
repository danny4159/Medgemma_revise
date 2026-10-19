"""원 계획의 연장·선택·A-S 판정 산술. 새 문턱은 추가하지 않는다."""
import math


def ge(a,b):
    # 유리수 비율의 float 반올림에만 쓰며 과학적 문턱을 변경하지 않는다.
    return a>=b or math.isclose(a,b,rel_tol=0,abs_tol=1e-12)


def extension(metrics):
    assert set(metrics)=={'S','A','N'}
    reasons={}
    for cond,rows in metrics.items():
        old,new=rows['4'],rows['8']
        recovery=ge(new['recall']-old['recall'],.02)
        loss=(ge(old['target_nll']*.95,new['target_nll']) and
              new['contradiction_count']<=old['contradiction_count'] and ge(new['recall'],old['recall']))
        reasons[cond]=dict(recall_improvement=recovery,nll_and_generation=loss)
    return dict(extend=any(v['recall_improvement'] or v['nll_and_generation'] for v in reasons.values()),reasons=reasons)


def swap_condition(metrics):
    assert set(metrics)=={'S','A','N'}
    priority={'N':0,'S':1,'A':2}
    return min(metrics,key=lambda c:(-metrics[c]['recall'],metrics[c]['contradiction_count'],priority[c]))


def outcome(comparison,valid_learning):
    if not valid_learning: return 'execution_failed'
    if ge(comparison['semantic_difference'][0],.05) and ge(.05,comparison['contradiction_difference'][1]):
        return 'pilot_positive' if comparison['point']['ci95'][0]>0 else 'promising_inconclusive'
    if not ge(comparison['upper_difference_ci']['ci95'][1],.05): return 'current_design_gain_not_supported'
    return 'inconclusive'
