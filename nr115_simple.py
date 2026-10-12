"""iter_115 보조 기술 통계(봉인 이후 추가, 잠금·completion 대상 아님): 차별 포착이 '출력 비어 있음'·개수·면적 같은 단순 속성으로 설명되는지.
table87.json(봉인된 산출물)만 읽는다. 새 점수·threshold·검토 정책을 만들지 않는다."""
import json
from pathlib import Path

from report86_common import sha

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "results/iter_115"
rows = json.loads((OUT / "table87.json").read_text())


def cnt(f, key):
    d = {}
    for r in rows:
        if f(r):
            d[r[key]] = d.get(r[key], 0) + 1
    return d


res = {"input_table87_sha256": sha(OUT / "table87.json"), "code_sha256": sha(Path(__file__)),
       "note": "봉인 이후 추가한 기술 통계. 사후 탐색이며 포착 규칙·점수를 바꾸지 않는다."}
G = ["err_cure_only", "err_mspc_only", "err_both", "err_neither", "ok_selected_by_cure_or_mspc", "ok_not_selected"]
res["cure_status_by_group"] = {g: cnt(lambda r, g=g: r["group"] == g, "cure_status") for g in G}
res["cure_empty_overall"] = {"n_empty": sum(1 for r in rows if r["n_C"] == 0), "of_which_error": sum(1 for r in rows if r["n_C"] == 0 and r["error_official"]),
                             "of_which_sel_cure": sum(1 for r in rows if r["n_C"] == 0 and r["sel_cure"]),
                             "of_which_sel_cure_and_not_mspc_err": sum(1 for r in rows if r["n_C"] == 0 and r["sel_cure"] and r["error_official"] and not r["sel_mspc"])}
res["mspc_empty_overall"] = {"n_empty": sum(1 for r in rows if r["n_P"] == 0)}
res["mg_empty_overall"] = {"n_empty": sum(1 for r in rows if r["n_M"] == 0), "of_which_sel_conf": sum(1 for r in rows if r["n_M"] == 0 and r["sel_conf"])}
# 개수: n_M vs n_GT, n_C vs n_M, n_P vs n_M (오류 87 vs 비오류)
res["count_mismatch"] = {}
for name, f in (("err", lambda r: r["error_official"] == 1), ("ok", lambda r: r["error_official"] == 0)):
    sub = [r for r in rows if f(r)]
    res["count_mismatch"][name] = {"n": len(sub), "n_M_ne_n_GT": sum(1 for r in sub if r["n_M"] != r["n_GT"]),
                                   "n_C_ne_n_M": sum(1 for r in sub if r["n_C"] != r["n_M"]), "n_P_ne_n_M": sum(1 for r in sub if r["n_P"] != r["n_M"])}
# 두 번째 모델의 공식 GT 대비 기본 오류율 (선택 집합 밖 포함)
res["second_model_error_vs_GT"] = {"cure": sum(r["cure_err_vs_GT"] for r in rows), "mspc": sum(r["mspc_err_vs_GT"] for r in rows), "N": len(rows)}
# 차별 포착 13개: 순위와 경계 근접(K=22)
res["only_rank_margin"] = {"cure_only_rank_cure": sorted(r["rank_cure"] for r in rows if r["group"] == "err_cure_only"),
                           "mspc_only_rank_mspc": sorted(r["rank_mspc"] for r in rows if r["group"] == "err_mspc_only"),
                           "cure_only_rank_mspc": sorted(r["rank_mspc"] for r in rows if r["group"] == "err_cure_only"),
                           "mspc_only_rank_cure": sorted(r["rank_cure"] for r in rows if r["group"] == "err_mspc_only")}
# 환자 중복
res["patients"] = {"cure_only": len({r["patient"] for r in rows if r["group"] == "err_cure_only"}), "mspc_only": len({r["patient"] for r in rows if r["group"] == "err_mspc_only"}),
                   "mspc_only_items": 6}
# 공식 유형이 ALT 에서 유지된 비율 (13개)
res["alt_preservation_13"] = {}
for r in rows:
    if r["group"] in ("err_cure_only", "err_mspc_only"):
        t, a = r["type_GT"], r["type_ALT"]
        k = "no_alt" if a == "NA" else "same" if a == t else "resolved" if a == "iou_ok" else "changed"
        res["alt_preservation_13"][k] = res["alt_preservation_13"].get(k, 0) + 1
# 유형 분포: 오류 전체(37) vs 차별 포착
res["type_GT_all_errors"] = cnt(lambda r: r["error_official"] == 1, "type_GT")
res["type_GT_only13"] = cnt(lambda r: r["group"] in ("err_cure_only", "err_mspc_only"), "type_GT")
p = OUT / "simple_explanations.json"
if p.exists():
    raise SystemExit("exists")
p.write_text(json.dumps(res, indent=1, ensure_ascii=False))
print(json.dumps(res, indent=1, ensure_ascii=False))
