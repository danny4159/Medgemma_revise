D24 bbox 생성 완료 알림을 기다립니다. 알림이 오면 결과를 확인하고 다음 단계를 진행하겠습니다.

# [orchestrator] 권한 거부된 도구 호출
- Bash: python -c "
import json
sets = json.load(open('results/iter_015/manifests/sets.json'))
e600 = sets['E600']['opacity']
e180 = sets['E180']['opacity']
print('E600 opacity n', len(e600), e600[:3])
print('E180 opacity n', len(e180), e180[:3])

# check confirm 800 ids from iter_012
import glob
conf_ids=set()
for f in glob.glob('results/iter_012/confirm_base/gen_worker*.jsonl'):
    for ln in open(f):
        if ln.strip():
            r=json.loads(ln)
            conf_ids.add(r['id'])
print('confirm_base unique patient ids', len(conf_ids))
print('E600 subset of confirm_base?', set(e600) <= conf_ids)
print('E180 subset of confirm_base?', set(e180) <= conf_ids)
missing = set(e600)-conf_ids
print('missing count', len(missing))
"

- Bash: nohup python3 -m rsna_diag.roi23_run --stage D24_bbox --ckpts M0,B0 --protocol results/iter_023/protocol_D24_bbox.json --workers 4 --gpus 0,1 --peak-gb 9 > /tmp/d24_bbox_run.log 2>&1 &
echo "launched pid $!"
