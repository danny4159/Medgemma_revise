"""제한된 MetaIO(.mha) reader (iter_019). SimpleITK가 없는 환경에서 실제 등장하는 3D scalar LOCAL binary MHA만 지원한다.

지원 범위: NDims=3, BinaryData=True, ElementDataFile=LOCAL, ElementNumberOfChannels<=1,
ElementType in {MET_UCHAR, MET_CHAR, MET_SHORT, MET_USHORT, MET_FLOAT, MET_DOUBLE, MET_INT, MET_UINT},
CompressedData True(zlib)/False, BinaryDataByteOrderMSB True/False.
공식 규약: https://docs.itk.org/en/latest/learn/metaio.html

지원하지 않는 header(비3D, non-LOCAL, ASCII data, 다중 채널, 알 수 없는 ElementType)는 MhaError로 실패시킨다(추측 금지).
DimSize는 [x, y, z] (x가 가장 빠르게 변함)이며, 반환 numpy 배열의 axis 순서는 (z, y, x) (C-order, x가 마지막 축).
"""
import zlib

import numpy as np

_TYPE_MAP = {
    "MET_UCHAR": "u1", "MET_CHAR": "i1",
    "MET_SHORT": "i2", "MET_USHORT": "u2",
    "MET_INT": "i4", "MET_UINT": "u4",
    "MET_FLOAT": "f4", "MET_DOUBLE": "f8",
}


class MhaError(RuntimeError):
    pass


def _parse_value(key, raw):
    raw = raw.strip()
    if key in ("NDims", "CompressedDataSize", "ElementNumberOfChannels", "HeaderSize"):
        return int(raw)
    if key in ("CompressedData", "BinaryData", "BinaryDataByteOrderMSB"):
        return raw.strip().lower() == "true"
    if key in ("DimSize",):
        return [int(x) for x in raw.split()]
    if key in ("ElementSpacing", "Offset", "TransformMatrix", "CenterOfRotation"):
        return [float(x) for x in raw.split()]
    return raw


def parse_header(data):
    """data(bytes) -> (header dict, payload_offset:int). ElementDataFile != LOCAL 이면 MhaError."""
    pos = 0
    header = {}
    n = len(data)
    while True:
        nl = data.find(b"\n", pos)
        if nl == -1:
            raise MhaError("header not terminated (no ElementDataFile line found)")
        line = data[pos:nl].decode("ascii", errors="strict")
        pos = nl + 1
        if "=" not in line:
            if line.strip() == "":
                continue
            raise MhaError(f"malformed header line: {line!r}")
        key, _, val = line.partition("=")
        key = key.strip()
        if key == "ElementDataFile":
            if val.strip() != "LOCAL":
                raise MhaError(f"unsupported ElementDataFile {val.strip()!r} (only LOCAL supported)")
            header[key] = "LOCAL"
            return header, pos
        header[key] = _parse_value(key, val)
        if pos >= n:
            raise MhaError("header not terminated (no ElementDataFile line found)")


def read_mha(path_or_bytes):
    """returns dict: array(z,y,x), dim_size(x,y,z), spacing(x,y,z), offset(x,y,z), direction(3x3 row-major), element_type, raw_header."""
    data = path_or_bytes if isinstance(path_or_bytes, (bytes, bytearray)) else open(path_or_bytes, "rb").read()
    hdr, off = parse_header(data)
    if hdr.get("ObjectType", "Image") != "Image":
        raise MhaError(f"unsupported ObjectType {hdr.get('ObjectType')!r}")
    if hdr.get("NDims") != 3:
        raise MhaError(f"unsupported NDims {hdr.get('NDims')!r} (only 3D supported)")
    if not hdr.get("BinaryData", False):
        raise MhaError("only BinaryData=True supported")
    nchan = hdr.get("ElementNumberOfChannels", 1)
    if nchan not in (1,):
        raise MhaError(f"unsupported ElementNumberOfChannels {nchan}")
    etype = hdr.get("ElementType")
    if etype not in _TYPE_MAP:
        raise MhaError(f"unsupported ElementType {etype!r}")
    dim = hdr.get("DimSize")
    if not dim or len(dim) != 3:
        raise MhaError(f"invalid DimSize {dim!r}")
    nx, ny, nz = dim
    nvoxels = nx * ny * nz
    msb = hdr.get("BinaryDataByteOrderMSB", False)
    dtype_code = (">" if msb else "<") + _TYPE_MAP[etype]
    dt = np.dtype(dtype_code)
    payload = data[off:]
    if hdr.get("CompressedData", False):
        size = hdr.get("CompressedDataSize")
        if size is None:
            raise MhaError("CompressedData=True but no CompressedDataSize")
        if len(payload) < size:
            raise MhaError(f"truncated compressed payload: have {len(payload)}, want {size}")
        raw = zlib.decompress(payload[:size])
    else:
        need = nvoxels * dt.itemsize
        if len(payload) < need:
            raise MhaError(f"truncated payload: have {len(payload)}, want {need}")
        raw = payload[:need]
    expect_bytes = nvoxels * dt.itemsize
    if len(raw) != expect_bytes:
        raise MhaError(f"decoded payload size {len(raw)} != expected {expect_bytes} (nx={nx} ny={ny} nz={nz} itemsize={dt.itemsize})")
    arr = np.frombuffer(raw, dtype=dt).reshape((nz, ny, nx))
    spacing = hdr.get("ElementSpacing", [1.0, 1.0, 1.0])
    offset = hdr.get("Offset", [0.0, 0.0, 0.0])
    tm = hdr.get("TransformMatrix", [1, 0, 0, 0, 1, 0, 0, 0, 1])
    direction = [tm[0:3], tm[3:6], tm[6:9]]
    return {"array": arr, "dim_size_xyz": dim, "spacing_xyz": spacing, "offset_xyz": offset,
            "direction": direction, "element_type": etype, "header": hdr,
            "anatomical_orientation": hdr.get("AnatomicalOrientation")}


