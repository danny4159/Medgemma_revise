"""iter_039 PadChest-GR 입력 검증·적격성·사전 표본 선택 (CPU only, 모델 미사용).

- padchest_audit038의 loader를 강화한 판본: JSON 중복 key, 결측 연결 필드, ImageID의 환자/study/split 충돌을 drop_duplicates 이전에 검사하고 차단한다.
- 표본 규칙은 모델 출력을 보기 전에 SPEC으로 잠근다 (seed 20260930). 문장 원문은 private manifest에만 둔다.
- 분할 zip(.001-.037)은 디스크에 합치지 않고 ConcatFile로 읽는다.
"""
import hashlib
import io
import json
import math
import os
import re
import zipfile
from collections import Counter, defaultdict

import pandas as pd

RAW = "results/datasets/padchest_gr/raw"
IMG_DIR = "results/datasets/padchest_gr/images"
JSON_NAME = "grounded_reports_20240819.json"
ZIP_NAME = "master_table.csv.zip"
PINNED = {
    JSON_NAME: "efa16513850dc10f87073debb9c4b3ae1d0a1ae611f01b5705e808179854b14b",
    ZIP_NAME: "3e1d27c603f7b89d36dec0b69d03b45714deb5e6aa866ba0e008987c2f40d9ba",
}
SEED = 20260930
# 사전 고정 시간 비교 문구 규칙: progression 필드가 None이 아니거나 sentence_en이 이 정규식과 맞으면 '시간 비교 필요'로 제외.
TEMPORAL_RE = re.compile(
    r"\b(increas\w*|decreas\w*|unchanged|previous\w*|prior|compar\w*|new|resolv\w*|stable|worsen\w*|improv\w*|"
    r"persist\w*|progress\w*|interval|again|remain\w*|since|follow-?up|reduc\w*|chang\w*|ago|evolution|evolv\w*)\b", re.I)
SPEC = {
    "seed": SEED, "sizes": {"D": 24, "E": 288, "E96": 96, "F": 120},
    "eligible": "abnormal==True, boxes nonempty & valid normalized xyxy, progression is None, sentence_en nonempty, "
                "no TEMPORAL_RE match, labels nonempty and mapped to label_group",
    "pair_rule": "per image: among eligible-finding pairs with distinct sentence_en, min sha256(seed|ImageID|i|j); "
                 "per patient: image with min sha256(seed|PatientID|ImageID) among images with >=2 eligible findings",
    "strata": "share_broad_group(label_group intersection of the pair) x multi_box(any finding of the pair has >1 official box)",
    "allocation": "largest-remainder proportional; in-stratum order by sha256(seed|split|PatientID); "
                  "D taken first, E288 from remainder, E96 = per-stratum first-min(q96,q288) of E288 order; F from validation",
    "qa_qb": "random assignment of the two sentences to IDs qA/qB by sha256(seed|ImageID|assign) parity",
}


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 22), b""):
            h.update(b)
    return h.hexdigest()


def h(*parts):
    return hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()


def _no_dup_pairs(pairs):
    d = {}
    for k, v in pairs:
        if k in d:
            raise ValueError(f"duplicate JSON key {k!r}")
        d[k] = v
    return d


class InputError(RuntimeError):
    pass


