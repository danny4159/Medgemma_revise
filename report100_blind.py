"""iter_100: 완료된 main 생성(N/T/L)과 GPU 없는 K/A 텍스트를 조건명 없는 blind ID로 묶어 의미 검토용 파일을 만든다.

- 생성 stage는 completion과 요청·protocol 검증(report100_gen의 verify)을 통과해야 한다.
- K = 저장 초안(C-G), A = 초안 + 고정 중복 제거 후 영역 본문 전체(D01.. 순서, 의미 선택 없음). T/L/N은 모델 출력.
- 조건명·mapping은 private_mapping.json에만 둔다. 검토 파일에는 reference 문장·atom만 포함한다(모델 입력에는 없었음).
"""
import hashlib
import json
from pathlib import Path

import report100_gen as G  # C.OUT 패치 + verify 연결
import report98_data as D
from report86_common import save, sha

C = G.C
OUT = G.OUT


def a_text(pk):
    return pk["draft"].rstrip() + " " + " ".join(g["body"] for g in pk["groups"])


def main():
    stage = OUT / "gen" / "main"
    req = OUT / "data" / "main" / "requests.json"
    proto = json.loads((stage / "protocol.json").read_text())
    workers = json.loads((stage / "mapping.json").read_text())["workers"]
    rows, expected = C.verify(stage, str(req), proto, workers)
    assert len(rows) == len(expected) == 6 and (stage / "completion.json").exists()
    dec = json.loads((OUT / "data" / "eligibility_decision.json").read_text())
    atoms = json.loads((OUT / "data" / "atom_ledger.json").read_text())["atoms"]
    am = json.load(open(D.REF_AMEND))["patients"]
    R = D.load_readings()
    outputs, mapping = [], {}
    for sel in dec["selected_patients"]:
        img, pi = sel["ImageID"], sel["patient"]
        pk = D.package(img, R)
        texts = {"K": pk["draft"], "A": a_text(pk)}
        flags = {"K": False, "A": False}
        for c in ("N", "T", "L"):
            r = [x for x in rows if x["id"] == "%s|%s" % (img, c)]
            assert len(r) == 1
            texts[c] = r[0]["text"]
            flags[c] = not r[0]["attempts"][-1]["ended_eos"]
        for c, t in texts.items():
            b = hashlib.sha256(("98017|iter100|%s|%s" % (img, c)).encode()).hexdigest()[:12]
            assert b not in mapping
            mapping[b] = dict(ImageID=img, patient=pi, condition=c)
            outputs.append(dict(blind_id=b, patient=pi, text=t, non_eos=flags[c], chars=len(t)))
    outputs.sort(key=lambda o: (o["patient"], o["blind_id"]))
    review = []
    for sel in dec["selected_patients"]:
        img, pi = sel["ImageID"], sel["patient"]
        review.append(dict(patient=pi, reference_facts=[dict(fact=f["fact_id"], sentence=f["sentence_en"], cls=f["v2_class"]) for f in am[img]["facts"]],
                           draft=D.package(img, R)["draft"], atoms_P=atoms[str(pi)]["P"], atoms_Q=atoms[str(pi)]["Q"],
                           outputs=[o for o in outputs if o["patient"] == pi]))
    dest = OUT / "eval" / "blind"
    save(dest / "private_mapping.json", mapping)
    save(dest / "review_input.json", dict(review=review, completion_sha=sha(stage / "completion.json"), source_sha=sha(__file__)))
    print(len(outputs), "blinded outputs ->", dest)


if __name__ == "__main__":
    main()
