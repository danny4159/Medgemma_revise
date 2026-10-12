"""iter_115 CPU 분석 실행기. 단계: prov -> lock -> analyze -> (nr115_verify.py) -> seal.

모든 결과는 results/iter_115/ 새 경로. 기존 파일은 덮어쓰지 않는다(이미 있으면 중단). 모델 추론·학습·다운로드·GPU 사용 없음.
prov   : iter_114 analysis_r1 의 stage_lock/ledger/protocol/verify 와 실제 읽는 원시 출력·items·raw_manifest·영상의 '현재' digest 를 잠금 값과 대조.
lock   : 코드 hash·분류 규약·prov digest 를 실제 시각과 함께 protocol.json 에 기록(분석 전). 이미 집계 결과를 본 사후 규약임을 명시.
analyze: 87행 표, 군별 집계, 차별 포착 13개 사례표와 overlay.
seal   : verify.json PASS 와 현재 모든 입력·코드·산출물 digest 가 lock 당시와 같을 때만 completion.json.
"""
import json
import os
import sys
import time
from pathlib import Path

from PIL import Image, ImageDraw

import nr113_core as B
import nr114_core as C
import nr115_core as K
from report86_common import ROOT, sha

R114 = ROOT / "results/iter_114"
AN114 = R114 / "analysis_r1"
OUT = ROOT / "results/iter_115"
CODE = ["nr115_core.py", "nr115_run.py", "nr115_verify.py", "nr115_tests.py", "nr114_core.py", "nr113_core.py", "nr107_geom.py"]
POSTHOC_NOTE = ("iter_114 집계 결과(포착 16/15/13, 차별 7/6)를 본 뒤 정한 사후 분류 규약이다. 사전등록·눈가림 평가·독립 확인이 아니며 "
                "t=0.3·유형 우선순위는 결과에 맞춰 바꾸지 않는다. 'CURE-only/MSPC-only'는 고정 검토 목록의 선택 차이이다.")


def wjson(p, obj):
    p = Path(p)
    if p.exists():
        raise SystemExit(f"refuse to overwrite {p}")
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(obj, indent=1, ensure_ascii=False))
    os.link(tmp, p)
    tmp.unlink()


def rj(p):
    return json.loads(Path(p).read_text())


# ---------------------------------------------------------------- prov
def current_input_hashes(stage_names=("INIT", "EXPAND")):
    h = {}
    for st in stage_names:
        r = rj(AN114 / f"runs_{'init' if st == 'INIT' else 'expand'}.json")
        for k in ("A", "MSPC", "CURE"):
            d = ROOT / r[k]
            for p in sorted(d.rglob("*")):
                if p.is_file() and p.suffix in (".json", ".jsonl") and "partial" not in p.name and "launch" not in p.name and "resource" not in p.name:
                    h[f"{st}/{k}/{p.relative_to(d)}"] = sha(p)
    return h


