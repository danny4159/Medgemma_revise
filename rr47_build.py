"""iter_047 자료 확정·요청 생성 (CPU only, 모델 출력 미사용).

python rr47_build.py feasibility           # 후보 열거·의미 검토표·층별 가용량·계획 quota 충족 여부 (results/iter_047/data/)
python rr47_build.py build D8              # D8 manifest·영상·요청 (D 층: 00/01/10/11 각 2명)
python rr47_build.py build E               # 계획 quota(각 24)를 채울 수 있을 때만. 못 채우면 gate만 기록하고 exit 3 (broad negative·reserve를 열지 않는다)
영상 규약은 iter_039/042와 동일: uint16 >> 8, 값 보존 RGB 복제, 중앙 square padding. 기존 파일은 덮어쓰지 않는다.
"""
import hashlib
import io
import json
import os
import re
import sys
from collections import Counter, defaultdict

import numpy as np
from PIL import Image

import pg39_data as D
import rr47_data as R
import rr47_spec as S
from rsna_diag import generate as G
from rsna_diag import geometry

OUT = "results/iter_047"
CONVENTION = "uint16 -> uint8 by right shift 8 (iter_039/042와 동일); no window/min-max/flip"
PLAN_QUOTA = {"D8": {"00": 2, "01": 2, "10": 2, "11": 2}, "E": {"00": 24, "01": 24, "10": 24, "11": 24}}
PRIOR_FILES = ["results/iter_039/data/manifest_private.jsonl", "results/iter_040/data/manifest_train_private.jsonl",
               "results/iter_040/data/manifest_eval_private.jsonl", "results/iter_042/data/manifest_private.jsonl",
               "results/iter_043/data/manifest_private.json"]


def sha(b):
    return hashlib.sha256(b).hexdigest()


def file_sha(p):
    return D.sha256_file(p)


def protected_ids():
    """H192 환자(E192)와 F120 환자는 열지 않는다. 기존 manifest의 PatientID만 읽는다."""
    h192 = {json.loads(x)["PatientID"] for x in open("results/iter_040/data/manifest_eval_private.jsonl")
            if json.loads(x)["eval_set"] == "H192"}
    f120 = {json.loads(x)["PatientID"] for x in open("results/iter_039/data/manifest_private.jsonl") if json.loads(x)["set"] == "F"}
    return h192, f120


def prior_seen():
    """기존 개발 집단과의 중복 표시용 (환자 ID·영상 pixel hash). 독립 확인이라고 부르지 않는다."""
    pats, pix = set(), set()
    for p in PRIOR_FILES:
        t = open(p).read()
        pats |= set(re.findall(r'"PatientID": "([^"]+)"', t))
        pix |= set(re.findall(r'"u8_pixel_sha256": "([0-9a-f]{64})"', t))
    return pats, pix


def orient(cand, code):
    """후보 -> qA/qB에 finding·상태를 배정. code가 '01'이면 qA=absent, qB=present. 같은 상태끼리(00/11)는 해시 parity로 배정."""
    f, st, se, ss = cand["findings"], cand["states"], cand["sentences_en"], cand["sentences_es"]
    want = S.code_states(code)
    order = None
    if st[0] != st[1]:
        order = [0, 1] if st[0] == want[0] else [1, 0]
    else:
        order = [0, 1] if int(D.h(S.SEED, cand["ImageID"], "assign"), 16) % 2 == 0 else [1, 0]
    q = {}
    for qi, oi in zip(S.IDS, order):
        q[qi] = dict(finding=f[oi], state=st[oi], sentence_en=se[oi], sentence_es=ss[oi], idx=cand["idx"][oi])
    return q


def feasibility(per_pat):
    cnt = Counter()
    by_pat = defaultdict(set)
    for pid, cs in per_pat.items():
        for c in cs:
            by_pat[R.truth_stratum(c["states"])].add(pid)
    for k, v in by_pat.items():
        cnt[k] = len(v)
    return dict(patients_by_truth_group=dict(cnt))


