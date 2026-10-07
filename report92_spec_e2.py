"""E128 수동 의미 판정 2부(행 35 이후). 규약·한계는 report92_spec_e.py 머리말과 같다."""
from report92_judge import M,C
from report92_spec_e import a,U,S,X,NU,NS,NX
SPEC={}
def put(ids,add=True,skip=(),ff=False,**kw):
    for i in ids.split():SPEC[i]=dict(kw,add=add,skip=list(skip),ff=ff)

# ---- row 35 reservoir / chronic
put('2833bd6f',m=[M(a(35,0),'strict','match','na','There is a right-sided port-a-cath.')],c=[S('reservoir device','There is a right-sided port-a-cath.',[a(35,0)],'port-a-cath은 reservoir 장치'),
    NU('pleural effusion','No pleural effusion or pneumothorax is seen.'),NU('pneumothorax','No pleural effusion or pneumothorax is seen.')])
put('5255239f',m=[M(a(35,0),'type_only','ambiguous','na','Superior cava device',True)],c=[S('device','Superior cava device',[a(35,0)],'상대정맥 장치 대 right hemithorax reservoir는 위치 모호')])
# ---- row 36
put('fb90e5ba',m=[M(a(36,0),'type_only','ambiguous','ambiguous','There is a moderate scoliosis of the thoracic spine.',True)],c=[S('scoliosis','There is a moderate scoliosis of the thoracic spine.',[a(36,0)],'thoracic 대 dorsolumbar, moderate 대 marked는 모호')],skip=['Moderate thoracic scoliosis'])
# ---- row 37
put('112a7391',c=[NU('pneumothorax','No signs of pneumothorax')])
put('b61819de',m=[M(a(37,0),'type_only','na','ambiguous','There is a pacemaker/defibrillator device with leads in the expected location in the right atrium and right ventricle.',True)],
    c=[S('pacemaker','There is a pacemaker/defibrillator device with leads in the expected location in the right atrium and right ventricle.',[a(37,0)],'defibrillator 가능성과 dual chamber 대응은 모호')],skip=['Pacemaker/defibrillator device in place'])
# ---- row 38
put('26625ea7',c=[NU('pulmonary abnormality','Pulmonary parenchyma without significant alterations')])
# ---- row 40
put('40dfdeee',c=[U('aortic elongation','Descendent aortic elongation'),U('cardiac surgery change','Changes secondary to cardiac surgery','수술 후 변화 서술; reference의 clips·sternotomy wiring과 직접 대응하지 않음')])
put('4569efc7',m=[M(a(40,2),'type_only','missing','na','There is evidence of prior sternotomy with sternal wires in place.')],c=[S('sternotomy wiring','There is evidence of prior sternotomy with sternal wires in place.',[a(40,2)],'median 위치 서술 누락')])
# ---- row 41
put('7622e30e',c=[U('supra-aortic trunk elongation','Supra-aortic trunk elongation'),NU('pulmonary abnormality','Pulmonary parenchyma without major alterations')])
# ---- row 42
put('030b6498',c=[NU('bone abnormality','There is no evidence of acute osseous abnormality.')])
# ---- row 43
put('dca2a1d3',c=[U('infiltrate','Slight retrocardiac infiltrate','retrocardiac 위치는 reference의 right suprahilar infiltrate와 다름')])
# ---- row 45
put('483f813f',c=[NU('consolidation','No parenchymal condensations.'),NU('cardiomegaly','Normal cardiothoracic index')])
# ---- row 47
put('bab64b7c',m=[M(a(47,1),'strict','na','match','There is a large hiatal hernia.')],c=[S('hiatal hernia','There is a large hiatal hernia.',[a(47,1)])],skip=['Large hiatal hernia'])
# ---- row 48
put('28670ab1',c=[U('cardiothoracic index','Cardiothoracic index at the upper limit of normal.','경계 정상 서술; reference 미언급')])
put('4d944d51',c=[U('atelectasis','Increased left basal density in relation to atelectasis'),U('consolidation','Increased left basal density in relation to consolidation'),U('pleural effusion','Pleural effusion','reference는 우측 costophrenic blunting만 기술')])
put('8d090261',c=[U('pleural effusion','There is a large opacity in the left lower lung field, likely representing a pleural effusion.',cert='possible'),
                  U('pleural effusion','There is also a small opacity in the right lower lung field, possibly representing a pleural effusion or consolidation.',cert='possible'),
                  NU('pulmonary opacity','The right lung appears relatively clear.'),NU('pneumothorax','There is no pneumothorax.')],skip=['Large left pleural effusion and small right pleural effusion'])
