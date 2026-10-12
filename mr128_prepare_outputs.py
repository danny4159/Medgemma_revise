"""감독 프로그램이 완료한 volume만 순차적으로 원격자 변환·렌더. 모델 polling 없음."""
import argparse
import fcntl
from pathlib import Path
import time
import nibabel as nib
import numpy as np
import psutil
import mr123_data as D
from mr128_data import OUT,ROOT,read,save,sha,verify_files,utc
from mr128_build import build


def fallback(study,inputs,failure):
    t0=time.monotonic();c=inputs['inputs'][study]
    verify_files({v['path']:v['sha256'] for v in c['files'].values()})
    a,b,info=D.load_case(c['files']['img.nii.gz']['path'],c['files']['brain.nii.gz']['path'])
    U=D.pick(*D.brain_range(b),0.05,0.95)
    if U!=c['U_idx'] or len(set(U))!=8:raise ValueError('fallback U changed')
    lo,hi=D.intensity_window(a,b);pngs={};directory=ROOT/'png/remaining'/study;directory.mkdir(parents=True,exist_ok=True)
    for k in U:
        p=directory/f's{k:03d}.png'
        if not p.exists():D.render_slice(a,k,lo,hi,info['canon_zooms']).save(p)
        pngs[str(k)]=dict(path=str(p),sha256=sha(p))
    result=dict(study_uid=study,series_id=c['key']['series_id'],U_idx=U,A_idx=U,A_range=None,
         A_fallback='official_segmentation_failed',S=None,vent_mm3=None,icv_mm3=None,
         window_p1_p99=[lo,hi],pngs=pngs,source_input=c,seg_failure=failure,
         canonical_shape=list(a.shape),nn_mismatches=None,overlay=None,overlay_sha256=None,
         warm_read_to_saved_s=time.monotonic()-t0,code_sha256=sha(__file__))
    save(OUT/'build/remaining'/(study+'.json'),result)
    return result


def main(pid):
    inputs=read(OUT/'remaining_inputs.json');expected=set(inputs['inputs']);done=set()
    with (OUT/'prepare_outputs.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        while done!=expected:
            for study in sorted(expected-done):
                output=OUT/'build/remaining'/(study+'.json')
                complete=OUT/'seg/remaining'/(study+'.complete.json');failed=OUT/'seg/remaining'/(study+'.failure.json')
                if output.exists():
                    r=read(output);verify_files({v['path']:v['sha256'] for v in r['pngs'].values()});done.add(study);continue
                if psutil.virtual_memory().available<4*1024**3:break
                if complete.exists():build(study,inputs,read(complete),'remaining');done.add(study)
                elif failed.exists():fallback(study,inputs,read(failed));done.add(study)
            alive=psutil.pid_exists(pid) and psutil.Process(pid).status()!=psutil.STATUS_ZOMBIE
            if done==expected:break
            if not alive:
                missing=sorted(expected-done)
                save(OUT/'prepare_outputs_incomplete.json',dict(missing=missing,done=sorted(done),created_utc=utc()))
                print('prepare incomplete',missing,flush=True);return 2
            time.sleep(15)
        paths={str(OUT/'build/remaining'/(s+'.json')):sha(OUT/'build/remaining'/(s+'.json')) for s in sorted(done)}
        save(OUT/'prepare_outputs_complete.json',dict(created_utc=utc(),builds=paths,expected=52,complete=len(done)==52,
             source_sha256=sha(__file__),remaining_inputs_sha256=sha(OUT/'remaining_inputs.json')))
        print('remaining builds complete52',flush=True);return 0


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--pid',type=int,required=True);a=ap.parse_args();raise SystemExit(main(a.pid))
