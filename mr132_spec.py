"""생성 전 고정한 MR-ART prompt·첫 줄 parser·사건 정의."""
import re
CONFIG=dict(model_id='google/medgemma-1.5-4b-it',revision='91850547d9f0b2fdd21aa7c5f4f3d1a8a52c243b',dtype='bfloat16',attention='sdpa',max_new_tokens=512,do_sample=False,seed=132)
SINGLE=('These are eight evenly spaced axial slices from one T1-weighted brain MRI acquisition. '
        'Assess motion-related image degradation visible in these images, such as blurring, ghosting, or ringing. '
        'Give a continuous degradation score from 0 to 100, where 0 means minimal degradation and 100 means severe degradation. '
        'On the first line output only the numeric score. Then briefly explain the visible evidence. '
        'Do not infer disease or use patient identity.')
PAIR=('These are two T1-weighted brain MRI acquisitions of the same person, with the same eight axial slice positions. '
      'Compare the motion-related image quality visible in the two acquisitions, including blurring, ghosting, or ringing. '
      'Choose the acquisition with better image quality: A or B. Use TIE if neither is visibly better, or UNKNOWN if you cannot assess. '
      'On the first line output only A, B, TIE, or UNKNOWN. Then briefly explain the visible evidence. '
      'Do not infer disease or use patient identity.')
ACQS=['standard','headmotion1','headmotion2']
PAIRS=[(0,1),(0,2),(1,2)]
def parse(text,kind,eos=True):
    if not eos or not text.strip(): return None
    line=text.strip().splitlines()[0].strip()
    if kind=='single':
        if not re.fullmatch(r'(?:\d+(?:\.\d+)?|\.\d+)',line): return None
        score=float(line)
        return score if 0<=score<=100 else None
    return line if line in ['A','B','TIE','UNKNOWN'] else None

def pair_value(pred,winner,strict=False):
    if pred is None or pred=='UNKNOWN': return 0.
    if pred=='TIE': return 0. if strict else .5
    return float(pred==winner)

def expansion(delta_single,delta_iqm,consistency,error_rate):
    return delta_single>=.10 and delta_iqm>=.05 and consistency>=.90 and error_rate<=.05
