"""실제 V96 사례의 공식 GT로 독립/공동 질문을 설명한다. 예측·실험 실행 없음.

데이터 이용 조건을 따르는 로컬 열람용 그림이며 자동 배포하지 않는다.
실행: /home/milab/anaconda3/bin/python plot_padchest_ab_example.py
기존 matplotlib 설치 환경을 그림에만 사용하며 연구 환경은 변경하지 않는다.
"""
from pathlib import Path
import hashlib
import json

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import Rectangle
import numpy as np
from PIL import Image


ROOT = Path(__file__).resolve().parent
RESEARCH = ROOT / "research"
MANIFEST = RESEARCH / "results/iter_040/data/manifest_eval_private.jsonl"
SENTENCES = {
    "qA": "Enlargement of the cardiac silhouette.",
    "qB": "Bilateral apical pleural thickening.",
}
COLORS = {"qA": "#00d5ef", "qB": "#ffb52e"}


def main():
    rows = [json.loads(line) for line in MANIFEST.read_text().splitlines()]
    candidates = [r for r in rows if r.get("eval_set") == "V96" and r["sentences"] == SENTENCES]
    assert len(candidates) == 1, "설명용 V96 사례를 유일하게 찾지 못함"
    row = candidates[0]
    arr = np.asarray(Image.open(RESEARCH / row["image_meta"]["path"]))
    assert arr.dtype == np.uint8 and arr.ndim == 2
    assert hashlib.sha256(arr.tobytes()).hexdigest() == row["image_meta"]["u8_pixel_sha256"]
    h, w = arr.shape
    assert (h, w) == (row["image_meta"]["h"], row["image_meta"]["w"])
    top, left, side = row["pad_top_left_side"]
    assert (top, left, side) == ((max(h, w)-h)//2, (max(h, w)-w)//2, max(h, w))
    canvas = np.zeros((side, side), dtype=np.uint8)
    canvas[top:top+h, left:left+w] = arr
    boxes = row["gt_boxes_xyxy_norm"]
    assert len(boxes["qA"]) == 1 and len(boxes["qB"]) == 2
    for group in boxes.values():
        for x0, y0, x1, y1 in group:
            assert 0 <= x0 < x1 <= 1 and 0 <= y0 < y1 <= 1

    font_path = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
    font_manager.fontManager.addfont(font_path)
    plt.rcParams.update({"font.family": font_manager.FontProperties(fname=font_path).get_name(),
                         "font.size": 12, "axes.unicode_minus": False, "pdf.fonttype": 42})
    fig = plt.figure(figsize=(16, 9), facecolor="#f5f7fb")
    fig.text(.045, .946, "같은 X-ray, 같은 소견 — 따로 묻기 vs 함께 묻기", fontsize=24, weight="bold", color="#172338")
    fig.text(.045, .903, "PadChest-GR 실제 V96 사례  |  색 박스 = 데이터셋의 정답(GT), 모델 예측 아님", fontsize=13, color="#536277")
    fig.text(.045, .854, "A  심장 음영 확대  ·  정답 박스 1개", fontsize=16, color="#007b98", weight="bold")
    fig.text(.52, .854, "B  양측 폐첨부 흉막 비후  ·  정답 박스 2개", fontsize=16, color="#a36500", weight="bold")
    fig.text(.045, .819, SENTENCES["qA"], fontsize=12, color="#536277")
    fig.text(.52, .819, SENTENCES["qB"], fontsize=12, color="#536277")

    panels = [
        (.045, ("qA",), "독립 요청 1  |  A만 질문", '“A 문장이 설명하는 위치를 찾아라.”'),
        (.36, ("qB",), "독립 요청 2  |  B만 질문", '“B 문장이 설명하는 위치를 찾아라.”'),
        (.675, ("qA", "qB"), "공동 요청 1회  |  A + B 질문", '“A와 B의 위치를 각각 구분해 찾아라.”'),
    ]
    for x, targets, title, question in panels:
        ax = fig.add_axes([x, .255, .28, .50])
        ax.imshow(canvas, cmap="gray", vmin=0, vmax=255)
        ax.set_axis_off()
        ax.set_title(title, fontsize=15, pad=13, color="#172338", weight="bold")
        for target in targets:
            for i, (x0, y0, x1, y1) in enumerate(boxes[target], 1):
                px, py = x0*w + left, y0*h + top
                ax.add_patch(Rectangle((px, py), (x1-x0)*w, (y1-y0)*h,
                                       fill=False, edgecolor=COLORS[target], linewidth=2.5))
                ax.text(px + side*.006, py + side*.006, f"{target[-1]}{i}",
                        ha="left", va="top", fontsize=12, weight="bold", color="#102030",
                        bbox={"facecolor": COLORS[target], "edgecolor": "none", "pad": 2})
        fig.text(x+.14, .23, question, ha="center", fontsize=12, color="#172338")
    fig.text(.045, .16, "질문에는 영상 + 문장만 제공하고, 위 정답 박스는 보여주지 않습니다.", fontsize=15, weight="bold", color="#172338")
    fig.text(.045, .116, "평가: 문장별 예측 박스 ↔ 해당 문장의 GT  →  IoU ≥ 0.3 일대일 매칭  →  F1 계산", fontsize=13, color="#536277")
    fig.text(.045, .077, "핵심: A·B는 소견 문장의 ID입니다. 한 문장에도 여러 박스가 있으며, 공동 질문에서도 문장–박스 대응을 유지해야 합니다.", fontsize=12, color="#536277")
    fig.text(.045, .035, "설명용 사례이며 성능 저하를 증명하는 예측 비교가 아닙니다. 질문은 실제 영어 프롬프트를 한국어로 요약했습니다.  |  로컬 연구 열람용", fontsize=10, color="#738094")
    for suffix in ("png", "pdf"):
        target = ROOT / f"padchest_ab_example.{suffix}"
        fig.savefig(target, dpi=190, facecolor=fig.get_facecolor())
        print(target)
    plt.close(fig)


if __name__ == "__main__":
    main()
