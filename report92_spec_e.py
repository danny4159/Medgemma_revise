"""E128 가림 판독 중 규칙표가 처리하지 못한 출력의 수동 의미 판정(assistant). 모델명 mapping은 열람하지 않았다.
단, 출력 문체가 조건을 드러낼 수 있어(예: 좌표 포함·FINDINGS 형식) 문체 수준의 완전한 눈가림은 아니다.
규약은 epoch2 annotation_notes와 동일: 일반 정상문은 부수 만성 변화를 자동 반박하지 않고, 반복 주장은 하나로 통합한다."""
from report92_judge import M,C

def a(row,k):return f'E{row:03}A{k:02}'
def U(finding,quote,note='reference가 지지·반박하지 않는 소견',cert='definite'):
    return C(finding,'positive','unknown',quote,note=note,cert=cert)
def S(finding,quote,refs,note=''):
    return C(finding,'positive','supported',quote,refs,note)
def X(finding,quote,refs,note):
    return C(finding,'positive','contradicted',quote,refs,note)
def NU(finding,quote,note='reference에 대응 음성 atom 없음'):
    return C(finding,'negative','unknown',quote,note=note)
def NS(finding,quote,refs,note=''):
    return C(finding,'negative','supported',quote,refs,note)
def NX(finding,quote,refs,note=''):
    return C(finding,'negative','contradicted',quote,refs,note or 'reference는 해당 소견을 확정 양성으로 기술')
SPEC={}
def put(ids,add=True,skip=(),ff=False,**kw):
    for i in ids.split():SPEC[i]=dict(kw,add=add,skip=list(skip),ff=ff)

# ---- row 1: pacemaker/chronic/goiter
put('9693875f',m=[M(a(1,0),'type_only','missing','na','Single-chamber pacemaker')],c=[S('pacemaker','Single-chamber pacemaker',[a(1,0)],'single-chamber 상세는 reference에 없음; 위치 누락'),U('pulmonary vascularization','Increased pulmonary vascularization in the central fields')])
put('a72bec15',m=[M(a(1,0),'type_only','match','na','There is a pacemaker visible in the left pectoral region.')],c=[U('cardiomegaly','The heart size is mildly enlarged.'),S('pacemaker','There is a pacemaker visible in the left pectoral region.',[a(1,0)])],skip=['Pacemaker present'])
put('b2fe7d40',c=[U('cardiothoracic index','Cardiothoracic index at the upper limit of normal.','경계 정상 서술; reference 미언급')])
# ---- row 3
put('b2450ed9',c=[U('hilar prominence','Prominent vascular hila'),NU('pulmonary infiltrate','No pulmonary infiltrates are appreciated')])
# ---- row 4 hilar congestion
put('75f36d63',m=[M(a(4,0),'strict','match','na','Increase in the cardiomedastinal silhouette, with congestive hila')],
    c=[U('cardiomediastinal silhouette enlargement','Increase in the cardiomedastinal silhouette, with congestive hila'),S('vascular congestion','Increase in the cardiomedastinal silhouette, with congestive hila',[a(4,0)]),
       U('congestive heart failure','Increase in the cardiomedastinal silhouette, suggestive of congestive heart failure',cert='possible'),NU('pleural effusion','Free costophrenic sinuses.'),
       U('bronchovascular markings','Slight increase in bronchovascular markings in the left lower lobe, suggestive of an infectious inflammatory process')])
# ---- row 6
put('f8b10c5f',c=[U('lung opacity','There is a patchy opacity in the right upper lobe.'),U('lung opacity','There is a patchy opacity in the left lower lobe.'),
                  NX('pulmonary opacity','The lungs are otherwise clear.',[a(6,0),a(6,1)],'reference는 기관지확장증과 만성 폐 변화 양성')],
    skip=['Patchy opacities in the right upper lobe and left lower lobe','Further evaluation is recommended'])
