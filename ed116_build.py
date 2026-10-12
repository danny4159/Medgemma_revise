"""iter_116 표본·요청·protocol·평가 잠금 (결과는 results/iter_116 아래에만, 기존 파일 덮어쓰기 거부).
 select   : 환자 선택(selection.json). GT는 읽지 않는다 (ledger_nogt만 사용).
 requests : TECH(12×4=48), MAIN(174×4=696), RESUME8(TECH의 처음 8행) 요청 파일. 입력 영상 padded pixel hash를 현재 파일에서 재계산한다.
 weights  : 현재 가중치 snapshot 내용 sha256을 iter_108 weights_lock과 대조한다.
 lock     : 평가·명세 코드와 입력의 hash를 잠금 시각과 함께 eval_lock.json에 기록한다 (생성 전).
 protocol : pg43_run.make_protocol (코드 hash·요청 hash·영상 digest·generation config·잠금 파일).
"""
import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path

import ed116_spec as ES
import pg43_run as RUN
from rsna_diag import generate as G

R116 = "results/iter_116"
PROV = f"{R116}/provenance"
LOCKDIR = f"{R116}/lock"
REQ = f"{R116}/requests"
PROTO = f"{R116}/protocol"
SNAP = Path("../hf_cache/hub/models--google--medgemma-1.5-4b-it/snapshots") / G.MODEL_REVISION
WLOCK108 = "results/iter_108/protocol/weights_lock.json"
EVAL_CODE = ["ed116_spec.py", "ed116_eval.py", "ed116_link.py", "ed116_build.py", "ed116_verify.py", "ed116_analyze.py", "test_ed116.py",
             "ev109_extract.py", "ev108_spec.py", "test_ev109_extract.py", "pg43_run.py", "rsna_diag/__init__.py", "rsna_diag/generate.py",
             "rsna_diag/geometry.py", "rsna_diag/prompts.py", "rsna_diag/qa_spec.py", "rsna_diag/metrics.py"]


def fsha(p):
    return RUN.file_sha(p)


def wr(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "x") as f:
        json.dump(obj, f, indent=1, sort_keys=True)


def ledger():
    return json.load(open(f"{PROV}/ledger_nogt.json"))["rows"]


def cmd_select():
    rows = ledger()
    sel = ES.select(rows)
    sel["spec_version"] = ES.SPEC_VERSION
    sel["ledger_nogt_sha256"] = fsha(f"{PROV}/ledger_nogt.json")
    wr(f"{LOCKDIR}/selection.json", sel)
    print(sel["n"])


def make_rows(rows, ids, stage, group_of):
    byid = {r["id"]: r for r in rows}
    out = []
    for rank, i in enumerate(ids):
        r = byid[i]
        draft = ES.answer_K(r)
        if draft is None:
            raise RuntimeError(f"unresolved draft in selected set {i}")
        _, _, pxs = G.load_image(r["image"])
        if RUN.file_sha(r["image"]) != r["file_sha256"]:
            raise RuntimeError(f"image file hash changed {i}")
        for cond in ES.COND_ORDER:
            prompt = ES.build_prompt(cond, r, draft)
            psha = ES.sha(prompt)
            has_img = cond in ES.IMAGE_CONDS
            row = dict(stage=stage, group=group_of[i], cond=cond, patient=i, targets=["O"], kind="correction", donor_patient=None,
                       modality="image" if has_img else "text", image=r["image"] if has_img else None,
                       image_file_sha256=r["file_sha256"] if has_img else None, input_pixel_sha256=pxs if has_img else None,
                       draft=draft, prompt=prompt, prompt_sha256=psha, caps=ES.CAPS,
                       order_key=f"{stage}|{rank:04d}|{ES.COND_ORDER.index(cond)}")
            row["request_id"] = ES.request_id(i, cond, psha, row["input_pixel_sha256"], G.MODEL_REVISION)
            out.append(row)
    return out


def write_jsonl(path, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "x") as f:
        for r in rows:
            f.write(json.dumps(r, sort_keys=True) + "\n")


