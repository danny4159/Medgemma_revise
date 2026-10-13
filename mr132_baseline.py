"""독립 환자60명의 fold 내부 전처리로 MRIQC 대조 선택."""
import itertools, time, joblib, numpy as np, sys, platform
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import KFold
import sklearn, scipy
from mr132_common import RES,read,save,sha,now
from mr132_preflight import rows
from mr132_spec import ACQS,PAIRS

def subject_accuracy(subs,values,labels):
    acc=[]
    for sub in subs:
        y=[labels[f'{sub}_acq-{a}_T1w'] for a in ACQS]; v=[values[f'{sub}_acq-{a}_T1w'] for a in ACQS]
        pair=[]
        for i,j in PAIRS:
            if y[i]==y[j]: continue
            pair.append(.5 if v[i]==v[j] else float((v[i]<v[j])==(y[i]<y[j])))
        if pair: acc.append(np.mean(pair))
    return float(np.mean(acc))

def main():
    start=time.monotonic(); lock=read(RES/'split_lock.json'); train=lock['splits']['iqm_train']
    iq=rows(RES/'metadata/IQMs.tsv'); scores=rows(RES/'metadata/scores.tsv'); labels={k:int(r['score']) for k,r in scores.items()}
    columns=[c for c in next(iter(iq.values())) if c!='bids_name' and not c.startswith(('size_','spacing_'))]
    assert all(c not in ['score','subject','age','sex','acq'] for c in columns)
    def X(keys):
        return np.array([[float(iq[k][c]) if iq[k][c].strip().lower() not in ['','nan','n/a'] else np.nan for c in columns] for k in keys])
    keys=[f'{s}_acq-{a}_T1w' for s in train for a in ACQS]; xx=X(keys); yy=np.array([labels[k] for k in keys]); assert not np.isinf(xx).any()
    candidates=[('logistic_C'+str(c),dict(kind='logistic',C=c)) for c in [.1,1,10]]+ [('forest_leaf'+str(c),dict(kind='forest',min_samples_leaf=c)) for c in [2,5]]
    def model(cfg):
        learner=LogisticRegression(C=cfg['C'],solver='lbfgs',max_iter=5000,random_state=132) if cfg['kind']=='logistic' else RandomForestClassifier(n_estimators=300,min_samples_leaf=cfg['min_samples_leaf'],max_features='sqrt',random_state=132,n_jobs=4)
        return make_pipeline(SimpleImputer(strategy='median',keep_empty_features=True),StandardScaler(),learner)
    folds=list(KFold(n_splits=5,shuffle=True,random_state=132).split(train)); cv={}; outpred={}
    for name,cfg in candidates:
        pred={}; fold_records=[]
        for f,(a,b) in enumerate(folds):
            ai=np.concatenate([np.arange(i*3,i*3+3) for i in a]); bi=np.concatenate([np.arange(i*3,i*3+3) for i in b]); m=model(cfg); m.fit(xx[ai],yy[ai]); prob=m.predict_proba(xx[bi]); val=prob @ m[-1].classes_
            pred.update({keys[i]:float(v) for i,v in zip(bi,val)})
            fold_records.append(dict(fold=f,train_subjects=[train[i] for i in a],validation_subjects=[train[i] for i in b],imputer_statistics=m[0].statistics_.tolist(),scaler_mean=m[1].mean_.tolist()))
        cv[name]=dict(config=cfg,accuracy=subject_accuracy(train,pred,labels),folds=fold_records); outpred[name]=pred
    learner=sorted(cv,key=lambda name:(-cv[name]['accuracy'],0 if cv[name]['config']['kind']=='logistic' else 1,list(cv).index(name)))[0]
    single={c:{k:float(r[c])*( -1 if c=='snr_total' else 1) for k,r in iq.items()} for c in ['cjv','efc','snr_total']}
    single_acc={c:subject_accuracy(train,v,labels) for c,v in single.items()}; best_single=max(single_acc,key=single_acc.get)
    strongest=learner if cv[learner]['accuracy']>single_acc[best_single] else best_single
    best=model(cv[learner]['config']); best.fit(xx,yy)
    out=RES/'baseline'; out.mkdir(exist_ok=False)
    joblib.dump(best,out/'selected_pipeline.joblib')
    # 보존 환자의 IQM도 예측하되 영상·VLM 출력은 열지 않는다. 설정은 CV60에서만 고른다.
    eval_keys=[f'{s}_acq-{a}_T1w' for stage in ['technical','development','holdout'] for s in lock['splits'][stage] for a in ACQS]
    pred=best.predict_proba(X(eval_keys)) @ best[-1].classes_
    vals=dict(single); vals[learner]={k:float(v) for k,v in zip(eval_keys,pred)}
    save(out/'predictions.json',dict(values=vals,selected_strongest=strongest,selected_single=best_single,selected_classifier=learner))
    save(out/'selection_lock.json',dict(created_at=now(),train_subjects=train,features=columns,excluded_features=[c for c in next(iter(iq.values())) if c not in columns],cv=cv,single_cv_accuracy=single_acc,selected_single=best_single,selected_classifier=learner,selected_strongest=strongest,pipeline_sha256=sha(out/'selected_pipeline.joblib'),predictions_sha256=sha(out/'predictions.json'),inputs={str(p):sha(p) for p in [RES/'split_lock.json',RES/'metadata/IQMs.tsv',RES/'metadata/scores.tsv']},code_sha256=sha(__file__),python=sys.executable,versions=dict(sklearn=sklearn.__version__,scipy=scipy.__version__,numpy=np.__version__),wall_s=time.monotonic()-start,iqm_generation_cost='미측정; 저장 표의 pipeline 추론만 측정'))
    print('MRIQC CV 선택',strongest,'단일',single_acc,'학습', {k:v['accuracy'] for k,v in cv.items()})

if __name__=='__main__': main()
