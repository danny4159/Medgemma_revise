"""iter_100: 지정 환자의 reference fact·초안·영역 본문 그룹을 텍스트로 출력한다(읽기 전용)."""
import json
import sys

import report98_data as D


def show(pis, maxlen=400):
    ids = D.abnormal_ids()
    R = D.load_readings()
    am = json.load(open(D.REF_AMEND))["patients"]
    by = {am[i]["patient_index"]: i for i in ids}
    for pi in pis:
        i = by[pi]
        pk = D.package(i, R)
        print("PATIENT", pi, i)
        print(" DRAFT:", pk["draft"])
        for f in am[i]["facts"]:
            print("  ", f["fact_id"], f["sentence_en"], "|", f["v2_class"], f["attr_req"], f["loc_req"])
        for g in pk["groups"]:
            print("  ", g["gid"], g["regions"], "|", g["body"][:maxlen])


if __name__ == "__main__":
    show([int(x) for x in sys.argv[1:]])
