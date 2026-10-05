재개 검사 완료 알림을 기다린다. 완료되면 결과 판정 후 freeze 검사와 본학습으로 넘어간다.

# [orchestrator] 권한 거부된 도구 호출
- Bash: ps aux --no-headers -o pid,etime,cmd -C python
- Bash: cat >> rsna_diag/lora.py <<'EOF'


def _tensor_bytes(t):
    t = t.detach().to("cpu").contiguous()
    if t.dtype == torch.bfloat16:
        return t.view(torch.int16).numpy().tobytes()
    return t.view(torch.uint8).numpy().tobytes() if t.dtype != torch.bool else t.numpy().tobytes()


def split_report(model, optimizer_params=None):
    """LoRA / 비LoRA parameter를 객체 단위로 분리해 개수·numel·byte를 센다 (iter_076 동결 검사).

    분리 기준은 이름 문자열이 아니라 'lora_' 이름의 parameter 객체와 나머지이다. 정규화 이름 충돌, 빈 집합(수·numel·byte 0)은 예외.
    optimizer_params: optimizer에 들어간 parameter 목록(있으면 비LoRA 포함 여부 검사).
    """
    lo, non = {}, {}
    for n, p in model.named_parameters():
        (lo if "lora_" in n else non)[n] = p
    norm = [n.replace(".base.", ".") for n in non]
    if len(set(norm)) != len(norm):
        raise RuntimeError("normalized non-LoRA parameter names collide")
    rep = {"n_lora": len(lo), "n_non_lora": len(non), "numel_lora": sum(p.numel() for p in lo.values()), "numel_non_lora": sum(p.numel() for p in non.values()),
           "bytes_lora": sum(p.numel() * p.element_size() for p in lo.values()), "bytes_non_lora": sum(p.numel() * p.element_size() for p in non.values()),
           "non_lora_requires_grad": sum(1 for p in non.values() if p.requires_grad), "lora_requires_grad_false": sum(1 for p in lo.values() if not p.requires_grad),
           "non_lora_dtypes": sorted({str(p.dtype) for p in non.values()}), "lora_dtypes": sorted({str(p.dtype) for p in lo.values()})}
    for k in ("n_lora", "n_non_lora", "numel_lora", "numel_non_lora", "bytes_lora", "bytes_non_lora"):
        if rep[k] <= 0:
            raise RuntimeError(f"empty parameter set: {k}=0")
    if optimizer_params is not None:
        ids = {id(p) for p in optimizer_params}
        rep["optimizer_contains_non_lora"] = sum(1 for p in non.values() if id(p) in ids)
        rep["optimizer_lora_covered"] = all(id(p) in ids for p in lo.values())
        rep["optimizer_n_params"] = len(ids)
    return rep


def exact_digest(model, lora=False):
    """정확한 parameter 이름·dtype·shape·byte 전체의 sha256 (정규화 없음). lora=False면 비LoRA만. 비어 있으면 예외. returns (hexdigest, n_params, n_bytes)."""
    h = hashlib.sha256()
    n_par = n_bytes = 0
    for n, p in sorted(model.named_parameters(), key=lambda x: x[0]):
        if ("lora_" in n) != lora:
            continue
        b = _tensor_bytes(p)
        h.update(f"{n}|{p.dtype}|{tuple(p.shape)}|{len(b)}".encode())
        h.update(b)
        n_par += 1
        n_bytes += len(b)
    if n_par == 0 or n_bytes == 0:
        raise RuntimeError("exact_digest over an empty parameter set")
    return h.hexdigest(), n_par, n_bytes
EOF
python -c "import ast;ast.parse(open('rsna_diag/lora.py').read())"
- Bash: python - <<'PYEOF'
p='sp75_eval.py'
s=open(p).read()

