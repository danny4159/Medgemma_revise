"""공식 연산은 그대로 실행하며 모델 구성 후 원 NIfTI 읽기 시작을 계측한다."""
import json
import os
from pathlib import Path
import runpy
import sys
import time

import tensorflow as tf

script=str(Path(sys.argv[1]).resolve())
gpus=tf.config.list_physical_devices('GPU')
if len(gpus)!=1:raise RuntimeError('single allowed GPU required')
limit=int(os.environ['SYNTHSEG_GPU_LIMIT_MIB'])
tf.config.set_logical_device_configuration(gpus[0],[tf.config.LogicalDeviceConfiguration(memory_limit=limit)])
print('GPU_ENVIRONMENT',json.dumps(dict(python=sys.executable,tensorflow=tf.__version__,
     visible=os.environ.get('CUDA_VISIBLE_DEVICES'),memory_limit_mib=limit)),flush=True)
events={}


def profile(frame,event,arg):
    if frame.f_code.co_filename!=script:return
    name=frame.f_code.co_name
    if name=='preprocess' and event=='call' and 'warm_start_monotonic' not in events:
        events['warm_start_monotonic']=time.monotonic()
        events['raw_input']=frame.f_locals.get('path_image')
    if name=='write_csv' and event=='return' and 'warm_start_monotonic' in events:
        events['last_csv_saved_monotonic']=time.monotonic()


sys.argv=sys.argv[1:]
sys.setprofile(profile)
try:runpy.run_path(script,run_name='__main__')
finally:
    sys.setprofile(None)
    events['process_end_monotonic']=time.monotonic()
    events['boundary_ko']='공식 모델 구성 후 preprocess 호출 직전부터 실제 원 NIfTI를 읽는다. 첫 predict tracing을 포함하며 steady-state 반복 처리량으로 해석하지 않는다.'
    print('SYNTHSEG_TIMING',json.dumps(events,ensure_ascii=False),flush=True)
