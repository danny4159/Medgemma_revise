"""처리량 비교용 고정 24명: iter_009 development 중 과거 출력 토큰 합이 가장 짧은 12명 + 가장 긴 12명 (결과 성능과 무관한 선택)."""
import json

from . import baselines

gt = json.load(open("results/iter_009/manifests/gt_manifest.json"))
dev = sorted(i for i in gt if gt[i]["split"] == "development")
recs = baselines.load_iter9_records(set(dev))
n = {i: recs[(i, "official_long")]["n_output_tokens"] + recs[(i, "concise")]["n_output_tokens"] for i in dev}
o = sorted(dev, key=lambda i: (n[i], i))
ids = sorted(o[:12] + o[-12:])
print(len(ids), [n[i] for i in ids])
json.dump(ids, open("results/iter_010/pilot/thr24_ids.json", "w"))
