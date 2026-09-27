"""iter_017 재사용 검증: iter_015/016의 확정 표본·B0 concise bbox·direct QA·기존 evidence 결과를 현재 입력·adapter·요청과 대조하고
검증 근거(원본 sha256 포함)를 results/iter_017/reuse/reuse_manifest.json에 남긴다. 과거 protocol은 재잠금하지 않는다.

사용: python -m rsna_diag.ev17_reuse build
"""
import glob
import json
import os
import sys

from . import lock_protocol, qa_gen, qa_requests as Q, qa_reuse, qa_protocol

OLD = "results/iter_016"
MANIFEST = f"{Q.OUT}/reuse/reuse_manifest.json"
# 재사용하는 iter_016 stage: (stage, ckpt)
OLD_STAGES = [(f"{st}", ck) for st in ("e180_plain", "e600x_plain") for ck in ("M0", "B0", "C")] + [("p60_ev", "M0"), ("p180x_ev", "M0")]


def _protocol_of(stage_dir):
    want = json.load(open(f"{stage_dir}/completion.json"))["protocol_digest"]
    hits = [f for f in sorted(glob.glob(f"{OLD}/protocols/*.json")) if lock_protocol.digest_of(f) == want]
    if len(hits) != 1:
        raise qa_gen.QAError(f"{stage_dir}: {len(hits)} iter_016 protocol files match completion digest")
    return hits[0]


def build(out=MANIFEST):
    if os.path.exists(out):
        raise SystemExit(f"{out} exists (not overwriting)")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    m = {"manifests": qa_reuse.import_manifests()}
    # checkpoint table: 새로 계산해 iter_016 표와 같아야 한다 (qa_requests.checkpoints는 다르면 예외)
    tab_new = Q.checkpoints()
    tab_old = json.load(open(f"{OLD}/manifests/checkpoints.json"))
    if tab_new != tab_old:
        raise qa_gen.QAError("iter_017 checkpoint table differs from iter_016")
    m["checkpoints"] = {k: v.get("digest") for k, v in tab_new.items() if k != "_note"}
    tab = tab_new
    m["bbox_B0"] = qa_reuse.verify_old_bbox_reuse("B0", tab)
    old_ck = qa_reuse.verify_old_stage(f"{Q.SRC}/gen/d12_bbox__B0", f"{Q.SRC}/requests/d12_bbox__B0.jsonl", "B0",
                                       qa_reuse._protocol_of(f"{Q.SRC}/gen/d12_bbox__B0"), tab)
    old_ck["completion_sha256"] = qa_reuse.fsha(f"{Q.SRC}/gen/d12_bbox__B0/completion.json")
    m["bbox_B0_d12"] = old_ck
    m["iter016_stages"] = {}
    for st, ck in OLD_STAGES:
        d = f"{OLD}/gen/{st}__{ck}"
        pp = _protocol_of(d)
        info = qa_reuse.verify_old_stage(d, f"{OLD}/requests/{st}__{ck}.jsonl", ck, pp, tab)
        info["completion_sha256"] = qa_reuse.fsha(f"{d}/completion.json")
        m["iter016_stages"][f"{st}__{ck}"] = info
    json.dump(m, open(out, "w"), indent=1)
    return m


def pins(path=MANIFEST):
    """검증된 reuse manifest -> {bbox 원본 경로: sha256}. bbox_records의 pinned 인자."""
    m = json.load(open(path))
    b = m["bbox_B0"]
    return {b["path"]: b["sha256"]}


def install_pins(path=MANIFEST):
    Q.PINNED_SHA.clear()
    Q.PINNED_SHA.update(pins(path))
    return Q.PINNED_SHA


if __name__ == "__main__":
    if sys.argv[1:2] == ["build"]:
        r = build()
        print(json.dumps({"n_stages": len(r["iter016_stages"]), "bbox_B0": {k: r["bbox_B0"][k] for k in ("path", "n", "sha256")}}, indent=1))
    else:
        sys.exit("usage: python -m rsna_diag.ev17_reuse build")
