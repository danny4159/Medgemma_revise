"""iter_042 fixture (CPU). 결과: results/iter_042/tests/fixtures_pg42.json (덮어쓰기 거부)."""
import json
import os
import sys

import numpy as np

import pg39_spec as S39
import pg42_data as PD
import pg42_spec as S

EOT = "<end_of_turn>"
res = []


def chk(name, cond):
    res.append({"name": name, "pass": bool(cond)})


b1 = '{"box_2d": [100, 100, 500, 500], "label": "qA"}'
# parse_G
r = S.parse_G("[]" + EOT, True)
chk("empty list -> empty", r["cls"] == "empty" and r["boxes"] == [])
r = S.parse_G(f"[{b1}]" + EOT, True)
chk("one box -> nonempty", r["cls"] == "nonempty" and len(r["boxes"]) == 1)
r = S.parse_G(f"```json\n[{b1}]\n```" + EOT, True)
chk("fenced json -> nonempty", r["cls"] == "nonempty")
r = S.parse_G(f'[{{"box_2d": [100, 100, 500, 500], "label": "Pleural effusion"}}]' + EOT, True)
chk("wrong label -> invalid (lenient nonempty flagged)", r["cls"] == "invalid" and r["lenient_nonempty"])
r = S.parse_G(f'[{{"box_2d": [100, 100, 500, 500], "label": "qB"}}]' + EOT, True)
chk("other-ID box -> invalid", r["cls"] == "invalid")
r = S.parse_G(f"[{b1}" , False)
chk("truncated -> invalid", r["cls"] == "invalid")
r = S.parse_G("There is no effusion." + EOT, True)
chk("prose -> invalid, not empty", r["cls"] == "invalid")
r = S.parse_G('[{"box_2d": [500, 100, 100, 500], "label": "qA"}]' + EOT, True)
chk("inverted coords -> invalid, not empty", r["cls"] == "invalid")
r = S.parse_G(f"[{b1}, {b1}]" + EOT, True)
chk("duplicate boxes kept (2 boxes)", r["cls"] == "nonempty" and len(r["boxes"]) == 2)
# parse_P
for t, want in [("Yes.\n" + EOT, "yes"), ("no" + EOT, "no"), ("YES!" + EOT, "yes"), ("Yes, there is a small effusion." + EOT, "invalid"),
                ("Yes. No." + EOT, "invalid"), ("", "invalid"), ("maybe" + EOT, "invalid")]:
    chk(f"parse_P {t!r}", S.parse_P(t, True) == want)
chk("parse_P truncated -> invalid", S.parse_P("Yes", False) == "invalid")
# gate
chk("gate yes -> C output", S.gate_output("yes", "nonempty", [[1, 2, 3, 4]]) == ("nonempty", [[1, 2, 3, 4]]))
chk("gate no -> empty", S.gate_output("no", "nonempty", [[1, 2, 3, 4]]) == ("empty", []))
chk("gate invalid -> invalid", S.gate_output("invalid", "empty", []) == ("invalid", []))
# neg score
chk("neg nonempty false_box", S.score_neg("nonempty")["false_box"] and S.score_neg("nonempty")["conservative_fail"])
chk("neg invalid not valid_empty but conservative fail", (not S.score_neg("invalid")["valid_empty"]) and S.score_neg("invalid")["conservative_fail"]
    and not S.score_neg("invalid")["false_box"])
