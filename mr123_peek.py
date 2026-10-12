import mr123_run as R, json, os, collections, sys
stage = sys.argv[1]
reqs = {r['id']: r for r in R.read_jsonl(R.GEN + stage + '/requests.jsonl')}
recs = []
for fn in sorted(os.listdir(R.GEN + stage)):
    if fn.startswith('worker_'):
        recs += R.read_jsonl(R.GEN + stage + '/' + fn)
print(len(recs), len({r['id'] for r in recs}))
for k, v in sorted(collections.Counter((reqs[r['id']]['label'], r['cond'], r['state']) for r in recs).items()):
    print(k, v)
print(collections.Counter((r['eos'], r['parse_code']) for r in recs), 'max_new_used', max(r['n_new'] for r in recs))
for r in recs[:int(sys.argv[2]) if len(sys.argv) > 2 else 4]:
    print(reqs[r['id']]['label'], r['cond'], r['n_new'], repr(r['text'][:260]))
