"""공통 preflight: runner(resume)·selector·evaluator가 모두 이 모듈을 거친다 (iter_005 수정).

iter_004 리뷰의 세 결함을 막는다.
1. 저장된 hash 문자열끼리만 비교하지 않고, 현재 실제 파일에서 file/pixel/변형 입력 hash와
   request 본문 hash를 다시 계산해 manifest 전체(완료된 요청 포함)와 대조한다.
2. verification을 지정 ID 집합·누락·중복·충돌·hash·수치 기준으로 검사한다.
3. selection의 config/predictions digest를 현재 유효 prediction에 연결한다.

검사 실패는 PreflightError로 올리며, 호출한 진입점은 `complete`나 투자 판정을 출력하지 않는다.
"""
import hashlib
import json
import math
import os

from .data import DATA_DIR, build_config, build_requests, config_hash, fixed_subsets, sha256_json
from .store import RESULT_FIELDS, read_jsonl

# verification 수치 기준 (iter_004 계획: teacher-forced 차이 1e-3 이하, 반복 차이도 같은 기준으로 강제)
VER_TF_TOL = 1e-3
VER_REPEAT_TOL = 1e-3
VER_REQUIRED_FIELDS = ["m_main", "m_repeat", "repeat_abs_diff", "m_tf", "tf_abs_diff",
                       "request_sha256", "config_sha256"]
VER_NUMERIC_FIELDS = ["m_main", "m_repeat", "repeat_abs_diff", "m_tf", "tf_abs_diff", "tf_lp_yes", "tf_lp_no"]


class PreflightError(RuntimeError):
    def __init__(self, stage, problems):
        self.stage = stage
        self.problems = problems
        super().__init__(f"preflight[{stage}] failed: {problems[:5]} (n={len(problems)})")


def request_body_hash(r):
    return sha256_json({k: v for k, v in r.items() if k != "request_sha256"})


# iter_006: 고정 부분집합의 필수 key. 저장본은 이 key만 가져야 한다 (누락·추가 모두 거부).
SUBSET_KEYS = ("calibration", "verification")


def check_subsets(subsets, reqs):
    """저장된 calibration·verification 목록을 `fixed_subsets(reqs)`의 결정적 재생성 결과와 대조한다.

    목록 순서는 의미가 없다: runner queue는 requests 순서로 만들고, verification 검사는 ID 집합으로 한다.
    정규화 규칙: (1) 중복 ID는 정규화 전에 거부, (2) 남은 목록을 ID 집합으로 비교. 따라서 순서만 다른
    저장본은 통과하고, 축소·공집합·추가·같은 크기의 ID 교체는 모두 거부한다. 문제 목록을 반환한다.
    """
    if not isinstance(subsets, dict):
        return [{"what": "subsets_not_a_dict", "type": type(subsets).__name__}]
    problems = []
    for k in SUBSET_KEYS:
        if k not in subsets:
            problems.append({"what": f"subset_{k}_missing_key"})
    extra = sorted(set(subsets) - set(SUBSET_KEYS))
    if extra:
        problems.append({"what": "subset_unexpected_keys", "keys": extra})
    try:
        expected = fixed_subsets(reqs)
    except (KeyError, IndexError, ValueError, TypeError) as e:
        return problems + [{"what": "subsets_not_regenerable", "error": repr(e)[:200]}]
    for k in SUBSET_KEYS:
        if k not in subsets:
            continue
        got = subsets[k]
        if not isinstance(got, list) or not all(isinstance(i, str) for i in got):
            problems.append({"what": f"subset_{k}_not_a_list_of_ids"})
            continue
        if len(got) != len(set(got)):
            problems.append({"what": f"subset_{k}_duplicate_ids", "n": len(got) - len(set(got))})
        missing = sorted(set(expected[k]) - set(got))
        added = sorted(set(got) - set(expected[k]))
        if missing or added:
            problems.append({"what": f"subset_{k}_differs_from_regenerated", "n_expected": len(expected[k]),
                             "n_stored": len(got), "missing": missing[:5], "added": added[:5]})
    return problems


