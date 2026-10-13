"""iter_138 자료 재연결 (CPU): iter_137이 만든 D6/E45 manifest·요청을 새로 선정하지 않고 재연결한다.
i137_data.link()로 iter_136 PNG의 hash·역할·D/E 비중복·annotation 면적·원 NIfTI hash를 다시 검사하고, 결과 rows가 iter_137 manifest와 같고
make_requests 결과가 iter_137 요청 파일과 byte 수준으로 같은지 확인한 뒤 iter_138 경로에 새 파일로 저장한다. 새 표본 선정·재렌더 없음."""
import sys
from i138_common import RES, DATA, OLD137, sha, read, save, now
import i137_data as D137


def main():
    m, rows, checks = D137.link()
    old = read(OLD137 / 'data/manifest.json')
    problems = list(checks['problems'])
    if rows != old['rows']: problems.append('rows_differ_from_iter137_manifest')
    for s, f in (('D', 'technical'), ('E', 'main')):
        mine = D137.make_requests(rows[s]); theirs = read(OLD137 / ('requests/%s.json' % f))
        if mine != theirs: problems.append('requests_differ_from_iter137_' + f)
    checks = dict(checks, problems=problems)
    run = not problems
    save(DATA / 'manifest.json', dict(created_at=now(), source='results/iter_137/data/manifest.json + results/iter_136/data/manifest.json(읽기 전용)', iter137_manifest_sha256=sha(OLD137 / 'data/manifest.json'),
                                       checks=checks, run_models=run, rows=rows,
                                       note='반복 개발 자료(MSD Task01 FLAIR). 독립 test 아님. N1은 annotation 면적 0 slice이며 임상 정상이 아니다. P는 GT 기반 선택이다.'))
    if run:
        save(RES / 'requests/technical.json', read(OLD137 / 'requests/technical.json')); save(RES / 'requests/main.json', read(OLD137 / 'requests/main.json'))
    print('run', run, {k: v for k, v in checks.items() if k != 'excluded_in_iter136'})
    return 0 if run else 1


if __name__ == '__main__':
    sys.exit(main())
