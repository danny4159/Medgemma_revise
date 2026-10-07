"""출력 전 고정 V32 reference 원자화. 직접 읽은 문구와 모호성을 보존한다."""
import json
from report90_numeric import OUT
from report86_common import save,sha

# 각 항목: source 문장 번호, 독립 소견, 극성, 확실성, 위치, 속성, 모호성.
SPECIAL={
0:[(0,'cardiomegaly','positive','possible','left ventricle','PA apparent; not confirmed lateral',True)],
9:[(0,'infiltrate','negative','definite','','significant',False),(0,'consolidation','negative','definite','','significant',False),(1,'cardiomegaly','negative','definite','','normal cardiothoracic index',False)],
13:[(0,'infiltrate','negative','definite','','',False),(0,'consolidation','negative','definite','','',False),(1,'central venous catheter','positive','definite','right jugular vein; tip beginning right atrium','',False)],
16:[(0,'alveolar interstitial infiltrate','positive','definite','perihilar; right predominant','alveolar/interstitial',True)],
17:[(0,'nipple shadow','positive','definite','','',True),(1,'nodular image','positive','definite','bilateral basal','small',True)],
18:[(0,'gynecomastia','positive','definite','bilateral','',False),(1,'metallic artifact','positive','definite','left cervical','metallic',False),(2,'suture','positive','possible','left cervical','',True)],
19:[(0,'aortic prominence','positive','definite','aortic knob','tracheal impression',False),(1,'mediastinal widening','positive','definite','mediastinum','slight; secondary prominent ascending aorta',False),(1,'aortic prominence','positive','definite','ascending aorta','',False),(2,'pleural effusion','negative','definite','costophrenic sinuses','',False),(3,'gynecomastia','positive','definite','bilateral','',False)],
20:[(0,'vascular congestion','positive','definite','hilar','',False),(1,'central venous catheter','positive','definite','subclavian vein','',False),(2,'cardiomegaly','positive','definite','','',False),(3,'atelectasis','positive','possible','retrocardiac','',False)],
23:[(0,'pacemaker','positive','definite','','',False),(1,'infiltrate','negative','definite','','',False),(1,'consolidation','negative','definite','','',False),(2,'pneumothorax','negative','definite','','',False)],
27:[(0,'interstitial infiltrate','positive','possible','right lung base','',False),(1,'chronic pulmonary change','positive','definite','lung parenchyma','chronic',True),(2,'fibrosis','positive','definite','bilateral apical','tracts',False),(3,'other relevant finding','negative','definite','outside described findings','',True)],
29:[(0,'pulmonary nodule','positive','definite','right lower lobe; peripheral posterior','2cm; well-defined rounded',False),(0,'pulmonary nodule','positive','definite','right middle lung field','9mm',False),(0,'lung neoplasm','positive','possible','right lung','',True),(1,'hilar prominence','positive','definite','left','',False),(2,'pleural effusion','negative','definite','costophrenic angles','',False),(3,'metallic artifact','positive','definite','','lighter-related',False)]}
DETAIL={1:('pleural effusion','left posterior costophrenic angle','small'),14:('scoliosis','dorsolumbar','right convexity'),21:('pacemaker','','dual chamber'),22:('hiatal hernia','',''),24:('aortic elongation','',''),25:('atelectasis','left lower lobe','segmental'),26:('catheter','neck',''),31:('pleural thickening','bilateral apical','')}

def main():
    path=OUT/'data/V32/manifest.json';rows=json.loads(path.read_text());refs=[]
    for i,r in enumerate(rows):
        atoms=[]
        entries=SPECIAL.get(i)
        if entries is None:
            entries=[]
            for j,f in enumerate(r['findings']):
                text=f['sentence_en'];ab=f['abnormal']
                name,loc,attrs=DETAIL.get(i,(text,'','')) if ab else ('no significant finding','','')
                if i==15:name,loc,attrs=[('air trapping','',''),('pleuroparenchymal change','','chronic'),('degenerative bone change','thoracic spine','degenerative')][j]
                if i==28:name,loc,attrs=[('metallic prosthesis','right humerus','metallic'),('scoliosis','dorsolumbar','')][j]
                if i==30 and ab:name=['tracheostomy tube','nasogastric tube'][j]
                if not ab:
                    if i==5 and j==0:name,loc,attrs='abnormal pleuroazygoesophageal recess','pleuroazygoesophageal recess','adequately visualized'
                    if i==14 and j==0:name='suspicious lesion'
                    if i==21:name='pacemaker complication'
                    if i==26:loc='chest'
                    if i==30:name,loc,attrs='major pulmonary alteration','lung parenchyma','major'
                entries.append((j,name,'positive' if ab else 'negative','definite',loc,attrs,'other' in text.lower()))
        for k,(j,name,pol,cert,loc,attrs,amb) in enumerate(entries):
            source=r['findings'][j]['sentence_en'];start=r['report'].index(source)
            # 중복 표현을 통합한 경우 두 원문을 함께 연결한다.
            if i==16:source=r['report'];start=0
            atoms.append(dict(id=f'V{i:02}A{k:02}',finding=name,polarity=pol,certainty=cert,location=loc,attributes=attrs,ambiguous=amb,
                source=source,start=start,end=start+len(source),source_index=j,abnormal=r['findings'][j]['abnormal']))
        assert all(r['report'][a['start']:a['end']]==a['source'] for a in atoms)
        refs.append(dict(id=r['ImageID'],patient=r['PatientID'],report=r['report'],abnormal=any(f['abnormal'] for f in r['findings']),atoms=atoms))
    save(OUT/'semantic/V32_reference_v3.json',dict(rows=refs,manifest_sha=sha(path),source_sha=sha(__file__),scope='assistant reference interpretation; not clinician gold; no generated V32 output seen; v3 merges V16 duplicate evidence spans'))

if __name__=='__main__':main()
