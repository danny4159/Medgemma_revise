SPIDER 이미지 다운로드가 아직 진행 중입니다(약 46%, 속도 저하). 백그라운드 완료 알림을 기다린 뒤 이어서 진행하겠습니다.

# [orchestrator] 권한 거부된 도구 호출
- Bash: curl -sI --max-time 15 https://zenodo.org/records/10159290 | head -5; echo RC=$?
- Bash: find /SSD1_1TB/home/milab/daniel/08_medgemma/legacy -iname "*spider*" 2>/dev/null; find /SSD1_1TB/home/milab/daniel/08_medgemma -maxdepth 3 -iname "*spider*" 2>/dev/null; find / -maxdepth 6 -iname "*spider*" 2>/dev/null | grep -v proc
- Bash: wget --timeout=15 -q -O /tmp/test_net.html https://zenodo.org/records/10159290; echo RC=$?; ls -la /tmp/test_net.html 2>/dev/null
- Bash: wget --timeout=15 -q -O /tmp/test_net.html https://zenodo.org/records/10159290
- Bash: python -c "
import zipfile
z = zipfile.ZipFile('masks.zip')
data = z.read('masks/101_t1.mha')
print(len(data))
# find header end
idx = data.find(b'ElementDataFile')
print(idx)
print(data[:idx+50])
"
- Bash: python -c "
import os
os.environ.setdefault('HF_HOME', '/SSD1_1TB/home/milab/daniel/08_medgemma/hf_cache')
os.environ.setdefault('HF_HUB_OFFLINE', '1')
import numpy as np, hashlib
from PIL import Image
import transformers
from rsna_diag import generate as G

proc = transformers.AutoProcessor.from_pretrained(G.MODEL_ID, revision=G.MODEL_REVISION)
img1 = Image.fromarray((np.random.RandomState(1).rand(50,50,3)*255).astype('uint8'))
img2 = Image.fromarray((np.random.RandomState(2).rand(50,50,3)*255).astype('uint8'))

def h(t):
    return hashlib.sha256(t.numpy().tobytes()).hexdigest()

out_ab = G.build_inputs_multi(proc, [img1, img2], 'hello')
out_ba = G.build_inputs_multi(proc, [img2, img1], 'hello')
print('pixel_values shape', out_ab['pixel_values'].shape)
print('order AB pv0 hash', h(out_ab['pixel_values'][0]))
print('order AB pv1 hash', h(out_ab['pixel_values'][1]))
print('order BA pv0 hash', h(out_ba['pixel_values'][0]))
print('order BA pv1 hash', h(out_ba['pixel_values'][1]))
print('AB.pv0==BA.pv1', h(out_ab['pixel_values'][0])==h(out_ba['pixel_values'][1]))
print('AB.pv1==BA.pv0', h(out_ab['pixel_values'][1])==h(out_ba['pixel_values'][0]))
print('input_ids equal (should be, same text/structure)', out_ab['input_ids'].tolist()==out_ba['input_ids'].tolist())
# reference: manual official-style construction
msgs = [{'role':'user','content':[{'type':'image','image':img1},{'type':'image','image':img2},{'type':'text','text':'hello'}]}]
ref = proc.apply_chat_template(msgs, add_generation_prompt=True, tokenize=True, return_dict=True, return_tensors='pt')
print('matches manual construction', h(ref['pixel_values'][0])==h(out_ab['pixel_values'][0]) and ref['input_ids'].tolist()==out_ab['input_ids'].tolist())
"

