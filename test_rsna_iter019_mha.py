"""iter_019 mi19_mha fixture 검사. 압축/비압축, endianness, 축 순서, 실제 SPIDER mask를 독립 계산으로 대조한다."""
import json
import struct
import sys
import zlib

import numpy as np

sys.path.insert(0, "/SSD1_1TB/home/milab/daniel/08_medgemma/research")
from rsna_diag import mi19_mha as M

results = []


def check(name, cond, detail=None):
    results.append({"name": name, "pass": bool(cond), "detail": detail})


def make_header(fields, elem_line="ElementDataFile = LOCAL\n"):
    lines = "".join(f"{k} = {v}\n" for k, v in fields.items())
    return (lines + elem_line).encode("ascii")


def test_uncompressed_uint8_roundtrip():
    nx, ny, nz = 3, 4, 2
    arr = np.arange(nx * ny * nz, dtype=np.uint8).reshape((nz, ny, nx))
    hdr = make_header({
        "ObjectType": "Image", "NDims": 3, "BinaryData": "True", "BinaryDataByteOrderMSB": "False",
        "CompressedData": "False", "TransformMatrix": "1 0 0 0 1 0 0 0 1", "Offset": "0 0 0",
        "ElementSpacing": "1.5 2.5 3.5", "DimSize": f"{nx} {ny} {nz}", "ElementType": "MET_UCHAR",
    })
    blob = hdr + arr.tobytes()
    out = M.read_mha(blob)
    check("uncompressed_uint8_shape", out["array"].shape == (nz, ny, nx), out["array"].shape)
    check("uncompressed_uint8_values", np.array_equal(out["array"], arr))
    check("uncompressed_spacing_xyz", out["spacing_xyz"] == [1.5, 2.5, 3.5])
    check("uncompressed_dimsize_xyz", out["dim_size_xyz"] == [nx, ny, nz])


def test_compressed_int16_roundtrip():
    nx, ny, nz = 5, 4, 3
    rng = np.random.RandomState(19)
    arr = (rng.rand(nz, ny, nx) * 2000 - 1000).astype(np.int16)
    raw = arr.tobytes()
    comp = zlib.compress(raw, 9)
    hdr = make_header({
        "ObjectType": "Image", "NDims": 3, "BinaryData": "True", "BinaryDataByteOrderMSB": "False",
        "CompressedData": "True", "CompressedDataSize": len(comp), "TransformMatrix": "1 0 0 0 1 0 0 0 1",
        "Offset": "-10 -20 -30", "ElementSpacing": "0.8 0.8 4.0", "DimSize": f"{nx} {ny} {nz}",
        "ElementType": "MET_SHORT",
    })
    blob = hdr + comp
    out = M.read_mha(blob)
    check("compressed_int16_values", np.array_equal(out["array"], arr))
    check("compressed_offset_xyz", out["offset_xyz"] == [-10.0, -20.0, -30.0])


def test_big_endian():
    nx, ny, nz = 2, 2, 2
    arr = np.array([[[1, 2], [3, 4]], [[5, 6], [7, 8]]], dtype=">i2")  # (z,y,x)
    hdr = make_header({
        "ObjectType": "Image", "NDims": 3, "BinaryData": "True", "BinaryDataByteOrderMSB": "True",
        "CompressedData": "False", "TransformMatrix": "1 0 0 0 1 0 0 0 1", "Offset": "0 0 0",
        "ElementSpacing": "1 1 1", "DimSize": f"{nx} {ny} {nz}", "ElementType": "MET_SHORT",
    })
    blob = hdr + arr.tobytes()
    out = M.read_mha(blob)
    check("big_endian_values", np.array_equal(out["array"], arr.astype("<i2")))


