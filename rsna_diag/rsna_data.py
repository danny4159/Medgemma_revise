"""RSNA 2018 adjudicated 자료 adapter: annotation/mapping 연결, 감사, 결정적 환자 split (iter_009).

- 최종 라벨은 labelGroup 'Calculated'(adjudication 결과)의 Normal / No Lung Opacity / Not Normal / Lung Opacity(local bbox)만 쓴다.
  Team 1/2/2a/QA/Adjudication 그룹의 개별 판독 라벨은 사용하지 않는다. 라벨 누락은 음성이 아니다.
- bbox: data.{x,y,width,height} pixel (annotation height/width=1024 canvas) -> xyxy.
- patient: mapping img_id `NNNNNNNN_SSS.png`의 8자리 접두어(NIH Patient ID). RSNA의 PatientID(DICOM)는 검사별 무작위라 쓰지 않는다.
"""
import collections
import hashlib
import json
import re
import zipfile

from . import dicom_min, geometry

SEED = 20260925
CAT_POS, CAT_NORMAL, CAT_NLONN = "opacity", "normal", "not_normal_no_opacity"
PRIORITY = [CAT_POS, CAT_NORMAL, CAT_NLONN]
LABEL_TO_CAT = {"Lung Opacity": CAT_POS, "Normal": CAT_NORMAL, "No Lung Opacity / Not Normal": CAT_NLONN}
# iter_010 분할 목표 (train / validation / 독립 확인)
SPLIT_TARGETS = {"train": {CAT_POS: 1200, CAT_NORMAL: 600, CAT_NLONN: 600},
                 "validation": {CAT_POS: 200, CAT_NORMAL: 100, CAT_NLONN: 100},
                 "confirm": {CAT_POS: 400, CAT_NORMAL: 200, CAT_NLONN: 200}}
IMG_RE = re.compile(r"(\d{8})_(\d{3})\.png")


def h(seed, key):
    return hashlib.sha1(f"{seed}:{key}".encode()).hexdigest()


def load_annotations(path):
    a = json.load(open(path))
    label = {}
    for g in a["labelGroups"]:
        for l in g["labels"]:
            label[l["id"]] = {"group": g["name"], "name": l["name"].strip(), "type": l["type"],
                              "mode": l["annotationMode"]}
    ann = a["datasets"][0]["annotations"]
    by = collections.defaultdict(lambda: {"cats": set(), "boxes": [], "exclude": False, "study": None, "series": None,
                                          "n_ann": 0})
    for x in ann:
        if "SOPInstanceUID" not in x:
            continue
        info = label[x["labelId"]]
        r = by[x["SOPInstanceUID"]]
        r["n_ann"] += 1
        r["study"], r["series"] = x["StudyInstanceUID"], x["SeriesInstanceUID"]
        if info["name"] == "Exclude":
            r["exclude"] = True
        if info["group"] != "Calculated":
            continue
        if info["name"] in LABEL_TO_CAT:
            r["cats"].add(LABEL_TO_CAT[info["name"]])
        if info["type"] == "local":
            d = x["data"]
            r["boxes"].append({"ann_id": x["id"], "n": x["annotationNumber"], "canvas": [x["width"], x["height"]],
                               "xywh": [d["x"], d["y"], d["width"], d["height"]]})
    return label, dict(by)


def load_mapping(path):
    m = json.load(open(path))
    sop_map, dups = {}, []
    for e in m:
        s = e["SOPInstanceUID"]
        if s in sop_map:
            dups.append(s)
        sop_map[s] = e
    return sop_map, dups


class RsnaZip:
    """전체 ZIP의 full member path <-> SOP UID. basename 충돌을 검출한다."""

    def __init__(self, path):
        self.path = path
        self.z = zipfile.ZipFile(path)
        self.members = {}
        self.collisions = []
        for n in self.z.namelist():
            if not n.endswith(".dcm"):
                continue
            sop = n.rsplit("/", 1)[-1][:-4]
            if sop in self.members:
                self.collisions.append((sop, self.members[sop], n))
            self.members[sop] = n

    def read(self, sop):
        return self.z.read(self.members[sop])

    def info(self, sop):
        i = self.z.getinfo(self.members[sop])
        return {"member": i.filename, "crc32": f"{i.CRC:08x}", "file_size": i.file_size}


def box_checks(rec):
    """local bbox 범위/면적 검사. returns list of problems."""
    prob = []
    for b in rec["boxes"]:
        cw, ch = b["canvas"]
        x, y, w, hh = b["xywh"]
        if (cw, ch) != (1024, 1024):
            prob.append(f"canvas {cw}x{ch}")
        if not (w > 0 and hh > 0):
            prob.append("nonpositive area")
        if x < 0 or y < 0 or x + w > cw + 1e-3 or y + hh > ch + 1e-3:
            prob.append("out of canvas")
    return prob


class AuditError(RuntimeError):
    pass