def cmd_requests():
    rows = ledger()
    sel = json.load(open(f"{LOCKDIR}/selection.json"))
    if sel["ledger_nogt_sha256"] != fsha(f"{PROV}/ledger_nogt.json"):
        sys.exit("selection이 현재 ledger와 다르다")
    group_of = {**{i: "tech" for i in sel["tech"]}, **{i: "mismatch" for i in sel["mismatch"]}, **{i: "control" for i in sel["control"]}}
    tech = make_rows(rows, sel["tech"], "TECH", group_of)
    main = make_rows(rows, sel["mismatch"] + sel["control"], "MAIN", group_of)
    resume8 = sorted(tech, key=lambda r: r["order_key"])[:8]
    for name, rr in (("TECH", tech), ("MAIN", main), ("RESUME8", resume8)):
        write_jsonl(f"{REQ}/{name}.jsonl", rr)
        ids = [r["request_id"] for r in rr]
        assert len(ids) == len(set(ids))
        print(name, len(rr), RUN.file_sha(f"{REQ}/{name}.jsonl"))
    # 입력 누설 검사: 요청에 GT/category가 없다
    txt = open(f"{REQ}/MAIN.jsonl").read()
    assert "category" not in txt and "gt_" not in txt


def cmd_weights():
    now = {p.name: {"sha256": RUN.file_sha(str(p.resolve())), "size": p.resolve().stat().st_size} for p in sorted(SNAP.iterdir())}
    ref = json.load(open(WLOCK108))["files"]
    diff = sorted(k for k in set(now) | set(ref) if now.get(k) != ref.get(k))
    res = dict(snapshot=str(SNAP), revision=G.MODEL_REVISION, n_files=len(now), reference=WLOCK108, reference_sha256=fsha(WLOCK108),
               differences_vs_reference=diff, files=now, checked_at=time.time())
    wr(f"{LOCKDIR}/weights_check.json", res)
    print("weights files", len(now), "diff", diff)
    if diff:
        sys.exit(1)


def lock_files():
    return (EVAL_CODE + [f"{PROV}/ledger_nogt.json", f"{PROV}/gt.json", f"{PROV}/provenance.json", f"{LOCKDIR}/selection.json",
                         f"{LOCKDIR}/weights_check.json"] + [f"{REQ}/{n}.jsonl" for n in ("TECH", "MAIN", "RESUME8")])


def cmd_lock(tests):
    t = time.time()
    d = dict(locked_at_epoch=t, locked_at_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t)), note=
             "생성(TECH/MAIN) 시작 전에 작성. 평가 코드·명세·표본·요청·정답 파일의 hash. 이 시각 이후 생성 결과를 보고 수정하지 않는다.",
             files={f: fsha(f) for f in lock_files() + [tests]}, spec_digest=ES.rules_digest())
    wr(f"{LOCKDIR}/eval_lock.json", d)
    print("locked", d["locked_at_utc"], len(d["files"]))


def cmd_protocol(stage, gate):
    wd = json.load(open(f"{LOCKDIR}/weights_check.json"))
    extra = dict(spec_version=ES.SPEC_VERSION, weights_check_sha256=fsha(f"{LOCKDIR}/weights_check.json"),
                 eval_lock_sha256=fsha(f"{LOCKDIR}/eval_lock.json"), model_revision=G.MODEL_REVISION, n_weight_files=wd["n_files"])
    lock = [f"{LOCKDIR}/eval_lock.json", f"{LOCKDIR}/selection.json", f"{PROV}/ledger_nogt.json", f"{LOCKDIR}/weights_check.json",
            "ed116_spec.py", "ed116_eval.py", "ev109_extract.py", "ev108_spec.py", "rsna_diag/qa_spec.py", "rsna_diag/metrics.py"]
    d = RUN.make_protocol(f"{REQ}/{stage}.jsonl", f"{PROTO}/protocol_{stage}.json", gate=gate, extra=extra, lock=lock)
    print("protocol", stage, RUN.file_sha(f"{PROTO}/protocol_{stage}.json"), d["n_requests"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["select", "requests", "weights", "lock", "protocol"])
    ap.add_argument("--stage")
    ap.add_argument("--gate")
    ap.add_argument("--tests")
    a = ap.parse_args()
    {"select": cmd_select, "requests": cmd_requests, "weights": cmd_weights}.get(a.cmd, lambda: None)() if a.cmd in ("select", "requests", "weights") else None
    if a.cmd == "lock":
        cmd_lock(a.tests)
    if a.cmd == "protocol":
        cmd_protocol(a.stage, a.gate)


if __name__ == "__main__":
    main()
