"""반복되는 문형(일반 음성문·표준 boilerplate·반복 환각문)에 한해 사전 고정 규칙표로 claim을 만든다.
규칙표는 reference atom과 문장 키워드의 대응만 사용하며, 모델 조건명은 입력으로 받지 않는다.
규칙에 없는 문장이 하나라도 있으면 Unhandled를 발생시켜 사람이 읽고 수동 판정하도록 한다."""
import re
from report92_judge import M,C

class Unhandled(Exception):pass

GENERIC=[r'no (other )?(significant|relevant) (radiological )?findings', r'no findings( of pathological significance)?', r'within normal limits', r'no radiological changes',
         r'no (other )?findings', r'no pathological findings for the patient\'s age', r'no (other )?relevant radiological (findings|alterations)',r'no other significant radiological findings']
# 일반문이 NSF/OTH atom으로 supported 되는지
def generic_refs(sentence,atoms,abnormal):
    s=sentence.lower();other='other' in s
    nsf=[a['id'] for a in atoms if a['finding']=='no significant finding' and a['polarity']=='negative']
    oth=[a['id'] for a in atoms if a['finding']=='other relevant finding']
    if other:return nsf+oth
    return nsf

def pieces(text):
    runs=re.findall(r'[^\[\]\n]+',text);out=[]
    for run in runs:
        for p in re.split(r'(?<=\.)\s+',run):
            p=p.strip()
            if re.search(r'[A-Za-z]{3}',p) and p not in ('FINDINGS:','IMPRESSION:') and not re.fullmatch(r'[0-9., ]+',p):out.append(p)
    return out

def has(atoms,*words,positive=True,definite_only=False):
    r=[]
    for a in atoms:
        if (a['polarity']=='positive')!=positive:continue
        if definite_only and a['certainty']!='definite':continue
        t=(a['finding']+' '+a['location']+' '+a['attributes']).lower()
        if any(w in t for w in words):r.append(a)
    return r

MORPH=('cardiomegaly','pleural effusion','scoliosis','mediastinal','goiter','paratracheal','tracheal displacement','fibrosis','pleural thickening','infiltrate','consolidation','alveolar','atelectasis','bronchiectasis','chronic','hilar','mass','nodule','kyphosis','cavit','volume loss','ground glass','bulla')

SIDES=('left','right','bilateral')
# (문장 regex, claim finding, atom 키워드). 반대 laterality·애매한 위치 대응은 자동 처리하지 않고 수동 판정으로 넘긴다.
POS=[(r'(significant )?aortic elongation|elongated aorta|elongation of the aorta','aortic elongation',['aortic elongation']),
     (r'chronic (pulmonary )?changes( in (the )?lung parenchyma)?','chronic pulmonary change',['chronic pulmonary change','chronic inflammatory change']),
     (r'aortic calcification|calcified (aortic )?atheromatosis|aortic atheromatosis|calcified atheromatosis','aortic calcification/atheromatosis',['aortic atheromatosis','aortic calcification','calcified aortic']),
     (r'hiatal hernia','hiatal hernia',['hiatal hernia']),
     (r'tracheostomy tube','tracheostomy tube',['tracheostomy']),
     (r'nasogastric tube','nasogastric tube',['nasogastric']),
     (r'(median |mid )?sternotomy|(sutures|cerclage) of (median )?sternotomy|mid sternotomy cerclage','sternotomy',['sternotomy','sternal wiring','sutures']),
     (r'pacemaker( present)?','pacemaker',['pacemaker']),
     (r'dorsolumbar scoliosis( with right convexity)?|dorsal scoliosis|dorsolumbar scoliosis with a double curve','scoliosis',['scoliosis']),
     (r'bilateral gynecomastia|gynecomastia','gynecomastia',['gynecomastia']),
     (r'central (line|route|venous catheter) (through|via) the right (internal )?(jugular|subclavian)( vein)?','central venous catheter',['central venous catheter']),
     (r'the heart size (is|appears) (mildly )?enlarged|increased cardiothoracic index|increased cardiac silhouette|enlargement of the cardiac silhouette','cardiomegaly',['cardiomegaly','cardiomediastinal silhouette enlargement'])]
POS.append((r'prominent (vascular )?hila( of (probable )?vascular (origin|character))?|prominent hilar of vascular character|vascular hilar (prominence|enlargement)','hilar prominence',['hilar prominence','hilar enlargement','vascular congestion']))
UNK_OK={'cardiomegaly','hilar prominence','central venous catheter','aortic elongation','chronic pulmonary change','aortic calcification/atheromatosis','hiatal hernia','tracheostomy tube','nasogastric tube','sternotomy','pacemaker','scoliosis','gynecomastia'}

