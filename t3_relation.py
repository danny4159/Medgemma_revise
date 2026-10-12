"""iter_120: Task3에서 '같은 target pixels + 서로 다른 reference 대상' 관계의 존재 여부를 모델 출력 없이 집계한다."""
import json, collections, itertools, sys
sys.path.insert(0, ".")
import t3_audit as a


def main():
    rows = a.load()
    for r in rows:
        k = a.ORD[r["tv"]]
        r["tk"] = k
        r["tsha"] = r["sha"][k]
        s = r["src"][k]
        r["tview"] = s["view"] if s else None
    rep = {}
    # (1) 동일 target hash 쌍의 reference 동일 여부
    g = collections.defaultdict(list)
    for r in rows:
        g[r["tsha"]].append(r)
    c = collections.Counter()
    for v in g.values():
        for x, y in itertools.combinations(v, 2):
            c[json.dumps(dict(ref_same=x["ref"] == y["ref"], refimg_same=x["sha"][0] == y["sha"][0],
                              ans_same=x["ans"] == y["ans"]))] += 1
    rep["same_target_hash_pairs"] = dict(c)
    # (2) 같은 case·같은 target view에서 reference organ이 다른 행 묶음
    g2 = collections.defaultdict(list)
    for r in rows:
        s = r["src"][0]
        if s and r["src"][r["tk"]]:
            g2[(s["dataset"], s["modality"], s["case"], r["tview"])].append(r)
    rep["case_view_group_hist"] = dict(collections.Counter(len(v) for v in g2.values()))
    multi = []
    for k, v in g2.items():
        organs = {x["src"][0]["organ"] for x in v}
        if len(v) > 1 and len(organs) > 1:
            multi.append((k, v))
    rep["case_view_groups_multi_organ"] = len(multi)
    ex = []
    for k, v in multi[:6]:
        ex.append(dict(key=k, rows=[dict(i=x["i"], organ=x["src"][0]["organ"], ref=x["ref"], ans=x["ans"], tsha=x["tsha"][:10],
                                          refsha=x["sha"][0][:10], size=x["sizes"][x["tk"]]) for x in v]))
    rep["examples"] = ex
    # (3) target 영상이 같은 pixels인지(동일 case·view·organ 다른 organ 의 영상 pixel 동일성)
    same_pix = 0
    tot = 0
    for k, v in multi:
        tot += 1
        if len({x["tsha"] for x in v}) == 1:
            same_pix += 1
    rep["multi_organ_groups_same_target_pixels"] = same_pix
    rep["multi_organ_groups_total"] = tot
    # (4) 이름은 같지만 organ 별로 영상이 다름(마스크 overlay 포함?) -> 영상 hash 다른 경우
    json.dump(rep, open("results/iter_120/data/relation_scan.json", "w"), indent=1, ensure_ascii=False, default=str)
    print(json.dumps(rep, indent=1, ensure_ascii=False, default=str)[:6000])


if __name__ == "__main__":
    main()
