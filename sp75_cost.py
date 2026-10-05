"""iter_076(결과 경로) 비용 측정: V8 supervised 전체 질문 workload(24 target)를 시스템(F,R,C,H)별로 원 T2 읽기부터 답변 저장까지 측정한다.

- 시스템마다 별도 subprocess(모델 적재 포함 wall 측정). block 안에서 시스템 순서는 block마다 번갈아(순환) 실행.
- 포함: zip에서 T2 read, slice 렌더, F 표시/R·C crop 입력 구성(ROI 좌표는 manifest의 GT-anatomy oracle 값을 사용 -> mask 획득 비용은 미측정 oracle 비용),
  모델 입력 구성·추론, 답변 저장. H는 원 image+mask read, PyRadiomics feature, RF predict(RF 학습/적재는 load로 분리).
- 보고: load 포함 wall / load 제외 처리 시간 / 요청당 시간 / GPU 지정 1장 기준 device-seconds.
- 출력은 results/iter_075/cost 아래 시스템·block별 JSON (존재하면 중단).
사용: python sp75_cost.py worker --system F --block 1 --adapter DIR --gpu 0   /  python sp75_cost.py blocks --nblocks 4 --gpu 0 --adapters '{...}'
"""
import argparse, json, os, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = 'results/iter_077/cost'


def worker(a):
    t_proc0 = time.perf_counter()
    if a.gpu is not None:
        os.environ['CUDA_VISIBLE_DEVICES'] = a.gpu
    sys.path.insert(0, os.path.join(HERE, 'results/environments/tv071'))
    sys.path.insert(0, os.path.join(HERE, 'results/environments/sitk67/site'))
    if a.system == 'H':
        sys.path.insert(0, os.path.join(HERE, 'results/environments/ch75/site'))
    import numpy as np
    import sp75_data as D
    import sp67_data as S
    import g71_data as G71
    from PIL import Image
    out_path = f'{OUT}/{a.system}_block{a.block}.json'
    if os.path.exists(out_path):
        sys.exit('exists')
    D.load_split()
    man = D.load_manifest()
    rows = sorted([r for r in man['rows'] if r['split'] == 'V8' and r['position_set'] == 'supervised' and not r['excluded']], key=lambda r: (int(r['patient']), r['ordinal']))
    answers, per = {}, []
    load_s = 0.0
    t_load = time.perf_counter()
    if a.system in ('F', 'R'):
        import sp75_gen as GN
        import sp75_vlm as V
        from rsna_diag import generate
        torch, proc, model = generate.load_model()
        generate.load_adapter(torch, model, a.adapter)
        env = generate.env_info(torch, proc, model)
        eos = env['eos_token_id']
        eos_ids = set(eos if isinstance(eos, list) else [eos])
        cands = GN.cand_ids(proc.tokenizer)
        torch.cuda.synchronize()
    elif a.system == 'C':
        import torch
        import sp75_c as C
        sel = json.load(open('results/iter_075/C/selection.json'))['selected']
        net = C.Net(torch)
        blob = torch.load(f"results/iter_075/C/lr{sel['lr']}/epoch_{sel['epoch']:02d}.pt", map_location='cpu', weights_only=True)
        net.trunk.load_state_dict(blob['trunk']); net.head.load_state_dict(blob['head'])
        for m in net.modules():
            m.cuda(); m.eval()
        torch.cuda.synchronize()
    else:  # H
        import sp75_h as H
        from sklearn.ensemble import RandomForestClassifier
        tr = sorted([r for r in man['rows'] if r['split'] == 'T24' and r['position_set'] == 'supervised' and not r['excluded']], key=lambda r: (int(r['patient']), r['ordinal']))
        cache = json.load(open('results/iter_075/H/features_T24_V8.json'))
        Xtr, names = H.matrix(tr, cache)
        med, keep = H.prep_fit(Xtr)
        cfg = json.load(open('results/iter_075/H/selection.json'))['selected']['cfg']
        rf = RandomForestClassifier(n_estimators=500, random_state=17, n_jobs=4, **cfg).fit(H.prep_apply(Xtr, med, keep), np.array([r['grade'] for r in tr]))
        ext = H.extractor()
    load_s = time.perf_counter() - t_load
    t0 = time.perf_counter()
    vol_cache = {}
    for r in rows:
        tr0 = time.perf_counter()
        pid = r['patient']
        if a.system == 'H':
            res = H.extract_patient(pid, [r['ordinal']], ext)
            f = res[r['ordinal']][0]
            x = np.array([[f.get(n, np.nan) for n in names]], float)
            pr = rf.predict_proba(H.prep_apply(x, med, keep))[0]
            answers[r['id']] = int(rf.classes_[int(np.argmax(pr))])
        else:
            if pid not in vol_cache:   # 환자당 한 번 원 T2 read + 렌더 (같은 환자의 target들이 공유)
                dd = S.load_pair(pid, 't2')   # image+mask read와 canonical 정렬·기하 검사 포함(기존 검증 경로 그대로; mask는 기하 검사에만 쓰인다)
                V_, spc = dd['V'], dd['spacing']
                idxs = G71.select_slices(V_.shape[0])
                imgs = []
                for idx in idxs:
                    arr, meta = G71.render_slice(V_, spc, idx)
                    imgs.append(arr)
                vol_cache[pid] = imgs
            imgs = vol_cache[pid]
            x0, y0, x1, y1 = r['roi']['roi_int_xyxy']
            if a.system == 'C':
                ts = []
                for arr in imgs:
                    crop = arr[y0:y1, x0:x1]
                    hh, ww = crop.shape
                    s = max(hh, ww); top, left = (s - hh) // 2, (s - ww) // 2
                    sq = np.zeros((s, s), np.uint8); sq[top:top + hh, left:left + ww] = crop
                    ts.append(np.asarray(Image.fromarray(sq, mode='L').resize((C.SIDE, C.SIDE), resample=Image.BILINEAR), np.float32) / 255.0)
                xb = C.to_tensor(ts).unsqueeze(0).cuda()
                with torch.no_grad():
                    pr = torch.softmax(net.forward(xb).float(), -1)[0].cpu().numpy()
                answers[r['id']] = int(np.argmax(pr)) + 1
            else:
                ims = []
                import sp75_data as DD
                from rsna_diag import geometry
                for arr in imgs:
                    if a.system == 'F':
                        rgb = np.repeat(arr[:, :, None], 3, axis=2)
                        rgb, _ = DD.draw_outline(rgb, r['roi']['roi_int_xyxy'])
                    else:
                        rgb = np.repeat(arr[y0:y1, x0:x1][:, :, None], 3, axis=2)
                    padded, _ = geometry.pad_square(rgb)
                    ims.append(Image.fromarray(padded))
                row2 = dict(r)
                inp = V.build_gen_inputs(proc, ims, V.PROMPTS[a.system])
                x_ = {k: (v.cuda().to(torch.bfloat16) if k == 'pixel_values' else v.cuda()) for k, v in inp.items()}
                with torch.no_grad():
                    outg = model.generate(**x_, max_new_tokens=V.MAX_NEW, do_sample=False)
                ids = outg[0, x_['input_ids'].shape[1]:].tolist()
                ended = len(ids) > 0 and ids[-1] in eos_ids
                txt = proc.tokenizer.decode(ids, skip_special_tokens=True)
                answers[r['id']] = V.parse(txt) if ended else None
                if a.system in ('F', 'R'):   # 후보 likelihood는 비용 workload의 선택 출력이 아니므로 측정하지 않는다(답변 생성과 저장까지)
                    pass
        per.append({'id': r['id'], 'seconds': time.perf_counter() - tr0})
    process_s = time.perf_counter() - t0
    os.makedirs(OUT, exist_ok=True)
    tmp = out_path + '.tmp'
    json.dump({'system': a.system, 'block': a.block, 'n_requests': len(rows), 'load_s': load_s, 'process_s': process_s, 'wall_incl_load_s': time.perf_counter() - t_proc0,
               'per_request_s_mean': process_s / len(rows), 'gpu': a.gpu, 'answers': answers, 'per': per, 'adapter': a.adapter, 'ts': time.time()}, open(tmp, 'w'))
    os.replace(tmp, out_path)
    print(a.system, a.block, 'load', round(load_s, 1), 'process', round(process_s, 1))