def sagittal_axis(direction, anatomical_orientation, tol=0.5):
    """index axis (0=x,1=y,2=z in DimSize order) that is dominantly aligned with the R/L physical
    coordinate. `direction[j]` = index axis j's direction cosines in the file's physical frame
    (MetaIO TransformMatrix row j, per https://docs.itk.org/en/latest/learn/metaio.html); by ITK/MetaIO
    convention physical component 0 is the L-R axis. Cross-checked against AnatomicalOrientation
    (index j must be labelled 'R' or 'L') so a single source is never trusted alone. Ambiguous
    (no axis dominant, or two axes both dominant) or missing/invalid AnatomicalOrientation -> MhaError;
    callers must treat that as an unsupported orientation, not guess.
    """
    if len(direction) != 3 or any(len(row) != 3 for row in direction):
        raise MhaError(f"invalid direction matrix shape: {direction!r}")
    col0 = [float(row[0]) for row in direction]
    absvals = [abs(v) for v in col0]
    order = sorted(range(3), key=lambda i: -absvals[i])
    j_best, j_second = order[0], order[1]
    if absvals[j_best] < tol:
        raise MhaError(f"no axis dominantly aligned with R-L physical axis: direction column-0 {col0!r}")
    if absvals[j_second] >= tol:
        raise MhaError(f"ambiguous sagittal axis (two axes >= {tol} on R-L column): direction column-0 {col0!r}")
    ao = anatomical_orientation
    if not ao or not isinstance(ao, str) or len(ao.strip()) != 3:
        raise MhaError(f"missing/invalid AnatomicalOrientation {ao!r}")
    ao = ao.strip()
    if any(ch not in "RLAPSI?" for ch in ao):
        raise MhaError(f"unsupported AnatomicalOrientation characters {ao!r}")
    if ao[j_best] not in "RL":
        raise MhaError(f"direction column-0 dominant axis {j_best} not confirmed R/L by AnatomicalOrientation {ao!r}")
    sign = 1.0 if col0[j_best] > 0 else -1.0
    return j_best, sign


def axis_layout(j_sag):
    """returns (array_axis_sag, array_axis_row, array_axis_col) for slicing a (z,y,x) array along
    index axis j_sag (0=x,1=y,2=z). array axis for index axis i is (2-i) since array shape is (z,y,x).
    row/col follow the legacy x-sagittal convention (row from the higher remaining index axis,
    col from the lower one), so j_sag=0 reproduces the original row=z, col=y layout exactly."""
    remaining = sorted(a for a in range(3) if a != j_sag)
    idx_col, idx_row = remaining[0], remaining[1]
    return 2 - j_sag, 2 - idx_row, 2 - idx_col


def take_slice(vol, array_axis_sag, array_axis_row, array_axis_col, idx):
    """2D slice of a 3D array at index `idx` along array_axis_sag, oriented (row=array_axis_row,
    col=array_axis_col). With 3 axes total, the two remaining axes after removing array_axis_sag
    are already exactly {array_axis_row, array_axis_col}; only their order can need a transpose."""
    sl = [slice(None)] * 3
    sl[array_axis_sag] = idx
    raw = vol[tuple(sl)]
    remaining_axes_in_order = [a for a in range(3) if a != array_axis_sag]
    if remaining_axes_in_order == [array_axis_row, array_axis_col]:
        return raw
    return raw.T
