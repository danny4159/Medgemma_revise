"""iter_113 실행기(CPU 전용). 단계: link -> lock -> analyze -> seal.
link: 저장 자산 연결 ledger 작성(순위·GT 오류 미계산). lock: 코드·입력·규칙 hash 를 시각과 함께 기록.
analyze: lock 검증 후 고정 비교 1회. seal: independent verify PASS 와 산출물 hash 연결.
기존 산출물이 있으면 덮어쓰지 않는다(입력·규칙 digest 가 같을 때만 재사용)."""
import json
import sys
import time
from pathlib import Path

import nr113_core as C

OUT = Path("results/iter_113")
R = Path("results")
PATHS = {
    "items": R / "iter_107/data/items.json", "cohort": R / "iter_107/data/cohort_summary.json",
    "raw_manifest": R / "iter_107/data/raw_manifest.json",
    "cure_completion": R / "iter_107/gen/M47/completion.json", "cure_dir": R / "iter_107/gen/M47/cure",
    "mg_completion": R / "iter_046/mg/V96_A_w2b4/completion.json", "mg_dir": R / "iter_046/mg/V96_A_w2b4",
    "selection": R / "iter_046/decisions/final_selection.json", "manifest_private": R / "iter_039/data/manifest_private.jsonl",
}
CODE = ["nr107_geom.py", "nr107_spec.py", "nr113_core.py", "nr113_run.py", "nr113_verify.py", "nr113_tests.py"]


def wjson(p, obj):
    p = Path(p)
    if p.exists():
        raise SystemExit(f"refuse to overwrite {p}")
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=1, ensure_ascii=False))
    tmp.rename(p)


def input_hashes():
    h = {}
    for k, p in PATHS.items():
        if k == "cure_dir":
            for sh in (0, 1):
                for fn in ("outputs.jsonl", "completion.json", "scientific_protocol.json"):
                    h[f"cure/shard{sh}/{fn}"] = C.sha256_file(p / f"shard{sh}" / fn)
        elif k == "mg_dir":
            for fn in ("raw_worker0.jsonl", "raw_worker1.jsonl", "completion.json", "launch_protocol.json"):
                h[f"mg/{fn}"] = C.sha256_file(p / fn)
        else:
            h[k] = C.sha256_file(p)
    return h


def cmd_link():
    ledger, excluded, glob = C.link(PATHS)
    wjson(OUT / "ledger.json", {"ledger": ledger, "link_excluded": excluded, "summary": glob})
    print(json.dumps(glob), "excluded:", excluded)


def cmd_lock():
    tests = OUT / "tests/fixtures.json"
    if not tests.exists() or not json.load(open(tests)).get("all_pass"):
        raise SystemExit("fixtures must pass before lock")
    proto = {"locked_at_unix": time.time(), "locked_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
             "tag": C.TAG, "thr_key": C.THR_KEY, "err_iou": C.ERR_IOU, "seed": C.SEED, "boot_n": C.BOOT_N,
             "review_frac": "ceil(N/4)", "rules": C.__doc__, "code_sha256": {f: C.sha256_file(f) for f in CODE if Path(f).exists()},
             "input_sha256": input_hashes(), "ledger_sha256": C.sha256_file(OUT / "ledger.json"), "fixtures_sha256": C.sha256_file(tests),
             "note": "analysis rules locked after ledger linking (no ranking/GT-error computed before lock); data are repeated development material, not an unseen test."}
    wjson(OUT / "protocol.json", proto)
    print("locked", proto["locked_at_utc"])


def verify_lock():
    p = json.load(open(OUT / "protocol.json"))
    for f, h in p["code_sha256"].items():
        if C.sha256_file(f) != h:
            raise SystemExit(f"code changed after lock: {f}")
    if p["input_sha256"] != input_hashes() or C.sha256_file(OUT / "ledger.json") != p["ledger_sha256"]:
        raise SystemExit("inputs changed after lock")
    return p


def cmd_analyze():
    p = verify_lock()
    led = json.load(open(OUT / "ledger.json"))
    t0 = time.time()
    res, ent, boot = C.analyze(led["ledger"])
    res["protocol_locked_at_utc"] = p["locked_at_utc"]
    res["analysis_wall_s"] = time.time() - t0
    res["link_excluded"] = led["link_excluded"]
    res["gpu_used"] = 0
    wjson(OUT / "report.json", res)
    wjson(OUT / "per_item.json", [{k: v for k, v in e.items() if k != "tk"} | {"tie_hash": e["tk"][0], "selected_D": e["item_key"] in res["selected_D"], "selected_B": e["item_key"] in res["selected_B"]} for e in ent])
    wjson(OUT / "bootstrap_diffs.json", boot)
    print(json.dumps({k: res[k] for k in ("N", "K", "capture_D", "capture_B", "diff", "n_errors_official")}), res["decision_inputs"], "wall", res["analysis_wall_s"])


def cmd_seal():
    v = json.load(open(OUT / "verify.json"))
    if not v.get("all_pass"):
        raise SystemExit("verification not PASS")
    files = {f: C.sha256_file(OUT / f) for f in ("protocol.json", "ledger.json", "report.json", "per_item.json", "bootstrap_diffs.json", "verify.json", "tests/fixtures.json")}
    wjson(OUT / "completion.json", {"status": "complete", "verify_all_pass": True, "files": files, "sealed_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})


if __name__ == "__main__":
    {"link": cmd_link, "lock": cmd_lock, "analyze": cmd_analyze, "seal": cmd_seal}[sys.argv[1]]()
