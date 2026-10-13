"""iter_135: 자료 연결 증거 + 저장 출력의 thought/final 구조 감사 (CPU, 신규 생성 없음).
원 iter_134 결과는 읽기만 한다. final 상태는 정확도/BA에 쓰지 않는다. 설명문의 임상 정답 여부는 판정하지 않는다."""
import glob, hashlib, json, os, re, sys, time, urllib.request
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import i134_spec as S

R = Path('results')
I134 = R / 'iter_134'
OUT = R / 'iter_135'
OFF = OUT / 'data_evidence' / 'official'
MIRROR = ('MedOtter/brats2023-gli-dataset', 'b032d353a3e80911a5f850bc54e6fb575298a354')
RG = ('JiayuLei/RadGenome-Brain_MRI', '0348ba42fad134da57b50e736ba858a8e73eb086')
THOUGHT_START, THOUGHT_END = 100, 101   # <unused94>, <unused95> (로컬 tokenizer로 확인)
SYN = 'https://repo-prod.prod.sagebase.org/repo/v1/entity/'


def sha(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()


def baseline_hashes():
    files = [p for p in glob.glob(str(I134 / '**' / '*'), recursive=True)
             if os.path.isfile(p) and '/_dl/' not in p and not p.endswith('.png') and 'neg_tmp' not in p]
    files += [str(Path('../agent/runs/iter_134') / n) for n in ('plan.md', 'review.json', 'review.md')]
    return {p: sha(p) for p in sorted(files) if os.path.exists(p)}


def load_jobs(job):
    return [json.loads(l) for f in sorted(glob.glob(str(I134 / 'jobs' / job / 'worker*.jsonl'))) for l in open(f)]


def synapse(path):
    try:
        r = urllib.request.urlopen(SYN + path, timeout=30)
        return dict(status=r.status, body=r.read()[:600].decode())
    except Exception as e:
        return dict(status=getattr(e, 'code', None), body=(e.read()[:400].decode() if hasattr(e, 'read') else str(e)))


def data_evidence():
    from huggingface_hub import HfApi
    os.environ.setdefault('HF_TOKEN_PATH', '/home/test/.cache/huggingface/token')
    api = HfApi()
    man = json.load(open(I134 / 'data' / 'data_manifest_v2.json'))
    cases = man['cases']
    # 기술4 + 평가32 = 36
    sel = json.load(open(I134 / 'data' / 'selection_v2.json'))
    tech_ids = [c if isinstance(c, str) else c.get('pid') for c in sel['technical']]
    main_ids = [c if isinstance(c, str) else c.get('pid') for c in sel['main']]
    ids = sorted(cases)
    mi = api.dataset_info(MIRROR[0], revision=MIRROR[1])
    mirror_files = {s.rfilename for s in mi.siblings}
    all_pids = sorted({f.split('/')[1] for f in mirror_files if f.startswith('ASNR-') and f.count('/') == 2})
    ri = api.dataset_info(RG[0], revision=RG[1])
    split = json.load(open(OFF / 'JiayuLei__RadGenome-Brain_MRI' / 'train_val_test_split.json'))
    key2split = {k: s for s, ks in split.items() for k in ks}
    gf = json.load(open(OFF / 'JiayuLei__RadGenome-Brain_MRI' / 'BraTS_GLI' / 'global_finding.json'))
    mw = json.load(open(OFF / 'JiayuLei__RadGenome-Brain_MRI' / 'BraTS_GLI' / 'modal_wise_finding.json'))
    prefix_count = Counter(p.rsplit('-', 1)[0] for p in all_pids)
    rows = []
    for pid in ids:
        key = pid + '-t2f'
        pre = pid.rsplit('-', 1)[0]
        rows.append(dict(
            pid=pid, role='technical' if pid in tech_ids else ('main' if pid in main_ids else 'unlisted'),
            radgenome_split=key2split.get(key), in_modal_wise_finding=key in mw,
            in_global_finding=pid in gf,
            mirror_flair_present=f'ASNR-MICCAI-BraTS2023-GLI-Challenge-TrainingData/{pid}/{pid}-t2f.nii.gz' in mirror_files,
            mirror_seg_present=f'ASNR-MICCAI-BraTS2023-GLI-Challenge-TrainingData/{pid}/{pid}-seg.nii.gz' in mirror_files,
            other_scan_ids_same_prefix_in_mirror=sorted(p for p in all_pids if p.startswith(pre + '-') and p != pid),
            report_key_in_manifest=cases[pid].get('report_key')))
    # 같은 5자리 prefix(동일 환자의 다른 시점 가능성)가 36 case 안에 중복되는지
    within = Counter(r['pid'].rsplit('-', 1)[0] for r in rows)
    ev = dict(
        created_at=time.strftime('%Y-%m-%dT%H:%M:%S%z'),
        n_cases=len(rows), n_technical=sum(r['role'] == 'technical' for r in rows), n_main=sum(r['role'] == 'main' for r in rows),
        status_labels={'confirmed': '직접 확인', 'unconfirmed': '미확인', 'mismatch': '불일치'},
        mirror=dict(repo=MIRROR[0], revision=mi.sha, requested_revision=MIRROR[1], license_card=mi.card_data.to_dict().get('license'),
                    readme_sha256=sha(OFF / 'MedOtter__brats2023-gli-dataset' / 'README.md'), n_files=len(mirror_files), n_patients_scans=len(all_pids),
                    official_origin_claim='README: Dataset Homepage https://www.synapse.org/#!Synapse:syn51156910; 공식 BraTS data use 인증 문구 없음',
                    is_official_release=False, verdict='unconfirmed: 비공식 미러, 원천 BraTS 이용 조건 승계 근거 없음'),
        radgenome=dict(repo=RG[0], revision=ri.sha, requested_revision=RG[1], license_card=ri.card_data.to_dict().get('license'),
                       readme_sha256=sha(OFF / 'JiayuLei__RadGenome-Brain_MRI' / 'README.md'),
                       split_file_sha256=sha(OFF / 'JiayuLei__RadGenome-Brain_MRI' / 'train_val_test_split.json'),
                       n_gli_global_reports=len(gf), n_gli_modal_wise=len(mw), split_sizes={k: len(v) for k, v in split.items()},
                       note='README는 license 헤더만 있음(24 bytes). 원천 BraTS release 연결 설명 없음. 현재 revision과 과거 문서(MIT) 문자열 일치.'),
        synapse=dict(
            project_syn51156910=synapse('syn51156910'), project_access_requirements=synapse('syn51156910/accessRequirement'),
            mapping_entity_syn51615438=synapse('syn51615438'), mapping_file_download=synapse('syn51615438/file'),
            mapping_verdict='unconfirmed: 항목 존재·이름(BraTS2023_2017_GLI_Mapping.xlsx)은 확인, 파일 내용은 403(unmet access requirements). Synapse 로그인·약관 필요, 우회하지 않음.'),
        linkage=dict(
            radgenome_report_to_case=dict(confirmed=sum(r['in_modal_wise_finding'] for r in rows), of=len(rows)),
            case_split_counts=dict(Counter(str(r['radgenome_split']) for r in rows)),
            mirror_files_present=dict(flair=sum(r['mirror_flair_present'] for r in rows), seg=sum(r['mirror_seg_present'] for r in rows)),
            same_prefix_duplicates_within_36={k: v for k, v in within.items() if v > 1},
            cases_with_other_scan_ids_in_mirror=[r['pid'] for r in rows if r['other_scan_ids_same_prefix_in_mirror']],
            msd_link='unconfirmed: BraTS2023↔2017 mapping 미접근, MSD Task01은 익명 ID라 ID 관계 부재. 영상 유사도 추측으로 인증하지 않음.',
            patient_independence='unconfirmed'),
        rows=rows)
    return ev


def final_split(rec):
    """토큰 id 위치로 thought/final 경계를 구조적으로 찾는다 (문자열 삭제·상태 단어 검색 없음)."""
    t = rec['tokens']
    has_s, has_e = THOUGHT_START in t, THOUGHT_END in t
    final_text = None
    if has_e:
        # 디코딩된 text에서 같은 마커 위치로 분할 (text는 special token 유지 상태)
        parts = rec['text'].split('<unused95>')
        final_text = parts[-1] if len(parts) == 2 else None
    elif not has_s:
        final_text = rec['text']
    ordered = (not (has_s and has_e)) or t.index(THOUGHT_START) < t.index(THOUGHT_END)
    return has_s, has_e, ordered, final_text


def structure_audit():
    out = {}
    cand = []
    for job in ('main', 'Tb_w2'):
        recs = load_jobs(job)
        by_cond = defaultdict(Counter)
        per = []
        for r in recs:
            cond = r['id'].split('__')[1]
            has_s, has_e, ordered, ft = final_split(r)
            strict = S.parse(r['text'], r['eos'])
            fin = S.parse(ft.lstrip('\n') if ft is not None else None, r['eos']) if ft is not None and has_e else None
            c = by_cond[cond]
            c['n'] += 1; c['eos'] += int(r['eos']); c['thought_start'] += int(has_s); c['thought_end'] += int(has_e)
            c['thought_open_no_final'] += int(has_s and not has_e); c['order_violation'] += int(not ordered)
            c['strict_valid_original'] += int(strict is not None)
            if has_e:
                c['final_structurally_extractable'] += int(fin is not None)
            per.append(dict(id=r['id'], cond=cond, eos=r['eos'], n_tokens=r['n_tokens'], thought_start=has_s, thought_end=has_e,
                            ordered=ordered, strict_state_original=strict, final_first_line_state=fin))
            # 첫 줄/설명 불일치 자동 후보 (원문 그대로 보존, 판정 아님)
            if cond != 'NONE':
                a = S.audit(r['text'], strict)
                if a == 'contradiction':
                    cand.append(dict(job=job, id=r['id'], strict_state=strict, text=r['text'], note='candidate only; scope/target unresolved by design'))
        out[job] = dict(n=len(recs), by_condition={k: dict(v) for k, v in sorted(by_cond.items())},
                        totals=dict(sum((Counter(v) for v in by_cond.values()), Counter())), per_record=per)
    return out, cand


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    before = baseline_hashes()
    json.dump(before, open(OUT / 'baseline_hashes_before.json', 'w'), indent=1)
    t1 = time.time()
    ev = data_evidence()
    t2 = time.time()
    st, cand = structure_audit()
    t3 = time.time()
    after = baseline_hashes()
    assert before == after, 'iter_134 baseline files changed'
    json.dump(ev, open(OUT / 'data_evidence.json', 'w'), indent=1, ensure_ascii=False)
    json.dump(st, open(OUT / 'output_structure_audit.json', 'w'), indent=1, ensure_ascii=False)
    json.dump(cand, open(OUT / 'contradiction_candidates.json', 'w'), indent=1, ensure_ascii=False)
    json.dump(dict(n_files=len(before), unchanged=True, wall_s=dict(hash=t1 - t0, data_evidence=t2 - t1, structure=t3 - t2)),
              open(OUT / 'invariance.json', 'w'), indent=1)
    print('ok', len(before), 'files unchanged; candidates', len(cand))


if __name__ == '__main__':
    main()
