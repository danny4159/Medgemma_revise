"""최소 DICOM 리더 (pydicom 미설치, pip 불가). RSNA 배포본(Explicit VR LE, JPEG baseline 1.2.840.10008.1.2.4.50)만 지원.

지원하지 않는 전송 구문·태그 조합은 예외를 던져 입력 gate를 실패시킨다 (조용히 추정하지 않는다).
"""
import io
import struct

from PIL import Image

EXPLICIT_LE = "1.2.840.10008.1.2.1"
JPEG_BASELINE = "1.2.840.10008.1.2.4.50"
LONG_VR = {"OB", "OW", "OF", "SQ", "UT", "UN", "OD", "OL", "UC", "UR"}
WANT = {
    (0x0002, 0x0010): "TransferSyntaxUID",
    (0x0008, 0x0018): "SOPInstanceUID",
    (0x0010, 0x0020): "PatientID",
    (0x0028, 0x0002): "SamplesPerPixel",
    (0x0028, 0x0004): "PhotometricInterpretation",
    (0x0028, 0x0010): "Rows",
    (0x0028, 0x0011): "Columns",
    (0x0028, 0x0100): "BitsAllocated",
    (0x0028, 0x0101): "BitsStored",
    (0x0028, 0x0102): "HighBit",
    (0x0028, 0x0103): "PixelRepresentation",
    (0x0028, 0x1050): "WindowCenter",
    (0x0028, 0x1051): "WindowWidth",
    (0x0028, 0x1052): "RescaleIntercept",
    (0x0028, 0x1053): "RescaleSlope",
    (0x0028, 0x0030): "PixelSpacing",
    (0x0028, 0x2110): "LossyImageCompression",
    (0x0018, 0x5101): "ViewPosition",
    (0x0008, 0x0060): "Modality",
    (0x0028, 0x0008): "NumberOfFrames",
    (0x0028, 0x1054): "RescaleType",
    (0x0028, 0x1056): "VOILUTFunction",
    (0x0028, 0x3010): "VOILUTSequence",
    (0x2050, 0x0020): "PresentationLUTShape",
}

# 신규 입력 gate: 이 조건 밖의 표시 관련 태그는 자동 추정하지 않고 exclusion 사유로 기록한다.
STANDARD_SIG = {"Rows": 1024, "Columns": 1024, "BitsAllocated": 8, "BitsStored": 8, "HighBit": 7, "PixelRepresentation": 0,
                "PhotometricInterpretation": "MONOCHROME2", "SamplesPerPixel": 1, "TransferSyntaxUID": JPEG_BASELINE}
ABSENT_TAGS = ("WindowCenter", "WindowWidth", "VOILUTFunction", "VOILUTSequence")


def _num(v):
    try:
        return float(str(v).split("\\")[0])
    except ValueError:
        return None


def display_problems(tags):
    """표시 관련 태그 검사. 빈 list면 'decoded 8-bit == 표시값' 가정이 성립한다.

    RescaleSlope/Intercept는 없거나 항등(1/0), Window*/VOI LUT는 없어야 하고, 단일 frame이며, Presentation LUT는 없거나 IDENTITY.
    """
    prob = []
    for k, v in STANDARD_SIG.items():
        if tags.get(k) != v:
            prob.append(f"dicom_{k}={tags.get(k)!r}")
    for k in ABSENT_TAGS:
        if k in tags:
            prob.append(f"dicom_{k}_present")
    if "RescaleSlope" in tags and _num(tags["RescaleSlope"]) != 1.0:
        prob.append(f"dicom_RescaleSlope={tags['RescaleSlope']!r}")
    if "RescaleIntercept" in tags and _num(tags["RescaleIntercept"]) != 0.0:
        prob.append(f"dicom_RescaleIntercept={tags['RescaleIntercept']!r}")
    if "NumberOfFrames" in tags and _num(tags["NumberOfFrames"]) != 1.0:
        prob.append(f"dicom_NumberOfFrames={tags['NumberOfFrames']!r}")
    if tags.get("PresentationLUTShape", "IDENTITY") != "IDENTITY":
        prob.append(f"dicom_PresentationLUTShape={tags['PresentationLUTShape']!r}")
    return prob


def _val(vr, raw):
    if vr in ("US",):
        return struct.unpack("<H", raw[:2])[0]
    if vr in ("UL",):
        return struct.unpack("<I", raw[:4])[0]
    return raw.decode("latin-1").rstrip("\x00 ").strip()


def parse(data):
    """returns (tags dict, pixel_fragments list[bytes] or native bytes)."""
    if data[128:132] != b"DICM":
        raise ValueError("not DICOM part-10")
    pos, n = 132, len(data)
    tags = {}
    pixel = None
    while pos + 8 <= n:
        g, e = struct.unpack("<HH", data[pos:pos + 4])
        vr = data[pos + 4:pos + 6].decode("latin-1")
        if vr in LONG_VR:
            ln = struct.unpack("<I", data[pos + 8:pos + 12])[0]
            hdr = 12
        else:
            ln = struct.unpack("<H", data[pos + 6:pos + 8])[0]
            hdr = 8
        if g == 0x7FE0 and e == 0x0010:
            body = pos + hdr
            if ln == 0xFFFFFFFF:
                frags, p = [], body
                while True:
                    tg, te, tl = struct.unpack("<HHI", data[p:p + 8])
                    p += 8
                    if (tg, te) == (0xFFFE, 0xE0DD):
                        break
                    if (tg, te) != (0xFFFE, 0xE000):
                        raise ValueError("bad encapsulated item")
                    frags.append(data[p:p + tl])
                    p += tl
                pixel = frags
            else:
                pixel = data[body:body + ln]
            break
        if ln == 0xFFFFFFFF:  # 정의 안 된 길이 시퀀스: 지원하지 않는다 (관심 태그 밖이면 전체 스캔 실패로 처리)
            raise ValueError(f"undefined-length element ({g:04x},{e:04x}) unsupported")
        if (g, e) in WANT:
            tags[WANT[(g, e)]] = _val(vr, data[pos + hdr:pos + hdr + ln])
        pos += hdr + ln
    return tags, pixel


def read_pixels(data):
    """DICOM bytes -> (meta dict, np.uint8 array (H,W) 또는 (H,W,3))."""
    import numpy as np
    tags, pixel = parse(data)
    if tags.get("TransferSyntaxUID") != JPEG_BASELINE:
        raise ValueError(f"unsupported transfer syntax {tags.get('TransferSyntaxUID')}")
    prob = display_problems(tags)
    if prob:
        raise ValueError(f"unsupported display tags: {prob}")
    if not isinstance(pixel, list) or len(pixel) < 1:
        raise ValueError("expected encapsulated pixel data")
    # 첫 item은 basic offset table일 수 있다 (길이 0이면 빈 table). 단일 frame: JPEG SOI(FFD8)로 시작하는 fragment를 이어붙인다.
    frames = [f for f in pixel if len(f) > 0]
    jpeg = b"".join(frames)
    if jpeg[:2] != b"\xff\xd8":
        raise ValueError("no JPEG SOI")
    im = Image.open(io.BytesIO(jpeg))
    im.load()
    arr = np.asarray(im)
    meta = dict(tags)
    meta["pil_mode"] = im.mode
    meta["array_shape"] = list(arr.shape)
    meta["array_dtype"] = str(arr.dtype)
    return meta, arr