def provenance():
    """반환: (prov dict, problems list). 원시 입력까지 현재 digest 를 stage_lock 값과 대조."""
    problems = []
    sl = rj(AN114 / "stage_lock_final.json")
    cur = current_input_hashes()
    if cur != sl["input_sha256"]:
        diff = sorted(set(cur) ^ set(sl["input_sha256"])) + sorted(k for k in cur if k in sl["input_sha256"] and cur[k] != sl["input_sha256"][k])
        problems.append(f"raw input digest != stage_lock_final: {diff[:5]}")
    if sha(AN114 / "ledger_final.json") != sl["ledger_sha256"]:
        problems.append("ledger_final.json digest != stage_lock_final.ledger_sha256")
    if sha(AN114 / "protocol.json") != sl["protocol_sha256"]:
        problems.append("protocol.json digest != stage_lock_final.protocol_sha256")
    ver = rj(AN114 / "verify_final.json")
    comp = rj(AN114 / "completion.json")
    # 분석 산출물 digest 가 completion 당시와 같은가
    for name, h in comp.get("files", {}).items():
        pth = AN114 / name
        if not pth.exists() or sha(pth) != h:
            problems.append(f"iter_114 completion file digest differs: {name}")
    items = rj(R114 / "data/items.json")
    man = {m["ImageID"]: m for m in rj(R114 / "data/raw_manifest.json")}
    by_item = {it["item_key"]: it for it in items}
    img_checked = set()
    for it in items:
        im = it["image_meta"]
        if it["ImageID"] in img_checked:
            continue
        img_checked.add(it["ImageID"])
        m = man.get(it["ImageID"])
        if m is None or m["sha256"] != im["raw_png_sha256"]:
            problems.append(f"raw_manifest mismatch {it['ImageID']}")
            continue
        if sha(Path(im["raw_path"])) != im["raw_png_sha256"]:
            problems.append(f"raw png digest differs {it['ImageID']}")
        u8 = ROOT / im["path"]
        im_u8 = Image.open(u8)
        import hashlib
        if hashlib.sha256(im_u8.tobytes()).hexdigest() != im["u8_pixel_sha256"]:
            problems.append(f"u8 pixel digest differs {it['ImageID']}")
        if im_u8.size != (im["w"], im["h"]):
            problems.append(f"u8 size differs {it['ImageID']}")
    # ledger <-> items(GT/ALT/문장) 및 ledger <-> 원시 출력 request id 연결
    L = rj(AN114 / "ledger_final.json")["ledger"]
    raw_ids = {"A": set(), "MSPC": set(), "CURE": set()}
    raw_item = {"A": {}, "MSPC": {}}
    for st in ("init", "expand"):
        r = rj(AN114 / f"runs_{st}.json")
        for k in ("A", "MSPC"):
            for p in sorted((ROOT / r[k]).glob("raw_worker*.jsonl")):
                for line in p.read_text().splitlines():
                    if line.strip():
                        d = json.loads(line)
                        raw_ids[k].add(d["request_id"])
                        raw_item[k][d["request_id"]] = (d["item_key"], d["ImageID"], d["sentence_sha256"])
        for p in sorted((ROOT / r["CURE"]).glob("cure/shard*/outputs.jsonl")):
            for line in p.read_text().splitlines():
                if line.strip():
                    raw_ids["CURE"].add(json.loads(line)["id"])
    seen = set()
    for l in L:
        it = by_item.get(l["item_key"])
        if it is None or l["item_key"] in seen:
            problems.append(f"ledger item missing/duplicate in items {l['item_key']}")
            continue
        seen.add(l["item_key"])
        if l["GT"] != it["gt"] or l["ALT"] != it["extra"] or l["ImageID"] != it["ImageID"] or l["sentence_sha256"] != it["sentence_sha256"] or l["PatientID"] != it["PatientID"]:
            problems.append(f"ledger vs items mismatch {l['item_key']}")
        for k, key in (("A", "mg_A_request_id"), ("MSPC", "mspc_request_id")):
            rid = l[key]
            if rid not in raw_ids[k]:
                problems.append(f"{k} request id not in raw {l['item_key']}")
            elif raw_item[k][rid] != (l["item_key"], l["ImageID"], l["sentence_sha256"]):
                problems.append(f"{k} raw record identity mismatch {l['item_key']}")
        if l["cure_request_id"] not in raw_ids["CURE"]:
            problems.append(f"CURE id not in raw {l['item_key']}")
    prov = {"stage_lock_final_sha256": sha(AN114 / "stage_lock_final.json"), "ledger_final_sha256": sha(AN114 / "ledger_final.json"),
            "protocol_114_sha256": sha(AN114 / "protocol.json"), "verify_final_sha256": sha(AN114 / "verify_final.json"),
            "report_114_sha256": sha(AN114 / "result_final/report.json"), "per_item_114_sha256": sha(AN114 / "result_final/per_item.json"),
            "items_sha256": sha(R114 / "data/items.json"), "raw_manifest_sha256": sha(R114 / "data/raw_manifest.json"),
            "n_raw_input_files_checked": len(cur), "raw_input_digest_matches_stage_lock": cur == sl["input_sha256"],
            "n_images_checked": len(img_checked), "n_ledger_rows": len(L), "verify_final_all_pass": ver.get("all_pass", ver.get("pass")),
            "scope_note": "원시 출력 파일 digest, 영상 raw/u8 pixel digest, ledger-items 및 ledger-원시 request id/item 식별 연결을 대조했다. 원시 logits→box 후처리는 재계산하지 않았다(iter_114 verify 인용)."}
    return prov, problems


