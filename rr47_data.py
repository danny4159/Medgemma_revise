"""iter_047 자료: pinned PadChest-GR metadata에서 명시적 존재/부재 문장을 고정 규칙으로 분류한다 (CPU only, 모델 미사용).

pg39_data의 pinned hash·연결 검사를 그대로 쓴다. 규칙 분류(rule)와 사람이 읽는 의미 검토(review)는 분리해 private 표로 남긴다.
원칙: 일반적인 정상·무소견, bbox 부재, 다른 질환의 부재에서 target 음성을 추론하지 않는다. 시간 비교·hedge·한정된 부정·다중 소견 문장·상충 annotation은 제외한다.
"""
import re
from collections import Counter, defaultdict

import pg39_data as D
import rr47_spec as S

# ---- 양성 문장: 단일 canonical finding만 명시, 부정/hedge/한정 없음 ----
POS_RE = {
    "cardiomegaly": r"\bcardiomegaly\b|increase in (the )?cardiac silhouette|enlargement of (the )?cardiac silhouette|increased cardiac silhouette|"
                    r"increased cardiothoracic (index|ratio)|enlarged cardiac silhouette",
    "effusion": r"pleural effusion",
    "consolidation": r"consolidation",
    "pneumothorax": r"pneumothorax",
    "nodule": r"\bnodule\b",
    "atelectasis": r"atelectasis",
    "scoliosis": r"scoliosis",
    "aortic_elongation": r"aortic elongation|elongation of (the )?(thoracic )?aorta|elongated aorta",
    "pacemaker": r"pacemaker",
}
POS_LABELS = {
    "cardiomegaly": ["cardiomegaly"], "effusion": ["pleural effusion"], "consolidation": ["consolidation"], "pneumothorax": ["pneumothorax"],
    "nodule": ["nodule"], "atelectasis": ["atelectasis", "laminar atelectasis", "lobar atelectasis", "segmental atelectasis"],
    "scoliosis": ["scoliosis"], "aortic_elongation": ["aortic elongation"], "pacemaker": ["pacemaker"],
}
# ---- 부정 문장 (cardiomegaly는 사전에 열거한 정상 문구, 나머지는 단일 소견의 명시적 부정) ----
NEG_CORE = r"(?:\bno\b|\bnot\b|without|absence of|\bfree of\b)"
NEG_RE = {
    "cardiomegaly": r"^(?:normal|conserved) cardiothoracic (?:index|ratio)\.?$|^cardiothoracic (?:index|ratio) (?:is )?(?:within normal limits|normal)\.?$|"
                    r"^(?:the )?(?:cardiac silhouette|heart size) (?:is )?(?:within normal limits|normal)\.?$|^mediastinum and cardiac silhouette within normal limits\.?$|^normal (?:cardiac silhouette|heart size)\.?$",
    "effusion": r"pleural effusion", "consolidation": r"consolidation", "pneumothorax": r"pneumothorax", "nodule": r"\bnodules?\b",
    "atelectasis": r"atelectasis", "scoliosis": r"scoliosis", "aortic_elongation": r"aortic elongation", "pacemaker": r"pacemaker",
}
TEMP2 = re.compile(r"\bknown\b|already|resolution|\bless\b|\bmore\b|residual|described|satellite|cited|/|further study", re.I)
ITEM_FIND = [("consolidation", r"(?:areas? of )?(?:lung parenchyma )?consolidations?"), ("nodule", r"(?:pulmonary |lung )?nodules?"),
             ("effusion", r"(?:pleural )?effusions?"), ("pneumothorax", r"pneumothorax"), ("atelectasis", r"atelectasis")]
ITEM_OTHER = r"masses|infiltrates?|pleural thickening|thickening"
_ITEM = "(?:" + "|".join([p for _, p in ITEM_FIND] + [ITEM_OTHER]) + ")"
NEG_LIST_RE = re.compile(r"^(?:(?:lungs and pleura|lungs|chest): )?(?:there is |there are )?no (?:evidence of )?(" + _ITEM + r"(?:, " + _ITEM + r")*(?:,? (?:or|and) " + _ITEM +
                         r")?)(?: in the (?:lung )?parenchyma)?(?: (?:is|are) (?:appreciated|observed|seen|visualized|identified))?\.?$", re.I)