def audit_all(label, ann, sop_map, dups, rz):
    """30000 영상 전체 연결/태그 감사. returns (per-image dict sop->eligibility record, summary dict).

    mapping SOP 중복 또는 ZIP basename 충돌이 있으면 연결이 모호하므로 AuditError로 중단한다 (집계만 하지 않는다).
    """
    if dups or rz.collisions:
        raise AuditError(f"mapping duplicate SOP={len(dups)} zip basename collisions={len(rz.collisions)}")
    summary = {"n_annotation_images": len(ann), "n_mapping": len(sop_map), "mapping_duplicate_sop": len(dups),
               "zip_members": len(rz.members), "zip_basename_collisions": len(rz.collisions),
               "excluded_reasons": collections.Counter(), "category_counts_eligible": collections.Counter(),
               "dicom_tag_signatures": collections.Counter()}
    recs = {}
    for sop, r in ann.items():
        reasons = []
        m = sop_map.get(sop)
        if m is None:
            reasons.append("not_in_mapping")
        if sop not in rz.members:
            reasons.append("not_in_zip")
        if r["exclude"]:
            reasons.append("exclude_label")
        if len(r["cats"]) != 1:
            reasons.append(f"calculated_cats={sorted(r['cats'])}")
        cat = next(iter(r["cats"])) if len(r["cats"]) == 1 else None
        if cat == CAT_POS and not r["boxes"]:
            reasons.append("opacity_without_box")
        if cat in (CAT_NORMAL, CAT_NLONN) and r["boxes"]:
            reasons.append("negative_with_box")
        reasons += box_checks(r)
        patient = None
        if m is not None:
            mm = IMG_RE.fullmatch(m["img_id"])
            if not mm:
                reasons.append("bad_img_id")
            else:
                patient = mm.group(1)
            if m["StudyInstanceUID"] != r["study"] or m["SeriesInstanceUID"] != r["series"]:
                reasons.append("study_series_uid_mismatch")
        if sop in rz.members:
            tags, _ = dicom_min.parse(rz.read(sop))
            sig = tuple(tags.get(k) for k in ("Rows", "Columns", "BitsStored", "PixelRepresentation", "PhotometricInterpretation",
                                              "SamplesPerPixel", "RescaleSlope", "RescaleIntercept", "WindowCenter", "WindowWidth",
                                              "NumberOfFrames", "PresentationLUTShape", "TransferSyntaxUID"))
            summary["dicom_tag_signatures"][str(sig)] += 1
            if tags.get("SOPInstanceUID") != sop:
                reasons.append("dicom_sop_tag_mismatch")
            reasons += dicom_min.display_problems(tags)
        recs[sop] = {"sop": sop, "img_id": m["img_id"] if m else None, "patient": patient, "category": cat,
                     "boxes": r["boxes"], "reasons": reasons, "orig_labels": m.get("orig_labels") if m else None}
        for x in reasons:
            summary["excluded_reasons"][x.split("=")[0]] += 1
        if not reasons:
            summary["category_counts_eligible"][cat] += 1
    summary["excluded_reasons"] = dict(summary["excluded_reasons"])
    summary["category_counts_eligible"] = dict(summary["category_counts_eligible"])
    summary["dicom_tag_signatures"] = dict(summary["dicom_tag_signatures"])
    return recs, summary


def patient_choice(recs, excluded_patients, seed=SEED):
    """eligible 영상에서 환자별 1영상을 고정 우선순위(양성->Normal->NLONN)와 seed 해시 순서로 고른다.

    returns (choice: patient -> rec, bias summary).
    """
    per = collections.defaultdict(list)
    for r in recs.values():
        if r["reasons"] or r["patient"] in excluded_patients:
            continue
        per[r["patient"]].append(r)
    choice, mixed = {}, 0
    for p, rs in per.items():
        cats = {r["category"] for r in rs}
        if len(cats) > 1:
            mixed += 1
        for c in PRIORITY:
            cand = sorted([r for r in rs if r["category"] == c], key=lambda r: h(seed, r["sop"]))
            if cand:
                choice[p] = cand[0]
                break
    bias = {"n_eligible_patients": len(per), "n_patients_multi_category": mixed,
            "note": "다중 category 환자는 양성>Normal>NLONN 우선순위로 배정되어 Normal/NLONN 풀은 양성 영상이 없는 환자로 편향된다"}
    return choice, bias


def make_split(choice, seed=SEED, targets=SPLIT_TARGETS):
    """환자 ID 해시 순으로 category 풀에서 split별로 순차 배정. 부족하면 예외 (과거 환자·중복으로 채우지 않는다).

    returns (splits: name -> sorted patients, pool sizes, reserve: category -> patients 남은 적격 환자).
    """
    pools = {c: sorted([p for p, r in choice.items() if r["category"] == c], key=lambda p: h(seed, "pat" + p))
             for c in PRIORITY}
    splits = {k: [] for k in targets}
    reserve = {}
    for c in PRIORITY:
        need = sum(t[c] for t in targets.values())
        if len(pools[c]) < need:
            raise RuntimeError(f"insufficient eligible patients for {c}: {len(pools[c])} < {need}")
        pos = 0
        for k, t in targets.items():
            splits[k] += pools[c][pos:pos + t[c]]
            pos += t[c]
        reserve[c] = pools[c][pos:]
    return {k: sorted(v) for k, v in splits.items()}, {c: len(v) for c, v in pools.items()}, reserve


def gt_entry(rec):
    """padding canvas(1024 정사각, offset 0) 기준 정규화 GT + 원본 xyxy."""
    top, left, side = geometry.pad_offsets(1024, 1024)
    out = []
    for b in rec["boxes"]:
        x, y, w, hh = b["xywh"]
        xyxy = [x, y, x + w, y + hh]
        out.append({"ann_id": b["ann_id"], "xyxy_px": xyxy, "yxyx_norm": geometry.canvas_to_norm(xyxy, top, left, side)})
    return out
