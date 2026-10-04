"""iter_069: 26개 후보 쌍의 영상 52장을 받고 manifest·contact sheet를 results/iter_069/cand 에 저장.
산출물은 새 경로 전용; 기존 파일이 있으면 공식 hash 검증 후 재사용, 아니면 실패한다."""
import json
import os
import sys

from PIL import Image, ImageDraw

import dd69_cases as C
import dd69_fetch as F


def main():
    rows = C.load_rows()
    recs = []
    for n, di, ai, lab, ev in C.CAND:
        r = rows[n]
        for kind, idx in (("DWI", di), ("ADC", ai)):
            p = r["image_%02d_path" % idx]
            rec = F.fetch_image(p)
            rec.update({"case": n, "kind": kind, "image_index": idx, "caption": r["image_%02d_caption" % idx],
                        "modality": r["image_%02d_modality" % idx]})
            recs.append(rec)
        print(n, "ok", flush=True)
    out = F.safe_dest("cand/image_manifest_cand.json")
    with open(out, "x") as f:
        json.dump({"hf_revision": F.HF_REV, "records": recs}, f, indent=1)
    # contact sheets: 한 장에 4쌍 (DWI | ADC), 캡션 제외하고 case 번호와 index만 표기
    per = 4
    by = {}
    for r in recs:
        by.setdefault(r["case"], {})[r["kind"]] = r
    cases = [x[0] for x in C.CAND]
    for s in range(0, len(cases), per):
        grp = cases[s:s + per]
        W = 420
        sheet = Image.new("RGB", (2 * W, len(grp) * (W + 24)), "white")
        d = ImageDraw.Draw(sheet)
        for k, n in enumerate(grp):
            for j, kind in enumerate(("DWI", "ADC")):
                im = Image.open(F.safe_dest(by[n][kind]["remote_path"])).convert("RGB")
                im.thumbnail((W, W))
                sheet.paste(im, (j * W, k * (W + 24) + 24))
                d.text((j * W + 4, k * (W + 24) + 4), f"case{n} {kind} idx{by[n][kind]['image_index']} {by[n][kind]['wh']}", fill="black")
        sheet.save(F.safe_dest(f"cand/sheet_{s // per:02d}.png"))
    print("sheets", (len(cases) + per - 1) // per)


if __name__ == "__main__":
    sys.exit(main())