def _load_required(out, name, loader, problems):
    path = os.path.join(out, name)
    if not os.path.exists(path):
        problems.append({"what": "required_file_missing", "file": name})
        return None
    try:
        return loader(path)
    except (ValueError, OSError) as e:  # JSON 파싱 실패 포함
        problems.append({"what": "required_file_unreadable", "file": name, "error": repr(e)[:200]})
        return None


def check_manifest(out, data_dir=DATA_DIR):
    """config·request 본문 hash와 현재 실제 입력을 재계산해 저장된 manifest 전체와 대조한다.

    iter_006: 필수 파일 누락·파싱 실패도 PreflightError로 올리고, 고정 부분집합을 결정적으로 재생성해 대조한다.
    반환: (cfg, chash, reqs, info, subsets). 불일치가 하나라도 있으면 PreflightError.
    """
    cfg = build_config()
    chash = config_hash(cfg)
    problems = []
    load_json = lambda p: json.load(open(p))  # noqa: E731
    stored_cfg = _load_required(out, "config.json", load_json, problems)
    reqs = _load_required(out, "requests.jsonl", read_jsonl, problems)
    info = _load_required(out, "image_info.json", load_json, problems)
    subsets = _load_required(out, "subsets.json", load_json, problems)
    if problems:
        raise PreflightError("manifest", problems)
    if stored_cfg.get("config_sha256") != chash:
        problems.append({"what": "config_hash_changed", "stored": stored_cfg.get("config_sha256"), "current": chash})
    ids = [r["id"] for r in reqs]
    if len(ids) != len(set(ids)):
        problems.append({"what": "duplicate_request_id", "n": len(ids) - len(set(ids))})
    for r in reqs:
        if request_body_hash(r) != r.get("request_sha256"):
            problems.append({"what": "request_body_hash_mismatch", "id": r["id"]})
        if r.get("config_sha256") != chash:
            problems.append({"what": "request_config_mismatch", "id": r["id"]})
    # 현재 파일에서 manifest를 다시 만든다 (모든 요청: 완료 여부와 무관)
    images = sorted(info)
    missing_files = [f for f in images if not os.path.exists(os.path.join(data_dir, f))]
    cur_reqs = None
    if missing_files:
        problems.append({"what": "missing_source_files", "files": missing_files})
    else:
        cur_reqs, cur_info = build_requests(data_dir=data_dir, images=images, cfg=cfg)
        for f in images:
            for k in ("source_file_sha256", "source_pixel_sha256", "width", "height", "input_pixel_sha256"):
                if cur_info[f][k] != info[f].get(k):
                    problems.append({"what": f"image_info_{k}_changed", "file": f})
        cur_by = {r["id"]: r for r in cur_reqs}
        for r in reqs:
            c = cur_by.get(r["id"])
            if c is None:
                problems.append({"what": "request_not_reproducible", "id": r["id"]})
            elif c != r:
                diff = sorted(k for k in set(c) | set(r) if c.get(k) != r.get(k))
                problems.append({"what": "request_differs_from_current_inputs", "id": r["id"], "fields": diff})
        extra = sorted(set(cur_by) - set(ids))
        if extra:
            problems.append({"what": "manifest_missing_requests", "n": len(extra)})
    # 현재 입력에서 재계산한 requests가 있으면 그것으로 부분집합을 재생성한다 (저장본 reqs를 믿지 않음)
    problems += check_subsets(subsets, cur_reqs if cur_reqs is not None else reqs)
    if problems:
        raise PreflightError("manifest", problems)
    return cfg, chash, reqs, info, subsets


