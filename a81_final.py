"""실제 출력·독립 계산·잠금 근거를 마지막으로 봉인한다."""
from pathlib import Path
import os
import numpy as np
import a81_common as C
import a81_run as R


def finish():
    files={}; stages={}; supplement={}
    os.environ['HF_HUB_OFFLINE']='1'
    os.environ.setdefault('HF_HOME','/SSD1_1TB/home/milab/daniel/08_medgemma/hf_cache')
    from transformers import AutoTokenizer
    tok=AutoTokenizer.from_pretrained('google/medgemma-1.5-4b-it',revision=C.CONFIG['model_revision'],local_files_only=True)
    for split in ('V8','E24'):
        proto=C.ROOT/f'protocol_{split}.json'; out=C.ROOT/f'gen/{split}'
        done=R.verify(proto,out)
        report_path=C.ROOT/f'eval/{split}.json'; verify_path=C.ROOT/f'eval/{split}_independent.json'
        report=C.read(report_path); ver=C.read(verify_path)
        assert ver['passed'] and ver['report_sha256']==C.sha(report_path)
        assert report['provenance']['protocol_sha256']==C.sha(proto)
        assert report['provenance']['baseline_sha256']==C.sha(C.ROOT/f'data/baseline_{split}.json')
        assert report['provenance']['selection_sha256']==C.sha(C.ROOT/'selection.json')
        completions=list(out.glob('completion_*.json')); assert len(completions)==1
        complete=C.read(completions[0]); assert complete['passed'] and complete['n']==len(done)
        assert complete['protocol_digest']==C.digest(C.read(proto))
        C.check_hashes(complete['files']); files.update(complete['files'])
        assert C.sha(complete['launch_file'])==complete['launch_sha256']
        launch=C.read(complete['launch_file']); assert not any(launch['exit_codes'])
        assert launch['workers']==C.read(C.ROOT/'resource_decision.json')['workers']
        for rec in done.values():
            env=C.read(rec['env_path'])['env']; eos=env['eos_token_id']; eos=eos if isinstance(eos,list) else [eos]
            assert rec['ended_eos']==bool(rec['suffix_ids'] and rec['suffix_ids'][-1] in eos)
            assert rec['text']==tok.decode(rec['suffix_ids'],skip_special_tokens=True)
            assert rec['raw']==tok.decode(rec['suffix_ids'],skip_special_tokens=False)
            assert len(rec['suffix_ids'])<=32
            assert C.sha(rec['env_path'])==rec['env_digest']
        n=len(done)
        stages[split]={'requests':n,'eos':sum(r['ended_eos'] for r in done.values()),
                       'valid':sum(r['parse_valid'] for r in done.values()),
                       'tokens':sum(r['n_new'] for r in done.values()),'launcher_wall_s':launch['wall_s'],
                       'req_per_min_including_load':n/launch['wall_s']*60,'peak_used_mib':launch['peak_used_mib'],
                       'generation_sum_s':sum(r['runtime_s'] for r in done.values()),
                       'p95_generation_s':float(np.percentile([r['runtime_s'] for r in done.values()],95)),
                       'max_new_tokens_observed':max(r['n_new'] for r in done.values()),'exit_codes':launch['exit_codes']}
        rows=C.read(C.ROOT/f'data/baseline_{split}.json')
        # 원 계획에 명시된 Q/C 최소오차 oracle: 실용 비교군으로 선택하지 않는다.
        ee=np.array([min(4 if r['Q'] is None else abs(r['Q']-r['grade']),abs(r['C']-r['grade'])) for r in rows])
        yy=np.array([r['grade'] for r in rows])
        supplement[split]={'posthoc_Q_C_oracle_class_std_mae':float(np.mean([ee[yy==g].mean() for g in sorted(set(yy))])),
                            'C_correct_n':sum(r['C']==r['grade'] for r in rows),
                            'note':'정답으로 선택한 사후 진단 상한; 실제 방법이나 독립 확인 아님.'}
        for p in [proto,report_path,verify_path,completions[0],Path(complete['launch_file']),C.ROOT/f'{split}_host_resources.json']:
            files[str(p)]=C.sha(p)
    for p in C.code_files()+[str(C.ROOT/'selection.json'),str(C.ROOT/'tests/technical_gate.json'),str(C.ROOT/'data/source_audit.json')]:
        files[p]=C.sha(p)
    C.save(C.ROOT/'completion.json',{'passed':True,'backend':'codex','stages':stages,'supplement':supplement,'files':files,
                                    'cost_scope':'신규 213 호출의 launcher wall은 적재부터 자식 종료까지. Q/C cached; 온라인 C/Q 전체 비용과 비교하지 않음.',
                                    'independent_confirmation':False})
    print(stages)


if __name__=='__main__': finish()
