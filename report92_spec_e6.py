"""iter_092 epoch6 V32(4 조건×32) 가림 판독의 assistant 의미 판정. 모델명 미열람, 규약은 epoch2 annotation_notes를 따른다."""
from report92_judge import M,C,G

AORTA=lambda q:C('aortic elongation','positive','unknown',q,note='정상 변이 가능성 및 reference 상세 부재')
def U(finding,quote,note='reference가 지지·반박하지 않는 부수 소견'):
    return C(finding,'positive','unknown',quote,note=note)
def S(finding,quote,refs,note=''):
    return C(finding,'positive','supported',quote,refs,note)
def X(finding,quote,refs,note):
    return C(finding,'positive','contradicted',quote,refs,note)
NS='No significant findings.'
SPEC={}
def put(ids,**kw):
    for i in ids.split():SPEC[i]=kw

# ref0 possible cardiomegaly(definite 양성 없음)
put('4ca98f02 5839651d a096fabc c451530f',c=[G(NS)])
# ref1 pleural effusion
put('4d6e4bf6 61f06ba7 8c0f2f4c a769a1c4',c=[U('air trapping','Signs of air trapping.')])
# ref2 normal
put('0fec9abd',c=[G(NS,['V02A00'])])
put('82b78788',c=[G(NS,['V02A00']),U('hiatal hernia','Small hiatal hernia.'),AORTA('Aortic elongation.'),G('No other relevant findings.',['V02A00'])])
put('b8df47f3',c=[G('No relevant findings.',['V02A00'])])
put('ff828cc8',c=[G(NS,['V02A00']),AORTA('Aortic elongation.')])
# ref3 normal
put('0ccaabeb 7eca3417',c=[G(NS,['V03A00'])])
put('4a12cffe',c=[G(NS,['V03A00']),AORTA('Aortic elongation.'),G('No other relevant findings.',['V03A00'])])
put('66af265c',c=[AORTA('Aortic elongation.'),G('No other significant radiological findings.',['V03A00'])])
# ref4 normal
put('1ed135ba 680643db 9a35b47b cc5a0b97',c=[G(NS,['V04A00'])])
# ref5 normal
put('2fa47963 63682b27 920a9d09 b00f124b',c=[G(NS,['V05A01'])])
# ref6 normal
put('3aea3095 4be0324a 879ca1b6 8dfb549c',c=[G(NS,['V06A00'])])
# ref7 normal
put('0f935094',c=[G('No relevant findings.',['V07A00'])])
put('1332c179 f455e98d',c=[G(NS,['V07A00'])])
put('378213e4',c=[G(NS,['V07A00']),U('mammary prostheses','Mammary prostheses.')])
# ref8 normal
put('11238a85',c=[C('nodular image','positive','unknown','Nodular image, probably due to superimposition, in the right upper lobe.',note='probable superimposition으로 한정된 가능 소견; reference 미언급을 음성으로 바꾸지 않음',cert='possible'),
                  C('benign-appearing image','positive','unknown','Image of probable benign etiology in the left axillary border of the heart.',note='가능 양성 병변 서술; reference 미언급',cert='possible')])
put('4d041a8d',c=[G(NS,['V08A00'])])
put('d7118008',c=[C('pulmonary nodule/opacity','negative','supported','I do not identify nodules or significant pulmonary opacities.',['V08A00']),
                  U('calcified granuloma','Some small calcified granulomas in the left upper lobe.','정상/유의 소견 없음 reference만으로 부수적 만성 소견을 명시 반박하지 않음'),
                  C('active infection','negative','supported','I do not appreciate signs of active infection.',['V08A00'])])
put('faae7750',c=[U('bone callus','Bone callus from an old fracture in the right humeral head.','오래된 부수 골 변화'),
                  U('fibrous tracts','Some fibrous tracts of the right axillary canal.'),
                  U('rib fracture callus','Fracture callus in the 6th left rib.','오래된 부수 골 변화')])
