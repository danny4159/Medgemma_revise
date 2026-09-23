"""iter_006 NIH 재감사·readiness·클래스별 target 생성 (CPU, GPU 0, 네트워크 없음).

실행:
  python research/audit_grounding_iter006.py --src research/results/iter_005 \
      --evidence research/results/iter_006/coord_evidence --out research/results/iter_006

- iter_005 산출물(metadata·영상·manifest·provenance)은 읽기 전용 입력이다. 실행 전후 입력 hash를 기록해
  변경이 없었음을 남긴다. 새 산출물은 --out 아래 새 파일 이름으로만 쓴다.
- 상태 필드의 의미
  * audit_run_complete: 이 감사 스크립트가 모든 단계를 끝까지 실행했는가 (데이터 준비 완료가 아님)
  * integrity_gate_pass: 필수 무결성 검사(REQUIRED_CHECKS)가 모두 정확히 True인가
  * lesion_probe_ready: integrity_gate_pass AND 좌표 canvas 직접 문서 근거 (엄격한 데이터 준비 완료)
  * gpu_probe_entry_allowed: lesion_probe_ready와 같다
"""
import argparse
import hashlib
import json
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from grounding_data import class_targets as CT  # noqa: E402
from grounding_data import coord_evidence, nih_audit  # noqa: E402
from grounding_data import targets as T  # noqa: E402

TOL = 1e-10


def dump(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f, indent=1, ensure_ascii=False, default=str)
    os.replace(tmp, path)


def tree_digest(src):
    """입력 디렉터리의 감사 대상 파일 sha256 목록 (실행 전후 비교용)."""
    files = [os.path.join(src, n) for n in ("nih_manifest.json", "provenance.json", "readiness.json",
                                            "nih_targets_fine64.npz")]
    for sub in ("data/nih/meta", "data/nih/images"):
        d = os.path.join(src, sub)
        files += [os.path.join(d, f) for f in sorted(os.listdir(d))]
    out = {}
    for p in files:
        h = hashlib.sha256()
        with open(p, "rb") as f:
            for c in iter(lambda: f.read(1 << 20), b""):
                h.update(c)
        out[os.path.relpath(p, src)] = h.hexdigest()
    return out


