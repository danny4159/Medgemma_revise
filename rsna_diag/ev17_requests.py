"""iter_017 evidence 요청 생성 (U/B/K/L, 조건부 X). reader는 base M0, localizer 출력은 검증·pin된 B0 seed17 concise bbox.

- GT category·정답은 요청 생성에 쓰지 않는다 (표본 목록만 사용). 기존 요청 파일은 덮어쓰지 않는다.
- source row(B0 bbox record)가 없으면 검출 실패가 아니라 입력 오류로 중단한다. invalid/truncated는 packet이 모두 not_provided이고 metadata에 남는다.
- X: 같은 k 그룹 안에서 ev17_spec.donor_map으로 좌표를 다른 환자 것으로 교체 (mapping은 results/iter_017/manifests/x_map_<name>.json에 잠글 파일로 저장).
사용:
  python -m rsna_diag.ev17_requests build --stage S --set P180 [--exclude-set P180] [--ids a,b] --conds U,B,K,L
  python -m rsna_diag.ev17_requests build_x --stage S --set E600 --map-name e600
"""
import argparse
import json
import os

from . import ev17_reuse, ev17_spec as V, qa_requests as Q, qa_spec as S


def _load(sets_name, exclude, ids_arg):
    sets = json.load(open(f"{Q.OUT}/manifests/sets.json"))
    man = {}
    for ln in open(f"{Q.OUT}/manifests/infer_manifest.jsonl"):
        r = json.loads(ln)
        man[r["id"]] = r
    ids = ids_arg.split(",") if ids_arg else Q.patients(sets, sets_name, exclude)
    return man, ids


def source_state(src, pid):
    """returns (status, boxes, source_request_id). 누락은 예외."""
    rec = src.get(pid)
    if rec is None:
        raise Q.RequestError(f"no B0 bbox record for {pid}")
    boxes, st = Q.predicted_boxes(rec)
    if st == "valid_nonempty":
        return st, boxes, rec.get("request_id")
    if st == "valid_empty":
        return st, [], rec.get("request_id")
    return "other:" + st, None, rec.get("request_id")


def build_rows(man, ids, conds, stage, cfg, ad, src, x_map=None):
    rows = []
    for i in ids:
        st, boxes, srid = source_state(src, i)
        stat = st if st.startswith("valid") else "other"
        for cond in conds:
            shown = boxes
            meta = {"version": V.VERSION, "cond": cond, "source": "B0", "source_request_id": srid, "source_status": st,
                    "k": (len(boxes) if boxes is not None else None)}
            if cond == "X":
                if x_map is None:
                    raise Q.RequestError("X requires x_map")
                if stat == "valid_nonempty":
                    m = x_map[i]
                    d_st, d_boxes, _ = source_state(src, m["donor"])
                    if d_st != "valid_nonempty" or len(d_boxes) != len(boxes):
                        raise Q.RequestError(f"donor {m['donor']} not a same-k nonempty prediction for {i}")
                    shown = d_boxes
                    meta.update({"donor": m["donor"], "shift": m["shift"], "group_n": m["group_n"], "same_coords": m["same_coords"]})
            pk = V.packet(cond, stat, shown)
            meta["packet_sha256"] = S.sha(V.packet_json(pk))
            for t in S.TARGETS:
                pr = V.prompt(t, cond, stat, shown)
                rows.append(Q.make_row(man[i], "M0", None, t, "plain", V.COND_NAME[cond], pr, S.sha(V.evidence_text(cond, stat, shown)), cfg, stage,
                                       extra=meta))
    return rows


def write(rows, stage):
    os.makedirs(f"{Q.OUT}/requests", exist_ok=True)
    p = f"{Q.OUT}/requests/{stage}__M0.jsonl"
    if os.path.exists(p):
        raise Q.RequestError(f"{p} exists (not overwriting)")
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    return p


def x_mapping(ids, src, name):
    items = {}
    for i in ids:
        st, boxes, _ = source_state(src, i)
        if st == "valid_nonempty":
            items[i] = boxes
    mp = V.donor_map(items)
    p = f"{Q.OUT}/manifests/x_map_{name}.json"
    if os.path.exists(p):
        old = json.load(open(p))
        if old != mp:
            raise Q.RequestError(f"{p} exists and differs")
    else:
        json.dump(mp, open(p, "w"), indent=1, sort_keys=True)
    return mp, p


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["build", "build_x"])
    ap.add_argument("--stage", required=True)
    ap.add_argument("--set", default=None)
    ap.add_argument("--exclude-set", default=None)
    ap.add_argument("--ids", default=None)
    ap.add_argument("--conds", default="U,B,K,L")
    ap.add_argument("--map-name", default=None)
    a = ap.parse_args()
    from . import qa_protocol
    ev17_reuse.install_pins()
    cfg, _ = qa_protocol.static_cfg()
    man, ids = _load(a.set, a.exclude_set, a.ids)
    src = Q.bbox_records("B0")
    ad = None
    if a.cmd == "build":
        conds = a.conds.split(",")
        rows = build_rows(man, ids, conds, a.stage, cfg, ad, src)
    else:
        mp, mpath = x_mapping(ids, src, a.map_name)
        rows = build_rows(man, ids, ["X"], a.stage, cfg, ad, src, x_map=mp)
        print("x_map", mpath)
    p = write(rows, a.stage)
    print(json.dumps({"stage": a.stage, "file": p, "n_patients": len(ids), "n_rows": len(rows)}))


if __name__ == "__main__":
    main()
