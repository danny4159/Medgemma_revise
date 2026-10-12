"""이번 경로의 필수 정상/오류·실제 GPU 재개 검사. 결과는 iter129에만 저장."""
import argparse
import ast
import copy
import json
from pathlib import Path
import shutil
import time
import uuid
import numpy as np
import mr123_data as D
import mr128_gen as G
from mr128_data import read,save,sha,verify_files
from mr129_eval import decide,metrics,states

OUT=Path('results/iter_129');G.OUT=OUT


def cpu():
    checks={}
    def check(name,ok):
        checks[name]=bool(ok)
        if not ok:raise AssertionError(name)
    def rejects(name,fn):
        try:fn()
        except (ValueError,KeyError):check(name,True);return
        check(name,False)
    a=np.arange(24,dtype=np.float32).reshape(2,3,4);b=a>12
    check('minmax_ignores_mask',D.normalization_window(a,b,'volume_minmax')==(0.,23.))
    check('P_default_preserved',D.normalization_window(a,b)==D.intensity_window(a,b))
    rejects('constant_rejected',lambda:D.normalization_window(np.ones((2,2,2)),normalization='volume_minmax'))
    bad=a.copy();bad[0,0,0]=np.nan
    rejects('nonfinite_rejected',lambda:D.normalization_window(bad,normalization='volume_minmax'))
    rejects('unknown_normalization',lambda:D.normalization_window(a,b,'unknown'))
    check('uncertain_invalid_denominators',metrics([0,0,1,1],['UNCERTAIN','INVALID','PRESENT','ABSENT'])['BA']==.25)
    check('refusal_distinct',states('I cannot interpret this.',True)==('INVALID','refusal'))
    check('non_eos_invalid',states('PRESENT',False)==('INVALID','truncated'))
    check('strict',states('PRESENT\nBrief.',True)==('PRESENT','ok_strict'))
    check('loose',states('PRESENT - likely.',True)==('PRESENT','ok_loose'))
    def dec(ba,gap,ci,sens=.8,spec=.8):
        from fractions import Fraction
        f=Fraction(str(gap));return decide({},dict(BA=ba,sensitivity=sens,specificity=spec),dict(mean_fraction=[f.numerator,f.denominator],CI95=ci))['outcome']
    check('positive_boundary',dec(.75,.15,[.001,.30],.65,.65)=='positive')
    check('zero_CI_lower_inconclusive',dec(.75,.15,[0,.30])=='inconclusive')
    check('negative_boundary',dec(.60,.1,[-.05,.149])=='negative')
    check('negative_strict_upper',dec(.60,.1,[-.05,.15])=='inconclusive')
    check('uniform_ABSENT_not_positive',dec(.5,0,[0,0],0,1)=='negative')
    root=OUT/'cpu_fixtures';root.mkdir(parents=True,exist_ok=True)
    for name,data,repair,valid in [('middle','{"id":"a"}\nBROKEN\n{"id":"b"}\n',True,False),
        ('terminated_bad','{"id":"a"}\nBROKEN\n',True,False),('nan','{"id":"a","value":NaN}\n',True,False),
        ('duplicate_key','{"id":"a","id":"b"}\n',True,False),
        ('duplicate_id','{"id":"a"}\n{"id":"a"}\n',False,False),('tail','{"id":"a"}\n{"id":',True,True)]:
        p=root/(name+'.'+uuid.uuid4().hex+'.jsonl');p.write_text(data)
        if valid:check(name,len(G.jsonl(p,repair))==1 and len(list(root.glob(p.name+'.torn.*')))==1)
        else:rejects(name,lambda p=p,repair=repair:G.jsonl(p,repair))
    # 허용 import 의존성은 읽기 함수만 사용하며 import 시 실행 entrypoint가 없다.
    for source in ['mr127_seg.py','mr127_select.py','mr127_assets.py','mr125_select.py']:
        tree=ast.parse(Path(source).read_text())
        calls=[]
        for node in tree.body:
            if isinstance(node,ast.Expr) and isinstance(node.value,ast.Call):calls.append(ast.unparse(node))
        check(source+'_no_import_entrypoint',not calls)
    save(OUT/'cpu_tests.json',dict(passed=True,count=len(checks),checks=checks))
    print('CPU required checks',len(checks),'PASS',flush=True)


