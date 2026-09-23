"""SCR (Segmentation in Chest Radiographs, JSRT 영상 기반) archive 검사.

영상·mask 파일명, 실제 해상도, mask 형식, organ별 대응률을 보고한다. subject 관계의 근거가 없으므로
case-disjoint만 확인된 것으로 둔다. 결절 위치(JSRT metadata)는 이 archive에 없으면 연결하지 않는다.
"""
import io
import re
import zipfile

import numpy as np
from PIL import Image

ZENODO_RECORD = "7056076"
CASE_RE = re.compile(r"(JPC[LN]N\d{3})")


def case_id(name):
    m = CASE_RE.search(name)
    return m.group(1) if m else None


def inspect_images(zbytes):
    zf = zipfile.ZipFile(io.BytesIO(zbytes))
    out, problems = {}, []
    for zi in zf.infolist():
        if zi.is_dir():
            continue
        cid = case_id(zi.filename)
        if cid is None:
            problems.append({"member": zi.filename, "what": "no_case_id"})
            continue
        data = zf.read(zi)
        try:
            im = Image.open(io.BytesIO(data))
            im.load()
        except Exception as e:
            problems.append({"member": zi.filename, "what": "decode_error", "error": repr(e)[:200]})
            continue
        a = np.asarray(im)
        if cid in out:
            problems.append({"member": zi.filename, "what": "duplicate_case"})
        out[cid] = {"member": zi.filename, "size": list(im.size), "mode": im.mode, "format": im.format,
                    "bytes": len(data), "dtype": str(a.dtype), "min": int(a.min()), "max": int(a.max()),
                    "array": a}
    return out, problems


def inspect_masks(zbytes):
    """organ은 mask 경로의 상위 디렉터리 이름(또는 파일명 접미사)에서 읽는다."""
    zf = zipfile.ZipFile(io.BytesIO(zbytes))
    out, problems, organs = {}, [], set()
    for zi in zf.infolist():
        if zi.is_dir():
            continue
        cid = case_id(zi.filename)
        if cid is None:
            problems.append({"member": zi.filename, "what": "no_case_id"})
            continue
        parts = zi.filename.split("/")
        organ = parts[-2] if len(parts) >= 2 else None
        if organ is None:
            problems.append({"member": zi.filename, "what": "no_organ_dir"})
            continue
        organs.add(organ)
        data = zf.read(zi)
        try:
            im = Image.open(io.BytesIO(data))
            im.load()
        except Exception as e:
            problems.append({"member": zi.filename, "what": "decode_error", "error": repr(e)[:200]})
            continue
        a = np.asarray(im)
        vals = np.unique(a)
        key = (cid, organ)
        if key in out:
            problems.append({"member": zi.filename, "what": "duplicate_case_organ"})
        out[key] = {"member": zi.filename, "size": list(im.size), "mode": im.mode, "format": im.format,
                    "bytes": len(data), "unique_values": vals[:10].tolist(), "n_unique": int(len(vals)),
                    "array": a}
    return out, problems, sorted(organs)


def burned_contour_score(img, mask, shift=12, thr_hi=235, thr_lo=20):
    """영상에 annotation 윤곽선이 그려져 있는지 검사.

    mask를 영상 크기로 nearest 축소한 뒤 경계 pixel을 구하고, 각 경계 pixel의 3x3 이웃에 극값(>=thr_hi와
    <=thr_lo가 모두) 있는 비율을 잰다. 기준선은 같은 경계를 x로 shift pixel 이동한 위치의 비율이다.
    윤곽선이 그려진 영상이면 경계 비율이 기준선보다 크게 높다.
    """
    g = np.asarray(Image.fromarray(img).convert("L"), dtype=np.int32)
    H, W = g.shape
    m = np.asarray(Image.fromarray((np.asarray(mask) > 0).astype(np.uint8) * 255).resize((W, H), Image.NEAREST)) > 0
    inner = m.copy()
    inner[1:-1, 1:-1] = m[1:-1, 1:-1] & m[:-2, 1:-1] & m[2:, 1:-1] & m[1:-1, :-2] & m[1:-1, 2:]
    edge = m & ~inner
    pad_hi = np.pad(g >= thr_hi, 1)
    pad_lo = np.pad(g <= thr_lo, 1)
    nb_hi = np.zeros_like(g, dtype=bool)
    nb_lo = np.zeros_like(g, dtype=bool)
    for dy in range(3):
        for dx in range(3):
            nb_hi |= pad_hi[dy:dy + H, dx:dx + W]
            nb_lo |= pad_lo[dy:dy + H, dx:dx + W]
    both = nb_hi & nb_lo
    ys, xs = np.nonzero(edge)
    if len(ys) == 0:
        return None
    on = float(both[ys, xs].mean())
    xs2 = np.clip(xs + shift, 0, W - 1)
    off = float(both[ys, xs2].mean())
    return {"edge_hit_rate": on, "shifted_hit_rate": off, "n_edge_px": int(len(ys))}


def binarize(a):
    """mask를 {0,1}로. 값이 정확히 두 종류(0과 양수)일 때만 허용하고, 그 외에는 오류로 둔다."""
    vals = np.unique(a)
    if a.ndim != 2:
        raise ValueError(f"mask ndim {a.ndim}")
    if len(vals) > 2 or vals.min() != 0:
        raise ValueError(f"mask not binary: {vals[:10]}")
    return (a > 0).astype(np.float64)