# run: lock + seal verification
s=s.replace("""def cmd_run(a):
    lock = json.load(open(f'{EVAL}/eval_lock.json'))
    for f, h in lock['files'].items():
        if sha_file(f) != h:
            sys.exit(f'locked file changed: {f}')
""","""def verify_lock_seal():
    lock = json.load(open(f'{EVAL}/eval_lock.json'))
    for f, h in lock['files'].items():
        if sha_file(f) != h:
            sys.exit(f'locked file changed: {f}')
    seal = json.load(open(f'{EVAL}/eval_seal.json'))
    if seal['lock_sha256'] != sha_file(f'{EVAL}/eval_lock.json'):
        sys.exit('seal does not match current lock')
    for f, h in seal['outputs'].items():
        if sha_file(f) != h:
            sys.exit(f'sealed E24 output changed: {f}')
    cur = {f for v in lock['vlm'].values() for f in files_of(v['dir'])}
    if cur != set(seal['outputs']) - set(lock['json_systems'].values()):
        sys.exit('E24 output file set differs from seal')
    return lock


def cmd_run(a):
    if os.path.exists(f'{EVAL}/report.json') or os.path.exists(f'{EVAL}/per_row.json'):
        sys.exit('report exists; refusing to overwrite')
    lock = verify_lock_seal()
""")

# flags: add CI-based info + C vs best vlm comparison
s=s.replace("""    comps = {}
    vl = [n for n in systems if n.startswith('F_') or n.startswith('R_')]""","""    comps = {}
    vl = [n for n in systems if n.startswith('F_') or n.startswith('R_')]
    sysh0 = {n: rep['systems'][n]['held']['class_std_mae'] for n in systems}
    best_vlm0 = min([v for v in ('F_adapted', 'R_adapted') if v in systems], key=lambda v: (sysh0[v], v))""")
s=s.replace("('C', 'H'), ('C', 'prior_ordinal'), ('H', 'prior_ordinal')]","('C', 'H'), ('C', 'prior_ordinal'), ('H', 'prior_ordinal'), ('C', best_vlm0), (best_vlm0, 'H')]")
s=s.replace("""    best_vlm = min([v for v in ('F_adapted', 'R_adapted') if v in systems], key=lambda v: sysh[v])
    flags['best_vlm'] = best_vlm""","""    best_vlm = best_vlm0
    flags['best_vlm'] = best_vlm
    ci = lambda key: comps[key]['held']['ci95']
    for v in ('F_adapted', 'R_adapted'):
        if v in flags:
            flags[v]['ci95_held_vs_prior_ordinal'] = ci(f'{v}_minus_prior_ordinal')
            flags[v]['ci95_held_vs_C'] = ci(f'{v}_minus_C')
            flags[v]['ci95_excludes_0_vs_prior_ordinal'] = ci(f'{v}_minus_prior_ordinal')[1] < 0
            flags[v]['ci95_excludes_0_vs_C'] = ci(f'{v}_minus_C')[1] < 0
    cb = ci(f'C_minus_{best_vlm}')
    flags['C_minus_best_vlm_ci95'] = cb
    flags['C_minus_best_vlm_ci_contains_both_plus_minus_0.20'] = bool(cb[0] < -MARGIN and cb[1] > MARGIN)""")
s=s.replace("""    os.makedirs(EVAL, exist_ok=True)
    per = [{'id'""","""    per = [{'id'""")
s=s.replace("""    json.dump(per, open(f'{EVAL}/per_row.json', 'w'))
    json.dump(rep, open(f'{EVAL}/report.json', 'w'), indent=1)""","""    for obj, fn in ((per, 'per_row.json'), (rep, 'report.json')):
        json.dump(obj, open(f'{EVAL}/{fn}.tmp', 'w'), indent=1)
        os.replace(f'{EVAL}/{fn}.tmp', f'{EVAL}/{fn}')""")

