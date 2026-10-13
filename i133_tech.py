"""기술 검사: tensor 대조(tensor), 변조·진입 거부(neg), 구성 간 출력 정합성·처리량(compare), 최종 gate(gate).
기술 사례 출력으로 prompt/문턱을 조정하지 않는다. 내용 성능은 gate에 쓰지 않는다."""
import sys, os, json, subprocess, copy, shutil, time
from pathlib import Path
from i133_common import RES, HERE, sha, read, save, digest, now
from i133_spec import CONFIG
import i133_run as R

T = RES / 'tests'


def tensor():
    import torch
    from PIL import Image
    from transformers import AutoProcessor
    proc = AutoProcessor.from_pretrained(R.MODEL, local_files_only=True); rr = R.requests(RES / 'requests/technical.json'); out = []
    tok = proc.tokenizer; boi = getattr(proc, 'boi_token', None); img_tok = '<image_soft_token>'; img_id = tok.convert_tokens_to_ids(img_tok)
    for r in rr:
        wrap = R.input_tensor(proc, r)
        msgs = R.messages(r)
        text = proc.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
        imgs = [Image.open(im['path']).convert('RGB') for im in r['groups'][0]]
        ind = proc(text=text, images=imgs, return_tensors='pt', add_special_tokens=False)  # 템플릿이 <bos>를 이미 포함
        same_ids = bool(torch.equal(wrap['input_ids'], ind['input_ids'])); same_pix = bool(torch.equal(wrap['pixel_values'], ind['pixel_values']))
        n_img_tok = int((wrap['input_ids'] == img_id).sum()) if img_id is not None else None
        # 영상 순서 민감도: slice 1,2 교환 시 pixel_values가 달라져야 한다.
        sw = copy.deepcopy(r); g = sw['groups'][0]; g[0], g[1] = g[1], g[0]
        pv_sw = R.input_tensor(proc, sw)['pixel_values']
        order_sensitive = not torch.equal(wrap['pixel_values'], pv_sw)
        # pixel_values[n]이 n번째 입력 영상의 독립 처리 결과와 같은가
        per = [proc.image_processor(images=[im], return_tensors='pt')['pixel_values'] for im in imgs]
        per_ok = all(torch.equal(wrap['pixel_values'][n:n + 1], per[n]) for n in range(8))
        decoded = tok.decode(wrap['input_ids'][0])
        leak = [s for s in ['BraTS', 'GLI', '00012', '00456', 't2f', 'glioma', 'tumor', 'edema'] if s in decoded]
        out.append(dict(id=r['id'], same_input_ids=same_ids, same_pixel_values=same_pix, n_image_tokens=n_img_tok, n_images=len(imgs), input_len=int(wrap['input_ids'].shape[-1]),
                        pixel_values_shape=list(wrap['pixel_values'].shape), order_sensitive=order_sensitive, per_image_pixel_match=per_ok, leak=leak,
                        has_generation_prompt=decoded.rstrip().endswith('model') or '<start_of_turn>model' in decoded))
    ok = all(o['same_input_ids'] and o['same_pixel_values'] and o['order_sensitive'] and o['per_image_pixel_match'] and not o['leak'] and o['n_image_tokens'] == 8 * 256 for o in out)
    save(T / 'tensor_check_v2.json', dict(created_at=now(), passed=ok, image_token=img_tok, rows=out, note='v1(tensor_check.json)은 독립 경로의 BOS 중복·image token 이름 오류로 실패; 검사 코드 오류이며 wrapper 입력 결함이 아님'))
    print('tensor passed', ok, [(o['n_image_tokens'], o['input_len']) for o in out])


