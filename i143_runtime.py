"""새 결과의 원자적 배타 저장과 생성 provenance 검사."""
import json
import os
import time
from pathlib import Path
from i141_common import digest,sha


def save(path,obj):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists(): raise FileExistsError(path)
    temp=path.with_name(path.name+f'.{os.getpid()}.{time.time_ns()}.partial')
    with temp.open('x') as f:
        json.dump(obj,f,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)
        f.write('\n'); f.flush(); os.fsync(f.fileno())
    # link는 이미 완료된 결과를 덮어쓰지 않는다. partial은 출처와 함께 보존한다.
    os.link(temp,path)


def validate_record(record,row,condition,epoch,provenance):
    assert record['condition']==condition and record['epoch']==epoch
    assert record['patient_id']==row['patient_id']
    assert record.get('image_source_patient',row['patient_id'])==row.get('image_source_patient',row['patient_id'])
    assert record['provenance']==provenance
    assert record['digest']==digest({k:v for k,v in record.items() if k!='digest'})
    assert record['input_hashes']==[im['sha256'] for im in row['images']]
    for im in row['images']: assert sha(im['path'])==im['sha256']
    assert record['n_tokens']==len(record['tokens']) and len(record['tokens'])>0
    return True
