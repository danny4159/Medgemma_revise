"""iter_107 기술 확인(CPU 판정): T4 출력의 연결·재개 동등성·변조 거부·admission 실패 기록. 결과는 새 JSON으로만 저장한다."""
import copy
import json
import shutil
import sys
from pathlib import Path

import nr107_run as RUN
import nr107_spec as S
from report86_common import ROOT, sha, sha_obj, save, read_jsonl_complete, record_digest

G = ROOT / "results/iter_107/gen"
T = ROOT / "results/iter_107/tests"
R = []


def chk(name, cond, detail=None):
    R.append({"name": name, "pass": bool(cond), "detail": detail})


def recs_of(out, nshards):
    d = {}
    for k in range(nshards):
        for r in read_jsonl_complete(Path(out) / "cure" / f"shard{k}" / "outputs.jsonl"):
            assert r["id"] not in d
            d[r["id"]] = r
    return d


def expect_fail(fn):
    try:
        fn()
    except AssertionError as e:
        return str(e)[:80]
    return None


def main():
    sd2 = sha_obj(RUN.scientific_protocol("T4", 2))
    sd1 = sha_obj(RUN.scientific_protocol("T4", 1))
    w2 = recs_of(G / "T4_w2", 2)
    rs = recs_of(G / "T4_resume", 1)
    want = {q["id"] for q in RUN.requests("T4")}
    chk("T4_w2 exact request set (4)", set(w2) == want and len(w2) == 4)
    chk("T4_resume exact request set (4)", set(rs) == want)
    for k in (0, 1):
        RUN.verify_completion(G / "T4_w2" / "cure" / f"shard{k}", "T4", k, 2, sd2)
    RUN.verify_completion(G / "T4_resume" / "cure" / "shard0", "T4", 0, 1, sd1)
    chk("completion verify (w2 x2, resume x1)", True)
    ev = [json.loads(l) for l in (G / "T4_resume/cure/shard0/executions.jsonl").read_text().splitlines()]
    starts = [e for e in ev if e["event"] == "start"]
    chk("resume: 2 executions, 2 then 2 todo", len(starts) == 2 and starts[0]["n_todo"] == 2 and starts[1]["n_done_before"] == 2, [(e["n_todo"], e["n_done_before"]) for e in starts])
    same = all(w2[i]["attempts"][-1]["suffix_ids"] == rs[i]["attempts"][-1]["suffix_ids"] and w2[i]["input_ids"] == rs[i]["input_ids"]
               and w2[i]["pixel_sha256"] == rs[i]["pixel_sha256"] for i in want)
    chk("token+input+pixel identical: 2 workers vs interrupted-resumed 1 worker", same)
    chk("all EOS, no cap retry", all(len(r["attempts"]) == 1 and r["attempts"][0]["ended_eos"] for r in w2.values()))
    items = {it["item_key"]: it for it in RUN.all_items()}
    for r in w2.values():
        it = items[r["item_key"]]
        assert r["prompt"] == "Ground the phrase: " + it["sentence"]
        assert "gt" not in r["prompt"].lower()
    chk("prompt == official 'Ground the phrase: {sentence}', no GT in prompt", True)
    chk("raw image hash linked", all(r["image_sha256"] == RUN.raw_map()[r["ImageID"]]["sha256"] for r in w2.values()))
    parsed = {i: S.parse_pg(r["text"], r["attempts"][-1]["ended_eos"]) for i, r in w2.items()}
    chk("T4 parse statuses", all(p["status"] == "valid_nonempty" for p in parsed.values()), {i[-14:]: (p["status"], len(p["boxes"])) for i, p in parsed.items()})
    peak = max(a["peak_mem_reserved_gb"] for r in w2.values() for a in r["attempts"])
    chk("peak reserved GiB", True, peak)
    ex = [json.loads(l) for k in (0, 1) for l in (G / "T4_w2/cure" / f"shard{k}" / "executions.jsonl").read_text().splitlines()]
    chk("loading_s", True, [round(e["loading_s"], 1) for e in ex if e["event"] == "start"])

    # 변조 거부 (사본 대상)
    base = T / "mut_v2"
    for name in ("drop_row", "dup_row", "text_edit", "prompt_edit_rehashed", "completion_hash", "control"):
        dst = base / name
        shutil.copytree(G / "T4_resume/cure/shard0", dst)
        rows = read_jsonl_complete(dst / "outputs.jsonl")
        if name == "drop_row":
            rows = rows[:-1]
        elif name == "dup_row":
            rows = rows + [rows[0]]
        elif name == "text_edit":
            rows[0]["text"] += " x"
        elif name == "prompt_edit_rehashed":
            rows[0]["prompt"] += " x"
            rows[0]["record_digest"] = record_digest(rows[0])
        if name != "control":
            with (dst / "outputs.jsonl").open("w") as f:
                for r in rows:
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")
        c = json.loads((dst / "completion.json").read_text())
        if name == "completion_hash":
            c["files"]["outputs.jsonl"] = "0" * 64
        else:  # completion 을 재봉인해 변조가 더 깊은 검증 분기(요청 집합·record digest·prompt 대조)에서 걸리는지 본다
            c["files"]["outputs.jsonl"] = sha(dst / "outputs.jsonl")
        (dst / "completion.json").write_text(json.dumps(c))
        res = expect_fail(lambda: RUN.verify_completion(dst, "T4", 0, 1, sd1))
        if name == "control":
            chk("mutation control accepted", res is None)
        else:
            chk("mutation rejected: " + name, res is not None, res)
    # protocol 변경 거부: 다른 nshards digest
    chk("wrong protocol digest rejected", expect_fail(lambda: RUN.verify_completion(G / "T4_resume/cure/shard0", "T4", 0, 1, sd2)) is not None)
    # admission 실패 기록
    la = json.loads(next((G / "T4_admission_refuse").glob("launch_*.json")).read_text())
    chk("admission refusal recorded (status failed, memory admission refused, children terminated, no outputs)",
        la["status"] == "failed" and "memory admission refused" in la["error"] and len(la["admission"]) == 2,
        {"error": la["error"][:140], "wall_s": la["wall_s"]})
    out = {"n": len(R), "n_pass": sum(r["pass"] for r in R), "all_pass": all(r["pass"] for r in R), "checks": R}
    save(T / "tech_T4_v2.json", out)
    print(out["n"], out["n_pass"], [r["name"] for r in R if not r["pass"]])
    return 0 if out["all_pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
