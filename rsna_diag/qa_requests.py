"""iter_015/016 요청 행렬 (iter_016: OUT=run-root, SRC=읽기 전용 source-root). 요청 행(row)은 실제 prompt 원문과 evidence digest를 포함하고, request_id는 모델 revision·adapter digest·영상 identity·
target·format·condition·실제 prompt·evidence·config digest·전처리 버전 전체의 hash다 (하나라도 바뀌면 id가 바뀐다).

- 일반 요청 파일에는 category·정답이 없다. oracle 요청만 GT bbox를 prompt로 받으며 별도 stage(condition=ev_oracle)로 생성한다.
- 사용:
  python -m rsna_diag.qa_requests checkpoints                     # checkpoint table(adapter tensor digest) 생성
  python -m rsna_diag.qa_requests build --stage S --kind qa|bbox|evidence --set D36 --ckpts M0,B0 --fmt plain [--exclude-set E180] [--conds ...]
"""
import argparse
import glob
import json
import os

from . import generate, parse as PA, prompts as P, qa_spec as S

OUT = os.environ.get("QA_RUN_ROOT", "results/iter_016")   # 새 출력은 항상 이 run-root 아래에만 쓴다
SRC = "results/iter_015"                                   # 과거(iter_015) 입력·결과는 읽기 전용 source-root
CKPT_SPEC = {
    "M0": None,
    "B0": "results/iter_012/train/lr2e-4_s17/epoch_05",
    "C": "results/iter_014/full/C_lr2e-05/epoch_03",
    "B29": "results/iter_012/train/lr2e-4_s29/epoch_05",
    "B43": "results/iter_012/train/lr2e-4_s43/epoch_05",
}
ID_FIELDS = ("model_revision", "adapter_digest", "id", "split", "file_sha256", "pixel_sha256", "target", "fmt", "condition",
             "prompt_sha256", "evidence_digest", "config_digest", "preprocess")


class RequestError(RuntimeError):
    pass


def compute_id(row):
    return S.request_key({k: row.get(k) for k in ID_FIELDS})


def make_row(item, ckpt, adapter_digest, target, fmt, condition, prompt, evidence_digest, cfg_digest, stage, extra=None):
    row = {"id": item["id"], "split": item["split"], "image": item["image"], "file_sha256": item["file_sha256"],
           "pixel_sha256": item["pixel_sha256"], "checkpoint": ckpt, "adapter_digest": adapter_digest, "target": target,
           "fmt": fmt, "condition": condition, "prompt": prompt, "prompt_sha256": P.digest(prompt),
           "evidence_digest": evidence_digest, "model_revision": generate.MODEL_REVISION, "config_digest": cfg_digest,
           "preprocess": generate.PREPROC_VERSION, "stage": stage}
    if extra:
        row["extra"] = extra
    row["request_id"] = compute_id(row)
    return row


def verify_row(row, cfg_digest):
    """행 변조(prompt·evidence·adapter·영상 hash·config 등)를 감지한다."""
    if row.get("prompt_sha256") != P.digest(row["prompt"]):
        raise RequestError(f"prompt_sha256 != sha(prompt) for {row.get('request_id')}")
    if row.get("config_digest") != cfg_digest:
        raise RequestError(f"config_digest differs from protocol for {row.get('request_id')}")
    if row.get("model_revision") != generate.MODEL_REVISION:
        raise RequestError("model revision differs")
    if row.get("request_id") != compute_id(row):
        raise RequestError(f"request_id != recomputed for {row.get('request_id')}")
    ev = row.get("evidence_digest")
    if ev is not None and row["condition"] == "direct":
        raise RequestError("direct request has evidence digest")
    return True


def load_rows(path, cfg_digest=None):
    rows = [json.loads(ln) for ln in open(path) if ln.strip()]
    ids = [r["request_id"] for r in rows]
    if len(set(ids)) != len(ids):
        raise RequestError(f"duplicate request_id in {path}")
    if cfg_digest:
        for r in rows:
            verify_row(r, cfg_digest)
    return rows


