"""iter_053 자료 gate + manifest 생성 (CPU only, 모델 미사용).

기존 iter_018 CheXpert 자산(results/iter_018/{source,manifests})을 읽기 전용으로 재검증한다. rsna_diag.cx18_data의 build/CLI는 호출하지 않는다.
python rr53_data.py check            # results/iter_053/data/data_check.json (자료·분할·중복·노출 검사)
python rr53_data.py build            # manifest_D/E/F.json (data_check가 passed일 때만, 기존 파일 덮어쓰기 금지)
"""
import csv
import glob
import hashlib
import io
import json
import os
import subprocess
import sys

import numpy as np
from PIL import Image

import rr53_spec as S
from rsna_diag import cx18_data as CD
from rsna_diag import cx18_spec as CX

OUT = "results/iter_053"
CSV_SHA256 = "40e3fdf15522fa1184d8b686f7695bf333b439b2b7a2f1db7c45d97a251bc05f"
HF_SHA256 = CD.HF_PARQUET_SHA256
MAN = "results/iter_018/manifests"
PC_D8_MANIFEST = "results/iter_047/data/manifest_D8.json"
EXPECT_SPLIT = {"D16": {c: 4 for c in CX.CATEGORIES}, "E48": {c: 12 for c in CX.CATEGORIES}}
EXPECT_F = {"present_present": 12, "absent_absent": 56, "absent_present": 17, "present_absent": 20}  # 계획: 00/01/10/11 = 56/17/20/12
EXPECT_F_BY_CODE = {"00": 56, "01": 17, "10": 20, "11": 12}
LEGACY_ROOT = "/SSD1_1TB/home/milab/daniel/08_medgemma/legacy/eval_samples"


class GateError(RuntimeError):
    pass


def sha(b):
    return hashlib.sha256(b).hexdigest()


def file_sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 22), b""):
            h.update(b)
    return h.hexdigest()