def positive(raw,l,finding,kws,atoms):
    hit=[a for a in has(atoms,*kws)]
    side_out={x for x in SIDES if x in l}
    if not hit:
        neg=has(atoms,*kws,positive=False)
        if neg and finding=='cardiomegaly':return (None,C(finding,'positive','contradicted',raw,[a['id'] for a in neg],'reference는 해당 소견을 명시적으로 음성으로 기술'))
        return None if finding not in UNK_OK else (None,C(finding,'positive','unknown',raw,note='reference 미언급 또는 대응 atom 없음'))
    a=hit[0];text=(a['location']+' '+a['attributes']+' '+a['finding']).lower()
    side_ref={x for x in SIDES if x in text}
    if (side_out or side_ref) and side_out!=side_ref:return None
    if finding=='scoliosis':
        for w in ('dorsolumbar','dorsal'):
            if (w in l)!=(w in text) and ('dorsal' in l or 'dorsolumbar' in l):return None
    if finding=='central venous catheter':
        ro={x for x in ('jugular','subclavian') if x in l};rr={x for x in ('jugular','subclavian') if x in text}
        if ro and rr and ro!=rr:return None
    if finding=='pacemaker' and ('single' in l or 'dual' in l) and (('single' in l and 'single' not in text) or ('dual' in l and 'dual' not in text)):return None
    if a['certainty']!='definite':return (None,C(finding,'positive','supported',raw,[a['id']],'reference는 가능 소견'))
    l=re.sub(r'\bmid\b','median',l)
    toks=[w for w in re.findall(r'[a-z]{4,}',(a['location']+' '+a['attributes']).lower())]
    ok=all(w in l for w in toks)
    if not toks or ok:m=M(a['id'],'strict','match' if a['location'] else 'na','match' if a['attributes'] else 'na',raw.rstrip('.'),a['ambiguous'])
    else:
        loc_ok=all(w in l for w in re.findall(r'[a-z]{4,}',a['location'].lower()))
        m=M(a['id'],'type_only','match' if loc_ok and a['location'] else ('missing' if a['location'] else 'na'),'missing' if a['attributes'] else 'na',raw.rstrip('.'),a['ambiguous'])
        if a['location'] and not loc_ok:m['location']='missing'
    return (m,C(finding,'positive','supported',raw,[a['id']]))

def claim_neg(sentence,finding,atoms,abnormal,contra_words,support_words=(),quote=None):
    q=quote or sentence;con=has(atoms,*contra_words,definite_only=True) if contra_words else []
    if con:return C(finding,'negative','contradicted',q,[a['id'] for a in con],'reference는 해당 소견을 확정 양성으로 기술')
    sup=has(atoms,*support_words,positive=False) if support_words else []
    nsf=[a for a in atoms if a['finding']=='no significant finding' and a['polarity']=='negative']
    if sup:return C(finding,'negative','supported',q,[a['id'] for a in sup])
    if nsf and not abnormal:return C(finding,'negative','supported',q,[a['id'] for a in nsf])
    return C(finding,'negative','unknown',q,note='reference에 대응 음성 atom 없음')

