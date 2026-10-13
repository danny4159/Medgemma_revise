"""평가 정보와 추론 요청 분리 및 사전 protocol 잠금."""
import argparse,itertools
from pathlib import Path
from mr132_common import RES,read,save,sha,digest,now
from mr132_spec import SINGLE,PAIR,ACQS,PAIRS,CONFIG

def build(stage):
    m=read(RES/'data'/f'{stage}_manifest.json'); split=read(RES/'split_lock.json'); scores=read(RES/'metadata_audit.json')['objects']
    rr=[]; ll=[]
    for n,sub in enumerate(m['subjects']):
        vv=[next(v for v in m['volumes'] if v['subject']==sub and v['acq']==a) for a in ACQS]
        label=[next(r['score'] for r in scores if r['subject']==sub and r['acq']==a) for a in ACQS]
        ll.append(dict(id=f'{stage}_p{n:03d}',subject=sub,grades=label,stratum='tie' if label[1]==label[2] else 'nontie',bids_names=[v['bids_name'] for v in vv]))
        for kind,group in [('single',[i]) for i in range(3)]+[('pair',[i,j]) for i,j in PAIRS]+[('pair',[j,i]) for i,j in PAIRS]:
            png_groups=[[dict(path=x['path'],sha256=x['sha256'],pixel_sha256=x['pixel_sha256']) for x in vv[i]['pngs']] for i in group]
            r=dict(id=f'{stage}_p{n:03d}_{kind}_'+''.join(map(str,group)),patient=f'{stage}_p{n:03d}',kind=kind,groups=png_groups,prompt=SINGLE if kind=='single' else PAIR)
            r['request_digest']=digest(r); rr.append(r)
    out=RES/'requests'; out.mkdir(exist_ok=True)
    save(out/f'{stage}.json',rr); save(RES/'data'/f'{stage}_labels.json',ll)
    print(stage,len(rr),'requests')

def lock():
    files=[Path(p) for p in ['mr132_common.py','mr132_spec.py','mr132_build.py','mr132_run.py','mr132_eval.py','mr132_verify.py','mr132_tests.py','mr132_tech.py','mr132_data.py','mr132_baseline.py','mr132_preflight.py','mr123_data.py']]
    inputs=[RES/'split_lock.json',RES/'metadata_audit.json',RES/'baseline/selection_lock.json',RES/'baseline/predictions.json',RES/'baseline/selected_pipeline.joblib']
    for stage in ['technical','development']:
        inputs += [RES/'data'/f'{stage}_manifest.json',RES/'data'/f'{stage}_labels.json',RES/'requests'/f'{stage}.json']
    model=Path('../hf_cache/models--google--medgemma-1.5-4b-it/snapshots')/CONFIG['revision']
    models={str(p.resolve()):dict(bytes=p.stat().st_size,sha256=sha(p)) for p in model.iterdir() if p.is_file()}
    save(RES/'protocol_lock_v2.json',dict(locked_at=now(),supersedes_pre_generation_lock=sha(RES/'protocol_lock.json'),config=CONFIG,code={str(p.resolve()):sha(p) for p in files},inputs={str(p.resolve()):sha(p) for p in inputs},model_files=models,metric=dict(primary='patient_mean_nontied_pair_accuracy',tie=.5,invalid=0,unknown=0,bootstrap=10000,seed=132,stratified_by='headmotion_grade_tie',order_consistency='same canonical choice among A/B/TIE; UNKNOWN or invalid counted inconsistent; all three pairs',expansion=dict(delta_single=.10,delta_iqm=.05,order_consistency=.90,invalid_unknown=.05))))
    print('평가·입력·모델 사전 잠금',sha(RES/'protocol_lock_v2.json'))

if __name__=='__main__':
    ap=argparse.ArgumentParser(); ap.add_argument('stage',choices=['technical','development','holdout','lock']); a=ap.parse_args()
    lock() if a.stage=='lock' else build(a.stage)