def write_new(path, text):
    if os.path.exists(path):
        raise FileExistsError(path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + f".{os.getpid()}.tmp"
    with open(tmp, "w") as f:
        f.write(text)
    os.replace(tmp, path)


def checked_sources():
    """HF Path 고유성·CSV 고정 digest를 cx18_data.load_sources/cross_check '앞에서' 강제한다 (set 축약으로 중복을 숨기지 않는다)."""
    import pandas as pd
    if file_sha(CD.MEDAUG_CSV) != CSV_SHA256:
        raise GateError("MedAug csv sha256 differs from pinned digest")
    if file_sha(CD.HF_PARQUET) != HF_SHA256:
        raise GateError("HF parquet sha256 differs from pinned digest")
    hf0 = pd.read_parquet(CD.HF_PARQUET)
    paths = list(hf0["Path"])
    if len(paths) != 234 or len(set(paths)) != len(paths):
        raise GateError(f"HF Path not unique/234: rows={len(paths)} unique={len(set(paths))}")
    raw_rows = list(csv.DictReader(open(CD.MEDAUG_CSV)))
    norm = [CD._norm_path(r["Path"]) for r in raw_rows]
    if len(norm) != 234 or len(set(norm)) != len(norm):
        raise GateError("MedAug csv Path not unique/234")
    hf, csv_by_path = CD.load_sources()
    cross = CD.cross_check(hf, csv_by_path)
    return hf, csv_by_path, dict(hf_rows=len(paths), hf_unique_paths=len(set(paths)), csv_rows=len(norm), csv_unique_paths=len(set(norm)),
                                 hf_sha256=HF_SHA256, csv_sha256=CSV_SHA256, cross_check=cross)


def verify_patients(hf):
    labels = json.load(open(f"{MAN}/labels.json"))
    sets = json.load(open(f"{MAN}/sets.json"))
    infer = [json.loads(l) for l in open(f"{MAN}/infer_manifest.jsonl")]
    if len(labels) != 169 or len(infer) != 169 or {r["id"] for r in infer} != set(labels):
        raise GateError("labels/infer manifest patient set != 169")
    # 원천에서 단일 frontal 선택 규칙을 다시 적용해 같은 환자·study인지 확인
    studies = CD.group_studies(hf)
    single, dropped = CD.select_single_frontal(studies)
    if set(single) != set(labels) or dropped:
        raise GateError(f"single-frontal selection differs from labels (n={len(single)}, dropped={dropped})")
    hf_by_path = {r["Path"]: r for _, r in hf.iterrows()}
    info = {}
    for pid, l in sorted(labels.items()):
        study, vname, row = single[pid]
        if row["Path"] != l["path"] or study != l["study"] or vname != l["view"]:
            raise GateError(f"{pid}: source row differs from labels")
        b = row["image"]["bytes"]
        if sha(b) != l["file_sha256"]:
            raise GateError(f"{pid}: source bytes sha != labels file_sha256")
        arr = np.asarray(Image.open(io.BytesIO(b)))
        if arr.dtype != np.uint8 or arr.ndim != 2:
            raise GateError(f"{pid}: unexpected decoded image {arr.dtype} {arr.shape}")
        if sha(arr.tobytes()) != l["pixel_sha256"]:
            raise GateError(f"{pid}: source pixel sha != labels pixel_sha256")
        ip = f"{MAN}/images/{pid}.jpg"
        if file_sha(ip) != l["file_sha256"]:
            raise GateError(f"{pid}: on-disk jpg sha != source bytes")
        cm = "present" if int(row["Cardiomegaly"]) == 3 else "absent"
        pe = "present" if int(row["Pleural Effusion"]) == 3 else "absent"
        if int(row["Cardiomegaly"]) not in (2, 3) or int(row["Pleural Effusion"]) not in (2, 3):
            raise GateError(f"{pid}: label not 2/3")
        if (cm, pe) != (l["cardiomegaly"], l["pleural_effusion"]) or l["category"] != f"{cm}_{pe}":
            raise GateError(f"{pid}: HF label state != labels.json")
        im = [r for r in infer if r["id"] == pid][0]
        if im["file_sha256"] != l["file_sha256"] or im["pixel_sha256"] != l["pixel_sha256"] or im["image"] != ip:
            raise GateError(f"{pid}: infer manifest differs from labels")
        info[pid] = dict(path=l["path"], study=l["study"], file_sha256=l["file_sha256"], pixel_sha256=l["pixel_sha256"], category=l["category"],
                         cardiomegaly=cm, pleural_effusion=pe, image=ip, ap_pa=l["ap_pa"], h=int(arr.shape[0]), w=int(arr.shape[1]))
    # 분할 재현
    cats = {}
    for pid, l in info.items():
        cats.setdefault(l["category"], []).append(pid)
    re_split = CX.split_patients(cats)
    if re_split != sets:
        raise GateError("recomputed split_patients != sets.json")
    # 분할 크기 (계획)
    for k, exp in EXPECT_SPLIT.items():
        for c, n in exp.items():
            if len(sets[k][c]) != n:
                raise GateError(f"{k}/{c} size {len(sets[k][c])} != {n}")
    fcodes = {S.code_of_category(c): len(v) for c, v in sets["F"].items()}
    if fcodes != EXPECT_F_BY_CODE:
        raise GateError(f"F sizes {fcodes} != plan {EXPECT_F_BY_CODE}")
    # 교집합: 환자·study(Path의 study는 환자 내 이름이므로 (환자,study) 쌍)·file/pixel hash
    members = {k: {p for v in sets[k].values() for p in v} for k in ("D16", "E48", "F")}
    inter = {}
    for a, b in (("D16", "E48"), ("D16", "F"), ("E48", "F")):
        inter[f"{a}&{b}"] = dict(patients=len(members[a] & members[b]),
                                 file_sha=len({info[p]["file_sha256"] for p in members[a]} & {info[p]["file_sha256"] for p in members[b]}),
                                 pixel_sha=len({info[p]["pixel_sha256"] for p in members[a]} & {info[p]["pixel_sha256"] for p in members[b]}),
                                 patient_study=len({(p, info[p]["study"]) for p in members[a]} & {(p, info[p]["study"]) for p in members[b]}))
    if any(v != 0 for d in inter.values() for v in d.values()):
        raise GateError(f"D/E/F intersection nonzero: {inter}")
    for k in members:
        if len({info[p]["file_sha256"] for p in members[k]}) != len(members[k]) or len({info[p]["pixel_sha256"] for p in members[k]}) != len(members[k]):
            raise GateError(f"duplicate file/pixel hash inside {k}")
    if len({info[p]["pixel_sha256"] for p in info}) != 169 or len({info[p]["file_sha256"] for p in info}) != 169:
        raise GateError("duplicate file/pixel hash among 169 patients")
    return info, sets, inter, dict(single_frontal_selection_reproduced=True, split_reproduced=True, n_patients=len(info))


def legacy_exact_dup(info):
    """legacy/eval_samples 전체의 이미지와 169개 영상의 file hash / 복원 pixel hash 정확 일치를 검사한다 (근사 average-hash 검사의 보완)."""
    fset = {v["file_sha256"] for v in info.values()}
    pset = {v["pixel_sha256"] for v in info.values()}
    n = 0
    hit = []
    for p in glob.glob(os.path.join(LEGACY_ROOT, "**", "*"), recursive=True):
        if not os.path.isfile(p) or not p.lower().endswith((".jpg", ".jpeg", ".png")):
            continue
        n += 1
        fh = file_sha(p)
        try:
            a = np.asarray(Image.open(p))
            ph = sha(a.tobytes()) if a.dtype == np.uint8 and a.ndim == 2 else None
        except Exception:
            ph = None
        if fh in fset or (ph is not None and ph in pset):
            hit.append(p)
    return dict(n_legacy_images_scanned=n, exact_file_or_pixel_matches=hit)


def exposure_scan(sets):
    """F 환자 ID가 과거 결과(manifest/iter_053 제외)에 나타났는지 grep으로 검사. D16/E48 노출은 iter_018 요청에서 확인한다."""
    out = {}
    for k in ("D16", "E48", "F"):
        ids = sorted({p for v in sets[k].values() for p in v})
        pat = os.path.join(OUT, "data", f"_ids_{k}.txt")
        os.makedirs(os.path.dirname(pat), exist_ok=True)
        if not os.path.exists(pat):
            open(pat, "w").write("\n".join(ids) + "\n")
        r = subprocess.run(["grep", "-rlF", "-f", pat, "results", "--include=*.jsonl", "--include=*.json", "--include=*.md", "--include=*.log"],
                           capture_output=True, text=True)
        files = sorted(f for f in r.stdout.splitlines() if not f.startswith(f"{OUT}/") and "iter_018/manifests" not in f)
        out[k] = dict(files_mentioning=files, n_files=len(files))
    return out


def check():
    hf, csv_by_path, src = checked_sources()
    info, sets, inter, rep = verify_patients(hf)
    pc = json.load(open(PC_D8_MANIFEST))
    pc_rows = pc["rows"]
    pc_ok = []
    for m in pc_rows:
        meta = m["image_meta"]
        if file_sha(meta["path"]) != meta["file_sha256"]:
            raise GateError(f"PadChest D8 image hash mismatch {meta['path']}")
        pc_ok.append(m["PatientID"])
    leg = legacy_exact_dup(info)
    exp = exposure_scan(sets)
    f_exposed = exp["F"]["n_files"]
    # F는 과거 출력에 노출되지 않아야 한다 (iter_018은 D16/E48만 요청). 노출이 있으면 F 확인 경로 비허용.
    f_ok = f_exposed == 0 and not leg["exact_file_or_pixel_matches"]
    res = dict(passed=True, f_independence_ok=bool(f_ok), source=src, patients=rep, d_e_f_intersections=inter,
               split_sizes={k: {c: len(v) for c, v in sets[k].items()} for k in sets}, legacy_exact_duplicate=leg, prior_exposure=exp,
               padchest_d8=dict(n_patients=len(pc_ok), n_distinct=len(set(pc_ok)), manifest=PC_D8_MANIFEST, manifest_sha256=file_sha(PC_D8_MANIFEST)),
               note=("HF validation 234행 고유 Path, MedAug 7 finding 대응, 169명 단일 frontal 선택·split 재현, patient/study/file/pixel 교집합 0. "
                     "임상 정답은 제공된 CheXpert validation annotation이며 재판독하지 않았다. 사전학습 노출은 미확인."))
    write_new(f"{OUT}/data/data_check.json", json.dumps(res, indent=1, sort_keys=True))
    print(json.dumps({k: res[k] for k in ("passed", "f_independence_ok", "split_sizes")}, indent=1))
    return res


def row_for(pid, info, set_name, qs=None):
    l = info[pid]
    code = S.code_of_category(l["category"])
    st = dict(qA=l["cardiomegaly"], qB=l["pleural_effusion"])
    q = {i: dict(finding=S.FINDING_PAIR[i], state=st[i]) for i in S.IDS}
    return dict(set=set_name, truth_code=code, PatientID=pid, ImageID=pid, StudyID=f"{pid}/{l['study']}", q=q,
                image_meta=dict(path=l["image"], file_sha256=l["file_sha256"], raw_png_sha256=None, u8_pixel_sha256=l["pixel_sha256"],
                                h=l["h"], w=l["w"]), source_path=l["path"])


def build():
    chk = json.load(open(f"{OUT}/data/data_check.json"))
    if chk.get("passed") is not True:
        raise GateError("data_check not passed")
    hf, _, _ = checked_sources()
    info, sets, _, _ = verify_patients(hf)
    ds_sha = file_sha(f"{OUT}/data/data_check.json")
    for name, key in (("D", "D16"), ("E", "E48"), ("F", "F")):
        rows = []
        for code in S.DRAFT_CODES:
            cat = S.CATEGORY_OF_CODE[code]
            for pid in sets[key][cat]:
                rows.append(row_for(pid, info, name))
        man = dict(set=name, source_set=key, spec_version=S.VERSION, rows=rows, data_check_sha256=ds_sha,
                   sets_json_sha256=file_sha(f"{MAN}/sets.json"), labels_json_sha256=file_sha(f"{MAN}/labels.json"),
                   infer_manifest_sha256=file_sha(f"{MAN}/infer_manifest.jsonl"))
        if name == "D":
            man["pc_oracle_rows"] = json.load(open(PC_D8_MANIFEST))["rows"]
            man["pc_oracle_manifest_sha256"] = file_sha(PC_D8_MANIFEST)
        if name == "F":
            man["role_note"] = ("F105는 iter_018에서 요청·출력에 쓰이지 않은 집단이다. iter_053은 이를 새 교정 질문의 확인용으로 용도 변경한다 "
                                "(원래 scope 진단의 F 실행이 아니다). E 결과의 사전 조건을 충족할 때만 실행한다.")
        write_new(f"{OUT}/data/manifest_{name}.json", json.dumps(man, indent=1))
        print(name, len(rows))


if __name__ == "__main__":
    {"check": check, "build": build}[sys.argv[1]]()
