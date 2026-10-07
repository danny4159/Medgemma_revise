"""iter_096 산출물 봉인: 최종 사용 파일(코드·입력·판정·보고·검증)의 sha256 목록을 completion.json으로 저장한다(새 파일만)."""
import sys
import time

from report96_lock import R96, ROOT
from report86_common import save, sha

CODE = ['report96_sem.py', 'report96_ref.py', 'report96_lock.py', 'report96_eval.py', 'report96_verify.py', 'report96_diff.py',
        'report96_review.py', 'report96_decide.py', 'report96_seal.py', 'test_report96.py']


def main(ver, rtag, tests):
    files = {c: sha(ROOT / c) for c in CODE}
    for rel in ('lock/input_manifest.json', f'judging/judgments_E32_{ver}.json', f'judging/sentence_review_{ver}.json', f'judging/case_review_E32_{ver}.json',
                f'eval/report_E32_{ver}{rtag}.json', f'eval/verify_E32_{ver}{rtag}.json', f'eval/correction_diff_E32_{ver}{rtag}.json',
                f'eval/decision_E32_{ver}{rtag}.json', f'tests/{tests}'):
        files['results/iter_096/' + rel] = sha(R96 / rel)
    save(R96 / f'completion_{ver}{rtag}.json', {'sealed_at': time.strftime('%Y-%m-%d %H:%M:%S'), 'final_version': ver + rtag, 'files': files,
                                              'superseded_drafts': 'judgments_E32.json, judgments_E32_v1/v2.json, report_E32*.json(v1,v2,v3 무태그) 등은 개발 이력으로 보존(최종 아님)'})
    print(len(files))


if __name__ == '__main__':
    main(*sys.argv[1:4])