def checkpoints(out=f"{OUT}/manifests/checkpoints.json"):
    import torch
    from . import eval_gate
    tab = {}
    for k, d in CKPT_SPEC.items():
        if d is None:
            tab[k] = {"dir": None, "digest": None}
            continue
        b = torch.load(os.path.join(d, "adapter.pt"), map_location="cpu", weights_only=True)
        tab[k] = {"dir": d, "digest": eval_gate.adapter_digest(d), "epoch": b.get("epoch"), "step": b.get("step"),
                  "train_digest": b.get("train_digest"), "lora": b["config"]}
    tab["_note"] = {"C": "B0(seed17) 위의 추가 SFT single trajectory. 독립 seed가 아니다. V200 선택 기준 통과 최적 모델이 아니다."}
    if os.path.exists(out):
        old = json.load(open(out))
        if old != tab:
            raise RequestError("checkpoint table exists and differs")
    json.dump(tab, open(out, "w"), indent=1)
    return tab


def patients(sets, name, exclude=None, per_cat=None):
    ids = [i for c in S.CATEGORIES for i in (sets[name][c][:per_cat] if per_cat else sets[name][c])]
    if exclude:
        ex = {i for c in S.CATEGORIES for i in sets[exclude][c]}
        ids = [i for i in ids if i not in ex]
    return ids


# bbox 원시 출력의 명시적 출처 목록. glob의 마지막 결과로 덮어쓰지 않는다. 같은 id가 두 출처에 있으면 오류.
# ("reuse", jsonl 경로) | ("gen", 완료된 stage 디렉터리). 신규(iter_016) e600 C bbox는 run-root gen에 있으면 추가된다.
def bbox_sources(ckpt):
    src = {"M0": [("reuse", f"{SRC}/reuse/bbox_M0_concise.jsonl")],
           "B0": [("reuse", f"{SRC}/reuse/bbox_B0_concise.jsonl"), ("gen", f"{SRC}/gen/d12_bbox__B0")],
           "C": [("gen", f"{SRC}/gen/e180_bbox__C"), ("gen", f"{SRC}/gen/d12_bbox__C")]}[ckpt]
    extra = f"{OUT}/gen/e600x_bbox__{ckpt}"
    if ckpt == "C" and os.path.isdir(extra):
        src.append(("gen", extra))
    return src


def bbox_records(ckpt, sources=None):
    """ckpt의 concise bbox 원시 record {id: record}. 명시한 출처만 읽고, 출처 간 동일 id 충돌은 거부한다."""
    out, origin = {}, {}
    for kind, p in (sources or bbox_sources(ckpt)):
        if kind == "reuse":
            recs = [json.loads(ln) for ln in open(p) if ln.strip()]
        else:
            if not os.path.exists(f"{p}/completion.json"):
                raise RequestError(f"bbox source {p} has no completion.json (incomplete stage)")
            recs = [r for f in sorted(glob.glob(f"{p}/gen_worker*.jsonl")) for r in generate.read_records(f)
                    if r.get("condition") == "bbox" and r.get("checkpoint") == ckpt]
        seen = set()
        for r in recs:
            if r["id"] in seen:
                raise RequestError(f"duplicate bbox record for {r['id']} inside source {p}")
            seen.add(r["id"])
            if r["id"] in out:
                raise RequestError(f"bbox record for {r['id']} present in both {origin[r['id']]} and {p}")
            out[r["id"]] = r
            origin[r["id"]] = p
    return out


def predicted_boxes(rec):
    """returns (boxes or None, status). 유효 출력만 boxes를 가진다 (빈 목록은 []). 형식 실패·잘림·누락은 None."""
    if rec is None:
        return None, "missing"
    pr = PA.parse_response(rec["suffix_text_raw"], rec["ended_eos"])
    if pr["status"] in PA.VALID:
        return [[int(round(v)) for v in b] for b in pr["boxes"]], pr["status"]
    return None, pr["status"]


