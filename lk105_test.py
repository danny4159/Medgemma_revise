"""iter_105 CPU 검사 + completion 변조(mutation) 검사. 결과는 새 파일로만 저장한다.

사용: python lk105_test.py cpu OUT.json
      python lk105_test.py mutate GEN_DIR STAGE WORKERS OUT.json   (완료된 shard를 tests 임시 사본에 복사해 변조 후 verify_completion이 거부하는지 확인)
"""
import copy
import hashlib
import json
import shutil
import sys
from pathlib import Path

import lk105_run as R
import lk105_spec as S
import pg39_data as D
from report86_common import sha, sha_obj, save


def check(res, name, cond, detail=None):
    res.append({"name": name, "pass": bool(cond), "detail": detail})


def cpu(out):
    res = []
    reports, m, links = D.load_inputs()
    by_img = {r["ImageID"]: r for r in reports}
    seen_pat, seen_img = set(), set()
    for st in ("D4", "E32", "R64"):
        rows, raw = R.stage_rows(st)
        for r in rows:
            f = by_img[r["ImageID"]]["findings"]
            i1, i2 = r["finding_idx"]
            ok = (f[i1]["sentence_en"] == r["S1"] and f[i2]["sentence_en"] == r["S2"] and f[i1]["boxes"][0] == r["box1"]
                  and f[i2]["boxes"][0] == r["box2"] and len(f[i1]["boxes"]) == 1 and len(f[i2]["boxes"]) == 1
                  and links["img2split"][r["ImageID"]] == "train" and links["img2patient"][r["ImageID"]] == r["PatientID"]
                  and sha(r["image"]) == r["file_sha256"] and sha(raw[r["ImageID"]]["raw_path"]) == raw[r["ImageID"]]["sha256"])
            check(res, f"input_gt_link_{st}_{r['ImageID'][:8]}", ok)
            check(res, f"no_overlap_{st}_{r['ImageID'][:8]}", r["PatientID"] not in seen_pat and r["ImageID"] not in seen_img)
            seen_pat.add(r["PatientID"])
            seen_img.add(r["ImageID"])
            # 두 문장의 모든 annotation(boxes+extra) 사이 교차 없음
            from lk105_data import inter_area
            a = [r["box1"]] + r["extra1"]
            b = [r["box2"]] + r["extra2"]
            check(res, f"annot_no_intersection_{st}_{r['ImageID'][:8]}", all(inter_area(x, y) == 0 for x in a for y in b))
    for system in S.SYSTEMS:
        for st in ("D4", "E32", "R64"):
            rows, _ = R.stage_rows(st)
            reqs = R.requests(st, system)
            check(res, f"n_requests_{system}_{st}", len(reqs) == 14 * len(rows), len(reqs))
            byid = {q["id"]: q for q in reqs}
            for r in rows:
                iid = r["ImageID"]
                for mod in ("img", "txt"):
                    for o in (0, 1):
                        pn = byid[f"{iid}|{system}|{mod}-N-o{o}"]["prompt"]
                        pc = byid[f"{iid}|{system}|{mod}-C-o{o}"]["prompt"]
                        pw = byid[f"{iid}|{system}|{mod}-W-o{o}"]["prompt"]
                        g = S.gt_letter(o)
                        w = "B" if g == "A" else "A"
                        sug = S.SUGGEST
                        check(res, f"cw_text_{system}_{st}_{iid[:6]}_{mod}_o{o}",
                              pc == pn.replace("Which assignment", sug.format(x=g) + "\nWhich assignment") and
                              pw == pn.replace("Which assignment", sug.format(x=w) + "\nWhich assignment") and sug.split("{")[0] not in pn)
                # 순서 반전: R1/R2 좌표 문자열 교환
                p0 = byid[f"{iid}|{system}|img-N-o0"]["prompt"].splitlines()
                p1 = byid[f"{iid}|{system}|img-N-o1"]["prompt"].splitlines()
                i_r1 = next(i for i, x in enumerate(p0) if x.startswith("R1:"))
                check(res, f"order_flip_{system}_{st}_{iid[:6]}", p0[i_r1][3:] == p1[i_r1 + 1][3:] and p0[i_r1 + 1][3:] == p1[i_r1][3:])
                # 텍스트 조건은 같은 문장 (영상 유무만 다름): 요청 prompt 동일
                check(res, f"text_same_prompt_{system}_{st}_{iid[:6]}",
                      all(byid[f"{iid}|{system}|img-{c}-o{o}"]["prompt"] == byid[f"{iid}|{system}|txt-{c}-o{o}"]["prompt"] for c in "NCW" for o in (0, 1)))
            # 좌표 왕복
            for r in rows:
                for key in ("box1", "box2"):
                    t = S.region_text(system, r, r[key])
                    v = json.loads(t)
                    if system == "CURE":
                        back = S.cxcywh_to_xyxy(v)
                        err = max(abs(x - y) for x, y in zip(back, r[key]))
                        check(res, f"coord_roundtrip_CURE_{r['ImageID'][:6]}_{key}", err < 1e-3, err)
                    else:
                        resp = json.dumps([{"box_2d": v, "label": "x"}])
                        pr = S.parse_pg("M15", resp, True, r)
                        err = max(abs(x - y) for x, y in zip(pr["boxes"][0], r[key]))
                        check(res, f"coord_roundtrip_M15_{r['ImageID'][:6]}_{key}", pr["status"] == "valid_nonempty" and err < 2e-3, err)
    # PG matching 합성
    row = {"box1": [0.1, 0.1, 0.3, 0.3], "box2": [0.6, 0.6, 0.9, 0.9]}
    check(res, "pg_A", S.pg_connection(row, [row["box1"]], [row["box2"]])[0] == "A")
    check(res, "pg_B", S.pg_connection(row, [row["box2"]], [row["box1"]])[0] == "B")
    check(res, "pg_zero_abstain", S.pg_connection(row, [], [])[0] is None)
    check(res, "pg_tie_abstain", S.pg_connection(row, [row["box1"], row["box2"]], [row["box1"], row["box2"]])[0] is None)
    check(res, "iou_identity", abs(S.iou(row["box1"], row["box1"]) - 1) < 1e-12)
    # parser
    P = S.parse_choice
    check(res, "parse_A", P("A", True) == ("A", "valid"))
    check(res, "parse_B_dot", P("B.", True) == ("B", "valid"))
    check(res, "parse_truncated", P("A", False) == (None, "truncated"))
    check(res, "parse_sentence_strict_invalid", P("The correct answer is A.", True) == (None, "format_invalid"))
    check(res, "lenient_statement", S.parse_choice_lenient("The correct answer is B.\n\nTherefore, the answer is B.", True) == ("B", "valid_statement"))
    check(res, "lenient_ambiguous", S.parse_choice_lenient("The answer is A. Actually the answer is B.", True) == (None, "ambiguous"))
    check(res, "lenient_echo", S.parse_choice_lenient("B: S1 is in R2 and S2 is in R1.", True) == ("B", "valid_echo"))
    check(res, "lenient_echo_wrong_pair_invalid", S.parse_choice_lenient("B: S1 is in R1 and S2 is in R2.", True)[0] is None)
    check(res, "cure_pg_parse", S.parse_pg("CURE", "x: [0.5, 0.5, 0.2, 0.2]", True, {})["boxes"] == [[0.4, 0.4, 0.6, 0.6]] or
          all(abs(a - b) < 1e-9 for a, b in zip(S.parse_pg("CURE", "x: [0.5, 0.5, 0.2, 0.2]", True, {})["boxes"][0], [0.4, 0.4, 0.6, 0.6])))
    check(res, "cure_pg_invalid_range", S.parse_pg("CURE", "x: [1.5, 0.5, 0.2, 0.2]", True, {})["status"] == "coord_invalid")
    check(res, "cure_pg_nobox", S.parse_pg("CURE", "cannot", True, {})["status"] == "no_box")
    ok = all(r["pass"] for r in res)
    save(out, {"n": len(res), "n_pass": sum(r["pass"] for r in res), "all_pass": ok, "results": res,
               "code_sha256": {f: sha(R.ROOT / f) for f in ("lk105_test.py", "lk105_spec.py", "lk105_run.py", "lk105_data.py")}})
    print(len(res), sum(r["pass"] for r in res), "all_pass" if ok else "FAIL")
    return 0 if ok else 1


