"""iter_097 epoch6 비교 batch(신규 R LR2e-5 / base / R LR1e-4 / R LR2e-4)의 assistant 판정.
blinded.json은 조건명을 제거한 상태이며 판정 중 private_mapping은 열지 않았다. 전문의 검토가 아니다.

규칙(사전 고정, iter_090 protocol 계승 + 이번 보완):
- 일반 정상문(No significant findings 등): reference에 비모호 전반 정상 원자가 있으면 supported, 없으면 unknown. 자동 모순 처리 안 함.
- 구체적 부정문(예: no pleural effusion, lungs are clear)이 비모호 확정 양성 reference와 정면 충돌하면 contradicted.
  reference 원자가 모호(ambiguous)이거나 가능(possible)이면 contradicted 대신 unknown + 'POSSIBLE_CONTRA' 표시(보수 경계에서만 반박으로 셈).
- 전반 정상 reference에 구체적 이상 소견을 추가한 출력: 미지원(unknown) + POSSIBLE_CONTRA. reference에 없는 추가 소견(비정상 reference)은 plain unknown.
- 'No other relevant findings' 류는 자동 모순 처리하지 않는다.
- strict: 소견 + reference가 명시한 위치·속성 모두 대응. 위치/속성 누락·충돌은 type_only."""
import json
import re
from report86_common import save,sha
from report97_train import OUT,ORIGINAL

PC='POSSIBLE_CONTRA: '
GENERIC=('No significant findings.','Within normal limits.','No relevant findings.','No significant radiological findings.','Chest without significant alterations.')

def m(ref,q,status,loc,att,amb=False):return dict(ref=ref,quote=q,status=status,location=loc,attributes=att,ambiguous=amb)
def c(finding,q,status,refs,pol='positive',cert='definite',note=''):return dict(finding=finding,polarity=pol,certainty=cert,status=status,quote=q,refs=refs,note=note)
def J(matches,claims,note=''):return dict(matches=matches,claims=claims,note=note)

def nsf_atoms(ref):return [a['id'] for a in ref['atoms'] if a['finding']=='no significant finding' and a['polarity']=='negative' and not a['ambiguous']]

def generic(ref,text):
    atoms=nsf_atoms(ref)
    return J([],[c('significant abnormality',text,'supported' if atoms else 'unknown',atoms[:1],'negative',note='일반 정상문'+('; reference 전반 정상 원자 있음' if atoms else '; 자동 모순·승인 안 함'))])

PATTERNS=dict(
    overall=[r'Normal chest X-ray\.',r'No acute cardiopulmonary process\.'],
    heart_normal=[r'The heart size is normal\.'],
    lungs_clear=[r'The lungs are clear without focal consolidation, pleural effusion, or pneumothorax\.',r'The lungs are clear with no focal consolidation, pleural effusion, or pneumothorax\.',r'The lungs are clear\.'],
    effusion=[r'There is no pleural effusion or pneumothorax\.'],
    osseous=[r'The visualized osseous structures are unremarkable\.',r'The visualized osseous structures are intact\.',r'The bones are intact\.',r'There is no evidence of acute bony abnormality\.'],
    mediastinum=[r'The mediastinal and hilar contours are (?:normal|unremarkable)\.',r'The mediastinal contours are (?:normal|unremarkable)\.',r'The mediastinum is unremarkable\.'])
FINDING=dict(overall='significant abnormality',heart_normal='cardiomegaly',lungs_clear='pulmonary opacity/consolidation',effusion='pleural effusion/pneumothorax',osseous='osseous abnormality',mediastinum='mediastinal abnormality')

