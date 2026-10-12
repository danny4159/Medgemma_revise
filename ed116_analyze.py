"""iter_116 본 분석: 검증된 MAIN completion → 환자별 표, 그룹별 report, 사전 투자 분기. 결과는 새 경로에만 쓴다 ('x' 모드).
사용: python ed116_analyze.py --gen results/iter_116/gen/MAIN --requests ... --protocol ... --out results/iter_116/eval
"""
import argparse
import json
import os
import sys

import ed116_eval as EV
import ed116_spec as ES
import ev109_extract as X
import pg43_run as RUN

PROV = "results/iter_116/provenance"
LOCKDIR = "results/iter_116/lock"


def load_inputs():
    rows = json.load(open(f"{PROV}/ledger_nogt.json"))["rows"]
    gt = json.load(open(f"{PROV}/gt.json"))
    sel = json.load(open(f"{LOCKDIR}/selection.json"))
    return {r["id"]: r for r in rows}, gt, sel


def model_answers(recs):
    """records → {patient: {cond: (answer|None, resolve dict, record)}}"""
    out = {}
    for r in recs:
        res = X.resolve("O", r["suffix_text_raw"], r["ended_eos"])
        out.setdefault(r["patient"], {})[r["cond"]] = (res["answer"], res, r)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gen", required=True)
    ap.add_argument("--requests", required=True)
    ap.add_argument("--protocol", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    lock = json.load(open(f"{LOCKDIR}/eval_lock.json"))
    bad = [f for f, h in lock["files"].items() if RUN.file_sha(f) != h]
    if bad:
        sys.exit(f"평가 잠금 파일이 변경됨: {bad}")
    recs = RUN.verify_completion(a.gen, a.requests, a.protocol)  # 요청 집합·record digest·영상 hash·보호 필드 재검증
    byid, gt, sel = load_inputs()
    ma = model_answers(recs)
    groups = {"mismatch": sel["mismatch"], "control": sel["control"]}
    for g, ids in groups.items():
        for i in ids:
            if set(ma.get(i, {})) != set(ES.COND_ORDER):
                sys.exit(f"조건 누락: {g} {i}")
    if set(ma) != set(sel["mismatch"]) | set(sel["control"]):
        sys.exit("분석 대상 외 환자 record가 있다")
    patients, per_patient = {}, []
    for g, ids in groups.items():
        patients[g] = []
        for i in ids:
            p = EV.make_patient(byid[i], gt[i], {c: ma[i][c][0] for c in ES.COND_ORDER})
            patients[g].append(p)
            pt = EV.point_scalars(p)
            per_patient.append(dict(id=i, group=g, category=p["cat"], gt=p["y"], answers=p["base"],
                                    correct={q: p["base"][q] == p["y"] for q in EV.POL},
                                    resolve={c: dict(source=ma[i][c][1]["source"], reason=ma[i][c][1]["reason"], rule=ma[i][c][1]["rule"]) for c in ES.COND_ORDER},
                                    raw={c: ma[i][c][2]["suffix_text_raw"] for c in ES.COND_ORDER},
                                    ended_eos={c: ma[i][c][2]["ended_eos"] for c in ES.COND_ORDER},
                                    joint03={q: pt[f"joint03_{q}"] for q in EV.JOINT_POL}, n_det=p["n_det"], n_gt=p["n_gt"],
                                    tp03=p["tp03"], request_ids={c: ma[i][c][2]["request_id"] for c in ES.COND_ORDER}))
    rep_mm = EV.group_report(patients["mismatch"])
    rep_ag = EV.group_report(patients["control"])
    dec = EV.decide(rep_mm, rep_ag)
    fmt = {}
    for g, ids in groups.items():
        fmt[g] = EV.format_report({c: [ma[i][c][2] for i in ids] for c in ES.COND_ORDER})
    comp = json.load(open(os.path.join(a.gen, "completion.json")))
    unresolved = [dict(id=i, raw=byid[i]["O"]["raw"], request_id=byid[i]["O"]["request_id"]) for i in sel["unresolved"]]
    report = dict(spec_version=ES.SPEC_VERSION, eval_lock_sha256=RUN.file_sha(f"{LOCKDIR}/eval_lock.json"), protocol_sha256=RUN.file_sha(a.protocol),
                  requests_sha256=RUN.file_sha(a.requests), n_records=len(recs), mismatch=rep_mm, control=rep_ag, decision=dec, format=fmt,
                  cost=comp["cost"], cost_this_attempt=comp.get("cost_this_attempt"), wall_s=comp["wall_s"], workers=comp["workers"],
                  mapping=comp["mapping"], unresolved_excluded_E600_K=unresolved,
                  note="불일치 87명은 K/B 중 하나가 맞는 구조로 선정한 집단이다. 자연 모집단 오류율·실용 이득으로 외삽하지 않는다.")
    os.makedirs(a.out, exist_ok=True)
    for name, obj in (("report.json", report), ("per_patient.json", per_patient)):
        with open(os.path.join(a.out, name), "x") as f:
            json.dump(obj, f, indent=1, sort_keys=True)
    print(json.dumps(dict(label=dec["label"], point=dec["point"], worst=dec["worst"]), indent=1))


if __name__ == "__main__":
    main()
