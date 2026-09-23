"""NIH ChestX-ray14: bbox CSV / Data_Entry / 공식 split 파싱, patient 단위 개발 split, ZIP member 확보.

좌표 규약: bbox CSV의 `[x,y,w,h]`는 배포 PNG canvas(pixel) 기준으로 해석하고 `[x0,y0,x1,y1] = [x,y,x+w,y+h]`로
명시적으로 변환한다. Data_Entry의 `OriginalImage[Width,Height]`는 좌표 canvas로 자동 사용하지 않는다.
canvas는 실제로 받은 PNG의 해상도와 배포 README의 기술로 따로 검증한다.
"""
import csv
import io
import random
import re
import zipfile

import numpy as np

HF_REPO = "alkzar90/NIH-Chest-X-ray-dataset"
BBOX_EXPECTED_HEADER = ["Image Index", "Finding Label", "Bbox [x", "y", "w", "h]"]
ENTRY_REQUIRED = ["Image Index", "Finding Labels", "Patient ID"]
# bbox CSV와 Data_Entry의 클래스 표기 차이 (관측 후 보고용 대응표; 자동 병합 근거는 보고서에 남긴다)
BBOX_TO_ENTRY_LABEL = {"Infiltrate": "Infiltration"}

SPLIT_SEED = 20260924
N_PATIENTS = 160
SPLIT_SIZES = {"train": 80, "validation": 32, "test": 48}
PER_STRATUM = {"train": 20, "validation": 8, "test": 12}
N_STRATA = 4  # 4 strata x 40명 = 160명
MIN_PER_CLASS = {"train": 20, "validation": 8, "test": 12}
MIN_READY_CLASSES = 2


def parse_bbox_csv(text):
    """비정상 header(`Bbox [x,y,w,h]`가 쉼표로 쪼개짐)와 trailing 빈 열을 명시적으로 검사한다."""
    rows = list(csv.reader(io.StringIO(text)))
    header = rows[0]
    report = {"raw_header": header, "n_header_cols": len(header)}
    core, trailing = header[:6], header[6:]
    report["header_core_matches_expected"] = core == BBOX_EXPECTED_HEADER
    report["trailing_header_cols"] = trailing
    report["trailing_header_all_empty"] = all(c.strip() == "" for c in trailing)
    boxes, problems = [], []
    col_counts = {}
    for i, r in enumerate(rows[1:], start=2):
        col_counts[len(r)] = col_counts.get(len(r), 0) + 1
        if not r or all(c.strip() == "" for c in r):
            problems.append({"line": i, "what": "empty_row"})
            continue
        extra = r[6:]
        if any(c.strip() for c in extra):
            problems.append({"line": i, "what": "non_empty_trailing", "values": extra})
        try:
            x, y, w, h = (float(v) for v in r[2:6])
        except ValueError:
            problems.append({"line": i, "what": "non_numeric_bbox", "values": r[2:6]})
            continue
        boxes.append({"line": i, "image": r[0].strip(), "label": r[1].strip(), "xywh": [x, y, w, h],
                      "xyxy": [x, y, x + w, y + h]})
    report["row_col_counts"] = col_counts
    report["n_rows"] = len(rows) - 1
    report["n_boxes"] = len(boxes)
    report["problems"] = problems
    return boxes, report


def parse_data_entry(text):
    rows = list(csv.reader(io.StringIO(text)))
    header = [h.strip() for h in rows[0]]
    report = {"raw_header": rows[0], "n_rows": len(rows) - 1}
    missing = [c for c in ENTRY_REQUIRED if c not in header]
    report["missing_required_cols"] = missing
    if missing:
        raise ValueError(f"Data_Entry missing columns {missing}")
    ix = {c: header.index(c) for c in header}
    entries, dup = {}, []
    for r in rows[1:]:
        if not r:
            continue
        rec = {c: r[ix[c]].strip() for c in header if ix[c] < len(r)}
        img = rec["Image Index"]
        if img in entries:
            dup.append(img)
        entries[img] = rec
    report["duplicate_image_ids"] = dup
    report["n_unique_images"] = len(entries)
    return entries, report


def parse_list(text):
    return [ln.strip() for ln in text.splitlines() if ln.strip()]


def filename_patient_prefix(img):
    m = re.fullmatch(r"(\d{8})_(\d{3})\.png", img)
    return m.group(1) if m else None


