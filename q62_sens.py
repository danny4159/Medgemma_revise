"""iter_062 사후 민감도(형식): 마지막 비공백 줄이 '[**]ANSWER: X[**]'(대소문자 무시, 굵게 표시 허용)인 경우도 유효로 인정.
양 모델에 동일하게 적용하며 1차 결과(parse_v2)를 대체하지 않는다. 사후 정의이므로 탐색용이다.
사용: python q62_sens.py
"""
import re, sys
import mri61_parse as P
import q62_eval as E

_orig = P.parse_v2
LEN = re.compile(r'^\**\s*answer\s*:\s*\**\s*([A-E])\s*\**\.?$', re.I)


def lenient(text):
    a = _orig(text)
    if a:
        return a
    ls = [l.strip() for l in text.strip().splitlines() if l.strip()]
    if not ls:
        return None
    m = LEN.match(ls[-1])
    return m.group(1).upper() if m else None


P.parse_v2 = lenient
sys.argv = ['q62_eval.py', '--out', 'results/iter_062/eval/report_sensitivity_lenient_format.json']
import argparse
ap = argparse.ArgumentParser()
ap.add_argument('--requests', default='results/iter_062/data/E21_requests.jsonl')
ap.add_argument('--labels', default='results/iter_062/data/E21_labels.json')
ap.add_argument('--manifest', default='results/iter_062/data/selection_manifest.json')
ap.add_argument('--qwen-dir', default='results/iter_062/gen_E21_qwen')
ap.add_argument('--qwen-protocol', default='results/iter_062/E21_protocol.json')
ap.add_argument('--medgemma-dir', default='results/iter_061/gen_E24')
ap.add_argument('--medgemma-protocol', default='results/iter_061/E24_protocol.json')
ap.add_argument('--medgemma-requests', default='results/iter_061/E24_requests.jsonl')
ap.add_argument('--out', default='results/iter_062/eval/report_sensitivity_lenient_format.json')
E.run(ap.parse_args([]))
