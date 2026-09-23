"""NIH bbox 좌표 canvas의 문서 근거 판정 (iter_006).

`fetch_nih_coord_evidence.py`가 저장한 쪽별 text에서 인용문이 실제로 있는지 코드로 확인한 뒤,
문서가 **명시한 내용(documented)**과 **추론(inferred)**을 분리한다.

판정 규칙
- `documented_direct`: bbox 좌표가 1024×1024 배포 PNG pixel 좌표라고 직접 말하는 문장이 있을 때만.
- `assumed`: 영상 해상도(1024)와 xywh 의미는 문서화되어 있지만 둘을 잇는 문장이 없을 때.
  영상 크기·좌표 범위·육안 overlay는 이 판정을 올리지 않는다.
- `undocumented`: 해상도나 xywh 의미 중 하나라도 인용을 확인하지 못했을 때.
"""
import json
import os
import re

# (key, source, pdf page(1-based), 인용문, tag). 인용문은 공백 정규화 후 부분 문자열로 찾는다.
CLAIMS = [
    ("readme_png_1024", "author_readme_mirror_pdf", 1,
     "112,120 frontal-view chest X-ray PNG images in 1024*1024 resolution", "image_resolution_1024"),
    ("readme_bbox_xywh", "author_readme_mirror_pdf", 2,
     "Bbox[x, y, w, h]. [x y] are coordinates of each box's topleft corner. [w h] represent the width and "
     "height of each box.", "xywh_semantics"),
    ("paper_resized_1024", "wang2017_cvpr_arxiv_pdf", 4,
     "resized as 1024×1024 bitmap images", "image_resolution_1024"),
    ("paper_eval_dims_1024", "wang2017_cvpr_arxiv_pdf", 8,
     "in contrast to the original image dimensions (1024 × 1024), the computed B-Boxes are often larger than the "
     "according GT B-Boxes", "gt_comparison_frame_1024_indirect"),
    ("paper_983_images_1600_boxes", "wang2017_cvpr_arxiv_pdf", 7,
     "for the 983 images with 1,600 annotated B-Boxes of pathologies", "annotation_count_paper"),
]
DIRECT_CANVAS_TAG = "bbox_canvas_direct"  # 현재 CLAIMS에는 없다: 찾지 못한 근거를 만들어 넣지 않는다

INFERENCES = [
    {"claim": "BBox_List_2017.csv의 x,y,w,h는 배포 1024×1024 PNG의 pixel 좌표다",
     "basis": ["readme_png_1024", "readme_bbox_xywh", "paper_resized_1024", "paper_eval_dims_1024"],
     "status": "inferred (문서 간 연결; 직접 명시 없음)",
     "supporting_observation": "전체 bbox 좌표 최대 x1=1012.1, y1=1022.0 (1024 이내). 관찰은 가정과 모순되지 않을 뿐 증명이 아님."},
    {"claim": "paper_eval_dims_1024 문장은 GT B-Box를 1024 영상 좌표로 비교했음을 시사한다",
     "basis": ["paper_eval_dims_1024"],
     "status": "inferred (heatmap 해상도 설명 문맥; GT 좌표계를 정의하는 문장 아님)"},
]


def _norm(s):
    return " ".join(s.replace(" ", " ").split())


def page_text(evidence_dir, source, page):
    p = os.path.join(evidence_dir, f"{source}_p{page:02d}.txt")
    if not os.path.exists(p):
        return None
    return open(p, encoding="utf-8", errors="replace").read()


def _raw_text(evidence_dir, source, page):
    """layout text의 두 단 섞임을 피하려고 pdftotext 기본 모드로 해당 쪽을 다시 추출한다."""
    import subprocess
    pdf = os.path.join(evidence_dir, f"{source}.pdf")
    if not os.path.exists(pdf):
        return None
    r = subprocess.run(["pdftotext", "-f", str(page), "-l", str(page), pdf, "-"], capture_output=True, text=True)
    return r.stdout


def box_listing(evidence_dir):
    """공식 Box 폴더 HTML의 파일 목록(name, itemSize, contentUpdated). 접근 실패면 None."""
    import datetime
    p = os.path.join(evidence_dir, "nih_box_official_page.html")
    if not os.path.exists(p):
        return None
    t = open(p, encoding="utf-8", errors="replace").read()
    out = {}
    for m in re.finditer(r'"name":"([^"]+)","itemSize":(\d+),.{0,200}?"contentUpdated":(\d+)', t):
        out[m.group(1)] = {"itemSize": int(m.group(2)),
                           "contentUpdated_utc": datetime.datetime.fromtimestamp(
                               int(m.group(3)), datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")}
    return out


def judge(evidence_dir, mirror_sizes=None):
    summ = json.load(open(os.path.join(evidence_dir, "fetch_summary.json")))
    claims = []
    for key, src, page, quote, tag in CLAIMS:
        s = summ["sources"].get(src, {})
        found = False
        for txt in (page_text(evidence_dir, src, page), _raw_text(evidence_dir, src, page)):
            if txt is not None and _norm(quote) in _norm(txt):
                found = True
                break
        claims.append({"key": key, "source": src, "url": s.get("url"), "sha256": s.get("sha256"),
                       "page": page, "quote": quote, "tag": tag, "quote_found_in_page": found,
                       "type": "documented" if found else "not_found"})
    tags = {c["tag"] for c in claims if c["quote_found_in_page"]}
    if DIRECT_CANVAS_TAG in tags:
        status = "documented_direct"
    elif {"image_resolution_1024", "xywh_semantics"} <= tags:
        status = "assumed"
    else:
        status = "undocumented"
    listing = box_listing(evidence_dir)
    prov = None
    if listing is not None and mirror_sizes:
        prov = {}
        for name, size in mirror_sizes.items():
            off = listing.get(name)
            prov[name] = {"mirror_bytes": size, "official_box_itemSize": off["itemSize"] if off else None,
                          "official_contentUpdated_utc": off["contentUpdated_utc"] if off else None,
                          "size_equal": (off is not None and off["itemSize"] == size),
                          "identity": "unverified (크기 일치는 동일성의 증거가 아님; Box 목록에 hash 없음)"}
    return {"coordinate_canvas_status": status,
            "direct_canvas_statement_found": DIRECT_CANVAS_TAG in tags,
            "claims": claims, "inferences": INFERENCES,
            "official_box_page": {"url": summ["sources"].get("nih_box_official_page", {}).get("url"),
                                  "fetched": summ["sources"].get("nih_box_official_page", {}).get("ok"),
                                  "n_listed_items": len(listing) if listing else 0,
                                  "note": "폴더 목록 JSON만 확인. 파일 본문은 받지 않음(공식 README 본문 미확인)."},
            "mirror_vs_official_listing": prov,
            "network": {k: summ[k] for k in ("ledger_bytes_total", "ledger_network_seconds", "ledger_n_requests",
                                             "wall_seconds", "network_accounting_note")}}
