"""출력 전 정답 항목 잠금과 원문 인용 판정표의 산술. 자동 임상 판정기가 아니다."""
import argparse
import re
import numpy as np
from i143_data import OUT
from i141_common import read,save,sha,now

LOCATIONS={
'0139':['brainstem'], '0038':['left external capsule region','frontal lobe'],
'0018':['brainstem'], '0228':['bilateral basal ganglia region','around the lateral ventricles','both frontal and parietal lobes'],
'0124':['adjacent to the right lateral ventricle','external capsule'], '0174':['brainstem'],
'0118':['left external capsule region','alongside the lateral ventricle','frontal-temporal lobe'],
'0020':['left frontal-parietal lobe'],
'0014':['bilateral cerebellum','left occipital lobe','basal ganglia region','periventricular area of the lateral ventricles','right frontal lobe'],
'0053':['alongside the right lateral ventricle'], '0248':['left frontal-parietal-occipital-temporal insular lobes'],
'0092':['bilateral cerebellum','right occipital lobe','thalamus'], '0046':['midbrain'], '0148':['right cerebellum'],
'0119':['junction area of the right frontal and parietal lobes'], '0136':['brainstem'], '0106':['left cerebellum'],
'0117':['left basal ganglia region'],
'0039':['right frontal-temporal-occipital lobes','insula','periventricular region adjacent to the lateral ventricles','junction of the bilateral frontal and parietal lobes','left cerebellum'],
'0144':['junction area of the right frontal and parietal lobes'], '0129':['left thalamus','bilateral occipital lobes'],
'0062':['right frontal parietal temporal insular lobes','right cerebellum'],
'0211':['left basal ganglia region','periventricular area','frontal-temporal-parietal-occipital lobes'],
'0078':['both cerebella','brainstem','junction area of the right frontal and parietal lobes'],
'0159':['right external capsule region','frontal-temporal-parietal lobe'], '0125':['left temporal-occipital lobe','thalamus'],
'0115':['midbrain'], '0170':[], '0165':['right frontal parietal lobe','insular lobe'], '0111':['right frontal lobe'],
'0157':['both cerebellar hemispheres','brainstem'], '0132':['brainstem','bilateral cerebellum'],
'0173':['brainstem','bilateral cerebellum','vermis','right parietal lobe'],
'0223':['left frontal-parietal-temporal-occipital lobes','cerebellum','left basal ganglia region'],
'0158':['right frontal lobe','insula','occipital lobe','left basal ganglia region'], '0233':['brainstem'],
'0149':['brainstem'], '0214':['right basal ganglia region','adjacent to the lateral ventricle','frontal, parietal, and temporal lobes'],
'0094':['left basal ganglia','thalamus','parahippocampal gyrus','brainstem','bilateral cerebellum'],
'0105':['left cerebellum'], '0017':['left frontal lobe','junction area of the parieto-occipital lobe','basal ganglia area','right frontal lobe'],
'0204':['right basal ganglia region','frontal lobe'],
'0083':['right basal ganglia','capsule externa','frontal-parietal-temporal lobes','brain stem','right cerebellum'],
'0089':['adjacent to the posterior horn of the left lateral ventricle'], '0128':['left cerebellum'],
'0114':['left basal ganglia region','external capsule area','around the lateral ventricle'],
'0023':['brainstem','left frontal-parietal-temporal-occipital lobe','basal ganglia region','bilateral corona radiata','right frontal-parietal-occipital lobe','right cerebellum'],
'0212':['brainstem','bilateral cerebellum']}

