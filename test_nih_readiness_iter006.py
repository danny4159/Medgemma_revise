"""iter_006: NIH readiness 필수 gate 단일 결함 주입 테스트 (CPU, 네트워크 없음, 원본 자료 읽기 전용).

실행: python research/test_nih_readiness_iter006.py --src research/results/iter_005 \
          --evidence research/results/iter_006/coord_evidence --out research/results/iter_006/nih_readiness_tests

각 사례는 실제 감사 입력의 메모리 복사본(영상은 fixture 디렉터리의 복사본)에 결함 하나를 넣는다.
metadata를 바꾸는 사례는 provenance 기록도 바뀐 bytes에 맞춰 갱신해, blob 검사가 아닌 목표 검사가
결함을 잡는지 확인한다 (blob 불일치 자체는 별도 사례).
"""
import argparse
import copy
import json
import os
import shutil
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from grounding_data import coord_evidence, nih_audit  # noqa: E402
from grounding_data.net import git_blob_sha1, sha256_bytes  # noqa: E402

RESULTS = []
BBOX = "data/BBox_List_2017.csv"
ENTRY = "data/Data_Entry_2017_v2020.csv"


def check(name, cond, detail=""):
    RESULTS.append({"test": name, "pass": bool(cond), "detail": str(detail)[:600]})
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {str(detail)[:220]}", flush=True)


def set_meta(inp, f, body, update_prov=True):
    inp["meta"][f] = body
    if update_prov:
        p = inp["prov_meta"][f]
        p["listed_git_blob_id"] = git_blob_sha1(body)
        p["sha256"] = sha256_bytes(body)


def lines_of(inp, f):
    return inp["meta"][f].decode("utf-8").split("\n")


def join(lines):
    return "\n".join(lines).encode("utf-8")


