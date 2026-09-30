"""iter_041 요청 파일 생성 (CPU only). 기존 iter_039 D24 / iter_040 V96 manifest를 그대로 읽고 새 요청만 만든다. GT는 읽지 않는다.

조건: I-short(qA,qB 각 1요청) / J-short(AB: qA→qB 순) / J-short-rev(BA: qB→qA 순, 문장에 붙은 qA/qB ID는 유지).
파일:
  requests_D24_C.jsonl   D24 x {I-short qA,qB, J-short, J-short-rev} = 96   (동작 확인 + 2/4 worker 구성 선택, C adapter)
  requests_D8_B.jsonl    D8  x 같은 4조건 = 32                            (동작 확인, B adapter)
  requests_V96_JAB.jsonl / requests_V96_JBA.jsonl  V96 x 1 = 96씩         (B, C 모두 사용)
  requests_V96_Icost.jsonl  V96 I-short 192 (C 비용 계측용 재실행, 새 request_id)

python pg41_build.py --out-dir results/iter_041/requests
"""
import argparse
import hashlib
import json
import os
import sys

import pg39_spec as S
from rsna_diag import generate as G

M39 = "results/iter_039/data/manifest_private.jsonl"
M40_EVAL = "results/iter_040/data/manifest_eval_private.jsonl"
LOCK40 = "results/iter_040/data/selection_lock.json"
OLD_REQ = {"D": "results/iter_039/requests_v2/requests_D.jsonl", "E96": "results/iter_039/requests_v2/requests_E96.jsonl",
           "V96I": "results/iter_040/requests/requests_V96.jsonl"}
COND_AB, COND_BA = "J-short", "J-short-rev"


def sha_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 22), b""):
            h.update(b)
    return h.hexdigest()


def rd(p):
    return [json.loads(l) for l in open(p) if l.strip()]


def order_key(patient, tag):
    return hashlib.sha256(f"iter041|{patient}".encode()).hexdigest() + "_" + tag


def mk(kind, m, cond, targets, prompt, caps, tag):
    imp = m["image_meta"]["path"]
    psha = hashlib.sha256(prompt.encode()).hexdigest()
    fsha = sha_file(imp)
    px = G.load_image(imp)[2]
    return {"request_id": S.request_id(kind, m["PatientID"], cond, targets, psha, fsha), "kind": kind, "patient": m["PatientID"],
            "image_id": m["ImageID"], "cond": cond, "targets": targets, "prompt": prompt, "prompt_sha256": psha, "caps": caps,
            "image": imp, "image_file_sha256": fsha, "input_pixel_sha256": px, "order_key": order_key(m["PatientID"], tag)}


def rows_for(kind, m, conds, i_kind=None):
    s = m["sentences"]
    out = []
    ik = i_kind or kind
    if "I" in conds:
        for pid in ("qA", "qB"):
            out.append(mk(ik, m, "I-short", [pid], S.prompt_I_short(s[pid], pid), S.CAPS_IC, f"I_{pid}"))
    if "AB" in conds:
        out.append(mk(kind, m, COND_AB, ["qA", "qB"], S.prompt_J_short([("qA", s["qA"]), ("qB", s["qB"])]), S.CAPS_J, "JAB"))
    if "BA" in conds:
        out.append(mk(kind, m, COND_BA, ["qA", "qB"], S.prompt_J_short([("qB", s["qB"]), ("qA", s["qA"])]), S.CAPS_J, "JBA"))
    return out


