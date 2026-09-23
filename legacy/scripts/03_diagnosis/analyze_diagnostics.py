"""Analyses the controlled diagnostic experiments."""
import json
import re
import sys

sys.path.insert(0, "/SSD1_1TB/home/milab/daniel/08_medgemma/legacy/scripts/02_eval")
from score_eval import parse_bbox, parse_cell, iou

D = "/SSD1_1TB/home/milab/daniel/08_medgemma/legacy/eval_results/diagnostics.jsonl"
rows = [json.loads(l) for l in open(D)]


def by(exp):
    return [r for r in rows if r["exp"] == exp]


print("=" * 78)
print("E1  SYNTHETIC MARKER — can it localise an unmistakable white disc?")
print("=" * 78)
g = by("E1_marker_grid")
hits, preds = 0, []
for r in g:
    p = parse_cell(r["output"])
    preds.append((r["dataset"], r["variant"], p, r["gt"]["cell"]))
    hits += p == r["gt"]["cell"]
print(f"  grid cell accuracy: {hits}/{len(g)} = {hits/len(g):.2f}   (random = 0.11)")
for d, v, p, gt in preds:
    print(f"     {d:14s} {v:13s} pred={p} gt={gt} {'OK' if p == gt else 'X'}")

b = by("E1_marker_bbox")
ious = []
for r in b:
    box = parse_bbox(r["output"])
    ious.append(iou(box, r["gt"]["bbox_xyxy"]) if box else 0.0)
print(f"\n  marker bbox mean IoU: {sum(ious)/len(ious):.3f}   IoU>=0.5: {sum(i>=0.5 for i in ious)}/{len(ious)}")
print(f"     per-sample: {[round(i,3) for i in ious]}")

for exp, key, opts in [("E1_marker_half_lr", "lr", ("left", "right")),
                       ("E1_marker_half_tb", "tb", ("top", "bottom"))]:
    rs = by(exp)
    ok = 0
    detail = []
    for r in rs:
        o = r["output"].lower()
        said = next((w for w in opts if w in o), None)
        ok += said == r["gt"][key]
        detail.append(f"{r['variant']}:{said}/{r['gt'][key]}")
    print(f"\n  {exp}: {ok}/{len(rs)} = {ok/len(rs):.2f}  (chance = 0.50)")
    print(f"     {', '.join(detail)}")

print()
print("=" * 78)
print("E2  CONTENTLESS IMAGES — does it answer confidently with no content?")
print("=" * 78)
for r in rows:
    if r["exp"].startswith("E2"):
        print(f"  [{r['dataset']:11s}] {r['exp']:17s} -> {r['output'][:150]!r}")

print()
print("=" * 78)
print("E3  ANSWER BIAS")
print("=" * 78)
a = by("E3_absurd")
yes = sum(bool(re.search(r"\byes\b", r["output"].lower())) for r in a)
print(f"  absurd findings (correct answer is always NO): said yes {yes}/{len(a)} = {yes/len(a):.2f}")
for v in sorted({r["variant"] for r in a}):
    sub = [r for r in a if r["variant"] == v]
    y = sum(bool(re.search(r"\byes\b", r["output"].lower())) for r in sub)
    print(f"     {v:20s} yes {y}/{len(sub)}")

n = by("E3_negated")
ok = flipped = unparsed = 0
for r in n:
    m = re.search(r"\b(yes|no)\b", r["output"].lower())
    if not m:
        unparsed += 1
        continue
    ok += m.group(1) == r["gt"]["expected"]
print(f"\n  negated phrasing ('is it FREE of X?'): correct {ok}/{len(n)-unparsed} "
      f"(unparsed {unparsed})")

print()
print("=" * 78)
print("E4  MODALITY IDENTIFICATION")
print("=" * 78)
for ds in ["deeplesion_ct", "brats2023", "vindr_cxr"]:
    mc = [r for r in by("E4_modality_mc") if r["dataset"] == ds]
    op = [r for r in by("E4_modality_open") if r["dataset"] == ds]
    mc_ok = sum(bool(re.match(rf"\s*\(?{r['gt']['expected']}\b", r["output"].strip(), re.I))
                or r["output"].strip().upper().startswith(r["gt"]["expected"]) for r in mc)
    print(f"  {ds:14s} forced-choice: {mc_ok}/{len(mc)}")
    print(f"       mc answers   : {[r['output'][:18] for r in mc]}")
    print(f"       open answers : {[r['output'][:26] for r in op]}")
