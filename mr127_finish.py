"""iter127의 실제 중단 경계와 입력 연결 결함을 봉인한다. 성능 판정기가 아니다."""
from collections import Counter
import csv
import json
from pathlib import Path
import subprocess
import time

import nibabel as nib
import numpy as np
import pandas as pd
from mr127_select import read,save,sha,OUT


def main():
    root=Path('results/iter_127')
    provenance=read(OUT/'provenance.json')
    assert all(sha(p)==h for p,h in provenance['inputs'].items())
    assert all(sha(p)==h for p,h in provenance['inherited_outputs'].items())
    selection=read(OUT/'selection_lock.json')
    verification=read(OUT/'independent_verify.json')
    assert verification['all_pass'] and verification['selection_sha256']==sha(OUT/'selection_lock.json')
    inputs=read(OUT/'tech_inputs.json')['inputs']
    assets=read(root/'assets.json'); fs=read(root/'fs_assets.json')
    for p,h in assets['source_files'].items():assert sha(p)==h
    for x in assets['weights'].values():assert sha(x['path'])==x['sha256']
    for p,h in fs['files'].items():assert sha(p)==h
    # 원 실측 로그로 초기 supervisor의 peak 집계 누락을 별도로 교정한다.
    runs=[]
    for completion in sorted((root/'seg').glob('*/completion.json')):
        stage=completion.parent.name; result=read(completion)
        raw=[]
        for p in completion.parent.glob('resources_*.jsonl'):
            for line in p.read_text().splitlines():raw.append(json.loads(line))
        actual_peak={g:max(x['used_mib'] for row in raw for x in row['gpus'] if x['index']==g) for g in ['0','1']}
        minimum_free={g:min(x['free_mib'] for row in raw for x in row['gpus'] if x['index']==g) for g in ['0','1']}
        outputs={}
        for s in ['7ISDTZ2JVG','5SWPQWD3DD']:
            d=Path('/home/test/.local/share/medgemma/mr_rate/iter127/seg')/stage/s/'attempt_000'
            files={str(p):sha(p) for p in d.glob('*') if p.is_file()}
            record=dict(artifacts=files,returncode=result['failures'].get(s,{}).get('returncode'))
            if (d/'seg.nii.gz').exists():
                a=np.asarray(nib.load(d/'seg.nii.gz').dataobj)
                record.update(foreground_voxels=int(np.count_nonzero(a)),total_voxels=int(a.size),
                              left_ventricle_voxels=int(np.count_nonzero(a==4)),right_ventricle_voxels=int(np.count_nonzero(a==43)))
            if (d/'vol.csv').exists():
                with (d/'vol.csv').open() as f:rows=list(csv.reader(f))
                if len(rows)==2:record['volumes_mm3']={k:float(v) for k,v in zip(rows[0][1:],rows[1][1:])}
            if (d/'qc.csv').exists():
                with (d/'qc.csv').open() as f:rows=list(csv.reader(f))
                if len(rows)==2:record['QC_raw']={k:float(v) for k,v in zip(rows[0][1:],rows[1][1:])}
            outputs[s]=record
        runs.append(dict(stage=stage,wall_s=result['wall_s'],actual_peak_gpu_total_mib=actual_peak,
                min_gpu_free_mib=minimum_free,per_worker_2GiB_headroom=all(x>=2048 for x in minimum_free.values()),
                original_summary_peak_mib=result['peak_gpu_total_mib'],
                summary_peak_mismatch=actual_peak!=result['peak_gpu_total_mib'],outputs=outputs,
                stage_passed=result['checks_passed'],completion_path=str(completion),completion_sha256=sha(completion)))
    technical_by={m['study_uid']:m for m in selection['manifest'] if m['role']=='tech'}
    visual=[]
    bad={'7ISDTZ2JVG':'복부·척추 단면. 측뇌실을 관측하는 뇌 T2 입력이 아님.',
         'PCKMK46BRL':'경부·척수 단면. 뇌 전체/측뇌실 관측 입력이 아님.'}
    for sid,m in technical_by.items():
        p=root/'diagnostics'/f'{sid}_U_diagnostic.png'
        assert p.exists()
        visual.append(dict(study_uid=sid,series_id=m['series_id'],patient_uid=m['patient_uid'],
              image_path=str(p),image_sha256=sha(p),image_tool='tools.view_image through functions.exec',
              actual_image_return_observed=True,body_scope_compatible=sid not in bad,
              observation_ko=bad.get(sid,'표시된 단면에서 두개 내 뇌 조직을 확인. 임상 확장 정답의 재판독은 하지 않음.'),
              timing_ko='SynthSeg pilot 이후 실제 반환 영상을 확인. 사전 시각 감사로 소급 기록하지 않음.'))
    metadata=pd.read_csv('/home/test/.local/share/medgemma/mr_rate/meta/metadata/batch23_metadata.csv',low_memory=False)
    fields=['patient_uid','study_uid','series_id','array_shape','array_spacing_mm','SeriesDescription','ProtocolName',
            'PerformedProcedureStepDescription','StudyDescription']
    rows=metadata[metadata.study_uid.isin(bad)&(metadata.classified_modality=='T2w')&(metadata.acquisition_plane=='AXIAL')][fields].fillna('').to_dict('records')
    diagnosis=dict(status='input_linkage_failed',visual_technical_inputs=visual,
        incompatible_studies=list(bad),metadata_series=rows,
        native_input_sha256={s:{k:v['sha256'] for k,v in inputs[s]['files'].items()} for s in bad},
        alternate_existing_series=[dict(study_uid=s,series_id='t2w-raw-axi',
             image_path=str(root/'diagnostics'/f'{s}_other_series_readonly.png'),
             image_sha256=sha(root/'diagnostics'/f'{s}_other_series_readonly.png'),
             actual_image_return_observed=True,observation_ko='동일 기존 ZIP의 다른 T2 series에는 뇌 단면이 있음. 입력 선택이나 모델 실행에 사용하지 않음.') for s in bad],
        explanation_ko='study에는 다른 신체 부위의 axial T2가 함께 있다. 작은 slice spacing 우선 규칙이 비뇌 series를 선택한다. 일반 brain-mask 출력/크기·affine 일치는 해부학적 입력 적합성을 보장하지 않는다.',
        conclusion_scope_ko='선택한 series 연결의 무효. SynthSeg의 뇌 MRI 능력 실패, 보고서 임상 오류, MR-RATE 전체 부적합을 입증하지 않는다.',
        uncertainty_ko='대체 뇌 series에서의 공식 SynthSeg ICV/QC 및 MedGemma 출력은 미실행.')
    save(root/'diagnostics/input_linkage_failure.json',diagnosis)
    budget=read(OUT/'budget_lock.json')
    # 모든 소유 자식 종료 이후 보존한다. 타 사용자 프로세스를 종료/변경하지 않는다.
    gpu=subprocess.check_output(['nvidia-smi','--query-compute-apps=pid,process_name,used_memory','--format=csv,noheader'],text=True)
    result=dict(status='execution_failed',valid_experiment=False,stage='technical_input_and_specialist_gate',
          selection_count=60,report_reviewed_cases=98,selection_arithmetic_checks=verification['check_count'],
          selected_role_counts=dict(Counter(m['role'] for m in selection['manifest'])),
          selected_semantics_scope_ko='전체 보고서의 명시적 크기 규약에 따라 선정. 실제 뇌 영상 연결은 별도이며 기술2명에서 실패.',
          visual_technical_count=8,visually_incompatible_count=2,
          official_segmentation_runs=runs,weights_check=read(root/'seg/weight_check.json'),
          new_mri_download_bytes=0,new_model_download_bytes=sum(x['size'] for x in assets['weights'].values()),
          proposed_zip_bytes=budget['total_bytes'],actual_existing_zip_bytes=budget['existing_bytes'],
          remaining_zip_bytes=budget['new_bytes'],medgemma_requests_completed=0,
          evaluator_prelocked=False,calibration_completed=False,exploration_completed=False,
          failure_scope='현재 axial T2 series 선택 규칙의 뇌/척추 연결과 기술 단계 입력 유효성',
          stop_reason_ko='기술8명의 실제 뇌 관측 전제가 2명에서 성립하지 않음. 공식 UCL/FreeSurfer 모델 출력도 유효한 전문 점수로 사용할 수 없음. 원 입력을 교체하거나 표본을 재선정하여 출력 후 조건을 바꾸지 않고 현재 설계를 보류.',
          replacement_boundary_ko='plan의 실제 파일 결함 대체는 모델 출력 전 봉인이 조건이다. 이 결함은 SynthSeg 출력 이후 발견했으므로 이번 engineer는 대체 분기를 소급 적용하지 않음. VLM 출력 전만 의미하는지 scientist의 별도 판단이 필요.',
          pending=['뇌 series 적합성을 포함한 입력 선택 설계','공식 전문 비교군 기술8명 유효 출력',
                   'mask 좌표/selector/ICV/QC 실측 검증','MedGemma 공식 processor·생성·재개·처리량 검사',
                   '생성 전 평가 코드 잠금','calibration12','explore40 U/A80건','독립 성능/비용 검산'],
          source_fixes_ko=['자원 peak 집계가 pending 종료 후 한 GPU를 누락하는 결함 수정. 원 로그 재집계 결과를 별도 보존; 수정된 집계의 새 GPU 실행 검증은 미완료.'],
          research_observation_ko='유효한 VLM 가설 검증 없음. 선정·공식 자산 경로 복구와 입력 연결 오류 확인만 완료.',
          recommendation_ko='현재 설계는 입력 전제 실패로 보류. 재개를 택하면 기존 ZIP의 실제 뇌 series 조건을 출력 전에 명시하고 최소 공식 비교로 곧바로 이어지는 별도 계획이 필요. 또 다른 설치/감사 반복이나 MRI 능력 기각은 권고하지 않음.',
          current_compute_processes=gpu.strip(),original_outputs_unchanged=True,
          created_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),
          source_sha256={str(p):sha(p) for p in Path('.').glob('mr127*.py')})
    save(root/'result.json',result)
    artifacts={str(p):sha(p) for p in root.rglob('*') if p.is_file() and p.name!='completion.json'}
    artifacts.update({str(p):sha(p) for p in root.rglob('completion.json')})
    for run in runs:
        for row in run['outputs'].values():artifacts.update(row['artifacts'])
    save(root/'completion.json',dict(status='execution_failed',valid_experiment=False,artifacts=artifacts,
         source_sha256=result['source_sha256'],inherited_outputs_sha256=provenance['inherited_outputs'],
         summary_ko='원 보고서 재선정과 공식2.0 자산 복구 후 기술2/8명에서 비뇌 series 연결을 확인. MedGemma 비교를 실행하지 않고 현재 설계를 보류.'))
    print(json.dumps(dict(status=result['status'],selection=60,reviewed=98,visual_inputs=8,incompatible=2,
        VLM_requests=0,new_MRI_bytes=0,output=str(root/'result.json')),ensure_ascii=False))
    return 2


if __name__=='__main__':raise SystemExit(main())
