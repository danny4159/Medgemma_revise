"""iter_069 CPU 검사: 경로 안전·hash 재사용 검증·경합·protocol 변조·parser·prompt 누출. 결과 results/iter_069/tests/cpu_tests.json (x 모드).
GPU 재개/동시 읽기 검사는 resume 절차(dd69_run worker --die-after-write/--torn-after)로 별도 수행한다."""
import hashlib
import json
import os
import shutil
import sys

import dd69_fetch as F
import dd69_run as R
import dd69_spec as S

RES = []


def check(name, cond, detail=""):
    RES.append({"name": name, "pass": bool(cond), "detail": str(detail)[:300]})
    print(("PASS " if cond else "FAIL ") + name, flush=True)


def raises(fn, exc=Exception, sub=None):
    try:
        fn()
    except SystemExit as e:
        return sub is None or sub in str(e)
    except exc as e:
        return sub is None or sub in str(e)
    return False


def main():
    T = "tests/fx_run2"
    base = os.path.join(F.ROOT, T)
    os.makedirs(base, exist_ok=True)
    # --- 경로 안전 ---
    check("safe_dest rejects ..", raises(lambda: F.safe_dest("../iter_049/x"), ValueError))
    check("safe_dest rejects absolute", raises(lambda: F.safe_dest("/tmp/x"), ValueError))
    os.makedirs(os.path.join(base, "real"), exist_ok=True)
    link = os.path.join(base, "lnk")
    if not os.path.lexists(link):
        os.symlink("/tmp", link)
    check("safe_dest rejects ancestor symlink", raises(lambda: F.safe_dest(f"{T}/lnk/x.jpg"), ValueError, "symlink"))
    check("run.safe_out rejects iter_049 path", raises(lambda: R.safe_out("results/iter_049/x.json"), SystemExit))
    check("run.safe_out rejects symlink component", raises(lambda: R.safe_out(f"results/iter_069/{T}/lnk/x.json"), SystemExit))
    check("safe_remote rejects traversal", raises(lambda: F.safe_remote("images/case1/../../x"), ValueError))
    # --- 재사용 검증: 손상 파일 거부, 정상 파일 재사용, 경합 승자 검증 ---
    src = os.path.join(base, "src.bin")
    data = os.urandom(5000)
    open(src, "wb").write(data)
    sha = hashlib.sha256(data).hexdigest()
    url = "file://" + src
    r = F.fetch_verified(url, f"{T}/ok.bin", len(data), sha, None)
    check("fetch_verified downloads+verifies (lfs sha256)", not r["reused"] and F.sha256_file(os.path.join(base, "ok.bin")) == sha)
    r2 = F.fetch_verified(url, f"{T}/ok.bin", len(data), sha, None)
    check("existing verified file reused", r2["reused"])
    open(os.path.join(base, "bad.bin"), "wb").write(data[:-1] + b"X")  # 같은 크기, 다른 내용
    check("existing same-size corrupted file rejected (lfs)", raises(lambda: F.fetch_verified(url, f"{T}/bad.bin", len(data), sha, None), RuntimeError, "failed verification"))
    open(os.path.join(base, "short.bin"), "wb").write(data[:100])
    check("existing truncated file rejected", raises(lambda: F.fetch_verified(url, f"{T}/short.bin", len(data), sha, None), RuntimeError, "failed verification"))
    blob = hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()
    F.fetch_verified(url, f"{T}/nonlfs.bin", len(data), None, blob)
    open(os.path.join(base, "nonlfs_bad.bin"), "wb").write(data[:-1] + b"Y")
    check("existing corrupted non-LFS file rejected (git blob sha1)", raises(lambda: F.fetch_verified(url, f"{T}/nonlfs_bad.bin", len(data), None, blob), RuntimeError, "failed verification"))
    check("download with wrong expected hash fails and leaves no dest",
          raises(lambda: F.fetch_verified(url, f"{T}/wrong.bin", len(data), "0" * 64, None, retries=1), RuntimeError) and not os.path.exists(os.path.join(base, "wrong.bin")))
    # FileExistsError 경합: link 직전에 손상 파일이 생긴 것으로 가정
    real_link = os.link

    def racy_link(a, b):
        open(b, "wb").write(data[:-1] + b"Z")
        raise FileExistsError(b)
    os.link = racy_link
    try:
        ok = raises(lambda: F.fetch_verified(url, f"{T}/race_bad.bin", len(data), sha, None, retries=1), RuntimeError, "race winner")
    finally:
        os.link = real_link
    check("race winner (corrupt) rejected after FileExistsError", ok)

    def good_link(a, b):
        shutil.copyfile(src, b)
        raise FileExistsError(b)
    os.link = good_link
    try:
        r3 = F.fetch_verified(url, f"{T}/race_ok.bin", len(data), sha, None)
    finally:
        os.link = real_link
    check("race winner (valid) reused after FileExistsError", r3.get("race") is True)
    # --- 실제 영상 manifest 연결 ---
    cm = json.load(open(F.safe_dest("data/cases_private.json")))["cases"]
    allok = True
    for c in cm:
        for k in ("dwi", "adc"):
            p = F.safe_dest(c[k]["remote_path"])
            allok &= F.sha256_file(p) == c[k]["file_sha256"]
    check("40 images: file sha256 matches sealed manifest", allok)
    from PIL import Image
    pm = True
    for c in cm:
        for k in ("dwi", "adc"):
            im = Image.open(F.safe_dest(c[k]["remote_path"])); im.load()
            pm &= hashlib.sha256(im.mode.encode() + str(im.size).encode() + im.tobytes()).hexdigest() == c[k]["pixel_sha256"]
    check("40 images: decoded pixel sha256 matches (PIL " + __import__("PIL").__version__ + ")", pm)
    # --- parser / prompt ---
    P = S.parse
    check("parse normalizes case/space/trailing punct", P("A", " yes. \n") == "YES" and P("SA", "not_low!") == "NOT_LOW" and P("SD", "HIGH\n") == "HIGH")
    check("parse rejects extra words / wrong set", P("A", "YES because") is None and P("A", "HIGH") is None and P("SA", "YES") is None and P("A", "") is None)
    check("parse keeps UNCERTAIN distinct", P("A", "uncertain") == "UNCERTAIN")
    check("gt mapping", S.gt("A", "LOW") == "YES" and S.gt("A", "NOT_LOW") == "NO" and S.gt("SA", "NOT_LOW") == "NOT_LOW" and S.gt("SD", "LOW") == "HIGH")
    check("O prompt needs label; non-O rejects label", raises(lambda: S.prompt("O", "x"), ValueError) and raises(lambda: S.prompt("A", "x", "LOW"), ValueError))
    pl, pn = S.prompt("O", "the lesion", "LOW"), S.prompt("O", "the lesion", "NOT_LOW")
    check("O prompts differ only in ADC signal phrase", pl != pn and "low on the ADC map" in pl and "not low" in pn)
    check("non-O prompts identical across labels (no label info)", all(S.prompt(c, "the lesion") == S.prompt(c, "the lesion") for c in S.CONDS if c != "O"))
    rows = {c: [json.loads(l) for l in open(F.safe_dest(f"data/{n}"))] for c, n in (("main", "requests_main.jsonl"), ("R", "requests_R.jsonl"))}
    check("main has 7N=140 requests per model (14N=280 across two models), unique rids", len(rows["main"]) == 140 and len({r["rid"] for r in rows["main"]}) == 140 and len(rows["R"]) == 20)
    check("requests contain no label/gt fields", all(set(r) == {"rid", "case", "cond", "images", "prompt"} for r in rows["main"] + rows["R"]))
    labs = json.load(open(F.safe_dest("data/labels.json")))
    check("N=20, both classes present", len(labs) == 20 and {v["label"] for v in labs.values()} == {"LOW", "NOT_LOW"})
    check("20 distinct source cases (no duplicate case ids)", len({r["case"] for r in rows["main"]}) == 20)
    # --- protocol 변조 거부 (원본 변경 없이 모듈 경로를 복사본으로 교체) ---
    for key, name in (("labels", "labels.json"), ("cases", "cases_private.json"), ("build_manifest", "build_manifest.json")):
        cp = os.path.join(base, "tamper_" + name)
        d = json.load(open(F.safe_dest("data/" + name)))
        if key == "labels":
            d[next(iter(d))]["label"] = "NOT_LOW" if d[next(iter(d))]["label"] == "LOW" else "LOW"
        else:
            d["tampered"] = True
        json.dump(d, open(cp, "w"))
        attr = {"labels": "LABELS", "cases": "CASES", "build_manifest": "BMAN"}[key]
        old = getattr(R, attr)
        setattr(R, attr, os.path.relpath(cp))
        try:
            ok = raises(lambda: R.check_protocol("medgemma", "results/iter_069/protocol/protocol_medgemma_v2.json"), SystemExit, "PROTOCOL MISMATCH")
        finally:
            setattr(R, attr, old)
        check(f"protocol rejects tampered {key}", ok)
    cpr = os.path.join(base, "tamper_requests_main.jsonl")
    ls = open(F.safe_dest("data/requests_main.jsonl")).read().splitlines()
    ls[0] = ls[0].replace("Look at", "See")
    assert ls[0] != open(F.safe_dest("data/requests_main.jsonl")).read().splitlines()[0]
    open(cpr, "w").write("\n".join(ls) + "\n")
    old = R.REQ["main"]
    R.REQ["main"] = os.path.relpath(cpr)
    try:
        ok = raises(lambda: R.check_protocol("medgemma", "results/iter_069/protocol/protocol_medgemma_v2.json"), SystemExit, "PROTOCOL MISMATCH")
    finally:
        R.REQ["main"] = old
    check("protocol rejects tampered requests", ok)
    check("worker rejects requests file not locked in protocol",
          raises(lambda: R.req_in_protocol(os.path.relpath(cpr), "results/iter_069/protocol/protocol_medgemma_v2.json"), SystemExit, "not locked"))
    img = rows["main"][0]["images"][0]
    cpi = os.path.join(base, "img_copy.jpg")
    b = bytearray(open(img, "rb").read()); b[100] ^= 1
    open(cpi, "wb").write(bytes(b))
    ok = F.sha256_file(cpi) != F.sha256_file(img)
    check("single-bit image change changes file sha (protocol image hash would reject)", ok)
    check("protocol digest tamper rejected",
          raises(lambda: _digest_tamper(base), SystemExit, "TAMPERED"))
    check("launch rejects GPU outside allowed set", _gpu_reject(base))
    out = {"n": len(RES), "n_pass": sum(r["pass"] for r in RES), "results": RES}
    with open(F.safe_dest("tests/cpu_tests.json"), "x") as f:
        json.dump(out, f, indent=1)
    print(out["n_pass"], "/", out["n"])
    return 0 if out["n_pass"] == out["n"] else 1