# ---- row 7
PORT=[M(a(7,4),'type_only','ambiguous','na','Right-sided port-a-cath.',True)]
put('a1809645',m=PORT,c=[S('device','Right-sided port-a-cath.',[a(7,4)],'port-a-cath 대 reference의 right axillary edge device는 모호')])
put('bc206d1b',m=[M(a(7,0),'type_only','na','ambiguous','Small left pleural effusion',True)],c=[S('pleural effusion','Small left pleural effusion',[a(7,0)],'small left 대 minimal 속성 모호')])
put('c32a857a',m=[M(a(7,0),'type_only','na','ambiguous','There is a small left pleural effusion.',True),M(a(7,4),'type_only','ambiguous','na','There is a right-sided port-a-cath.',True)],
    c=[S('pleural effusion','There is a small left pleural effusion.',[a(7,0)],'small left 대 minimal 속성 모호'),S('device','There is a right-sided port-a-cath.',[a(7,4)],'port-a-cath 대 axillary device는 모호'),NU('pneumothorax','There is no pneumothorax.')],
    skip=['Small left pleural effusion.'])
put('fa9bfb23',c=[U('pulmonary mass','Right upper lobe mass.')])
# ---- row 8
put('25d5f855',c=[U('hiatal hernia','There is a large hiatal hernia.','Chilaiditi 변이와 다른 소견; reference 미언급')],skip=['Large hiatal hernia'])
put('f1a7e81f',c=[U('hilar enlargement','Vascular hilar enlargement'),U('hemidiaphragm elevation','Right hemidiaphragm elevation')])
# ---- row 9 cardiomegaly
put('aabcffd8',m=[M(a(9,3),'strict','na','na','The heart size appears enlarged.')],c=[S('cardiomegaly','The heart size appears enlarged.',[a(9,3)]),
    NX('chest abnormality','Otherwise, unremarkable chest X-ray.',[a(9,2),a(9,4)],'reference는 scoliosis와 좌측 hemidiaphragm 거상을 확정 양성으로 기술')],skip=['Enlarged heart'])
put('d4db9f03',add=False,ff=True,m=[M(a(9,3),'strict','na','na','Cardiomegaly')],
    c=[NU('pulmonary nodule','I do not identify nodules in the lung parenchyma'),U('minor fissure fluid','There could be a small amount of fluid in the minor fissure','reference 미언급',cert='possible'),
       S('cardiomegaly','Cardiomegaly',[a(9,3)]),U('hilar density','Increase in right hilar density')])
# ---- row 10
put('a5ae465b',c=[NS('infiltrate/consolidation','No infiltrates or lung condensations are appreciated.',[a(10,1)])])
# ---- row 12
put('714155b8',m=[M(a(12,1),'strict','match','match','Left basal laminar atelectasis')],c=[U('left cardiac chamber enlargement','Growth of left cavities'),S('atelectasis','Left basal laminar atelectasis',[a(12,1)])])
# ---- row 13
put('52718f3a',c=[U('hilar prominence','Prominent hila')])
put('d75ead30',m=[M(a(13,1),'strict','na','na','The heart size is mildly enlarged.')],c=[S('cardiomegaly','The heart size is mildly enlarged.',[a(13,1)])])
# ---- row 15
put('8e574b96',c=[U('alveolar opacity','Slight alveolar space occupation at the right lung base'),U('costophrenic angle blunting','Slight blunting of the left costophrenic angle')])
# ---- row 16
put('46ee8555',c=[C('other abnormality','negative','supported','The rest is within normal limits',[a(16,2)],'나머지(폐 실질 포함) 정상 서술')])
put('6fe475ca',m=[M(a(16,0),'type_only','missing','na','There are sternotomy wires present.')],c=[S('sternotomy','There are sternotomy wires present.',[a(16,0)],'wires 서술; median 위치 누락')])
# ---- row 17
put('3cb982da',c=[NU('consolidation','At the moment, no consolidations or suspicious lesions are appreciated'),NU('suspicious lesion','At the moment, no consolidations or suspicious lesions are appreciated')])
# ---- row 18
put('a4b12645',c=[NS('cardiomegaly','Cardiothoracic index at the high limit of normal',[a(18,0)],'정상 상한 서술'),NU('pulmonary abnormality','Pulmonary parenchyma without relevant findings')])
# ---- row 19
CVC19=lambda q:dict(m=[M(a(19,0),'type_only','missing','na',q)],c=[S('central venous catheter',q,[a(19,0)],'경로는 일치; superior vena cava 팁 위치 누락')])
put('4ca07546',**CVC19('Central line through the right jugular vein.'))
put('ddb48fe5',**CVC19('Central line through the right internal jugular vein.'))
put('8399544f',m=[M(a(19,0),'type_only','ambiguous','na','There is a right-sided central venous catheter with the tip in the superior vena cava.')],
    c=[U('cardiomegaly','The heart size appears mildly enlarged.'),S('central venous catheter','There is a right-sided central venous catheter with the tip in the superior vena cava.',[a(19,0)],'right-sided와 SVC 팁 일치; jugular 경로 미기술'),
       U('port-a-cath','There is a right-sided port-a-cath with the tip in the superior vena cava.'),U('chest tube','There is a right-sided chest tube.'),U('chest tube','There is a left-sided chest tube.'),
       U('pleural effusion','There is a right-sided pleural effusion.'),U('pleural effusion','There is a left-sided pleural effusion.'),U('pulmonary edema','There is mild pulmonary edema.'),NU('pneumothorax','There is no pneumothorax.')],
    skip=['Bilateral pleural effusions','Mild pulmonary edema','Right-sided central venous catheter, right-sided port-a-cath'])