def predictions_digest(valid, chash):
    """주평가·민감도·검증에 쓰는 모든 결과 필드(RESULT_FIELDS)와 config hash를 묶은 digest.

    비결과 metadata(seconds, ts, phase)는 포함하지 않는다: 같은 결과의 재실행 시간 차이로 selection이
    무효화되지 않게 하기 위함이다.
    """
    body = {"config_sha256": chash,
            "results": {k: {f: valid[k][f] for f in RESULT_FIELDS} for k in sorted(valid)},
            "request_sha256": {k: valid[k]["request_sha256"] for k in sorted(valid)}}
    return hashlib.sha256(json.dumps(body, sort_keys=True, allow_nan=False).encode()).hexdigest()


def _finite(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def check_verification(ver_records, ver_ids, reqs, valid, chash):
    """지정 ID 집합·누락·중복·충돌·hash·수치 기준 검사. 실패 목록을 반환한다 (빈 목록이면 통과)."""
    problems = []
    req_by = {r["id"]: r for r in reqs}
    want = set(ver_ids)
    by_id = {}
    for x in ver_records:
        rid = x.get("id")
        if rid not in want:
            problems.append({"what": "unexpected_verification_id", "id": rid})
            continue
        miss = [f for f in VER_REQUIRED_FIELDS if f not in x]
        if miss:
            problems.append({"what": "verification_missing_fields", "id": rid, "fields": miss})
            continue
        nonfin = [f for f in VER_NUMERIC_FIELDS if f in x and not _finite(x[f])]
        if nonfin:
            problems.append({"what": "verification_non_finite", "id": rid, "fields": nonfin})
            continue
        if x["request_sha256"] != req_by[rid]["request_sha256"]:
            problems.append({"what": "verification_request_hash_mismatch", "id": rid})
            continue
        if x["config_sha256"] != chash:
            problems.append({"what": "verification_config_mismatch", "id": rid})
            continue
        by_id.setdefault(rid, []).append(x)
    for rid in sorted(want):
        recs = by_id.get(rid, [])
        if not recs:
            problems.append({"what": "verification_missing", "id": rid})
            continue
        if len(recs) > 1:
            keys = {json.dumps({f: r[f] for f in VER_NUMERIC_FIELDS if f in r}, sort_keys=True) for r in recs}
            problems.append({"what": "verification_conflict" if len(keys) > 1 else "verification_duplicate",
                             "id": rid, "n": len(recs)})
        x = recs[0]
        if rid not in valid:
            problems.append({"what": "verification_without_valid_prediction", "id": rid})
            continue
        if x["m_main"] != valid[rid]["m"]:
            problems.append({"what": "verification_m_main_not_current_prediction", "id": rid})
        if abs(x["m_tf"] - valid[rid]["m"]) > VER_TF_TOL or x["tf_abs_diff"] > VER_TF_TOL:
            problems.append({"what": "verification_tf_fail", "id": rid, "tf_abs_diff": x["tf_abs_diff"]})
        if abs(x["m_repeat"] - valid[rid]["m"]) > VER_REPEAT_TOL or x["repeat_abs_diff"] > VER_REPEAT_TOL:
            problems.append({"what": "verification_repeat_fail", "id": rid, "repeat_abs_diff": x["repeat_abs_diff"]})
    return problems


def check_selection(sel_all, valid, chash, reqs):
    """selection이 현재 유효 prediction과 config에 연결되는지 검사."""
    problems = []
    for k in ("predictions_digest", "config_sha256", "requests_digest"):
        if k not in sel_all:
            problems.append({"what": f"selection_missing_{k}"})
    if problems:
        return problems
    if sel_all["config_sha256"] != chash:
        problems.append({"what": "selection_config_mismatch"})
    if sel_all["predictions_digest"] != predictions_digest(valid, chash):
        problems.append({"what": "stale_selection_predictions_digest"})
    if sel_all["requests_digest"] != requests_digest(reqs):
        problems.append({"what": "selection_requests_digest_mismatch"})
    return problems


def requests_digest(reqs):
    return hashlib.sha256("\n".join(r["request_sha256"] for r in reqs).encode()).hexdigest()
