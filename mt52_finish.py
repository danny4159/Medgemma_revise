"""자료 gate 실패 종료를 원시 실행·검증 근거와 연결한다. 연구 성공 판정 아님."""
import json
from mt52_prepare import ROOT,OUT,save,sha256_file

def main():
    paths=['audit/data_gate.json','provenance/all_image_returns_v2.json','provenance/iter051_return_links_v2.json',
        'tests/data_verify_final.json','tests/input_tensor_final.json','tests/final_fixtures.json',
        'tests/resume_current_result.json','tests/revalidation/tests/data_fixtures.json',
        'eval/source_lock.json','eval/D24_report.json','eval/D24_independent_verify.json','pilot/throughput.json',
        'tests/protocol_final.json','usage_ledger.json','provenance/old_pilot_source_verify.json']
    objs={p:json.loads((OUT/p).read_text()) for p in paths}
    gate=objs['audit/data_gate.json'];assert gate['run_E'] is False and gate['E_available']==263
    prior=objs['provenance/iter051_return_links_v2.json']
    assert prior['status']=='PASS' and len(prior['cases'])==254 and not prior['missing']
    assert len(prior['other_image_returns'])==13 and sha256_file(ROOT/prior['rollout'])==prior['rollout_sha256']
    for p,h in gate['source_digests'].items():assert sha256_file(ROOT/p)==h
    for p in ['tests/data_verify_final.json','tests/input_tensor_final.json','tests/final_fixtures.json',
              'tests/resume_current_result.json','tests/revalidation/tests/data_fixtures.json','eval/D24_independent_verify.json','tests/protocol_final.json']:
        assert objs[p]['status']=='PASS'
    for p,h in objs['eval/source_lock.json']['files'].items():assert sha256_file(ROOT/p)==h
    report=objs['eval/D24_report.json'];verifier=objs['eval/D24_independent_verify.json']
    assert verifier['report_sha256']==sha256_file(OUT/'eval/D24_report.json')
    assert verifier['verifier_sha256']==sha256_file(ROOT/'mt52_d_verify.py')
    assert verifier['raw_digests']==report['integrity']['raw_digests']
    for p,h in verifier['raw_digests'].items():assert sha256_file(ROOT/p)==h
    job=OUT/'pilot/D24_caps2';completions=list(job.glob('attempts/*/completion.json'));assert len(completions)==1
    complete=json.loads(completions[0].read_text());assert complete['exit_codes']==[0,0] and complete['n']==296
    assert complete['records']==verifier['raw_digests']
    sources=sorted(ROOT.glob('mt52*.py'))+sorted(ROOT.glob('test_mt52*.py'))
    files=[OUT/p for p in paths]+sources+completions+[job/'protocol.json']
    save(OUT/'completion.json',{'artifact_bundle_sealed':True,'iteration_outcome':'data_gate_failed',
        'valid_experiment':False,'self_check':'FAIL','E_run':False,'D_requests':296,
        'D_non_EOS':len(report['integrity']['non_eos']),'E_available':263,'E_required':280,
        'files':{str(p.relative_to(ROOT)):sha256_file(p) for p in files},
        'raw_digests':verifier['raw_digests'],
        'limitations':['No E hypothesis test','D non-EOS remains after F/U cap doubling',
            'Final-stage doubling not pursued after definitive data gate failure; no E technical gate approval',
            'Agent audit is not clinical gold adjudication','Interrupted generation costs only bounded from below']})
    print('SEALED gate failure, SELF_CHECK FAIL')

if __name__=='__main__':main()