HEDGE = re.compile(r"probabl|possibl|could|suspic|suspect|suggest|compatible|rule out|rule-out|cannot|can't|likely|questionable|doubt|\bmay\b|\bmight\b|"
                   r"relat|associat|attribut|consistent|resembl|appear|\bvs\b|differential|versus|\bor\b|\band\b|limit|border|upper|high end|"
                   r"normal|equivocal|uncertain|unclear|tend|mild to|diagnostic impression|\bAP\b", re.I)
QUALIFIED_NEG = re.compile(r"significant|relevant|important|substantial|major|large|massive|remarkable|obvious|clear|\bother\b|evident|"
                           r"prior|previous|\bnew\b|since|chest ct|described|current study|\bor\b|\band\b|,|:|signs?|suggest", re.I)
SPEC_NEG_OK = {  # 음성 문장 허용 구문(고정): 앞부분 부정 + target 어구
    "effusion": re.compile(r"^(?:there is |there are )?(?:no|without) (?:evidence of |sign of )?(?:pleural )?effusions?(?: (?:is|are) (?:appreciated|observed|seen|visualized|identified))?\.?$|"
                           r"^(?:i do not|we do not) (?:appreciate|identify|see|observe) (?:a )?(?:pleural )?effusion\.?$|"
                           r"^no pleural effusion(?: (?:is|are) (?:appreciated|observed|seen|visualized|identified))?\.?$", re.I),
    "consolidation": re.compile(r"^(?:there is |there are )?no (?:evidence of |areas? of )?consolidations?(?: (?:is|are) (?:appreciated|observed|seen|visualized|identified))?\.?$", re.I),
    "pneumothorax": re.compile(r"^(?:there is |there are )?no (?:evidence of |sign of |signs of )?pneumothorax(?: (?:is|are) (?:appreciated|observed|seen|visualized|identified))?\.?$|"
                               r"^(?:i do not|we do not) (?:appreciate|identify|see|observe|evidence) (?:signs? of )?pneumothorax\.?$", re.I),
    "nodule": re.compile(r"^(?:there is |there are )?no (?:pulmonary |lung )?nodules?(?: (?:is|are) (?:appreciated|observed|seen|visualized|identified))?\.?$|"
                         r"^(?:i do not|we do not) (?:appreciate|identify|see|observe) (?:pulmonary |lung )?nodules?\.?$", re.I),
    "atelectasis": re.compile(r"^(?:there is |there are )?no (?:evidence of )?atelectasis(?: (?:is|are) (?:appreciated|observed|seen|visualized|identified))?\.?$", re.I),
    "scoliosis": re.compile(r"^(?:there is |there are )?no (?:evidence of )?scoliosis(?: (?:is|are) (?:appreciated|observed|seen|visualized|identified))?\.?$", re.I),
    "aortic_elongation": re.compile(r"^(?:there is |there are )?no (?:evidence of )?aortic elongation\.?$", re.I),
    "pacemaker": re.compile(r"^(?:there is |there are )?no pacemaker\.?$", re.I),
}
# ---- 같은 영상에서 target 소견과 연관된 모든 문장·label (상충/모호 annotation 검출용) ----
BROAD = {  # target 소견에 대한 '주장'을 담을 수 있는 어휘. 이 어휘가 있는 문장이 명확한 지지 문장이 아니면 그 영상의 해당 소견은 모호로 제외한다.
    "cardiomegaly": r"cardiomeg|cardiothoracic|cardiac (?:silhouette|size|enlarg)|heart size|enlarged heart|cardiac index",
    "effusion": r"effusion|costophrenic|pleural fluid",
    "consolidation": r"consolidat|infiltrat|alveolar|condensation|pneumonia",
    "pneumothorax": r"pneumothorax",
    "nodule": r"nodul|\bmass|granuloma",
    "atelectasis": r"atelecta|volume loss|hypoexpansion|collapse",
    "scoliosis": r"scolio",
    "aortic_elongation": r"aortic elong|elongat\w* (?:of )?(?:the )?(?:thoracic )?aort|elongated aort",
    "pacemaker": r"pacemaker|defibrillator|electrode|dual chamber|\bdevice\b",
}
VETO = {"bilateral pleural effusion component.", "check-up after pacemaker placement, with the end of the electrode in the right ventricle."}
ES_POS = {"cardiomegaly": r"cardiomegalia|silueta card|[ií]ndice cardiotor|aumento", "effusion": r"derrame pleural", "consolidation": r"consolidaci",
          "pneumothorax": r"neumot[oó]rax", "nodule": r"n[oó]dulo", "atelectasis": r"atelectasia", "scoliosis": r"escoliosis",
          "aortic_elongation": r"elongaci[oó]n a[oó]rtica|aorta elongada|alargamiento a[oó]rtico", "pacemaker": r"marcapasos"}
