"""iter_054 자료 구축: source 검증 → 영상 hash/mode → 의존성 component → 사전 의심 선별 → 기술 표본 → 요청·eval 매핑.
출력(모두 새 파일, 덮어쓰기 금지): results/iter_054/data/{images_info,eval_manifest,data_report}.json, requests.jsonl.
모델 출력은 읽지 않는다. 의심 선별은 어휘 규칙이며 임상 재판독이 아니다 (원 점수에서 제거하지 않고 민감도 분석에만 사용)."""
import json
import os
import re
import sys
from collections import Counter

os.environ.setdefault("HF_HOME", "/SSD1_1TB/home/milab/daniel/08_medgemma/hf_cache")
os.environ.setdefault("HF_HUB_OFFLINE", "1")
import numpy as np
from PIL import Image

import mc54_requests as R
import mc54_spec as S

SRC = "results/iter_054/source"
DATA = "results/iter_054/data"
STOP = set("a an the of in on with and or to is are was were be by for at as from this that these those it its into no not "
           "there showing shows show seen image images view after before without within between over under left right "
           "arrow arrows".split())


def jload(p):
    return json.load(open(p))


def verify_source():
    man = jload(f"{SRC}/source_manifest.json")
    for f, m in man["files"].items():
        if S.sha(open(m["saved"], "rb").read()) != m["sha256"]:
            sys.exit(f"source changed: {f}")
    return man


def words(t):
    return {w for w in re.findall(r"[a-z]+", t.lower()) if w not in STOP and len(w) > 2}


def frac(opt, cap):
    w = words(opt)
    return len(w & words(cap)) / len(w) if w else 0.0


def suspicion(d):
    """pair별 사전 의심 규칙: 어느 영상이든 (틀린 선택지의 caption 어휘 포함률 − 정답 선택지의 포함률) ≥ 0.25."""
    out = []
    for k in ("1", "2"):
        cor = d[f"im_{k}_correct"]
        o_c = d["option_A"] if cor == "A" else d["option_B"]
        o_w = d["option_B"] if cor == "A" else d["option_A"]
        cap = d[f"cap_{k}"]
        out.append(round(frac(o_w, cap) - frac(o_c, cap), 4))
    return out


def load_rgb(path):
    """JPEG → RGB. L은 3채널 복제(값 보존), RGB는 그대로. 그 외 mode는 거부(조용한 정규화 금지)."""
    im = Image.open(path)
    im.load()
    if im.mode == "RGB":
        arr = np.asarray(im)
    elif im.mode == "L":
        arr = np.asarray(im.convert("RGB"))
    else:
        raise ValueError(f"unsupported mode {im.mode} {path}")
    return im.mode, Image.fromarray(arr), arr


def components(pairs, dataset, imginfo, pmc_of):
    """공유 영상 local / PMC / 동일 pixel hash로 pair를 연결한 union-find 성분."""
    par = {p: p for p in pairs}

    def f(x):
        while par[x] != x:
            par[x] = par[par[x]]
            x = par[x]
        return x

    key_owner = {}
    for p in pairs:
        d = dataset[p]
        keys = []
        for k in ("im_1_local", "im_2_local"):
            loc = d[k]
            keys += [("img", loc), ("pmc", pmc_of[loc])]
            if loc in imginfo:
                keys.append(("px", imginfo[loc]["pixel_sha256"]))
        for kk in keys:
            if kk in key_owner:
                par[f(p)] = f(key_owner[kk])
            else:
                key_owner[kk] = p
    comp = {}
    for p in pairs:
        comp.setdefault(f(p), []).append(p)
    return sorted((sorted(v) for v in comp.values()), key=lambda v: (-len(v), v[0]))


