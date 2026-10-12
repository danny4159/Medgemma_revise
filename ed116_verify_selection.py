"""iter_116 선택·분모 독립 재계산: ledger/ed116_link를 쓰지 않고 iter_016 원 응답, iter_035 detector 원 예측, iter_012 SFT 원 출력, labels에서
직접 87/505/8 분모와 정답 구성을 다시 만든다 (답 추출은 승인된 ev109_extract.resolve만 재사용).
사용: python ed116_verify_selection.py <출력 json> ('x' 모드)"""
import glob
import hashlib
import json
import sys

import ev108_spec as S
import ev109_extract as X

R = "results"


def jl(p):
    return [json.loads(x) for x in open(p) if x.strip()]


def main(out):
    sets = json.load(open(f"{R}/iter_016/manifests/sets.json"))["E600"]
    labels = json.load(open(f"{R}/iter_016/manifests/labels.json"))
    ids = sorted(i for v in sets.values() for i in v)
    O = {}
    for st in ("e180_plain", "e600x_plain"):
        reqs = {q["request_id"]: q for q in jl(f"{R}/iter_016/requests/{st}__M0.jsonl")}
        for f in sorted(glob.glob(f"{R}/iter_016/gen/{st}__M0/gen_worker*.jsonl")):
            for r in jl(f):
                q = reqs[r["request_id"]]
                if q["target"] == "O":
                    O[q["id"]] = (r["suffix_text_raw"], r["ended_eos"])
    det = json.load(open(f"{R}/iter_035/confirm800/det17/raw_preds.json"))
    sft = {}
    for f in sorted(glob.glob(f"{R}/iter_012/confirm_sft_seed17/gen_worker*.jsonl")):
        for r in jl(f):
            if r.get("prompt_name") == "concise":
                sft[r["id"]] = (r["suffix_text_raw"], r["ended_eos"])
    K, B, unres, mism, agree = {}, {}, [], [], []
    for i in ids:
        k = X.resolve("O", *O[i])["answer"]
        b = "yes" if any(s >= 0.70 for s in det[i]["scores"]) else "no"
        K[i], B[i] = k, b
        if k is None:
            unres.append(i)
        elif k != b:
            mism.append(i)
        else:
            agree.append(i)
    y = {i: ("yes" if labels[i]["category"] == "opacity" else "no") for i in ids}
    agree.sort(key=lambda i: hashlib.sha256(("iter116|" + labels[i]["patient"]).encode()).hexdigest())
    sel = json.load(open(f"{R}/iter_116/lock/selection.json"))
    G = {}
    for i in mism + agree:
        st, _ = S.parse_saved_bbox(*sft[i])
        G[i] = {"ok": "yes", "empty": "no"}.get(st)
    res = dict(
        n_E600=len(ids), n_unresolved=len(unres), n_mismatch=len(mism), n_agree=len(agree),
        mismatch_K_correct=sum(K[i] == y[i] for i in mism), mismatch_B_correct=sum(B[i] == y[i] for i in mism),
        mismatch_K_wrong_B_correct=sum(K[i] != y[i] and B[i] == y[i] for i in mism),
        agree_both_correct=sum(K[i] == y[i] for i in agree), agree_both_wrong=sum(K[i] != y[i] for i in agree),
        mismatch_G_yes=sum(G[i] == "yes" for i in mism), mismatch_G_no=sum(G[i] == "no" for i in mism), mismatch_G_unresolved=sum(G[i] is None for i in mism),
        control_G_unresolved=sum(G[i] is None for i in agree[12:99]),
        category_mismatch={c: sum(labels[i]["category"] == c for i in mism) for c in ("opacity", "normal", "not_normal_no_opacity")},
        category_control={c: sum(labels[i]["category"] == c for i in agree[12:99]) for c in ("opacity", "normal", "not_normal_no_opacity")},
        control_K_correct=sum(K[i] == y[i] for i in agree[12:99]),
        selection_matches_locked=(sorted(mism) == sorted(sel["mismatch"]) and agree[:12] == sel["tech"] and agree[12:99] == sel["control"] and sorted(unres) == sorted(sel["unresolved"])),
        disjoint_tech_control_mismatch=not (set(agree[:12]) & set(agree[12:99])) and not (set(mism) & set(agree[:99])))
    json.dump(res, open(out, "x"), indent=1)
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main(sys.argv[1])
