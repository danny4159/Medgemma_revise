"""완료 근거와 불확실성을 함께 보존. 연구 성공 판정은 독립 리뷰에 맡긴다."""
import datetime
import json
import os
import sys
from pathlib import Path
from report86_common import ROOT, R86, sha
from report88_handoff import OUT, write_new
from report88_eval import load_final


def verified(path):
    obj=json.loads(path.read_text());assert obj['passed'],path
    for p,h in obj.get('files',{}).items():assert sha(p)==h,p
    return obj


def main():
    h=json.loads((OUT/'handoff.json').read_text())
    for p,d in h['preserved'].items():assert sha(ROOT.parent/p)==d,p
    src=json.loads((ROOT/'results/iter_087/source_manifest.json').read_text())
    for group in ('inputs','plans'):
        for entry in src[group].values():assert sha(ROOT.parent/entry['path'])==entry['sha256']
    lock=json.loads((OUT/'eval_lock.json').read_text())
    for p,d in lock['files'].items():assert sha(p)==d
    independent=verified(OUT/'verify/independent.json');sv=verified(OUT/'verify/sensitivity.json')
    tests=verified(OUT/'tests/path_tests_v2.json')
    assert tests['source_sha256']==sha(ROOT/'test_report88.py')
    history=verified(OUT/'checks/protocol_history.json')
    rows,reads,amend,v1,initial,j=load_final()
    r=json.loads((OUT/'eval/report.json').read_text());old=json.loads((R86/'E96/eval_v2/report.json').read_text())
    original=json.loads((R86/'E96/eval/report.json').read_text())
    table={}
    for c in r['summary']['all']['conditions']:
        a=r['summary']['all']['conditions'][c];b=old['summary']['all']['conditions'][c]
        table[c]={'original_iter086':original['summary']['all']['conditions'][c], 'corrected_iter086':b,'iter088':a,
          'definitions':'recall v1/v2 분모72/73. old strict는 위치만 부분 반영, new strict는 명시 위치·속성 완전 일치. common 모순55명, extended56명. 다른 정의를 동일 지표로 취급하지 않음.'}
    write_new(OUT/'comparison_table.json',table)
    family=[]
    for pi,row in enumerate(rows):
        img=row['ImageID']
        for f in amend[img]['facts']:
            txt=f['sentence_en'].lower()
            if any(t in txt for t in ('granuloma','air trapping','prosthes','blunting','fracture','scoliosis','kyphosis')):
                entries={c:o['facts'].get(f['fact_id']) for c,o in j[img].items()}
                family.append({'patient':f'P{pi:03}','reference':f,'states':entries})
                if 'calcified granuloma' in txt or 'air trapping' in txt:
                    assert all(v['s']=='U' for v in entries.values())
    write_new(OUT/'adjudication/family_audit.json',{'facts':family,
      'reviewed_rules':['A2 air trapping','A7 calcified granuloma','N범위 비대칭: no effusion 대 blunting','방사선불투과 이물과 유방 보형물','정상 심장 크기 대 intracardiac mass'],
      'finding':'A2/A7은 앞선 모든 대상에서 U 일관. 같은 심방 종괴 i 오류7개 및 범위 오류는 changes.json으로 연결. 전체 판정을 전문가가 전수 확인했다는 의미 아님.',
      'notes':'generic/접속 목록 precision 단순화 및 모호 개념은 sensitivity_spec에서 범위를 고정. 극단적 C-H_explicit_region_only는 모든 C-H 충돌을 인위 제거한 stress bound여서 실제 대안 의미 판정이나 투자 근거로 사용하지 않음.'})
    parts=sorted(OUT.glob('part_P*.txt'))
    initial_done=(OUT/'structural_initial.json').stat().st_mtime
    first=parts[0].stat().st_mtime;last=parts[-1].stat().st_mtime
    start=datetime.datetime.fromisoformat(h['time_utc']).timestamp()
    now=datetime.datetime.now(datetime.timezone.utc)
    execution={'python':sys.executable,'cuda_visible_devices':os.environ.get('CUDA_VISIBLE_DEVICES'),
      'new_gpu_requests':0,'new_training_steps':0,'new_model_loads':0,'new_packages':0,
      'reason_cpu_only':'계획된 작업은 저장 출력 의미 평가와 산술 검증. 새 GPU 생성으로 이 평가 결함을 해결할 수 없으며 계획이 새 생성을 금지.',
      'timing':{'handoff_time_utc':h['time_utc'],'now_utc':now.isoformat(),'handoff_to_first_saved_pair_s':first-start,
        'first_to_last_pair_s':last-first,'nine_later_pairs_outputs':144,'observed_later_annotation_outputs_per_min':144/((last-first)/60),
        'from_initial_structural_check_to_now_s':now.timestamp()-initial_done,'handoff_to_now_s':now.timestamp()-start,
        'boundary':'파일 mtime 차이의 경과시간. 읽기·판정·전사·검사·컨텍스트 비용 포함; 순수 인적 작업시간/CPU compute시간 아님.',
        'planning_limitation':'첫 묶음 기반 완료 예상은 실행 전에 별도 파일로 고정하지 못함. 사후 예상치를 만들지 않음.'},
      'recoveries':['handoff stream의 비JSON행을 별도 기록 후 출처 검사 통과.',
        '독립 v1 검증에서 보완 판정표를 원 report에 연결해 실패; 원본/eval 및 보완본/eval_v2를 각각 검증하여 통과. 원 결과 변경 없음.',
        'protocol history에서 Edit만 추적한 최초 검사 실패; Bash의 문자열 변경도 안전하게 읽어 원 lock/현재 source 모두 byte 재구성 성공.',
        'path fixture 최초12/14: 예상 오류 문구와 표본 JSON키 오류. 실제 덮어쓰기 거부/파일보존은 작동. fixture 수정 후14/14. 누락 조건 검사도 정확한 outputs 거부 분기로 강화.'],
      'pending_uncertainties':['원자적 임상 주장 완전 분할은 상속 접속 목록 단순화로 미충족; 임상 precision은 승인 대상 아님.',
        'CURE 노출의 checkpoint별 환자/선택 로그 미확보; 학습 미노출 일반화 주장 불가.',
        '과거 수동 회귀 두 입력의 tensor/logit 미보존으로6/8 suffix 일치의 원인 미확정.',
        '모호 개념을 U로 두면 CURE recall 차이CI가0을 포함; 효과 확증과 신규 방법 필요성은 미확정.']}
    write_new(OUT/'execution_summary.json',execution)
    outputs={str(p.relative_to(ROOT)):sha(p) for p in OUT.rglob('*') if p.is_file()}
    codes={str(p.relative_to(ROOT)):sha(p) for p in sorted(ROOT.glob('report88_*.py'))+[ROOT/'test_report88.py']}
    deps={p:sha(ROOT/p) for p in ['report87_eval.py','report87_view.py','report86_common.py','report86_eval.py','report86_view.py','report86_facts.py']}
    write_new(OUT/'completion.json',{'state':'implementation_complete_pending_full_review','patients':96,'outputs':768,'new_annotated_patients':20,
      'rechecked_patients':24,'source_files_preserved':len(h['preserved']),'outputs_sha256':outputs,'code_sha256':codes,'dependency_sha256':deps,
      'independent_pass':independent['passed'],'sensitivity_pass':sv['passed'],'path_tests_pass':tests['passed'],
      'scientific_status':'탐색 관찰. 연구 목표 완료/독립 임상 검증/방법 효과 확증 아님.',
      'self_check':'FAIL','self_check_reason':'산술·구조 검사는 통과했으나 원자 주장 분할의 상속 단순화와 의미 대응 불확실성, 과거 수동 회귀 원인 미확정이 남아 사용자 규칙에 따라 보수적으로 FAIL. full review 필요.'})
    print(json.dumps({'state':'complete_pending_full_review','outputs_sealed':len(outputs),'codes':len(codes),'originals_preserved':len(h['preserved']),'self_check':'FAIL'},ensure_ascii=False))


if __name__=='__main__':main()
