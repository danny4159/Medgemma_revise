"""iter_120 자료 적합성 판정: 계획 기준(CT, 동일 target decoded pixels, 두 공식 GT IoU<=0.1, 같은 원천·case)을 audit_raw.json에서 적용."""
import json, datetime, hashlib

raw = json.load(open("results/iter_120/data/audit_raw.json"))
pairs = raw["pairs_sample"]  # 동일 target 쌍 전체(2개)가 sample에 포함됨
assert raw["n_pairs_same_target_hash"] == len(pairs) or len(pairs) <= 12
ct = [p for p in pairs if p["dataset"] in ("LUNA16", "WORD", "Verse2019", "1K", "AMOS22", "CTPelvic1K", "SegRap", "SegTHOR", "HaNSeg_sagittal", "COVID_19_20", "4C2021")]
eligible = [p for p in ct if p["same_case"] and p["iou_ans"] <= 0.1]
dec = {
    "locked_at_utc": datetime.datetime.utcnow().isoformat() + "Z",
    "parquet_rev": raw["parquet_rev"],
    "n_rows": raw["n_rows"],
    "distinct_target_decoded_pixel_hash": raw["distinct_target_hash"],
    "same_target_pixel_pairs_total": raw["n_pairs_same_target_hash"],
    "same_target_pixel_pairs": pairs,
    "ct_same_target_pairs": len(ct),
    "eligible_pairs_ct_iou_le_0.1": len(eligible),
    "run_models": len(eligible) >= 8,
    "reason": "동일 target decoded pixels를 공유하는 행 쌍이 1148행 중 2쌍뿐이며 모두 MRI(ACDC, BraTS2020)이고 GT IoU가 0.82/1.0이다. 계획의 적격 기준(CT, GT IoU<=0.1) 충족 0쌍. 각 행은 reference·target 슬라이스가 자체 고유 영상이므로 'reference만 바꾸는 paired 대조'가 이 공개 파일에서 성립하지 않는다.",
    "stop": "계획 1단계 종료 규칙에 따라 모델 다운로드·추론, 다른 Task/MRI/temporal 자동 이동 없음",
}
json.dump(dec, open("results/iter_120/data/eligibility_decision.json", "w"), indent=1, ensure_ascii=False)
print(json.dumps({k: v for k, v in dec.items() if k != "same_target_pixel_pairs"}, ensure_ascii=False, indent=1))
