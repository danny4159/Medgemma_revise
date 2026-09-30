"""세 prompt의 원문 고정 (iter_009 계획).

- official_long: 보존한 공식 notebook 셀 11의 f-string을 그대로 평가하여 object_name만 치환한다.
- concise: 계획서에 고정된 원문.
- legacy_detect: legacy/scripts/04_official_format/rerun_localization_official.py의 DETECT 문자열을 ast로 추출하고 동일 target을 치환한다.
"""
import ast
import hashlib
import json
import re

TARGET = "pulmonary opacity suspicious for pneumonia"
NOTEBOOK = "results/iter_009/source/official/cxr_anatomy_localization_with_hugging_face.ipynb"
LEGACY_SCRIPT = "/SSD1_1TB/home/milab/daniel/08_medgemma/legacy/scripts/04_official_format/rerun_localization_official.py"

CONCISE = ('Localize all pulmonary opacities suspicious for pneumonia in this chest radiograph. Return only a JSON list. '
           'Each entry must contain "box_2d": [y_min, x_min, y_max, x_max] and a nonempty "label" string. '
           'Coordinates must be between 0 and 1000 relative to the entire square-padded image, with y before x. '
           'Return [] if no such opacity is visible.')


def official_long(target=TARGET, notebook=NOTEBOOK):
    nb = json.load(open(notebook))
    for c in nb["cells"]:
        src = "".join(c["source"])
        if c["cell_type"] == "code" and 'prompt = f"""' in src:
            m = re.search(r'prompt = f"""(.*?)"""', src, re.S)
            return eval('f"""' + m.group(1) + '"""', {"object_name": target})
    raise RuntimeError("official prompt cell not found")


def legacy_detect(target=TARGET, script=LEGACY_SCRIPT):
    tree = ast.parse(open(script).read())
    for n in tree.body:
        if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", None) == "DETECT":
            return ast.literal_eval(n.value).format(obj=target)
    raise RuntimeError("DETECT not found")


def all_prompts():
    return {"official_long": official_long(), "concise": CONCISE, "legacy_detect": legacy_detect()}


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()