# 정상형 base 서술(FINDINGS/IMPRESSION)의 이미지별 비기본 판정. 기본은 unknown.
BASE_TABLE={
 0:dict(heart_normal=('unknown',['V00A00'],PC+'reference는 가능(possible) apparent cardiomegaly')),
 1:dict(effusion=('contradicted',['V01A00'],'reference: small left posterior costophrenic angle effusion')),
 9:dict(heart_normal=('supported',['V09A02'],''),lungs_clear=('supported',['V09A00','V09A01'],'')),
 13:dict(lungs_clear=('supported',['V13A00','V13A01'],'')),
 14:dict(osseous=('contradicted',['V14A01'],'osseous unremarkable vs dorsolumbar scoliosis')),
 15:dict(osseous=('contradicted',['V15A02'],'osseous intact vs degenerative bone changes'),lungs_clear=('contradicted',['V15A01'],'lungs clear vs chronic pleuroparenchymal changes')),
 17:dict(lungs_clear=('unknown',['V17A01'],PC+'reference nodular images 모호')),
 19:dict(effusion=('supported',['V19A03'],''),mediastinum=('contradicted',['V19A01'],'mediastinum unremarkable vs slight mediastinal widening')),
 24:dict(mediastinum=('contradicted',['V24A00'],'mediastinal contours unremarkable vs elongated aorta')),
 25:dict(lungs_clear=('contradicted',['V25A00'],'lungs clear vs segmental LLL atelectasis')),
 27:dict(lungs_clear=('contradicted',['V27A02'],'lungs clear vs fibrotic tracts')),
}

def base_normal(idx,ref,text):
    claims=[];table=BASE_TABLE.get(idx,{});atoms=nsf_atoms(ref)
    for cat,pats in PATTERNS.items():
        for p in pats:
            hit=re.search(p,text)
            if hit:
                if cat=='overall':status,refs,note=('supported',atoms[:1],'일반 정상 impression') if atoms else ('unknown',[],'일반 정상 impression; 자동 모순·승인 안 함')
                else:status,refs,note=table.get(cat,('unknown',[],''))
                claims.append(c(FINDING[cat],hit.group(0),status,refs,'negative',note=note));break
    return J([],claims)

