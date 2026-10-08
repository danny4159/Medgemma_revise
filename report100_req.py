"""iter_100 교정 요청 구성: N(근거 없음) / T(영역 본문) / L(같은 본문 + 실제 질의 영역 이름). K/A는 GPU 요청 없음.

모델 입력에는 reference·P/Q·평가 라벨·정답 bbox를 넣지 않는다. 영역 본문은 29개 전부(좌표·헤더 제거, 공백 정규화, 정확 중복 제거만).
"""
import argparse
import hashlib
import json
import re
from pathlib import Path

import report98_data as D
from report86_common import save, sha, sha_obj

ROOT = D.ROOT
OUT = ROOT / "results" / "iter_100"
LOCK = OUT / "data" / "eligibility_decision.json"
D8_INPUTS = ROOT / "results" / "iter_085" / "D8" / "inputs.json"
D8_READINGS = ROOT / "results" / "iter_086" / "D8" / "readings.jsonl"
CONDS = ["N", "T", "L"]

HEAD = "Below is a draft report for the attached chest X-ray.\n\nDraft report:\n%s\n\nAutomatically generated region notes (they may be incorrect):\n%s\n\n"
TASK = ("Task: Review the draft report against the image. Keep every statement of the draft that is supported by the image. "
        "Change or add a statement only when the image or a note supports it, and do not copy note statements that you cannot verify on the image. "
        "Output only the final revised report text.")


def notes(pk, cond):
    if cond == "N":
        return "(none)"
    lines = []
    for g in pk["groups"]:
        if cond == "T":
            lines.append("%s: %s" % (g["gid"], g["body"]))
        else:
            lines.append("%s (generated for region: %s): %s" % (g["gid"], "; ".join(g["regions"]), g["body"]))
    return "\n".join(lines)


def prompt(pk, cond):
    return HEAD % (pk["draft"], notes(pk, cond)) + TASK


def build_requests(items, readings):
    """items: [(ImageID, image_path, file_sha256)] -> 요청 목록(환자 순서 고정, 조건 N,T,L)과 검사 기록."""
    reqs, info = [], []
    for img, path, fsha in items:
        assert sha(path) == fsha, ("image hash mismatch", img)
        pk = D.package(img, readings)
        for c in CONDS:
            reqs.append(dict(id="%s|%s" % (img, c), image=str(path), file_sha256=fsha, prompt=prompt(pk, c)))
        info.append(dict(ImageID=img, n_groups=len(pk["groups"]), draft_chars=len(pk["draft"]),
                         body_chars=sum(len(g["body"]) for g in pk["groups"])))
    return reqs, info


def leak_check(reqs, refs):
    """요청 prompt에 reference 문장·평가 라벨이 들어갔는지(문장 전체 일치) 검사한다. 문제 목록 반환."""
    bad = []
    for r in reqs:
        img = r["id"].split("|")[0]
        for s in refs.get(img, []):
            if s.lower().strip(". ") and len(s) > 25 and s.lower() in r["prompt"].lower():
                bad.append(dict(id=r["id"], sentence=s))
        for w in ("P/Q", "reference", "ground truth", "recovery", "preservation"):
            if w in r["prompt"].lower():
                bad.append(dict(id=r["id"], word=w))
    return bad


def tl_identity(reqs, readings):
    """T/L 본문 byte 동일성(헤더 제거 후 gid와 본문이 일치), 순서 동일, L 출처 = 실제 저장 source, N 동일 template을 검사한다."""
    problems = []
    for img in sorted(set(r["id"].split("|")[0] for r in reqs)):
        pk = D.package(img, readings)
        by = dict((r["id"].split("|")[1], r) for r in reqs if r["id"].startswith(img + "|"))
        if sorted(by) != sorted(CONDS):
            problems.append(dict(img=img, problem="conditions"))
            continue
        for c in CONDS:
            if by[c]["image"] != by["N"]["image"] or by[c]["file_sha256"] != by["N"]["file_sha256"]:
                problems.append(dict(img=img, cond=c, problem="image_differs"))
            if not by[c]["prompt"].endswith(TASK) or pk["draft"] not in by[c]["prompt"]:
                problems.append(dict(img=img, cond=c, problem="template_or_draft"))
        t_lines = by["T"]["prompt"].split("(they may be incorrect):\n")[1].split("\n\n" + "Task:")[0].split("\n")
        l_lines = by["L"]["prompt"].split("(they may be incorrect):\n")[1].split("\n\n" + "Task:")[0].split("\n")
        if len(t_lines) != len(l_lines) or len(t_lines) != len(pk["groups"]):
            problems.append(dict(img=img, problem="group_count"))
            continue
        for g, tl, ll in zip(pk["groups"], t_lines, l_lines):
            tg, tb = tl.split(": ", 1)
            m = re.match(r"^(D\d\d) \(generated for region: (.*?)\): (.*)$", ll, re.S)
            if not m or tg != g["gid"] or tb != g["body"] or m.group(1) != g["gid"] or m.group(3) != tb.strip() \
                    or m.group(2).split("; ") != g["regions"]:
                problems.append(dict(img=img, gid=g["gid"], problem="T_L_mismatch"))
        if "(none)" not in by["N"]["prompt"]:
            problems.append(dict(img=img, problem="N_notes"))
    return problems


