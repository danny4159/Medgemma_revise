"""iter_048 D24 선택 단계 판정 (CPU). 규칙은 plan.md를 결과 전에 코드로 고정한 것이며 결과를 보고 바꾸지 않는다.

stage1 (epoch 2 vs 5):
  extend = (D24 F1@0.3 E_I e5 - e2 >= 0.02) or (D24 F1@0.3 J_J e5 - e2 >= 0.02)
           or (E의 I형식 D24 teacher-forced CE가 e2 대비 e5에서 5% 이상 감소) or (J의 J형식(AB+BA) D24 CE가 e2 대비 e5에서 5% 이상 감소)
  extend=True 이면 E/J 두 trajectory를 함께 8 epoch까지 한 번 연장 (const LR, 같은 train_config).
select (후보 2/5/(8)): 공통 epoch = argmax (E_I F1@0.3 + J_J F1@0.3)/2 on D24, J_J = AB/BA 평균.
  동률은 (두 점수의 최솟값이 큰 쪽) -> 이른 epoch. E/J를 서로 다른 epoch에서 고르지 않는다. C 초기점(참고)도 같은 D24 표에 보고하지만 후보가 아니다.
출력은 새 파일만 쓴다 (덮어쓰기 거부).

python pg48_dsel.py stage1 --out results/iter_048/decisions/D24_stage1.json
python pg48_dsel.py select --epochs 2 5 [8] --out results/iter_048/decisions/v96_gate.json
"""
import argparse
import hashlib
import json
import os
import sys

import numpy as np

import pg39_spec as S39
import pg43_run as R
import pg48_eval as E
import pg48_import as IM

ROOT = "results/iter_048"
MAN = E.MAN
TH = 0.02
CE_DROP = 0.05


def ents_d24():
    man = json.load(open(MAN))
    return {e["PatientID"]: e for e in man["D24"]}, [e["PatientID"] for e in man["D24"]]


def d24_dir(label):
    return f"{ROOT}/gen/D24_{label}", f"{ROOT}/requests/requests_D24.jsonl", f"{ROOT}/protocol/proto_D24_{label}.json"


def score_label(label, ents):
    gd, rq, pr = d24_dir(label)
    recs = R.verify_completion(gd, rq, pr)
    byk = {(r["patient"], r["cond"], tuple(r["targets"])): r for r in recs}
    return E.score_dir(byk, ents), R.verify_protocol(pr, rq)[0]


def d24_table(labels):
    ents, pids = ents_d24()
    out = {}
    for lab in labels:
        sc, pdig = score_label(lab, ents)
        row = {"protocol_digest": pdig}
        for kind in ("I", "AB", "BA", "J"):
            row[kind] = {m: float(E.pat_vec(sc, pids, kind, m).mean()) for m in ("f1_03", "f1_05", "recall_03", "fp_03")}
        row["invalid"] = {k: sum(v[0] not in E.parse.VALID for v in sc[k].values()) for k in ("I", "AB", "BA")}
        out[lab] = row
    return out


def ce_of(name, ep):
    p = f"{ROOT}/decisions/ce_{name}_e{ep}.json"
    return json.load(open(p)), p


