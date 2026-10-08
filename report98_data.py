"""iter_098: 저장 CURE 출력(E96 비정상 48명)에서 초안(C-G)·영역 설명 본문을 추출하고 reference와 연결한다.

모델 입력에는 reference/평가 라벨을 넣지 않는다. 평가용 private 정보는 별도 함수로만 읽는다.
"""
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
R86 = ROOT / "results" / "iter_086"
R87 = ROOT / "results" / "iter_087"
INPUTS = R86 / "E" / "inputs_E96.json"
READINGS = R86 / "E96" / "readings.jsonl"
REF_AMEND = R87 / "reference_amend_E96.json"
REF_PRIV = R86 / "E" / "reference_facts_E_private.json"

HDR = re.compile(r"^Location of the (?P<name>[^:]+): \[[^\]]*\]\. Description: (?P<body>.*)$", re.S)
COORD = re.compile(r"\[\s*-?\d*\.?\d+(?:\s*,\s*-?\d*\.?\d+){3}\s*\]")


def sha(s):
    return hashlib.sha256(s.encode()).hexdigest()


def norm_ws(s):
    return re.sub(r"\s+", " ", s).strip()


def load_inputs():
    return json.load(open(INPUTS))


def load_readings():
    out = {}
    for line in open(READINGS):
        r = json.loads(line)
        out[(r["ImageID"], r["condition"])] = r
    return out


def abnormal_ids():
    return [i["ImageID"] for i in load_inputs() if i["stratum"] == "abnormal"]


def extract_regions(h):
    """C-H 레코드의 29개 영역 segment에서 (영역명, 본문)을 추출한다. 형식 실패는 예외."""
    segs = h["segments"]
    assert segs[-1]["source"] == "C|G", segs[-1]["source"]
    out = []
    for s in segs[:-1]:
        m = HDR.match(s["text"].strip())
        if not m:
            raise ValueError("region header parse failed: %r" % s["text"][:80])
        name = m.group("name").strip()
        assert s["source"] == "C|" + name, (s["source"], name)
        body = m.group("body").strip()
        assert not COORD.search(body), body
        out.append((name, body))
    assert len(out) == 29, len(out)
    return out


def dedup_bodies(regions):
    """공백 정규화 후 정확히 동일한 본문만 묶는다. 순서는 원 source 순(첫 등장)."""
    order, srcs = [], {}
    for name, body in regions:
        k = norm_ws(body)
        if k not in srcs:
            srcs[k] = []
            order.append(k)
        srcs[k].append(name)
    return [(k, srcs[k]) for k in order]


def draft_text(g):
    """C-G 초안: 좌표 표기 제거(있다면)만 한다."""
    return norm_ws(COORD.sub("", g["text"])) if "[" in g["text"] else g["text"].strip()


def package(img_id, R=None):
    R = R or load_readings()
    g = R[(img_id, "C-G")]
    h = R[(img_id, "C-H")]
    regions = extract_regions(h)
    return {
        "ImageID": img_id,
        "draft": draft_text(g),
        "groups": [{"gid": "D%02d" % (i + 1), "body": b, "regions": r}
                   for i, (b, r) in enumerate(dedup_bodies(regions))],
    }


def reference(img_id):
    am = json.load(open(REF_AMEND))["patients"][img_id]
    priv = json.load(open(REF_PRIV))[img_id]
    return am, priv