# ---- row 49
put('027db69f',m=[M(a(49,0),'type_only','ambiguous','ambiguous','Extensive area of adjacent consolidation in the right lower lobe',True)],
    c=[S('alveolar infiltrate','Extensive area of adjacent consolidation in the right lower lobe',[a(49,0)],'우하엽만 기술; 우상엽 포함 여부와 폐렴 해석은 모호'),U('cavitary lesion','Cavitary lesion in the right upper lobe'),
       U('chronic pulmonary change','Chronic changes in the left lung'),U('pleural thickening','Biapical pleural thickening')])
put('6015adb4',m=[M(a(49,0),'type_only','ambiguous','match','The lungs are clear except for patchy opacities in the right lower lobe.',True)],
    c=[S('alveolar infiltrate','The lungs are clear except for patchy opacities in the right lower lobe.',[a(49,0)],'우하엽 한정; reference는 우상엽·우하엽 후기저 분절'),NU('bone abnormality','The bones are intact.')],skip=['Patchy opacities in the right lower lobe, suggestive of pneu'])
put('b4f8c0c3',m=[M(a(49,0),'type_only','ambiguous','missing','Right lower lobe infiltrate.',True)],c=[S('alveolar infiltrate','Right lower lobe infiltrate.',[a(49,0)],'우하엽만 기술')])
# ---- row 50
put('8304c880',m=[M(a(50,1),'type_only','ambiguous','na','Osteosynthesis material in the left shoulder',True)],c=[S('osteosynthesis','Osteosynthesis material in the left shoulder',[a(50,1)],'left shoulder 대 left clavicle 위치 모호')])
put('e3740e49',c=[U('fixation device','There is a fixation device in the left humerus.','left humerus는 reference의 left clavicle과 다른 해부 위치')])
# ---- row 52
put('1fb78658',c=[U('pleural effusion','There is a small right pleural effusion.')],skip=['Small right pleural effusion'])
put('b998a14e',m=[M(a(52,2),'type_only','missing','na','Chronic changes in the lung parenchyma related to age.')],c=[S('chronic inflammatory change','Chronic changes in the lung parenchyma related to age.',[a(52,2)],'bilateral base 위치 누락')])
# ---- row 53
put('130645e3',m=[M(a(53,0),'type_only','ambiguous','ambiguous','Laminar atelectasis in the lingula',True)],c=[S('atelectasis','Laminar atelectasis in the lingula',[a(53,0)],'lingula는 좌측이나 bilateral basal·segmental과 일치 여부 모호')])
# ---- row 56
put('4422c839',c=[U('scoliosis','Marked dorsal scoliosis with left concavity'),NX('pulmonary abnormality','Pulmonary parenchyma without radiological alterations.',[a(56,0)]),NU('cardiomegaly','Cardiothoracic index without radiological alterations')])
put('dbfc294d',c=[U('surgical clip','There is a surgical clip in the right mediastinum.')])
# ---- row 58
put('0ed36cfc',m=[M(a(58,0),'type_only','match','ambiguous','There is a nodular opacity in the right lower lobe.',True)],c=[S('ground glass pattern/pseudonodule','There is a nodular opacity in the right lower lobe.',[a(58,0)],'ground glass 속성 누락')],skip=['Nodular opacity in the right lower lobe.'])
put('ab613299',m=[M(a(58,0),'type_only','match','ambiguous','Nodular image, probably due to superimposition, in the right base',True)],c=[S('pseudonodule','Nodular image, probably due to superimposition, in the right base',[a(58,0)],'ground glass 속성 누락; superimposition 해석')]+[NU('cardiomegaly','Normal cardiothoracic index')])
# ---- row 59
put('cb1dcaf1',m=[M(a(59,0),'type_only','match','ambiguous','There is a small nodule in the right upper lobe.',True)],c=[S('calcified granuloma','There is a small nodule in the right upper lobe.',[a(59,0)],'calcified 속성 누락')],skip=['Small nodule in the right upper lobe.'])
# ---- row 60
put('2fdc4a1f',m=[M(a(60,0),'strict','match','na','Anterior elevation of the right hemidiaphragm without apparent cause')],c=[S('hemidiaphragm elevation','Anterior elevation of the right hemidiaphragm without apparent cause',[a(60,0)]),U('atelectasis','Small laminar atelectasis in the left base')])
put('f37cabf2',m=[M(a(60,0),'type_only','missing','na','There is elevation of the right hemidiaphragm.')],
    c=[U('low lung volumes','The lung volumes are low.'),S('hemidiaphragm elevation','There is elevation of the right hemidiaphragm.',[a(60,0)],'anterior 위치 누락'),
       U('atelectasis/consolidation','There is increased opacity in the right lower lung field, which may represent atelectasis or consolidation.',cert='possible'),
       U('pleural effusion','There is a small left pleural effusion.'),NU('pneumothorax','There is no pneumothorax.')],skip=['Low lung volumes with right hemidiaphragm elevation'])
