"""iter_059: 전체 비용 측정·회귀 경로의 공통 검사(허용 GPU 매핑, 메모리 admission, digest 잠금, 새 run 경로, 완료 검증, GT 검사).
순수 함수 중심이며 test_hdglio59.py가 같은 함수를 직접 검사한다.
"""
import hashlib
import json
import os
import subprocess

ROOT = os.path.abspath(".")
CODE_FILES = ["hdglio59_hd.py", "hdglio59_u8.py", "hdglio59_common.py", "hdglio59_timing.py", "hdglio59_report.py",
              "hdglio59_regress.py", "msd56_run.py", "msd56_data.py", "hdglio58_eval.py", "msd57_analysis.py"]
NS = 6


class TechError(RuntimeError):
    pass


def sha_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def atomic_json(path, obj, exclusive=False):
    if exclusive and os.path.exists(path):
        raise FileExistsError(path)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f, indent=1, default=str)
    os.replace(tmp, path)


def allowed_physical(env_value):
    """상속된 CUDA_VISIBLE_DEVICES(논리 index -> 물리 index/UUID 목록)를 반환. 비어 있으면 오류(제한 불명)."""
    if not env_value:
        raise TechError("CUDA_VISIBLE_DEVICES not inherited; allowed GPU set unknown")
    return [x.strip() for x in env_value.split(",") if x.strip()]


def pick_gpu(logical, allowed):
    """허용 집합 내부의 논리 index만 허용하고 물리 id를 반환한다."""
    if not (0 <= logical < len(allowed)):
        raise TechError(f"gpu logical {logical} outside allowed {allowed}")
    return allowed[logical]


def gpu_table():
    r = subprocess.run(["nvidia-smi", "--query-gpu=index,uuid,memory.used,memory.total", "--format=csv,noheader,nounits"],
                       capture_output=True, text=True, check=True)
    out = {}
    for ln in r.stdout.strip().splitlines():
        i, u, used, tot = [x.strip() for x in ln.split(",")]
        out[i] = {"uuid": u, "used_mib": int(used), "total_mib": int(tot)}
    return out


def admit(table, phys, peak_mib, margin_mib=2048):
    """실제 전체 점유 + 예상 peak + 2GiB 여유가 용량 이내여야 한다."""
    g = table.get(str(phys))
    if g is None:
        raise TechError(f"gpu {phys} not in nvidia-smi table")
    need = g["used_mib"] + peak_mib + margin_mib
    if need > g["total_mib"]:
        raise TechError(f"insufficient memory gpu {phys}: used {g['used_mib']} + peak {peak_mib} + margin {margin_mib} > {g['total_mib']}")
    return {"gpu": phys, "uuid": g["uuid"], "used_mib": g["used_mib"], "peak_mib": peak_mib, "margin_mib": margin_mib, "total_mib": g["total_mib"]}


def new_run_dir(path):
    """기존 경로(부분 출력 포함)는 덮어쓰지 않는다. 부모만 만든다."""
    if os.path.exists(path):
        raise FileExistsError(path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    return path


def current_digests(extra_files=()):
    d = {f: sha_file(f) for f in CODE_FILES if os.path.exists(f)}
    for f in extra_files:
        d[f] = sha_file(f)
    return d


def check_locked(lock, current):
    """잠금 파일의 digest와 현재 digest가 모두 같아야 한다(source/checkpoint/config 불일치 거부)."""
    bad = {k: (v, current.get(k)) for k, v in lock.items() if current.get(k) != v}
    if bad:
        raise TechError(f"digest mismatch: {sorted(bad)}")


def check_gt_rows(gt_rows, cases_chosen, split):
    """GT 중복 key, case/split 대응, 구간 수를 검사한다."""
    seen = set()
    for g in gt_rows:
        k = (g["case"], g["slab"])
        if k in seen:
            raise TechError(f"duplicate GT key {k}")
        seen.add(k)
    split_cases = {c["case"] for c in cases_chosen if c["split"] == split}
    gt_cases = {g["case"] for g in gt_rows if g["split"] == split}
    if gt_cases != split_cases:
        raise TechError(f"GT case set != split {split} case set: {gt_cases ^ split_cases}")
    other = {g["case"] for g in gt_rows if g["split"] != split} & split_cases
    if other:
        raise TechError(f"case(s) appear under two splits: {other}")
    for c in split_cases:
        if sorted(g["slab"] for g in gt_rows if g["case"] == c) != list(range(NS)):
            raise TechError(f"{c}: GT slabs != 0..{NS - 1}")


def verify_run(kind, run_dir, cases):
    """완료 검증: summary.json 존재, 정확한 case 집합, 각 6개 답변. 부분 출력(summary 없음)은 불완전."""
    sp = f"{run_dir}/summary.json"
    if not os.path.exists(sp):
        raise TechError(f"{run_dir}: no summary.json (incomplete)")
    s = json.load(open(sp))
    if s["cases"] != list(cases):
        raise TechError(f"{run_dir}: case list mismatch")
    pref = "hd_" if kind == "HD" else "u8_"
    flags = {"invalid_answers": 0, "non_eos": 0}
    for c in cases:
        p = f"{run_dir}/{pref}{c}.json"
        if not os.path.exists(p):
            raise TechError(f"{p} missing")
        a = json.load(open(p))["answers"]
        if [x["slab"] for x in a] != list(range(NS)):
            raise TechError(f"{p}: slab list")
        for x in a:
            if x["answer"] not in ("PRESENT", "ABSENT"):
                flags["invalid_answers"] += 1
            if kind == "U8" and not x["ended_eos"]:
                flags["non_eos"] += 1
    extra = [f for f in os.listdir(run_dir) if f.startswith(pref) and f.endswith(".json") and f[len(pref):-5] not in cases]
    if extra:
        raise TechError(f"unexpected outputs {extra}")
    return s, flags
