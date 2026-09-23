"""Label-free tile selectors. 이 모듈은 annotation 경로를 받지 않는다."""
import numpy as np

from .data import FINDINGS, GRID

NT = GRID * GRID
MAIN_METHODS = ["C_blur", "D_blur", "C_mean", "D_mean", "crop_conf"]


def argmax_tie_low(v):
    v = np.asarray(v, dtype=np.float64)
    mx = v.max()
    idx = np.flatnonzero(v == mx)
    return int(idx[0]), int(len(idx))


def margin_table(requests, valid, field="m"):
    """(image, finding) -> {'orig': float, 'crop'|'blur'|'mean': [9]}"""
    tab = {}
    for r in requests:
        rec = valid[r["id"]]
        d = tab.setdefault(r["image"], {}).setdefault(r["finding"], {
            "crop": [None] * NT, "blur": [None] * NT, "mean": [None] * NT})
        if r["kind"] == "orig":
            d["orig"] = rec[field]
        else:
            d[r["kind"]][r["tile"]] = rec[field]
    return tab


def removal_scores(tab_img, kind, findings=FINDINGS):
    """D[q] = m(I,q) - m(T(I,R),q), C[q] = D[q] - mean_{q'!=q} D[q'] (각 tile별)."""
    D = {q: np.array([tab_img[q]["orig"] - x for x in tab_img[q][kind]]) for q in findings}
    C = {}
    for q in findings:
        others = [D[o] for o in findings if o != q]
        C[q] = D[q] - np.mean(others, axis=0)
    return D, C


def select_all(requests, valid, field="m", findings=FINDINGS):
    tab = margin_table(requests, valid, field)
    sel, scores, ties = {}, {}, []
    for img in sorted(tab):
        Db, Cb = removal_scores(tab[img], "blur", findings)
        Dm, Cm = removal_scores(tab[img], "mean", findings)
        sel[img], scores[img] = {}, {}
        for q in findings:
            crop = np.array(tab[img][q]["crop"])
            maps = {"C_blur": Cb[q], "D_blur": Db[q], "C_mean": Cm[q], "D_mean": Dm[q], "crop_conf": crop}
            sel[img][q] = {}
            for meth, v in maps.items():
                t, n = argmax_tie_low(v)
                sel[img][q][meth] = t
                if n > 1:
                    ties.append({"image": img, "finding": q, "method": meth, "n_tied": n})
            # 다른 질문 하나를 뺀 C_blur (민감도 전용, 주결과 대체 금지)
            loqo = {}
            for drop in findings:
                if drop == q:
                    continue
                sub = [f for f in findings if f != drop]
                _, Csub = removal_scores(tab[img], "blur", sub)
                loqo[drop] = argmax_tie_low(Csub[q])[0]
            sel[img][q]["C_blur_loqo"] = loqo
            scores[img][q] = {
                "m_orig": tab[img][q]["orig"],
                "m_crop": crop.tolist(),
                "crop_mean": float(crop.mean()),
                "crop_max": float(crop.max()),
                "D_blur": Db[q].tolist(), "C_blur": Cb[q].tolist(),
                "D_mean": Dm[q].tolist(), "C_mean": Cm[q].tolist(),
            }
    return {"selection": sel, "scores": scores, "ties": ties}