def cmd_prov():
    prov, problems = provenance()
    prov["problems"] = problems
    wjson(OUT / "provenance.json", prov)
    print("problems:", problems if problems else "none")
    if problems:
        sys.exit(1)


# ---------------------------------------------------------------- lock
def cmd_lock():
    pv = rj(OUT / "provenance.json")
    if pv["problems"]:
        raise SystemExit("provenance has problems")
    wjson(OUT / "protocol.json", {
        "locked_at_unix": time.time(), "locked_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "posthoc_note": POSTHOC_NOTE, "t_cover": K.T_COVER, "types": list(K.TYPES), "err_iou": B.ERR_IOU,
        "plan_md_sha256": sha(ROOT.parent / "agent/runs/iter_115/plan.md"),
        "code_sha256": {c: sha(ROOT / c) for c in CODE if (ROOT / c).exists()}, "provenance_sha256": sha(OUT / "provenance.json"),
        "note": "분석 실행 전 잠금. nr115_verify.py/nr115_tests.py 가 아직 없으면 목록에서 제외된다(분석 시 존재 여부 재확인)."})


# ---------------------------------------------------------------- analyze
COL = {"M": (220, 30, 30), "C": (255, 140, 0), "P": (150, 40, 200), "GT": (30, 170, 60), "ALT": (40, 100, 230)}


def draw_boxes(dr, boxes, w, h, color, width=4, dash=False):
    for b in boxes:
        xy = [b[0] * w, b[1] * h, b[2] * w, b[3] * h]
        if not dash:
            dr.rectangle(xy, outline=color, width=width)
        else:
            x0, y0, x1, y1 = xy
            step = 24
            x = x0
            while x < x1:
                dr.line([(x, y0), (min(x + step / 2, x1), y0)], fill=color, width=width)
                dr.line([(x, y1), (min(x + step / 2, x1), y1)], fill=color, width=width)
                x += step
            y = y0
            while y < y1:
                dr.line([(x0, y), (x0, min(y + step / 2, y1))], fill=color, width=width)
                dr.line([(x1, y), (x1, min(y + step / 2, y1))], fill=color, width=width)
                y += step