def stage1(a):
    if os.path.exists(a.out):
        sys.exit("exists")
    tab = d24_table(["E_e2", "E_e5", "J_e2", "J_e5"])
    ce = {}
    for n in ("E", "J"):
        for ep in (2, 5):
            ce[f"{n}_e{ep}"], _ = ce_of(n, ep)
    dE = tab["E_e5"]["I"]["f1_03"] - tab["E_e2"]["I"]["f1_03"]
    dJ = tab["J_e5"]["J"]["f1_03"] - tab["J_e2"]["J"]["f1_03"]
    ceE2, ceE5 = ce["E_e2"]["ce_token_mean"]["I"], ce["E_e5"]["ce_token_mean"]["I"]
    ceJ2, ceJ5 = ce["J_e2"]["ce_J_both_orders_token_mean"], ce["J_e5"]["ce_J_both_orders_token_mean"]
    cond = {"E_I_f1_03_gain_e5_minus_e2": dE, "J_J_f1_03_gain_e5_minus_e2": dJ, "cond_E_f1>=0.02": dE >= TH, "cond_J_f1>=0.02": dJ >= TH,
            "E_I_ce_e2_e5": [ceE2, ceE5], "E_ce_drop_frac": (ceE2 - ceE5) / ceE2, "cond_E_ce_drop>=5%": (ceE2 - ceE5) / ceE2 >= CE_DROP,
            "J_J_ce_e2_e5": [ceJ2, ceJ5], "J_ce_drop_frac": (ceJ2 - ceJ5) / ceJ2, "cond_J_ce_drop>=5%": (ceJ2 - ceJ5) / ceJ2 >= CE_DROP}
    extend = bool(cond["cond_E_f1>=0.02"] or cond["cond_J_f1>=0.02"] or cond["cond_E_ce_drop>=5%"] or cond["cond_J_ce_drop>=5%"])
    out = {"stage": "stage1_e2_vs_e5", "extend_to_8_epochs": extend, "run": extend, "conditions": cond, "d24_table": tab,
           "ce_files": {k: {"adapter_digest": v["adapter_digest"], "ce_token_mean": v["ce_token_mean"], "ce_J_both_orders": v["ce_J_both_orders_token_mean"]} for k, v in ce.items()},
           "source_sha256": {"pg48_dsel.py": R.file_sha("pg48_dsel.py"), "pg48_eval.py": R.file_sha("pg48_eval.py")},
           "note": "D24는 선택 자료. 이 판정은 epoch 연장 여부만 정한다."}
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    json.dump(out, open(a.out, "w"), indent=1)
    print(json.dumps({"extend": extend, **cond}, indent=1))


def adapter_info(name, ep):
    d = f"{ROOT}/train/{name}_s17/epoch_{ep:02d}"
    import torch
    b = torch.load(os.path.join(d, "adapter.pt"), map_location="cpu", weights_only=True)
    return {"path": d, "digest": b["digest"], "file_sha256": R.file_sha(os.path.join(d, "adapter.pt")), "epoch": ep, "step": b.get("step")}


def select(a):
    if os.path.exists(a.out):
        sys.exit("exists")
    eps = list(a.epochs)
    tab = d24_table([f"{n}_e{ep}" for n in ("E", "J") for ep in eps])
    # C 초기점 (참고; 후보 아님)
    ents, pids = ents_d24()
    cd = IM.load_c_d24()
    csc = E.score_dir(cd["records"], ents)
    cref = {k: {m: float(E.pat_vec(csc, pids, k, m).mean()) for m in ("f1_03", "f1_05")} for k in ("I", "AB", "BA", "J")}
    scores = {}
    for ep in eps:
        e_i, j_j = tab[f"E_e{ep}"]["I"]["f1_03"], tab[f"J_e{ep}"]["J"]["f1_03"]
        scores[ep] = {"E_I": e_i, "J_J": j_j, "mean": (e_i + j_j) / 2, "min": min(e_i, j_j)}
    best = sorted(eps, key=lambda ep: (-round(scores[ep]["mean"], 12), -round(scores[ep]["min"], 12), ep))[0]
    ad = {n: adapter_info(n, best) for n in ("E", "J")}
    st1 = json.load(open(f"{ROOT}/decisions/D24_stage1.json"))
    out = {"run": True, "stage": "select_common_epoch", "common_epoch": best, "candidates": eps, "scores_d24": {str(k): v for k, v in scores.items()},
           "d24_table": tab, "c_initial_d24_reference": cref, "adapters": ad, "stage1_decision_sha256": R.file_sha(f"{ROOT}/decisions/D24_stage1.json"),
           "extended": 8 in eps, "stage1_extend": st1["extend_to_8_epochs"],
           "v96_runs": {n: {"gen_dir": f"{ROOT}/gen/V96_{n}_e{best}", "requests": f"{ROOT}/requests/requests_V96.jsonl",
                            "protocol": f"{ROOT}/protocol/proto_V96_{n}_e{best}.json"} for n in ("E", "J")},
           "rule": "argmax (E_I + J_J)/2 F1@0.3 on D24; tie -> larger min -> earlier epoch",
           "source_sha256": {"pg48_dsel.py": R.file_sha("pg48_dsel.py")}}
    json.dump(out, open(a.out, "w"), indent=1)
    print(json.dumps({"common_epoch": best, "scores": out["scores_d24"]}, indent=1))


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s1 = sub.add_parser("stage1")
    s1.add_argument("--out", required=True)
    s2 = sub.add_parser("select")
    s2.add_argument("--epochs", nargs="+", type=int, required=True)
    s2.add_argument("--out", required=True)
    a = ap.parse_args()
    {"stage1": stage1, "select": select}[a.cmd](a)


if __name__ == "__main__":
    main()