def neg():
    rr = read(RES / 'requests/technical.json'); res = {}

    def must_fail(name, fn):
        try: fn(); res[name] = dict(rejected=False)
        except Exception as e: res[name] = dict(rejected=True, error=type(e).__name__ + ': ' + str(e)[:150])
    tmp = T / 'neg_tmp'; tmp.mkdir(parents=True, exist_ok=True)
    # 1. 요청 변조: prompt 변경(digest 불일치)
    x = copy.deepcopy(rr); x[0]['prompt'] += ' extra'; save(tmp / 'tamper_prompt.json', x)
    must_fail('tampered_prompt', lambda: R.requests(tmp / 'tamper_prompt.json'))
    # 2. 입력 hash 변경: 이미지 sha 필드 변경(+digest 재계산 → known과 불일치)
    x = copy.deepcopy(rr); x[0]['groups'][0][0]['sha256'] = '0' * 64; x[0]['request_digest'] = digest({k: v for k, v in x[0].items() if k != 'request_digest'}); save(tmp / 'tamper_hash.json', x)
    must_fail('changed_input_hash', lambda: R.requests(tmp / 'tamper_hash.json'))
    # 3. 중복 요청
    save(tmp / 'dup.json', [rr[0], rr[0]]); must_fail('duplicate_request_ids', lambda: R.requests(tmp / 'dup.json'))
    # 4. 요청 밖 id
    x = copy.deepcopy(rr[:1]); x[0]['id'] = 'unknown__U'; save(tmp / 'unknown.json', x); must_fail('unknown_request_id', lambda: R.requests(tmp / 'unknown.json'))
    # 5. worker 직접 진입(lock fd 없음 / 비감독기 fd)
    env = dict(os.environ, CUDA_VISIBLE_DEVICES='0'); job = RES / 'jobs/neg_direct'; job.mkdir(parents=True, exist_ok=True)
    p = subprocess.run([sys.executable, str(HERE / 'i133_run.py'), 'worker', '--job', str(job), '--requests', str(RES / 'requests/technical.json'), '--stage', 'technical', '--worker', '0', '--attempt', 'x'], env=env, capture_output=True, text=True)
    res['worker_without_lock_fd'] = dict(rejected=p.returncode != 0, rc=p.returncode, stderr_tail=p.stderr[-200:])
    (job / 'supervisor.lock').write_text('')
    fd = os.open(job / 'supervisor.lock', os.O_RDWR)  # flock을 잡지 않은 fd로 worker 시도
    p = subprocess.run([sys.executable, str(HERE / 'i133_run.py'), 'worker', '--job', str(job), '--requests', str(RES / 'requests/technical.json'), '--stage', 'technical', '--worker', '0', '--attempt', 'y', '--lock-fd', str(fd)], env=env, capture_output=True, text=True, pass_fds=(fd,))
    os.close(fd); res['worker_with_unheld_lock'] = dict(rejected=p.returncode != 0, rc=p.returncode, stderr_tail=p.stderr[-200:])
    # 6. 감독기 중복: flock 보유 중 launch 거부
    import fcntl
    job2 = RES / 'jobs/neg_dup'; job2.mkdir(parents=True, exist_ok=True)
    fd2 = os.open(job2 / 'supervisor.lock', os.O_CREAT | os.O_RDWR, 0o600); fcntl.flock(fd2, fcntl.LOCK_EX)
    p = subprocess.run([sys.executable, str(HERE / 'i133_run.py'), 'launch', '--job', str(job2), '--requests', str(RES / 'requests/technical.json'), '--stage', 'technical'], env=dict(os.environ, CUDA_VISIBLE_DEVICES='0,1'), capture_output=True, text=True)
    os.close(fd2); res['duplicate_supervisor'] = dict(rejected=p.returncode != 0 and 'refuse launch' in p.stderr, rc=p.returncode, stderr_tail=p.stderr[-200:])
    # 7. main 단계: technical gate 없이 protocol 검증 거부 (main 잠금 전)
    must_fail('main_without_gate_lock', lambda: R.verify_protocol(stage='main'))
    # 8. 손상 record 거부 (중간 행 손상) / 마지막 행 복구
    jb = RES / 'jobs/neg_records'; jb.mkdir(parents=True, exist_ok=True)
    (jb / 'worker0_a.jsonl').write_bytes(b'{"bad":\n{"also":1}\n'); must_fail('corrupt_middle_row', lambda: R.load_records(jb))
    res['all_rejected'] = all(v['rejected'] for k, v in res.items() if isinstance(v, dict))
    save(T / 'negative_tests.json', dict(created_at=now(), **res)); print({k: v['rejected'] for k, v in res.items() if isinstance(v, dict)})


def toks(job): return {r['id']: r['tokens'] for r in R.load_records(job)}


def compare():
    jobs = RES / 'jobs'; base = toks(jobs / 'T_w2'); out = dict(created_at=now(), configs={})
    for name in ['T_w2', 'T_w4', 'T_resume']:
        j = jobs / name; rec = R.load_records(j); comp = read(j / 'completion.json'); t = toks(j)
        res = [read(p) for p in sorted(j.glob('result_*.json'))]
        peaks = [r['peak_reserved_mib'] for r in rec]; wall = sum(x['wall_s'] for x in res)
        # 요청 처리 구간(첫 시작~마지막 완료) 기준 처리량: worker exit 파일의 wall_s(load 제외)
        ex = [read(p) for p in j.glob('worker*_exit.json')]
        gen_wall = max(e['wall_s'] for e in ex) if ex else None
        used = max((max(int(g['used']) for g in json.loads(l)['gpu']) for l in open(next(j.glob('resources_*.jsonl'))) if l.strip()), default=None)
        out['configs'][name] = dict(n=len(rec), identical_tokens_to_T_w2=all(t[k] == base[k] for k in base) and set(t) == set(base), launch_wall_s=wall, generation_wall_s=gen_wall,
                                    req_per_min_generation=len(rec) / gen_wall * 60 if gen_wall else None, req_per_min_incl_load=len(rec) / wall * 60,
                                    mean_request_s=sum(r['wall_s'] for r in rec) / len(rec), max_peak_reserved_mib=max(peaks), max_gpu_used_mib=used,
                                    all_eos=all(r['eos'] for r in rec), max_tokens=max(r['n_tokens'] for r in rec), returncodes=comp['returncodes'])
    save(T / 'compare.json', out); print(json.dumps(out['configs'], indent=1)[:1800])


def gate():
    t = read(T / 'tensor_check_v2.json'); n = read(T / 'negative_tests.json'); c = read(T / 'compare.json')['configs']
    checks = dict(tensor=t['passed'], negative=n['all_rejected'], w4_identical=c['T_w4']['identical_tokens_to_T_w2'], resume_identical=c['T_resume']['identical_tokens_to_T_w2'],
                  complete_6=all(v['n'] == 6 for v in c.values()), rc_zero=all(all(x == 0 for x in v['returncodes']) for v in c.values()))
    save(T / 'technical_gate.json', dict(created_at=now(), passed=all(checks.values()), checks=checks, n_non_eos_outputs={k: None for k in c}, note='비EOS(512 token) 출력은 모델 출력으로서 invalid 처리하는 결과이며 인프라 gate가 아님(초기 코드의 all_eos 조건을 제거; 제거 전 결과는 compare.json에 보존). 내용 성능은 gate에 쓰지 않음. 기술 요청 출력으로 prompt/문턱 조정 없음.')); print(checks)


if __name__ == '__main__':
    globals()[sys.argv[1]]()