def overlay(l, r, item, path, maxw=640):
    im = Image.open(ROOT / item["image_meta"]["path"]).convert("RGB")
    w, h = im.size
    s = maxw / w
    base = im.resize((maxw, int(h * s)))
    W, H = base.size
    panels = []
    for name, key, desc in (("MG", "M", "MG(A_U_e5, thr0.8)"), ("CURE", "C", "CURE"), ("MSPC", "P", "MSPC")):
        p = base.copy()
        dr = ImageDraw.Draw(p)
        draw_boxes(dr, l["GT"], W, H, COL["GT"], 3)
        if l["ALT"]:
            draw_boxes(dr, l["ALT"], W, H, COL["ALT"], 3, dash=True)
        draw_boxes(dr, l[key], W, H, COL[key], 3)
        dr.rectangle([0, 0, W, 16], fill=(0, 0, 0))
        dr.text((3, 2), f"{desc} red/orange/purple=pred green=GT blue-dash=ALT", fill=(255, 255, 255))
        panels.append(p)
    cap_h = 46
    canvas = Image.new("RGB", (W * 3, H + cap_h), (0, 0, 0))
    for i, p in enumerate(panels):
        canvas.paste(p, (i * W, 0))
    dr = ImageDraw.Draw(canvas)
    dr.text((4, H + 3), f"{l['item_key']} patient#{item['patient_rank'] if 'patient_rank' in item else '?'} \"{l['cure_text'][:90]}\"", fill=(255, 255, 255))
    dr.text((4, H + 17), f"type_GT={r['type_GT']} type_ALT={r['type_ALT']} IoU(M,GT)={r['iou_M_GT']:.2f} IoU(C,GT)={r['iou_C_GT']:.2f} IoU(P,GT)={r['iou_P_GT']:.2f} "
                          f"cure_sel={int(r['sel_cure'])} mspc_sel={int(r['sel_mspc'])} conf_sel={int(r['sel_conf'])}", fill=(255, 255, 0))
    dr.text((4, H + 31), "overlay = 연결/기하 설명용. 미표기 영역은 정상·환각 판정 아님", fill=(180, 180, 180))
    canvas.save(path)


def cmd_analyze():
    proto = rj(OUT / "protocol.json")
    for c, h in proto["code_sha256"].items():
        if sha(ROOT / c) != h:
            raise SystemExit(f"code changed after lock: {c}")
    prov, problems = provenance()
    if problems or sha_prov_changed(prov, proto):
        raise SystemExit(f"provenance changed/problems: {problems}")
    ledger = rj(AN114 / "ledger_final.json")["ledger"]
    rep = rj(AN114 / "result_final/report.json")
    per = {x["item_key"]: x for x in rj(AN114 / "result_final/per_item.json")}
    entries, excl = C.build_entries(ledger)
    cap, sel, Kk = C.captures(entries)
    assert Kk == rep["K"] and len(entries) == rep["N"]
    sel_keys = {f: {entries[i]["item_key"] for i in sel[f]} for f in K_FIELDS}
    by_key = {l["item_key"]: l for l in ledger}
    rank_c, bd_c = K.rank_info(entries, "D")
    rank_p, bd_p = K.rank_info(entries, "P")
    rank_b, bd_b = K.rank_info(entries, "B")
    rows = []
    for i, e in enumerate(entries):
        k = e["item_key"]
        s = {"cure": k in sel_keys["D"], "mspc": k in sel_keys["P"], "confidence": k in sel_keys["B"]}
        pi = per[k]
        assert (s["cure"], s["mspc"], s["confidence"]) == (pi["sel_cure"], pi["sel_mspc"], pi["sel_conf"]), f"selection differs from iter_114 {k}"
        r = K.row_metrics(by_key[k], e, s)
        r["rank_cure"], r["rank_mspc"], r["rank_conf"] = rank_c[i], rank_p[i], rank_b[i]
        r["group"] = K.group_of(r)
        rows.append(r)
    agg = K.aggregate(rows)
    grp_counts = {g: agg[g]["n_items"] for g in K.GROUPS}
    comp = rep["complementarity_B"]
    assert grp_counts["err_cure_only"] == len(comp["a_only_errors"]) and grp_counts["err_mspc_only"] == len(comp["b_only_errors"])
    assert grp_counts["err_both"] == len(comp["both_errors"]) and grp_counts["err_neither"] == len(comp["neither_errors"])
    items = {it["item_key"]: it for it in rj(R114 / "data/items.json")}
    detail_keys = list(comp["a_only_errors"]) + list(comp["b_only_errors"])
    detail = []
    for k in detail_keys:
        l, r = by_key[k], next(x for x in rows if x["item_key"] == k)
        it = items[k]
        d = dict(r)
        d.update({"which": "cure_only" if k in comp["a_only_errors"] else "mspc_only",
                  "M": l["M"], "M_scores": l["M_scores"], "C": l["C"], "P": l["P"], "P_scores": l["P_scores"], "GT": l["GT"], "ALT": l["ALT"],
                  "raw_links": {"A_request_id": l["mg_A_request_id"], "MSPC_request_id": l["mspc_request_id"], "CURE_request_id": l["cure_request_id"],
                                "image_raw_png_sha256": it["image_meta"]["raw_png_sha256"], "u8_pixel_sha256": it["image_meta"]["u8_pixel_sha256"],
                                "image_path": it["image_meta"]["path"], "sentence_sha256": l["sentence_sha256"]},
                  "alt_preservation": ("no_alt" if r["type_ALT"] == K.NA else "alt_type_same" if r["type_ALT"] == r["type_GT"] else
                                       "alt_error_resolved" if r["type_ALT"] == K.NON_ERR else "alt_type_changed"),
                  "patient_other_detail_items": sum(1 for kk in detail_keys if kk != k and by_key[kk]["PatientID"] == l["PatientID"])})
        detail.append(d)
        overlay(l, r, it, OUT / f"overlays/{r['which'] if 'which' in r else d['which']}_{k}.png")
    out = {"posthoc_note": POSTHOC_NOTE, "N": len(rows), "K": Kk, "n_patients": len({r["patient"] for r in rows}),
           "excluded_from_ranking": excl, "capture_recomputed": {"cure": cap["D"], "mspc": cap["P"], "confidence": cap["B"]},
           "rank_boundary": {"cure": bd_c, "mspc": bd_p, "confidence": bd_b}, "group_counts": grp_counts,
           "t_cover": K.T_COVER}
    wjson(OUT / "table87.json", rows)
    wjson(OUT / "groups.json", {"summary": out, "aggregate": agg})
    wjson(OUT / "cases13.json", detail)
    wjson(OUT / "analysis_done.json", {"files": {n: sha(OUT / n) for n in ("table87.json", "groups.json", "cases13.json")},
                                       "overlays": {p.name: sha(p) for p in sorted((OUT / "overlays").glob("*.png"))}})
    print(json.dumps(out["group_counts"]), out["capture_recomputed"])


