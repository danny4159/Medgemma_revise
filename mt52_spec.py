"""고정 CT workflow prompt, 엄격 MCQ parser, 추론 필드 경계."""
import hashlib
import json
import re

MODEL_REVISION='91850547d9f0b2fdd21aa7c5f4f3d1a8a52c243b'
FINAL='Give a brief rationale, then write exactly one answer on the last line as Answer: <A-E>.'
F='Describe the observations and uncertainties visible in this image. Do not choose a diagnosis option. Preserve the image index when describing findings.'
U='Integrate the following image-indexed observations into a concise imaging summary. Preserve relevant findings, uncertainty, and image indices. Do not choose a diagnosis option.'
H='Describe the observations and uncertainties across all provided images together. Preserve image indices. Do not choose a diagnosis option.'

def digest(obj):
    return hashlib.sha256(json.dumps(obj,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()

def check_case(c):
    if set(c)!={'case_key','CLINICAL_HISTORY','options','images'}:
        raise ValueError('inference fields')
    if set(c['options'])!=set('ABCDE'):
        raise ValueError('option keys')
    for im in c['images']:
        if set(im)!={'id','path'}:raise ValueError('image fields')

def context(c):
    check_case(c)
    return 'Clinical history:\n'+c['CLINICAL_HISTORY']+'\nOptions:\n'+'\n'.join(f'{k}. {c["options"][k]}' for k in 'ABCDE')

def prompt(c,stage,parents=(),index=None):
    base=context(c)
    if stage=='F':return base+f'\nImage index: {index+1}\n'+F
    if stage=='U':
        if len(parents)!=len(c['images']):raise ValueError('missing F outputs')
        return base+'\n'+U+'\n'+'\n'.join(f'Image {i+1}:\n{s}' for i,s in enumerate(parents))
    if stage=='H':return base+'\n'+H
    if stage in ('T','D'):
        if parents:raise ValueError('unexpected parent')
        return base+'\n'+FINAL
    if stage in ('C','R','X'):
        if len(parents)!=1:raise ValueError('exactly one summary required')
        return base+'\nImaging summary:\n'+parents[0]+'\n'+FINAL
    raise ValueError('unknown stage')

def parse(text):
    lines=[s.strip() for s in text.splitlines() if s.strip()]
    if not lines or not re.fullmatch(r'Answer: [A-E]',lines[-1]):return None
    if len(re.findall(r'(?im)^\s*Answer\s*:',text))!=1:return None
    return lines[-1][-1]
