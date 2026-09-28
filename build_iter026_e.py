"""iter_026 E60/E200 요청 생성: V_M0/V_B0/RD_M0 (con_* pool). rule/copy/empty baseline은 생성 없이 이후 평가 단계에서 계산한다.
사용: python build_iter026_e.py E60
     python build_iter026_e.py E200_extra   (E60에 포함되지 않은 나머지 140명)
"""
import json
import sys

from rsna_diag import roi23_data as D, roi26_data as D26, roi26_requests as Q, roi26_protocol as P

stage = sys.argv[1]
cfg, _ = P.static_cfg()
items, gts = D.load_confirm_pool()
sets = json.load(open("results/iter_023/manifests/sets.json"))

if stage == "E60":
    ids = sorted(sets["E60"]["primary"] + sets["E60"]["boundary"])
elif stage == "E200_extra":
    e60 = set(sets["E60"]["primary"] + sets["E60"]["boundary"])
    e200 = set(sets["E200"]["primary"] + sets["E200"]["boundary"])
    ids = sorted(e200 - e60)
else:
    raise SystemExit(f"unknown stage {stage}")

stage_items = {i: items[i] for i in ids}
tab = Q.checkpoints(["M0", "B0"])

v = Q.build_v(stage_items, tab, cfg, ["M0", "B0"], stage)
for ck, rows in v.items():
    print("V", ck, len(rows))
    Q.write_rows(f"{stage}_V__{ck}", rows)

b0_recs, n_total = D26.source_bbox_records("B0", "concise")
print("B0 confirm concise source total records (all prompts)", n_total, "concise", len(b0_recs))
props = {}
for i in ids:
    rec = b0_recs.get(i)
    props[i] = D26.proposal_for("B0", rec) if rec else (None, "missing")
rd_rows, unavail = Q.build_rd(stage_items, props, tab, cfg, stage, ckpt="M0")
print("RD", len(rd_rows), "unavailable", unavail)
Q.write_rows(f"{stage}_RD__M0", rd_rows)

json.dump({"stage": stage, "ids": ids, "n": len(ids), "n_unavailable_rd": len(unavail), "unavailable_rd": unavail},
          open(f"results/iter_026/manifests_{stage}_build.json", "w"), indent=1)
print("done", stage, len(ids))