def select(per_pat, quotas, used=()):
    """희소 층(mixed) 우선, 층 안에서는 finding 쌍 그룹을 번갈아 순서대로 뽑는다(그룹 내 hash 순). returns {code: [selected]}."""
    used = set(used)
    out = {}
    groups_order = [("01", "mixed"), ("10", "mixed"), ("00", "neg2"), ("11", "pos2")]
    for code, grp in groups_order:
        n = quotas.get(code, 0)
        pools = defaultdict(list)
        for pid, cs in per_pat.items():
            if pid in used:
                continue
            for c in cs:
                if R.truth_stratum(c["states"]) == grp:
                    pools[tuple(c["findings"])].append(c)
        for k in pools:
            pools[k].sort(key=lambda c: D.h(S.SEED, code, c["PatientID"], c["ImageID"], c["findings"]))
        gkeys = sorted(pools, key=lambda k: D.h(S.SEED, code, k))
        chosen = []
        while len(chosen) < n:
            progressed = False
            for k in gkeys:
                while pools[k] and pools[k][0]["PatientID"] in used:
                    pools[k].pop(0)
                if pools[k] and len(chosen) < n:
                    c = pools[k].pop(0)
                    chosen.append(c)
                    used.add(c["PatientID"])
                    progressed = True
            if not progressed:
                break
        out[code] = chosen
    return out


def extract(z, idx, iid, img_dir):
    zi = idx[iid]
    raw = z.read(zi)
    a = np.asarray(Image.open(io.BytesIO(raw)))
    if a.dtype != np.uint16 or a.ndim != 2:
        raise D.InputError(f"{iid}: unexpected image dtype/shape {a.dtype} {a.shape}")
    b = (a >> 8).astype(np.uint8)
    path = os.path.join(img_dir, iid)
    os.makedirs(img_dir, exist_ok=True)
    if not os.path.exists(path):
        tmp = path + f".{os.getpid()}.tmp.png"
        Image.fromarray(b).save(tmp)
        os.replace(tmp, path)
    h, w = a.shape
    return dict(path=path, zip_member=zi.filename, zip_crc=zi.CRC, raw_png_sha256=sha(raw), u16_pixel_sha256=sha(a.tobytes()),
                u8_pixel_sha256=sha(b.tobytes()), h=h, w=w, file_sha256=file_sha(path))


