"""iter_099: 환자 index별 reference 사실·초안·영역 설명 본문을 출력한다 (읽기 전용 검토 보조)."""
import json
import sys

import report98_data as D


def main(pis, max_body=400):
    R = D.load_readings()
    am = json.load(open(D.REF_AMEND))["patients"]
    idx = {am[i]["patient_index"]: i for i in D.abnormal_ids()}
    for pi in pis:
        i = idx[pi]
        pk = D.package(i, R)
        print("=====P%03d %s" % (pi, i))
        for f in am[i]["facts"]:
            print(" FACT", f["fact_id"], f["v2_class"], "|", f["sentence_en"])
        print(" DRAFT:", pk["draft"])
        for g in pk["groups"]:
            print(" ", g["gid"], g["regions"][:2], len(g["regions"]), "|", g["body"][:max_body])


if __name__ == "__main__":
    main([int(x) for x in sys.argv[1:]])