put('df5b9e45',m=[M(a(19,0),'type_only','missing','na','Central route through the right jugular')],
    c=[S('central venous catheter','Central route through the right jugular',[a(19,0)],'SVC 팁 위치 누락'),U('cardiac silhouette enlargement','Increased cardiac silhouette'),
       U('pleural effusion','Probable bilateral pleural effusion','reference 미언급',cert='possible'),U('pulmonary vascularization','Increased pulmonary vascularization')])
# ---- row 20
put('09e7b944',c=[U('hyperinflation/emphysema','The lungs are hyperinflated with flattened diaphragms, suggesting emphysema.'),U('pleural effusion','There is a right pleural effusion.'),
                  U('pleural effusion','There is a left pleural effusion.'),U('lung opacity','There is a right upper lobe opacity.'),NU('pneumothorax','There is no pneumothorax.')],
    skip=['Emphysema with bilateral pleural effusions'])
put('88f8cc4a',m=[M(a(20,0),'type_only','match','missing','Biapical pleuroparenchymal thickening'),M(a(20,1),'strict','match','na','Blunting of the costophrenic angles')],
    c=[S('pleural thickening','Biapical pleuroparenchymal thickening',[a(20,0)],'marked 속성 누락'),S('costophrenic angle blunting','Blunting of the costophrenic angles',[a(20,1)]),
       U('cardiac silhouette enlargement','Enlargement of the cardiac silhouette'),NS('pulmonary opacity','I do not visualize opacities in the right lower lobe',[a(20,2)],'opacities를 infiltrate에 대응; 우하엽으로 한정')])
# ---- row 21
put('a5da4c35',m=[M(a(21,0),'strict','match','na','Small calcified granuloma in the left lower lobe')],c=[S('calcified granuloma','Small calcified granuloma in the left lower lobe',[a(21,0)])])
# ---- row 22
put('15a060c2',m=[M(a(22,0),'type_only','na','missing','Cardiomegaly')],c=[S('cardiomegaly','Cardiomegaly',[a(22,0)],'global 속성 누락')])
put('e859f039',m=[M(a(22,0),'type_only','na','missing','The heart size is enlarged.')],c=[S('cardiomegaly','The heart size is enlarged.',[a(22,0)],'global 속성 누락'),NU('bone abnormality','There is no evidence of acute bony abnormality.')],skip=['Cardiomegaly'])
# ---- row 23
put('fe6c85e8',c=[U('interstitial pattern','Bilateral interstitial pattern'),U('pleural thickening','New bilateral apical pleural thickening')])
# ---- row 24
put('4b3f7188',m=[M(a(24,1),'strict','match','na','Central route through the right jugular to the superior vena cava'),M(a(24,0),'type_only','na','conflict','Endotracheal tube at 3.3 cm from the carina')],
    c=[NU('pulmonary infiltrate','No infiltrates or lung condensations are appreciated.'),S('central venous catheter','Central route through the right jugular to the superior vena cava',[a(24,1)]),
       S('endotracheal tube','Endotracheal tube at 3.3 cm from the carina',[a(24,0)],'거리 3.3 대 3.1 cm 수치 차이')])
