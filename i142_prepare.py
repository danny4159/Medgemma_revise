"""새 SDK 사본을 파생하고 실제 원본 hash와 사전 평가 계약을 잠근다."""
import difflib
import shutil
import subprocess
from i142_common import *
from ar70_patch import EDITS

def main():
    assert not RES.exists(), '기존 결과 경로 보존'
    RES.mkdir()
    reuse = read(ROOT.parent / 'agent/runs/iter_142/reuse_manifest.json')
    for path, info in reuse['files'].items():
        actual = subprocess.check_output(['git','hash-object','--',path], cwd=ROOT, text=True).strip()
        assert actual == info['blob']
    # 원 ZIP의 파일을 현재 공식 소스와 독립 대조한다.
    import zipfile
    archive = ROOT / 'results/iter_070/external/autorg_src.zip'
    with zipfile.ZipFile(archive) as z:
        src_files = {}
        for p in SRC.rglob('*'):
            if not p.is_file() or '__pycache__' in p.parts:
                continue
            name = str(p.relative_to(SRC.parent))
            assert hashlib.sha256(z.read(name)).hexdigest() == sha(p), name
            src_files[str(p)] = sha(p)
    shutil.copytree(SRC, RES/'external', ignore=shutil.ignore_patterns('__pycache__'))
    diff = []
    for filename in dict.fromkeys(e[0] for e in EDITS):
        original = (SRC/filename).read_text()
        text = original
        for file, old, new in EDITS:
            if file == filename:
                assert text.count(old) == 1
                text = text.replace(old,new)
        (RES/'external'/filename).write_text(text)
        diff.extend(difflib.unified_diff(original.splitlines(True),text.splitlines(True),'a/'+filename,'b/'+filename))
    (RES/'external/compatibility.diff').write_text(''.join(diff))
    weights = read(MODELS/'weights_manifest.json')
    weight_files = {}
    for name, h in weights.items():
        if name.endswith(('.model','.pkl')):
            p = MODELS/'autorg'/name
            assert sha(p) == h, name
            weight_files[str(p)] = h
    for p in (MODELS/'gpt2pm').glob('*'):
        if p.is_file():
            weight_files[str(p)] = sha(p)
    # 공식 GPT2 checkpoint는 기존 고정 revision 자산이다. 현 hash를 별도 고정.
    old = read(OLD/'data_manifest.json')
    inputs = []
    for r in old['rows']:
        assert sha(r['source_path']) == r['source_sha256']
        inputs.append({'patient_id':r['patient_id'], 'role':r['role'],
                       'image':r['source_path'],'image_sha256':r['source_sha256'],'modal':'DWI'})
    assert len(inputs)==8 and sum(r['role']=='main' for r in inputs)==6
    save(RES/'inference_inputs.json', inputs)
    save(RES/'asset_manifest.json', {'created_at':now(),'official_source_revision':SRC.name,
         'source_archive_sha256':sha(archive),'source_files':src_files,'weights':weight_files,
         'checkpoint_revisions':weights,'reused_blobs':reuse['files'],
         'environment_python':str(ENV),'base_environment_changed':False,
         'training_exposure':{'SEG':'공식 README에 ISLES2022 학습 명시; 환자별 노출 미확인',
           'RGv2':'공식 README에 RadGenome 학습 명시; 현재 8명 공식 train, 환자별 노출 미확인',
           'DWI_report_target':'DWI dispatch 지원. 배포 modal_wise_finding에는 ADC만 있어 실제 DWI target 학습 미확인'}})
    save(RES/'evaluation_contract.json', {'created_at':now(),
       'contract':read(OLD/'reference_locked.json')['evaluation_contract'],
       'primary':'AutoRG 최종 출력 − 저장된 개별 MedGemma; 환자 평균 명시 양성 atom 일치율',
       'bounds':'절단 시 unmentioned/unresolved를 상한에 포함; 미완결 모순의 최악은 1',
       'decision':'보수적 recall 이득 >=0.05, 모순 증가 최악 <=0.05; 불확실성이 행동을 바꾸면 inconclusive',
       'seed':142,'bootstrap_replicates':10000,'new_clinical_truth':False})
    files = {str(p):sha(p) for p in [ROOT/'i142_common.py',ROOT/'i142_prepare.py',ROOT/'i142_worker.py',ROOT/'i142_launch.py',ROOT/'i142_eval.py',
        RES/'asset_manifest.json',RES/'inference_inputs.json',RES/'evaluation_contract.json',
        OLD/'reference_locked.json',OLD/'eval/report.json',OLD/'eval/per_patient.json',OLD/'data_manifest.json']}
    files.update(weight_files)
    files.update({str(p):sha(p) for p in (RES/'external').rglob('*') if p.is_file()})
    x = {'created_at':now(),'files':files,'technical_max_length':300,'seed':42,
         'model':'RGv2','eval_mode':'region_segtool','main_n':6}
    x['digest'] = digest(x)
    save(RES/'protocol_technical.json',x)
    print({'inputs':len(inputs),'official_files_verified':len(src_files),'weights_verified':len(weight_files),'digest':x['digest']})

if __name__=='__main__':
    main()