chk("neg empty success", S.score_neg("empty")["valid_empty"] and not S.score_neg("empty")["conservative_fail"])
# pos score: multi-box matching, invalid, empty
gt = [[100, 100, 300, 300], [600, 600, 900, 900]]
s = S.score_pos("nonempty", [[100, 100, 300, 300], [600, 600, 900, 900]], gt)
chk("pos perfect f1=1", abs(s["f1_03"] - 1) < 1e-9 and s["fp_03"] == 0)
s = S.score_pos("nonempty", [[100, 100, 300, 300], [0, 0, 50, 50]], gt)
chk("pos 1 tp of 2 pred/2 gt f1=.5 fp=1", abs(s["f1_03"] - 0.5) < 1e-9 and s["fp_03"] == 1)
s = S.score_pos("empty", [], gt)
chk("pos empty f1=0 empty flag", s["f1_03"] == 0 and s["empty"] and not s["invalid"])
s = S.score_pos("invalid", [[100, 100, 300, 300]], gt)
chk("pos invalid f1=0 invalid flag", s["f1_03"] == 0 and s["invalid"])
# stats
w = S.wilson(0, 20)
chk("wilson 0/20 hi ~0.161", abs(w[2] - 0.1611) < 2e-3 and w[1] == 0)
w = S.wilson(20, 20)
chk("wilson 20/20 lo ~0.839", abs(w[1] - 0.8389) < 2e-3)
d = S.boot_diff(np.ones(10), np.zeros(10), 0.95)
chk("bootstrap degenerate flagged", d["degenerate"] and d["mean"] == 1.0)
d = S.boot_diff(np.array([1, 0, 1, 1, 0, 0.0]), np.zeros(6), 0.95)
chk("bootstrap reproducible", d == S.boot_diff(np.array([1, 0, 1, 1, 0, 0.0]), np.zeros(6), 0.95) and not d["degenerate"])
# prompts
p = S.build_prompts()
chk("G_short == prompt_I_short('Pleural effusion.','qA')", p["G_short"] == S39.prompt_I_short("Pleural effusion.", "qA"))
chk("G_neutral contains absent-permitting text", "may be present or absent" in p["G_neutral"] and "return []" in p["G_neutral"])
chk("prompts contain no report/absence phrasing", all("no evidence" not in v.lower() and "not visible" not in v.lower() or k == "G_short" for k, v in p.items()))
# 적격성 (양성): 합성 report
def rep(findings):
    return {"ImageID": "i", "StudyID": "s", "findings": findings}
B = [0.1, 0.1, 0.5, 0.5]
def pf(sent, labels=("pleural effusion",), boxes=(B,), prog=None):
    return {"sentence_en": sent, "abnormal": True, "boxes": [list(b) for b in boxes], "labels": list(labels), "progression": prog,
            "extra_boxes": [], "locations": []}
ok, why, tgt, boxes = PD.pos_target(rep([pf("Left pleural effusion.")]))
chk("pos simple eligible", ok and len(boxes) == 1)
chk("pos mixed label excluded", not PD.pos_target(rep([pf("Effusion and mass.", labels=("pleural effusion", "pleural mass"))]))[0])
chk("pos no box excluded", not PD.pos_target(rep([pf("Pleural effusion.", boxes=())]))[0])
chk("pos progression excluded", not PD.pos_target(rep([pf("Pleural effusion.", prog="increased")]))[0])
chk("pos temporal phrase excluded", not PD.pos_target(rep([pf("Pleural effusion, unchanged.")]))[0])
chk("pos second effusion sentence with other label excludes image",
    not PD.pos_target(rep([pf("Left pleural effusion."), pf("Loculated effusion.", labels=("loculated pleural effusion",))]))[0])
chk("pos duplicate boxes merged", len(PD.pos_target(rep([pf("Pleural effusion."), pf("Right pleural effusion.")]))[3]) == 1)
chk("pos invalid box excluded", not PD.pos_target(rep([pf("Pleural effusion.", boxes=([0.5, 0.5, 0.1, 0.9],))]))[0])
chk("neg detection only abnormal=false", PD.neg_sentences(rep([{"sentence_en": "No pleural effusion.", "abnormal": False, "sentence_es": "x"}])) != []
    and PD.neg_sentences(rep([pf("Pleural effusion.")])) == [])
os.makedirs("results/iter_042/tests", exist_ok=True)
out = "results/iter_042/tests/fixtures_pg42.json"
if os.path.exists(out):
    sys.exit("fixtures output exists")
json.dump({"n": len(res), "n_pass": sum(r["pass"] for r in res), "results": res}, open(out, "x"), indent=1)
print(sum(r["pass"] for r in res), "/", len(res), [r["name"] for r in res if not r["pass"]])
