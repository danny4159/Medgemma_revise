"""D 단계: 모델별 baseline singleton B 선택(S1/S2의 D BA02, 동률이면 T1). 사용: python sp67_select.py <requests_D> <labels_D> <protocol_D> <gen_root> <out.json>"""
import json, sys
import numpy as np
import m65_run as M65
import sp67_eval as E
import sp67_run as R


def main():
    req, lab, prot, gen, out = sys.argv[1:6]
    pdig = R.check_protocol(prot, req, lab)
    truth = E.truth_map(lab)
    sel = {}
    for model in R.MODELS:
        recs = E.load_recs(gen, model, req, pdig)
        t = E.Table(recs, truth, ['S1', 'S2'])
        ba = {}
        for n in ('S1', 'S2'):
            ba[n] = E.ba_from_counts(t.patient_counts(t.pred[n]))[0]
        sel[model] = {'B': 't1' if ba['S1'] >= ba['S2'] else 't2', 'D_BA02': ba, 'rule': 'higher D BA02, tie -> t1', 'protocol_digest': pdig}
    json.dump(sel, open(out, 'w'), indent=1)
    print(sel)


if __name__ == '__main__':
    main()