def d8_select(dm):
    """D24에서 층을 포함한 hash 순서의 D8: share1 두 환자 전부 + share0_multi1 앞 3 + share0_multi0 앞 3 (환자 hash 오름차순)."""
    h = lambda m: hashlib.sha256(f"D8|{m['PatientID']}".encode()).hexdigest()
    by = {}
    for m in sorted(dm, key=h):
        by.setdefault(m["stratum"], []).append(m)
    sel = by["share1_multi0"] + by["share1_multi1"] + by["share0_multi1"][:3] + by["share0_multi0"][:3]
    assert len(sel) == 8
    return sel


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", required=True)
    a = ap.parse_args()
    if os.path.exists(a.out_dir) and os.listdir(a.out_dir):
        sys.exit("out-dir not empty")
    os.makedirs(a.out_dir, exist_ok=True)
    lock = json.load(open(LOCK40))
    if sha_file(M40_EVAL) != lock["manifest_eval_sha256"] or sha_file(M39) != lock["iter039_manifest_sha256"]:
        sys.exit("manifest hash != selection_lock")
    dm = [m for m in rd(M39) if m["subset"] == "D"]
    vm = [m for m in rd(M40_EVAL) if m["eval_set"] == "V96"]
    assert len(dm) == 24 and len(vm) == 96 and len({m["PatientID"] for m in vm}) == 96
    files = {}
    files["requests_D24_C.jsonl"] = [r for m in dm for r in rows_for("D24", m, ("I", "AB", "BA"))]
    files["requests_D8_B.jsonl"] = [r for m in d8_select(dm) for r in rows_for("D8", m, ("I", "AB", "BA"))]
    files["requests_V96_JAB.jsonl"] = [r for m in vm for r in rows_for("V96", m, ("AB",))]
    files["requests_V96_JBA.jsonl"] = [r for m in vm for r in rows_for("V96", m, ("BA",))]
    files["requests_V96_Icost.jsonl"] = [r for m in vm for r in rows_for("V96cost", m, ("I",))]
    # 기존 요청과의 대조: I-short는 (환자,target)별 prompt·영상 hash가 기존과 같아야 하고, J-short(AB)는 iter_039 E96/D 요청과 같아야 한다.
    old = {}
    for k, p in OLD_REQ.items():
        for r in rd(p):
            old[(r["patient"], r["cond"], tuple(r["targets"]))] = r
    chk = {"I_short_vs_old": 0, "J_short_AB_vs_old": 0, "mismatch": []}
    for fn, rows in files.items():
        for r in rows:
            key = (r["patient"], r["cond"], tuple(r["targets"]))
            if r["cond"] in ("I-short", "J-short") and key in old:
                o = old[key]
                same = all(o[k] == r[k] for k in ("prompt_sha256", "image_file_sha256", "input_pixel_sha256", "caps", "image"))
                chk["I_short_vs_old" if r["cond"] == "I-short" else "J_short_AB_vs_old"] += 1
                if not same:
                    chk["mismatch"].append([fn, r["request_id"]])
    for fn, rows in files.items():
        ids = [r["request_id"] for r in rows]
        assert len(ids) == len(set(ids)), fn
        with open(os.path.join(a.out_dir, fn), "x") as f:
            for r in sorted(rows, key=lambda r: r["order_key"]):
                f.write(json.dumps(r) + "\n")
    # J-short-rev는 AB와 같은 문장·ID를 순서만 바꾼 것이어야 한다.
    for m in vm[:3] + dm[:3]:
        ab = rows_for("x", m, ("AB",))[0]["prompt"]
        ba = rows_for("x", m, ("BA",))[0]["prompt"]
        s = m["sentences"]
        assert ab.index(f'qA: "{s["qA"]}"') < ab.index(f'qB: "{s["qB"]}"')
        assert ba.index(f'qB: "{s["qB"]}"') < ba.index(f'qA: "{s["qA"]}"') and 'qA: "' in ba and 'qB: "' in ba
    summ = {"counts": {k: len(v) for k, v in files.items()}, "d8_patients": [m["PatientID"] for m in d8_select(dm)],
            "d8_strata": [m["stratum"] for m in d8_select(dm)], "old_request_crosscheck": chk,
            "file_sha256": {k: sha_file(os.path.join(a.out_dir, k)) for k in files},
            "manifest_sha256": {M39: sha_file(M39), M40_EVAL: sha_file(M40_EVAL)},
            "planned_generation_requests": {"D24_C_two_configs(2w+4w)": 2 * len(files["requests_D24_C.jsonl"]),
                                            "D8_B": len(files["requests_D8_B.jsonl"]),
                                            "V96_J_B_and_C": 2 * (len(files["requests_V96_JAB.jsonl"]) + len(files["requests_V96_JBA.jsonl"])),
                                            "V96_I_cost_C": len(files["requests_V96_Icost.jsonl"])}}
    summ["planned_total"] = sum(summ["planned_generation_requests"].values())
    json.dump(summ, open(os.path.join(a.out_dir, "summary.json"), "x"), indent=1)
    print(json.dumps(summ, indent=1))
    if chk["mismatch"]:
        sys.exit("old request mismatch")


if __name__ == "__main__":
    main()
