"""iter_097: 조건명을 가린 재판정(이번)과 iter_090 상속 판정의 환자별 일치도. 같은 reference·같은 score 규칙의 반복 판정 drift 점검."""
import json
from report86_common import save,sha
from report97_train import OUT,ORIGINAL

def load(p,cond):return {x['image_id']:x for x in json.loads(p.read_text()) if x['condition']==cond}

def main():
    new=OUT/'semantic/epoch6/eval/per_output.json'
    pairs=[('base_V32',ORIGINAL/'recovery/semantic/epoch2/eval/per_output.json','base_report'),
           ('R_lr0.0001_report',ORIGINAL/'recovery/semantic/epoch6/eval/per_output.json','R_lr0.0001_report'),
           ('R_lr0.0002_report',ORIGINAL/'recovery/semantic/epoch6/eval/per_output.json','R_lr0.0002_report')]
    refs={r['id']:i for i,r in enumerate(json.loads((ORIGINAL/'semantic/V32_reference_v3.json').read_text())['rows'])}
    out={}
    for cond,oldp,oldc in pairs:
        a=load(new,cond);b=load(oldp,oldc);diffs=[]
        for k in a:
            if a[k]['strict_recall']!=b[k]['strict_recall'] or a[k]['contradiction']!=b[k]['contradiction'] or a[k]['type_recall']!=b[k]['type_recall']:
                diffs.append(dict(ref_index=refs[k],strict=[a[k]['strict_recall'],b[k]['strict_recall']],type=[a[k]['type_recall'],b[k]['type_recall']],
                    contradiction=[a[k]['contradiction'],b[k]['contradiction']],text_equal=None))
        out[cond]=dict(n=len(a),n_patients_differing=len(diffs),differences=diffs)
    save(OUT/'decisions/rejudge_agreement.json',dict(results=out,sources={str(new):sha(new),__file__:sha(__file__)},
        scope='새 batch는 조건명을 가리고 새로 판정; 이전 판정은 iter_090 상속값. 불일치는 판정 drift 또는 규칙 차이.'))
    print(json.dumps({k:v['n_patients_differing'] for k,v in out.items()}));print(json.dumps(out['base_V32']['differences']))

if __name__=='__main__':main()
