"""일관성 스캔으로 찾은 규칙 불일치를 같은 규칙으로 고친 판정 v2를 새 파일에 만든다(v1 보존). 수정은 (환자, 출력, 사실)별로 기록한다.
python report86_apply_corrections.py <in> <out> <corrections.json>
corrections.json: [{"patient":"P002","output":"O3","old":"F1=U","new":"F1=N:\"...\"","why":"..."}]
"""
import json
import sys

src, dst, cj = sys.argv[1:4]
lines = open(src).read().split('\n')
corr = json.load(open(cj))
cur = None
applied = []
for i, ln in enumerate(lines):
    if ln.startswith('P') and ln[1:].isdigit():
        cur = ln.strip()
        continue
    for c in corr:
        if cur == c['patient'] and ln.startswith(c['output'] + ':'):
            assert c['old'] in ln, (c, ln)
            lines[i] = ln.replace(c['old'], c['new'], 1)
            applied.append(c)
assert len(applied) == len(corr), 'not all corrections applied'
with open(dst, 'x') as f:
    f.write('\n'.join(lines))
print(json.dumps({'applied': len(applied)}))
