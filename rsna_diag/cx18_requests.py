"""iter_018 target-scope 진단(CheXpert) 요청 행렬. qa_requests.make_row/load_rows/RequestError를 그대로 재사용해
request_id 계산·검증(qa_gen이 내부에서 호출하는 qa_requests.verify_row)을 RSNA 요청과 동일한 방식으로 공유한다.

환자당 방향(main/aux) x 조건(D/U/T/Tscope) = 8개 요청. target 필드에는 방향 이름(main/aux)을 쓴다(질문 finding은
cx18_spec.DIRECTIONS로 방향에서 유도되므로 별도 인코딩이 필요 없다). checkpoint는 항상 M0(base, adapter 없음)다.
사용: python -m rsna_diag.cx18_requests build --stage d16 --set D16 --fmt plain
"""
import argparse
import json
import os

from . import cx18_spec as CX, qa_protocol, qa_requests as Q

OUT = "results/iter_018"
CKPT = "M0"


def load_manifest():
    man = {}
    for ln in open(f"{OUT}/manifests/infer_manifest.jsonl"):
        r = json.loads(ln)
        if r["id"] in man:
            raise Q.RequestError(f"duplicate id in infer_manifest: {r['id']}")
        man[r["id"]] = r
    return man


def load_sets():
    return json.load(open(f"{OUT}/manifests/sets.json"))


def load_labels():
    return json.load(open(f"{OUT}/manifests/labels.json"))


def patient_ids(sets, set_name):
    s = sets[set_name]
    ids = [pid for cat in CX.CATEGORIES for pid in s[cat]]
    if len(set(ids)) != len(ids):
        raise Q.RequestError(f"duplicate patient id across categories in set {set_name}")
    return sorted(ids)


def build_rows(pids, labels, man, fmt, stage, cfg_digest):
    rows = []
    for pid in pids:
        item = man[pid]
        cat = labels[pid]["category"]
        if item["split"] != cat:
            raise Q.RequestError(f"manifest split {item['split']} != label category {cat} for {pid}")
        for direction in CX.DIRECTIONS:
            for cond in CX.CONDITIONS:
                prompt, ev_digest = CX.prompt_and_evidence(direction, cond, fmt, cat)
                extra = {"direction": direction, "category": cat, "cond": cond}
                row = Q.make_row(item, CKPT, None, direction, fmt, cond, prompt, ev_digest, cfg_digest, stage, extra=extra)
                rows.append(row)
    return rows


def build(a):
    sets, labels, man = load_sets(), load_labels(), load_manifest()
    cfg, _ = qa_protocol.static_cfg()
    pids = patient_ids(sets, a.set)
    rows = build_rows(pids, labels, man, a.fmt, a.stage, cfg)
    ids = [r["request_id"] for r in rows]
    if len(set(ids)) != len(ids):
        raise Q.RequestError("duplicate request_id in freshly built rows")
    os.makedirs(f"{OUT}/requests", exist_ok=True)
    p = f"{OUT}/requests/{a.stage}__{CKPT}.jsonl"
    if os.path.exists(p):
        raise Q.RequestError(f"{p} exists (not overwriting)")
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    print(json.dumps({"stage": a.stage, "set": a.set, "n_patients": len(pids), "n_rows": len(rows)}))


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    b = sp.add_parser("build")
    b.add_argument("--stage", required=True)
    b.add_argument("--set", required=True)
    b.add_argument("--fmt", default="plain")
    a = ap.parse_args()
    if a.cmd == "build":
        build(a)


if __name__ == "__main__":
    main()
