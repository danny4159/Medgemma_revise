"""iter_095 실제 wrapper의 통제된 중단·재개 시험 (D8, 1 worker, 16요청).
1) --limit 6으로 정상 중단(저장 후 종료)  2) torn tail 행을 붙인 뒤 --resume  3) 완료 후 재실행(덮어쓰기·추가 저장 없음)
4) 같은 out를 --resume 없이 시작하면 거부. 기준: D8/w4 출력과 token/입력 동일. 결과는 tests/resume_result.json(새 파일)."""
import json
import os
import subprocess
import sys

from report95_common import ROOT, R95, CURE_PY, isolated_env, sha, save, read_jsonl_complete

OUT = R95 / 'D8/resume/shard0'


def run(args):
    env = isolated_env()
    env['CUDA_VISIBLE_DEVICES'] = os.environ['CUDA_VISIBLE_DEVICES']
    return subprocess.run([str(CURE_PY), str(ROOT / 'report95_gen.py'), '--stage', 'D8', '--gpu', sys.argv[1], '--out', str(OUT),
                           '--shard', '0', '--nshards', '1'] + args, cwd=ROOT, env=env, capture_output=True, text=True)


def main():
    res = {}
    r1 = run(['--limit', '6'])
    n1 = len(read_jsonl_complete(OUT / 'outputs.jsonl'))
    res['step1_limit6'] = {'rc': r1.returncode, 'n_saved': n1, 'completion_exists': (OUT / 'completion.json').exists()}
    with (OUT / 'outputs.jsonl').open('a') as f:
        f.write('{"id": "partial-torn-row')
    r2 = run(['--resume'])
    recs = read_jsonl_complete(OUT / 'outputs.jsonl')
    res['step2_resume'] = {'rc': r2.returncode, 'n_complete': len(recs), 'completion_exists': (OUT / 'completion.json').exists(),
                           'stderr_tail': r2.stderr[-200:]}
    before = {f: sha(OUT / f) for f in ('outputs.jsonl', 'completion.json')}
    r3 = run(['--resume'])
    after = {f: sha(OUT / f) for f in ('outputs.jsonl', 'completion.json')}
    res['step3_rerun_completed'] = {'rc': r3.returncode, 'unchanged': before == after}
    r4 = run([])
    res['step4_no_resume_refused'] = {'rc': r4.returncode, 'refused': r4.returncode != 0 and 'FileExistsError' in r4.stderr}
    # 비교: w4 기준 출력
    ref = {}
    for s in (R95 / 'D8/w4').glob('shard*'):
        for r in read_jsonl_complete(s / 'outputs.jsonl'):
            ref[r['id']] = r
    diff = [r['id'] for r in recs if r['attempts'][-1]['suffix_ids'] != ref[r['id']]['attempts'][-1]['suffix_ids']
            or r['input_ids'] != ref[r['id']]['input_ids']]
    res['compare_to_w4'] = {'n': len(recs), 'n_ids_equal_set': {r['id'] for r in recs} == set(ref), 'n_mismatch': len(diff), 'mismatch': diff,
                            'ids_unique': len({r['id'] for r in recs}) == len(recs)}
    res['all_pass'] = (res['step1_limit6']['rc'] == 0 and n1 == 6 and not res['step1_limit6']['completion_exists']
                       and res['step2_resume']['rc'] == 0 and res['step2_resume']['n_complete'] == 16 and res['step2_resume']['completion_exists']
                       and res['step3_rerun_completed']['unchanged'] and res['step4_no_resume_refused']['refused']
                       and not diff and res['compare_to_w4']['ids_unique'])
    save(R95 / 'tests/resume_result.json', res)
    print(json.dumps(res, indent=1))


if __name__ == '__main__':
    main()