# ---- row 61
put('635ef635',c=[U('nodule','There is a small nodule in the left upper lobe.')],skip=['Small nodule in the left upper lobe.'])
put('807ffb83',m=[M(a(61,0),'type_only','ambiguous','ambiguous','Small infiltrate in the left lower lobe',True)],c=[S('infiltrate','Small infiltrate in the left lower lobe',[a(61,0)],'left middle field 대 left lower lobe 위치 모호')])
# ---- row 63
put('0d65bc51',m=[M(a(63,0),'type_only','na','ambiguous','Global cardiomegaly',True)],c=[S('cardiomegaly','Global cardiomegaly',[a(63,0)],'global 대 severe 정도 표현 모호')])
put('f64dfc94',m=[M(a(63,0),'type_only','na','missing','The heart appears enlarged.')],c=[S('cardiomegaly','The heart appears enlarged.',[a(63,0)],'severe 정도 누락')],skip=['Cardiomegaly.'])
# ---- row 64
put('4625baf8',m=[M(a(64,0),'strict','match','na','Dorsolumbar scoliosis with right convexity')],c=[C('significant abnormality','negative','unknown','Chest without significant radiological alterations.',note='같은 출력이 scoliosis를 기술하여 범위 한정 일반문으로 처리'),S('scoliosis','Dorsolumbar scoliosis with right convexity',[a(64,0)])])
# ---- row 66
put('9e9ea06b',m=[M(a(66,0),'type_only','na','na','Signs of hyperinflation',True)],c=[S('air trapping','Signs of hyperinflation',[a(66,0)],'hyperinflation을 air trapping에 대응하는 해석은 모호')])
# ---- row 67
put('59364caa',m=[M(a(67,1),'type_only','ambiguous','na','There is a linear opacity in the right mid lung, likely representing a scar.',True)],c=[S('fibrotic bands','There is a linear opacity in the right mid lung, likely representing a scar.',[a(67,1)],'right mid lung 대 right upper lobe 위치 모호')])
put('b89a3d76',c=[U('minor fissure thickening','Thickening of the minor fissure')])
# ---- row 68
put('7a160bfd',c=[U('hilar congestion','Congestive hila')])
# ---- row 69
put('0adc3ff1',m=[M(a(69,1),'strict','na','na','Signs of air trapping')],c=[S('air trapping','Signs of air trapping',[a(69,1)])])
# ---- row 70
put('37e0dfe2',m=[M(a(70,0),'strict','na','na','A tracheostomy tube is also present.'),M(a(70,2),'strict','match','na','A nasogastric tube is seen coursing into the stomach.')],
    c=[U('endotracheal tube','The patient is intubated with an endotracheal tube in place.','reference는 tracheostomy tube만 기술'),S('tracheostomy tube','A tracheostomy tube is also present.',[a(70,0)]),
       S('nasogastric tube','A nasogastric tube is seen coursing into the stomach.',[a(70,2)]),U('pulmonary edema','The lungs are diffusely hazy with increased interstitial markings, suggestive of pulmonary edema.',cert='possible'),
       U('pleural effusion','There is also evidence of bilateral pleural effusions.'),NU('cardiomegaly','The heart size appears normal.'),NU('pneumothorax','There is no pneumothorax.')],skip=['Pulmonary edema and bilateral pleural effusions'])
