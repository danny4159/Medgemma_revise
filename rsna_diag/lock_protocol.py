"""독립 평가 300명 실행 전에 입력·prompt·parser·평가기·baseline·분할 digest를 잠근다 (iter_009).

results/iter_009/locked_protocol.json 을 쓰고, 이미 존재하면 현재 digest와 대조해 불일치 시 실패한다 (덮어쓰지 않음).
사용: python -m rsna_diag.lock_protocol [--check]
"""
import hashlib
import json
import os
import sys

from . import prompts as P

OUT = "results/iter_009/locked_protocol.json"
FILES = ["rsna_diag/generate.py", "rsna_diag/parse.py", "rsna_diag/metrics.py", "rsna_diag/evaluate.py", "rsna_diag/geometry.py",
         "rsna_diag/prompts.py", "rsna_diag/rsna_data.py", "rsna_diag/dicom_min.py", "rsna_diag/run_shards.py",
         "results/iter_009/manifests/infer_manifest.jsonl", "results/iter_009/manifests/gt_manifest.json",
         "results/iter_009/manifests/dev80_ids.json", "results/iter_009/manifests/eval300_ids.json",
         "results/iter_009/manifests/exclusion_previous_nih_patients.json",
         "results/iter_009/source/official/cxr_anatomy_localization_with_hugging_face.ipynb"]


def sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def current():
    d = {"files": {f: sha(f) for f in FILES}, "prompts": {k: P.digest(v) for k, v in P.all_prompts().items()}}
    dev_env = json.load(open("results/iter_009/dev/run/gen_shard0.jsonl.env.json"))
    d["generation_config_digest"] = dev_env["config_digest"]
    d["generation_env"] = dev_env["env"]
    return d


def main():
    cur = current()
    if os.path.exists(OUT):
        old = json.load(open(OUT))
        diff = {k: (old["locked"]["files"].get(k), v) for k, v in cur["files"].items() if old["locked"]["files"].get(k) != v}
        if diff or old["locked"]["prompts"] != cur["prompts"] or old["locked"]["generation_config_digest"] != cur["generation_config_digest"]:
            print("LOCK MISMATCH", json.dumps(diff, indent=1))
            sys.exit(1)
        print("lock verified")
        return
    if "--check" in sys.argv:
        print("no lock yet")
        return
    json.dump({"locked": cur, "note": "development 완료 후, 독립 평가 300명 생성 전에 잠금. 이후 변경은 새 결과 경로·별도 계획이 필요하다."},
              open(OUT, "w"), indent=1, default=str)
    print("locked", OUT)


if __name__ == "__main__":
    main()