# ref9 normal (구체 음성 atom만 있음)
put('15c76ed6',c=[G('No relevant findings.')])
put('43c3cfd4 b251c581 ff9a315b',c=[G(NS)])
# ref10 normal
put('23ee179d 5334d65b 926b7496 bd120b3a',c=[G(NS,['V10A00'])])
# ref11 normal
put('10d9027a',c=[G(NS,['V11A00'])])
put('3ed5dca6',c=[G(NS,['V11A00']),AORTA('Aortic elongation.'),G('No relevant findings.',['V11A00'])])
put('647014b3',c=[G(NS,['V11A00']),AORTA('Aortic elongation.'),G('No other relevant findings.',['V11A00'])])
put('b55dfcc1',c=[G('Within normal limits.',['V11A00'])])
# ref12 normal
put('0e414c2f 401946ae',c=[G('No significant radiological findings.',['V12A00'])])
put('11d5ea86 e25458bd',c=[G(NS,['V12A00'])])
# ref13 right jugular CVC
JUG='Central route through the right jugular to the superior vena cava.'
for i,tail in [('0f79d0cc','No other significant findings.'),('33a1b580','No other significant radiological findings.'),('96f9ee15','No other significant findings.'),('b2c9b3b6','No other significant radiological findings.')]:
    put(i,m=[M('V13A02','type_only','ambiguous','na',JUG)],c=[S('central venous catheter',JUG,['V13A02'],'경로(right jugular) 일치; 팁 SVC 대 right atrium 시작부는 위치 모호'),G(tail)])
# ref14 scoliosis
put('331f8d10',c=[G('Chest without significant alterations.',['V14A02'])])
put('9c03d20f bc0fab28',m=[M('V14A01','type_only','missing','ambiguous','Mild biconvex scoliosis.')],
    c=[S('scoliosis','Mild biconvex scoliosis.',['V14A01'],'biconvex 대 right convexity 속성 모호'),G('No other relevant findings.',['V14A02'])])
put('a096d55b',m=[M('V14A01','type_only','ambiguous','missing','Dorsal scoliosis.')],c=[G(NS,['V14A02']),S('scoliosis','Dorsal scoliosis.',['V14A01'],'dorsal 대 dorsolumbar 부분 일치')])
# ref15 air trapping 등
put('0d25d145 45a8f3e5 7ab1aed8 c7cab19a',c=[U('infiltrate','Right basal infiltrate.')])
# ref16 perihilar alveolar/interstitial infiltrates
put('9308840e',m=[M('V16A00','type_only','ambiguous','ambiguous','Pulmonary parenchyma with image of alveolar consolidation in the right lung.',True)],
    c=[S('alveolar infiltrate','Pulmonary parenchyma with image of alveolar consolidation in the right lung.',['V16A00'],'perihilar·interstitial 여부 모호')])
put('94c332bd',c=[U('cardiomegaly','Cardiomegaly.'),U('costophrenic angle blunting','Blunting of the right costophrenic angle.')])
put('99486236',m=[M('V16A00','type_only','ambiguous','match','Pulmonary parenchyma with diffuse bilateral infiltrative-alveolar pattern.',True)],
    c=[U('cardiothoracic index','Cardiothoracic index at the limit of pathological significance.'),U('costophrenic angle blunting','Blunting of the right costophrenic angle.'),
       S('alveolar interstitial infiltrate','Pulmonary parenchyma with diffuse bilateral infiltrative-alveolar pattern.',['V16A00'],'bilateral diffuse 대 right predominant 위치 모호')])
put('9b0640d9',c=[U('cardiomegaly','Cardiomegaly.'),U('costophrenic angle blunting','Blunting of the right costophrenic angle.'),
                  C('infiltrate/consolidation','negative','contradicted','No clear images of infiltrates or condensations are appreciated.',['V16A00'],'reference는 perihilar alveolar/interstitial infiltrate 양성')])