def link_boxes(boxes, entries, test_list, trainval_list):
    """bbox → Data_Entry(patient) 연결, 클래스 표기, 공식 split 소속, 중복을 보고한다."""
    test, trainval = set(test_list), set(trainval_list)
    rep = {"n_boxes": len(boxes)}
    imgs = sorted({b["image"] for b in boxes})
    rep["n_images"] = len(imgs)
    missing = [i for i in imgs if i not in entries]
    rep["images_missing_in_data_entry"] = missing
    # 동일 (image,label,xywh) 완전 중복
    seen, exact_dup = set(), []
    for b in boxes:
        k = (b["image"], b["label"], tuple(b["xywh"]))
        if k in seen:
            exact_dup.append(b["line"])
        seen.add(k)
    rep["exact_duplicate_box_lines"] = exact_dup
    labels = sorted({b["label"] for b in boxes})
    rep["bbox_labels"] = labels
    entry_labels = sorted({l for e in entries.values() for l in e["Finding Labels"].split("|")})
    rep["data_entry_labels"] = entry_labels
    rep["bbox_labels_not_in_entry_vocab"] = [l for l in labels if l not in entry_labels]
    rep["label_mapping_used"] = BBOX_TO_ENTRY_LABEL
    # bbox 클래스가 Data_Entry의 해당 영상 finding 목록에 있는지
    consistent, inconsistent = 0, []
    for b in boxes:
        e = entries.get(b["image"])
        if e is None:
            continue
        lab = BBOX_TO_ENTRY_LABEL.get(b["label"], b["label"])
        if lab in e["Finding Labels"].split("|"):
            consistent += 1
        else:
            inconsistent.append({"line": b["line"], "image": b["image"], "bbox_label": b["label"],
                                 "entry_labels": e["Finding Labels"]})
    rep["bbox_label_in_entry_labels"] = consistent
    rep["bbox_label_not_in_entry_labels"] = inconsistent
    # patient ID: Data_Entry가 authoritative, filename prefix는 교차 확인
    pid_mismatch = []
    for i in imgs:
        e = entries.get(i)
        if e is None:
            continue
        pref = filename_patient_prefix(i)
        if pref is None or int(pref) != int(e["Patient ID"]):
            pid_mismatch.append({"image": i, "prefix": pref, "patient_id": e["Patient ID"]})
    rep["patient_id_prefix_mismatch"] = pid_mismatch
    split_of = {}
    for i in imgs:
        split_of[i] = ("test" if i in test else "") + ("train_val" if i in trainval else "") or "none"
    rep["official_split_images"] = {s: sum(1 for v in split_of.values() if v == s) for s in sorted(set(split_of.values()))}
    rep["official_split_boxes"] = {}
    for b in boxes:
        s = split_of[b["image"]]
        rep["official_split_boxes"][s] = rep["official_split_boxes"].get(s, 0) + 1
    rep["n_patients"] = len({entries[i]["Patient ID"] for i in imgs if i in entries})
    return rep, split_of


def canvas_checks(boxes, canvas_w=1024, canvas_h=1024):
    """범위 밖 좌표를 원시 그대로 보고한다 (clipping·scale 추정 없음)."""
    out = []
    for b in boxes:
        x0, y0, x1, y1 = b["xyxy"]
        bad = []
        if b["xywh"][2] <= 0 or b["xywh"][3] <= 0:
            bad.append("non_positive_size")
        if x0 < 0 or y0 < 0:
            bad.append("negative_origin")
        if x1 > canvas_w or y1 > canvas_h:
            bad.append("exceeds_canvas")
        if bad:
            out.append({"line": b["line"], "image": b["image"], "label": b["label"], "xyxy": b["xyxy"], "issues": bad})
    return out


def patient_images(boxes, entries):
    """patient -> 정렬된 bbox 영상 목록. 영상 선택 규칙: patient의 bbox 영상 중 Image Index 사전순 첫 번째."""
    by_pid = {}
    for i in sorted({b["image"] for b in boxes}):
        if i in entries:
            by_pid.setdefault(entries[i]["Patient ID"], []).append(i)
    chosen = {pid: v[0] for pid, v in by_pid.items()}
    return by_pid, chosen


def image_classes(boxes):
    out = {}
    for b in boxes:
        out.setdefault(b["image"], set()).add(b["label"])
    return {k: sorted(v) for k, v in out.items()}


