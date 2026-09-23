"""iter_006: NIH bbox 좌표 규약의 문서 근거 수집 (CPU, 네트워크 소량).

실행: python research/fetch_nih_coord_evidence.py --out research/results/iter_006/coord_evidence

- 예산: 누적 20 MiB, ledger 계상 네트워크 15분 (grounding_data/net.DownloadLedger). 전체 영상 archive는 받지 않는다.
- 각 자료의 URL, HTTP 상태, 받은 bytes, sha256을 기록하고 PDF는 pdftotext로 쪽별 text를 저장한다.
- 쪽별 keyword 줄(1024, bbox, x/y/w/h 등)을 자동 추출한다. 문서가 **명시한 내용**과 **추론**의 구분은
  `nih_coord_evidence.py`의 판정표가 이 추출 결과를 인용해 정한다 (자동으로 verified 승격하지 않는다).
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from grounding_data import net  # noqa: E402

BUDGET_BYTES = 20 * 1024 * 1024
BUDGET_SECONDS = 15 * 60
SOURCES = [
    {"key": "author_readme_mirror_pdf", "kind": "pdf",
     "url": "https://huggingface.co/datasets/roy-jarjoura/ChestXrays/resolve/main/README_CHESTXRAY.pdf?download=true",
     "role": "NIH 저자 README (HF 미러; 원배포 동일성 미확인)"},
    {"key": "wang2017_cvpr_arxiv_pdf", "kind": "pdf", "url": "https://arxiv.org/pdf/1705.02315v5",
     "role": "Wang et al. ChestX-ray8 (CVPR 2017) 원논문 arXiv 판"},
    {"key": "nih_box_official_page", "kind": "html", "url": "https://nihcc.app.box.com/v/ChestXray-NIHCC",
     "role": "NIH 공식 배포 Box 페이지 (접근 여부만 기록)"},
]
KEYWORDS = re.compile(r"1024|bbox|bounding|\bx\s*,\s*y\b|\[x|width|height|coordinat|pixel|resiz|top[- ]left|upper[- ]left",
                      re.I)


def pdf_pages(path):
    n = None
    info = subprocess.run(["pdfinfo", path], capture_output=True, text=True)
    for ln in info.stdout.splitlines():
        if ln.startswith("Pages:"):
            n = int(ln.split()[1])
    pages = []
    for p in range(1, (n or 0) + 1):
        r = subprocess.run(["pdftotext", "-layout", "-f", str(p), "-l", str(p), path, "-"],
                           capture_output=True, text=True)
        pages.append(r.stdout)
    return pages


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    ledger = net.DownloadLedger(os.path.join(args.out, "download_ledger.json"), budget_bytes=BUDGET_BYTES,
                                budget_seconds=BUDGET_SECONDS)
    t0 = time.time()
    recs = {}
    for s in SOURCES:
        rec = {**s, "fetched_at": time.strftime("%Y-%m-%d %H:%M:%S")}
        local = os.path.join(args.out, s["key"] + (".pdf" if s["kind"] == "pdf" else ".html"))
        try:
            if os.path.exists(local) and os.path.getsize(local) > 0:
                body, rec["fetch"] = open(local, "rb").read(), "cached"
            else:
                body = ledger.get(s["url"], s["key"])
                rec["fetch"] = "downloaded"
                with open(local, "wb") as f:
                    f.write(body)
            rec.update({"ok": True, "bytes": len(body), "sha256": net.sha256_bytes(body), "local": local})
            if s["kind"] == "pdf":
                if not body.startswith(b"%PDF"):
                    rec.update({"ok": False, "error": "not_a_pdf"})
                else:
                    pages = pdf_pages(local)
                    rec["n_pages"] = len(pages)
                    rec["keyword_lines"] = []
                    for i, txt in enumerate(pages, start=1):
                        with open(os.path.join(args.out, f"{s['key']}_p{i:02d}.txt"), "w") as f:
                            f.write(txt)
                        for ln in txt.splitlines():
                            if KEYWORDS.search(ln):
                                rec["keyword_lines"].append({"page": i, "line": " ".join(ln.split())[:300]})
            else:
                txt = body.decode("utf-8", "replace")
                rec["html_title"] = (re.search(r"<title>(.*?)</title>", txt, re.S | re.I) or [None, None])[1]
                rec["html_mentions_1024"] = "1024" in txt
                rec["note"] = "JS 렌더링 페이지일 수 있어 본문 부재가 자료 부재를 뜻하지 않음"
        except Exception as e:  # 접근 실패는 기록만 한다
            rec.update({"ok": False, "error": repr(e)[:300]})
        recs[s["key"]] = rec
    summary = {"sources": recs, "ledger_bytes_total": ledger.data["bytes_total"],
               "ledger_network_seconds": ledger.data["seconds_total"], "ledger_n_requests": ledger.data["n_requests"],
               "wall_seconds": time.time() - t0, "budget_bytes": BUDGET_BYTES, "budget_seconds": BUDGET_SECONDS,
               "network_accounting_note": "ledger 수치는 이 스크립트의 GET 본문만 계상한다. DNS·TLS·header와 "
                                          "다른 도구의 조회는 포함하지 않는다."}
    with open(os.path.join(args.out, "fetch_summary.json"), "w") as f:
        json.dump(summary, f, indent=1, ensure_ascii=False)
    for k, r in recs.items():
        print(k, r.get("ok"), r.get("bytes"), r.get("n_pages"), r.get("error"))


if __name__ == "__main__":
    main()
