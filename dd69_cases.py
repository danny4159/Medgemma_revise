"""iter_069: 후보 180행 -> 캡션 기반 1차 적격 판정(영상 확인 전) 고정표.

판정 기준(출력 전 고정): 별도 DWI·ADC 영상, DWI 캡션에 고신호 표현, ADC 캡션에 신호(저/고/등신호·ADC 값) 표현,
같은 대상, 복수 병변이면 ADC image index가 가장 작은 쌍. 'restriction' 표현만 있으면 ADC 신호 label을 만들지 않는다.
label: LOW(ADC 감소) / NOT_LOW(ADC 비감소: 고신호·등신호·정상 범위).
각 항목: (title번호, DWI image index, ADC image index, ADC label, 캡션 근거 요약)
"""
import json
import re

TRAIN = "results/iter_049/raw/train.jsonl"
TRAIN_SHA256 = "7b38ceddc9cb1cf3a8dc0f9179c694caf826cd5716bb1b326e71d36e9e7d9b3a"

# 캡션 기반 후보(영상 확인 전). 제외 사유는 EXCLUDED_TEXT에 기록.
CAND = [
    (1017, 2, 3, "NOT_LOW", "DWI b1000 high signal in tumour / ADC map high ADC value 1.15"),
    (5324, 4, 5, "NOT_LOW", "DWI increased intensity (T2 shine-through) / ADC increased values (small hemorrhagic area excepted)"),
    (7006, 9, 8, "LOW", "DWI slight hyperintensity / ADC low signal"),
    (7529, 10, 11, "LOW", "DWI high signal / ADC low signal"),
    (8511, 7, 8, "LOW", "DWI hyperintense / ADC hypointense"),
    (12899, 2, 1, "LOW", "DWI high signal mass / ADC low values"),
    (13776, 5, 6, "LOW", "DWI abnormal high signal bilateral putamina / ADC drop of signal"),
    (14583, 7, 8, "LOW", "DWI high-signal mass / ADC low-signal mass"),
    (14665, 5, 6, "LOW", "DWI partially hyperintense lesion / ADC reduced signal"),
    (14955, 7, 8, "NOT_LOW", "DWI b1000 high signal (T2 shine-through) / ADC isointense to cerebellar parenchyma"),
    (15611, 17, 18, "NOT_LOW", "DWI subtle hyperintense / ADC hyperintense facilitated"),
    (16138, 4, 5, "LOW", "DWI high signal b1000 / ADC low signal"),
    (16818, 6, 7, "LOW", "DWI marked increase in signal / ADC marked hypointensity"),
    (17136, 4, 5, "LOW", "DWI hyperintense / ADC hypointense (sagittal abscess)"),
    (17812, 4, 5, "LOW", "DWI marked high signal b1000 / ADC low signal (star)"),
    (17999, 5, 7, "LOW", "DWI hyperintensity bilateral frontal/left parietal cortex / ADC hypointensity bilateral frontal lobe (same level)"),
    (18326, 7, 8, "LOW", "DWI high signal in lesion cavity / ADC low signal"),
    (18487, 3, 4, "NOT_LOW", "DWI high signal bilateral thalami / ADC no significant decreased or increased signal"),
    (18529, 3, 4, "LOW", "DWI hyperintensity of tumour / ADC clearly low"),
    (18569, 3, 4, "LOW", "DWI moderate hyperintensity prostatic lesion / ADC low signal"),
    (18805, 10, 3, "LOW", "DWI hyperintensity dorsal brainstem / ADC hypointensity dorsal brainstem"),
    (18862, 10, 11, "LOW", "DWI high signal areas / ADC drop in signal"),
    (18876, 6, 7, "LOW", "DWI b1000 high signal / ADC low signal"),
    (18942, 2, 3, "LOW", "DWI highly hyperintense / ADC very low value"),
    (18963, 7, 8, "NOT_LOW", "DWI mild hyperintensity both frontal lesions / ADC hyperintensity of both frontal lesions"),
    (19278, 6, 7, "NOT_LOW", "DWI high signal intensity within lesion / ADC elevated values"),
]

EXCLUDED_TEXT = {
    10538: "복수 nodule, 서로 다른 ADC 값", 10637: "ADC 캡션에 신호 표현 없이 restriction 유무만", 11245: "DWI 고신호 표현 없음, ADC iso-hypo 모호",
    11468: "DWI isointense (고신호 아님)", 11492: "DWI 3장 동일 캡션 panel", 11797: "ADC 캡션에 신호 표현 없이 restriction만",
    11851: "ADC 캡션에 신호 표현 없이 restriction만", 12083: "DWI 고신호 표현 없음", 13099: "DWI 고신호 표현 없음", 13109: "ADC 값만",
    13186: "DWI 고신호 표현 없음", 14053: "신호 표현 없이 restriction만", 14491: "DWI 고신호 표현 없음", 14798: "DWI 고신호 표현 없음",
    14811: "DWI iso-to-hyper 모호", 15287: "DWI 고신호 표현 없음", 15668: "DWI 캡션 비어 있음", 15705: "신호 표현 없음", 16026: "DWI 고신호 표현 없음",
    16041: "caption(DWI no alteration)과 본문(restricted diffusion) 충돌", 16176: "DWI 고신호 표현 없음", 16214: "DWI 고신호 표현 없음",
    16400: "DWI 증가 diffusivity, 다성분", 16434: "DWI no change", 16475: "ADC 캡션에 신호 표현 없이 restriction만", 16551: "DWI 고신호 표현 없음",
    16764: "캡션에 신호 표현 없음", 17161: "DWI hypointense", 17189: "신호 표현 없이 restriction만", 17195: "신호 표현 없이 restriction만",
    17331: "DWI hyposignal", 17516: "DWI 고신호 표현 없음", 18260: "ADC intermediate 모호", 18274: "DWI 신호 표현 없이 restriction만",
    18319: "DWI 신호 표현 없이 restriction만", 18685: "DWI low-intermediate", 18900: "신호 표현 없이 restriction만 (다성분)",
    19040: "DWI 고신호 표현 없음", 19046: "DWI 신호 표현 없이 restriction만", 19097: "DWI 캡션에 신호 표현 없음", 19126: "신호 표현 없이 restriction만",
    19214: "캡션에 신호 표현 없음", 3602: "신호 표현 없이 abnormal diffusion", 8609: "DWI low signal", 9565: "DWI high signal 아님",
    9816: "DWI 중심 low signal·주변 high (다성분)", 9988: "DWI hypointensity", 15047: "다성분(주변 hypo, 중심 moderate)",
}


def load_rows():
    import hashlib
    raw = open(TRAIN, "rb").read()
    if hashlib.sha256(raw).hexdigest() != TRAIN_SHA256:
        raise RuntimeError("train.jsonl sha256 mismatch")
    return {int(re.search(r"\d+", r["title"]).group()): r for r in (json.loads(l) for l in raw.decode().splitlines())}


def search180(rows):
    """계획의 180행 검색 재현: non-longitudinal, 전체 caption에 ADC와 DWI/diffusion-weighted."""
    out = []
    for k, r in rows.items():
        if r["is_longitudinal"] is not False:
            continue
        caps = " ".join(r["image_%02d_caption" % i] for i in range(1, 50))
        if re.search(r"\bADC\b", caps) and re.search(r"\bDWI\b|diffusion[- ]weighted", caps, re.I):
            out.append(k)
    return sorted(out)
