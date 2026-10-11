"""iter_108 한정 자료 점검: 환자 집합·정답·저장 B0 bbox·F(M0 direct plain) 출력·영상 hash 연결을 읽기 전용으로 검증한다.

읽는 자산 (모두 기존 결과, 수정하지 않는다):
  iter_016/manifests/{sets,labels,infer_manifest,checkpoints}, iter_015/reuse/bbox_B0_concise.jsonl,
  iter_016/gen/{e180_plain,e600x_plain}__M0 (F), iter_017/gen/{p180,e600x}_ev17__M0 (역사적 참조).
"""
import glob
import hashlib
import json
import os
from pathlib import Path

import ev108_spec as S
from rsna_diag import qa_spec

ROOT = Path(__file__).resolve().parent
R16 = ROOT / "results/iter_016"
R15 = ROOT / "results/iter_015"
R17 = ROOT / "results/iter_017"
LOCKED_INPUTS = [R16 / "manifests/sets.json", R16 / "manifests/labels.json", R16 / "manifests/infer_manifest.jsonl",
                 R16 / "manifests/checkpoints.json", R15 / "reuse/bbox_B0_concise.jsonl", R15 / "reuse/reuse_report.json"]
F_STAGES = ["e180_plain__M0", "e600x_plain__M0"]
REF_STAGES = {"p180_ev17__M0": R17 / "gen/p180_ev17__M0", "e600x_ev17__M0": R17 / "gen/e600x_ev17__M0"}


def file_sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 22), b""):
            h.update(b)
    return h.hexdigest()


def read_jsonl(p):
    return [json.loads(l) for l in open(p) if l.strip()]


def load_assets():
    sets = json.load(open(R16 / "manifests/sets.json"))
    labels = json.load(open(R16 / "manifests/labels.json"))
    infer = {r["id"]: r for r in read_jsonl(R16 / "manifests/infer_manifest.jsonl")}
    ckpt = json.load(open(R16 / "manifests/checkpoints.json"))
    bbox = {}
    for r in read_jsonl(R15 / "reuse/bbox_B0_concise.jsonl"):
        if r["id"] in bbox:
            raise ValueError(f"duplicate bbox record {r['id']}")
        bbox[r["id"]] = r
    return sets, labels, infer, ckpt, bbox


def audit(sets, labels, infer, ckpt, bbox):
    """returns (report dict, problems list). 문제가 있으면 모델 비교를 실행하지 않는다."""
    problems = []
    rep = {"sets": {}, "nonempty": {}, "status": {}}
    b0_digest = None
    if isinstance(ckpt, dict):
        c = ckpt.get("B0") or ckpt.get("checkpoints", {}).get("B0")
        b0_digest = (c or {}).get("digest") if isinstance(c, dict) else None
    rep["b0_adapter_digest_checkpoints"] = b0_digest
    for name in ("P180", "E600"):
        ids_by_cat = sets[name]
        allids = [i for c in S.CATS for i in ids_by_cat[c]]
        if len(allids) != len(set(allids)):
            problems.append(f"{name}: duplicate ids")
        rep["sets"][name] = {c: len(ids_by_cat[c]) for c in S.CATS}
        ne, st = {c: 0 for c in S.CATS}, {}
        for c in S.CATS:
            for i in ids_by_cat[c]:
                if labels[i]["category"] != c:
                    problems.append(f"{i}: label category {labels[i]['category']} != set {c}")
                if i not in infer:
                    problems.append(f"{i}: missing infer manifest")
                    continue
                if i not in bbox:
                    problems.append(f"{i}: missing bbox")
                    continue
                b = bbox[i]
                if b.get("checkpoint") != "B0" or b.get("condition") != "bbox":
                    problems.append(f"{i}: bbox record not B0/bbox")
                if b0_digest and b.get("adapter_digest") != b0_digest:
                    problems.append(f"{i}: bbox adapter digest != checkpoints B0")
                s, boxes = S.parse_saved_bbox(b["suffix_text_raw"], b["ended_eos"])
                st[s] = st.get(s, 0) + 1
                if s == "ok":
                    ne[c] += 1
                if s in ("invalid", "truncated"):
                    problems.append(f"{i}: saved bbox {s}")
        rep["nonempty"][name] = ne
        rep["status"][name] = st
    want = {"P180": {"opacity": 54, "normal": 1, "not_normal_no_opacity": 17},
            "E600": {"opacity": 164, "normal": 5, "not_normal_no_opacity": 67}}
    for name in want:
        if rep["nonempty"][name] != want[name]:
            problems.append(f"{name}: nonempty {rep['nonempty'][name]} != plan {want[name]}")
    # P180 ⊂ E600
    p = {i for c in S.CATS for i in sets["P180"][c]}
    e = {i for c in S.CATS for i in sets["E600"][c]}
    if not p <= e:
        problems.append("P180 not subset of E600")
    # 영상 file hash
    bad = 0
    for i in e:
        r = infer[i]
        if not os.path.exists(ROOT / r["image"]) or file_sha(ROOT / r["image"]) != r["file_sha256"]:
            bad += 1
    rep["image_file_hash_mismatch"] = bad
    if bad:
        problems.append(f"image file hash mismatch {bad}")
    return rep, problems


def load_gen_dir(d, rows_path=None):
    """completion을 가진 생성 디렉터리의 record를 읽는다 (worker 파일 hash 대조). returns (records, completion)."""
    d = Path(d)
    comp = json.load(open(d / "completion.json"))
    recs = []
    for fn in sorted(glob.glob(str(d / "gen_worker*.jsonl"))):
        pf = comp.get("per_file", {})
        recs += read_jsonl(fn)
    return recs, comp


def load_F():
    """F: iter_016 M0 direct plain (target O/A). returns {(id,target): record}. 중복/충돌은 예외."""
    out = {}
    comps = {}
    for st in F_STAGES:
        recs, comp = load_gen_dir(R16 / "gen" / st)
        comps[st] = {k: comp.get(k) for k in ("n_expected", "n_actual_unique", "n_missing", "n_duplicate", "n_extra", "returncodes",
                                              "protocol_digest", "requests_sha256", "verify_error")}
        for r in recs:
            if r.get("condition") != "direct" or r.get("fmt") != "plain" or r.get("checkpoint") != "M0":
                continue
            k = (r["id"], r["target"])
            if k in out:
                raise ValueError(f"duplicate F record {k}")
            out[k] = r
    return out, comps