# ref17 nipple shadow / nodular
put('0deacd99 0f35f49a db162296',c=[G(NS)])
put('4476e458',c=[G('Within normal limits.')])
# ref18 gynecomastia 등
put('8b2d5ccf c8430b96 d30f7d43',c=[G('No relevant findings.')])
put('8f940ca6',c=[G(NS)])
# ref19 aortic knob
put('1302dd12 6b239214 eccf8955',c=[G(NS)])
put('8c41ada2',m=[M('V19A00','type_only','missing','missing','Aortic elongation.',True)],
    c=[G(NS),S('aortic prominence','Aortic elongation.',['V19A00'],'elongation 대 prominent aortic button 용어 모호'),U('scoliosis','Dorsal scoliosis.'),U('hemidiaphragm elevation','Elevation of the right hemidiaphragm.')])
# ref20 hilar congestion / subclavian CVC / cardiomegaly
JUG2='Central route through the right jugular to the superior vena cava.'
CVC=lambda:X('jugular catheter route',JUG2,['V20A01'],'reference는 subclavian 경로')
put('97a1efd3',m=[M('V20A01','type_only','conflict','na',JUG2),M('V20A02','strict','na','na','Cardiomegaly.'),M('V20A00','type_only','missing','na','Vascular congestion.')],
    c=[CVC(),U('nasogastric tube','Nasogastric tube below the diaphragm.'),S('cardiomegaly','Cardiomegaly.',['V20A02']),S('vascular congestion','Vascular congestion.',['V20A00'],'hilar 위치 누락')])
put('9f705d90',m=[M('V20A01','type_only','conflict','na',JUG2)],c=[CVC(),U('nasogastric tube','Infradiaphragmatic nasogastric tube.')])
put('a03ceb89',m=[M('V20A01','type_only','conflict','na',JUG2)],c=[CVC(),C('pleural effusion','positive','unknown','Probable bilateral pleural effusion.',note='reference 미언급',cert='possible')])
put('df6abeb8',m=[M('V20A01','type_only','conflict','na',JUG2),M('V20A02','strict','na','na','Cardiomegaly.')],
    c=[CVC(),S('cardiomegaly','Cardiomegaly.',['V20A02']),AORTA('Aortic elongation.'),C('pulmonary infiltrate','negative','unknown','No pulmonary infiltrates are appreciated.',note='reference에 해당 음성 atom 없음')])
# ref21 dual chamber pacemaker
put('00912ce8',c=[U('hilar enlargement','Bilateral hilar enlargement of probable vascular origin.'),U('cardiomegaly','Cardiomegaly at the expense of the left ventricle.'),AORTA('Aortic elongation.'),
                  C('pulmonary infiltrate','negative','unknown','No pulmonary infiltrates are appreciated.',note='reference에 해당 음성 atom 없음')])
put('6ba6a0bc',m=[M('V21A00','strict','na','match','Dual chamber pacemaker.')],c=[U('chronic pulmonary change','Chronic pulmonary changes.'),U('cardiomegaly','Cardiomegaly.'),S('pacemaker','Dual chamber pacemaker.',['V21A00'])])
put('9ae881b2',m=[M('V21A00','strict','na','match','Dual chamber pacemaker.')],
    c=[U('cardiomegaly','Cardiomegaly.'),S('pacemaker','Dual chamber pacemaker.',['V21A00']),AORTA('Aortic elongation.'),U('aortic atheromatosis','Calcified aortic atheromatosis.'),U('spondylosis','Signs of spondylosis in the spine.'),G('No other relevant findings.')])
put('effc02d3',m=[M('V21A00','type_only','na','conflict','Biventricular pacemaker.')],c=[X('pacemaker type','Biventricular pacemaker.',['V21A00'],'reference는 bicameral(dual chamber); biventricular는 속성 불일치'),G(NS)])
# ref22 hiatal hernia
put('09fc7fc7',m=[M('V22A00','strict','na','na','Hiatal hernia.')],c=[S('hiatal hernia','Hiatal hernia.',['V22A00'])])
put('197ebb85',m=[M('V22A00','strict','na','na','A large hiatus hernia containing a part of the gastric bubble.')],
    c=[U('cardiomegaly','Cardiomegaly.'),AORTA('Aortic elongation.'),S('hiatal hernia','A large hiatus hernia containing a part of the gastric bubble.',['V22A00'],'large 등 추가 서술은 reference 상세 부재')])
