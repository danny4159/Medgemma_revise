"""iter_054 반입 파일 검사: reuse_manifest blob 일치, import 가능, mc54_* 코드가 승인된 저수준 함수만 호출하는지 AST로 확인.
결과: tests/reuse_check.json"""
import ast
import glob
import json
import subprocess
import sys

MAN = "/SSD1_1TB/home/milab/daniel/08_medgemma/agent/runs/iter_054/reuse_manifest.json"
ALLOWED = {"G": {"load_model", "build_inputs", "build_inputs_text", "generate", "env_info", "static_env", "CFG_KEYS", "MODEL_ID",
                 "MODEL_REVISION", "HF_HOME"},
           "P43": {"sha_bytes", "file_sha", "canon", "record_digest", "read_records", "repair_tail", "try_flock", "gpu_free_mib",
                   "allowed_gpus", "_union_len", "RunError"}}
FORBIDDEN_NOTE = ["G.load_image (square padding)", "G.load_adapter", "G.main/run_worker/run_request*", "pg43_run.worker_main/launch_main/verify_completion"]


def main():
    man = json.load(open(MAN))
    files = man["files"]
    res = {"manifest_state": man.get("state"), "blobs": {}}
    for f, m in files.items():
        h = subprocess.run(["git", "hash-object", "--", f], capture_output=True, text=True, check=True).stdout.strip()
        res["blobs"][f] = {"manifest_blob": m["blob"], "worktree_blob": h, "match": h == m["blob"]}
    uses = {"G": set(), "P43": set()}
    for fn in sorted(glob.glob("mc54_*.py")):
        tree = ast.parse(open(fn).read())
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id in uses:
                uses[node.value.id].add(node.attr)
    res["used_attributes"] = {k: sorted(v) for k, v in uses.items()}
    res["disallowed_used"] = {k: sorted(v - ALLOWED[k]) for k, v in uses.items()}
    res["forbidden_paths_not_called"] = FORBIDDEN_NOTE
    try:
        import pg43_run  # noqa: F401
        from rsna_diag import generate, geometry, prompts, queue_lock  # noqa: F401
        res["import_ok"] = True
    except Exception as e:  # noqa: BLE001
        res["import_ok"] = False
        res["import_error"] = str(e)
    res["all_pass"] = (all(v["match"] for v in res["blobs"].values()) and res["import_ok"]
                       and not any(res["disallowed_used"].values()))
    json.dump(res, open(sys.argv[1], "x"), indent=1)
    print(json.dumps({k: res[k] for k in ("all_pass", "import_ok", "disallowed_used", "used_attributes")}, indent=1))


if __name__ == "__main__":
    main()
