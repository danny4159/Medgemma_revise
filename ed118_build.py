"""iter_118 요청·ledger·weights·평가 잠금 (결과는 results/iter_118 아래에만, 기존 파일 덮어쓰기 거부).

 ledger   : ledger_nogt(PNG 정보) + detector raw preds → data/ledger_det.json (정답 없음, label==1만, 원 score 보존)
 requests : TECH(6×3=18), MAIN(192×3=576), RESUME6(TECH 처음 6행). 요청에는 불투명 slot(s0..s2)만 있고 C/W 정오·category는 없다.
            정오 매핑은 private/cond_map.json (부모/평가 전용).
 weights  : 현재 가중치 snapshot sha256을 iter_116 weights_check와 대조한다.
 lock     : 평가 코드·fixture·정답/매핑 digest를 잠금 시각과 함께 private/eval_lock.json에 기록한다 (생성 전).
 protocol : 생성 전용 protocol — 정답/평가 파일을 잠금 목록에 넣지 않는다 (worker가 읽지 않는다).
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

import ed118_gen as RUN
import ed118_spec as S
from rsna_diag import generate as G

OUT = "results/iter_118"
DATA = f"{OUT}/data"
PRIV = f"{OUT}/private"
REQ = f"{OUT}/requests"
PROTO = f"{OUT}/protocol"
SNAP = Path("../hf_cache/hub/models--google--medgemma-1.5-4b-it/snapshots") / G.MODEL_REVISION
WCHECK116 = "results/iter_116/lock/weights_check.json"
GEN_LOCK_CODE = ["ed118_gen.py", "ed118_guard.py", "ed118_spec.py", "ed116_spec.py", "ev108_spec.py", "ev109_extract.py", "ed118_build.py",
                 "rsna_diag/__init__.py", "rsna_diag/generate.py", "rsna_diag/geometry.py", "rsna_diag/prompts.py", "rsna_diag/qa_spec.py"]
EVAL_CODE = ["ed118_spec.py", "ed118_eval.py", "ed118_verify.py", "ed118_tests.py", "ed118_build.py", "ed118_data.py", "ed118_det.py",
             "ed118_guard.py", "ed118_run.py", "ed116_spec.py", "ev108_spec.py", "ev109_extract.py", "rsna_diag/metrics.py", "rsna_diag/geometry.py",
             "rsna_diag/qa_spec.py", "ed118_gen.py"]


def fsha(p):
    return RUN.file_sha(p)


def wr(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "x") as f:
        json.dump(obj, f, indent=1, sort_keys=True)


def cmd_ledger():
    led = json.load(open(f"{DATA}/ledger_nogt.json"))["rows"]
    raw = json.load(open(f"{OUT}/det/raw_preds.json"))
    assert raw["ledger_sha256"] == fsha(f"{DATA}/ledger_nogt.json") and raw["checkpoint_sha256"] == "576b8d789ef5f9e1924d7ad6e56954d51589dc437eaa12215874ce77cd3cc76c"
    rows = []
    for r in led:
        p = raw["preds"][r["id"]]
        keep = [i for i, l in enumerate(p["labels"]) if l == 1]
        h, w = r["size_hw"]
        assert p["img_hw"] == [h, w]
        rows.append(dict(r, det=dict(boxes_xyxy_px=[p["boxes_xyxy_px"][i] for i in keep], scores=[p["scores"][i] for i in keep])))
    wr(f"{DATA}/ledger_det.json", dict(rows=rows, raw_preds_sha256=fsha(f"{OUT}/det/raw_preds.json"), threshold=S.THR))
    print("ledger_det", len(rows))


def make_rows(rows, labels, stage, cond_map):
    out = []
    for rank, r in enumerate(rows):
        pid = r["id"]
        gt = labels[pid]["gt_answer"]
        _, _, pxs = G.load_image(r["image"])
        if fsha(r["image"]) != r["file_sha256"] or pxs is None:
            raise RuntimeError(f"image hash changed {pid}")
        order = S.rotation(pid)
        cond_map[pid] = {f"s{k}": c for k, c in enumerate(order)}
        for k, c in enumerate(order):
            prompt = S.build_prompt(S.cond_draft(c, gt), r)
            psha = S.sha(prompt)
            row = dict(stage=stage, cond=f"s{k}", patient=pid, targets=["O"], kind="draft_probe", donor_patient=None, modality="image",
                       image=r["image"], image_file_sha256=r["file_sha256"], input_pixel_sha256=pxs, prompt=prompt, prompt_sha256=psha,
                       caps=S.CAPS, order_key=f"{stage}|{rank:04d}|{k}")
            row["request_id"] = S.request_id(pid, f"s{k}", psha, pxs, G.MODEL_REVISION)
            out.append(row)
    return out


def write_jsonl(path, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "x") as f:
        for r in rows:
            f.write(json.dumps(r, sort_keys=True) + "\n")


def cmd_requests():
    led = json.load(open(f"{DATA}/ledger_det.json"))["rows"]
    labels = json.load(open(f"{PRIV}/labels.json"))
    cond_map = {}
    tech = make_rows([r for r in led if r["stage"] == "TECH"], labels, "TECH", cond_map)
    main = make_rows([r for r in led if r["stage"] == "MAIN"], labels, "MAIN", cond_map)
    resume6 = sorted(tech, key=lambda r: r["order_key"])[:6]
    for name, rr in (("TECH", tech), ("MAIN", main), ("RESUME6", resume6)):
        write_jsonl(f"{REQ}/{name}.jsonl", rr)
        assert len({r["request_id"] for r in rr}) == len(rr)
        print(name, len(rr), fsha(f"{REQ}/{name}.jsonl"))
    wr(f"{PRIV}/cond_map.json", cond_map)
    txt = open(f"{REQ}/MAIN.jsonl").read() + open(f"{REQ}/TECH.jsonl").read()
    for bad in ("category", "gt_answer", "opacity\"", "correct_draft", "wrong_draft", "labels"):
        assert bad not in txt.replace("Use the information", "").replace("pulmonary opacity", ""), bad
    # 환자별 세 요청: 영상·packet·공통 지시 동일, draft 줄만 다름
    for rows in (tech, main):
        by = {}
        for r in rows:
            by.setdefault(r["patient"], []).append(r)
        for pid, rs in by.items():
            assert len(rs) == 3 and len({r["image"] for r in rs}) == 1 and len({r["input_pixel_sha256"] for r in rs}) == 1, pid
            stripped = {r["prompt"].replace("\n\n" + S.draft_line("yes"), "").replace("\n\n" + S.draft_line("no"), "") for r in rs}
            assert len(stripped) == 1, pid
    print("요청 검사 통과: 정답/조건 이름 없음, 환자별 영상·packet·공통 지시 동일")


def cmd_weights():
    now = {p.name: {"sha256": fsha(str(p.resolve())), "size": p.resolve().stat().st_size} for p in sorted(SNAP.iterdir())}
    ref = json.load(open(WCHECK116))["files"]
    diff = sorted(k for k in set(now) | set(ref) if now.get(k) != ref.get(k))
    res = dict(snapshot=str(SNAP), revision=G.MODEL_REVISION, n_files=len(now), reference=WCHECK116, reference_sha256=fsha(WCHECK116),
               differences_vs_reference=diff, files=now, checked_at=time.time())
    wr(f"{DATA}/weights_check.json", res)
    print("weights files", len(now), "diff", diff)
    if diff:
        sys.exit(1)


def cmd_lock(tests):
    t = time.time()
    files = {f: fsha(f) for f in EVAL_CODE}
    for p in (f"{PRIV}/labels.json", f"{PRIV}/cond_map.json", f"{DATA}/ledger_nogt.json", f"{DATA}/ledger_det.json", f"{DATA}/data_provenance.json",
              f"{DATA}/dedup_raw_check.json", f"{DATA}/weights_check.json", f"{OUT}/det/raw_preds.json", f"{OUT}/det/regress.json", tests,
              f"{REQ}/TECH.jsonl", f"{REQ}/MAIN.jsonl", f"{REQ}/RESUME6.jsonl", "../agent/runs/iter_118/plan.md", "../agent/runs/iter_118/plan.json"):
        files[p] = fsha(p)
    d = dict(locked_at_epoch=t, locked_at_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t)), files=files,
             classifier_version=S.CLASSIFIER_VERSION, spec_digest=S.rules_digest(),
             note="TECH/MAIN 생성 시작 전 작성. 평가 분류·정책·통계 코드와 정답·매핑 파일 hash. 생성 결과를 보고 수정하지 않는다.")
    wr(f"{PRIV}/eval_lock.json", d)
    print("locked", d["locked_at_utc"], len(files))


def gen_lock_files():
    return GEN_LOCK_CODE + [f"{DATA}/ledger_nogt.json", f"{DATA}/ledger_det.json", f"{DATA}/weights_check.json", f"{OUT}/det/raw_preds.json"]


def cmd_protocol(stage):
    wd = json.load(open(f"{DATA}/weights_check.json"))
    extra = dict(spec_version=S.SPEC_VERSION, model_revision=G.MODEL_REVISION, n_weight_files=wd["n_files"],
                 weights_check_sha256=fsha(f"{DATA}/weights_check.json"),
                 note="생성 protocol은 정답/평가 파일을 잠그지 않는다. 평가 잠금은 부모가 private/eval_lock.json으로 검증한다.")
    d = RUN.make_protocol(f"{REQ}/{stage}.jsonl", f"{PROTO}/protocol_{stage}.json", extra=extra, lock=gen_lock_files())
    bad = [f for f in d["locked_files"] if "private" in f]
    assert not bad, bad
    print("protocol", stage, fsha(f"{PROTO}/protocol_{stage}.json"), d["n_requests"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["ledger", "requests", "weights", "lock", "protocol"])
    ap.add_argument("--stage")
    ap.add_argument("--tests")
    a = ap.parse_args()
    {"ledger": cmd_ledger, "requests": cmd_requests, "weights": cmd_weights}.get(a.cmd, lambda: None)()
    if a.cmd == "lock":
        cmd_lock(a.tests)
    if a.cmd == "protocol":
        cmd_protocol(a.stage)


if __name__ == "__main__":
    main()
