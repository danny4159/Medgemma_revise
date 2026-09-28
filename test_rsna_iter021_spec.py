"""iter_021 mi19_spec 회귀 검사: D8 v1 실행에서 발견된 box_str 형식 문제(참조 box를 bare JSON
list로 보여주면 모델이 답변에서도 요구된 {"box_2d":...,"label":...} 구조를 생략)의 재발 방지.
box_str이 더 이상 대괄호로 시작하는 bare list를 반환하지 않고, 좌표 값 자체는 보존하는지 확인한다.
"""
import json

from rsna_diag import mi19_spec as S

RESULT_DIR = "results/iter_021/tests"
results = []


def check(name, cond, detail=None):
    results.append({"name": name, "pass": bool(cond), "detail": detail})


def test_box_str_not_bare_json_list():
    s = S.box_str([220, 469, 333, 757])
    check("box_str_no_leading_bracket", not s.strip().startswith("["), s)
    check("box_str_contains_values", all(str(v) in s for v in (220, 469, 333, 757)), s)
    check("box_str_has_corner_labels", "top-left" in s and "bottom-right" in s, s)


def test_prompts_do_not_contain_bare_box_json():
    ref = [220, 469, 333, 757]
    bare_list_json = json.dumps(ref)
    for name, fn in [("J_RT", S.prompt_J_RT), ("J_TR", S.prompt_J_TR), ("S1", S.prompt_S1), ("A", S.prompt_A)]:
        p = fn(ref)
        check(f"{name}_no_bare_box_json_list", bare_list_json not in p, p[:200])
        if name != "S1":  # S1 is describe-only (DESCRIBE_INSTR), it must NOT ask for box_2d output
            check(f"{name}_has_output_instr", "box_2d" in p and '"label": "referenced vertebra"' in p)
        else:
            check("S1_is_describe_only_no_box_2d", "box_2d" not in p and "Do not output coordinates" in p)


def test_prompt_O_unchanged_point_format():
    # O was 100% valid in D8 v1 (single image, point not box) -- keep its point format unchanged.
    p = S.prompt_O([500, 500])
    check("O_still_uses_bracket_point", "[500,500]" in p, p[:200])


for fn in [test_box_str_not_bare_json_list, test_prompts_do_not_contain_bare_box_json,
           test_prompt_O_unchanged_point_format]:
    fn()

n_pass = sum(1 for r in results if r["pass"])
out = {"n": len(results), "n_pass": n_pass, "results": results}
print(json.dumps(out, indent=1, default=str))
import os
os.makedirs(RESULT_DIR, exist_ok=True)
json.dump(out, open(f"{RESULT_DIR}/fixtures_spec021.json", "w"), indent=1, default=str)
assert n_pass == len(results), "some fixtures failed"
