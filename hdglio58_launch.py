"""iter_058: HD-GLIO shard 실행기. python hdglio58_launch.py SPLIT OUTNAME GPUS(e.g. 0,1) WORKERS_PER_GPU [CASE_LIMIT]
case를 round-robin으로 worker에 배정하고 worker별 pred/timing 폴더에 쓴다(출력 충돌 없음). 허용 GPU는 상속된 CUDA_VISIBLE_DEVICES의 논리 index.
"""
import json
import os
import subprocess
import sys
import time

ROOT = os.path.abspath(".")
PY = f"{ROOT}/results/environments/hdglio58/bin/python"
PARAMS = f"{ROOT}/results/iter_058/external/weights/params"


def sha_file(p):
    import hashlib
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def write_manifest(base, split):
    """run 디렉터리의 pred와 입력 4채널 hash를 case별로 연결해 기록한다(eval이 검증). 이미 있으면 덮어쓰지 않는다."""
    import glob
    mp = f"{base}/pred_manifest.json"
    if os.path.exists(mp):
        raise FileExistsError(mp)
    man = {}
    for f in sorted(glob.glob(f"{base}/*/pred/BRATS_*.nii.gz")):
        cid = os.path.basename(f)[:-len(".nii.gz")]
        assert cid not in man, f"duplicate {cid}"
        man[cid] = {"pred_sha256": sha_file(f),
                    "input_sha256": {s: sha_file(f"{ROOT}/results/iter_058/hd/input_{split}/{cid}_{s}.nii.gz") for s in ("0000", "0001", "0002", "0003")}}
    json.dump(man, open(mp + ".tmp", "w"), indent=1)
    os.replace(mp + ".tmp", mp)


def main():
    if sys.argv[1] == "manifest":  # python hdglio58_launch.py manifest SPLIT NAME  (사후 생성; 기존 run 용)
        write_manifest(f"{ROOT}/results/iter_058/hd/run_{sys.argv[3]}", sys.argv[2])
        return
    split, name, gpus, wpg = sys.argv[1], sys.argv[2], sys.argv[3].split(","), int(sys.argv[4])
    limit = int(sys.argv[5]) if len(sys.argv) > 5 else None
    inherited = os.environ.get("CUDA_VISIBLE_DEVICES")
    allowed = inherited.split(",") if inherited else None
    if allowed is not None:
        assert all(g in allowed for g in gpus), (gpus, allowed)
    cases = json.load(open(f"{ROOT}/results/iter_058/hd/{split}_cases.json"))
    if limit:
        cases = cases[:limit]
    workers = [(g, k) for g in gpus for k in range(wpg)]
    shards = {w: [c for i, c in enumerate(cases) if i % len(workers) == j] for j, w in enumerate(workers)}
    base = f"{ROOT}/results/iter_058/hd/run_{name}"
    os.makedirs(base, exist_ok=True)
    procs = []
    t0 = time.time()
    for (g, k), cs in shards.items():
        if not cs:
            continue
        tag = f"g{g}w{k}"
        os.makedirs(f"{base}/{tag}", exist_ok=True)
        cj = f"{base}/{tag}/cases.json"
        json.dump(cs, open(cj, "w"))
        env = dict(os.environ, HD_GLIO_PARAMS=PARAMS, CUDA_VISIBLE_DEVICES=g, HDG_PROCS=os.environ.get("HDG_PROCS", "2"))
        log = open(f"{base}/{tag}/stdout.log", "w")
        p = subprocess.Popen([PY, f"{ROOT}/hdglio58_pred.py", f"{ROOT}/results/iter_058/hd/input_{split}", f"{base}/{tag}/pred",
                              cj, f"{base}/{tag}/timing.json"], stdout=log, stderr=subprocess.STDOUT, env=env)
        procs.append((tag, p))
    rcs = {tag: p.wait() for tag, p in procs}
    wall = time.time() - t0
    json.dump({"split": split, "gpus": gpus, "workers_per_gpu": wpg, "n_cases": len(cases), "rc": rcs, "wall_s": wall,
               "shards": {f"g{g}w{k}": v for (g, k), v in shards.items()}}, open(f"{base}/launch.json", "w"), indent=1)
    print("rc", rcs, "wall", wall)
    if all(r == 0 for r in rcs.values()):
        write_manifest(base, split)
    sys.exit(0 if all(r == 0 for r in rcs.values()) else 1)


if __name__ == "__main__":
    main()