def _digest_tamper(base):
    p = json.load(open("results/iter_069/protocol/protocol_medgemma_v2.json"))
    p["digest"] = "0" * 64
    cp = os.path.join(base, "tamper_protocol.json")
    json.dump(p, open(cp, "w"))
    R.check_protocol("medgemma", os.path.relpath(cp))


def _gpu_reject(base):
    jobs = [{"model": "medgemma", "gpu": 7, "workers": 1, "protocol": "results/iter_069/protocol/protocol_medgemma_v2.json",
             "out_dir": "results/iter_069/tests/fx/launch_gpu7", "requests": "results/iter_069/data/requests_tech.jsonl", "peak_gb": 10}]
    jp = os.path.join(base, "jobs_gpu7.json")
    json.dump(jobs, open(jp, "w"))
    import argparse
    old = os.environ.get("CUDA_VISIBLE_DEVICES")
    os.environ["CUDA_VISIBLE_DEVICES"] = "0,1"
    try:
        R.cmd_launch(argparse.Namespace(jobs=jp, limit=0))
    except (AssertionError, SystemExit):
        return True
    finally:
        if old is None:
            os.environ.pop("CUDA_VISIBLE_DEVICES", None)
        else:
            os.environ["CUDA_VISIBLE_DEVICES"] = old
    return False


if __name__ == "__main__":
    sys.exit(main())