def load_inputs(raw=RAW):
    """원본 두 파일을 pinned sha와 대조하고 연결 오류를 차단한다. returns (reports, master, links)."""
    shas = {n: sha256_file(os.path.join(raw, n)) for n in PINNED}
    if shas != PINNED:
        raise InputError(f"raw sha256 mismatch: {shas}")
    z = zipfile.ZipFile(os.path.join(raw, ZIP_NAME))
    if z.testzip() is not None:
        raise InputError("master zip CRC failure")
    if z.namelist() != ["master_table.csv"]:
        raise InputError(f"unexpected zip members {z.namelist()}")
    m = pd.read_csv(z.open("master_table.csv"), dtype=str)
    with open(os.path.join(raw, JSON_NAME)) as f:
        reports = json.load(f, object_pairs_hook=_no_dup_pairs)
    need = ["ImageID", "PatientID", "StudyID", "split", "label", "label_group"]
    for c in need:
        if c not in m.columns:
            raise InputError(f"master column missing {c}")
    for c in ["ImageID", "PatientID", "StudyID", "split"]:
        if m[c].isna().any() or (m[c].str.strip() == "").any():
            raise InputError(f"blank {c} in master")
    for key in ("PatientID", "StudyID", "split"):
        if (m.groupby("ImageID")[key].nunique() > 1).any():
            raise InputError(f"ImageID with conflicting {key}")
    for a, b in (("StudyID", "PatientID"), ("PatientID", "split")):
        if (m.groupby(a)[b].nunique() > 1).any():
            raise InputError(f"{a} with conflicting {b}")
    if m.split.isin(["train", "validation", "test"]).sum() != len(m):
        raise InputError("unknown split value")
    first = m.drop_duplicates("ImageID").set_index("ImageID")
    ids = [r.get("ImageID") for r in reports]
    if any(not isinstance(i, str) or not i for i in ids):
        raise InputError("blank ImageID in reports")
    if len(ids) != len(set(ids)):
        raise InputError("duplicate ImageID in reports")
    miss = [i for i in ids if i not in first.index]
    if miss:
        raise InputError(f"{len(miss)} report images not in master")
    bad_study = sum(r.get("StudyID") != first.StudyID[r["ImageID"]] for r in reports)
    if bad_study:
        raise InputError(f"{bad_study} report/master StudyID mismatches")
    lab2grp = defaultdict(set)
    for lab, grp in zip(m.label, m.label_group):
        lab2grp[lab].add(grp)
    if any(len(v) > 1 for v in lab2grp.values()):
        raise InputError("label maps to multiple label_group")
    links = {"img2split": first.split.to_dict(), "img2patient": first.PatientID.to_dict(),
             "img2study": first.StudyID.to_dict(), "lab2grp": {k: next(iter(v)) for k, v in lab2grp.items()},
             "inputs_sha256": shas}
    return reports, m, links


def valid_box(b):
    return (isinstance(b, list) and len(b) == 4 and all(isinstance(v, (int, float)) and not isinstance(v, bool)
                                                        and math.isfinite(v) for v in b)
            and 0 <= b[0] < b[2] <= 1 and 0 <= b[1] < b[3] <= 1)


def eligibility(f, lab2grp):
    """returns (True, '') or (False, reason). reason은 집계용."""
    if f.get("abnormal") is not True:
        return False, "not_abnormal"
    for k in ("sentence_en", "boxes", "labels", "locations"):
        if k not in f:
            return False, "schema_missing"
    if not f["boxes"]:
        return False, "no_box"
    if not all(valid_box(b) for b in f["boxes"]):
        return False, "invalid_box"
    if f.get("progression") is not None:
        return False, "progression_field"
    s = f["sentence_en"]
    if not isinstance(s, str) or not s.strip():
        return False, "empty_sentence"
    if TEMPORAL_RE.search(s):
        return False, "temporal_phrase"
    if not f["labels"] or any(l not in lab2grp for l in f["labels"]):
        return False, "label_unmapped"
    return True, ""


def image_pool(reports, links, split):
    """split의 환자 -> 사전 규칙으로 고른 (영상, 문장쌍) 후보. returns (pool list, exclusion counts)."""
    lab2grp = links["lab2grp"]
    excl = Counter()
    per_pat = defaultdict(list)
    for r in reports:
        iid = r["ImageID"]
        if links["img2split"][iid] != split:
            continue
        el = []
        for idx, f in enumerate(r["findings"]):
            ok, why = eligibility(f, lab2grp)
            if ok:
                el.append(idx)
            else:
                excl[why] += 1
        if len(el) < 2:
            excl["image_lt2_eligible"] += 1
            continue
        pairs = [(i, j) for a, i in enumerate(el) for j in el[a + 1:]
                 if r["findings"][i]["sentence_en"].strip().lower() != r["findings"][j]["sentence_en"].strip().lower()]
        if not pairs:
            excl["image_no_distinct_pair"] += 1
            continue
        i, j = min(pairs, key=lambda p: h(SEED, iid, p[0], p[1]))
        fi, fj = r["findings"][i], r["findings"][j]
        share = bool({lab2grp[l] for l in fi["labels"]} & {lab2grp[l] for l in fj["labels"]})
        multi = len(fi["boxes"]) > 1 or len(fj["boxes"]) > 1
        per_pat[links["img2patient"][iid]].append(
            {"PatientID": links["img2patient"][iid], "ImageID": iid, "StudyID": r["StudyID"], "i": i, "j": j,
             "share_group": share, "multi_box": multi, "split": split})
    pool = []
    for pid, cands in per_pat.items():
        pool.append(min(cands, key=lambda c: h(SEED, pid, c["ImageID"])))
    excl["patients_with_pool_image"] = len(pool)
    return pool, dict(excl)