put('f8bd82a3',m=[M(a(70,1),'strict','match','na','Metal sutures at the cervical level')],c=[S('surgical change','Metal sutures at the cervical level',[a(70,1)]),U('alveolar infiltrate','Bilateral alveolar infiltrates'),
    U('interstitial infiltrate','Bilateral interstitial infiltrates'),NU('mediastinal abnormality','No major changes are observed at the level of the mediastinum')])
# ---- row 72
put('6d3134f4',m=[M(a(72,0),'type_only','match','missing','There is a nodule in the left upper lobe.',True)],c=[S('cavitated image','There is a nodule in the left upper lobe.',[a(72,0)],'cavitation 속성 누락; nodule과 cavitated image 대응은 모호')],skip=['Nodule in the left upper lobe.'])
put('9b2ebb82',c=[NU('pulmonary tuberculosis','No evidence of pulmonary or ganglionic tuberculous disease')])
# ---- row 73
put('3d9147a1',c=[U('scoliosis','There is a mild scoliosis of the thoracic spine.')])
# ---- row 74
put('2213a41c',m=[M(a(74,1),'type_only','missing','na','There are sternotomy wires present.')],c=[S('sternotomy sutures','There are sternotomy wires present.',[a(74,1)],'median 위치 서술 누락')])
put('66746b9c',c=[U('kyphosis','Dorsal kyphosis')])
# ---- row 76
put('d8f02303',c=[U('rib fracture callus','Callus of fracture in the seventh left rib arch')])
# ---- row 78
put('d1d68439',m=[M(a(78,0),'type_only','na','missing','There is a pacemaker in place.')],
    c=[U('pulmonary edema','There is pulmonary edema, with increased opacity in the right lower lung field.'),U('pleural effusion','There is a small right pleural effusion.','reference는 좌측 흉수 기술; 우측 흉수는 별도 주장'),
       NU('pulmonary opacity','The left lung is relatively clear.','좌측 흉수를 반박하는 문구로 보기 모호'),S('pacemaker','There is a pacemaker in place.',[a(78,0)],'ventricular position 속성 누락')],skip=['Cardiomegaly with pulmonary edema'])
put('feadfd9f',m=[M(a(78,1),'type_only','missing','na','Pleural effusion')],c=[U('central venous catheter','Central venous catheter via right jugular vein with distal end in the superior vena cava'),
    U('atelectasis','Increased retrocardiac density in relation to atelectasis'),S('pleural effusion','Pleural effusion',[a(78,1)],'left 위치 누락')])