# 이미지 index -> [(text 시작, 판정)]. 비정상(비일반) 출력 전부를 출력별로 직접 판정했다.
S={
 1:[('Signs of air trapping.',J([],[c('air trapping','Signs of air trapping.','unknown',[],note='reference는 pleural effusion만; 미지원')]))],
 2:[('No significant findings. Small hiatal hernia.',J([],[c('significant abnormality','No significant findings.','supported',['V02A00'],'negative'),
      c('hiatal hernia','Small hiatal hernia.','unknown',[],note=PC+'전반 정상 reference에 이상 소견 추가'),
      c('aortic elongation','Aortic elongation.','unknown',[],note=PC+'전반 정상 reference에 이상 소견 추가'),
      c('other findings','No other relevant findings.','unknown',[],'negative')]))],
 3:[('Aortic elongation. No other',J([],[c('aortic elongation','Aortic elongation.','unknown',[],note=PC+'전반 정상 reference에 이상 소견 추가'),
      c('other findings','No other significant radiological findings.','unknown',[],'negative')]))],
 7:[('No significant findings. Mammary',J([],[c('significant abnormality','No significant findings.','supported',['V07A00'],'negative'),
      c('mammary prostheses','Mammary prostheses.','unknown',[],note=PC+'전반 정상 reference에 이상 소견 추가')]))],
 8:[('Nodular image, probably',J([],[c('nodular image','Nodular image, probably due to superimposition, in the right upper lobe.','unknown',[],cert='possible',note=PC+'전반 정상 reference에 가능 소견 추가'),
      c('benign image','Image of probable benign etiology in the left axillary border of the heart.','unknown',[],cert='possible',note=PC+'전반 정상 reference에 가능 소견 추가')])),
    ('FINDINGS:\nThe lungs are clear. The heart size is normal. The mediastinal and hilar contours are unremarkable. There is no pleural effusion or pneumothorax. There are calcified granulomas',
      J([],[c('lungs clear','The lungs are clear.','unknown',[],'negative'),
      c('calcified granulomas','There are calcified granulomas in the right upper lobe.','unknown',[],note=PC+'전반 정상 reference에 이상 소견 추가; 반복 loop(비EOS)')],'비EOS 반복')),
    ('Calcified granulomas in the right apex.',J([],[c('calcified granulomas','Calcified granulomas in the right apex.','unknown',[],note=PC+'전반 정상 reference에 이상 소견 추가; 반복 loop(비EOS)')],'비EOS 반복'))],
 11:[('No significant findings. Aortic elongation.',J([],[c('significant abnormality','No significant findings.','supported',['V11A00'],'negative'),
      c('aortic elongation','Aortic elongation.','unknown',[],note=PC+'전반 정상 reference에 이상 소견 추가')]))],
 13:[('Central route through the right jugular. No relevant findings.',J([m('V13A02','Central route through the right jugular.','type_only','missing','na')],
      [c('central venous catheter','Central route through the right jugular.','supported',['V13A02']),c('other findings','No relevant findings.','unknown',[],'negative')],'tip 위치 누락')),
    ('Central route through the right jugular to the superior vena cava. No other significant radiological',J([m('V13A02','Central route through the right jugular to the superior vena cava.','type_only','conflict','na',True)],
      [c('central venous catheter','Central route through the right jugular to the superior vena cava.','supported',['V13A02']),
       c('catheter tip in SVC','to the superior vena cava','unknown',['V13A02'],note=PC+'reference tip은 right atrium 시작부; SVC/cavoatrial 경계 모호'),
       c('other findings','No other significant radiological findings.','unknown',[],'negative')],'tip SVC vs RA 시작부')),
    ('Central route through the right jugular to the superior vena cava. No other significant findings.',J([m('V13A02','Central route through the right jugular to the superior vena cava.','type_only','conflict','na',True)],
      [c('central venous catheter','Central route through the right jugular to the superior vena cava.','supported',['V13A02']),
       c('catheter tip in SVC','to the superior vena cava','unknown',['V13A02'],note=PC+'reference tip은 right atrium 시작부; SVC/cavoatrial 경계 모호'),
       c('other findings','No other significant findings.','unknown',[],'negative')],'tip SVC vs RA 시작부')),
    ('FINDINGS:\n\nThe heart size is normal.',J([m('V13A02','A right internal jugular central venous catheter is present.','type_only','missing','na')],
      [c('central venous catheter','A right internal jugular central venous catheter is present.','supported',['V13A02']),
       c('lungs clear','The lungs are clear without focal consolidation, pleural effusion, or pneumothorax.','supported',['V13A00','V13A01'],'negative'),
       c('significant abnormality','No acute cardiopulmonary process.','unknown',[],'negative')],'tip 누락'))],
 14:[('Mild biconvex scoliosis.',J([m('V14A01','Mild biconvex scoliosis.','type_only','missing','conflict')],
      [c('scoliosis','Mild biconvex scoliosis.','supported',['V14A01']),c('scoliosis curvature','biconvex','unknown',['V14A01'],note='reference는 right convexity; biconvex는 다른 곡선 기술'),
       c('other findings','No other relevant findings.','supported',['V14A02'],'negative',note='reference도 No other relevant findings(모호)')],'dorsolumbar 위치 누락; convexity 표현 불일치'))],
 15:[('Right basal infiltrate.',J([],[c('basal infiltrate','Right basal infiltrate.','unknown',[],note='reference에 없음; 미지원')]))],
 16:[('Pulmonary parenchyma with image of alveolar consolidation in the right lung.',J([m('V16A00','Pulmonary parenchyma with image of alveolar consolidation in the right lung.','type_only','missing','match',True)],
      [c('alveolar consolidation','Pulmonary parenchyma with image of alveolar consolidation in the right lung.','supported',['V16A00'])],'perihilar 위치 누락; reference 모호')),
    ('FINDINGS:\n\nThe heart size appears enlarged.',J([m('V16A00','There is increased opacity in the right lung field, suggestive of pulmonary edema or consolidation.','possible_only','missing','ambiguous',True)],
      [c('right lung opacity','There is increased opacity in the right lung field','supported',['V16A00'],cert='possible'),
       c('cardiomegaly','The heart size appears enlarged.','unknown',[]),
       c('pulmonary edema','pulmonary edema or consolidation','unknown',[],cert='possible')],'hedge된 대응')),
    ('Cardiomegaly. Pulmonary edema.',J([],[c('cardiomegaly','Cardiomegaly.','unknown',[]),c('pulmonary edema','Pulmonary edema.','unknown',[])])),
    ('Cardiomegaly. Blunting',J([],[c('cardiomegaly','Cardiomegaly.','unknown',[]),c('costophrenic blunting','Blunting of the right costophrenic angle.','unknown',[]),
      c('infiltrate','No clear images of infiltrates or condensations are appreciated.','unknown',['V16A00'],'negative',note=PC+'reference 확정 infiltrates이나 원자가 모호')]))],
 18:[],
 20:[('Central route through the right jugular to the superior vena cava. Nasogastric tube with',J([m('V20A01','Central route through the right jugular to the superior vena cava.','type_only','conflict','na')],
      [c('central venous catheter','Central route through the right jugular to the superior vena cava.','supported',['V20A01']),
       c('jugular catheter route','Central route through the right jugular','contradicted',['V20A01'],note='reference는 subclavian 경로'),
       c('nasogastric tube','Nasogastric tube with the distal end in the stomach.','unknown',[],note='reference 언급 없음')])),
    ('Central route through the right jugular to the superior vena cava. Infradiaphragmatic',J([m('V20A01','Central route through the right jugular to the superior vena cava.','type_only','conflict','na')],
      [c('central venous catheter','Central route through the right jugular to the superior vena cava.','supported',['V20A01']),
       c('jugular catheter route','Central route through the right jugular','contradicted',['V20A01'],note='reference는 subclavian 경로'),
       c('nasogastric tube','Infradiaphragmatic nasogastric tube.','unknown',[],note='reference 언급 없음')])),
    ('Central route through the right jugular to the superior vena cava. Probable bilateral',J([m('V20A01','Central route through the right jugular to the superior vena cava.','type_only','conflict','na')],
      [c('central venous catheter','Central route through the right jugular to the superior vena cava.','supported',['V20A01']),
       c('jugular catheter route','Central route through the right jugular','contradicted',['V20A01'],note='reference는 subclavian 경로'),
       c('pleural effusion','Probable bilateral pleural effusion.','unknown',[],cert='possible',note='reference 언급 없음')])),
    ('FINDINGS:\n\nThe heart size appears mildly enlarged.',J([m('V20A02','The heart size appears mildly enlarged.','strict','na','na'),
      m('V20A01','A right internal jugular central venous catheter is seen terminating in the superior vena cava.','type_only','conflict','na'),
      m('V20A03','There is mild right lower lung atelectasis.','type_only','conflict','na')],
      [c('cardiomegaly','The heart size appears mildly enlarged.','supported',['V20A02']),
       c('central venous catheter','A right internal jugular central venous catheter is seen terminating in the superior vena cava.','supported',['V20A01']),
       c('jugular catheter route','A right internal jugular central venous catheter','contradicted',['V20A01'],note='reference는 subclavian 경로'),
       c('nasogastric tube','A nasogastric tube is seen coursing into the stomach.','unknown',[],note='reference 언급 없음'),
       c('right lower lung atelectasis','There is mild right lower lung atelectasis.','unknown',['V20A03'],note='reference는 possible retrocardiac atelectasis; 위치 상이')],'V20A00 hilar congestion 누락'))],
 21:[('Cardiomegaly. Dual chamber pacemaker. Aortic',J([m('V21A00','Dual chamber pacemaker.','strict','na','match')],
      [c('pacemaker','Dual chamber pacemaker.','supported',['V21A00']),c('cardiomegaly','Cardiomegaly.','unknown',[]),c('aortic elongation','Aortic elongation.','unknown',[]),
       c('aortic atheromatosis','Calcified aortic atheromatosis.','unknown',[]),c('spondylosis','Signs of spondylosis in the spine.','unknown',[]),
       c('other findings','No other relevant findings.','unknown',[],'negative')])),
    ('Chronic pulmonary changes. Cardiomegaly. Dual chamber pacemaker.',J([m('V21A00','Dual chamber pacemaker.','strict','na','match')],
      [c('pacemaker','Dual chamber pacemaker.','supported',['V21A00']),c('chronic pulmonary change','Chronic pulmonary changes.','unknown',[]),c('cardiomegaly','Cardiomegaly.','unknown',[])])),
    ('Pacemaker. No significant radiological findings.',J([m('V21A00','Pacemaker.','type_only','na','missing')],
      [c('pacemaker','Pacemaker.','supported',['V21A00']),c('significant abnormality','No significant radiological findings.','unknown',[],'negative')],'dual chamber 속성 누락')),
    ('FINDINGS:\n\nThe lungs are clear. The heart size is normal. There is no pleural effusion or pneumothorax. The patient has a pacemaker.',J([m('V21A00','The patient has a pacemaker.','type_only','na','missing')],
      [c('pacemaker','The patient has a pacemaker.','supported',['V21A00']),c('lungs clear','The lungs are clear.','unknown',[],'negative'),c('cardiomegaly','The heart size is normal.','unknown',[],'negative'),
       c('significant abnormality','No acute cardiopulmonary process.','unknown',[],'negative')],'dual chamber 속성 누락'))],
 22:[('Large hiatal hernia.',J([m('V22A00','Large hiatal hernia.','strict','na','na')],[c('hiatal hernia','Large hiatal hernia.','supported',['V22A00']),c('hernia size','Large','unknown',['V22A00'],note='reference에 크기 없음')])),
    ('Hiatal hernia.',J([m('V22A00','Hiatal hernia.','strict','na','na')],[c('hiatal hernia','Hiatal hernia.','supported',['V22A00'])])),
    ('Vascular hilar enlargement',J([m('V22A00','Hiatal hernia.','strict','na','na')],[c('hiatal hernia','Hiatal hernia.','supported',['V22A00']),
      c('hilar vascular enlargement','Vascular hilar enlargement of probable vascular origin.','unknown',[],cert='possible'),c('other findings','No other relevant findings.','unknown',[],'negative')])),
    ('FINDINGS:\nThe heart size is normal.',J([m('V22A00','There is a large hiatal hernia.','strict','na','na')],
      [c('hiatal hernia','There is a large hiatal hernia.','supported',['V22A00']),c('lungs clear','The lungs are clear without focal consolidation, pleural effusion, or pneumothorax.','unknown',[],'negative')]))],
 23:[("Pacemaker. No alterations in the chest",J([m('V23A00','Pacemaker.','strict','na','na')],[c('pacemaker','Pacemaker.','supported',['V23A00']),c('significant abnormality',"No alterations in the chest for the patient's age.",'unknown',[],'negative')])),
    ('Pacemaker. Cardiomegaly.',J([m('V23A00','Pacemaker.','strict','na','na')],[c('pacemaker','Pacemaker.','supported',['V23A00']),c('cardiomegaly','Cardiomegaly.','unknown',[]),c('aortic elongation','Aortic elongation.','unknown',[])])),
    ('Chronic changes in lung parenchyma. Cardiomegaly. Dual chamber',J([m('V23A00','Dual chamber pacemaker.','strict','na','na')],
      [c('pacemaker','Dual chamber pacemaker.','supported',['V23A00']),c('pacemaker type','Dual chamber','unknown',['V23A00'],note='reference에 type 없음'),c('cardiomegaly','Cardiomegaly.','unknown',[]),
       c('aortic valve prosthesis','Aortic valve prosthesis.','unknown',[]),c('congestive heart failure','Signs of congestive heart failure.','unknown',[])])),
    ('FINDINGS:\n\nThe heart size is mildly enlarged.',J([m('V23A00','There is a pacemaker/defibrillator device with leads in the expected location.','strict','na','na')],
      [c('pacemaker','There is a pacemaker/defibrillator device with leads in the expected location.','supported',['V23A00']),
       c('pneumothorax','There is no pleural effusion or pneumothorax.','supported',['V23A03'],'negative'),
       c('cardiomegaly','The heart size is mildly enlarged.','unknown',[]),c('vascular congestion','There is mild pulmonary vascular congestion.','unknown',[])]))],
 24:[('Chronic pulmonary changes. Aortic elongation. Scoliosis.',J([m('V24A00','Aortic elongation.','strict','na','na')],
      [c('aortic elongation','Aortic elongation.','supported',['V24A00']),c('chronic pulmonary change','Chronic pulmonary changes.','unknown',[]),c('scoliosis','Scoliosis.','unknown',[])])),
    ('No significant findings. Small right infrahilar',J([],[c('significant abnormality','No significant findings.','unknown',[],'negative'),
      c('infiltrate','Small right infrahilar interstitial infiltrate.','unknown',[]),c('scoliosis','Slight dorsal scoliosis.','unknown',[])]))],
 25:[('Chronic pulmonary changes.',J([],[c('chronic pulmonary change','Chronic pulmonary changes.','unknown',[],note='reference는 segmental LLL atelectasis')])),
    ('Chronic changes in lung parenchyma. No other',J([],[c('chronic pulmonary change','Chronic changes in lung parenchyma.','unknown',[],note='reference는 segmental LLL atelectasis'),c('other findings','No other relevant findings.','unknown',[],'negative')]))],
 27:[('Chronic pulmonary changes.',J([m('V27A01','Chronic pulmonary changes.','strict','match','match',True)],[c('chronic pulmonary change','Chronic pulmonary changes.','supported',['V27A01'])],'reference 모호')),
    ('Chronic changes in lung parenchyma.',J([m('V27A01','Chronic changes in lung parenchyma.','strict','match','match',True)],[c('chronic pulmonary change','Chronic changes in lung parenchyma.','supported',['V27A01'])],'reference 모호'))],
 28:[('No significant findings. Left humeral head prosthesis.',J([m('V28A00','Left humeral head prosthesis.','type_only','conflict','na')],
      [c('significant abnormality','No significant findings.','unknown',[],'negative'),c('humeral prosthesis laterality','Left humeral head prosthesis.','contradicted',['V28A00'],note='reference는 right humerus')])),
    ('FINDINGS:\n\nThe lungs are clear.',J([m('V28A00','There is a right shoulder prosthesis.','strict','match','match',True)],
      [c('shoulder prosthesis','There is a right shoulder prosthesis.','supported',['V28A00'],note='shoulder vs humerus 표현 차이'),c('lungs clear','The lungs are clear.','unknown',[],'negative')],'위치 표현 모호')),
    ('Osteosynthesis material, right shoulder.',J([m('V28A00','Osteosynthesis material, right shoulder.','type_only','match','ambiguous',True)],
      [c('osteosynthesis material','Osteosynthesis material, right shoulder.','unknown',['V28A00'],note='prosthesis가 아닌 fixation hardware 표현; 대응 모호'),
       c('spondylosis','Signs of spondylosis in the spine.','unknown',[]),c('other findings','No other relevant findings.','unknown',[],'negative')],'소견 종류 모호')),
    ('Right shoulder prosthesis. No other relevant findings.',J([m('V28A00','Right shoulder prosthesis.','strict','match','match',True)],
      [c('shoulder prosthesis','Right shoulder prosthesis.','supported',['V28A00'],note='shoulder vs humerus 표현 차이'),c('other findings','No other relevant findings.','unknown',[],'negative')],'위치 표현 모호'))],
 29:[('Chronic pulmonary changes.',J([],[c('chronic pulmonary change','Chronic pulmonary changes.','unknown',[],note='reference에 없음')])),
    ('No signs of pleural detachment',J([],[c('pleural detachment','No signs of pleural detachment are seen in the left hemithorax.','unknown',[],'negative'),c('rib callus','Bone calluses from fractures in the 5th and 6th left rib arches are visible.','unknown',[])])),
    ('FINDINGS:\nThe heart size is normal.',J([m('V29A00','There is a nodular opacity in the right lower lobe.','type_only','missing','missing')],
      [c('pulmonary nodule','There is a nodular opacity in the right lower lobe.','supported',['V29A00']),c('lungs clear','The lungs are clear without focal consolidation, pleural effusion, or pneumothorax.','unknown',[],'negative')],'크기·peripheral posterior 누락')),
    ('No definitive images of pulmonary parenchyma nodules',J([],[c('pulmonary nodule','No definitive images of pulmonary parenchyma nodules or masses are observed.','contradicted',['V29A00','V29A01'],'negative',note='reference는 확정 nodules')]))],
 30:[('Tracheostomy tube. No other relevant findings.',J([m('V30A00','Tracheostomy tube.','strict','na','na')],[c('tracheostomy tube','Tracheostomy tube.','supported',['V30A00']),c('other findings','No other relevant findings.','unknown',[],'negative')],'NG tube 누락')),
    ('Tracheostomy tube.',J([m('V30A00','Tracheostomy tube.','strict','na','na')],[c('tracheostomy tube','Tracheostomy tube.','supported',['V30A00'])],'NG tube 누락')),
    ('FINDINGS:\n\nThe patient is intubated',J([m('V30A00','A tracheostomy tube is also present.','strict','na','na'),m('V30A01','A nasogastric tube is visualized.','strict','na','na')],
      [c('tracheostomy tube','A tracheostomy tube is also present.','supported',['V30A00']),c('nasogastric tube','A nasogastric tube is visualized.','supported',['V30A01']),
       c('endotracheal tube','The patient is intubated with an endotracheal tube in place.','unknown',[],note='reference에 없음; trach과 동시 기술'),
       c('lungs clear','The lungs are clear bilaterally.','supported',['V30A02'],'negative')]))],
 31:[('Chronic pulmonary changes.',J([],[c('chronic pulmonary change','Chronic pulmonary changes.','unknown',[],note='reference는 bilateral apical pleural thickening')])),
    ('Prominent aortic button.',J([],[c('aortic prominence','Prominent aortic button.','unknown',[]),c('costophrenic blunting','Blunting of the left costophrenic angle.','unknown',[])]))],
}

