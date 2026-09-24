"""GT/예측 bbox overlay (좌표축 눈금·테두리 포함). 좌표 연결 검사와 사례 검토용."""
from PIL import Image, ImageDraw


def draw(img_path, gt_boxes=(), pred_boxes=(), size=512, title=""):
    """gt/pred boxes: [y0,x0,y1,x1] in 0-1000 (padding canvas). GT=초록, 예측=빨강."""
    im = Image.open(img_path).convert("RGB").resize((size, size))
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, size - 1, size - 1], outline=(255, 255, 0), width=2)
    for t in range(0, 1001, 100):
        p = t * size / 1000
        d.line([(p, 0), (p, 8)], fill=(255, 255, 0))
        d.line([(0, p), (8, p)], fill=(255, 255, 0))
        d.text((p + 2, 9), str(t), fill=(255, 255, 0))
        d.text((10, p), str(t), fill=(255, 255, 0))
    for b, col in [(g, (0, 255, 0)) for g in gt_boxes] + [(p, (255, 60, 60)) for p in pred_boxes]:
        y0, x0, y1, x1 = [v * size / 1000 for v in b]
        d.rectangle([x0, y0, x1, y1], outline=col, width=2)
    if title:
        d.text((size // 2 - 60, size - 14), title, fill=(255, 255, 255))
    return im


def montage(images, cols=4):
    w, h = images[0].size
    rows = (len(images) + cols - 1) // cols
    out = Image.new("RGB", (w * cols, h * rows))
    for i, im in enumerate(images):
        out.paste(im, ((i % cols) * w, (i // cols) * h))
    return out
