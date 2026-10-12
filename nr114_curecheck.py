"""iter_114 CURE 개발 회귀: 새 경로(nr114_cure)의 T4 출력과 iter_107 M47 저장 출력의 입력 token·pixel hash·생성 token·parser 결과를 대조한다 (CPU).
새 결과 파일 results/iter_114/dev/cure_regress.json (기존 파일 덮어쓰기 금지)."""
import json
import sys
from pathlib import Path

import nr107_spec as S
import nr114_cure as C
from report86_common import read_jsonl_complete, sha_obj

OLD = C.ROOT / "results/iter_107/gen/M47/cure"


def main(run):
    out = C.ROOT / run
    sd = sha_obj(C.scientific_protocol("T4", 2))
    new = []
    for s in (0, 1):
        _, recs = C.verify_completion(C.shard_dir(out, s), "T4", s, 2, sd)
        new += recs
    old = {}
    for s in (0, 1):
        for r in read_jsonl_complete(OLD / f"shard{s}/outputs.jsonl"):
            old[r["id"]] = r
    rows = []
    for r in new:
        o = old[r["id"]]
        pn = S.parse_pg(r["text"], r["attempts"][-1]["ended_eos"])
        po = S.parse_pg(o["text"], o["attempts"][-1]["ended_eos"])
        rows.append({"id": r["id"], "input_ids_equal": r["input_ids"] == o["input_ids"], "pixel_sha_equal": r["pixel_sha256"] == o["pixel_sha256"],
                     "suffix_ids_equal": r["attempts"][-1]["suffix_ids"] == o["attempts"][-1]["suffix_ids"], "text_equal": r["text"] == o["text"],
                     "parse_equal": pn == po, "status": pn["status"], "n_image_tokens": r["n_image_tokens"], "n_pixel_values": r["n_pixel_values"],
                     "ended_eos": r["attempts"][-1]["ended_eos"], "n_attempts": len(r["attempts"])})
    res = {"run": run, "n": len(rows), "all_equal": all(x["input_ids_equal"] and x["pixel_sha_equal"] and x["suffix_ids_equal"] and x["parse_equal"] for x in rows),
           "rows": rows, "builder_vs_official_chat_template": "asserted inside nr114_cure.generate() for every request (processor.apply_chat_template tensors torch.equal)"}
    p = C.R114 / "dev/cure_regress.json"
    with p.open("x") as f:
        json.dump(res, f, indent=1)
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main(sys.argv[1])