def test_axis_order_x_fastest():
    # DimSize = [nx=4,1,1]; x가 가장 빠르게 변하므로 배열은 (1,1,4)이고 값 순서가 그대로 유지돼야 한다
    nx, ny, nz = 4, 1, 1
    vals = np.array([10, 20, 30, 40], dtype=np.uint8)
    hdr = make_header({
        "ObjectType": "Image", "NDims": 3, "BinaryData": "True", "BinaryDataByteOrderMSB": "False",
        "CompressedData": "False", "TransformMatrix": "1 0 0 0 1 0 0 0 1", "Offset": "0 0 0",
        "ElementSpacing": "1 1 1", "DimSize": f"{nx} {ny} {nz}", "ElementType": "MET_UCHAR",
    })
    blob = hdr + vals.tobytes()
    out = M.read_mha(blob)
    check("axis_order_x_fastest", np.array_equal(out["array"][0, 0, :], vals))


def test_rejects_non_local():
    hdr = make_header({"ObjectType": "Image", "NDims": 3, "BinaryData": "True", "DimSize": "1 1 1",
                       "ElementType": "MET_UCHAR"}, elem_line="ElementDataFile = foo.raw\n")
    try:
        M.read_mha(hdr)
        check("rejects_non_local", False)
    except M.MhaError:
        check("rejects_non_local", True)


def test_rejects_ndims_2():
    hdr = make_header({"ObjectType": "Image", "NDims": 2, "BinaryData": "True", "DimSize": "2 2",
                       "ElementType": "MET_UCHAR"})
    blob = hdr + bytes(4)
    try:
        M.read_mha(blob)
        check("rejects_ndims_2", False)
    except M.MhaError:
        check("rejects_ndims_2", True)


def test_rejects_truncated_payload():
    nx, ny, nz = 2, 2, 2
    hdr = make_header({"ObjectType": "Image", "NDims": 3, "BinaryData": "True", "BinaryDataByteOrderMSB": "False",
                       "CompressedData": "False", "DimSize": f"{nx} {ny} {nz}", "ElementType": "MET_UCHAR"})
    blob = hdr + bytes(3)  # need 8
    try:
        M.read_mha(blob)
        check("rejects_truncated_payload", False)
    except M.MhaError:
        check("rejects_truncated_payload", True)


def test_real_spider_mask():
    import zipfile
    z = zipfile.ZipFile("/SSD1_1TB/home/milab/daniel/08_medgemma/research/results/iter_021/source/masks.zip")
    data = z.read("masks/101_t1.mha")
    out = M.read_mha(data)
    # 독립 재계산: 헤더 텍스트를 직접 파싱해 대조
    idx = data.find(b"ElementDataFile = LOCAL\n")
    header_txt = data[:idx].decode("ascii")
    fields = dict(ln.split(" = ", 1) for ln in header_txt.strip().split("\n"))
    dimsize = [int(x) for x in fields["DimSize"].split()]
    comp_size = int(fields["CompressedDataSize"])
    payload = data[idx + len(b"ElementDataFile = LOCAL\n"):idx + len(b"ElementDataFile = LOCAL\n") + comp_size]
    raw = zlib.decompress(payload)
    nx, ny, nz = dimsize
    arr_check = np.frombuffer(raw, dtype="<i2").reshape((nz, ny, nx))
    check("real_mask_dimsize", out["dim_size_xyz"] == dimsize)
    check("real_mask_values_independent", np.array_equal(out["array"], arr_check))
    labels = sorted(set(np.unique(out["array"]).tolist()))
    check("real_mask_nonneg_labels", all(v >= 0 for v in labels), labels[:20])
    # instance connectivity 최소 검사: label>0 voxel count > 0
    check("real_mask_has_foreground", int((out["array"] > 0).sum()) > 0)


for fn in [test_uncompressed_uint8_roundtrip, test_compressed_int16_roundtrip, test_big_endian,
           test_axis_order_x_fastest, test_rejects_non_local, test_rejects_ndims_2,
           test_rejects_truncated_payload, test_real_spider_mask]:
    fn()

n_pass = sum(1 for r in results if r["pass"])
print(json.dumps({"n": len(results), "n_pass": n_pass, "results": results}, indent=1, default=str))
json.dump({"n": len(results), "n_pass": n_pass, "results": results},
          open("/SSD1_1TB/home/milab/daniel/08_medgemma/research/results/iter_021/tests/fixtures_mha.json", "w"), indent=1, default=str)
assert n_pass == len(results), "some fixtures failed"
