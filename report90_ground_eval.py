"""문장 조건부 grounding의 완전성 검사와 독립 matching 대조."""
import argparse
import json
from pathlib import Path
import numpy as np
import report90_gen_safe as S
from report90_numeric import OUT
from report86_common import save,sha
import report89_model as M
from rsna_diag.parse import parse_response,VALID
from rsna_diag.metrics import patient_metrics

def independent(pred,gt,t):
    def iou(a,b):
        inter=max(0,min(a[2],b[2])-max(a[0],b[0]))*max(0,min(a[3],b[3])-max(a[1],b[1]))
        union=(a[2]-a[0])*(a[3]-a[1])+(b[2]-b[0])*(b[3]-b[1])-inter
        return inter/union if union else 0
    matched={}
    def aug(j,seen):
        for k,p in enumerate(pred):
            if k not in seen and iou(gt[j],p)>=t:
                seen.add(k)
                if k not in matched or aug(matched[k],seen):matched[k]=j;return True
        return False
    tp=sum(aug(j,set()) for j in range(len(gt)))
    return 2*tp/(len(gt)+len(pred)) if len(gt)+len(pred) else 0.

def run(a):
    stage=Path(a.stage).resolve();proto=json.loads((stage/'protocol.json').read_text());workers=json.loads((stage/'mapping.json').read_text())['workers']
    records,expected=S.verify(stage,a.requests,proto,workers);assert len(records)==len(expected) and (stage/'completion.json').exists()
    rows=json.loads(Path(a.manifest).read_text());by={r['ImageID']+'|ground':r for r in rows};assert set(by)==set(expected)
    per=[]
    for rec in records:
        row=by[rec['id']];target=M.ground_target(row,0);assert expected[rec['id']]['prompt']==target[0]
        gt=[v['box_2d'] for v in json.loads(target[1])];parsed=parse_response(rec['text'],rec['attempts'][-1]['ended_eos'])
        if parsed['status'] in VALID and any(x!='finding' for x in parsed['labels']):parsed['status']='wrong_label'
        pred=parsed['boxes'] if parsed['status'] in VALID else []
        scores={str(t):patient_metrics(pred,gt,t)['f1'] for t in (.3,.5)}
        checks={str(t):abs(scores[str(t)]-independent(pred,gt,t))<1e-12 for t in (.3,.5)};assert all(checks.values())
        per.append(dict(id=rec['id'],patient=row['PatientID'],scores=scores,status=parsed['status'],independent=checks,gt=gt,pred=pred,record_digest=rec['record_digest']))
    save(a.output,dict(n=len(per),scores={str(t):float(np.mean([r['scores'][str(t)] for r in per])) for t in (.3,.5)},
        invalid=sum(r['status'] not in VALID for r in per),per_patient=per,
        sources={p:sha(p) for p in [a.requests,a.manifest,str(stage/'completion.json'),__file__,'report89_model.py','rsna_diag/parse.py','rsna_diag/metrics.py']},
        scope='정답 문장을 제공하는 보조 위치 진단; 자유 판독 정확도와 별개'))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--stage',required=True);p.add_argument('--requests',default=str(OUT/'data/V16/requests.json'));p.add_argument('--manifest',default=str(OUT/'data/V16/manifest.json'));p.add_argument('--output',required=True);run(p.parse_args())
