"""iter_054 요청 행 구성 (결정적). 추론 행에는 pair ID·정답·caption·category를 넣지 않는다 (불투명 request_id).
평가용 대응(request_id → pair/영상 슬롯/순서)은 별도 eval 매핑에만 둔다.
같은 함수를 launch 시점에 잠긴 source에서 재구성해 요청 파일과 대조하는 데도 쓴다."""
import hashlib
import json

import mc54_spec as S

REV = "mc54_requests_v1"


def rid(kind, cond, pair, image_local, order):
    return S.sha(f"{REV}|{kind}|{cond}|{pair}|{image_local}|{order}")[:24]


def build(dataset, imginfo, avail_pairs, tech_pairs):
    """dataset: 공식 dataset.json dict. imginfo: {local(int): {path,file_sha256,pixel_sha256,mode,size}}.
    avail_pairs: 두 영상이 모두 확보된 pair ID 집합. tech_pairs: 기술 표본 pair ID 집합.
    returns rows(list), evalmap({request_id: {...}})."""
    rows, evalmap = [], {}

    def add(row, meta):
        row["prompt_sha256"] = S.sha(row["prompt"])
        row["order_key"] = S.sha(row["request_id"])[:16]
        row["stage"] = "tech" if meta["pair"] in tech_pairs else "main"
        assert row["request_id"] not in evalmap
        rows.append(row)
        evalmap[row["request_id"]] = meta

    for pid in sorted(avail_pairs):
        d = dataset[pid]
        q, oa, ob = d["question"], d["option_A"], d["option_B"]
        slots = [("im1", d["im_1_local"]), ("im2", d["im_2_local"])]
        for kind in ("mc", "gd"):
            for order in S.ORDERS:
                prompt = S.mc_prompt(q, oa, ob, order)
                for slot, loc in slots:
                    ii = imginfo[loc]
                    cond = f"{kind}_img_{order}"
                    add({"request_id": rid(kind, cond, pid, loc, order), "kind": kind, "cond": cond, "modality": "image",
                         "image": ii["path"], "image_file_sha256": ii["file_sha256"], "input_pixel_sha256": ii["pixel_sha256"],
                         "image_mode": ii["mode"], "prompt": prompt, "assistant_text": None,
                         "caps": S.CAPS_MC if kind == "mc" else None},
                        {"pair": pid, "slot": slot, "order": order, "kind": kind, "cond": cond, "option": None})
                cond = f"{kind}_text_{order}"
                add({"request_id": rid(kind, cond, pid, "text", order), "kind": kind, "cond": cond, "modality": "text",
                     "image": None, "image_file_sha256": None, "input_pixel_sha256": None, "image_mode": None,
                     "prompt": prompt, "assistant_text": None, "caps": S.CAPS_MC if kind == "mc" else None},
                    {"pair": pid, "slot": "text", "order": order, "kind": kind, "cond": cond, "option": None})
        for opt, text in (("A", oa), ("B", ob)):
            for slot, loc in slots:
                ii = imginfo[loc]
                cond = "ps_img"
                add({"request_id": rid("ps", cond + opt, pid, loc, "none"), "kind": "ps", "cond": cond, "modality": "image",
                     "image": ii["path"], "image_file_sha256": ii["file_sha256"], "input_pixel_sha256": ii["pixel_sha256"],
                     "image_mode": ii["mode"], "prompt": q, "assistant_text": text, "caps": None},
                    {"pair": pid, "slot": slot, "order": "none", "kind": "ps", "cond": cond, "option": opt})
            cond = "ps_text"
            add({"request_id": rid("ps", cond + opt, pid, "text", "none"), "kind": "ps", "cond": cond, "modality": "text",
                 "image": None, "image_file_sha256": None, "input_pixel_sha256": None, "image_mode": None, "prompt": q,
                 "assistant_text": text, "caps": None},
                {"pair": pid, "slot": "text", "order": "none", "kind": "ps", "cond": cond, "option": opt})
    return rows, evalmap


def write_jsonl(path, rows):
    with open(path, "x") as f:
        for r in rows:
            f.write(json.dumps(r, sort_keys=True, ensure_ascii=False) + "\n")


def read_jsonl(path):
    return [json.loads(l) for l in open(path) if l.strip()]