def judge(idx,ref,text):
    if text in GENERIC:return generic(ref,text)
    for key,j in S.get(idx,[]):
        if text.startswith(key):return j
    if text.startswith('FINDINGS:'):return base_normal(idx,ref,text)
    raise KeyError((idx,text[:60]))

def main(name='epoch6'):
    root=OUT/f'semantic/{name}';blinded=json.loads((root/'blinded.json').read_text())
    refs=json.loads((ORIGINAL/'semantic/V32_reference_v3.json').read_text())['rows'];ix={r['id']:i for i,r in enumerate(refs)}
    judgments=[]
    for rec in blinded['records']:
        i=ix[rec['image_id']];j=judge(i,refs[i],rec['text'])
        judgments.append(dict(blind_id=rec['blind_id'],matches=j['matches'],claims=j['claims'],internal_conflicts=[],format_failure=False,note=j['note']))
    assert len({j['blind_id'] for j in judgments})==len(blinded['records'])==128
    import report90_semantic_eval as E
    byref={r['id']:r for r in refs};byj={j['blind_id']:j for j in judgments}
    for rec in blinded['records']:E.score(byref[rec['image_id']],rec,byj[rec['blind_id']])  # 저장 전 anchor·규칙 검증
    for k in range(0,32,4):
        ids={refs[x]['id'] for x in range(k,k+4)};blind={r['blind_id'] for r in blinded['records'] if r['image_id'] in ids}
        save(root/f'judgments/part_{k//4:02}.json',dict(blinded_sha=sha(root/'blinded.json'),judgments=[j for j in judgments if j['blind_id'] in blind],
            helper_sha=sha(__file__),scope='assistant 판정(전문의 아님); 규칙은 파일 상단 docstring; 비정상 출력은 출력별 수작업, 일반 정상문·정상형 base 서술은 규칙 표'))
    print(len(judgments))

if __name__=='__main__':main()