# ---- row 80
put('a421c8e3',c=[U('cardiothoracic index','Cardiothoracic index at the upper limit of normal','경계 정상 서술; reference 미언급')])
# ---- row 81
put('217a67a6',m=[M(a(81,2),'strict','match','na','There are sternotomy wires present.')],c=[S('sternal wiring','There are sternotomy wires present.',[a(81,2)])])
put('e4ebccb9',c=[U('nodular image','Left basal nodular image')])
# ---- row 83
put('00388bb9',c=[NU('bone abnormality','There is no evidence of acute bony abnormality.')])
put('556e7e40',c=[U('infiltrate','Infiltrates in the lingula and left lower lobe')])
# ---- row 84
MASS=lambda q:dict(m=[M(a(84,0),'type_only','na','ambiguous',q,True)],c=[S('pulmonary mass',q,[a(84,0)],'known 속성은 단일 영상 서술로 확인 불가')])
put('3553dd34',m=[M(a(84,0),'type_only','na','ambiguous','Cavitary mass in the right upper lobe',True)],c=[U('consolidation','Pneumonic consolidation in the right upper lobe'),
    S('pulmonary mass','Cavitary mass in the right upper lobe',[a(84,0)],'known 속성은 단일 영상 서술로 확인 불가'),U('pleural effusion','Right pleural effusion')])
put('803d8fd4 bbb1db16',**MASS('Right upper lobe mass.'))
put('90e39554',m=[M(a(84,0),'type_only','na','ambiguous','The right lung shows significant opacification, particularly in the right upper lobe, with a possible mass or consolidation.',True)],
    c=[S('pulmonary mass','The right lung shows significant opacification, particularly in the right upper lobe, with a possible mass or consolidation.',[a(84,0)],'possible 표현·consolidation 대안 병기로 대응 모호'),
       NU('pulmonary opacity','The left lung is relatively clear.'),NU('pleural effusion','There is no evidence of pleural effusion.')],skip=['Right upper lobe consolidation or mass','Further evaluation is recommended'])
# ---- row 86
put('09a9bd36',c=[U('hemidiaphragm elevation','Anterior elevation of the right hemidiaphragm'),NU('pulmonary abnormality','Pulmonary parenchyma without significant findings')])
put('ece5bec0',m=[M(a(86,0),'type_only','missing','na','The lung volumes are low.',True)],
    c=[S('hypoventilation','The lung volumes are low.',[a(86,0)],'low lung volumes를 bibasal hypoventilation에 대응하는 해석은 모호'),U('hemidiaphragm elevation','There is elevation of the right hemidiaphragm.'),
       NX('bone abnormality','The visualized bony structures are unremarkable.',[a(86,1),a(86,2)])],skip=['IMPRESSION: Low lung volumes with elevation'])
# ---- row 87
SCO=lambda q:dict(m=[M(a(87,0),'type_only','ambiguous','na',q,True)],c=[S('scoliosis',q,[a(87,0)],'dorsolumbar 대 dorsal 위치 범위 모호')])
put('403b7873 9ea0ee46',**SCO('Dorsolumbar scoliosis with a double curve.'))
put('8fc213f0',m=[M(a(87,0),'strict','match','na','There is a moderate dextroscoliosis of the thoracic spine.')],c=[S('scoliosis','There is a moderate dextroscoliosis of the thoracic spine.',[a(87,0)])],skip=['Moderate dextroscoliosis','Otherwise, unremarkable chest X-ray'])
put('a05f5cbc',m=[M(a(87,0),'type_only','ambiguous','na','Dorsolumbar scoliosis',True)],c=[NU('metastatic lung disease','No signs of metastatic lung disease.'),S('scoliosis','Dorsolumbar scoliosis',[a(87,0)],'dorsolumbar 대 dorsal 위치 범위 모호')])
# ---- row 88
put('6b152fa1',add=False,c=[NU('pulmonary/mediastinal abnormality','No significant alterations are observed in the pulmonary parenchyma or mediastinum.','reference의 우주기관지 이물과 직접 대응하지 않음'),
    NU('cardiomediastinal abnormality','The cardiomediastinal silhouette is within normal limits.')])
