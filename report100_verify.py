"""iter_100 산술 재계산: judgments.json을 report100_eval을 import하지 않고 다시 읽어 환자·조건별 지표를 계산해 report_v2.json과 대조한다.
의미 라벨(judgments)은 같은 입력이므로 이 검사는 독립 의미 검증이 아니다. 또한 생성 비용·비EOS 기록을 원시 worker 파일에서 집계한다."""
import json
from pathlib import Path

from report86_common import read_jsonl_complete, save, sha

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "results" / "iter_100"


def main():
    ev = OUT / "eval"
    judg = json.loads((ev / "judgments.json").read_text())["judgments"]
    mp = json.loads((ev / "blind" / "private_mapping.json").read_text())
    rep = json.loads((ev / "report_v2.json").read_text())
    ri = json.loads((ev / "blind" / "review_input.json").read_text())["review"]
    clearq = {}
    for r in ri:
        clearq[r["patient"]] = [a["id"] for a in r["atoms_Q"] if a["status"] == "clear"]
    by = {}
    for j in judg:
        m = mp[j["blind_id"]]
        by.setdefault(m["patient"], {})[m["condition"]] = j
    mismatches, table = [], {}
    for pi, cs in by.items():
        kk = lambda j, f: set(x["key"] for x in j[f])
        for c, j in cs.items():
            rec = sum(1 for a in clearq[pi] if j["Q"][a]["status"] == "recovered")
            pdam = sum(1 for v in j["P"].values() if v["status"] != "preserved")
            ne = len(kk(j, "explicit") - kk(cs["K"], "explicit"))
            ni = len(kk(j, "internal") - kk(cs["K"], "internal"))
            nu = len(kk(j, "unverifiable") - kk(cs["K"], "unverifiable"))
            safe = rec >= 1 and pdam == 0 and ne == 0 and ni == 0
            table.setdefault(str(pi), {})[c] = dict(Q_recovered=rec, P_damaged=pdam, new_explicit=ne, new_internal=ni, new_unverifiable=nu, safe_recovery=safe)
            ref = rep["table"][str(pi)][c]
            for k, v in table[str(pi)][c].items():
                if ref[k] != v:
                    mismatches.append((pi, c, k, ref[k], v))
    # 비용·EOS: 원시 worker 파일
    recs = []
    for s in range(2):
        recs += read_jsonl_complete(OUT / "gen" / "main" / f"worker_{s}.jsonl")
    ids = [r["id"] for r in recs]
    launch = json.loads((OUT / "gen" / "main" / "launch_000.json").read_text())
    cost = dict(n_requests=len(recs), unique=len(set(ids)),
                per_request=[dict(id=r["id"].split("|")[1] + "|" + r["id"][:6], input_tokens=len(r["input_ids"]),
                                  attempts=[a["n_new"] for a in r["attempts"]], ended_eos=r["attempts"][-1]["ended_eos"]) for r in sorted(recs, key=lambda r: r["id"])],
                non_eos=sum(not r["attempts"][-1]["ended_eos"] for r in recs), launch_wall_s_incl_loading=launch["wall_s"],
                gpu_mapping=launch["mapping"], generated_tokens_total=sum(sum(a["n_new"] for a in r["attempts"]) for r in recs))
    out = dict(n_mismatch=len(mismatches), mismatches=mismatches, cost=cost, report_sha=sha(ev / "report_v2.json"),
               note="산술 재계산만 수행. 의미 판정의 독립 검증이 아님")
    save(ev / "verify.json", out)
    print(json.dumps(dict(n_mismatch=len(mismatches), non_eos=cost["non_eos"], wall=cost["launch_wall_s_incl_loading"], tokens=cost["generated_tokens_total"])))


if __name__ == "__main__":
    main()
