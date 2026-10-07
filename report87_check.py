"""부분 판정 파일 구문·대응 검사(점수 계산·저장 없음). python report87_check.py <part files...>"""
import sys
from pathlib import Path

import report86_eval as E1
import report87_eval as E
from report86_common import R86
from report86_view import load


def main(paths):
    rows, reads, v1refs = load('E96')
    amend = E.load_amend()
    v1j = E1.parse_judgments((R86 / 'E96/judgments_E96_v2.txt').read_text(), rows, v1refs)
    ok = True
    for p in paths:
        try:
            jud = E.parse_v3(Path(p).read_text(), rows, amend, reads, v1j, subset=True)
            n_cl = sum(len(o['claims']) for d in jud.values() for o in d.values())
            n_i = sum(len(o['internal']) for d in jud.values() for o in d.values())
            print('OK', Path(p).name, 'patients', len(jud), 'claim lines', n_cl, 'internal', n_i)
        except E.JudgmentError as e:
            ok = False
            print('ERR', Path(p).name, e)
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main(sys.argv[1:])
