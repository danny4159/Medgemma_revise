"""iter_109 추출 규칙의 합성 fixture. 실제 출력·GT를 쓰지 않는다. 통과 후 규칙 파일 hash를 lock 파일로 저장한다(기존 파일 덮어쓰기 금지)."""
import hashlib
import json
import os
import sys
import time
from pathlib import Path

import ev109_extract as X
from rsna_diag import qa_spec

E = "<end_of_turn>"
Q = qa_spec.Q_O
# (name, target, raw, ended_eos, expected_answer, expected_source)
CASES = [
    ("bare_yes", "O", "Yes.\n" + E, True, "yes", "semantic_v1"),
    ("bare_normal_A", "A", "Normal." + E, True, "no", "semantic_v1"),
    ("bare_normal_O_rejected", "O", "Normal." + E, True, None, "unresolved"),
    ("leading_yes_explanation", "O", "Yes. There is a right lower lobe opacity.\n" + E, True, "yes", "explicit"),
    ("leading_no_explanation", "O", "No. The lungs are clear.\n" + E, True, "no", "explicit"),
    ("leading_no_comma", "A", "No, the study is unremarkable." + E, True, "no", "explicit"),
    ("leading_markdown", "O", "**Yes**\n\nThere is an opacity." + E, True, "yes", "explicit"),
    ("no_noun_phrase_start", "O", "No evidence of pneumonia is seen." + E, True, None, "unresolved"),
    ("conclusion_answer_colon", "A", "The image shows a chest tube. The image is abnormal.\n\nAnswer: Yes" + E, True, "yes", "explicit"),
    ("conclusion_therefore", "O", "A lobar process is described.\n\nTherefore, the answer is yes." + E, True, "yes", "explicit"),
    ("conclusion_final", "A", "Final answer: no" + E, True, "no", "explicit"),
    ("conclusion_repeat_same", "O", "Yes. Opacity present.\n\nAnswer: Yes" + E, True, "yes", "explicit"),
    ("lead_conclusion_conflict", "O", "Yes. Opacity.\n\nFinal answer: no" + E, True, None, "unresolved"),
    ("two_conclusions_conflict", "O", "Answer: yes\nAnswer: no" + E, True, None, "unresolved"),
    ("quoted_answer", "O", 'The reader said "the answer is yes" but this is unverified.' + E, True, None, "unresolved"),
    ("code_fence", "O", "```\nAnswer: yes\n```" + E, True, None, "unresolved"),
    ("blockquote", "O", "> Answer: yes" + E, True, None, "unresolved"),
    ("question_echo_only", "O", Q + E, True, None, "unresolved"),
    ("question_echo_with_answer", "O", Q + "\nAnswer: yes" + E, True, None, "unresolved"),
    ("possibly_yes", "O", "Possibly yes." + E, True, None, "unresolved"),
    ("yes_possibly", "O", "Yes. This could possibly be pneumonia." + E, True, None, "unresolved"),
    ("if_conditional", "O", "If there is fever, the answer is yes." + E, True, None, "unresolved"),
    ("opposite_token_in_text", "O", "Yes. There is no pleural effusion." + E, True, None, "unresolved"),
    ("conclusion_with_opposite_no", "A", "There is no pneumothorax.\n\nAnswer: Yes" + E, True, None, "unresolved"),
    ("explanation_no_answer", "A", "The image appears to be a chest radiograph with subtle findings." + E, True, None, "unresolved"),
    ("image_is_abnormal_sentence", "A", "The image is abnormal." + E, True, None, "unresolved"),
    ("not_eos", "O", "Yes. Opacity present", False, None, "unresolved"),
    ("empty", "O", E, True, None, "unresolved"),
    ("bbox_list", "O", '[{"box_2d":[1,2,3,4]}]' + E, True, None, "unresolved"),
    ("answer_mid_sentence", "O", "I think the answer is yes because of the opacity." + E, True, None, "unresolved"),
]


def main():
    out_dir = Path("results/iter_109/tests")
    out_dir.mkdir(parents=True, exist_ok=True)
    res, ok_all = [], True
    for name, tg, raw, eos, exp_a, exp_src in CASES:
        r = X.resolve(tg, raw, eos)
        ok = r["answer"] == exp_a and r["source"] == exp_src
        r2 = X.resolve(tg, raw, eos)
        ok = ok and r == r2  # 결정성: 동일 입력 동일 출력
        ok_all &= ok
        res.append(dict(name=name, ok=ok, expected=[exp_a, exp_src], got=[r["answer"], r["source"], r["reason"]]))
    # 인터페이스에 GT/조건이 없음: resolve 시그니처 확인
    import inspect
    sig = list(inspect.signature(X.resolve).parameters)
    res.append(dict(name="signature_no_gt", ok=sig == ["target", "raw", "ended_eos"], got=sig))
    ok_all &= res[-1]["ok"]
    summary = dict(version=X.RULES_VERSION, n=len(res), n_pass=sum(r["ok"] for r in res), all_pass=bool(ok_all), results=res)
    print(summary["n_pass"], "/", summary["n"])
    for r in res:
        if not r["ok"]:
            print("FAIL", r)
    if ok_all:
        p = out_dir / "fixtures_extract.json"
        if p.exists():
            sys.exit("fixtures_extract.json exists; not overwriting")
        p.write_text(json.dumps(summary, indent=1, ensure_ascii=False))
        lock = out_dir.parent / "extract_lock.json"
        if lock.exists():
            sys.exit("lock exists")
        files = {f: hashlib.sha256(open(f, "rb").read()).hexdigest() for f in ("ev109_extract.py", "test_ev109_extract.py", "ev108_spec.py", "rsna_diag/qa_spec.py")}
        lock.write_text(json.dumps(dict(locked_at_unix=time.time(), locked_at=time.strftime("%Y-%m-%dT%H:%M:%S%z"), rules_version=X.RULES_VERSION,
                                        files_sha256=files, note="GT 연결 전 잠금. 이후 규칙 변경 금지."), indent=1))
        print("locked", files)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
