"""iter_078 E24 사전 잠금 생성. E24 출력 전에 검색 은행·참고 map·Q 출처·M 선택·checkpoint·prompt·parser·metric·코드를 hash로 고정한다."""
import glob, hashlib, json, os, sys

OUT = 'results/iter_078'


def sha_file(p):
    return hashlib.sha256(open(p, 'rb').read()).hexdigest()


def main():
    path = f'{OUT}/eval/eval_lock_E24.json'
    if os.path.exists(path):
        sys.exit('lock exists')
    rep = json.load(open(f'{OUT}/eval/report_V8.json'))
    if not rep['proceed_to_E24']:
        sys.exit('V8 rule says hold E24')
    files = ['rf78_ref.py', 'rf78_vlm.py', 'rf78_gen.py', 'rf78_eval.py', 'rf78_launch.py', 'sp75_gen.py', 'sp75_vlm.py', 'sp75_metrics.py', 'sp75_c.py', 'sp75_data.py', 'g71_data.py', 'sp67_data.py',
             'rsna_diag/generate.py', 'rsna_diag/lora.py', 'rsna_diag/queue_lock.py', 'rsna_diag/geometry.py', 'rsna_diag/prompts.py', 'rsna_diag/mi19_mha.py', 'rsna_diag/mi19_render.py',
             f'{OUT}/features.json', f'{OUT}/data/refs_E24.json', f'{OUT}/data/labels_E24.json', f'{OUT}/data/refs_V8.json', f'{OUT}/eval/select_M.json', f'{OUT}/eval/report_V8.json',
             'results/iter_075/data/manifest.json', 'results/iter_075/C/selection.json', 'results/iter_075/C/lr0.0001/epoch_40.pt',
             'results/iter_077/train/R_lr2e-4/epoch_16/adapter.pt']
    files += sorted(glob.glob('results/iter_077/gen/E24/R_adapted/gen_worker*.jsonl')) + sorted(glob.glob('results/iter_077/gen/V8/R_lr2e-4_ep16/gen_worker*.jsonl'))
    lock = {'files': {f: sha_file(f) for f in files}, 'requests': {'E24': sha_file(f'{OUT}/data/refs_E24.json')}, 'adapter_digest': '72417dc383a99d36b797f77d12d050124749abf370b220c70108cc51b88cfc2c',
            'split': 'E24', 'dirs': {c: f'{OUT}/gen/E24_main/{c}' for c in 'LID'}, 'select_M_sha256': sha_file(f'{OUT}/eval/select_M.json'),
            'note': 'V8 판정 후 E24 생성 전 잠금. 이후 prompt/참고 수/검색기/checkpoint/M 변경 없음.'}
    json.dump(lock, open(path, 'w'), indent=1)
    print('locked', len(files))


if __name__ == '__main__':
    main()