CONTRACT=dict(
    primary='환자별 공개 항목 matched/전체 항목의 환자 평균. finding/signal/location/morphology/distribution별 병기.',
    match='같은 DWI 소견에 대한 명시적 항목만 matched. 명시 좌우·위치 구성요소가 모두 필요. 원문 생략 좌우를 추론하지 않는다.',
    uncertain='애매한 동의어·대응은 unresolved. 비EOS/invalid boundary에서 아직 안 나온 항목도 unresolved로 상한에 유지.',
    contradiction='같은 범위의 명시 반대 주장만 확정. 미완결 출력은 관측 모순과 별도로 추가 모순 가능 상한1.',
    extra='정답 미언급 소견은 미검증 추가 주장. 임상 허위로 간주하지 않는다.',
    assessor='assistant 텍스트 대응, 전문의 임상 평가 아님. 조건·epoch를 가린 package와 원문 인용 사용.',
    positive='A-S lower semantic recall difference >=.05 AND upper contradiction difference <=.05; CI crosses0 => promising inconclusive',
    negative='유효 학습 및 의미 범위상 반전 없음, A-S paired95% upper <.05',
    extension='V epoch4→8 conservative recall +.02 OR target NLL -5% and contradiction count nonincreasing; loss-only with worse generation does not extend.',
    checkpoint='공통 epoch8 또는16, 조건별 선택 없음',
    swap_selection='최종 V conservative recall 최대, 모순 최소, 동률 N/S/A',
    bootstrap=dict(seed=17,replicates=10000,unit='patient',percentiles=[2.5,97.5]))


def lock():
    refs=read(OUT/'reference_locked.json')['rows']; output=[]
    for r in refs:
        text=r['original_text']; target=r['target']; pid=r['patient_id']; atoms=[]
        def add(kind,quote,label=None):
            start=text.lower().index(quote.lower()); quote=text[start:start+len(quote)]
            atoms.append(dict(id=f'{pid}__{len(atoms):02d}',type=kind,quote=quote,start=start,end=start+len(quote),label=label or quote.lower()))
        if pid.endswith('0170'):
            add('signal',target,'no conspicuous DWI hyperintensity')
        else:
            m=re.search(r'abnormal signals?|abnormal flake-like signal intensity',text,re.I)
            assert m,pid
            add('finding',m.group(),'abnormal signal')
            for m in re.finditer(r'(?:high|low) (?:signal intensity|signals?) on (?:the )?DWI(?: sequence)?|(?:high|low) DWI signals?|hyperintense on DWI',target,re.I):
                # 0078/0223 추가 저신호의 위치는 반드시 함께 대응하도록 label에 고정.
                q=m.group(); label='DWI high signal' if ('high' in q.lower() or 'hyperintense' in q.lower()) else 'DWI low signal'
                if 'low' in label and pid.endswith('0078'): label+=' in parts of brainstem'
                if 'low' in label and pid.endswith('0223'): label+=' in left basal ganglia region'
                add('signal',q,label)
            for word in ['scattered','dispersed','disseminated','multiple']:
                if re.search(r'\b'+word+r'\b',target,re.I): add('distribution',word,word)
            for word in ['patchy','plaque-like','plaques','punctate','spot-like','spotty','speckled','sheet-like','flake-like','nodular','small']:
                if re.search(r'\b'+word+r'\b',target,re.I): add('morphology',word,word)
            for q in LOCATIONS[pid[-4:]]: add('location',q)
            assert any(a['type']=='signal' for a in atoms),pid
        output.append(dict(patient_id=pid,split=r['split'],atoms=atoms))
    train=[r for r in output if r['split']=='T']
    sets={r['patient_id']:{a['type']+':'+a['label'] for a in r['atoms']} for r in train}
    scores={pid:sum(len(s&t)/len(s|t) for other,t in sets.items() if other!=pid)/(len(sets)-1) for pid,s in sets.items()}
    prior=min(scores,key=lambda x:(-scores[x],x))
    save(OUT/'eval_contract.json',dict(created_at=now(),contract=CONTRACT,reference_sha256=sha(OUT/'reference_locked.json'),
         code_sha256=sha(__file__),rows=output,prior_patient=prior,prior_scores=scores,
         prior_text=next(r['target'] for r in refs if r['patient_id']==prior)))
    print('평가 항목 잠금',sum(len(r['atoms']) for r in output),'prior',prior)


def paired_ci(a,b):
    delta=np.asarray(a)-np.asarray(b); rng=np.random.default_rng(17)
    samples=delta[rng.integers(0,len(delta),size=(10000,len(delta)))].mean(1)
    return dict(mean=float(delta.mean()),ci95=np.percentile(samples,[2.5,97.5]).tolist())


if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('command',choices=['lock']); a=p.parse_args(); lock()