CVC24=lambda q:dict(m=[M(a(24,1),'type_only','missing','na',q)],c=[S('central venous catheter',q,[a(24,1)],'right jugular 경로 일치; SVC 팁 위치 누락')])
put('6fc6283c 8019c883',**CVC24('Central line through the right internal jugular vein.'))
put('aad1dcd1',m=[M(a(24,1),'strict','match','na','There is a right internal jugular central venous catheter with the tip in the superior vena cava.')],
    c=[S('central venous catheter','There is a right internal jugular central venous catheter with the tip in the superior vena cava.',[a(24,1)]),U('nasogastric tube','There is a nasogastric tube with the tip in the stomach.'),
       U('lung opacity','There is a right lower lobe opacity.'),NU('pulmonary opacity','The left lung is clear.')],skip=['The patient is rotated','Right lower lobe opacity'])
# ---- row 26
put('f2213c16',m=[M(a(26,0),'strict','na','na','There is a tracheostomy tube in place.')],
    c=[S('tracheostomy tube','There is a tracheostomy tube in place.',[a(26,0)]),U('pleural effusion','There is a moderate right pleural effusion with associated atelectasis.'),
       U('pleural effusion','There is a small left pleural effusion with associated atelectasis.'),U('pulmonary edema','There is mild pulmonary edema.'),NU('pneumothorax','There is no pneumothorax.')],
    skip=['The patient is rotated','Moderate right pleural effusion','Small left pleural effusion','Mild pulmonary edema','Tracheostomy tube in place'])
# ---- row 28
put('f13a27e9',c=[U('diaphragmatic lobulation','Diaphragmatic lobulation')])
# ---- row 29
put('2863de20',c=[U('interstitial-alveolar infiltrate','Diffuse bilateral interstitial-alveolar infiltrate'),U('pleural effusion','Pleural effusion'),
                  U('cardiomegaly obscured','Cardiomegaly is not visualized due to the bilateral pleural effusion','심비대 판단 불가 서술'),U('hilar congestion','Congestive hila')])
put('359a28bf',m=[M(a(29,0),'strict','na','match','The patient is intubated with the endotracheal tube tip terminating approximately 4 cm above the carina.'),
                  M(a(29,1),'type_only','missing','na','A right internal jugular central venous catheter is present.')],
    c=[S('endotracheal tube','The patient is intubated with the endotracheal tube tip terminating approximately 4 cm above the carina.',[a(29,0)]),
       S('central venous catheter','A right internal jugular central venous catheter is present.',[a(29,1)],'right jugular 일치; SVC 근처 말단 위치 누락'),
       U('pulmonary edema','There is mild to moderate pulmonary edema with bilateral diffuse opacities, more prominent in the lower lung zones.'),
       U('pleural effusion','There is a small left pleural effusion.'),NU('pneumothorax','No pneumothorax is identified.')],
    skip=['Mild to moderate pulmonary edema with bilateral diffuse','Small left pleural effusion.','Endotracheal tube in appropriate','Right internal jugular central venous catheter in appropriat'])
CVC29=lambda q:dict(m=[M(a(29,1),'type_only','missing','na',q)],c=[S('central venous catheter',q,[a(29,1)],'right jugular 일치; SVC 근처 말단 위치 누락')])
put('9b545b54 bf799433',**CVC29('Central line through the right internal jugular vein.'))
# ---- row 30
put('6040f500',c=[U('cardiomegaly','The heart size is mildly enlarged.')])
put('60ed32d5',c=[U('cardiomegaly','Increased cardiothoracic index')])
# ---- row 31
put('605a78a3',c=[U('pleural effusion','Left pleural effusion')])
put('e8bb9cf1',c=[U('lung opacity','The lungs are clear except for a focal opacity in the left upper lobe.')],skip=['Focal opacity in the left upper lobe'])
# ---- row 32
put('894bd7cc',m=[M(a(32,0),'strict','match','na','Significant radiological improvement of the alveolar infiltrate in the left upper lobe',True)],
    c=[S('infiltrate','Significant radiological improvement of the alveolar infiltrate in the left upper lobe',[a(32,0)],'비교 검사 전제의 호전 서술; 현재 존재 여부 모호')])