# lock / seal
start=s.index("def cmd_lock(a):")
end=s.index("if __name__ == '__main__':")
new='''def cmd_lock(a):
    """첫 E24 출력 전: 코드·선택 근거·checkpoint·manifest·환경·계획 hash를 고정. 생성 출력은 포함하지 않는다(별도 seal)."""
    spec = json.load(open(a.spec))
    files = {f: sha_file(f) for f in CODE}
    for name, p in spec['json_systems'].items():
        if os.path.exists(p):
            sys.exit(f'E24 prediction output already exists before lock: {p}')
    for name, v in spec['vlm'].items():
        if files_of(v['dir']):
            sys.exit(f'E24 output already exists before lock: {v["dir"]}')
    for f in spec.get('extra_files', []):
        files[f] = sha_file(f)
    if os.path.exists(f'{EVAL}/eval_lock.json'):
        sys.exit('lock exists')
    os.makedirs(EVAL, exist_ok=True)
    tmp = f'{EVAL}/eval_lock.json.tmp'
    json.dump({'vlm': spec['vlm'], 'json_systems': spec['json_systems'], 'files': files, 'selection': spec.get('selection')}, open(tmp, 'w'), indent=1)
    os.replace(tmp, f'{EVAL}/eval_lock.json')
    print('locked', len(files))


def cmd_seal(a):
    """E24 출력 완료 후: 요청 집합 완전성·provenance 확인 뒤 출력 파일 hash를 봉인한다."""
    lock = json.load(open(f'{EVAL}/eval_lock.json'))
    for f, h in lock['files'].items():
        if sha_file(f) != h:
            sys.exit(f'locked file changed: {f}')
    man = D.load_manifest()
    rows = sorted([r for r in man['rows'] if r['split'] == 'E24' and not r['excluded']], key=lambda r: (int(r['patient']), r['ordinal']))
    outputs = {}
    for name, spec in lock['vlm'].items():
        load_vlm(spec['dir'], rows, spec['variant'], spec['adapter_digest'])   # 누락/중복/집합 밖/입력 hash/adapter 불일치면 예외
        for f in files_of(spec['dir']):
            outputs[f] = sha_file(f)
    for name, p in lock['json_systems'].items():
        load_json_pred(p, rows)
        outputs[p] = sha_file(p)
    if os.path.exists(f'{EVAL}/eval_seal.json'):
        sys.exit('seal exists')
    tmp = f'{EVAL}/eval_seal.json.tmp'
    json.dump({'lock_sha256': sha_file(f'{EVAL}/eval_lock.json'), 'outputs': outputs, 'n_rows': len(rows)}, open(tmp, 'w'), indent=1)
    os.replace(tmp, f'{EVAL}/eval_seal.json')
    print('sealed', len(outputs))


'''
s=s[:start]+new+s[end:]
s=s.replace("""    l = sp.add_parser('lock'); l.add_argument('--spec', required=True)
    a = ap.parse_args()
    {'run': cmd_run, 'lock': cmd_lock}[a.c](a)""","""    l = sp.add_parser('lock'); l.add_argument('--spec', required=True)
    sp.add_parser('seal')
    a = ap.parse_args()
    {'run': cmd_run, 'lock': cmd_lock, 'seal': cmd_seal}[a.c](a)""")
open(p,'w').write(s)
PYEOF
python -c "import ast;ast.parse(open('sp75_eval.py').read())"; grep -n "os.makedirs(EVAL" sp75_eval.py
- Bash: python - <<'PYEOF'
p='sp76_select.py'
s=open(p).read()
s=s.replace("""if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('c', choices=['select_v8', 'select_final'])
    a = ap.parse_args()
    {'select_v8': cmd_select_v8, 'select_final': cmd_select_final}[a.c](a)""","""def cmd_lock_spec(a):
    \"\"\"eval lock 명세 작성: 최종 F/R adapter, base F/R, C/H 선택 근거. (실제 lock은 sp75_eval.py lock --spec).\"\"\"
    fin = json.load(open(f'{OUT}/select_final.json'))['final']
    csel = json.load(open('results/iter_075/C/selection.json'))['selected']
    vlm = {'F_base': {'variant': 'F', 'adapter_dir': None, 'adapter_digest': None, 'dir': f'{OUT}/gen/E24/F_base'},
           'R_base': {'variant': 'R', 'adapter_dir': None, 'adapter_digest': None, 'dir': f'{OUT}/gen/E24/R_base'}}
    extra = [f'{OUT}/select_v8.json', f'{OUT}/select_final.json', 'results/iter_075/data/manifest.json', 'results/iter_075/env_record.json', 'results/iter_075/C/selection.json',
             'results/iter_075/H/selection.json', 'results/iter_075/H/features_T24_V8.json',
             f"results/iter_075/C/lr{csel['lr']}/epoch_{csel['epoch']:02d}.pt"]
    for v in ('F', 'R'):
        f = fin[v]
        vlm[f'{v}_adapted'] = {'variant': v, 'adapter_dir': f['adapter_dir'], 'adapter_digest': f['adapter_digest'], 'dir': f'{OUT}/gen/E24/{v}_adapted'}
        extra += [f"{f['adapter_dir']}/adapter.pt", f"{f['adapter_dir']}/val_ce.json", f"{traj_dir(v, f['lr'])}/train_config.json"]
    code = ['sp75_pipeline.py', 'sp76_select.py', 'sp76_cpred.py', 'sp75_train.py', 'sp75_c.py', 'sp75_h.py', 'sp67_data.py', 'g71_data.py', 'rsna_diag/generate.py', 'rsna_diag/lora.py']
    spec = {'vlm': vlm, 'json_systems': {'C': f'{OUT}/pred/pred_C_E24.json', 'H': f'{OUT}/pred/pred_H_E24.json'}, 'extra_files': extra + code,
            'selection': {'final': {v: {k: fin[v][k] for k in ('lr', 'epoch', 'adapter_digest')} for v in fin}, 'C': csel}}
    os.makedirs(f'{OUT}/eval', exist_ok=True)
    atomic_write(spec, f'{OUT}/eval/lock_spec.json')
    print('wrote lock spec')


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('c', choices=['select_v8', 'select_final', 'lock_spec'])
    a = ap.parse_args()
    {'select_v8': cmd_select_v8, 'select_final': cmd_select_final, 'lock_spec': cmd_lock_spec}[a.c](a)""")
