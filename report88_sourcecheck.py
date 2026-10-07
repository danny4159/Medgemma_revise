"""잠금 후 변경·공개 checkpoint 노출·수동 회귀의 한정 파일 확인."""
import hashlib
import ast
import json
import re
from pathlib import Path
from report86_common import ROOT, R86, sha
from report88_handoff import OUT, OLD, write_new


def main():
    h=json.loads((OUT/'handoff.json').read_text())
    txt=None; states=[]; events=[]
    # 셸을 재실행하지 않는다. 로그의 상수 문자열/replace만 AST로 읽어 메모리에서 재구성.
    for lineno,line in enumerate((ROOT.parent/'agent/runs/iter_087/claude_stream.jsonl').open(),1):
        try: obj=json.loads(line)
        except json.JSONDecodeError: continue
        msg=obj.get('message',{}) if isinstance(obj,dict) else {}
        cs=msg.get('content',[]) if isinstance(msg,dict) else []
        if not isinstance(cs,list): continue
        for c in cs:
            if not isinstance(c,dict) or c.get('type')!='tool_use':continue
            name=c.get('name'); z=c.get('input',{})
            path=z.get('file_path','')
            before=txt
            if path.endswith('/report87_eval.py'):
                if name=='Write':txt=z['content']
                elif name=='Edit':txt=txt.replace(z['old_string'],z['new_string'],1)
            if name=='Bash' and 'report87_eval.py' in z.get('command',''):
                cmd=z['command']; env={}
                for chunk in re.findall(r"<<'EOF'\n(.*?)\nEOF",cmd,re.S):
                    try: tree=ast.parse(chunk)
                    except SyntaxError:continue
                    for node in tree.body:
                        if isinstance(node,ast.Assign) and len(node.targets)==1 and isinstance(node.targets[0],ast.Name):
                            key=node.targets[0].id; val=node.value
                            if key=='s' and isinstance(val,ast.Call) and isinstance(val.func,ast.Attribute) and val.func.attr=='read':
                                env['s']=txt if str(env.get('p','')).endswith('report87_eval.py') else None
                            elif key=='s' and isinstance(val,ast.Call) and isinstance(val.func,ast.Attribute) and val.func.attr=='replace' and env.get('s') is not None:
                                args=[env[a.id] if isinstance(a,ast.Name) else ast.literal_eval(a) for a in val.args]
                                env['s']=env['s'].replace(*args)
                            else:
                                try:env[key]=ast.literal_eval(val)
                                except (ValueError,TypeError):pass
                        elif isinstance(node,ast.Expr) and isinstance(node.value,ast.Call) and isinstance(node.value.func,ast.Attribute) and node.value.func.attr=='write':
                            if str(env.get('p','')).endswith('report87_eval.py') and env.get('s') is not None: txt=env['s']
            if txt is not None and txt!=before:
                states.append(hashlib.sha256(txt.encode()).hexdigest());events.append({'line':lineno,'tool':name,'sha256':states[-1]})
    lock=json.loads((OLD/'protocol_lock.json').read_text())
    assert lock['files']['report87_eval.py'] in states
    assert txt==(ROOT/'report87_eval.py').read_text()
    write_new(OUT/'checks/protocol_history.json',{'passed':True,'states':states,'events':events,'locked_state_index':states.index(lock['files']['report87_eval.py']),
      'current_sha256':sha(ROOT/'report87_eval.py'),'source_stream_sha256':h['preserved']['agent/runs/iter_087/claude_stream.jsonl'],
      'note':'Write/Edit뿐 아니라 Bash의 문자열 변경까지 읽어 재구성. 오류 묶음 수집·loc_req 없는 비교 제외·co-evidence 검사 추가가 잠금 뒤 변경이다. 집계 산식 변경은 없음. amendment02의 별도 과거 lock 부재는 유지; 현재 handoff에서 봉인.'})
    src=ROOT/'results/iter_085/official/source'
    manifest=json.loads((src.parent/'source_manifest.json').read_text())
    used=['README.md','configs/training/multi_task_medgemma-4b-it_v12_custom_eval_500_steps_curriculum_1500_steps_with_augmentation.yaml',
      'vlm_research_kit/data/datasets/padchest_dataset.py','scripts/train_medgemma.py','vlm_research_kit/checkpointing.py']
    # 원 manifest 형식은 경로->sha256.
    verified={}
    for p in used:
        v=manifest['files'][p]
        expected=v['sha256'] if isinstance(v,dict) else v
        verified[p]=sha(src/p)==expected
    assert all(verified.values())
    snap=ROOT/'results/iter_085/models/models--pamessina--medgemma-4b-it-cure/snapshots/4bb5dc5a5025a854d1f25e475769949915b08b44'
    cfg=json.loads((snap/'adapter_config.json').read_text())
    assert cfg['base_model_name_or_path']=='google/medgemma-4b-it'
    exposure=json.loads((R86/'exposure_check_final.json').read_text())
    write_new(OUT/'checks/exposure.json',{'official_source':manifest['url'],'source_verified':verified,
      'adapter_revision':snap.name,'adapter_base':cfg['base_model_name_or_path'],'license':'health-ai-developer-foundations',
      'evidence':[
        '공식 README와 adapter card는 validation 성능 기반 dataset/class/region sampling curriculum을 명시한다.',
        '공개 v12 예시 config는 PadChest-GR train/validation을 분리하지만 validation 80 GRG/100 PG 표본으로 custom 평가하고 1500-step sampling 재가중 및 best-metric checkpoint 관리를 설정한다.',
        '따라서 validation은 gradient 학습과 분리돼도 선택/curriculum 노출이 가능한 개발 자료다.',
        'adapter card/config에 이 공개 가중치의 정확한 학습 config/환자별 curriculum·checkpoint 선택 로그 연결은 없다. v12가 해당 가중치의 정확한 recipe라고 단정하지 않는다.',
        'E96 개별 영상의 학습/선택 노출 여부는 미확정. 문자열 일치만으로 암기/누수 확정 불가. C-H의 PadChest 확장 실패는 논문 공식 MIMIC 평가 재현 실패가 아니다.'
      ],'prior_exact_match_summary':{k:v.get('summary',{}) for k,v in exposure.items()},
      'files':{str(p):sha(p) for p in [src.parent/'source_manifest.json',snap/'README.md',snap/'adapter_config.json',R86/'exposure_check_final.json',*[src/p for p in used]]}})
    man=ROOT/'results/manual_rsna_report_transfer_20261006'
    prot=json.loads((man/'protocol.json').read_text());byid={r['id']:r for r in prot['rows']}; rr={}
    for model in ('base','sft'):
        saved=json.loads((R86/f'manual_regress/{model}_result.json').read_text())
        assert saved['orig_file_sha256']==sha(man/f'{model}.jsonl')
        assert saved['protocol_sha256']==sha(man/'protocol.json')
        old={r['id']:r for r in map(json.loads,(man/f'{model}.jsonl').read_text().splitlines())}
        checks=[]
        for it in saved['items']:
            row=byid[it['id']]
            assert sha(row['image'])==row['file_sha256']
            assert len(old[it['id']]['suffix_ids'])==it['n_new_old']
            checks.append({'id':it['id'],'image_sha256':row['file_sha256'],'input_ids_equal_saved':it['input_ids_equal'],
              'tokens_equal_saved':it['tokens_equal'],'old_tokens':it['n_new_old'],'new_tokens':it['n_new_new']})
        rr[model]={'items':checks,'n_equal':sum(x['tokens_equal_saved'] for x in checks),'n':len(checks)}
    write_new(OUT/'checks/manual_regression.json',{'source_checks_passed':True,'results':rr,
      'diagnosis':'base/SFT의 같은 두 입력에서 각각6/8 suffix 일치. input_ids8/8, 원 영상파일 hash 일치. 과거 pixel_values tensor·새 suffix 배열/원시 logits가 보존되지 않아 최초 token 차이와 tensor 동등성/원인을 증명할 수 없음.',
      'scope':'원 RSNA 수동 관찰 provenance 한계. 별도 입력/출력 검증된 E96의 의미 재평가와 구분. 새 모델 호출 없음.',
      'files':{str(p):sha(p) for p in [man/'protocol.json',man/'base.jsonl',man/'sft.jsonl',R86/'manual_regress/base_result.json',R86/'manual_regress/sft_result.json',R86/'manual_regress/diff_diagnosis_env.json',ROOT/'report86_manual_regress.py']}})
    print('protocol history, source exposure, manual provenance checks complete')


if __name__=='__main__':main()