put('ddf29242',m=[M('V22A00','strict','na','na','Hiatal hernia.')],c=[U('hilar enlargement','Vascular hilar enlargement of probable vascular origin.'),S('hiatal hernia','Hiatal hernia.',['V22A00']),G('No other relevant findings.')])
put('e4d8bc75',m=[M('V22A00','strict','na','na','Hiatal hernia.')],c=[U('scoliosis','Dorsolumbar scoliosis with a double curve.'),U('midline displacement','Displacement of the midline structures.'),S('hiatal hernia','Hiatal hernia.',['V22A00']),G('No other relevant findings.')])
# ref23 pacemaker, infiltrate/consolidation/pneumothorax 음성
PAL="No alterations in the chest for the patient's age."
for i in ('8186a648','ec6d395e'):
    put(i,m=[M('V23A00','strict','na','na','Pacemaker.')],c=[S('pacemaker','Pacemaker.',['V23A00']),C('chest abnormality','negative','unknown',PAL,note='reference에 일반 정상 atom 없음')])
put('d91dd942',m=[M('V23A00','strict','na','na','Dual chamber pacemaker.')],
    c=[U('chronic pulmonary change','Chronic changes in lung parenchyma.'),U('cardiomegaly','Cardiomegaly.'),S('pacemaker','Dual chamber pacemaker.',['V23A00']),U('supra-aortic atheromatosis','Supra-aortic atheromatosis.'),
       U('aortic valve prosthesis','Aortic valve prosthesis.'),U('congestive heart failure','Signs of congestive heart failure.')])
put('fec0b9d2',m=[M('V23A00','strict','na','na','Dual chamber pacemaker.')],
    c=[U('cardiomegaly','Cardiomegaly at the expense of the left cavities.'),U('mediastinal narrowing','Narrowing of the superior mediastinum.'),S('pacemaker','Dual chamber pacemaker.',['V23A00']),U('aortic atheromatosis','Aortic atheromatosis.'),
       C('pulmonary infiltrate','negative','supported','No pulmonary infiltrates are appreciated.',['V23A01'])])
# ref24 aortic elongation
put('475b6f3b',c=[U('scoliosis','Dorsolumbar scoliosis with a double curve.'),U('costophrenic angle blunting','Blunting of the left costophrenic angle.'),U('diaphragm flattening','Flattening of the gas diaphragms.'),G('No other relevant findings.')])
put('9363cc09',c=[G(NS)])
put('e01e178f',c=[G(NS),U('interstitial infiltrate','Small right infrahilar interstitial infiltrate.'),U('scoliosis','Slight dorsal scoliosis.')])
put('ec067396',c=[G('No significant radiological findings.')])
# ref25 LLL atelectasis
put('012f8bbf',c=[U('chronic pulmonary change','Chronic pulmonary changes at the bases.'),U('hilar prominence','Prominent hila of probable vascular origin.')])
put('424d4584 bbadbbae f114c0f5',c=[U('chronic pulmonary change','Chronic changes in lung parenchyma.'),G('No other relevant findings.')])
# ref26 neck catheter + chest without alterations
put('aba559d9',c=[G('Within normal limits.',['V26A01'])])
put('c0b9168d',c=[G('No findings.',['V26A01'])])
put('da91ff0d f250650c',c=[G(NS,['V26A01'])])
# ref27
put('24567c66 bd0bd7a3',c=[G('No significant radiological findings.',note='reference는 만성 변화·섬유화 양성; 일반 문구는 자동 반박하지 않음')])
put('8fab09a8',m=[M('V27A01','strict','match','match','Chronic changes in lung parenchyma.',True)],c=[S('chronic pulmonary change','Chronic changes in lung parenchyma.',['V27A01'])])
put('be01f820',m=[M('V27A01','strict','match','match','Chronic changes in lung parenchyma.',True)],c=[S('chronic pulmonary change','Chronic changes in lung parenchyma.',['V27A01']),C('other relevant finding','negative','supported','No other relevant findings.',['V27A03'],'reference 음성 atom은 모호')])
# ref28 right humeral prosthesis / scoliosis
put('217b5494',m=[M('V28A00','type_only','match','ambiguous','Screw in the right humerus.',True)],
    c=[G(NS),U('osteosynthesis','Osteosynthesis in the left shoulder.','좌측 견관절 고정물; reference는 우측 상완 보철'),S('metallic device','Screw in the right humerus.',['V28A00'],'screw 대 prosthesis 장치 유형 모호')])