def blocks(a):
    systems = ['F', 'R', 'C', 'H']
    ad = json.loads(a.adapters)
    os.makedirs(f'{OUT}/logs', exist_ok=True)
    ledger = []
    for b in range(1, a.nblocks + 1):
        order = systems[(b - 1) % 4:] + systems[:(b - 1) % 4]   # 순환 시작점으로 시스템 순서 번갈아
        for s in order:
            cmd = [sys.executable, 'sp75_cost.py', 'worker', '--system', s, '--block', str(b), '--gpu', a.gpu]
            if s in ('F', 'R'):
                cmd += ['--adapter', ad[s]]
            t0 = time.time()
            rc = subprocess.call(cmd, stdout=open(f'{OUT}/logs/{s}_block{b}.log', 'w'), stderr=subprocess.STDOUT)
            ledger.append({'block': b, 'system': s, 'order_in_block': order.index(s), 'rc': rc, 'wall_s': time.time() - t0})
            if rc != 0:
                sys.exit(f'worker failed {s} block {b}')
    json.dump(ledger, open(f'{OUT}/blocks_ledger.json', 'w'), indent=1)


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest='c', required=True)
    w = sp.add_parser('worker'); w.add_argument('--system', required=True, choices=['F', 'R', 'C', 'H']); w.add_argument('--block', type=int, required=True)
    w.add_argument('--adapter', default=None); w.add_argument('--gpu', default=None)
    b = sp.add_parser('blocks'); b.add_argument('--nblocks', type=int, default=4); b.add_argument('--gpu', required=True); b.add_argument('--adapters', required=True)
    a = ap.parse_args()
    {'worker': worker, 'blocks': blocks}[a.c](a)