def write_new(path, text):
    if os.path.exists(path):
        raise FileExistsError(path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + f".{os.getpid()}.tmp"
    with open(tmp, "w") as f:
        f.write(text)
    os.replace(tmp, path)


def make_requests(rows, with_oracle):
    """manifest rows -> 요청 행 (환자별 R1/R2/T 4 draft + BJ 1 + BI 2 [+ O 4]). 정답/corruption 여부는 prompt·ID에 넣지 않는다."""
    reqs = []
    for m in rows:
        q = m["q"]
        fp = {i: q[i]["finding"] for i in S.IDS}
        img = m["image_meta"]["path"]
        fsha = m["image_meta"]["file_sha256"]
        px = G.load_image(img)[2]
        base = dict(kind="rr47", patient=m["PatientID"], caps=S.CAPS, donor_patient=None)

        def add(cond, targets, prompt, modality, draft=None):
            psha = S.sha(prompt)
            rid = S.request_id("rr47", m["PatientID"], cond, targets, psha, px if modality == "image" else "text")
            r = dict(base, request_id=rid, cond=cond, targets=list(targets), prompt=prompt, prompt_sha256=psha, modality=modality, draft=draft,
                     image=img if modality == "image" else None, image_file_sha256=fsha if modality == "image" else None,
                     input_pixel_sha256=px if modality == "image" else None,
                     order_key=S.sha(f"{S.SEED}|{rid}")[:16])
            reqs.append(r)

        for code in S.DRAFT_CODES:
            items = S.draft_text(fp, code)
            add(f"R1_d{code}", S.IDS, S.prompt_R1(items), "image", code)
            add(f"R2_d{code}", S.IDS, S.prompt_R2(items), "image", code)
            add(f"T_d{code}", S.IDS, S.prompt_T(items), "text", code)
        add("BJ", S.IDS, S.prompt_BJ(fp), "image")
        for i in S.IDS:
            add(f"BI_{i}", [i], S.prompt_BI(fp[i], i), "image")
        if with_oracle:
            truth = [(i, q[i]["state"]) for i in S.IDS]
            for code in S.DRAFT_CODES:
                add(f"O_d{code}", S.IDS, S.prompt_O(S.draft_text(fp, code), truth), "image", code)
    ids = [r["request_id"] for r in reqs]
    assert len(ids) == len(set(ids))
    return reqs


def main():
    cmd = sys.argv[1]
    os.makedirs(f"{OUT}/data", exist_ok=True)
    reports, master, links = D.load_inputs()
    h192, f120 = protected_ids()
    per_pat, review, cnt = R.enumerate_pairs(reports, links, "train", banned_patients=h192 | f120)
    feas = feasibility(per_pat)
    if cmd == "feasibility":
        pats, pix = prior_seen()
        acc = Counter(r["rule"] for r in review if r["rule"])
        rej = Counter(r["reason"] for r in review if not r["rule"])
        info = dict(version=S.VERSION, protected=dict(H192=len(h192), F120=len(f120)), enumerate_counters=dict(cnt),
                    n_candidate_patients=len(per_pat), feasibility=feas, plan_quota=PLAN_QUOTA,
                    plan_total_needed_by_group=dict(mixed=PLAN_QUOTA["D8"]["01"] + PLAN_QUOTA["D8"]["10"] + PLAN_QUOTA["E"]["01"] + PLAN_QUOTA["E"]["10"],
                                                   neg2=PLAN_QUOTA["D8"]["00"] + PLAN_QUOTA["E"]["00"], pos2=PLAN_QUOTA["D8"]["11"] + PLAN_QUOTA["E"]["11"]),
                    rule_accept_counts=dict(acc), rule_reject_reasons=dict(rej), n_prior_dev_patients_seen=len(pats),
                    input_sha256=links["inputs_sha256"], spec_version=S.VERSION)
        write_new(f"{OUT}/data/feasibility.json", json.dumps(info, indent=1))
        write_new(f"{OUT}/data/review_private.json", json.dumps(dict(
            note="규칙 분류 + 출력 전 의미 검토. 검토자는 임상의가 아닌 자동화 에이전트이며 새 영상 판독이 아니다. 전체 원 보고서는 metadata에 없다.",
            veto=sorted(R.VETO), reviewed_distinct_accepted_sentences=sorted({(r["sentence_en"], r["rule"]) for r in review if r["rule"]}),
            rows=review), indent=0, default=list))
        print(json.dumps(info, indent=1))
        return
    name = sys.argv[2]
    quota = PLAN_QUOTA[name]
    if name == "E":
        # D8 환자와 겹치지 않아야 한다. D8 manifest는 먼저 확정돼 있어야 한다.
        dm = json.load(open(f"{OUT}/data/manifest_D8.json"))
        used = {m["PatientID"] for m in dm["rows"]}
        used_img = {m["ImageID"] for m in dm["rows"]}
        sel = select(per_pat, quota, used)
        short = {c: quota[c] - len(sel[c]) for c in quota if len(sel[c]) < quota[c]}
        if short:
            gate = dict(run=False, reason="data gate: planned strata cannot be filled without broad negatives/reserve", shortfall=short,
                        selected={c: len(v) for c, v in sel.items()}, feasibility=feas)
            write_new(f"{OUT}/data/E_data_gate.json", json.dumps(gate, indent=1))
            print(json.dumps(gate, indent=1))
            sys.exit(3)
    else:
        used, used_img = set(), set()
        sel = select(per_pat, quota, used)
        short = {c: quota[c] - len(sel[c]) for c in quota if len(sel[c]) < quota[c]}
        if short:
            raise SystemExit(f"D8 quota cannot be filled: {short}")
    pats_prior, pix_prior = prior_seen()
    z = D.open_image_zip()
    idx = D.zip_index(z)
    rows = []
    for code in S.DRAFT_CODES:
        for c in sel[code]:
            q = orient(c, code)
            meta = extract(z, idx, c["ImageID"], f"{OUT}/data/images")
            rows.append(dict(set=name, truth_code=code, PatientID=c["PatientID"], ImageID=c["ImageID"], StudyID=c["StudyID"], q=q, image_meta=meta,
                             pad_top_left_side=list(geometry.pad_offsets(meta["h"], meta["w"])),
                             patient_seen_in_prior_dev=c["PatientID"] in pats_prior, pixel_seen_in_prior_dev=meta["u8_pixel_sha256"] in pix_prior))
    for k in ("PatientID", "StudyID", "ImageID"):
        assert len({r[k] for r in rows}) == len(rows), f"duplicate {k}"
    assert len({r["image_meta"]["u8_pixel_sha256"] for r in rows}) == len(rows), "duplicate pixel"
    if name == "E":
        assert not ({r["ImageID"] for r in rows} & used_img)
    manifest = dict(set=name, convention=CONVENTION, spec_version=S.VERSION, quota=quota, rows=rows,
                    raw_inputs_sha256=links["inputs_sha256"], protected_excluded=dict(H192=len(h192), F120=len(f120)))
    write_new(f"{OUT}/data/manifest_{name}.json", json.dumps(manifest, indent=1))
    reqs = make_requests(rows, with_oracle=(name == "D8"))
    write_new(f"{OUT}/requests/requests_{name}.jsonl", "".join(json.dumps(r, sort_keys=True) + "\n" for r in reqs))
    print(name, "patients", len(rows), "requests", len(reqs), Counter(r["cond"].split("_")[0] for r in reqs))


if __name__ == "__main__":
    main()
