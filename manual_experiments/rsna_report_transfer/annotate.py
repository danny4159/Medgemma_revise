"""모델명/정답 공개 전 assistant가 원문을 읽고 고정한 문장 분류. 임상의 평가 아님."""
from .run import OUT, save

# id | target | laterality | contradiction | evidence quote
DATA='''0050b6d770|present|right|0|Right lower lobe consolidation.
00a6c52a6b|possible|right|0|possibly pleural effusion or consolidation.
02b79ec60e|present|right|1|There is a small opacity in the right lower lobe.
059ea6e6de|absent|unspecified|0|without focal consolidation
082723f1cb|possible|left|1|Possible opacity in the left lower lung field.
0a5b305a34|unmentioned|unspecified|0|possibly representing a small pleural effusion or atelectasis.
0b2cba8397|absent|unspecified|0|without focal consolidation
0d8963a431|absent|unspecified|0|Normal chest X-ray.
129929c814|present|bilateral|0|bilateral pulmonary edema with significant opacities in the lower lung fields
131b8d3ede|absent|unspecified|0|The lungs are clear.
142c280d98|present|bilateral|0|The right upper lobe shows patchy opacity and reticular changes. The left upper lobe also shows some patchy opacity.
150f102cdd|absent|unspecified|0|The lungs are clear.
19f1ba38c1|absent|unspecified|0|The lungs are well-expanded and clear bilaterally.
1abed766e1|absent|unspecified|0|The lungs are clear.
1c37c5f3da|present|bilateral|0|diffuse bilateral pulmonary edema, with increased opacity in the perihilar regions
1f30573dd4|absent|unspecified|0|no evidence of consolidation
24d260aaed|present|bilateral|0|Bilateral pulmonary infiltrates
2bf290589e|absent|unspecified|0|The lungs are clear.
2dad5823f9|absent|unspecified|0|The lungs are clear.
302004de96|unmentioned|unspecified|0|Right upper lobe scar.
30542fafaf|unmentioned|unspecified|0|which may represent atelectasis or scarring.
32eb272708|absent|unspecified|0|The lungs are clear, with normal lung markings.
36e637d211|unmentioned|unspecified|0|Left pneumothorax with subcutaneous emphysema.
3f424c0aa1|absent|unspecified|0|The lungs are clear.
3f699c05fc|absent|unspecified|0|The lungs are clear.
40650a3499|possible|right|0|possibly representing atelectasis or early pneumonia.
431bd00381|absent|unspecified|0|no focal consolidation
43ad4673d3|absent|unspecified|0|The lungs are clear.
43bc134a93|unmentioned|unspecified|0|Multiple bilateral pulmonary nodules.
462a02d1c9|unmentioned|unspecified|0|Right pleural effusion.
46fbd2071a|absent|unspecified|0|The lungs are clear.
4a56a42528|unmentioned|unspecified|0|Large right pleural effusion with associated atelectasis.
4adf81d609|unmentioned|unspecified|0|The patient is rotated.
514455d7d3|absent|unspecified|0|The lungs are clear bilaterally.
51f68d1273|absent|unspecified|0|The lungs are clear.
5375d37ef6|absent|unspecified|0|no focal consolidation
53895346a6|absent|unspecified|0|without focal consolidation
549c22766f|absent|unspecified|0|The lungs are clear.
58772a9ba2|absent|unspecified|0|without focal consolidation
5a47d51d63|absent|unspecified|0|The lungs are clear.
5d5edd08c4|absent|unspecified|0|The lungs are clear.
5e2030c579|present|right|0|There is increased opacity in the right lower lung field
60a97dae7e|absent|unspecified|0|The lungs are clear.
621641a9eb|absent|unspecified|0|no evidence of consolidation
645f58cd1c|absent|unspecified|0|The lungs are clear.
67b4af318a|absent|unspecified|0|The lungs are clear.
69e4755e47|absent|unspecified|0|without focal consolidation
6c118fd082|present|bilateral|0|diffuse bilateral infiltrates.
6cfb884190|possible|right|0|Right lower lobe consolidation/mass.
6e4fc6f4c9|absent|unspecified|0|The lungs are clear bilaterally.
6ebb05b99b|absent|unspecified|0|The lungs are clear.
6ee0e5f156|absent|unspecified|0|The lungs are clear.
71091ddd53|present|left|1|Small opacity in the left lower lung field.
72ef8526f3|present|right|0|Right upper and lower lobe opacities.
731a0464e3|absent|unspecified|0|The lungs are clear.
73c4ea452b|present|right|0|There is a small opacity in the right lower lung field.
73e30d14f5|absent|unspecified|0|The lungs are clear.
74bb15098b|absent|unspecified|0|The lungs are clear.
75399af126|absent|unspecified|0|The lungs are clear.
79065229c3|absent|unspecified|0|The lungs are clear.
7a23acbf15|present|bilateral|0|extensive bilateral pulmonary infiltrates
7a7b6db880|absent|unspecified|0|The lungs are clear.
7d8847cacd|unmentioned|unspecified|0|Large left pleural effusion with associated atelectasis. Pulmonary edema in the right lung.
816d403eae|absent|unspecified|0|The lungs are clear.
94c9e3a6b1|unmentioned|unspecified|0|Large right pleural effusion.
9759e4773a|absent|unspecified|0|The lungs are clear.
977ec1cc31|present|bilateral|0|multiple bilateral patchy opacities
993bf6f2d7|absent|unspecified|0|The lungs are clear.
9b9283e317|absent|unspecified|0|without evidence of consolidation
9c7087a675|absent|unspecified|0|The lungs are clear.
9e4cde91eb|absent|unspecified|0|The lungs are clear.
9f1c2149dd|unmentioned|unspecified|0|which may represent atelectasis or scarring.
a097923c0b|absent|unspecified|0|no focal consolidation
a1b947a834|present|bilateral|0|Right upper lobe and left upper lobe pneumonia.
a1ee89a19f|absent|unspecified|0|no evidence of focal consolidation
a39e3a1c1f|present|right|0|Small opacity in the right lower lung field.
a419d41ec8|absent|unspecified|0|The lungs are clear.
a7aefa5099|absent|unspecified|0|Normal chest X-ray.
a87cf760ac|absent|unspecified|0|The lungs are clear.
a89de51d84|absent|unspecified|0|The lungs are clear.
a8e41f1d7c|present|left|1|Small opacity in the left lower lobe.
a92f37ba28|unmentioned|unspecified|0|Right pleural effusion with partial right lung collapse.
a9455762aa|unmentioned|unspecified|0|Cardiomegaly and pulmonary edema.
a96ffaf884|absent|unspecified|0|The lungs are clear.
a9821c8b12|present|left|0|left lower lobe opacity.
ad514eda1a|absent|unspecified|0|The lungs are clear.
af199663af|absent|unspecified|0|The lungs are clear.
b34c6fce6a|present|bilateral|0|Right-sided pneumonia with volume loss and possible pleural effusion.
b35e9842dc|absent|unspecified|0|The lungs are clear.
b495bc7b6a|unmentioned|unspecified|0|Bilateral pulmonary nodules and cardiomegaly.
b5a6547615|absent|unspecified|0|The lungs are clear.
b9fe8d005e|possible|right|0|possibly representing consolidation or atelectasis.
bde97d89db|absent|unspecified|0|The lungs are clear.
bf7e2ab9a6|possible|bilateral|0|The findings are suggestive of pulmonary edema and/or infection.
c04c9ac955|absent|unspecified|0|The lungs are clear.
c0bd55ae6c|absent|unspecified|0|The lungs are clear.
c14fe48530|absent|unspecified|0|The lungs are clear.
c2cad9a9eb|absent|unspecified|0|without focal consolidation
c33e2b8601|absent|unspecified|0|The lungs are clear.
c4c81162b3|possible|right|0|suggestive of a large consolidation or mass.
c8c425432f|absent|unspecified|0|The lungs are clear bilaterally.
c9b139b2e1|present|bilateral|0|diffuse bilateral pulmonary opacities
cb592e5f07|present|bilateral|0|bilateral pulmonary edema, with increased opacity in the lung fields
cbd75fdeee|absent|unspecified|0|The lungs are clear bilaterally.
cc2e90962d|absent|unspecified|0|The lungs are clear.
d5fc024404|absent|unspecified|0|The lungs are clear.
d95c46de76|absent|unspecified|0|No acute cardiopulmonary process identified.
da207ed09e|absent|unspecified|0|Normal chest X-ray.
db36c61ac0|absent|unspecified|0|The lungs are clear.
e0b75d054b|present|left|0|Left lower lobe opacity.
e1e4710e40|possible|left|0|possibly atelectasis or consolidation.
e5e997b77b|possible|right|0|possibly representing atelectasis or consolidation.
e7b20294fd|absent|unspecified|0|The lungs are clear.
e84aa29f9a|absent|unspecified|0|The lungs are clear.
e9390c4211|absent|unspecified|0|The lungs are clear.
edde57dd1d|absent|unspecified|0|no evidence of consolidation
f1dba1ca42|present|bilateral|0|There are bilateral patchy opacities
f258d6873f|absent|unspecified|0|The lungs are clear.
f3081f2a33|absent|unspecified|0|The lungs are clear.
f5a24bce16|absent|unspecified|0|The right lung is clear. The left lung is clear.
'''

def main():
    annotations={}
    for line in DATA.strip().splitlines():
        id_,target,laterality,contradiction,quote=line.split('|',4)
        assert id_ not in annotations
        annotations[id_]={'target':target,'laterality':laterality,'contradiction':bool(int(contradiction)),
                          'quote':quote,'report_valid':target!='invalid'}
    save(OUT/'annotations.json',annotations)

if __name__=='__main__':main()
