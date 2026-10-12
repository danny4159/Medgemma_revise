"""공식 FreeSurfer unet의 모든 학습 weight가 공식 HDF5 값과 일치하는지 검사한다."""
import hashlib
import json
import os
from pathlib import Path
import runpy
import time

os.environ['TF_USE_LEGACY_KERAS']='1'
import h5py
import numpy as np
import tensorflow as tf


def sha(p):
    h=hashlib.sha256()
    with open(p,'rb') as f:
        for b in iter(lambda:f.read(4<<20),b''):h.update(b)
    return h.hexdigest()


def main():
    root=Path('/home/test/.local/share/medgemma/mr_rate/iter127/freesurfer')
    script=root/'mri_synthseg.py'
    official=runpy.run_path(str(script),run_name='official_module_for_weight_audit')
    labs=np.unique(np.load(root/'models/synthseg_segmentation_labels_2.0.npy'))
    tf.random.set_seed(125); np.random.seed(125)
    # 데이터 추론을 CPU로 대체하지 않는다. weight 연결만 CPU에서 확인한다.
    with tf.device('/CPU:0'):
        net=official['unet'](input_shape=[None,None,None,1],nb_labels=len(labs),nb_levels=5,
                 nb_conv_per_level=2,conv_size=3,nb_features=24,feat_mult=2,activation='elu',batch_norm=-1,name='unet')
        file=root/'models/synthseg_2.0.h5'
        net.load_weights(str(file),by_name=True)
    records=[]
    with h5py.File(file,'r') as f:
        for layer in net.layers:
            actual=layer.get_weights()
            if not actual:continue
            assert layer.name in f, ('HDF5 layer missing',layer.name)
            names=f[layer.name].attrs['weight_names']
            names=[n.decode() if isinstance(n,bytes) else n for n in names]
            expected=[np.asarray(f[layer.name][n]) for n in names]
            assert len(actual)==len(expected)
            equal=all(np.array_equal(a,e) for a,e in zip(actual,expected))
            records.append(dict(layer=layer.name,weight_arrays=len(actual),parameters=sum(a.size for a in actual),equal=equal))
    assert records and all(r['equal'] for r in records)
    result=dict(all_pass=True,layers=records,weighted_layers=len(records),weight_arrays=sum(r['weight_arrays'] for r in records),
        parameters=sum(r['parameters'] for r in records),hdf5_sha256=sha(file),official_source_sha256=sha(script),
        tensorflow=tf.__version__,seed=125,source_sha256=sha(__file__),
        created_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),
        scope_ko='공식 FreeSurfer segmentation unet의 모든 학습 weight HDF5 대조. QC 모델·임상 정답·출력 적합성을 인증하지 않음.')
    with Path('results/iter_127/seg/weight_check.json').open('x') as f:json.dump(result,f,ensure_ascii=False,indent=2)
    print('weight_check',len(records),'layers',result['weight_arrays'],'arrays',result['parameters'],'parameters')


if __name__=='__main__':main()
