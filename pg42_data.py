"""iter_042 후보 열거·적격성 (CPU only, 모델 출력 미사용). pg39_data의 loader만 재사용하고 적격성 함수는 별도다.

- 음성: 원본 abnormal=false 문장에서 현재 영상의 pleural effusion 부재가 명시된 경우만 (regex는 후보 열거용, 최종 판단은 눈가림 검토 기록 review_private.json).
- 양성: effusion 관련 모든 abnormal 문장이 labels==['pleural effusion'] + 유효 boxes + progression None + 시간 비교 문구 없음.
- 환자당 한 영상은 sha256('iter042-v1|'+PatientID+'|'+ImageID) 최소 순. 결과 기반 교체 금지.
"""
import hashlib
import json
import re

import pg39_data as D

SEL_TAG = "iter042-v1"
TARGET = "pleural effusion"
EFF_RE = re.compile(r"effusion|pleural fluid", re.I)
NEG_MENTION_RE = re.compile(r"effusion", re.I)
EXCLUDE_MANIFESTS = ["results/iter_039/data/manifest_private.jsonl", "results/iter_040/data/manifest_train_private.jsonl",
                     "results/iter_040/data/manifest_eval_private.jsonl"]


def sel_hash(patient, image):
    return hashlib.sha256(f"{SEL_TAG}|{patient}|{image}".encode()).hexdigest()


def load_excluded():
    pats, studies, images = set(), set(), set()
    for p in EXCLUDE_MANIFESTS:
        for ln in open(p):
            d = json.loads(ln)
            pats.add(d["PatientID"])
            studies.add(d["StudyID"])
            images.add(d["ImageID"])
    return pats, studies, images


def neg_sentences(r):
    """영상의 abnormal=false 문장 중 effusion을 언급한 것들의 (index, en, es)."""
    return [(i, f["sentence_en"], f.get("sentence_es")) for i, f in enumerate(r["findings"])
            if f.get("abnormal") is False and NEG_MENTION_RE.search(f["sentence_en"])]


def pos_target(r):
    """양성 판정. returns (ok, reason, target_finding_indices, merged_boxes)."""
    rel = [i for i, f in enumerate(r["findings"])
           if f.get("abnormal") is True and (EFF_RE.search(f["sentence_en"]) or any(EFF_RE.search(l) for l in f.get("labels", [])))]
    tgt = [i for i in rel if TARGET in r["findings"][i].get("labels", [])]
    if not tgt:
        return False, "no_target_label", [], []
    for i in rel:
        f = r["findings"][i]
        if f["labels"] != [TARGET]:
            return False, "mixed_or_other_effusion_label", tgt, []
        if not f["boxes"] or not all(D.valid_box(b) for b in f["boxes"]):
            return False, "no_or_invalid_box", tgt, []
        if f.get("progression") is not None:
            return False, "progression_field", tgt, []
        if D.TEMPORAL_RE.search(f["sentence_en"]):
            return False, "temporal_phrase", tgt, []
    boxes, seen = [], set()
    for i in tgt:
        for b in r["findings"][i]["boxes"]:
            k = tuple(b)
            if k not in seen:
                seen.add(k)
                boxes.append(list(b))
    return True, "", tgt, boxes


def enumerate_candidates(reports, links, restrict_patients=None, exclude=None):
    """split=='train' 영상의 음성/양성 후보 (영상 단위). exclude=(pats,studies,images)이면 제외, restrict_patients면 그 환자만."""
    out = {"neg": [], "pos": []}
    for r in reports:
        iid = r["ImageID"]
        if links["img2split"][iid] != "train":
            continue
        pid = links["img2patient"][iid]
        if restrict_patients is not None and pid not in restrict_patients:
            continue
        if exclude is not None and (pid in exclude[0] or r["StudyID"] in exclude[1] or iid in exclude[2]):
            continue
        ns = neg_sentences(r)
        ok, why, tgt, boxes = pos_target(r)
        base = {"PatientID": pid, "ImageID": iid, "StudyID": r["StudyID"]}
        if ns:
            out["neg"].append({**base, "neg_sentences": ns,
                               "other_findings": [(i, f["abnormal"], f["sentence_en"]) for i, f in enumerate(r["findings"])]})
        if ok:
            out["pos"].append({**base, "target_idx": tgt, "boxes": boxes,
                               "target_sentences": [r["findings"][i]["sentence_en"] for i in tgt],
                               "other_findings": [(i, f["abnormal"], f["sentence_en"]) for i, f in enumerate(r["findings"])]})
    return out
