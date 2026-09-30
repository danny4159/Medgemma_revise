"""iter_043 요청 파일 생성 (CPU only). GT는 요청에 넣지 않는다 (prompt에는 문장만, 영상은 해당 조건의 영상만).
python pg43_requests.py --out-dir results/iter_043/requests

D8_M0 / D8_C : D8 환자 x 두 문장의 I-short 실제 영상(kind D8) + text-only(kind D8) [+ C만 self-swap 회귀 8건(kind swap, donor==recipient)]
MAIN_M0 / MAIN_C : V96 text-only 192건(kind V96text) + 21쌍 양방향 영상 교환 42건(kind swap)
실제 영상 조건은 새로 생성하지 않고 기존 출력(M0: iter_039 E96, C: iter_040/041)을 재사용한다.
"""
import argparse
import hashlib
import json
import os
import sys

import pg39_spec as S39
import pg43_prep as PREP

CAPS = S39.CAPS_IC


def sha(s):
    return hashlib.sha256(s.encode()).hexdigest()


def row(kind, cond, patient, target, sent, modality, img_entry, donor=None, recipient_entry=None, self_swap=False):
    prompt = S39.prompt_I_short(sent, target)
    psha = sha(prompt)
    if modality == "image":
        marker = img_entry["input_pixel_sha256"]
        extra = {"image": img_entry["image"], "image_file_sha256": img_entry["image_file_sha256"],
                 "input_pixel_sha256": img_entry["input_pixel_sha256"], "image_id": img_entry["ImageID"]}
    else:
        marker = "TEXT_ONLY"
        extra = {"image": None, "image_file_sha256": None, "input_pixel_sha256": None, "image_id": None}
    if donor:
        marker += f"|donor={donor}"
    rid = S39.request_id(kind, patient, cond, [target], psha, marker)
    r = {"request_id": rid, "kind": kind, "modality": modality, "patient": patient, "cond": cond, "targets": [target],
         "prompt": prompt, "prompt_sha256": psha, "caps": CAPS, "donor_patient": donor,
         "recipient_image_id": recipient_entry["ImageID"] if recipient_entry else None,
         "order_key": sha("4305|" + rid)}
    r.update(extra)
    if self_swap:
        r["self_swap_regression"] = True
    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", required=True)
    a = ap.parse_args()
    man = json.load(open("results/iter_043/data/manifest_private.json"))
    v96 = {e["PatientID"]: e for e in man["V96"]}
    d24 = {e["PatientID"]: e for e in man["D24"]}
    d8 = [d24[p] for p in man["D8"]]
    out = {}
    real8, text8 = [], []
    for e in d8:
        for t in ("qA", "qB"):
            real8.append(row("D8", "I-short", e["PatientID"], t, e["sentences"][t], "image", e))
            text8.append(row("D8", "I-short-text", e["PatientID"], t, e["sentences"][t], "text", None))
    selfswap = [row("swap", "I-short-selfswap", e["PatientID"], "qA", e["sentences"]["qA"], "image", e, donor=e["PatientID"],
                    recipient_entry=e, self_swap=True) for e in d8]
    out["D8_M0"] = real8 + text8
    out["D8_C"] = real8 + text8 + selfswap
    text96 = [row("V96text", "I-short-text", e["PatientID"], t, e["sentences"][t], "text", None)
              for e in man["V96"] for t in ("qA", "qB")]
    swaps = []
    for p in man["pairs"]:
        for rec, don in ((p["a"], p["b"]), (p["b"], p["a"])):
            er, ed = v96[rec["PatientID"]], v96[don["PatientID"]]
            swaps.append(row("swap", "I-short-swap", er["PatientID"], rec["qID"], er["sentences"][rec["qID"]], "image", ed,
                             donor=ed["PatientID"], recipient_entry=er))
    assert len(text96) == 192 and len(swaps) == 42
    out["MAIN_M0"] = text96 + swaps
    out["MAIN_C"] = text96 + swaps
    os.makedirs(a.out_dir, exist_ok=True)
    summ = {}
    for name, rows in out.items():
        p = os.path.join(a.out_dir, f"requests_{name}.jsonl")
        if os.path.exists(p):
            sys.exit(f"exists {p}")
        ids = [r["request_id"] for r in rows]
        assert len(ids) == len(set(ids))
        with open(p, "w") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")
        summ[name] = {"n": len(rows), "sha256": PREP.fsha(p),
                      "by_kind_cond": {f"{k}|{c}": sum(1 for r in rows if (r["kind"], r["cond"]) == (k, c))
                                       for k, c in sorted({(r["kind"], r["cond"]) for r in rows})}}
    # 기존 실제 영상 요청과 재구성 행의 대조 (D8: M0=iter_039 D_v2, C=iter_041 D24_C)
    old = {"M0": PREP.read_jsonl("results/iter_039/requests_v2/requests_D.jsonl"),
           "C": PREP.read_jsonl("results/iter_041/requests/requests_D24_C.jsonl")}
    chk = {}
    for m, orows in old.items():
        omap = {(r["patient"], tuple(r["targets"])): r for r in orows if r["cond"] == "I-short"}
        bad = 0
        for r in real8:
            o = omap[(r["patient"], tuple(r["targets"]))]
            bad += not (o["prompt_sha256"] == r["prompt_sha256"] and o["image"] == r["image"] and o["image_file_sha256"] == r["image_file_sha256"]
                        and o["input_pixel_sha256"] == r["input_pixel_sha256"] and o["caps"] == r["caps"])
        chk[m] = {"n_checked": len(real8), "mismatch": bad}
    assert all(v["mismatch"] == 0 for v in chk.values()), chk
    # 교환 행의 prompt는 원래 수신자 요청(V96 real)의 prompt와 동일해야 한다
    oldv = {(r["patient"], tuple(r["targets"])): r for r in PREP.read_jsonl("results/iter_040/requests/requests_V96.jsonl") if r["cond"] == "I-short"}
    swap_bad = sum(oldv[(r["patient"], tuple(r["targets"]))]["prompt_sha256"] != r["prompt_sha256"] for r in swaps)
    text_bad = sum(oldv[(r["patient"], tuple(r["targets"]))]["prompt_sha256"] != r["prompt_sha256"] for r in text96)
    summ["reconstruction_check"] = {"D8_real_vs_old": chk, "swap_prompt_vs_V96_real_mismatch": swap_bad, "text_prompt_vs_V96_real_mismatch": text_bad}
    assert swap_bad == 0 and text_bad == 0
    json.dump(summ, open(os.path.join(a.out_dir, "summary.json"), "x"), indent=1)
    print(json.dumps(summ, indent=1))


if __name__ == "__main__":
    main()
