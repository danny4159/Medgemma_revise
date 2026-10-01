"""iter_048 요청 행렬 생성 (CPU). 요청은 adapter와 무관하다(adapter는 protocol에 잠긴다). GT/labels는 읽지 않는다.

  python pg48_requests.py --out-dir results/iter_048/requests
환자 x {I-short qA, I-short qB, J-short AB(qA 먼저), J-short-rev BA(qB 먼저)}: D24 96 / V96 384 / D8(D24 앞 8 지정 환자) 32.
기존 iter_041 요청(C의 V96 J, D24)과 prompt·caps·영상·hash가 같은지 대조해 summary에 남긴다(request_id 규칙 pg39_spec.request_id와 kind 동일 -> 같은 행은 같은 id).
"""
import argparse
import hashlib
import json
import os
import sys

import pg39_spec as S

MAN = "results/iter_043/data/manifest_private.json"
OLD = {"D24": "results/iter_041/requests/requests_D24_C.jsonl", "V96": ["results/iter_041/requests/requests_V96_JAB.jsonl",
                                                                    "results/iter_041/requests/requests_V96_JBA.jsonl"]}


def sha(s):
    return hashlib.sha256(s.encode()).hexdigest()


def rows_for(kind, ents):
    out = []
    for e in ents:
        sents = e["sentences"]
        okey = sha(e["PatientID"])
        base = {"kind": kind, "patient": e["PatientID"], "image_id": e["ImageID"], "image": e["image"], "image_file_sha256": e["image_file_sha256"],
                "input_pixel_sha256": e["input_pixel_sha256"], "modality": "image"}
        for t in ("qA", "qB"):
            p = S.prompt_I_short(sents[t], t)
            out.append(dict(base, cond="I-short", targets=[t], prompt=p, prompt_sha256=sha(p), caps=list(S.CAPS_IC), order_key=f"{okey}_I_{t}"))
        pab = S.prompt_J_short([("qA", sents["qA"]), ("qB", sents["qB"])])
        pba = S.prompt_J_short([("qB", sents["qB"]), ("qA", sents["qA"])])
        out.append(dict(base, cond="J-short", targets=["qA", "qB"], prompt=pab, prompt_sha256=sha(pab), caps=list(S.CAPS_J), order_key=f"{okey}_JAB"))
        out.append(dict(base, cond="J-short-rev", targets=["qA", "qB"], prompt=pba, prompt_sha256=sha(pba), caps=list(S.CAPS_J), order_key=f"{okey}_JBA"))
    for r in out:
        r["request_id"] = S.request_id(r["kind"], r["patient"], r["cond"], r["targets"], r["prompt_sha256"], r["image_file_sha256"])
    ids = [r["request_id"] for r in out]
    if len(ids) != len(set(ids)):
        raise RuntimeError("duplicate request ids")
    return out


def write_new(path, rows):
    if os.path.exists(path):
        raise RuntimeError(f"exists: {path}")
    tmp = path + f".{os.getpid()}.tmp"
    with open(tmp, "w") as f:
        for r in sorted(rows, key=lambda r: r["order_key"]):
            f.write(json.dumps(r) + "\n")
    os.replace(tmp, path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", required=True)
    a = ap.parse_args()
    os.makedirs(a.out_dir, exist_ok=True)
    man = json.load(open(MAN))
    d24, v96 = man["D24"], man["V96"]
    d8set = set(man["D8"])
    built = {"D24": rows_for("D24", d24), "V96": rows_for("V96", v96), "D8": rows_for("D8", [e for e in d24 if e["PatientID"] in d8set])}
    summ = {"counts": {k: len(v) for k, v in built.items()}, "manifest_sha256": hashlib.sha256(open(MAN, "rb").read()).hexdigest()}
    # iter_041 대조
    cmpres = {}
    for k, files in (("D24", [OLD["D24"]]), ("V96", OLD["V96"])):
        old = [json.loads(l) for fn in files for l in open(fn) if l.strip()]
        new = {(r["patient"], r["cond"], tuple(r["targets"])): r for r in built[k]}
        mism, matched = [], 0
        for o in old:
            n = new.get((o["patient"], o["cond"], tuple(o["targets"])))
            if n is None or any(n[f] != o[f] for f in ("prompt", "prompt_sha256", "caps", "image", "image_file_sha256", "input_pixel_sha256", "request_id")):
                mism.append(o["request_id"])
            else:
                matched += 1
        cmpres[k] = {"old_rows": len(old), "matched_identical_fields_incl_request_id": matched, "mismatch": mism}
    summ["compare_with_iter_041_requests"] = cmpres
    for k, rows in built.items():
        write_new(os.path.join(a.out_dir, f"requests_{k}.jsonl"), rows)
    summ["file_sha256"] = {f"requests_{k}.jsonl": hashlib.sha256(open(os.path.join(a.out_dir, f"requests_{k}.jsonl"), "rb").read()).hexdigest() for k in built}
    json.dump(summ, open(os.path.join(a.out_dir, "summary.json"), "x"), indent=1)
    print(json.dumps(summ, indent=1))
    if any(v["mismatch"] for v in cmpres.values()):
        sys.exit("mismatch with iter_041 requests")


if __name__ == "__main__":
    main()
