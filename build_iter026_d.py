"""iter_026 D24 요청 생성 (동작 확인 stage)."""
import json

from rsna_diag import roi23_data as D, roi26_data as D26, roi26_requests as Q, roi26_protocol as P

cfg, _ = P.static_cfg()
items, gts = D.load_val_pool()
d24, counts = D.select_d24(items, gts)
d24_items = {i: items[i] for i in d24}
tab = Q.checkpoints(["M0", "B0"])
print("tab ok", {k: tab[k]["digest"] for k in tab})

v = Q.build_v(d24_items, tab, cfg, ["M0", "B0"], "D")
for ck, rows in v.items():
    print("V", ck, len(rows))
    Q.write_rows(f"D_V__{ck}", rows)

o = Q.build_o(d24_items, gts, tab, cfg, ["M0", "B0"], "D")
for ck, rows in o.items():
    print("O", ck, len(rows))
    Q.write_rows(f"D_O__{ck}", rows)

b0_recs = D26.load_val_b0_records()
props = {}
for i in d24:
    rec = b0_recs.get(i)
    props[i] = D26.proposal_for("B0", rec) if rec else (None, "missing")
rd_rows, unavail = Q.build_rd(d24_items, props, tab, cfg, "D", ckpt="M0")
print("RD", len(rd_rows), "unavailable", unavail)
Q.write_rows("D_RD__M0", rd_rows)

t = Q.build_text(tab, cfg, ["M0", "B0"], "D")
for ck, rows in t.items():
    print("TEXT", ck, len(rows))
    Q.write_rows(f"D_TEXT__{ck}", rows)

json.dump({"d24_ids": d24, "layer_counts": counts, "n_unavailable_rd": len(unavail), "unavailable_rd": unavail},
          open("results/iter_026/manifests_d24_build.json", "w"), indent=1)
print("done")
