"""보존 CURE 자산 검증과 기존 공식 대조 입력 준비. E를 읽지 않는다."""
import json
from report90_numeric import OUT
from report86_common import R85,save,sha,base_path,adapter_path_C

def main():
    source=R85/'model_manifest.json';manifest=json.loads(source.read_text());checks={p:sha(p)==h for p,h in manifest['files'].items()};assert all(checks.values())
    config=json.loads((adapter_path_C()/'adapter_config.json').read_text());assert config['base_model_name_or_path']=='google/medgemma-4b-it'
    reference=R85/'cure_check/result.json';old=json.loads(reference.read_text());assert old['pass'] and old['adapter_sha256']==sha(adapter_path_C()/'adapter_model.safetensors')
    row=json.loads((R85/'D8/raw_manifest.json').read_text())[0];assert sha(row['raw_path'])==row['sha256']
    requests=[dict(id=row['ImageID']+'|report',image=row['raw_path'],file_sha256=row['sha256'],prompt='Generate a grounded report.')]
    save(OUT/'tech/cure_requests.json',requests)
    save(OUT/'tech/cure_assets.json',dict(passed=True,model_files=checks,model_manifest_sha=sha(source),reference_sha=sha(reference),
        base=base_path('C'),adapter=str(adapter_path_C()),adapter_sha=old['adapter_sha256'],
        source_sha=sha(__file__),scope='기존 공식 checkpoint/processor 자산 확인; 새 wrapper 출력 대조는 별도 필요'))

if __name__=='__main__':main()
