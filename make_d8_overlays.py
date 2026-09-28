"""iter_021: D8 환자의 R/T 렌더링 이미지에 선택된 instance ref_box/target_gt_box(및 O의 point)를
그려 실제 overlay를 만든다. 좌표 변환(native mask bbox -> resize -> pad -> normalized)이 실제
렌더링된 이미지 위에서 시각적으로 올바른 위치(척추体 부위)에 놓이는지 확인하기 위한 것이다.
D8 전체와, gate.json에서 확인된 두 방향 유형(j_sag=0/legacy x-sagittal, j_sag=2/z-sagittal, 즉
107_t2와 같은 패턴)에서 최소 1명씩을 포함해 저장한다. E/F 모델 출력은 보지 않는다(자료 자체의
좌표 정합성만 확인).
"""
import json
import os

from PIL import Image, ImageDraw

DATA_DIR = "results/iter_021/data"
OUT_DIR = "results/iter_021/overlays"


def draw_one(png_path, boxes_norm, points_norm, out_path):
    im = Image.open(png_path).convert("RGB")
    side = im.size[0]
    draw = ImageDraw.Draw(im)
    colors = ["red", "lime", "cyan", "yellow"]
    for i, (label, b) in enumerate(boxes_norm):
        y0n, x0n, y1n, x1n = b  # yxyx norm [0,1000]
        x0, y0, x1, y1 = x0n * side / 1000.0, y0n * side / 1000.0, x1n * side / 1000.0, y1n * side / 1000.0
        c = colors[i % len(colors)]
        draw.rectangle([x0, y0, x1, y1], outline=c, width=3)
        draw.text((x0 + 2, max(0, y0 - 12)), str(label), fill=c)
    for label, p in points_norm:
        yn, xn = p
        x, y = xn * side / 1000.0, yn * side / 1000.0
        draw.ellipse([x - 5, y - 5, x + 5, y + 5], outline="magenta", width=3)
    im.save(out_path)


def main():
    manifest = json.load(open(f"{DATA_DIR}/manifest.json"))
    split = json.load(open(f"{DATA_DIR}/split.json"))
    gate = {e["patient"]: e for e in json.load(open(f"{DATA_DIR}/gate.json"))["eligible"]}
    d_pids = split["D"]
    os.makedirs(OUT_DIR, exist_ok=True)
    j_sag_seen = set()
    extra_pids = []
    for pid in sorted(manifest):
        j = gate[pid]["j_sag"]
        if j not in j_sag_seen:
            j_sag_seen.add(j)
            if pid not in d_pids:
                extra_pids.append(pid)
    targets = list(d_pids) + extra_pids
    made = []
    for pid in targets:
        m = manifest[pid]
        boxes_r = [(inst["label"], inst["ref_box_norm"]) for inst in m["instances"]]
        boxes_t = [(inst["label"], inst["target_gt_norm"]) for inst in m["instances"]] + \
                  [(o["label"], o["box_norm"]) for o in m["other_gt_boxes_in_T_norm"]]
        points_t = [(inst["label"], inst["point_norm"]) for inst in m["instances"]]
        out_r = f"{OUT_DIR}/{pid}_R_overlay.png"
        out_t = f"{OUT_DIR}/{pid}_T_overlay.png"
        draw_one(m["R"]["path"], boxes_r, [], out_r)
        draw_one(m["T"]["path"], boxes_t, points_t, out_t)
        made.append({"patient": pid, "j_sag": gate[pid]["j_sag"], "R": out_r, "T": out_t,
                     "instances": [i["label"] for i in m["instances"]]})
    json.dump({"made": made, "in_D": list(d_pids), "extra_for_orientation_coverage": extra_pids},
              open(f"{OUT_DIR}/index.json", "w"), indent=1)
    print(json.dumps({"n_made": len(made), "j_sag_types_covered": sorted(j_sag_seen)}, indent=1))


if __name__ == "__main__":
    main()