open(p,'w').write(s)
PYEOF
python -c "import ast;ast.parse(open('sp76_select.py').read())"
- Bash: python - <<'PYEOF'
p='test_sp75.py'
s=open(p).read()
s=s.replace('"""iter_075 CPU fixture:','"""iter_075/076 CPU fixture (iter_076: 결과 경로 변경 + 선택·연장·gate·평가 경계·tail 복구 검사 추가):')
s=s.replace("결과: results/iter_075/tests/fixtures_cpu.json","결과: results/iter_076/tests/fixtures_cpu.json")
s=s.replace("""fails = [k for k, v in res.items() if not v['pass']]
out = 'results/iter_075/tests/fixtures_cpu.json'""","""# ---- iter_076 추가 검사 ----
import sp76_select as SEL
import sp75_train as TR
import sp75_eval as EV
import sp75_gen as GN
chk('pick_lr_lowest_primary', SEL.pick_lr([{'lr': '2e-5', 'primary': 0.9, 'ce': 1.0}, {'lr': '2e-4', 'primary': 0.8, 'ce': 5.0}]) == '2e-4')
chk('pick_lr_tie_primary_then_ce', SEL.pick_lr([{'lr': '2e-5', 'primary': 0.8, 'ce': 2.0}, {'lr': '2e-4', 'primary': 0.8, 'ce': 1.0}]) == '2e-4')
chk('pick_lr_full_tie_smaller_lr', SEL.pick_lr([{'lr': '2e-4', 'primary': 0.8, 'ce': 1.0}, {'lr': '2e-5', 'primary': 0.8, 'ce': 1.0}]) == '2e-5')
chk('ext_ce_exactly_5pct_extends', SEL.needs_extension({'primary': 0.8, 'ce': 2.0}, {'primary': 0.8, 'ce': 1.9})[0])
chk('ext_ce_4pct_no', not SEL.needs_extension({'primary': 0.8, 'ce': 2.0}, {'primary': 0.8, 'ce': 1.92})[0])
chk('ext_primary_gain_0.10_extends', SEL.needs_extension({'primary': 0.9, 'ce': 2.0}, {'primary': 0.8, 'ce': 2.5})[0])
chk('ext_primary_gain_0.09_no', not SEL.needs_extension({'primary': 0.89, 'ce': 2.0}, {'primary': 0.8, 'ce': 2.5})[0])
chk('final_epoch_prefers_better_primary', SEL.final_epoch({16: {'primary': 0.9, 'ce': 1.0}, 32: {'primary': 0.8, 'ce': 3.0}}) == 32)
chk('final_epoch_tie_ce_then_earlier', SEL.final_epoch({16: {'primary': 0.8, 'ce': 1.0}, 32: {'primary': 0.8, 'ce': 1.0}}) == 16 and
    SEL.final_epoch({16: {'primary': 0.8, 'ce': 2.0}, 32: {'primary': 0.8, 'ce': 1.0}}) == 32)
chk('final_epoch_excludes_epoch8', SEL.final_epoch({8: {'primary': 0.1, 'ce': 0.1}, 16: {'primary': 0.9, 'ce': 1.0}}) == 16)
g = {'status': 'PASS', 'official_loss': 6.12, 'logits_f32_ce_mean': 6.12, 'loss_sum_over_n': 6.12, 'rel_diff_official_vs_loss_sum': 0.0, 'n_valid_tokens': 2, 'n_valid_independent': 2, 'provenance': {'a': 1}}
chk('gate_pass_valid', TR.validate_gate(g, {'a': 1}) == [])
chk('gate_rejects_fail_status', bool(TR.validate_gate(dict(g, status='FAIL'), {'a': 1})))
chk('gate_rejects_nan', bool(TR.validate_gate(dict(g, loss_sum_over_n=float('nan')), {'a': 1})))
chk('gate_rejects_rel_gt_1e-6', bool(TR.validate_gate(dict(g, loss_sum_over_n=6.12 * (1 + 2e-6), rel_diff_official_vs_loss_sum=2e-6), {'a': 1})))
chk('gate_rejects_token_mismatch', bool(TR.validate_gate(dict(g, n_valid_independent=3), {'a': 1})))
chk('gate_rejects_provenance_change', bool(TR.validate_gate(g, {'a': 2})))
chk('gate_rejects_inconsistent_stored_rel', bool(TR.validate_gate(dict(g, rel_diff_official_vs_loss_sum=0.5), {'a': 1})))
# eval 경계: C_not_worse는 엄격 부등호(0.10 이상 나쁘면 false), H 우위는 0.10 초과일 때만
chk('eval_constants', (EV.MARGIN, EV.PASS_ABS, EV.H_TOL, EV.C_NOT_WORSE) == (0.20, 1.0, 0.10, 0.10))
import tempfile
with tempfile.TemporaryDirectory() as td:
    pj = os.path.join(td, 'p.json')
    erows = [{'id': 'a', 'patient': '1', 'ordinal': 1, 'position_set': 'supervised'}, {'id': 'b', 'patient': '2', 'ordinal': 3, 'position_set': 'held'}]
    good = [{'id': 'a', 'patient': '1', 'ordinal': 1, 'position_set': 'supervised', 'pred': 2}, {'id': 'b', 'patient': '2', 'ordinal': 3, 'position_set': 'held', 'pred': 3}]
    def tryload(preds):
        json.dump({'preds': preds}, open(pj, 'w'))
        try:
            EV.load_json_pred(pj, erows); return True
        except RuntimeError:
            return False
    chk('json_pred_ok', tryload(good))
    chk('json_pred_rejects_duplicate', not tryload(good + [good[0]]))
    chk('json_pred_rejects_missing', not tryload(good[:1]))
    chk('json_pred_rejects_extra', not tryload(good + [dict(good[0], id='z')]))
    chk('json_pred_rejects_bad_grade', not tryload([dict(good[0], pred=7), good[1]]))
    gp = os.path.join(td, 'w.jsonl')
    open(gp, 'wb').write(b'{"id": "a"}\\n{"id": "b", "te')
    r1 = GN.repair_tail(gp)
    chk('gen_repair_torn_tail', r1 is not None and open(gp, 'rb').read() == b'{"id": "a"}\\n')
    open(gp, 'wb').write(b'{"id": "a"}\\n{"id": "b"}')
    chk('gen_complete_last_line_without_newline_kept', GN.repair_tail(gp) is None and open(gp, 'rb').read().endswith(b'}'))
    open(gp, 'wb').write(b'{"id": "a"}\\n')
    chk('gen_repair_noop_on_clean', GN.repair_tail(gp) is None)
fails = [k for k, v in res.items() if not v['pass']]
out = 'results/iter_076/tests/fixtures_cpu.json'""")
s=s.replace("""print(len(res), 'checks', len(fails), 'fails', fails)""","""print(len(res), 'checks', len(fails), 'fails', fails)
sys.exit(1 if fails else 0)""")
open(p,'w').write(s)
PYEOF
python test_sp75.py 2>&1 | tail -5
- Bash: sed -i 's#结果#결과#' test_sp75.py; grep -n "iter_075/tests\|print(len(res)" test_sp75.py
- Monitor: {"description": "resume test (det_ref/A/B, g1, nd) progress or failure", "timeout_ms": 1800000, "command": "until [ -f results/iter_076/tests/resume/resume_compare.json ]; do if grep -lE \"Traceback|OutOfMemoryError\" results/iter_076/tests/resume/*.out >/dev/null 2>&1; then echo \"ERROR in: $(grep -lE 'Traceback|OutOfMemoryError' results/iter_076/tests/resume/*.out | tr '\\n' ' ')\"; break; fi; sleep 60; done; ls results/iter_076/tests/resume | tr '\\n' ' '"}
