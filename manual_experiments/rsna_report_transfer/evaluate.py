"""블라인드 문장 분류를 고정한 뒤 환자별 paired 비교를 계산한다."""
import json
from collections import Counter
import numpy as np
from .run import OUT, save, sha


def main():
    generated={}
    for model in ('base','sft'):
        marker=json.loads((OUT/f'{model}_completed.json').read_text())
        assert marker['output_sha256']==sha(OUT/f'{model}.jsonl')
        rows=[json.loads(s) for s in (OUT/f'{model}.jsonl').read_text().splitlines()]
        assert len(rows)==len({r['id'] for r in rows})==60
        generated[model]={r['id']:r for r in rows}
    assert set(generated['base'])==set(generated['sft'])
    for id_,r in generated['base'].items():
        other=generated['sft'][id_]
        for field in ('input_ids_sha256','input_pixel_sha256','prompt_sha256','protocol_digest'):
            assert r[field]==other[field],(id_,field)
    reports=json.loads((OUT/'blinded_reports.json').read_text())
    annotations=json.loads((OUT/'annotations.json').read_text())
    assert set(annotations)=={r['id'] for r in reports}
    for r in reports:
        a=annotations[r['id']]
        assert a['target'] in ('present','possible','absent','unmentioned','invalid')
        assert a['quote'] and a['quote'] in r['text']
        assert a['report_valid']==(a['target']!='invalid')
    key=json.loads((OUT/'blind_key.json').read_text())
    labels=json.loads((OUT/'labels.json').read_text())
    paired={}
    for r in reports:
        k=key[r['id']]
        paired.setdefault(k['patient_id'],{})[k['model']]={**r,**annotations[r['id']]}
    assert len(paired)==60 and all(set(p)=={'base','sft'} for p in paired.values())
    summary={'annotation_sha256':sha(OUT/'annotations.json'),'groups':{}}
    rng=np.random.default_rng(20261006)
    for category in ('opacity','normal','not_normal_no_opacity'):
        ps=[p for id_,p in paired.items() if labels[id_]['category']==category]
        a=np.array([[int(p[m]['target'] in ('present','possible')) for m in ('base','sft')] for p in ps])
        delta=a[:,1]-a[:,0]
        ci=np.quantile(delta[rng.integers(0,len(ps),size=(10000,len(ps)))].mean(axis=1),[.025,.975])
        summary['groups'][category]={'n':len(ps),'base_mentions':int(a[:,0].sum()),'sft_mentions':int(a[:,1].sum()),
            'new_mentions':int(((a[:,0]==0)&(a[:,1]==1)).sum()),'lost_mentions':int(((a[:,0]==1)&(a[:,1]==0)).sum()),
            'both_mentions':int((a.sum(axis=1)==2).sum()),'neither_mentions':int((a.sum(axis=1)==0).sum()),
            'difference':float(delta.mean()),'paired_bootstrap_95ci':ci.tolist(),
            'categories':{m:dict(Counter(p[m]['target'] for p in ps)) for m in ('base','sft')}}
    summary['quality']={m:{'valid_reports':sum(p[m]['report_valid'] for p in paired.values()),
        'truncated':sum(p[m]['truncated'] for p in paired.values()),
        'contradictions':sum(p[m]['contradiction'] for p in paired.values())} for m in ('base','sft')}
    save(OUT/'summary.json',summary)
    save(OUT/'paired_assessments.json',{id_:{'label':labels[id_],**p} for id_,p in sorted(paired.items())})
    lines=['# 환자별 원문 비교','',
           '동일 영상·동일 질문. 분류는 모델명과 정답을 숨기고 assistant가 수행했으며 전문의 판독 검증이 아니다.','']
    for id_,p in sorted(paired.items()):
        lines.extend([f"## {id_} | 정답 분류: {labels[id_]['category']}",''])
        for m,title in (('base','기본 MedGemma'),('sft','RSNA bbox LoRA SFT')):
            r=p[m]
            lines.extend([f'### {title}','',r['text'],'',
                f"문장 분류: {r['target']} / 출력 절단: {r['truncated']} / 근거: {r['quote']}",''])
    (OUT/'PAIRED_REPORTS.md').write_text('\n'.join(lines))
    print(json.dumps(summary,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