def main():
    man = verify_source()
    dataset = jload(f"{SRC}/data__dataset.json")
    idict = jload(f"{SRC}/data__image_dict.json")
    fetch = jload(f"{DATA}/fetch_manifest.json")
    assert len(dataset) == 176
    if any(os.path.exists(f"{DATA}/{n}") for n in ("images_info.json", "eval_manifest.json", "data_report.json", "requests.jsonl")):
        sys.exit("build outputs exist; refusing to overwrite")
    local_of = {v["local"]: v for v in idict.values()}
    pmc_of = {v["local"]: re.search(r"(PMC\d+)", v["dlink"]).group(1) for v in idict.values()}
    # im_x_local ↔ image_dict 일치 검사
    for pid, d in dataset.items():
        for k in ("1", "2"):
            ent = idict.get(d[f"im_{k}"])
            if ent is None or ent["local"] != d[f"im_{k}_local"]:
                sys.exit(f"pair {pid}: im_{k} not consistent with image_dict")
    # 영상 정보
    imginfo, missing = {}, {}
    for r in fetch:
        loc = r["local"]
        if r["status"] != "ok":
            missing[loc] = {"status": r["status"], "candidates": r.get("candidates")}
            continue
        if S.sha(open(r["saved"], "rb").read()) != r["sha256"]:
            sys.exit(f"image changed {r['saved']}")
        mode, pil, arr = load_rgb(r["saved"])
        imginfo[loc] = {"path": r["saved"], "file_sha256": r["sha256"], "mode": mode, "size": list(pil.size),
                        "pixel_sha256": S.sha(arr.tobytes() + str(arr.shape).encode()), "pmc": r["pmc"],
                        "file_name": r["file_name"], "s3_key": r["s3_key"]}
    all_locals = {d[f"im_{k}_local"] for d in dataset.values() for k in ("1", "2")}
    assert all_locals == set(imginfo) | set(missing), (len(all_locals), len(imginfo), len(missing))
    avail = sorted(p for p, d in dataset.items() if d["im_1_local"] in imginfo and d["im_2_local"] in imginfo)
    unavailable = sorted(set(dataset) - set(avail))
    # 중복 pixel (서로 다른 local이 같은 pixel)
    pxc = Counter(v["pixel_sha256"] for v in imginfo.values())
    dup_px = {h: [l for l, v in imginfo.items() if v["pixel_sha256"] == h] for h, c in pxc.items() if c > 1}
    comps = components(sorted(dataset), dataset, imginfo, pmc_of)
    comp_of = {p: i for i, c in enumerate(comps) for p in c}
    avail_comp_sizes = Counter(comp_of[p] for p in avail)
    # 기술 표본: seed 54, ID hash 순서, category 포함
    order = sorted(avail, key=lambda p: S.sha(f"{S.SEED}|{p}"))
    cats = lambda p: set(dataset[p]["category_1"]) | set(dataset[p]["category_2"])
    tech, covered = [], set()
    for p in order:
        if len(tech) >= 12:
            break
        if cats(p) - covered:
            tech.append(p)
            covered |= cats(p)
    for p in order:
        if len(tech) >= 12:
            break
        if p not in tech:
            tech.append(p)
    # 추가 포함(자원 검사): 원본 크기 최대 영상 pair, 답변 token 최장 pair
    import transformers
    from rsna_diag import generate as G
    os.environ.setdefault("HF_HOME", G.HF_HOME)
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    tk = transformers.AutoProcessor.from_pretrained(G.MODEL_ID, revision=G.MODEL_REVISION).tokenizer
    biggest = max(imginfo, key=lambda l: (imginfo[l]["size"][0] * imginfo[l]["size"][1], l))
    p_big = min(p for p in avail if biggest in (dataset[p]["im_1_local"], dataset[p]["im_2_local"]))
    ntok = {p: max(len(tk.encode(dataset[p]["option_A"], add_special_tokens=False)),
                   len(tk.encode(dataset[p]["option_B"], add_special_tokens=False))) for p in avail}
    p_long = max(avail, key=lambda p: (ntok[p], p))
    extras = [p for p in (p_big, p_long) if p not in tech]
    tech_all = sorted(set(tech) | set(extras))
    rows, evalmap = R.build(dataset, imginfo, set(avail), set(tech_all))
    R.write_jsonl(f"{DATA}/requests.jsonl", rows)
    susp = {p: suspicion(dataset[p]) for p in dataset}
    flagged = sorted(p for p, v in susp.items() if max(v) >= 0.25)
    pairs_meta = {}
    for p in sorted(dataset):
        d = dataset[p]
        pairs_meta[p] = {"im1_local": d["im_1_local"], "im2_local": d["im_2_local"], "im1_correct": d["im_1_correct"],
                         "im2_correct": d["im_2_correct"], "categories": sorted(cats(p)), "component": comp_of[p],
                         "available": p in avail, "suspect_scores": susp[p], "suspect_flag": p in flagged,
                         "tech": p in tech_all, "tech_role": ("sample" if p in tech else ("extra_big_image" if p == p_big else
                                                              "extra_long_answer") if p in tech_all else None)}
    ev = {"source_revision": man["revision"], "pairs": pairs_meta, "requests": evalmap,
          "components": [{"id": i, "pairs": c, "n": len(c), "n_available": avail_comp_sizes.get(i, 0)} for i, c in enumerate(comps)]}
    comp_sz = [len(c) for c in comps]
    rep = {"n_pairs_official": len(dataset), "n_pairs_available": len(avail), "unavailable_pairs": unavailable,
           "missing_images": {str(k): v for k, v in missing.items()}, "n_unique_images_official": len(all_locals),
           "n_unique_images_acquired": len(imginfo), "n_unique_pmc": len(set(pmc_of.values())),
           "n_unique_pixel_hash": len(pxc), "duplicate_pixel_groups": dup_px,
           "n_components_all_pairs": len(comps), "component_sizes_top10": comp_sz[:10], "max_component_share_all": comp_sz[0] / len(dataset),
           "n_components_available": len(avail_comp_sizes),
           "max_component_share_available": max(avail_comp_sizes.values()) / len(avail),
           "image_modes": dict(Counter(v["mode"] for v in imginfo.values())),
           "tech_pairs": tech_all, "tech_sample": tech, "tech_extras": {"big_image_pair": p_big, "big_image_local": biggest,
                                                                           "long_answer_pair": p_long, "max_answer_tokens": ntok[p_long]},
           "tech_categories_covered": sorted(covered), "n_requests": len(rows), "n_requests_by_kind": dict(Counter(r["kind"] for r in rows)),
           "n_requests_tech": sum(r["stage"] == "tech" for r in rows),
           "n_text_only_requests": sum(r["modality"] == "text" for r in rows),
           "suspect_rule": "any image: frac(wrong option content words in caption) - frac(correct option) >= 0.25",
           "n_suspect_flagged": len(flagged), "suspect_pairs": flagged,
           "repeated_question_options": sum(c > 1 for c in Counter((d["question"], d["option_A"], d["option_B"]) for d in dataset.values()).values()),
           "license_note": "figures from PMC Open Access subset via AWS pmc-oa-opendata (per-article licenses vary, e.g. CC BY-NC); research diagnostic use only",
           "note": "ambiguous image (two different PMC versions) kept missing; pair not substituted"}
    for n, o in (("images_info.json", imginfo), ("eval_manifest.json", ev), ("data_report.json", rep)):
        with open(f"{DATA}/{n}", "x") as f:
            json.dump(o, f, indent=1)
    print(json.dumps({k: rep[k] for k in ("n_pairs_available", "n_unique_images_acquired", "n_unique_pmc", "n_components_available",
                                          "max_component_share_available", "n_requests", "n_requests_tech", "n_suspect_flagged",
                                          "duplicate_pixel_groups", "tech_extras")}, indent=1))


if __name__ == "__main__":
    main()
