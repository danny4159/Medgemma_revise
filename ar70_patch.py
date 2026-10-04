"""iter_070: build a minimally patched copy of the official AutoRG-Brain source (pinned SHA).

Patches (everything else is untouched):
 1. inferenceSdk.AutoRG_Brain.__init__: do not overwrite CUDA_VISIBLE_DEVICES (keep inherited GPU set).
 2. GPT-2 base 'healx/gpt-2-pubmed-medium' -> local pinned snapshot via env AR70_GPT2.
 3. generate(max_length=300) -> env AR70_MAXLEN (default 300), to allow the pre-registered single cap doubling.
Writes a unified diff to <out>/ar70_patch.diff.
"""
import difflib
import os
import shutil
import sys

SHA = '9670703c88e8f599c0c7edc472a5ffce4dd72b0e'
SRC = f'results/iter_070/external/src/AutoRG-Brain-{SHA}'
DST = 'results/iter_070/external/patched'

EDITS = [
    ('AutoRG_Brain/inference/inferenceSdk.py',
     '        os.environ["CUDA_VISIBLE_DEVICES"] = str(gpu_id[0])\n',
     '        # ar70: inherited CUDA_VISIBLE_DEVICES is kept (original overwrote it); gpu_id[0] is the logical index\n'),
    ('AutoRG_Brain/inference/inferenceSdk.py',
     'max_length=300,',
     "max_length=int(os.environ.get('AR70_MAXLEN', '300')),"),
    ('AutoRG_Brain/network/language_model_patchwise.py',
     'self.checkpoint = "healx/gpt-2-pubmed-medium"',
     "self.checkpoint = __import__('os').environ.get('AR70_GPT2', 'healx/gpt-2-pubmed-medium')"),
    ('AutoRG_Brain/network_training/nnUNetTrainerV2_llm_resize_new.py',
     'checkpoint = "healx/gpt-2-pubmed-medium"',
     "checkpoint = __import__('os').environ.get('AR70_GPT2', 'healx/gpt-2-pubmed-medium')"),
    # 4. transformers moved BeamSearchScorer; same class, new module path (unused in greedy decoding)
    ('AutoRG_Brain/network/language_model_patchwise.py',
     'from transformers.generation_beam_search import BeamSearchScorer',
     'from transformers.generation.beam_search import BeamSearchScorer'),
]


def main():
    # --reapply: re-derive edited files from the pinned SRC into an existing DST (derived copy only)
    reapply = len(sys.argv) > 1 and sys.argv[1] == '--reapply'
    if os.path.exists(DST) and not reapply:
        sys.exit('refusing to overwrite ' + DST)
    if not os.path.exists(DST):
        shutil.copytree(SRC, DST, ignore=shutil.ignore_patterns('__pycache__', 'results'))
    diff = []
    for f in dict.fromkeys(e[0] for e in EDITS):
        orig = open(os.path.join(SRC, f)).read()
        t = orig
        for ef, old, new in EDITS:
            if ef == f:
                assert t.count(old) == 1, (f, old, t.count(old))
                t = t.replace(old, new)
        open(os.path.join(DST, f), 'w').write(t)
        diff += list(difflib.unified_diff(orig.splitlines(True), t.splitlines(True), f'a/{f}', f'b/{f}'))
    open(os.path.join(DST, 'ar70_patch.diff'), 'w').write(''.join(diff))
    print(''.join(diff))


if __name__ == '__main__':
    main()
