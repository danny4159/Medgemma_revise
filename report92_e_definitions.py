"""E128 reference 원자 정의. E 모델 출력 생성 전에 manifest 원문만 읽고 직접 검토해 작성했다(reviewed=true).
형식: report90_e_reference가 요구하는 [문장 index(들), finding, polarity, certainty, location, attributes, ambiguous]."""
import json
from report86_common import save,sha
from report90_numeric import OUT as ORIGINAL
OUT=ORIGINAL/'recovery'

def P(i,finding,loc='',attr='',cert='definite',amb=False):return [i,finding,'positive',cert,loc,attr,amb]
def N(i,finding,loc='',attr='',amb=False):return [i,finding,'negative','definite',loc,attr,amb]
def OTH(i):return N(i,'other relevant finding','outside described findings','',True)
def NSF(i,attr=''):return N(i,'no significant finding','',attr)
POSS='possible'

ROWS={
0:[P(0,'infiltrate','right lower','subtle; infectious-inflammatory origin to assess',amb=True),P(1,'aortic elongation')],
1:[P(0,'pacemaker','upper left hemithorax'),P(1,'chronic pulmonary change'),N(2,'pneumothorax'),P(3,'intrathoracic goiter')],
2:[N(0,'pulmonary finding','lung'),P(1,'aortic elongation')],
3:[P(0,'aortic elongation')],
4:[P(0,'vascular congestion','hilar')],
5:[P(0,'calcified aortic atheromatosis'),P(1,'aortic elongation'),OTH(2)],
6:[P(0,'bronchiectasis','right suprahilar'),P(1,'chronic pulmonary change'),P(2,'aortic atheromatosis'),P(3,'aortic elongation'),P(4,'scoliosis','dorsal','right convexity'),P(5,'rib fracture callus','left fifth rib arch')],
7:[P(0,'pleural effusion','','minimal'),P(1,'costophrenic angle blunting','left','residual'),P(2,'absence of breast','left'),P(3,'metal clips','right axilla'),P(4,'device','right axillary edge',amb=True),
   P(5,'nodular image','right posterior 6th-7th rib','small; may be vascular crossing',POSS,True)],
8:[P(0,'Chilaiditi sign','','normal variant',amb=True),P(1,'aortic elongation'),P(2,'pleural thickening','biapical'),P(3,'degenerative bone change')],
9:[N(0,'infiltrate'),N(0,'consolidation'),P(1,'scoliosis','dorsal','marked'),P(2,'cardiomegaly'),P(3,'hemidiaphragm elevation','left')],
10:[P(0,'air trapping'),N(1,'consolidation','','currently'),P(2,'nodule','right basal','not visualized in lateral projection',amb=True),P(3,'nipple shadow','','probable',POSS,True)],
11:[N(0,'pulmonary abnormality','lung parenchyma'),N(1,'mediastinal abnormality','mediastinal silhouette'),P(2,'scoliosis','dorsal')],
12:[P(0,'vascular congestion','hilar','probable vascular etiology',amb=True),P(1,'atelectasis','left basal','laminar'),P(2,'aortic elongation'),P(3,'degenerative bone change','axial skeleton','age-related',amb=True)],
13:[P(0,'aortic elongation'),P(1,'cardiomegaly'),P(2,'aortic calcification','arch'),P(3,'pleural thickening','apical')],
14:[NSF(0),P(1,'dense image','right posterior 6th rib arch','PA projection',amb=True)],
15:[P(0,'fibrosis','upper lobes','tracts',POSS,True),OTH(1)],
16:[P(0,'sternotomy','median'),P(1,'sutures'),N(2,'pulmonary abnormality','lung parenchyma')],
17:[P(0,'costophrenic angle blunting','right'),OTH(1)],
18:[N(0,'cardiomediastinal abnormality'),N(1,'pleural effusion','costophrenic sinuses'),P(2,'diaphragmatic lobulation','right')],
19:[P(0,'central venous catheter','right jugular vein to superior vena cava'),P(1,'hilar enlargement','right','probable vascular origin',amb=True)],
20:[P(0,'pleural thickening','bilateral apical','marked'),P(1,'costophrenic angle blunting','bilateral'),N(2,'infiltrate')],
21:[P(0,'calcified granuloma','left base'),P(1,'pleural thickening','bilateral apical')],
22:[P(0,'cardiomegaly','','global')],
23:[P(0,'nodules','middle fields','compatible with nipples',amb=True)],
24:[P(0,'endotracheal tube','','3.1 cm from carina'),P(1,'central venous catheter','right jugular; tip superior vena cava'),P(2,'aortic elongation'),P(3,'hilar prominence','','probable vascular origin',amb=True)],
25:[P(0,'mechanical change','','associated',amb=True),P(1,'scoliosis','dorsolumbar')],
26:[P(0,'tracheostomy tube')],
27:[P(0,'goiter',amb=True),P([1,2],'paratracheal mass','right paratracheal','compresses and displaces trachea')],
28:[N(0,'consolidation'),P(1,'aortic elongation'),OTH(2)],
29:[P(0,'endotracheal tube','','4 cm from carina'),P(1,'central venous catheter','right jugular; distal end near superior vena cava')],
30:[N(0,'consolidation'),P(1,'calcified aortic atheromatosis'),P(2,'spondylosis','spine'),OTH(3)],
31:[P(0,'azygos lobulation'),P(1,'chronic pulmonary change'),P(2,'retrocardiac laminar ectasia',amb=True)],
32:[P(0,'infiltrate','left upper lobe')],
33:[P(0,'bulla','left upper lobe')],
34:[P(0,'hilar prominence','','probable vascular origin',amb=True),OTH(1)],
35:[P(0,'reservoir device','right hemithorax'),P(1,'chronic pulmonary change','predominantly bases','significant')],
36:[P(0,'scoliosis','dorsolumbar','marked')],
37:[P(0,'pacemaker','','dual chamber'),P(1,'aortic elongation')],
38:[P(0,'cardiomediastinal silhouette enlargement'),N(1,'consolidation'),N(2,'pleural effusion')],
39:[P(0,'calcified aortic atheromatosis'),P(1,'hilar prominence','','probable vascular origin',amb=True),P(2,'gynecomastia','bilateral'),P(3,'degenerative bone change','dorsolumbar','osteophytosis')],
40:[N(0,'consolidation'),P(1,'surgical clips'),P(2,'sternotomy wiring','median'),P(3,'spondylosis')],
41:[P(0,'cardiomegaly'),P(1,'aortic calcification'),P(2,'aortic elongation'),P(3,'calcification','right arm'),P(4,'degenerative change','axial column')],
42:[P(0,'cardiomegaly'),P(1,'aortic elongation'),P(2,'hilar prominence','','vascular')],
43:[N(0,'pleural rub'),P(1,'infiltrate','right suprahilar','small'),P(2,'costophrenic angle blunting','left')],
44:[P(0,'gynecomastia','bilateral')],
45:[P(0,'mammary prosthesis','bilateral'),P(1,'scoliosis','','parenthetical',amb=True),OTH(2)],
46:[P(0,'calcified aortic atheromatosis'),OTH(1)],
47:[N(0,'pulmonary metastatic involvement'),P(1,'hiatal hernia','','large'),P(2,'mechanical change','dorsal spine',amb=True)],
48:[P(0,'costophrenic angle blunting','right'),P(1,'hilar prominence','','probable vascular etiology',amb=True),P(2,'calcified granuloma','right basal')],
49:[P(0,'alveolar infiltrate','right upper lobe and right lower lobe posterior basal segments','compatible with pneumonia condensation',amb=True)],
50:[NSF(0),P(1,'osteosynthesis','left clavicle')],
51:[P(0,'alveolar infiltrate','right lung base','inflammatory/infectious process'),OTH(1)],
52:[P(0,'osteopenia','','diffuse'),P(1,'aortic elongation'),P(2,'chronic inflammatory change','bilateral base'),P(3,'scoliosis'),N(4,'no significant finding','','radiological',True)],
53:[P(0,'atelectasis','bilateral basal; left predominant','segmental'),N(1,'consolidation')],
54:[NSF(0,'pulmonary parenchyma and cardiomediastinal silhouette'),N(1,'bone lesion'),P(2,'gynecomastia','bilateral')],
55:[P(0,'atelectasis','left lower lobe','laminar')],
56:[P(0,'volume loss','right upper lobe'),OTH(1)],
57:[P(0,'chronic pulmonary change'),P(1,'aortic elongation'),P(2,'diaphragmatic lobulation'),P(3,'vertebral crushing','middle dorsal')],
58:[P(0,'ground glass pattern','right basal','pseudonodule; possibly infectious-inflammatory',amb=True)],
59:[P(0,'calcified granuloma','right upper lobe'),P(1,'scoliosis','dorsolumbar')],
60:[P(0,'hemidiaphragm elevation','right anterior'),P(1,'hilar reinforcement','bilateral'),N(2,'alveolar infiltrate','','disappearance; LSD abbreviation',True)],
61:[P(0,'infiltrate','left middle field','faint',amb=True),P(1,'breast prosthesis','bilateral')],
62:[P(0,'paraspinal line detachment','left','related to lipomatosis',amb=True)],
63:[P(0,'cardiomegaly','','severe'),P(1,'spondylosis','dorsal'),N(2,'consolidation','lung','clear')],
64:[P(0,'scoliosis','dorsolumbar')],
65:[P(0,'hilar prominence','','vascular nature'),P(1,'tracheal displacement','lateral wall of trachea'),P(2,'goiter')],
66:[P(0,'air trapping'),P(1,'cardiothoracic index','','at limit of pathological significance',amb=True),P(2,'bronchiectasis','bibasal','probable',POSS,True),N(3,'consolidation'),N(4,'pleural effusion','costophrenic sinuses')],
67:[P(0,'kyphoscoliosis','dorsal'),P(1,'fibrotic bands','right upper lobe')],
68:[N(0,'suspicious lesion'),P(1,'calcified aortic atheromatosis'),OTH(2)],
69:[P(0,'pectus excavatum'),P(1,'air trapping')],
70:[P(0,'tracheostomy tube'),P(1,'surgical change','cervical'),P(2,'nasogastric tube','infradiaphragmatic')],
71:[P(0,'alveolar opacity','lingula and left lower lobe','alveolar space occupation',amb=True)],
72:[P(0,'cavitated image','left upper lobe','AP projection'),P(1,'diagnostic uncertainty','','infectious-inflammatory process versus cavitary tumor; CT needed',POSS,True)],
73:[P(0,'chronic pulmonary change'),P(1,'aortic elongation'),P(2,'nodule','right middle lung field')],
74:[P(0,'cardiomegaly'),P(1,'sternotomy sutures','median')],
75:[N(0,'pulmonary finding'),P(1,'vertebral wedging','dorsal'),P(2,'kyphosis','','slight')],
76:[P(0,'mastectomy','bilateral'),OTH(1)],
77:[N(0,'infiltrate'),N(0,'consolidation'),P(1,'bronchiectasis','left basal','probable',POSS,True)],
78:[P(0,'pacemaker','','distal end in ventricular position'),P(1,'pleural effusion','left'),P(2,'costophrenic angle blunting','right'),P(3,'hilar enlargement','','probable vascular origin',amb=True),P(4,'aortic calcification')],
79:[P(0,'diaphragmatic lobulation','right anterior'),N(1,'consolidation')],
80:[P(0,'gynecomastia'),P(1,'aortic elongation'),OTH(2)],
81:[P(0,'cardiothoracic index','','upper limit of normal',amb=True),P(1,'aortic elongation'),P(2,'sternal wiring','sternotomy'),OTH(3)],
82:[P(0,'nodular images','above left pulmonary hilum','correspond to orthogonally projected vessels',amb=True)],
83:[P(0,'rib fracture','left'),N(1,'pleural effusion','costophrenic angles'),P(2,'degenerative change','right glenohumeral joint')],
84:[P(0,'pulmonary mass','','known'),P(1,'post-lobectomy change')],
85:[P(0,'chronic pulmonary change','right lower lobe'),P(1,'air trapping')],
86:[P(0,'hypoventilation','bibasal',amb=True),P(1,'vertebral wedging','middle dorsal','anterior'),P(2,'kyphosis','dorsal')],
87:[P(0,'scoliosis','dorsal')],
88:[P(0,'metallic foreign body','right main bronchus','dental bridge'),N(1,'atelectasis','right lung','not caused by foreign body')],
89:[P(0,'linear tracts','right upper lobe',amb=True),P(1,'nodules','','small high-density; suggestive of calcified granulomas',amb=True)],
90:[P(0,'scoliosis','dorsolumbar'),OTH(1)],
91:[P(0,'hiatal hernia')],
92:[P(0,'endotracheal tube','','1.7 cm from carina'),P(1,'pleural effusion','bilateral')],
93:[P(0,'spondylosis','dorsal')],
94:[P(0,'costophrenic angle blunting','left'),N(1,'pulmonary abnormality','pulmonary parenchyma')],
95:[N(0,'consolidation'),P(1,'surgical clips','right paravertebral'),OTH(2)],
96:[NSF(0)],97:[N(0,'consolidation'),N(0,'pulmonary opacity'),N(1,'cardiomediastinal abnormality')],98:[NSF(0,'for patient age')],99:[NSF(0)],100:[NSF(0)],101:[NSF(0)],
102:[NSF(0)],103:[NSF(0)],104:[N(0,'cardiomediastinal abnormality'),N(1,'infiltrate','','of pathological significance')],105:[NSF(0)],
106:[N(0,'infiltrate'),N(0,'consolidation'),N(1,'cardiomegaly')],107:[NSF(0)],108:[NSF(0,'for patient age')],109:[NSF(0)],110:[NSF(0)],111:[NSF(0)],112:[NSF(0)],
113:[N(0,'infiltrate'),N(0,'consolidation')],114:[NSF(0,'for patient age')],115:[N(0,'infiltrate'),N(0,'consolidation'),N(1,'cardiomegaly')],116:[NSF(0)],117:[NSF(0,'for patient age')],118:[NSF(0)],119:[NSF(0)],120:[NSF(0)],
121:[N(0,'cardiomegaly'),N(1,'mediastinal abnormality'),N(2,'pulmonary abnormality','lung parenchyma'),N(3,'pleural effusion'),N(4,'bone abnormality'),NSF(5)],
122:[NSF(0)],123:[N(0,'infiltrate'),N(0,'consolidation')],124:[N(0,'cardiomediastinal abnormality'),N(1,'pleural effusion','costophrenic angles'),NSF(2)],125:[N(0,'cardiomediastinal abnormality'),N(1,'pleural effusion','costophrenic angles')],126:[NSF(0)],127:[NSF(0)],
}

def main():
    data=OUT/'data/E128/manifest.json';rows=json.loads(data.read_text());assert len(rows)==128==len(ROWS)
    for i,r in enumerate(rows):
        n=len(r['findings'])
        for a in ROWS[i]:
            idx=[a[0]] if isinstance(a[0],int) else a[0];assert all(0<=j<n for j in idx),(i,a)
        covered={j for a in ROWS[i] for j in ([a[0]] if isinstance(a[0],int) else a[0])}
        assert covered==set(range(n)),(i,'미포함 문장',set(range(n))-covered)
    save(OUT/'semantic/E_definitions.json',dict(manifest_sha=sha(data),source_sha=sha(__file__),
        rows=[dict(id=r['ImageID'],reviewed=True,atoms=ROWS[i]) for i,r in enumerate(rows)]))
    print('E definitions',sum(len(v) for v in ROWS.values()),'atoms')

if __name__=='__main__':main()