ES_NEG = re.compile(r"\bno\b|\bsin\b|ausencia|normal|conservad|dentro de l[ií]mites", re.I)
ES_STEM_NEG = {"cardiomegaly": r"card|cardiotor", "effusion": r"derrame", "consolidation": r"consolidaci", "pneumothorax": r"neumot",
               "nodule": r"n[oó]dul", "atelectasis": r"atelectas", "scoliosis": r"escolios", "aortic_elongation": r"a[oó]rtic|aorta",
               "pacemaker": r"marcapasos"}


def neg_list(s, es):
    """나열형 명시적 부정 -> [(finding, 'absent')...] 또는 None (패턴 불일치). 스페인어 문장도 부정어와 해당 어근을 가져야 한다."""
    m = NEG_LIST_RE.match(s)
    if not m:
        return None
    body = m.group(1).lower()
    ks = [k for k, p in ITEM_FIND if re.search(p, body)]
    if not ks:
        return None
    if not ES_NEG.search(es):
        return None
    return [(k, "absent") for k in ks], "ok"


def norm(s):
    return re.sub(r"\s+", " ", s.strip())


def classify_sentence(f):
    """finding dict -> ([(finding_id, state), ...], 'ok') 이 문장이 명확히 지지하는 (finding, state) 목록. 아니면 (None, reason).
    양성은 단일 finding만, 음성은 단일 finding 또는 고정 어휘의 나열형 부정(예: 'No consolidations, nodules or masses')을 허용한다."""
    s = norm(f["sentence_en"])
    es = norm(f.get("sentence_es", ""))
    low = s.lower()
    if low in VETO:
        return None, "reviewer_veto"
    if D.TEMPORAL_RE.search(s) or TEMP2.search(s):
        return None, "temporal"
    hits = [k for k, p in BROAD.items() if re.search(p, low)]
    if f.get("abnormal") is True:
        cand = [k for k in S.FINDING_ORDER if re.search(POS_RE[k], low)]
        if len(cand) != 1:
            return None, "pos_no_or_multi_finding"
        k = cand[0]
        if not set(f.get("labels", [])) <= set(POS_LABELS[k]) or not f.get("labels"):
            return None, "pos_label_mismatch"
        if HEDGE.search(s) or re.search(r"\bno\b|\bnot\b|without|absence|\bnor\b|free of", low):
            return None, "pos_hedge_or_negation"
        other = [h for h in hits if h != k and h not in ("cardiomegaly",)]
        if other:
            return None, "pos_other_finding_words"
        if not re.search(ES_POS[k], es, re.I) or ES_NEG.search(es):
            return None, "pos_es_mismatch"
        return [(k, "present")], "ok"
    # 부정
    lst = neg_list(s, es)
    if lst is not None:
        return lst
    cand = [k for k in S.FINDING_ORDER if re.search(NEG_RE[k], low)]
    if len(cand) != 1:
        return None, "neg_no_or_multi_finding"
    k = cand[0]
    if k == "cardiomegaly":
        if not re.search(NEG_RE[k], low):
            return None, "neg_pattern"
        if not re.search(ES_STEM_NEG[k], es, re.I) or not re.search(r"normal|conservad|sin|dentro de l[ií]mites|sin alteraciones", es, re.I):
            return None, "neg_es_mismatch"
        return [(k, "absent")], "ok"
    if QUALIFIED_NEG.search(s.replace("There is no", "").replace("there is no", "")) and not SPEC_NEG_OK[k].match(s):
        return None, "neg_qualified"
    if not SPEC_NEG_OK[k].match(s):
        return None, "neg_pattern"
    if not ES_NEG.search(es) or not re.search(ES_STEM_NEG[k], es, re.I):
        return None, "neg_es_mismatch"
    return [(k, "absent")], "ok"