K_FIELDS = ("D", "P", "B")


def sha_prov_changed(prov, proto):
    return sha(OUT / "provenance.json") != proto["provenance_sha256"]


# ---------------------------------------------------------------- seal
def cmd_seal():
    proto = rj(OUT / "protocol.json")
    ver = rj(OUT / "verify.json")
    if not ver.get("all_pass"):
        raise SystemExit("verify not all_pass")
    done = rj(OUT / "analysis_done.json")
    for n, h in done["files"].items():
        if sha(OUT / n) != h:
            raise SystemExit(f"output changed {n}")
    for n, h in done["overlays"].items():
        if sha(OUT / "overlays" / n) != h:
            raise SystemExit(f"overlay changed {n}")
    for n, h in ver["checked_digests"].items():
        pth = OUT / n if (OUT / n).exists() else ROOT / n
        if sha(pth) != h:
            raise SystemExit(f"verified file changed after verify: {n}")
    for c, h in proto["code_sha256"].items():
        if sha(ROOT / c) != h:
            raise SystemExit(f"locked code changed: {c}")
    prov, problems = provenance()
    if problems or sha(OUT / "provenance.json") != proto["provenance_sha256"]:
        raise SystemExit("input digests changed since lock")
    wjson(OUT / "completion.json", {"completed_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                                   "files": {n: sha(OUT / n) for n in ("provenance.json", "protocol.json", "table87.json", "groups.json", "cases13.json", "verify.json", "analysis_done.json")},
                                   "overlays": done["overlays"], "gpu_used": False, "new_model_requests": 0})


if __name__ == "__main__":
    {"prov": cmd_prov, "lock": cmd_lock, "analyze": cmd_analyze, "seal": cmd_seal}[sys.argv[1]]()
