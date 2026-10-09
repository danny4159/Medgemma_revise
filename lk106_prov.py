"""iter_106 한정 자료 연결: iter_105 D4/E32 36명의 입력을 원 PadChest-GR metadata와 대조하고 저장 PG 출력·iter_086/095 출력과의 연결 가능성을 기록한다.
자유 문장 의미는 판정하지 않는다. 결과: results/iter_106/provenance/provenance.json (새 파일만 생성).
"""
import json
import sys
from pathlib import Path

import lk106_spec as S
import pg39_data as D
from report86_common import ROOT, sha, sha_obj, save, read_jsonl_complete

R105 = ROOT / "results/iter_105"
R106 = ROOT / "results/iter_106"
DATA = R105 / "data"


def main():
    reports, m, links = D.load_inputs()
    by = {r["ImageID"]: r for r in reports}
    out = {"patients": [], "checks": {}}
    bad = []
    all_rows = []
    for stage in ("D4", "E32"):
        rows = json.loads((DATA / f"inputs_{stage}.json").read_text())
        raw = {r["ImageID"]: r for r in json.loads((DATA / f"raw_manifest_{stage}.json").read_text())}
        for r in rows:
            iid = r["ImageID"]
            rep = by[iid]
            f = rep["findings"]
            idx = r["finding_idx"]
            f1, f2 = f[idx[0]], f[idx[1]]
            chk = {
                "patient": links["img2patient"][iid] == r["PatientID"], "study": rep["StudyID"] == r["StudyID"],
                "split_train": links["img2split"][iid] == "train", "S1": f1["sentence_en"] == r["S1"], "S2": f2["sentence_en"] == r["S2"],
                "box1_main_single": len(f1["boxes"]) == 1 and [float(v) for v in f1["boxes"][0]] == r["box1"],
                "box2_main_single": len(f2["boxes"]) == 1 and [float(v) for v in f2["boxes"][0]] == r["box2"],
                "extra1": [[float(v) for v in b] for b in (f1.get("extra_boxes") or [])] == r["extra1"],
                "extra2": [[float(v) for v in b] for b in (f2.get("extra_boxes") or [])] == r["extra2"],
                "image_sha": sha(r["image"]) == r["file_sha256"], "raw_sha": sha(raw[iid]["raw_path"]) == raw[iid]["sha256"],
                "gt_boxes_disjoint": S.iou(r["box1"], r["box2"]) == 0.0,
                "S1_ne_S2": r["S1"].strip().lower() != r["S2"].strip().lower(),
            }
            if not all(chk.values()):
                bad.append((iid, [k for k, v in chk.items() if not v]))
            out["patients"].append({"stage": stage, "ImageID": iid, "PatientID": r["PatientID"], "StudyID": r["StudyID"], "S1": r["S1"], "S2": r["S2"],
                                    "n_extra1": len(r["extra1"]), "n_extra2": len(r["extra2"]), "labels1": r["labels1"], "labels2": r["labels2"],
                                    "area1": (r["box1"][2] - r["box1"][0]) * (r["box1"][3] - r["box1"][1]),
                                    "area2": (r["box2"][2] - r["box2"][0]) * (r["box2"][3] - r["box2"][1]),
                                    "checks_ok": all(chk.values())})
            all_rows.append(r)
    ids = [r["ImageID"] for r in all_rows]
    pats = [r["PatientID"] for r in all_rows]
    studies = [r["StudyID"] for r in all_rows]
    out["checks"] = {"n_patients": len(all_rows), "unique_images": len(set(ids)) == len(ids), "unique_patients": len(set(pats)) == len(pats),
                     "unique_studies": len(set(studies)) == len(studies), "problems": bad,
                     "n_with_extra_annotation_S1": sum(bool(r["extra1"]) for r in all_rows),
                     "n_with_extra_annotation_S2": sum(bool(r["extra2"]) for r in all_rows),
                     "main_box_semantics": "boxes=공식 주 box(단일), extra_boxes=별도 보조 annotation. 주 정답은 box1/box2만; extra는 민감도 전용"}
    # iter_086 E96 / D8 / iter_095 출력과의 연결 가능성 (ImageID, Patient, Study)
    link = {}
    for name, p in {"iter086_E96": ROOT / "results/iter_086/E96/readings.jsonl", "iter086_D8": ROOT / "results/iter_086/D8/readings.jsonl"}.items():
        if p.exists():
            recs = read_jsonl_complete(p)
            iids = {r.get("ImageID") for r in recs if r.get("ImageID")}
            link[name] = {"path": str(p.relative_to(ROOT)), "n_images": len(iids), "overlap_with_iter106_images": sorted(iids & set(ids)),
                          "overlap_patient": sorted({by[i]["ImageID"] for i in iids if i in by and links["img2patient"][i] in set(pats)}),
                          "task": "GRG(소견 발견)+영역 Describe: 정답 문장 미제공"}
        else:
            link[name] = {"path": str(p.relative_to(ROOT)), "exists": False}
    p95 = ROOT / "results/iter_095"
    iids95 = set()
    for f in p95.rglob("*.json*"):
        try:
            txt = f.read_text()
        except Exception:
            continue
        for i in ids:
            if i in txt:
                iids95.add(i)
    link["iter095_any_file_mentions"] = {"overlap_with_iter106_images": sorted(iids95)}
    # 저장 독립 PG(iter_105) 출력의 요청 완전성
    ind = {}
    for stage, gdir, n in (("E32", R105 / "gen/E32/cure", 2), ("D4", R105 / "gen/D4_w1f/cure", 1)):
        recs = {}
        for k in range(n):
            for r in read_jsonl_complete(gdir / f"shard{k}" / "outputs.jsonl"):
                if r["kind"] == "pg":
                    recs[r["id"]] = r
        rows = json.loads((DATA / f"inputs_{stage}.json").read_text())
        want = {f"{r['ImageID']}|CURE|pg-{k}" for r in rows for k in ("S1", "S2")}
        ind[stage] = {"n_pg_records": len(recs), "n_expected": len(want), "exact_set": set(recs) == want,
                      "prompt_matches_S": all(recs[f"{r['ImageID']}|CURE|pg-{k}"]["prompt"] == S.pg_prompt(r[k]) for r in rows for k in ("S1", "S2")),
                      "final_not_eos": sum(not r["attempts"][-1]["ended_eos"] for r in recs.values()),
                      "protocol_digests": sorted({r["protocol_digest"] for r in recs.values()})}
    out["links"] = link
    out["iter105_independent_pg"] = ind
    out["comparability_note"] = ("GRG/Describe 출력은 정답 문장을 받지 않고 소견을 스스로 발견하므로 PG(정답 문장 제공)와 paired 비교 불가. 이번 비교는 "
                                 "동일 영상·동일 두 문장을 받는 PG 내부(I vs J)로 한정한다. 자유 문장 의미는 재판정하지 않았다.")
    out["source_sha256"] = {f: sha(ROOT / f) for f in ("lk106_prov.py", "lk106_spec.py", "pg39_data.py")}
    save(R106 / "provenance/provenance.json", out)
    print(json.dumps({"checks": out["checks"], "links": {k: (v.get("overlap_with_iter106_images") if isinstance(v, dict) else v) for k, v in link.items()},
                      "ind": ind}, indent=1)[:3500])
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