put('d0efd9fd',m=[M('V28A00','type_only','conflict','missing','Left humeral head prosthesis.')],c=[G(NS),X('humeral prosthesis laterality','Left humeral head prosthesis.',['V28A00'],'reference는 우측 상완')])
put('e836933d',m=[M('V28A00','type_only','match','missing','Right shoulder prosthesis (partially visualized).')],c=[S('shoulder prosthesis','Right shoulder prosthesis (partially visualized).',['V28A00'],'metallic 속성 누락'),U('kyphosis','Dorsal kyphosis.'),G('No other relevant findings.')])
put('fec6273d',m=[M('V28A00','type_only','match','ambiguous','Osteosynthesis material, right shoulder.',True)],c=[S('metallic device','Osteosynthesis material, right shoulder.',['V28A00'],'osteosynthesis 대 prosthesis 장치 유형 모호'),U('spondylosis','Signs of spondylosis in the spine.'),G('No other relevant findings.')])
# ref29 nodules
put('0a075030',c=[C('pleural detachment','negative','unknown','No signs of pleural detachment are seen in the left hemithorax.',note='reference 음성 atom은 costophrenic angles 흉수'),U('rib fracture callus','Bone calluses from fractures in the 5th and 6th left rib arches are visible.')])
put('19d18019',c=[C('pulmonary tuberculosis','negative','unknown','No signs of pulmonary tuberculosis are appreciated.',note='reference 미언급')])
put('e2722e07',c=[G('No relevant findings.')])
put('ee4e2502',c=[C('pulmonary nodule/mass','negative','contradicted','No definitive images of pulmonary parenchyma nodules or masses are observed.',['V29A00','V29A01'],'reference는 2cm와 9mm 폐결절 양성')])
# ref30 tracheostomy / NG tube
put('031c8ff8',m=[M('V30A00','strict','na','na','Tracheostomy tube.')],c=[S('tracheostomy tube','Tracheostomy tube.',['V30A00'])])
put('1a0a6a73',m=[M('V30A00','strict','na','na','Tracheostomy tube.')],c=[S('tracheostomy tube','Tracheostomy tube.',['V30A00']),G('No other relevant findings.',note='reference는 NG tube 양성; 일반 문구는 자동 반박하지 않음')])
put('3600a9e2',m=[M('V30A00','strict','na','na','Tracheostomy tube.')],c=[S('tracheostomy tube','Tracheostomy tube.',['V30A00']),U('surgical staples','Cervical surgical staples.'),U('hilar prominence','With prominent hila.')])
put('a3a3d0bf',m=[M('V30A00','strict','na','na','Tracheostomy tube.')],c=[S('tracheostomy tube','Tracheostomy tube.',['V30A00']),U('surgical staples','Cervical surgical staples.'),U('PICC line','Right picc line through the right subclavian vein.'),
    C('pulmonary infiltrate/consolidation','negative','supported','No infiltrates or lung condensations are appreciated.',['V30A02'])])
# ref31 apical pleural thickening
put('35f3c57a',c=[U('aortic prominence','Prominent aortic button.'),U('costophrenic angle blunting','Blunting of the left costophrenic angle.')])
put('623067de',c=[U('hilar prominence','Prominent vascular hila.'),U('chronic pulmonary change','Chronic pulmonary changes.')])
put('7e3ba041',c=[G(NS)])
put('e32fccb1',c=[U('chronic pulmonary change','Chronic pulmonary changes.')])
