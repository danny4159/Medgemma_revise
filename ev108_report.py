"""iter_108 단계 평가: 검증된 생성 출력 + 저장 F 로 P180/E600 보고서와 확대 decision 을 만든다.

python ev108_report.py p180 --dirs TECH=<dir> P180R=<dir>   -> results/iter_108/eval/report_P180.json, decision_P180.json
python ev108_report.py e600 --dirs TECH=<dir> P180R=<dir> E600R=<dir> --gate results/iter_108/eval/decision_P180.json
기존 파일은 덮어쓰지 않는다. 모든 입력 출력은 ev108_run.verify_completion 으로 재검증한다.
"""
import argparse
import json
import sys
from collections import Counter

import numpy as np

import ev108_data as D
import ev108_eval as E
import ev108_run as RUN
import ev108_spec as S

EVAL = D.ROOT / "results/iter_108/eval"
DATA = D.ROOT / "results/iter_108/data"
PROTO = D.ROOT / "results/iter_108/protocol"


def save_new(path, obj):
    if path.exists():
        raise FileExistsError(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".{__import__('os').getpid()}.tmp")
    tmp.write_text(json.dumps(obj, indent=1, ensure_ascii=False, default=str))
    tmp.replace(path)


def load_stage_records(stage, d):
    recs = RUN.verify_completion(str(d), str(DATA / f"requests_{stage}.jsonl"), str(PROTO / f"protocol_{stage}.json"))
    return recs


def assemble(dirs):
    """returns (nonempty ids by stage, ans dict, records list)."""
    ans, allrecs, stage_ids = {}, [], {}
    for stage, d in dirs.items():
        recs = load_stage_records(stage, d)
        allrecs += recs
        stage_ids[stage] = sorted({r["patient"] for r in recs})
        for r in recs:
            k = (r["patient"], r["cond"], r["target"])
            if k in ans:
                raise ValueError(f"duplicate answer {k}")
            ans[k] = r
    return stage_ids, ans, allrecs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("which", choices=["p180", "e600"])
    ap.add_argument("--dirs", nargs="+", required=True)
    ap.add_argument("--gate", default=None)
    ap.add_argument("--tag", default="")
    a = ap.parse_args()
    dirs = dict(x.split("=", 1) for x in a.dirs)
    want = {"p180": {"TECH", "P180R"}, "e600": {"TECH", "P180R", "E600R"}}[a.which]
    if set(dirs) != want:
        sys.exit(f"dirs must be exactly {sorted(want)}")
    if a.which == "e600":
        g = json.load(open(a.gate))
        if g.get("run") is not True or g.get("stage") != "P180":
            sys.exit("E600 expansion not permitted by P180 decision")
    sets, labels, infer, ckpt, bbox = D.load_assets()
    rep, problems = D.audit(sets, labels, infer, ckpt, bbox)
    if problems:
        sys.exit(f"audit problems {problems[:3]}")
    cats = {i: labels[i]["category"] for i in labels}
    stage_ids, ans, recs = assemble(dirs)
    F, _ = D.load_F()
    for (pid, tg), r in F.items():
        ans[(pid, "F", tg)] = r
    nonempty = sorted({p for v in stage_ids.values() for p in v})
    name = "P180" if a.which == "p180" else "E600"
    full = sets[name]
    full_ids = {i for c in S.CATS for i in full[c]}
    ne_in_full = [p for p in nonempty if p in full_ids]
    assert len(ne_in_full) == len(nonempty) == sum(rep["nonempty"][name].values()), "nonempty set != audited set"
    bstatus = {i: S.parse_saved_bbox(bbox[i]["suffix_text_raw"], bbox[i]["ended_eos"])[0] for i in full_ids}
    geo = json.load(open(DATA / "geometry.json"))
    out = {"stage": name, "dirs": dirs, "parser_primary": "semantic_v1", "audit": rep}
    for parser in ("sem", "strict"):
        out[f"comparisons_{parser}"] = E.comparisons(nonempty, cats, ans, parser)
        out[f"policies_{parser}"] = E.policy_report({c: full[c] for c in S.CATS}, cats, bstatus, ans, parser)
    out["crop_stats"] = E.crop_stats(geo, labels, nonempty)
    # 형식 상태 분포 (조건·질문별, semantic_v1/strict)
    fmt = {}
    for cond in ("F", "D", "T", "C", "L"):
        for tg in S.TARGETS:
            if (cond, tg) == ("L", "A"):
                continue
            sts = [S.sem(tg, ans[(p, cond, tg)]["suffix_text_raw"], ans[(p, cond, tg)]["ended_eos"])[0] for p in nonempty]
            sts_strict = [S.strict(tg, ans[(p, cond, tg)]["suffix_text_raw"], ans[(p, cond, tg)]["ended_eos"])[0] for p in nonempty]
            fmt[f"{cond}_{tg}"] = {"semantic": dict(Counter(sts)), "strict": dict(Counter(sts_strict))}
    out["format_status"] = fmt
    # 비용: 이번 요청들의 생성 시간·입력 token (정책이 실제 호출하는 요청만 정책 비용에 반영)
    cost = {}
    for cond in ("D", "T", "C", "L"):
        rr = [r for r in recs if r["cond"] == cond]
        cost[cond] = {"n": len(rr), "mean_generate_s": float(np.mean([r["runtime_s_total"] for r in rr])),
                      "mean_input_tokens": float(np.mean([r["n_input_tokens"] for r in rr])),
                      "mean_output_tokens": float(np.mean([r["n_output_tokens"] for r in rr])),
                      "n_retry": int(sum(len(r["attempts"]) > 1 for r in rr)), "n_final_not_eos": int(sum(not r["ended_eos"] for r in rr))}
    out["cost_this_run"] = cost
    out["cost_note"] = ("정책 비용은 policy가 필요로 하는 호출만 합산: R=localizer(미측정, iter_012 저장)+T 1호출(O)+F 1호출(A), "
                        "R_L=localizer+L 1호출+F 1호출, R_B=localizer+F 1호출, F=2호출. 값은 cost_this_run 평균×nonempty 수로 계산하며 wall-clock 비율이 아님")
    save_new(EVAL / f"report_{name}{a.tag}.json", out)
    if a.which == "p180":
        ne_by = {e: 0 for e in E.EXPAND_ENDPOINTS}
        e_nonempty = rep["nonempty"]["E600"]
        ne_by["T_minus_D_O"] = sum(e_nonempty.values())
        ne_by["T_minus_C_O"] = sum(e_nonempty.values())
        ne_by["T_minus_D_A_nno"] = e_nonempty["not_normal_no_opacity"]
        dec = E.expansion_decision(out["comparisons_sem"], ne_by)
        dec.update({"stage": "P180", "run": dec["expand"], "report": f"report_{name}{a.tag}.json",
                    "report_sha256": D.file_sha(EVAL / f"report_{name}{a.tag}.json"),
                    "eval_code_sha256": {f: D.file_sha(D.ROOT / f) for f in ("ev108_eval.py", "ev108_report.py", "ev108_spec.py")}})
        save_new(EVAL / f"decision_P180{a.tag}.json", dec)
        print(json.dumps(dec, indent=1))
    else:
        fin = {"stage": "E600", "limited_positive": {k: E.limited_positive(out["comparisons_sem"]["comparisons"][k]) for k in E.EXPAND_ENDPOINTS},
               "report": f"report_{name}{a.tag}.json"}
        save_new(EVAL / f"final_E600{a.tag}.json", fin)
        print(json.dumps(fin, indent=1))


if __name__ == "__main__":
    main()
