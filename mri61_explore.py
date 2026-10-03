"""iter_061: OmniBrainBench closed-ended QA 적격성 탐색(모델 출력 없음)."""
import json, collections, re

C = collections.Counter
MRI = {'mri', 't1w', 't2w', 'flair', 't1ce', 'adc', 'dwi', 'magnetic resonance angiography'}
d = json.load(open('results/iter_061/data/raw/closed-ended-qa_6823.json'))
xs = [x for x in d if x['task_label'] == 'Disease Diagnosis Reasoning'
      and all(m.lower() in MRI for m in x['modality_type'])]
print(len(xs), C(x['source_file'].split('_')[0] for x in xs))


def ans(x):
    return x['options']['ABCDE'.index(x['answer'])]


leak = [x for x in xs if ans(x).lower() in x['question'].lower()]
print('answer-string in question', len(leak), C(x['source_file'].split('_')[0] for x in leak))
for x in leak[:4]:
    print(' ', ans(x), '|', x['question'][:250])
print('non-unique options', sum(1 for x in xs if len(set(x['options'])) != 5))
print('stems', C(x['question'].strip().split('.')[-1][:80] for x in xs).most_common(12))
pm = [x for x in xs if x['source_file'].startswith('PubMed')]
print('PubMed', len(pm), C(x['image_path'][0].split('_')[0] for x in pm))
print('Image N refs', C(x['source_file'].split('_')[0] for x in xs if 'Image 1' in x['question']))
print('label vs answer mismatch', sum(1 for x in xs if x['label'].strip('() ').lower() not in (ans(x).lower(), x['answer'].lower())
      and not re.sub(r'^\([A-E]\)\s*', '', x['label']).lower().startswith(ans(x).lower()[:6])))