def build(a):
    sets = json.load(open(f"{OUT}/manifests/sets.json"))
    man = {}
    for ln in open(f"{OUT}/manifests/infer_manifest.jsonl"):
        r = json.loads(ln)
        man[r["id"]] = r
    labels = json.load(open(f"{OUT}/manifests/labels.json")) if a.kind == "evidence" and "oracle" in a.conds.split(",") else None
    tab = json.load(open(f"{OUT}/manifests/checkpoints.json"))
    from . import qa_protocol
    cfg, _ = qa_protocol.static_cfg()
    ids = a.ids.split(',') if a.ids else patients(sets, a.set, a.exclude_set, a.per_cat)
    os.makedirs(f"{OUT}/requests", exist_ok=True)
    counts = {}
    ckpts = a.ckpts.split(",")
    per = {c: [] for c in ckpts}
    for c in ckpts:
        ad = tab[c]["digest"]
        if a.kind == "qa":
            for i in ids:
                for t in S.TARGETS:
                    per[c].append(make_row(man[i], c, ad, t, a.fmt, "direct", S.qa_prompt(t, a.fmt), None, cfg, a.stage))
        elif a.kind == "bbox":
            for i in ids:
                per[c].append(make_row(man[i], c, ad, "bbox", "concise", "bbox", P.CONCISE, None, cfg, a.stage))
        else:  # evidence: reader는 base(M0)
            src = bbox_records(a.evidence_source)
            for i in ids:
                for cond in a.conds.split(","):
                    if cond == "oracle":
                        boxes = [b["yxyx_norm"] for b in labels[i]["boxes"]]
                        txt, meta = S.evidence_text("oracle", boxes), {"source": "gt"}
                    elif cond == "unavailable":
                        txt, meta = S.evidence_text("unavailable"), {"source": None}
                    else:
                        if i not in src:
                            raise RequestError(f"no {a.evidence_source} bbox record for {i}")
                        boxes, st = predicted_boxes(src[i])
                        txt = S.evidence_text("predicted", boxes)
                        meta = {"source": a.evidence_source, "source_request_id": src[i].get("request_id"), "source_status": st}
                    for t in S.TARGETS:
                        per[c].append(make_row(man[i], c, ad, t, a.fmt, f"ev_{cond}", S.qa_prompt(t, a.fmt, txt), S.sha(txt), cfg,
                                               a.stage, extra=meta))
    for c, rows in per.items():
        p = f"{OUT}/requests/{a.stage}__{c}.jsonl"
        if os.path.exists(p):
            raise RequestError(f"{p} exists (not overwriting)")
        with open(p, "w") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")
        counts[c] = len(rows)
    print(json.dumps({"stage": a.stage, "n_patients": len(ids), "rows": counts}))


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    sp.add_parser("checkpoints")
    b = sp.add_parser("build")
    b.add_argument("--stage", required=True)
    b.add_argument("--kind", required=True, choices=["qa", "bbox", "evidence"])
    b.add_argument("--set", default=None)
    b.add_argument("--per-cat", type=int, default=None, help="각 category의 앞 N명 (표본은 category별로 먼저 고정한 뒤 요청을 구성한다)")
    b.add_argument("--ids", default=None, help="stress 등 명시적 id 목록(쉼표)")
    b.add_argument("--exclude-set", default=None)
    b.add_argument("--ckpts", required=True)
    b.add_argument("--fmt", default="plain")
    b.add_argument("--conds", default="predicted,unavailable,oracle")
    b.add_argument("--evidence-source", default="B0")
    a = ap.parse_args()
    if a.cmd == "checkpoints":
        print(json.dumps({k: v.get("digest") for k, v in checkpoints().items() if k != "_note"}))
    else:
        build(a)


if __name__ == "__main__":
    main()
