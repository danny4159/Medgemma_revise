"""iter_106: (1) D4 I1/I2를 iter_105 D4_w1f 저장 PG와 token 대조, (2) E32 직전 protocol 잠금 기록. 새 파일만 만든다."""
import time

import lk106_run as R
from report86_common import read_jsonl_complete, sha, sha_obj, save, ROOT


def main():
    old = {r["id"]: r for r in read_jsonl_complete("results/iter_105/gen/D4_w1f/cure/shard0/outputs.jsonl") if r["kind"] == "pg"}
    new = {}
    for k in (0, 1):
        for r in read_jsonl_complete(f"results/iter_106/gen/D4_w2/cure/shard{k}/outputs.jsonl"):
            new[r["id"]] = r
    cmp = []
    for i, r in old.items():
        n = new[i.replace("|pg-S1", "|I1").replace("|pg-S2", "|I2")]
        cmp.append({"id": i, "tokens_equal": r["attempts"][-1]["suffix_ids"] == n["attempts"][-1]["suffix_ids"],
                    "input_ids_equal": r["input_ids"] == n["input_ids"], "pixel_equal": r["pixel_sha256"] == n["pixel_sha256"]})
    ok = all(c["tokens_equal"] and c["input_ids_equal"] and c["pixel_equal"] for c in cmp)
    print(ok, len(cmp))
    save(R.R106 / "tests/reproduce_iter105_D4_independent.json", {"n": len(cmp), "all_equal": ok, "checks": cmp})
    lock = {"time": time.time(), "iso": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "purpose": "E32 생성 직전 잠금(D4 결과를 본 뒤, E32 출력 전). prompt·parser·문턱·표본 변경 없음",
            "d4_gate": "J 8요청 중 malformed(coord_invalid/truncated)=0, 최종 비EOS=0 -> E32 진입(plan 3절). no_box 다수는 형식 관찰이며 gate 아님",
            "e32_requests_sha256": sha_obj(R.requests("E32", "CURE")),
            "sources": {f: sha(ROOT / f) for f in R.EXEC_SOURCES + ["lk106_eval.py", "lk106_verify.py", "lk106_test.py", "lk106_runtests.py", "lk106_prov.py",
                                                                    "lk106_tech.py", "lk106_lock.py"]},
            "inputs_E32": sha(R.DATA / "inputs_E32.json"), "weights_lock": sha(R.LOCKFILE),
            "worker_config": "CURE 2 workers (1/GPU); 2 workers/GPU는 메모리 admission 거부(D4_w4: free 11988/8 MiB vs need 12048)"}
    save(R.R106 / "protocol/lock_before_E32.json", lock)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
