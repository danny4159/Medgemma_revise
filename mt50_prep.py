"""iter_050 자료 gate 1단계: 원본 재검증 + 감사용 contact sheet/텍스트 생성 (CPU).

- train.jsonl sha, 영상 896개 file sha/size(iter_049 manifest 대조), symlink/경로 이탈, alpha 검사, pixel hash 재현.
- case별 contact sheet(원본 순서 번호 표시)와 감사용 텍스트를 results/iter_050/audit/ 에 새로 만든다.
"""
import json
import os
import sys

from PIL import Image, ImageDraw

import mt50_common as C

TILE = 384
COLS = 4


def main():
    out = os.path.join(C.OUT, "audit")
    os.makedirs(os.path.join(out, "sheets"), exist_ok=True)
    tp = os.path.join(C.R49, "raw", "train.jsonl")
    assert C.file_sha(tp) == C.TRAIN_SHA, "train sha mismatch"
    cases = C.read_jsonl(os.path.join(C.R49, "audit_v2", "eligible_cases.jsonl"))
    man = json.load(open(os.path.join(C.R49, "image_manifest.json")))
    by_path = {r["path"]: r for r in man["records"]}
    assert len(by_path) == 896 and man["hf_revision"] == C.HF_REVISION
    rows, bad = [], []
    for c in cases:
        ims = []
        for i, im in enumerate(c["images"]):
            rec = by_path[im["path"]]
            p = C.safe_image_path(im["path"])
            if os.path.getsize(p) != rec["size"] or C.file_sha(p) != rec["file_sha256"]:
                bad.append(im["path"])
            rgb, info = C.load_rgb(im["path"])
            if info["native_pixel_sha256"] != rec["pixel_sha256"]:
                bad.append("pixel:" + im["path"])
            rows.append({"case_key": c["case_key"], "index": i, "path": im["path"], "id": im["id"],
                         "file_sha256": rec["file_sha256"], **info})
            ims.append(rgb)
        n = len(ims)
        cols = min(COLS, n)
        rws = (n + cols - 1) // cols
        sheet = Image.new("RGB", (cols * TILE, rws * TILE), (40, 40, 40))
        d = ImageDraw.Draw(sheet)
        for i, rgb in enumerate(ims):
            t = rgb.resize((TILE, TILE), Image.LANCZOS)
            x, y = (i % cols) * TILE, (i // cols) * TILE
            sheet.paste(t, (x, y))
            d.rectangle([x, y, x + 22, y + 16], fill=(255, 255, 0))
            d.text((x + 4, y + 2), str(i), fill=(0, 0, 0))
        sp = os.path.join(out, "sheets", c["case_key"].replace("Case number ", "c") + ".png")
        if not os.path.exists(sp):
            sheet.save(sp)
    with open(os.path.join(out, "regression_source_check_v2.json"), "x") as f:
        json.dump({"train_sha256": C.TRAIN_SHA, "n_cases": len(cases), "n_images": len(rows), "bad": bad,
                   "alpha_min_values": sorted({r["alpha_min"] for r in rows if r["alpha_min"] is not None}),
                   "modes": {m: sum(1 for r in rows if r["mode"] == m) for m in {r["mode"] for r in rows}}},
                  f, indent=1)
    with open(os.path.join(out, "image_rows_verified_v2.jsonl"), "x") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    # 감사용 텍스트 (정답 포함: 감사 전용, 추론 worker는 읽지 않는다)
    if not os.path.exists(os.path.join(out, "case_text_for_audit.md")):
      with open(os.path.join(out, "case_text_for_audit.md"), "x") as f:
        for c in cases:
            f.write("## %s | n_img=%d | %s\n" % (c["case_key"], len(c["images"]), ",".join(c["_audit"]["sub_modalities"])))
            f.write("HISTORY: %s\n" % c["CLINICAL_HISTORY"])
            for k in C.LETTERS:
                f.write("  %s%s %s\n" % ("*" if k == c["_eval"]["correct_answer"] else " ", k, c["options"][k]))
            f.write("\n")
    print("images", len(rows), "bad", bad)


if __name__ == "__main__":
    main()