def judge(text,atoms,abnormal,partial=False):
    ms=[];cs=[];bad=[];seen=set()
    def add(c):
        k=(c['finding'],c['quote'],c['polarity'])
        if k not in seen:seen.add(k);cs.append(c)
    for raw in pieces(text):
        s=raw.rstrip('.').strip();l=s.lower()
        if any(re.fullmatch(g,l) for g in GENERIC):
            refs=generic_refs(s,atoms,abnormal);add(C('significant abnormality','negative','supported' if refs else 'unknown',raw,refs));continue
        if l=='the heart size is normal':add(claim_neg(raw,'cardiomegaly',atoms,abnormal,['cardiomegaly','cardiomediastinal silhouette enlargement'],['cardiomegaly']));continue
        if re.fullmatch(r'the mediastin(al|um)( contours| and hilar contours)?( is| are) (unremarkable|normal)',l) or l=='the mediastinal and hilar contours are normal':
            w=['mediastinal','goiter','paratracheal','tracheal displacement']+(['hilar'] if 'hilar' in l else [])
            add(claim_neg(raw,'mediastinal abnormality',atoms,abnormal,w,['mediastinal']));continue
        m=re.fullmatch(r'the lungs are clear( bilaterally)?(,? (with|without)( no evidence of| no focal| focal)? (focal )?consolidation, pleural effusion,? or pneumothorax)?',l)
        if m:
            add(claim_neg(raw,'pulmonary opacity',atoms,abnormal,['infiltrate','consolidation','alveolar','atelectasis','fibrosis','fibrotic','chronic pulmonary','chronic inflammatory','bronchiectasis','mass','ground glass','volume loss','cavit','bulla'],['infiltrate','consolidation','pulmonary']))
            if 'consolidation' in l:
                add(claim_neg(raw,'consolidation',atoms,abnormal,['infiltrate','consolidation','alveolar','atelectasis'],['consolidation','infiltrate']))
                add(claim_neg(raw,'pleural effusion',atoms,abnormal,['pleural effusion'],['pleural effusion']))
                add(claim_neg(raw,'pneumothorax',atoms,abnormal,['pneumothorax'],['pneumothorax']))
            continue
        if re.fullmatch(r'no (significant )?infiltrates or (lung|pulmonary) condensations are appreciated|no significant infiltrates or consolidations are appreciated|no infiltrates or pulmonary condensations are appreciated|no pulmonary infiltrates are appreciated',l):
            add(claim_neg(raw,'infiltrate/consolidation',atoms,abnormal,['infiltrate','consolidation','alveolar','atelectasis'],['infiltrate','consolidation']));continue
        if l=='there is no pleural effusion or pneumothorax':
            add(claim_neg(raw,'pleural effusion',atoms,abnormal,['pleural effusion'],['pleural effusion']));add(claim_neg(raw,'pneumothorax',atoms,abnormal,['pneumothorax'],['pneumothorax']));continue
        if l in ('there is no evidence of pulmonary edema',):
            add(claim_neg(raw,'pulmonary edema',atoms,abnormal,[],[]));continue
        if l in ('the visualized osseous structures are unremarkable','the visualized osseous structures are within normal limits'):
            add(claim_neg(raw,'osseous abnormality',atoms,abnormal,['scoliosis','spondylosis','fracture','kyphosis','vertebral','degenerative','osteopenia'],['bone']));continue
        if l=='normal chest x-ray':
            con=has(atoms,*MORPH,definite_only=True)
            add(C('chest abnormality','negative','contradicted',raw,[a['id'] for a in con],'reference는 확정 형태 이상 기술') if con else claim_neg(raw,'chest abnormality',atoms,abnormal,[],[]));continue
        if l=='no acute cardiopulmonary process':
            con=has(atoms,'infiltrate','consolidation','alveolar','pleural effusion','pneumothorax',definite_only=True)
            add(C('acute cardiopulmonary process','negative','contradicted',raw,[a['id'] for a in con],'reference는 급성 가능 소견을 확정 양성으로 기술') if con else claim_neg(raw,'acute cardiopulmonary process',atoms,abnormal,[],[]));continue
        if l in ('cardiomegaly','mild cardiomegaly','enlarged heart. otherwise, unremarkable chest x-ray'):
            hit=[a for a in has(atoms,'cardiomegaly','cardiomediastinal silhouette enlargement') if a['certainty']=='definite']
            if hit:
                a=hit[0]
                if a['location'] or a['attributes']:
                    bad.append(raw);continue
                ms.append(M(a['id'],'strict','na','na',raw.rstrip('.'),a['ambiguous']));add(C('cardiomegaly','positive','supported',raw,[a['id']]))
            else:
                neg=has(atoms,'cardiomegaly',positive=False)
                add(C('cardiomegaly','positive','contradicted',raw,[a['id'] for a in neg],'reference는 해당 소견을 명시적으로 음성으로 기술') if neg else C('cardiomegaly','positive','unknown',raw,note='reference 미언급'))
            continue
        if l=='there could be a small amount of fluid in the minor fissure':
            if has(atoms,'pleural effusion','fissure'):bad.append(raw)
            else:add(C('minor fissure fluid','positive','unknown',raw,note='reference 미언급',cert='possible'))
            continue
        if l=='increase in right hilar density':
            if has(atoms,'hilar','hilum','vascular congestion'):bad.append(raw)
            else:add(C('hilar density','positive','unknown',raw,note='reference 미언급'))
            continue
        if l=='i do not identify nodules in the lung parenchyma':
            if has(atoms,'nodul','granuloma','mass'):bad.append(raw)
            else:add(C('pulmonary nodule','negative','unknown',raw,note='reference에 대응 음성 atom 없음'))
            continue
        done=False
        for pattern,finding,kws in POS:
            if re.fullmatch(pattern,l):
                done=True;r=positive(raw,l,finding,kws,atoms)
                if r is None:bad.append(raw)
                else:
                    if r[0]:ms.append(r[0])
                    add(r[1])
                break
        if not done:bad.append(raw)
    if partial:return ms,cs,bad
    if bad:raise Unhandled(bad)
    return ms,cs
