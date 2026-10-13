"""iter_133: GPU 출력 전에 고정한 prompt·첫 줄 parser·렌더 설정 (U/L/M)."""
CONFIG = dict(model_id='google/medgemma-1.5-4b-it', revision='91850547d9f0b2fdd21aa7c5f4f3d1a8a52c243b', dtype='bfloat16',
              attention='sdpa', max_new_tokens=512, do_sample=False, seed=133, batch=1)
CATS = ['HIGH', 'MIXED_HIGH_LOW', 'OTHER', 'UNKNOWN']
COMMON = ('These are eight evenly spaced axial FLAIR MRI slices of one brain, ordered from inferior to superior. '
          'Describe the visible FLAIR signal of the main lesion. '
          'On the first line output only one of: HIGH, MIXED_HIGH_LOW, OTHER, UNKNOWN. '
          'HIGH means the lesion appears hyperintense (high signal); it does not state whether low-signal components are absent. '
          'MIXED_HIGH_LOW means both high-signal and low-signal components are visible within the lesion. '
          'OTHER means a different signal pattern. UNKNOWN means the signal cannot be assessed. '
          'Then briefly explain the visible evidence.')
GUIDE = (' A thin red rectangle on each slice marks the approximate region around the lesion on that slice. '
         'It is only a coarse guide, and not every tissue inside the rectangle is lesion.')
NOPIX = ' In this input, no MRI pixel data are provided: every image is a neutral gray background that contains only the red rectangle.'
PROMPTS = dict(U=COMMON, L=COMMON + GUIDE, M=COMMON + GUIDE + NOPIX)
RENDER = dict(side=896, rect_rgb=[255, 0, 0], rect_px=2, gray=[128, 128, 128], normalization='volume_minmax', n_slices=8,
              round_half='down', mask_rule='seg>0', orientation='closest_canonical_RAS')
FORBIDDEN_IN_PROMPT = ['BraTS', 'GLI', 't2f', 'glioma', 'tumor', 'edema', 'RadGenome', 'sub-', 'report']


def parse(text, eos=True):
    if not eos or not text or not text.strip():
        return None
    line = text.strip().splitlines()[0].strip()
    return line if line in CATS else None