def mutate(gen_dir, stage, workers, out):
    """완료된 shard를 사본으로 복사해 변조하고 verify_completion이 모두 거부하는지 확인한다."""
    res = []
    import time
    work = R.R105 / f"tests/mut_{int(time.time())}"
    for system in S.SYSTEMS:
        sd = sha_obj(R.scientific_protocol(stage, system, workers))
        src = R.shard_dir(gen_dir, system, 0)
        base = work / f"{system}_orig"
        shutil.copytree(src, base, ignore=shutil.ignore_patterns("worker.lock"))
        # 정상 사본은 통과해야 한다
        try:
            R.verify_completion(base, stage, system, 0, workers, sd)
            check(res, f"{system}_clean_copy_accepted", True)
        except AssertionError as e:
            check(res, f"{system}_clean_copy_accepted", False, str(e))
        recs = [json.loads(l) for l in (base / "outputs.jsonl").read_text().splitlines() if l]

        def rewrite(d, lines, fix_completion=True):
            (d / "outputs.jsonl").write_text("".join(l if l.endswith("\n") else l + "\n" for l in lines))
            if fix_completion:  # completion의 파일 hash를 맞춰 '내용 검증' 자체가 거부하는지 확인
                c = json.loads((d / "completion.json").read_text())
                c["files"]["outputs.jsonl"] = sha(d / "outputs.jsonl")
                c["n_own_records"] = len([x for x in lines if x.strip()])
                (d / "completion.json").write_text(json.dumps(c))

        def case(name, mut, fix=True):
            d = work / f"{system}_{name}"
            shutil.copytree(base, d)
            lines = (d / "outputs.jsonl").read_text().splitlines()
            lines = mut([json.loads(l) for l in lines])
            rewrite(d, [json.dumps(x, ensure_ascii=False) for x in lines], fix)
            try:
                R.verify_completion(d, stage, system, 0, workers, sd)
                check(res, f"{system}_{name}_rejected", False, "accepted")
            except AssertionError as e:
                check(res, f"{system}_{name}_rejected", True, str(e)[:100])

        case("missing_record", lambda r: r[:-1])
        case("duplicate_record", lambda r: r + [r[0]])
        case("extra_foreign_id", lambda r: r + [dict(r[0], id=r[0]["id"] + "x")])
        def tamper_text(r):
            r[3]["text"] = "A" if r[3]["text"] != "A" else "B"
            return r
        case("tampered_text_digest_stale", tamper_text)
        def tamper_prompt(r):
            r[2]["prompt"] += " "
            r[2]["record_digest"] = None
            return r
        case("prompt_changed", tamper_prompt)
        def swap_modality(r):
            x = next(i for i in r if i["modality"] == "text")
            x["n_image_tokens"] = 5
            from report86_common import record_digest
            x["record_digest"] = record_digest(x)
            return r
        case("text_with_image_tokens", swap_modality)
        # completion 파일 hash 변조(내용 수정 후 completion 미갱신)
        d = work / f"{system}_completion_stale"
        shutil.copytree(base, d)
        (d / "outputs.jsonl").write_text((d / "outputs.jsonl").read_text().replace("A", "B", 1))
        try:
            R.verify_completion(d, stage, system, 0, workers, sd)
            check(res, f"{system}_completion_stale_rejected", False)
        except AssertionError as e:
            check(res, f"{system}_completion_stale_rejected", True, str(e)[:100])
        # protocol digest 변조
        try:
            R.verify_completion(base, stage, system, 0, workers, sd + "0")
            check(res, f"{system}_wrong_protocol_digest_rejected", False)
        except AssertionError as e:
            check(res, f"{system}_wrong_protocol_digest_rejected", True, str(e)[:100])
    ok = all(r["pass"] for r in res)
    save(out, {"n": len(res), "n_pass": sum(r["pass"] for r in res), "all_pass": ok, "results": res})
    print(len(res), sum(r["pass"] for r in res), "all_pass" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    if sys.argv[1] == "cpu":
        raise SystemExit(cpu(sys.argv[2]))
    raise SystemExit(mutate(sys.argv[2], sys.argv[3], int(sys.argv[4]), sys.argv[5]))