def target_checks(tg, manifest):
    """클래스 분리·coarse 일치·unknown 처리 검증."""
    by = {r["image"]: r for r in manifest}
    res = {"coarse_vs_fine_mean_max_abs": 0.0, "coarse_vs_direct16_max_abs": 0.0,
           "class_only_area_max_abs_err": 0.0, "n_multiclass_images": 0,
           "n_multiclass_where_classwise_differs_from_all_union": 0, "unknown_channels_all_zero": True,
           "n_observed_pairs": int(tg["observed"].sum()), "other_class_leak_max": 0.0}
    for i, img in enumerate(tg["image_id"]):
        r = by[str(img)]
        W, H = r["width"], r["height"]
        labels = sorted({a["label"] for a in r["annotation"]})
        allu = T.bbox_union_occupancy([a["xyxy"] for a in r["annotation"]], W, H)
        if len(labels) > 1:
            res["n_multiclass_images"] += 1
        differs = False
        for k, c in enumerate(CT.MAIN_CLASSES):
            f, co = tg["fine"][i, k], tg["coarse"][i, k]
            res["coarse_vs_fine_mean_max_abs"] = max(res["coarse_vs_fine_mean_max_abs"],
                                                     float(np.abs(co - T.coarse_from_fine(f)).max()))
            if not tg["observed"][i, k]:
                if np.abs(f).max() != 0 or np.abs(co).max() != 0 or c in labels:
                    res["unknown_channels_all_zero"] = False
                continue
            own = [a["xyxy"] for a in r["annotation"] if a["label"] == c]
            direct16 = T.bbox_union_occupancy(own, W, H, n=T.COARSE)
            res["coarse_vs_direct16_max_abs"] = max(res["coarse_vs_direct16_max_abs"], float(np.abs(co - direct16).max()))
            # 다른 클래스 box가 있는 영상: 전체 union과 달라야 클래스 분리가 실제로 작동한 것
            # (클래스 간 누출 자체는 test_class_targets_iter006.py의 손계산 fixture로 검사한다)
            if any(a["label"] != c for a in r["annotation"]) and np.abs(f - allu).max() > TOL:
                differs = True
            # 다른 클래스 box 영역 중 이 클래스 box 밖의 cell 질량 = 0 이어야 한다 (cell 단위 보수적 검사)
            own_cells = T.bbox_union_occupancy(own, W, H) > 0
            res["other_class_leak_max"] = max(res["other_class_leak_max"], float(np.abs(f[~own_cells]).max())
                                              if (~own_cells).any() else 0.0)
            own_area = T.bbox_union_occupancy(own, W, H).sum()
            res["class_only_area_max_abs_err"] = max(res["class_only_area_max_abs_err"], float(abs(f.sum() - own_area)))
        if len(labels) > 1 and differs:
            res["n_multiclass_where_classwise_differs_from_all_union"] += 1
    res["pass"] = bool(res["coarse_vs_fine_mean_max_abs"] <= TOL and res["coarse_vs_direct16_max_abs"] <= TOL
                       and res["class_only_area_max_abs_err"] <= TOL and res["unknown_channels_all_zero"])
    counts = {}
    for k, c in enumerate(CT.MAIN_CLASSES):
        counts[c] = {s: int((tg["observed"][:, k] & (tg["split"] == s)).sum()) for s in ("train", "validation", "test")}
    res["observed_counts"] = counts
    res["n_images_with_no_main_class"] = int((~tg["observed"].any(axis=1)).sum())
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--evidence", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    t0 = time.time()
    before = tree_digest(args.src)
    status = {"audit_run_complete": False, "started": time.strftime("%Y-%m-%d %H:%M:%S")}
    dump(os.path.join(args.out, "readiness_iter006.json"), {**status, "lesion_probe_ready": False,
                                                            "note": "running"})

    inp = nih_audit.load_inputs(args.src)
    mirror_sizes = {"README_CHESTXRAY.pdf": json.load(open(os.path.join(args.evidence, "fetch_summary.json")))
                    ["sources"]["author_readme_mirror_pdf"].get("bytes")}
    for f in nih_audit.META_FILES[1:]:
        mirror_sizes[f.split("/")[-1]] = len(inp["meta"][f])
    ev = coord_evidence.judge(args.evidence, mirror_sizes)
    dump(os.path.join(args.out, "nih_coord_evidence_judgement.json"), ev)

    checks, warnings, ctx = nih_audit.run_checks(inp)
    rd = nih_audit.readiness(checks, ev["coordinate_canvas_status"])
    dump(os.path.join(args.out, "nih_reaudit_checks.json"), {"required_checks": nih_audit.REQUIRED_CHECKS,
                                                             "checks": checks, "warnings": warnings})

    tg = CT.build_split_targets(inp["manifest"])
    tchk = target_checks(tg, inp["manifest"])
    np.savez_compressed(os.path.join(args.out, "nih_class_targets.npz"), **tg)
    dump(os.path.join(args.out, "nih_class_targets_summary.json"), {
        "classes": CT.MAIN_CLASSES, "shape_fine": list(tg["fine"].shape), "shape_coarse": list(tg["coarse"].shape),
        "unknown_rule": "해당 클래스 bbox 없음 = unknown (observed=False, target 0, loss·metric 제외); 음성 GT 아님",
        "checks": tchk,
        "canvas_caveat": "target은 bbox 좌표를 1024 PNG canvas로 해석한 가정(assumed)에 의존한다"})

    after = tree_digest(args.src)
    split_sizes = {s: sum(1 for r in inp["manifest"] if r["split"] == s) for s in ("train", "validation", "test")}
    readiness = {
        "iteration": "iter_006",
        "gpu_device_minutes": 0.0,
        "audit_run_complete": True,
        "audit_run_complete_meaning": "감사 스크립트가 모든 단계를 실행했다는 뜻이며 데이터 준비 완료가 아님",
        **rd,
        "gpu_probe_entry_allowed": rd["lesion_probe_ready"],
        "class_targets_pass": tchk["pass"],
        "preserved": {"n_patients": len({r["patient_id"] for r in inp["manifest"]}), "split_sizes": split_sizes,
                      "input_files_hashed": len(before), "inputs_unchanged_during_audit": before == after,
                      "input_digest_sha256": hashlib.sha256(json.dumps(before, sort_keys=True).encode()).hexdigest()},
        "provenance_limitations": [
            "NIH metadata·영상은 HF 미러(고정 revision)에서 받음. 원배포와의 byte 동일성은 unverified.",
            "공식 Box 폴더 목록과 크기 비교만 수행 (hash 없음): nih_coord_evidence_judgement.json의 mirror_vs_official_listing.",
            "README 미러 PDF는 공식 Box 목록의 README_CHESTXRAY.pdf와 크기가 다르다 (다른 판일 수 있음)."],
        "warnings": warnings,
        "wall_seconds": time.time() - t0,
    }
    readiness["package_complete"] = None
    readiness["package_complete_note"] = "iter_005의 package_complete는 폐기: audit_run_complete(실행)와 " \
                                         "lesion_probe_ready(데이터 준비)로 분리"
    dump(os.path.join(args.out, "readiness_iter006.json"), readiness)
    print(json.dumps({k: readiness[k] for k in ("audit_run_complete", "integrity_gate_pass", "lesion_probe_ready",
                                                  "coordinate_canvas_status", "failed_required_checks",
                                                  "class_targets_pass", "preserved")}, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
