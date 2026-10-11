"""reuse_manifest required_checks (qa_spec): 질문·정답 mapping, strict/semantic_v1 허용·거부·EOS fixture, 저장 F 출력과 iter_016 보고(M0 semantic S_scope 0.6100)의 연결.
결과: results/iter_108/tests/qaspec_checks.json (새 파일만)."""
import hashlib
import json
import sys
from pathlib import Path

import ev108_data as D
import ev108_spec as S
from rsna_diag import qa_spec as Q

CH = []


def chk(n, ok, d=None):
    CH.append({"name": n, "pass": bool(ok), "detail": d})


EOT = "<end_of_turn>"
out = Path(sys.argv[1])
if out.exists():
    sys.exit("exists")
chk("blob_matches_manifest_sha1", __import__("subprocess").run(["git", "hash-object", "--", "rsna_diag/qa_spec.py"], capture_output=True, text=True).stdout.strip()
    == "b1955bf8516a0a08b0ccad91ca65d4e66461e885")
chk("pairs", Q.GT_PAIR == {"opacity": ("yes", "yes"), "normal": ("no", "no"), "not_normal_no_opacity": ("no", "yes")})
chk("Q_O_text", Q.Q_O == "Is there a pulmonary opacity suspicious for pneumonia in this chest radiograph?")
chk("Q_A_mentions_rsna_normal", "RSNA chest-radiograph labeling convention" in Q.Q_A and "A healed rib fracture alone counts as Normal." in Q.Q_A)
cases = [("O", "Yes.\n" + EOT, ("valid", "yes")), ("O", "no" + EOT, ("valid", "no")), ("O", "Yes" , ("truncated", None)),
         ("O", "The image shows an opacity." + EOT, ("explanation", None)), ("O", "Yes. No." + EOT, ("contradictory", None)),
         ("O", '[{"box_2d":[1,2,3,4]}]' + EOT, ("bbox_list", None)), ("O", "" + EOT, ("empty", None)),
         ("A", "Abnormal" + EOT, ("valid", "yes")), ("A", "Normal." + EOT, ("valid", "no")), ("O", "Normal" + EOT, ("explanation", None)),
         ("A", '{"answer":"yes"}' + EOT, ("valid", "yes")), ("A", '{"answer":"yes","x":1}' + EOT, ("explanation", None)),
         ("A", "yes yes" + EOT, ("explanation", None))]
for tg, raw, want in cases:
    eos = not raw.endswith("Yes") or raw.endswith(EOT)
    got = S.sem(tg, raw, eos)
    chk(f"sem_{tg}_{raw[:18]!r}", got == want, got)
# 저장 F 출력 연결: iter_016 보고 M0 S_scope(semantic) 0.6100과 이번 재계산(E600, F policy) 대조
sets, labels, infer, ckpt, bbox = D.load_assets()
F, _ = D.load_F()
per = {c: [] for c in S.CATS}
for c in S.CATS:
    for i in sets["E600"][c]:
        o = S.sem("O", F[(i, "O")]["suffix_text_raw"], F[(i, "O")]["ended_eos"])
        a = S.sem("A", F[(i, "A")]["suffix_text_raw"], F[(i, "A")]["ended_eos"])
        per[c].append(int(o[1] == Q.GT_PAIR[c][0] and a[1] == Q.GT_PAIR[c][1]))
sc = sum(sum(v) / len(v) for v in per.values()) / 3
rep = json.load(open("results/iter_016/e600/report.json"))
chk("F_semantic_S_scope_E600_equals_iter016_M0_0.61", abs(sc - 0.61) < 1e-9, sc)
json.dump({"n": len(CH), "n_pass": sum(c["pass"] for c in CH), "checks": CH}, open(out, "x"), indent=1, default=str)
print(f"{sum(c['pass'] for c in CH)}/{len(CH)}")
for c in CH:
    if not c["pass"]:
        print("FAIL", c["name"], c["detail"])
