"""공식 CLI 실행 전 GPU growth 설정만 적용한다. source/model 연산은 수정하지 않는다."""
import json
import os
from pathlib import Path
import runpy
import sys
import tensorflow as tf

gpus=tf.config.list_physical_devices('GPU')
if len(gpus)!=1:
    raise RuntimeError(f'허용된 단일 GPU가 필요함: {gpus}')
limit=int(os.environ.get('SYNTHSEG_GPU_LIMIT_MIB','20000'))
tf.config.set_logical_device_configuration(gpus[0],[tf.config.LogicalDeviceConfiguration(memory_limit=limit)])
print('GPU_ENVIRONMENT',json.dumps(dict(python=sys.executable,tensorflow=tf.__version__,
    visible=os.environ.get('CUDA_VISIBLE_DEVICES'),memory_limit_mib=limit,gpus=[str(g) for g in gpus]),ensure_ascii=False),flush=True)
script=sys.argv[1]
sys.argv=sys.argv[1:]
runpy.run_path(script,run_name='__main__')
