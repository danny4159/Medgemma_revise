"""iter_019 요청 행렬. phase1(J_RT,J_TR,A,O,S1)은 manifest만으로 만들 수 있다. S2는 완료된 S1 record가 필요하다 (2단계).

request_id = sha256(patient|condition|label|images(path,file_sha256 순서대로)|prompt|config_digest)[:32].
"""
import argparse
import hashlib
import json
import os

from . import generate, mi19_spec as S

DATA_DIR = "results/iter_021/data"


def sha(b):
    return hashlib.sha256(b if isinstance(b, bytes) else b.encode()).hexdigest()


def req_id(fields):
    return sha(json.dumps(fields, sort_keys=True, default=str))[:32]


def _img(path, file_sha256):
    return {"path": path, "file_sha256": file_sha256}


def make_row(pid, condition, label, images, prompt, cfg_digest, extra=None):
    row = {"id": f"{pid}__{condition}__{label}", "patient": pid, "condition": condition, "label": label,
           "images": images, "prompt": prompt, "prompt_sha256": S.sha(prompt),
           "model_revision": generate.MODEL_REVISION, "config_digest": cfg_digest}
    if extra:
        row["extra"] = extra
    row["request_id"] = req_id({"patient": pid, "condition": condition, "label": label,
                                "images": [(i["path"], i["file_sha256"]) for i in images],
                                "prompt_sha256": row["prompt_sha256"], "config_digest": cfg_digest,
                                "model_revision": row["model_revision"]})
    return row


def build_phase1(manifest, patient_ids, cfg_digest):
    """returns {condition: [rows]} for J_RT, J_TR, A, O, S1."""
    out = {c: [] for c in ("J_RT", "J_TR", "A", "O", "S1")}
    for pid in patient_ids:
        m = manifest[pid]
        r_img = _img(m["R"]["path"], m["R"]["file_sha256"])
        t_img = _img(m["T"]["path"], m["T"]["file_sha256"])
        for inst in m["instances"]:
            lab = inst["label"]
            ref = inst["ref_box_norm"]
            out["J_RT"].append(make_row(pid, "J_RT", lab, [r_img, t_img], S.prompt_J_RT(ref), cfg_digest))
            out["J_TR"].append(make_row(pid, "J_TR", lab, [t_img, r_img], S.prompt_J_TR(ref), cfg_digest))
            out["A"].append(make_row(pid, "A", lab, [t_img], S.prompt_A(ref), cfg_digest))
            out["O"].append(make_row(pid, "O", lab, [t_img], S.prompt_O(inst["point_norm"]), cfg_digest))
            out["S1"].append(make_row(pid, "S1", lab, [r_img, t_img], S.prompt_S1(ref), cfg_digest))
    return out


def build_s2(manifest, patient_ids, cfg_digest, s1_records):
    """s1_records: {request_id: record} (검증된 완료 S1 record). returns [rows]."""
    out = []
    for pid in patient_ids:
        m = manifest[pid]
        t_img = _img(m["T"]["path"], m["T"]["file_sha256"])
        for inst in m["instances"]:
            lab = inst["label"]
            s1_row = make_row(pid, "S1", lab, [_img(m["R"]["path"], m["R"]["file_sha256"]), t_img],
                              S.prompt_S1(inst["ref_box_norm"]), cfg_digest)
            rec = s1_records.get(s1_row["request_id"])
            if rec is None:
                raise RuntimeError(f"missing S1 record for {pid}/{lab}")
            desc = rec["suffix_text_raw"]
            if rec.get("ended_eos"):
                desc = desc[:-len("<end_of_turn>")] if desc.endswith("<end_of_turn>") else desc
            desc = desc.strip()
            row = make_row(pid, "S2", lab, [t_img], S.prompt_S2(desc), cfg_digest,
                          extra={"s1_request_id": rec["request_id"], "s1_ended_eos": rec.get("ended_eos"),
                                 "s1_description_sha256": S.sha(desc)})
            out.append(row)
    return out


def load_rows(path, cfg_digest=None):
    rows = [json.loads(ln) for ln in open(path) if ln.strip()]
    ids = [r["request_id"] for r in rows]
    if len(set(ids)) != len(ids):
        raise RuntimeError(f"duplicate request_id in {path}")
    if cfg_digest:
        for r in rows:
            if r["config_digest"] != cfg_digest:
                raise RuntimeError(f"config_digest mismatch for {r['request_id']}")
            if r.get("model_revision") != generate.MODEL_REVISION:
                raise RuntimeError("model revision differs")
    return rows


def write_rows(rows, path):
    if os.path.exists(path):
        raise RuntimeError(f"{path} exists (not overwriting)")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", required=True, choices=["1", "2"])
    ap.add_argument("--split", required=True, choices=["D", "E", "F"])
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--s1-dir", default=None, help="phase 2: 완료된 S1 gen_worker*.jsonl 디렉터리")
    a = ap.parse_args()
    manifest = json.load(open(f"{DATA_DIR}/manifest.json"))
    split = json.load(open(f"{DATA_DIR}/split.json"))
    pids = split[a.split]
    cfg, _ = generate.static_config()
    if a.phase == "1":
        built = build_phase1(manifest, pids, cfg)
        counts = {}
        for cond, rows in built.items():
            p = f"{a.out_dir}/{a.split}__{cond}.jsonl"
            write_rows(rows, p)
            counts[cond] = len(rows)
        print(json.dumps({"split": a.split, "phase": 1, "counts": counts}))
    else:
        import glob
        s1_records = {}
        for f in sorted(glob.glob(os.path.join(a.s1_dir, "gen_worker*.jsonl"))):
            for ln in open(f):
                if ln.strip():
                    r = json.loads(ln)
                    rid = r["request_id"]
                    if rid in s1_records:
                        raise RuntimeError(f"duplicate S1 request_id {rid} across worker files in {a.s1_dir}")
                    s1_records[rid] = r
        rows = build_s2(manifest, pids, cfg, s1_records)
        p = f"{a.out_dir}/{a.split}__S2.jsonl"
        write_rows(rows, p)
        print(json.dumps({"split": a.split, "phase": 2, "counts": {"S2": len(rows)}}))


if __name__ == "__main__":
    main()