def apportion(sizes, n):
    """largest remainder. sizes: {stratum: count}."""
    tot = sum(sizes.values())
    raw = {k: n * v / tot for k, v in sizes.items()}
    q = {k: min(sizes[k], int(math.floor(x))) for k, x in raw.items()}
    rem = n - sum(q.values())
    for k in sorted(raw, key=lambda k: (-(raw[k] - math.floor(raw[k])), k)):
        if rem <= 0:
            break
        if q[k] < sizes[k]:
            q[k] += 1
            rem -= 1
    return q


def stratum(c):
    return f"share{int(c['share_group'])}_multi{int(c['multi_box'])}"


def select(pool, split, sizes, banned_patients=(), banned_ok=lambda c: True):
    """pool을 층별 hash 순으로 정렬하고 D/E/E96를 (또는 F를) 뽑는다. returns dict name -> list of candidates (순서 유지)."""
    by = defaultdict(list)
    for c in pool:
        if c["PatientID"] in banned_patients or not banned_ok(c):
            continue
        by[stratum(c)].append(c)
    for k in by:
        by[k].sort(key=lambda c: h(SEED, split, c["PatientID"]))
    out = {}
    for name, n in sizes:
        cnt = {k: len(v) for k, v in by.items()}
        n_eff = min(n, sum(cnt.values()))
        q = apportion(cnt, n_eff) if n_eff else {}
        chosen = []
        for k in sorted(by):
            chosen += by[k][:q.get(k, 0)]
            by[k] = by[k][q.get(k, 0):]
        out[name] = {"chosen": chosen, "quota": q, "n_requested": n, "n_selected": len(chosen),
                     "stratum_sizes_before": cnt}
    return out


def assign_ids(iid, fi_idx, fj_idx):
    """두 finding index를 qA/qB에 무작위 배정 (좌표·category·원문 순서와 독립)."""
    if int(h(SEED, iid, "assign"), 16) % 2 == 0:
        return {"qA": fi_idx, "qB": fj_idx}
    return {"qA": fj_idx, "qB": fi_idx}


# ---------------- 분할 zip 읽기 ----------------
class ConcatFile(io.RawIOBase):
    """binary-split 파일들을 하나의 seekable 읽기 전용 파일처럼 읽는다."""

    def __init__(self, paths):
        self.paths = paths
        self.sizes = [os.path.getsize(p) for p in paths]
        self.starts = [0]
        for s in self.sizes:
            self.starts.append(self.starts[-1] + s)
        self.total = self.starts[-1]
        self.pos = 0
        self._fh = {}

    def readable(self):
        return True

    def seekable(self):
        return True

    def tell(self):
        return self.pos

    def seek(self, off, whence=0):
        self.pos = {0: off, 1: self.pos + off, 2: self.total + off}[whence]
        return self.pos

    def _f(self, i):
        if i not in self._fh:
            self._fh[i] = open(self.paths[i], "rb")
        return self._fh[i]

    def readinto(self, b):
        want = len(b)
        got = 0
        while got < want and self.pos < self.total:
            i = max(k for k in range(len(self.sizes)) if self.starts[k] <= self.pos)
            f = self._f(i)
            f.seek(self.pos - self.starts[i])
            n = min(want - got, self.sizes[i] - (self.pos - self.starts[i]))
            data = f.read(n)
            if not data:
                break
            b[got:got + len(data)] = data
            got += len(data)
            self.pos += len(data)
        return got

    def close(self):
        for f in self._fh.values():
            f.close()
        super().close()


def open_image_zip(img_dir=IMG_DIR):
    parts = [os.path.join(img_dir, f"PadChest_GR.zip.{i:03d}") for i in range(1, 38)]
    for p in parts:
        if not os.path.exists(p):
            raise InputError(f"missing part {p}")
    cf = io.BufferedReader(ConcatFile(parts), buffer_size=1 << 20)
    return zipfile.ZipFile(cf)


def zip_index(z):
    """basename -> ZipInfo (충돌이면 오류)."""
    idx = {}
    for zi in z.infolist():
        if zi.is_dir():
            continue
        b = os.path.basename(zi.filename)
        if b in idx:
            raise InputError(f"zip basename collision {b}")
        idx[b] = zi
    return idx
