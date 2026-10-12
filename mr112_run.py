"""iter_112 실행기: 한 프로세스가 모델을 두 GPU에 분산해 manifest 요청을 순서대로 처리한다.
--mode tech: region 요청은 공식 생성(greedy, max_new_tokens400)+scoring, full 요청은 scoring. --mode main: scoring만.
기록은 요청 단위 JSONL 한 줄(원자적 append+fsync). 같은 protocol digest의 완료 요청만 재사용한다. GT는 읽지 않는다."""
import argparse
import fcntl
import hashlib
import json
import os
import sys
import time

import torch

import mr112_model as MM
import mr112_spec as S

D = "results/iter_112"
CODE = ["mr112_spec.py", "mr112_model.py", "mr112_run.py"]


def fsha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def protocol_digest(man_path):
    d = {p: fsha(p) for p in CODE}
    d["manifest"] = fsha(man_path)
    d["weights_manifest"] = fsha(f"{D}/weights_manifest.json")
    return hashlib.sha256(json.dumps(d, sort_keys=True).encode()).hexdigest(), d


def peak_mib():
    return [round(torch.cuda.max_memory_allocated(i) / 2**20) for i in range(torch.cuda.device_count())]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", required=True, choices=["tech", "main"])
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--tag", default="")
    ap.add_argument("--checks", action="store_true")
    a = ap.parse_args()
    man_path = f"{D}/data/manifest.json"
    man = json.load(open(man_path))
    pd, files = protocol_digest(man_path)
    out_dir = f"{D}/scores"
    os.makedirs(out_dir, exist_ok=True)
    out = f"{out_dir}/{a.mode}{a.tag}_scores.jsonl"
    lock = open(out + ".lock", "w")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)  # 동일 출력 단일 소유
    done = set()
    if os.path.exists(out):
        for l in open(out):
            try:
                r = json.loads(l)
            except json.JSONDecodeError:
                continue  # torn tail
            if r["protocol_digest"] != pd:
                sys.exit("기존 출력의 protocol digest 불일치: 재사용 거부")
            done.add(r["request_id"])
    reqs = [q for q in man["requests"] if q["group"] == a.mode]
    if a.limit:
        reqs = reqs[:a.limit]
    todo = [q for q in reqs if q["request_id"] not in done]
    print(f"mode={a.mode} total={len(reqs)} done={len(done)} todo={len(todo)}", flush=True)
    if not todo:
        return
    rows = {r["id"]: r for r in man["rows"]}
    model, tok, load_s = MM.load()
    print(f"loaded {load_s:.0f}s peak_MiB={peak_mib()}", flush=True)
    if a.checks:
        import mr112_checks
        os.makedirs(f"{D}/tech", exist_ok=True)
        ok = mr112_checks.run_checks(model, tok, man, f"{D}/tech/checks{a.tag}.json")
        print("checks_ok", ok, "peak_MiB", peak_mib(), flush=True)
    cache = {}
    for q in todo:
        r = rows[q["id"]]
        # 영상 로딩 시 file/pixel hash 재검증 (manifest 연결)
        if q["id"] not in cache:
            if hashlib.sha256(open(r["image"], "rb").read()).hexdigest() != r["file_sha256"]:
                raise RuntimeError(f"영상 hash 불일치 {q['id']}")
            cache.clear()
            pv = MM.load_image(r["image"])
            cache[q["id"]] = (pv, MM.vit_features(model, pv))
        pv, vit = cache[q["id"]]
        t0 = time.time()
        rec = dict(request_id=q["request_id"], id=q["id"], group=q["group"], kind=q["kind"], det_index=q["det_index"], box=q["box"],
                   protocol_digest=pd, prompt_sha256=hashlib.sha256(q["prompt"].encode()).hexdigest(), target=q["target"],
                   file_sha256=r["file_sha256"], pixel_values_sha256=hashlib.sha256(pv.numpy().tobytes()).hexdigest())
        rec.update(MM.score(model, tok, q["prompt"], vit, q["target"]))
        rec["score_s"] = time.time() - t0
        if a.mode == "tech" and q["kind"] == "region":
            t1 = time.time()
            txt = MM.generate(model, tok, q["prompt"], pv)
            rec["generated"] = txt
            rec["gen_s"] = time.time() - t1
        rec["peak_mib"] = peak_mib()
        rec["wall_s"] = time.time() - t0
        with open(out, "a") as f:
            f.write(json.dumps(rec) + "\n")
            f.flush()
            os.fsync(f.fileno())
        print(q["request_id"], q["kind"], round(rec["mean_logprob"], 4), f"{rec['wall_s']:.1f}s", rec["peak_mib"], flush=True)


if __name__ == "__main__":
    main()