put('b8347d67',m=[M(a(88,0),'type_only','ambiguous','missing','There is a metallic foreign body in the right lung.',True)],c=[S('metallic foreign body','There is a metallic foreign body in the right lung.',[a(88,0)],'right lung 대 right main bronchus, dental bridge 속성 누락')],skip=['Metallic foreign body in the right lung.'])
# ---- row 89
put('7e51e581',m=[M(a(89,1),'type_only','na','missing','There is a nodular opacity in the right upper lobe.',True)],c=[S('nodules','There is a nodular opacity in the right upper lobe.',[a(89,1)],'small high-density·calcified granuloma 속성 누락')],skip=['Nodular opacity in the right upper lobe.'])
# ---- row 91
put('b98738f5',m=[M(a(91,0),'strict','na','na','There is a large hiatal hernia.')],c=[S('hiatal hernia','There is a large hiatal hernia.',[a(91,0)])],skip=['Large hiatal hernia'])
# ---- row 92
put('66875dcc',m=[M(a(92,1),'strict','match','na','Bilateral pleural effusion without significant changes compared to the study performed yesterday')],
    c=[S('pleural effusion','Bilateral pleural effusion without significant changes compared to the study performed yesterday',[a(92,1)]),
       X('endotracheal tube position','Endotracheal tube at 3 cm from the carina',[a(92,0)],'reference는 carina에서 1.7 cm')])
put('ec6f7d0a',m=[M(a(92,0),'type_only','na','conflict','The patient is intubated with the endotracheal tube tip terminating approximately 4 cm above the carina.')],
    c=[X('endotracheal tube position','The patient is intubated with the endotracheal tube tip terminating approximately 4 cm above the carina.',[a(92,0)],'reference는 carina에서 1.7 cm'),
       NU('cardiomegaly','The heart size is normal, and the mediastinal contours are unremarkable.'),NU('mediastinal abnormality','The heart size is normal, and the mediastinal contours are unremarkable.'),
       NU('bone abnormality','The visualized osseous structures are intact.')],skip=['Intubated with endotracheal tube tip in satisfactory position'])
# ---- row 95
put('661fe78b',c=[U('pleural thickening','Biapical pleural thickening'),U('pleuroparenchymal tracts','Pleuroparenchymal tracts in the left upper lobe')])
# ---- normal rows
put('ac20245f',c=[NS('pulmonary abnormality','Pulmonary parenchyma without significant findings.',[a(97,1)])])
put('37cc1660',c=[NS('pulmonary abnormality','Pulmonary parenchyma without significant alterations',[a(98,0)])])
put('d6ec87b5',c=[NS('cardiomegaly','Cardiothoracic ratio at the upper limit of normal',[a(103,0)],'정상 상한 서술')])
put('646ea3f8',c=[U('pleural effusion','Radiological improvement with a decrease in volume of bilateral pleural effusion','정상 reference에서 부수 양성 주장; 자동 모순 처리하지 않음'),NS('pneumothorax','No signs of pneumothorax are appreciated',[a(107,0)])])
put('1e66b101',c=[U('surgical clips','There are surgical clips in the right axilla.')])
put('fe9f31fc',c=[U('post-surgical change','Changes secondary to left breast surgery')])
put('657650f0',c=[X('pleural thickening','Biapical pleuroparenchymal thickening',[a(121,2)],'reference는 폐 실질 이상 없음을 명시'),U('bone island','Bone island in the right humeral head','양성 정상 변이; reference의 골 이상 없음과 자동 충돌로 보지 않음')])
put('ca89b5a1',c=[NS('cardiomediastinal abnormality','Mediastinum and cardiac silhouette within normal limits.',[a(124,0)]),NS('pulmonary nodule/consolidation','No nodules or areas of consolidation in the lung parenchyma.',[a(124,2)]),
    NS('pleural effusion','Costophrenic angles are clear.',[a(124,1)])])
put('2a3042ff',c=[NS('cardiomegaly','Cardiothoracic ratio at the upper limit of normal',[a(127,0)],'정상 상한 서술'),NS('pulmonary nodule/consolidation','No nodules or areas of consolidation in the lung parenchyma.',[a(127,0)]),
    NS('pleural effusion','Free costophrenic sinuses.',[a(127,0)]),NS('pulmonary nodule/infiltrate','No nodules or lung infiltrates',[a(127,0)])])