def make_dev_split(boxes, entries, seed=SPLIT_SEED):
    """성능 관측 전 고정하는 patient 단위 개발 split (공식 benchmark test가 아님).

    1) patient마다 bbox 영상 하나(사전순 첫 번째)를 고른다.
    2) 선택 영상의 bbox 클래스로 patient 수를 세고, 상위 N_STRATA개 클래스를 stratum 후보로 둔다
       (동률은 클래스 이름순).
    3) patient의 stratum = 선택 영상 클래스 중 후보에 속하는 것 가운데 patient 수가 가장 적은 클래스.
    4) stratum마다 patient ID 정렬 후 random.Random(seed + k)로 섞어 20/8/12명을 train/validation/test에 배정.
       stratum pool이 40명 미만이면 채우지 않고 부족을 보고한다 (숫자를 임의 축소하지 않음).
    """
    by_pid, chosen = patient_images(boxes, entries)
    cls = image_classes(boxes)
    counts = {}
    for pid, img in chosen.items():
        for c in cls[img]:
            counts[c] = counts.get(c, 0) + 1
    ranked = sorted(counts, key=lambda c: (-counts[c], c))
    strata = ranked[:N_STRATA]
    pool = {c: [] for c in strata}
    for pid in sorted(chosen, key=int):
        cs = [c for c in cls[chosen[pid]] if c in strata]
        if not cs:
            continue
        s = min(cs, key=lambda c: (counts[c], c))
        pool[s].append(pid)
    assign, shortfall = {}, {}
    need = sum(PER_STRATUM.values())
    for k, c in enumerate(strata):
        pids = list(pool[c])
        random.Random(seed + k).shuffle(pids)
        if len(pids) < need:
            shortfall[c] = {"available": len(pids), "needed": need}
        start = 0
        for split, n in PER_STRATUM.items():
            for pid in pids[start:start + n]:
                assign[pid] = {"split": split, "stratum": c, "image": chosen[pid], "classes": cls[chosen[pid]]}
            start += n
    info = {"seed": seed, "class_patient_counts_chosen_image": counts, "strata": strata,
            "stratum_pool_sizes": {c: len(pool[c]) for c in strata}, "shortfall": shortfall,
            "n_patients_with_bbox": len(chosen),
            "n_patients_multiple_bbox_images": sum(1 for v in by_pid.values() if len(v) > 1)}
    return assign, info


def split_class_counts(assign):
    out = {}
    for pid, a in assign.items():
        for c in a["classes"]:
            out.setdefault(c, {s: 0 for s in SPLIT_SIZES})[a["split"]] += 1
    return out


def lesion_readiness(assign, class_counts):
    sizes = {s: sum(1 for a in assign.values() if a["split"] == s) for s in SPLIT_SIZES}
    ok_classes = [c for c, v in class_counts.items() if all(v[s] >= MIN_PER_CLASS[s] for s in MIN_PER_CLASS)]
    return {"split_sizes": sizes, "split_sizes_target": SPLIT_SIZES,
            "sizes_met": sizes == SPLIT_SIZES and len(assign) == N_PATIENTS,
            "classes_meeting_minimum": sorted(ok_classes), "min_per_class": MIN_PER_CLASS,
            "classes_met": len(ok_classes) >= MIN_READY_CLASSES}


class ZipIndex:
    """HTTPRangeFile 위의 표준 zipfile로 central directory를 읽는다."""

    def __init__(self, rangefile):
        self.rf = rangefile
        # EOCD(+zip64 locator, comment) 영역을 한 번에 prefetch
        tail = min(self.rf.size, 1 << 17)
        self.rf.prefetch(self.rf.size - tail, self.rf.size - 1)
        self.zf = zipfile.ZipFile(self.rf)
        self.rf.disk_cache_dir = None  # member 데이터는 영상 파일로 따로 저장한다
        self.members = {zi.filename.split("/")[-1]: zi for zi in self.zf.infolist() if not zi.is_dir()}

    def read_member(self, name):
        zi = self.members[name]
        # local header(30) + name + extra(여유 1 KiB) + 압축 데이터를 한 번에 요청
        self.rf.prefetch(zi.header_offset, zi.header_offset + 30 + len(zi.filename.encode()) + 1024 + zi.compress_size)
        with self.zf.open(zi) as f:  # 표준 zipfile이 CRC-32를 검사한다
            data = f.read()
        return data, {"member": zi.filename, "compress_type": zi.compress_type, "compress_size": zi.compress_size,
                      "file_size": zi.file_size, "crc32": f"{zi.CRC:08x}", "header_offset": zi.header_offset}


def decode_png(data):
    from PIL import Image
    im = Image.open(io.BytesIO(data))
    im.load()
    a = np.asarray(im)
    return im, a