def runtime():
    from mr129_control import run,verified,verify_lock
    verify_lock();reg=read(OUT/'technical_regression.json');choice=read(OUT/'throughput_selection.json')
    workers=4 if choice['compare_four_workers'] else 2
    stage='runtime';req_file=OUT/'tech_requests.json';peak=10000
    rc=run(stage,req_file,pause=4,workers=workers,peak=peak,max_new=reg['max_new'])
    if rc!=75:raise ValueError('actual partial pause did not happen')
    req,partial=G.verify(OUT/'gen'/stage)
    if not 0<len(partial)<16:raise ValueError('partial size')
    prefix={p.name:p.read_bytes() for p in (OUT/'gen'/stage).glob('worker*.jsonl')}
    # 실제 재개 진입에서 max_new 변경이 새 child 없이 거부되어야 한다.
    before=len(list((OUT/'gen'/stage).glob('*.launch.json')))
    try:run(stage,req_file,workers=workers,peak=peak,max_new=1024 if reg['max_new']==512 else 512)
    except ValueError as e:change_error=str(e)
    else:raise AssertionError('config change accepted')
    if len(list((OUT/'gen'/stage).glob('*.launch.json')))!=before:raise AssertionError('child started on config mismatch')
    victim=next((OUT/'gen'/stage).glob('worker*.jsonl'))
    with victim.open('ab') as f:f.write(b'{"id":')
    if run(stage,req_file,workers=workers,peak=peak,max_new=reg['max_new'])!=0:raise ValueError('runtime resume failed')
    _,rows=verified(stage);_,reference=verified(reg['stage']);byid={r['id']:r for r in reference}
    check_tokens=all(r['tokens']==byid[r['id']]['tokens'] for r in rows)
    check_inputs=all(r['input_ids_sha256']==byid[r['id']]['input_ids_sha256'] and
        r['pixel_values_sha256']==byid[r['id']]['pixel_values_sha256'] for r in rows)
    check_prefix=all((OUT/'gen'/stage/name).read_bytes().startswith(data) for name,data in prefix.items())
    c_hash=sha(OUT/'gen'/stage/'completion.json')
    if run(stage,req_file,workers=workers,peak=peak,max_new=reg['max_new'])!=0:raise ValueError('complete reverify')
    if sha(OUT/'gen'/stage/'completion.json')!=c_hash:raise ValueError('completed result changed')
    tests={'partial_real_run':True,'partial_output_prefix_preserved':check_prefix,'torn_tail_backup':bool(list((OUT/'gen'/stage).glob('*.torn.*'))),
           'resume_tokens_equal':check_tokens,'resume_tensor_hashes_equal':check_inputs,'complete_reverify_unchanged':True,'config_change_rejected':True}
    # 검증 entrypoint에 실제 duplicate/missing record를 넣는다. 원 산출물은 수정하지 않는다.
    base=OUT/'runtime_fixtures';base.mkdir(parents=True,exist_ok=True)
    for name in ['duplicate','missing','tampered','wrong_worker']:
        dst=base/name;dst.mkdir(exist_ok=True)
        shutil.copyfile(OUT/'gen'/stage/'config.json',dst/'config.json')
        for wid in range(workers):shutil.copyfile(OUT/'gen'/stage/f'worker{wid}.jsonl',dst/f'worker{wid}.jsonl')
        p=dst/'worker0.jsonl';lines=p.read_bytes().splitlines(keepends=True)
        if name=='duplicate':p.write_bytes(b''.join(lines+[lines[0]]))
        elif name=='missing':p.write_bytes(b''.join(lines[1:]))
        elif name=='tampered':
            row=json.loads(lines[0]);row['text']='ABSENT';lines[0]=(json.dumps(row)+'\n').encode();p.write_bytes(b''.join(lines))
        else:
            other=dst/'worker1.jsonl';other.write_bytes(other.read_bytes()+lines[0]);p.write_bytes(b''.join(lines[1:]))
        try:
            expected,rr=G.verify(dst)
            if len(rr)!=len(expected):raise ValueError('missing outputs rejected')
        except ValueError as e:tests[name+'_rejected']=True
        else:raise AssertionError(name+' accepted')
    if not all(tests.values()):raise AssertionError(tests)
    results=[read(p) for p in (OUT/'gen'/stage).glob('*.result.json')]
    total_wall=sum(r['wall_s'] for r in results);peak_total={g:max(r['peak_gpu_total_mib'][g] for r in results) for g in ['0','1']}
    save(OUT/'runtime_checks.json',dict(passed=True,checks=tests,workers=workers,partial_count=len(partial),
        config_change_error=change_error,total_wall_s=total_wall,requests_per_minute=960/total_wall,
        GPU_peak_mib=peak_total,comparison_includes_restart_overhead=True))
    if workers==4:
        # 재개 비용을 포함한 보수적인 전체16건 처리량 비교. 불리한 비용을 숨기지 않는다.
        select_four=total_wall<choice['technical_wall_s'] and check_tokens and all(v+4*1024<=24576 for v in peak_total.values())
        new=dict(choice,workers=4 if select_four else 2,four_worker_wall_including_resume_s=total_wall,
                 four_worker_tokens_same=check_tokens,
                 reason_ko='기술16건의 재개 포함 전체 wall 비교와 정합성·메모리 여유로 선택. 중단 페널티가 있어 단독 steady-state 우열은 미확정.')
        save(OUT/'throughput_selection_final.json',new)
    else:save(OUT/'throughput_selection_final.json',choice)
    verify_files(read(OUT/'preservation_before.json'))
    print('RUNTIME required checks PASS',tests,'workers',workers,'wall',total_wall,flush=True)


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('action',choices=['cpu','runtime']);a=ap.parse_args()
    (cpu if a.action=='cpu' else runtime)()
