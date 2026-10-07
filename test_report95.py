"""iter_095 CPU 검사: 실제 report95_gen의 로딩 전 검증 경로(중복·변조·잘못된 protocol·덮어쓰기)와 요청/잠금 연결.
결과는 새 파일 results/iter_095/tests/cpu_tests.json. 모델을 적재하지 않는다."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import report95_common as C
import report95_gen as G
from report95_common import R95, sha, sha_obj, save, record_digest, requests, scientific_protocol

T = R95 / 'tests'
results = []


def check(name, cond, info=None):
    results.append({'name': name, 'pass': bool(cond), 'info': info})
    print(('PASS ' if cond else 'FAIL ') + name, info or '')


def fake_rec(q, sci_digest, **kw):
    r = {'id': q['id'], 'ImageID': q['ImageID'], 'fmt': q['fmt'], 'region': q['region'], 'prompt': q['prompt'],
         'protocol_digest': sci_digest, 'text': 'x', 'attempts': [{'ended_eos': True, 'runtime_s': 1, 'peak_mem_reserved_gb': 1, 'suffix_ids': [1]}]}
    r.update(kw)
    r['record_digest'] = record_digest(r)
    return r


def write_rows(path, rows, raw=None):
    with open(path, 'w') as f:
        for r in rows:
            f.write(json.dumps(r) + '\n')
        if raw:
            f.write(raw)


def expect_fail(fn, name):
    try:
        fn()
        check(name, False, 'no exception')
    except AssertionError as e:
        check(name, True, str(e)[:80])


def main():
    sel = json.loads((C.LOCK / 'selection.json').read_text())
    # --- 요청 구성 ---
    for st, n in (('D8', 16), ('E32', 256), ('E64', 512)):
        rq = requests(st)
        check(f'requests_{st}_count', len(rq) == n and len({r['id'] for r in rq}) == n, len(rq))
    r32 = requests('E32')
    check('E32_prompts_official_describe', all(r['prompt'] == f"Describe the {r['region']}." for r in r32))
    check('D8_has_both_formats', {r['fmt'] for r in requests('D8')} == {'D', 'L'})
    check('E32_E64_disjoint_cover_E96', set(sel['E32']).isdisjoint(sel['E64']) and len(set(sel['E32']) | set(sel['E64'])) == 96)
    check('regions_8_and_broad_subset', len(C.REGIONS) == 8 and set(C.BROAD) <= set(C.REGIONS))
    src = (C.ROOT / 'results/iter_084/preflight_01/official/vlm_research_kit/data/datasets/chest_imagenome_dataset.py').read_text()
    check('official_prompt_strings_in_source', 'f"Describe the {location}."' in src and 'f"Locate and describe the {location}."' in src)
    # --- 기존 C 출력(Locate and describe) 연결 ---
    old = C.old_C_records('E96')
    miss = [(i, r) for i in sel['E32'] for r in C.REGIONS if (i, r) not in old]
    check('old_LD_available_for_E32_regions', not miss and all((i, 'G') in old for i in sel['E32']), len(miss))
    d8 = {i for i in C.stage_patients('D8')}
    oldd = C.old_C_records('D8')
    check('old_LD_available_for_D8', all((i, r) in oldd for i in d8 for r in C.D8_REGIONS), len(oldd))
    # --- 자기 행 검증 (G.load_own) ---
    sci_digest = sha_obj(scientific_protocol('D8'))
    rq = requests('D8')
    reqmap = {r['id']: r for r in rq}
    tmp = Path(tempfile.mkdtemp(dir=T if T.exists() else None))
    try:
        out = tmp / 'o'
        out.mkdir()
        good = [fake_rec(rq[0], sci_digest), fake_rec(rq[1], sci_digest)]
        write_rows(out / 'outputs.jsonl', good)
        check('load_own_accepts_valid', len(G.load_own(out, reqmap, sci_digest)) == 2)
        write_rows(out / 'outputs.jsonl', good + [good[0]])
        expect_fail(lambda: G.load_own(out, reqmap, sci_digest), 'load_own_rejects_duplicate_id')
        bad = dict(good[0]); bad['text'] = 'tampered'
        write_rows(out / 'outputs.jsonl', [bad, good[1]])
        expect_fail(lambda: G.load_own(out, reqmap, sci_digest), 'load_own_rejects_tampered_row')
        write_rows(out / 'outputs.jsonl', [fake_rec(rq[0], 'f' * 64), good[1]])
        expect_fail(lambda: G.load_own(out, reqmap, sci_digest), 'load_own_rejects_wrong_protocol_digest')
        alien = dict(rq[0]); alien['id'] = 'zzz|C95|D|left lung'
        write_rows(out / 'outputs.jsonl', [fake_rec(alien, sci_digest)])
        expect_fail(lambda: G.load_own(out, reqmap, sci_digest), 'load_own_rejects_request_outside_set')
        wp = fake_rec({**rq[0], 'prompt': 'Describe the left lung.'}, sci_digest) if rq[0]['prompt'] != 'Describe the left lung.' else \
            fake_rec({**rq[0], 'prompt': 'something else'}, sci_digest)
        write_rows(out / 'outputs.jsonl', [wp])
        expect_fail(lambda: G.load_own(out, reqmap, sci_digest), 'load_own_rejects_prompt_mismatch')
        # torn tail는 완결 행만 읽는다
        write_rows(out / 'outputs.jsonl', good, raw='{"id": "partial')
        check('torn_tail_ignored_by_reader', len(G.load_own(out, reqmap, sci_digest)) == 2)
    finally:
        shutil.rmtree(tmp)
    # --- CLI(로딩 전 경로): 이미 있는 출력 디렉터리·허용 GPU 밖·결과 경로 밖 거부 ---
    env = dict(os.environ, CUDA_VISIBLE_DEVICES='0,1')
    tdir = T / f'cli_{os.getpid()}'
    base = [str(C.CURE_PY), str(C.ROOT / 'report95_gen.py'), '--stage', 'D8']

    def run(args, e=env):
        return subprocess.run(base + args, cwd=C.ROOT, env=e, capture_output=True, text=True)

    r = run(['--gpu', '5', '--out', str(tdir / 'a')])
    check('cli_rejects_gpu_outside_allowed', r.returncode != 0 and 'not in inherited' in r.stderr)
    r = run(['--gpu', '0', '--out', '/tmp/not_in_iter095'])
    check('cli_rejects_out_outside_iter095', r.returncode != 0 and 'ValueError' in r.stderr)
    (tdir / 'exists').mkdir(parents=True)
    r = run(['--gpu', '0', '--out', str(tdir / 'exists')])
    check('cli_rejects_existing_dir_without_resume', r.returncode != 0 and 'FileExistsError' in r.stderr)
    # 잘못된 protocol로 --resume: 다른 shard 설정의 protocol이 있으면 모델 로딩 전 거부
    d = tdir / 'proto'
    d.mkdir()
    save(d / 'scientific_protocol.json', {'scientific': {'x': 1}, 'scientific_digest': 'x', 'stage': 'D8', 'shard': 0, 'nshards': 2})
    r = run(['--gpu', '0', '--out', str(d), '--resume', '--shard', '0', '--nshards', '4'])
    check('cli_resume_rejects_protocol_mismatch', r.returncode != 0 and 'protocol/shard mismatch' in r.stderr, r.stderr[-120:])
    # 완료된 출력에 대한 재실행이 completion/outputs를 바꾸지 않는지는 GPU 단계(resume 시험)에서 검사한다.
    out_path = T / (sys.argv[1] if len(sys.argv) > 1 else 'cpu_tests.json')
    ok = all(x['pass'] for x in results)
    save(out_path, {'n': len(results), 'n_pass': sum(x['pass'] for x in results), 'all_pass': ok,
                    'source_sha256': {f: sha(C.ROOT / f) for f in ('report95_common.py', 'report95_gen.py', 'report95_lock.py', 'test_report95.py')},
                    'items': results})
    print(json.dumps({'n': len(results), 'pass': sum(x['pass'] for x in results)}))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