def image_states(r):
    """한 영상의 findings -> ({finding_id: [(state, idx)]}, ambiguous finding set, per-sentence rows)."""
    states = defaultdict(list)
    ambiguous = set()
    rows = []
    for idx, f in enumerate(r["findings"]):
        res, why = classify_sentence(f)
        low = (f.get("sentence_en") or "").lower()
        labs = " ".join(f.get("labels", []) if f.get("abnormal") is True else []).lower()
        related = {k for k, p in BROAD.items() if re.search(p, low) or re.search(p, labs)}
        rows.append((idx, res, why, related))
        for k, st in (res or []):
            states[k].append((st, idx))
    for idx, res, why, related in rows:
        supported = {k for k, _ in (res or [])}
        for k in related:
            # target 소견과 연관된 문장이 '명확한 지지 문장'이 아니면(다른 소견 문장·한정/hedge 문장 포함) 그 영상의 해당 소견은 모호
            if k not in supported:
                ambiguous.add(k)
    for k, v in states.items():
        if len({s for s, _ in v}) > 1 or len(v) > 1 and len({i for _, i in v}) > 1:
            ambiguous.add(k)
    return states, ambiguous, rows


def enumerate_pairs(reports, links, split="train", banned_patients=()):
    """환자 -> 후보 [(image, pair)]. ambiguity 규칙을 통과한 서로 다른 두 finding. 한 나열형 부정 문장에서 나온 두 absent도 허용(문장 출처를 기록).
    returns (per_patient dict, review_rows list, counters)."""
    cnt = Counter()
    per_pat = defaultdict(list)
    review = []
    for r in reports:
        iid = r["ImageID"]
        if links["img2split"][iid] != split:
            continue
        pid = links["img2patient"][iid]
        if pid in banned_patients:
            cnt["banned_patient_image"] += 1
            continue
        states, amb, rows = image_states(r)
        usable = {}
        for k, v in states.items():
            if k in amb:
                cnt["finding_ambiguous_in_image"] += 1
                continue
            usable[k] = v[0]
        for idx, res, why, _ in rows:
            f = r["findings"][idx]
            review.append(dict(ImageID=iid, idx=idx, sentence_en=f["sentence_en"], sentence_es=f.get("sentence_es"),
                               abnormal=f.get("abnormal"), labels=f.get("labels"),
                               rule=(";".join("%s:%s" % x for x in res) if res else None), reason=why,
                               image_ambiguous_for=sorted(k for k, _ in res if k in amb) if res else None))
        ks = sorted(usable)
        for a in range(len(ks)):
            for b in range(a + 1, len(ks)):
                (sa, ia), (sb, ib) = usable[ks[a]], usable[ks[b]]
                per_pat[pid].append(dict(PatientID=pid, ImageID=iid, StudyID=r["StudyID"],
                                         findings=[ks[a], ks[b]], states=[sa, sb], idx=[ia, ib],
                                         sentences_en=[r["findings"][ia]["sentence_en"], r["findings"][ib]["sentence_en"]],
                                         sentences_es=[r["findings"][ia]["sentence_es"], r["findings"][ib]["sentence_es"]]))
    return per_pat, review, cnt


def truth_stratum(states):
    """상태 쌍 -> 층 이름 (qA,qB 배정 전): 'neg2','mixed','pos2'."""
    n = sum(s == "present" for s in states)
    return {0: "neg2", 1: "mixed", 2: "pos2"}[n]