def run(inp, canvas="assumed"):
    checks, warnings, ctx = nih_audit.run_checks(inp)
    return checks, nih_audit.readiness(checks, canvas)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--evidence", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    fx = os.path.join(args.out, "fixtures")
    if os.path.exists(fx):
        shutil.rmtree(fx)
    os.makedirs(fx)
    base = nih_audit.load_inputs(args.src)
    selected = {r["image"] for r in base["manifest"]}

    # 정상 입력
    checks, rd = run(copy.deepcopy(base))
    check("valid: integrity gate passes, strict readiness false (canvas assumed) with canvas blocker only",
          rd["integrity_gate_pass"] and not rd["lesion_probe_ready"]
          and [b["what"] for b in rd["blockers"]] == ["coordinate_canvas_not_directly_documented"], rd["blockers"])
    rd2 = nih_audit.readiness(checks, "documented_direct")
    check("valid + (synthetic) documented_direct canvas: lesion_probe_ready true", rd2["lesion_probe_ready"])
    rd3 = nih_audit.readiness(checks, "undocumented")
    check("valid + undocumented canvas: false", not rd3["lesion_probe_ready"])

    def case(name, mutate, expect):
        inp = copy.deepcopy(base)
        mutate(inp)
        c, r = run(inp)
        failed = r["failed_required_checks"]
        ok = (not r["integrity_gate_pass"]) and (not r["lesion_probe_ready"]) and all(e in failed for e in expect)
        # 최소한 한 사례군은 목표 검사만 실패하는지(단일 결함 분리) 기록한다
        check(f"defect {name}: readiness false, {expect} failed", ok, {"failed": failed})
        return failed

    bl = lines_of(base, BBOX)
    # 선택되지 않은 영상의 bbox 행 (다른 검사에 영향이 적은 곳에 결함을 넣는다)
    free_i = next(i for i, ln in enumerate(bl[1:], start=1) if ln and ln.split(",")[0] not in selected)
    sel_i = next(i for i, ln in enumerate(bl[1:], start=1) if ln and ln.split(",")[0] in selected)

    def bbox_row(i, fn):
        def m(inp):
            L = lines_of(inp, BBOX)
            parts = L[i].split(",")
            L[i] = ",".join(fn(parts))
            set_meta(inp, BBOX, join(L))
        return m

    def header(inp):
        L = lines_of(inp, BBOX)
        L[0] = L[0].replace("h]", "hh]")
        set_meta(inp, BBOX, join(L))

    iso = {}
    iso["header"] = case("bbox header core changed", header, ["bbox_header_format"])
    iso["trailing"] = case("bbox row non-empty trailing column",
                           bbox_row(free_i, lambda p: p[:6] + ["junk"] + p[7:]), ["bbox_header_format"])
    iso["short_row"] = case("bbox row with 5 columns", bbox_row(free_i, lambda p: p[:5]), ["bbox_header_format"])

    def empty_row(inp):
        L = lines_of(inp, BBOX)
        L.insert(free_i, ",,,,,")
        set_meta(inp, BBOX, join(L))

    iso["empty_row"] = case("bbox empty row inserted", empty_row, ["bbox_header_format"])
    for tok in ("nan", "inf", "-inf"):
        iso[f"coord_{tok}"] = case(f"bbox coordinate {tok}", bbox_row(free_i, lambda p, t=tok: p[:4] + [t] + p[5:]),
                                   ["bbox_coords_finite_positive"])
    iso["zero_w"] = case("bbox zero width", bbox_row(free_i, lambda p: p[:4] + ["0"] + p[5:]),
                         ["bbox_coords_finite_positive"])
    iso["neg_h"] = case("bbox negative height", bbox_row(free_i, lambda p: p[:5] + ["-3"] + p[6:]),
                        ["bbox_coords_finite_positive"])
    iso["neg_x"] = case("bbox negative origin", bbox_row(free_i, lambda p: p[:2] + ["-1"] + p[3:]),
                        ["bbox_coords_finite_positive"])
    iso["oob"] = case("bbox exceeds 1024 canvas", bbox_row(free_i, lambda p: p[:2] + ["1000", p[3], "100"] + p[5:]),
                      ["bbox_within_assumed_canvas"])
    iso["label_link"] = case("bbox label not among image findings (selected image)",
                             bbox_row(sel_i, lambda p: p[:1] + ["Hernia"] + p[2:]), ["finding_link"])
    iso["sel_coord"] = case("selected image bbox coordinate changed (manifest annotation stale)",
                            bbox_row(sel_i, lambda p: p[:2] + [str(float(p[2]) + 1.0)] + p[3:]),
                            ["annotation_matches_csv"])

    el = lines_of(base, ENTRY)
    bbox_imgs = {ln.split(",")[0] for ln in bl[1:] if ln}
    free_e = next(i for i, ln in enumerate(el[1:], start=1) if ln and ln.split(",")[0] not in bbox_imgs)
    bbox_free_e = next(i for i, ln in enumerate(el[1:], start=1)
                       if ln and ln.split(",")[0] in bbox_imgs and ln.split(",")[0] not in selected)
    sel_e = next(i for i, ln in enumerate(el[1:], start=1) if ln and ln.split(",")[0] in selected)
    hdr = el[0].split(",")
    pid_col, lab_col = hdr.index("Patient ID"), hdr.index("Finding Labels")

    def entry(fn):
        def m(inp):
            set_meta(inp, ENTRY, join(fn(lines_of(inp, ENTRY))))
        return m

    iso["dup_id"] = case("Data_Entry duplicate image ID", entry(lambda L: L[:-1] + [L[free_e]] + L[-1:]),
                         ["metadata_ids_unique"])

    def relabel(L):
        p = L[bbox_free_e].split(",")
        p[lab_col] = "No Finding"
        L[bbox_free_e] = ",".join(p)
        return L

    iso["finding_link"] = case("Data_Entry findings of a bbox image lose the bbox class", entry(relabel),
                               ["finding_link"])

    def repid(L):
        p = L[sel_e].split(",")
        p[pid_col] = str(int(p[pid_col]) + 999999)
        L[sel_e] = ",".join(p)
        return L

    iso["patient_link"] = case("Data_Entry patient ID of a selected image changed", entry(repid), ["patient_link"])
    iso["no_col"] = case("Data_Entry missing Patient ID column",
                         entry(lambda L: [L[0].replace("Patient ID", "PatientID")] + L[1:]), ["patient_link"])

    def list_dup(inp):
        L = lines_of(inp, "data/test_list.txt")
        set_meta(inp, "data/test_list.txt", join([L[0]] + L))

    iso["list_dup"] = case("official test_list duplicate ID", list_dup, ["metadata_ids_unique"])
    # metadata blob 불일치 (provenance 기록은 그대로)
    iso["blob"] = case("metadata blob mismatch (Data_Entry byte changed, record unchanged)",
                       lambda inp: set_meta(inp, ENTRY, inp["meta"][ENTRY] + b"\n", update_prov=False),
                       ["meta_blob_integrity"])
    iso["blob_readme"] = case("metadata blob mismatch (README changed, record unchanged)",
                              lambda inp: set_meta(inp, "README.md", inp["meta"]["README.md"] + b" ",
                                                   update_prov=False), ["meta_blob_integrity"])

    def drop_blob(inp):
        inp["prov_meta"][BBOX]["listed_git_blob_id"] = None

    iso["no_blob"] = case("provenance listed blob id missing", drop_blob, ["meta_blob_integrity"])

    # manifest·split
    def man(fn):
        def m(inp):
            fn(inp["manifest"])
        return m

    tr = next(i for i, r in enumerate(base["manifest"]) if r["split"] == "train")

    def move_split(M):
        M[tr]["split"] = "validation"

    iso["move_split"] = case("manifest patient moved train->validation", man(move_split),
                             ["split_reproducible", "split_sizes_160_80_32_48"])

    def dup_patient(M):
        r = copy.deepcopy(M[tr])
        r["split"] = "test"
        M.append(r)

    iso["dup_patient"] = case("same patient/image in two splits", man(dup_patient),
                              ["split_no_overlap", "split_sizes_160_80_32_48"])

    def drop_rows(M):
        del M[:]

    iso["empty_manifest"] = case("manifest emptied (sample reduced)", man(drop_rows),
                                 ["split_sizes_160_80_32_48", "main_classes_meet_minimum"])

    def ann(M):
        M[tr]["annotation"][0]["xyxy"][2] += 5.0

    iso["ann"] = case("manifest annotation tampered", man(ann), ["annotation_matches_csv"])

    def pid(M):
        M[tr]["patient_id"] = str(int(M[tr]["patient_id"]) + 1)

    iso["man_pid"] = case("manifest patient id tampered", man(pid), ["patient_link"])

    # 영상 결함 (fixture 복사본)
    img0 = base["manifest"][tr]["image"]
    src0 = base["image_paths"][img0]

    def img_case(name, make):
        p = os.path.join(fx, name + "_" + img0)
        make(p)

        def m(inp):
            inp["image_paths"][img0] = p
        return case(f"image {name}", m, ["images_hash_size"])

    def pixel(p):
        a = np.array(Image.open(src0))
        a[10, 10] = (a[10, 10].astype(int) + 1) % 256
        Image.fromarray(a).save(p)

    iso["img_pixel"] = img_case("one pixel changed", pixel)
    iso["img_resave"] = img_case("re-encoded (same pixels, different file bytes)",
                                 lambda p: Image.open(src0).save(p, compress_level=1))
    iso["img_resize"] = img_case("resized to 512", lambda p: Image.open(src0).resize((512, 512)).save(p))
    iso["img_missing"] = img_case("missing file", lambda p: None)

    def img_dup(inp):
        other = next(r["image"] for r in inp["manifest"] if r["split"] == "test")
        inp["image_paths"][other] = inp["image_paths"][img0]

    iso["img_dup"] = case("test image file replaced by a train image (pixel dup across splits)", img_dup,
                          ["images_hash_size", "split_no_overlap"])

    # readiness 함수 자체의 fail-closed
    for label, mut in (("missing key", lambda c: c.pop("patient_link")),
                       ("pass is string 'true'", lambda c: c.__setitem__("finding_link", {"pass": "true"})),
                       ("pass is None", lambda c: c.__setitem__("images_hash_size", {"pass": None})),
                       ("pass is 1", lambda c: c.__setitem__("split_no_overlap", {"pass": 1})),
                       ("entry not a dict", lambda c: c.__setitem__("meta_blob_integrity", True))):
        c2 = copy.deepcopy(checks)
        mut(c2)
        r = nih_audit.readiness(c2, "documented_direct")
        check(f"readiness fail-closed: {label}", not r["integrity_gate_pass"] and not r["lesion_probe_ready"],
              r["failed_required_checks"])
    check("readiness: every REQUIRED check has at least one injected defect that fails it",
          set(nih_audit.REQUIRED_CHECKS) <= {k for v in iso.values() for k in v},
          sorted(set(nih_audit.REQUIRED_CHECKS) - {k for v in iso.values() for k in v}))

    # 좌표 근거 판정: 인용문이 없으면 assumed로도 올리지 않는다
    ev_fx = os.path.join(fx, "evidence_missing_xywh")
    os.makedirs(ev_fx)
    shutil.copy(os.path.join(args.evidence, "fetch_summary.json"), ev_fx)
    for f in os.listdir(args.evidence):
        if f.endswith(".txt") and not f.startswith("author_readme_mirror_pdf_p02"):
            shutil.copy(os.path.join(args.evidence, f), ev_fx)
    j = coord_evidence.judge(ev_fx)
    check("coord evidence without README xywh page -> undocumented (not assumed)",
          j["coordinate_canvas_status"] == "undocumented", j["coordinate_canvas_status"])
    j = coord_evidence.judge(args.evidence)
    check("coord evidence (real) -> assumed, direct statement not found, all quotes found",
          j["coordinate_canvas_status"] == "assumed" and not j["direct_canvas_statement_found"]
          and all(c["quote_found_in_page"] for c in j["claims"]), [(c["key"], c["quote_found_in_page"])
                                                                   for c in j["claims"]])

    n_fail = sum(not r["pass"] for r in RESULTS)
    with open(os.path.join(args.out, "nih_readiness_tests.json"), "w") as f:
        json.dump({"n": len(RESULTS), "n_fail": n_fail, "results": RESULTS,
                   "failed_sets": {k: v for k, v in iso.items()}}, f, indent=1, ensure_ascii=False)
    print(f"NIH readiness tests: {len(RESULTS) - n_fail}/{len(RESULTS)} pass")
    if n_fail:
        sys.exit(1)


if __name__ == "__main__":
    main()