def d8_items(n=4):
    """기술 검사용 D8 4명: 총 입력(본문 길이)이 가장 긴 환자 1명 + 나머지는 sha256('report100_d8|'+ImageID) 오름차순 3명. E96과 환자/study/영상 비중복 확인."""
    d8 = json.load(open(D8_INPUTS))
    E = D.load_inputs()
    pe, se, ie = set(i["PatientID"] for i in E), set(i["StudyID"] for i in E), set(i["ImageID"] for i in E)
    R = D.load_readings(D8_READINGS)
    for i in d8:
        assert i["PatientID"] not in pe and i["StudyID"] not in se and i["ImageID"] not in ie
    size = dict((i["ImageID"], len(D.package(i["ImageID"], R)["draft"]) + sum(len(g["body"]) for g in D.package(i["ImageID"], R)["groups"])) for i in d8)
    longest = max(d8, key=lambda i: size[i["ImageID"]])
    rest = sorted([i for i in d8 if i is not longest], key=lambda i: hashlib.sha256(("report100_d8|" + i["ImageID"]).encode()).hexdigest())
    return [longest] + rest[:n - 1], R, size


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("stage", choices=["D8", "main"])
    a = ap.parse_args()
    dest = OUT / "data" / a.stage
    if a.stage == "D8":
        sel, R, size = d8_items()
        items = [(i["ImageID"], i["image"], i["file_sha256"]) for i in sel]
        meta = dict(patients=[i["ImageID"] for i in sel], input_size_chars=dict((i["ImageID"], size[i["ImageID"]]) for i in sel),
                    source_inputs=str(D8_INPUTS), source_readings=str(D8_READINGS), source_inputs_sha=sha(D8_INPUTS), source_readings_sha=sha(D8_READINGS))
        refs = {}
    else:
        dec = json.loads(LOCK.read_text())
        assert (OUT / "data" / "lock_complete.json").exists() and dec["run_generation"]
        lc = json.loads((OUT / "data" / "lock_complete.json").read_text())
        assert all(sha(OUT / "data" / n) == h for n, h in lc["files"].items())
        E = dict((i["ImageID"], i) for i in D.load_inputs())
        sel_ids = [s["ImageID"] for s in dec["selected_patients"]]
        items = [(i, E[i]["image"], E[i]["file_sha256"]) for i in sel_ids]
        R = D.load_readings()
        am = json.load(open(D.REF_AMEND))["patients"]
        refs = dict((i, [f["sentence_en"] for f in am[i]["facts"]]) for i in sel_ids)
        meta = dict(patients=sel_ids, roles=dict((s["ImageID"], s["role"]) for s in dec["selected_patients"]), lock_complete_sha=sha(OUT / "data" / "lock_complete.json"))
    reqs, info = build_requests(items, R)
    probs = leak_check(reqs, refs) + tl_identity(reqs, R)
    assert not probs, probs
    assert len(set(r["id"] for r in reqs)) == len(reqs)
    save(dest / "requests.json", reqs)
    save(dest / "manifest.json", dict(stage=a.stage, n_requests=len(reqs), requests_sha=sha(dest / "requests.json"), per_patient=info, meta=meta,
                                      checks=dict(leak_check="reference 문장/평가 단어 없음", tl_identity="T/L 본문·gid·순서 동일, L 출처=저장 source", n_conditions=3),
                                      source_sha=dict(req=sha(__file__), data=sha(ROOT / "report98_data.py"))))
    print(a.stage, len(reqs), "requests ->", dest)


if __name__ == "__main__":
    main()
