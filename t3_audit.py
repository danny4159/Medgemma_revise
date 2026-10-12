"""iter_120 Task3(MedSG multi_view) 한정 자료 적합성 점검.
bench_task3.parquet 한 파일만 읽는다. 모델 출력 없음. 결과: results/iter_120/data/audit.json
"""
import json, hashlib, re, sys, collections, io, itertools
import pyarrow.parquet as pq
from PIL import Image

REV = "557aa67d13c4cbfe458ca9d1d02f42dfee185d1a"
P = ("results/iter_120/data/hf/datasets--MedSG-Bench--MedSG-Bench-parquet/snapshots/%s/bench_task3.parquet" % REV)
ORD = {"first": 0, "second": 1, "third": 2}
BOX = re.compile(r"\((\d+),(\d+)\),\((\d+),(\d+)\)")


def iou(a, b):
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    i = ix * iy
    u = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - i
    return i / u if u > 0 else 0.0


def source_of(name):
    # 예: LUNA16_CT_RightLung_npy_imgs_casenum_..._top.png
    m = re.match(r"(.+?)_(CT|MRI|MR)_(.+?)_npy_imgs_casenum_(.+)_(top|front|side)\.png$", name)
    if not m:
        return None
    return dict(dataset=m.group(1), modality=m.group(2), organ=m.group(3), case=m.group(4), view=m.group(5))


def load():
    t = pq.read_table(P).to_pylist()
    out = []
    for i, r in enumerate(t):
        n = r["num_images"]
        imgs = [r["image_bytes_%d" % k] for k in range(1, n + 1)]
        paths = [x.split("/")[-1] for x in json.loads(r["images_json"])]
        m = re.search(r"locate this object in the (\w+) image", r["question"])
        qq = r["question"].replace("<|box_start|>", "").replace("<|box_end|>", "")
        rb = BOX.findall(qq)
        ref = [int(v) for v in rb[0]] if rb else None
        ans = json.loads(r["answer_xyxy"]) if isinstance(r["answer_xyxy"], str) else list(r["answer_xyxy"])
        sizes = []
        psha = []
        for b in imgs:
            im = Image.open(io.BytesIO(b))
            sizes.append(list(im.size))
            psha.append(hashlib.sha256(im.convert("RGB").tobytes()).hexdigest())
        out.append(dict(
            i=i, n=n, paths=paths, tv=m.group(1) if m else None, ref=ref, ans=ans,
            extra=r["extra_json"], q=r["question"], sizes=sizes,
            sha=[hashlib.sha256(b).hexdigest() for b in imgs], psha=psha,
            src=[source_of(p) for p in paths]))
    return out


def main():
    rows = load()
    rep = {"parquet_rev": REV, "n_rows": len(rows)}
    rep["num_images"] = dict(collections.Counter(r["n"] for r in rows))
    rep["target_view_word"] = dict(collections.Counter(r["tv"] for r in rows))
    rep["unparsed_source"] = sum(1 for r in rows if any(s is None for s in r["src"]))
    rep["datasets_modality"] = dict(collections.Counter(r["src"][0]["dataset"] + "/" + r["src"][0]["modality"] for r in rows if r["src"][0]))
    rep["question_templates"] = dict(collections.Counter(re.sub(r"\(\d+,\d+\),\(\d+,\d+\)", "B", r["q"]) for r in rows).most_common(12))
    # 대상 영상 선택: 질문이 지정한 번째
    for r in rows:
        k = ORD.get(r["tv"])
        r["tidx"] = k
        r["tsha"] = r["psha"][k] if k is not None and k < r["n"] else None
        r["tsize"] = r["sizes"][k] if k is not None and k < r["n"] else None
        r["tview"] = r["src"][k]["view"] if k is not None and k < r["n"] and r["src"][k] else None
        r["rview"] = r["src"][0]["view"] if r["src"][0] else None
        r["rsha"] = r["psha"][0]
        r["rsize"] = r["sizes"][0]
    # 같은 target 영상 hash 그룹
    g = collections.defaultdict(list)
    for r in rows:
        if r["tsha"]:
            g[r["tsha"]].append(r)
    rep["distinct_target_hash"] = len(g)
    rep["target_group_size_hist"] = dict(collections.Counter(len(v) for v in g.values()))
    pairs = []
    for h, v in g.items():
        for a, b in itertools.combinations(v, 2):
            same_case = a["src"][0] and b["src"][0] and a["src"][0]["case"] == b["src"][0]["case"] and a["src"][0]["dataset"] == b["src"][0]["dataset"]
            pairs.append(dict(
                a=a["i"], b=b["i"], same_case=bool(same_case),
                dataset=a["src"][0]["dataset"] if a["src"][0] else None,
                organ_a=a["src"][0]["organ"] if a["src"][0] else None,
                organ_b=b["src"][0]["organ"] if b["src"][0] else None,
                case=a["src"][0]["case"] if a["src"][0] else None,
                ref_sha_same=a["rsha"] == b["rsha"],
                ref_box_a=a["ref"], ref_box_b=b["ref"],
                ans_a=a["ans"], ans_b=b["ans"], iou_ans=iou(a["ans"], b["ans"]),
                ref_view_a=a["rview"], ref_view_b=b["rview"], target_view=a["tview"], tsize=a["tsize"]))
    rep["n_pairs_same_target_hash"] = len(pairs)
    rep["pairs_same_case"] = sum(p["same_case"] for p in pairs)
    rep["pairs_by_organ_equal"] = sum(p["organ_a"] == p["organ_b"] for p in pairs)
    rep["pairs_ans_iou_le_0.1"] = sum(p["iou_ans"] <= 0.1 for p in pairs)
    rep["pairs_ans_iou_le_0.1_diff_organ"] = sum(p["iou_ans"] <= 0.1 and p["organ_a"] != p["organ_b"] for p in pairs)
    rep["pairs_ans_iou_le_0.1_same_organ"] = sum(p["iou_ans"] <= 0.1 and p["organ_a"] == p["organ_b"] for p in pairs)
    rep["pairs_sample"] = pairs[:12]
    rep["sizes"] = dict(collections.Counter(json.dumps(r["tsize"]) for r in rows).most_common(8))
    rep["extra_sizes"] = dict(collections.Counter(r["extra"] for r in rows).most_common(8))
    rep["organs"] = dict(collections.Counter((r["src"][0]["dataset"], r["src"][0]["organ"]) .__repr__() for r in rows if r["src"][0]).most_common(60))
    with open("results/iter_120/data/audit_raw.json", "w") as f:
        json.dump(rep, f, indent=1, ensure_ascii=False, default=str)
    keys = [k for k in rep if k not in ("pairs_sample", "question_templates", "organs")]
    print(json.dumps({k: rep[k] for k in keys}, ensure_ascii=False, indent=1, default=str))
    print(json.dumps(rep["pairs_sample"][:6], ensure_ascii=False, default=str))
    print(json.dumps(rep["question_templates"], ensure_ascii=False)[:1500])


if __name__ == "__main__":
    main()
