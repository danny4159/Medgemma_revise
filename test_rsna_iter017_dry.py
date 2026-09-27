"""iter_017 분석 코드 경로 dry-run (과학적 결과 아님): iter_016의 기존 evidence 응답을 ev17 조건 이름으로 복제한 가짜 신규 stage로
ev17_analysis.analyze 전체 경로(표·비교·하위집단·decision)가 실행되는지 확인한다. 이 출력은 어떤 결론에도 쓰지 않는다.
사용: python test_rsna_iter017_dry.py results/iter_017/tests/dryrun_analysis.json"""
import copy
import json
import sys
from unittest import mock

from rsna_diag import ev17_analysis as A, ev17_reuse, qa_eval as E, qa_requests as Q

out = sys.argv[1]
ev17_reuse.install_pins()
man = json.load(open(ev17_reuse.MANIFEST))
old = A.old_pairs(man)
src = old["p60_ev__M0"] + old["p180x_ev__M0"]
pred = [(r, x) for r, x in src if r["condition"] == "ev_predicted"]
st = A.status_by_id([r["id"] for r, _ in pred], Q.bbox_records("B0"))
fake = []
for cond in ("U", "B", "K", "L"):
    for r, x in pred:
        r2 = copy.deepcopy(r)
        r2["condition"] = f"ev17_{cond}"
        x2 = dict(x)
        fake.append((r2, x2))


def fake_load(stage, ckpt, protocol, gen_root="gen"):
    if stage == "dryx":
        out = []
        for r, x in pred:
            r2 = copy.deepcopy(r)
            r2["condition"] = "ev17_X"
            out.append((r2, dict(x)))
        return out
    return list(fake)


with mock.patch.object(E, "load_stage", fake_load):
    res = A.analyze("P180", [("dry", "none")], out, x_stages=[("dryx", "none")])
d = res["decision_expand"]
print("dry-run OK; keys:", sorted(res)[:6], "...", "expand:", d["expand_to_E600"], "hold:", d["hold_reasons"])
assert set(res["main"]) == {"B-U", "L-K"} and res["n_logical_requests_new"] == 5 * len(pred) and "L-X" in res["secondary"]
