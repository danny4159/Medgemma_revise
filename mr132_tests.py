"""이번 사건 정의·방향·재사용 경계와 실제 protocol 실패 경로 검사."""
import argparse,ast,copy,fcntl,hashlib,json,os,subprocess
from pathlib import Path
import numpy as np,nibabel as nib
from mr132_common import RES,DATA,read,save,sha,digest,now
from mr132_spec import parse,pair_value,expansion

def cpu():
    import mr123_data as renderer
    checks=[]
    def test(name,value):
        checks.append(dict(name=name,pass_=bool(value)))
        if not value:raise AssertionError(name)
    blob=subprocess.check_output(['git','hash-object','--','mr123_data.py'],text=True).strip(); test('source_blob',blob=='c9e673cbb6e495adcfe2d1d264097c2a3d72ee45')
    for s,value in [('0',0),('100',100),('25.5',25.5),('101',None),('-1',None),('Score: 25',None),('25%',None),('NaN',None),('25\nExplanation',25)]:test('score_'+s,parse(s,'single')==value)
    for s,v in [('A','A'),('B','B'),('TIE','TIE'),('UNKNOWN','UNKNOWN'),('A or B',None),('a',None)]:test('choice_'+s,parse(s,'pair')==v)
    test('nonEOS_invalid',parse('A','pair',False) is None)
    test('tie_half',pair_value('TIE',0)==.5 and pair_value('TIE',0,True)==0)
    test('unknown_zero',pair_value('UNKNOWN',0)==0)
    test('expansion_boundary',expansion(.10,.05,.90,.05))
    for values in [(.099,.05,.9,.05),(.10,.049,.9,.05),(.10,.05,.899,.05),(.10,.05,.9,.051)]:test('no_expansion_'+str(values),not expansion(*values))
    a=np.zeros((32,32,8),np.float32); a[3:8,4:9,:]=1; a[22:27,23:28,:]=2
    im=renderer.render_slice(a,3,0,2,[1,1,1]); pixels=np.asarray(im)
    test('radiological_RAS_corners',pixels[770,770,0]>100 and pixels[195,195,0]>240 and pixels[770,195,0]==0)
    ni=nib.Nifti1Image(a,np.diag([-2,3,4,1])); can=nib.as_closest_canonical(ni)
    test('LAS_to_RAS',nib.aff2axcodes(can.affine)==('R','A','S'))
    test('physical_coordinate',np.allclose(ni.affine@np.array([4,5,3,1]),can.affine@np.array([27,5,3,1])))
    for arr in [np.zeros((2,2,2)),np.full((2,2,2),np.nan)]:
        try:renderer.normalization_window(arr,normalization='volume_minmax'); ok=False
        except ValueError:ok=True
        test('invalid_volume_'+str(arr.flat[0]),ok)
    imported=[n.names for n in ast.walk(ast.parse(Path('mr132_data.py').read_text())) if isinstance(n,ast.ImportFrom) and n.module=='mr123_data']
    test('renderer_import_allowlist',[[n.name for n in names] for names in imported]==[['normalization_window','render_slice']])
    m=read(RES/'data/technical_manifest.json')
    test('actual_RAS_finite',all(v['canonical_axcodes']=='RAS' and np.isfinite(v['canonical_affine']).all() and min(v['canonical_zooms'])>0 for v in m['volumes']))
    test('source_and_png_current',all(sha(v['source']['path'])==v['source']['sha256'] and all(sha(p['path'])==p['sha256'] for p in v['pngs']) for v in m['volumes']))
    # 현재 cache 경로에서 source/config 변경은 실제 adapter가 거부한다.
    from mr132_data import render
    original=next(r for r in read(RES/'split_lock.json')['objects'] if r['bids_name']==m['volumes'][0]['bids_name'])
    tampered=copy.deepcopy(original);tampered['md5']='0'*32
    try:render(tampered,0,'technical');ok=False
    except AssertionError:ok=True
    test('changed_source_reject',ok)
    import mr132_data
    old=copy.deepcopy(mr132_data.CFG); mr132_data.CFG['side']=895
    try:render(original,0,'technical');ok=False
    except AssertionError:ok=True
    finally:mr132_data.CFG=old
    test('changed_config_reject',ok)
    test('no_legacy_paths',all(str(DATA) in p['path'] for v in m['volumes'] for p in v['pngs']))
    for c in checks:c['pass']=c.pop('pass_')
    save(RES/'tests/cpu.json',dict(created_at=now(),all_pass=True,checks=checks,visual_inspection=dict(paths=[str(RES/'data/v0000_montage.png'),str(RES/'data/v0001_montage.png')],evidence='실제 view_image 반환을 확인; axial 정렬·뇌 표시 확인; 영상 품질 임상 판정 아님')))
    print('CPU',len(checks),'PASS')

def runtime():
    from mr132_run import load_records,verify_job,requests
    checks=[]
    def test(n,v):
        checks.append(dict(name=n,pass_=bool(v)))
        if not v:raise AssertionError(n)
    pilot=RES/'gen/pilot_b1'; resume=RES/'gen/resume'; req=RES/'requests/pilot.json'
    reference=verify_job(pilot,req); recovered=verify_job(resume,req)
    test('partial_resume_tokens',{r['id']:r['tokens'] for r in reference}=={r['id']:r['tokens'] for r in recovered})
    test('resume_unique_complete',len(recovered)==len(read(req))==len({r['id'] for r in recovered}))
    stamp={str(p):sha(p) for p in resume.glob('worker*.jsonl')}
    verify_job(resume,req);test('complete_immutable',all(sha(p)==h for p,h in stamp.items()))
    # 독립 결과 사본에서 중복·중간 손상·마지막 꼬리·변조를 실제 loader로 검사.
    root=RES/'tests/runtime'; root.mkdir(exist_ok=False)
    line=(json.dumps(reference[0])+'\n').encode()
    for name,raw,repair,expected in [('duplicate',line+line,False,False),('middle_corruption',b'{bad}\n'+line,True,False),('torn_tail',line+b'{bad',True,True),('record_tamper',line.replace(b'"n_tokens":',b'"n_tokens":1,"other":'),False,False)]:
        job=root/name; job.mkdir(); (job/'worker0.jsonl').write_bytes(raw)
        try:out=load_records(job,repair=repair);passed=len(out)==1
        except Exception:passed=False
        test(name,passed==expected)
    altered=copy.deepcopy(read(req));altered[0]['prompt']+=' changed'; path=root/'changed_request.json';save(path,altered)
    try:requests(path);ok=False
    except AssertionError:ok=True
    test('request_tamper_rejected',ok)
    altered=read(req)+[read(req)[0]];path=root/'duplicate_request.json';save(path,altered)
    try:requests(path);ok=False
    except AssertionError:ok=True
    test('duplicate_request_rejected',ok)
    fd=os.open(root/'supervisor.lock',os.O_CREAT|os.O_RDWR,0o600);fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
    cmd=['python','mr132_run.py','launch','--job',str(root),'--requests',str(req)]
    result=subprocess.run(cmd,capture_output=True,text=True);os.close(fd);test('concurrent_launch_rejected',result.returncode!=0 and 'active supervisor/children' in result.stderr)
    for c in checks:c['pass']=c.pop('pass_')
    save(RES/'tests/runtime.json',dict(created_at=now(),checks=checks,all_pass=all(c['pass'] for c in checks)))
    print('runtime',len(checks),'PASS')

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('mode',choices=['cpu','runtime']);a=ap.parse_args()
    cpu() if a.mode=='cpu' else runtime()
