"""기술 두 구성의 실제 출력·재개 prefix·warm/cold 처리량과 선택 근거."""
from collections import Counter
import math
from pathlib import Path
from mr128_data import OUT,read,save,sha,utc,verify_files
from mr128_gen import verify
from mr128_eval import states


def intervals_union(intervals):
    end=None;total=0
    for a,b in sorted(intervals):
        if end is None or a>end:total+=b-a
        elif b>end:total+=b-end
        end=b if end is None else max(end,b)
    return total


def profile(directory):
    directory=Path(directory);_,rows=verify(directory,allow_completed_archive=True)
    events=[read(p) for p in directory.glob('*.worker*.events.json')]
    groups=[g for e in events for g in e['groups']]
    emitted=[i for g in groups for i in g['ids']]
    if sorted(emitted)!=sorted(r['id'] for r in rows):raise ValueError('timing coverage differs from completed requests')
    results=[read(p) for p in directory.glob('*.result.json')]
    warm=intervals_union([(g['start'],g['end_after_saved']) for g in groups])
    return dict(count=len(rows),cold_wall_s_including_resume=sum(r['wall_s'] for r in results),
         warm_active_union_s=warm,warm_requests_per_minute=len(rows)*60/warm,
         raw_read_to_saved_p95_s=__import__('numpy').quantile([g['end_after_saved']-g['start'] for g in groups],0.95).item(),
         peak_gpu_total_mib={gpu:max(r['peak_gpu_total_mib'][gpu] for r in results) for gpu in ['0','1']},
         min_gpu_free_mib={gpu:min(r['min_gpu_free_mib'][gpu] for r in results) for gpu in ['0','1']},
         model_loads=len(events),state_counts=dict(Counter(states(r['text'],r['eos'])[0] for r in rows)),
         parser_codes=dict(Counter(states(r['text'],r['eos'])[1] for r in rows)),
         EOS=sum(r['eos'] for r in rows),max_tokens=max(r['n_new'] for r in rows),
         all_processor_checks=all(r['tensor_check']['passed'] for r in rows),
         CPU_RAM_IO_note_ko='원 NIfTI 읽기·window·render·processor·생성·저장 시간은 warm 구간에 포함. 시스템 CPU/RAM/I/O 세부 peak는 이 두 trial에서 별도 수집하지 않았다.')


def main():
    _,b1=verify(OUT/'gen/tech_b1',allow_completed_archive=True);_,b2=verify(OUT/'gen/tech_b2')
    lookup={r['id']:r for r in b1};other={r['id']:r for r in b2}
    if set(lookup)!=set(other) or len(lookup)!=16:raise ValueError('comparison requests')
    prefix=read(OUT/'gen/tech_b2/prefix_preserved.json')
    preserved=all(other[r['id']]==r for r in prefix['rows'])
    if not preserved:raise ValueError('completed prefix changed during resume')
    token_mismatches=[r['id'] for r in b2 if r['tokens']!=lookup[r['id']]['tokens']]
    state_mismatches=[r['id'] for r in b2 if states(r['text'],r['eos'])[0]!=states(lookup[r['id']]['text'],lookup[r['id']]['eos'])[0]]
    a=profile(OUT/'gen/tech_b1');b=profile(OUT/'gen/tech_b2')
    save(OUT/'pilot_comparison.json',dict(created_utc=utc(),b1=a,b2=b,token_mismatches=token_mismatches,
         token_mismatch_count=len(token_mismatches),state_mismatch_count=len(state_mismatches),
         partial_rows_preserved=prefix['count'],prefix_unchanged=preserved,
         adopted=dict(batch=1,workers=2,max_new_tokens=512),
         adopted_reason_ko='batch2의 실제 greedy token이 baseline과 10/16 다르므로 출력 정합성을 보장하는 batch1을 유지한다. 첫 줄 상태는 같지만 더 큰 입력에서의 답 안정성은 확인되지 않았다.',
         concurrency_note_ko='worker 수와 GPU 수를 분리해 같은 GPU에 여러 worker를 매핑할 수 있다. 비교16건은 batch2 및 부분재개 검증에 사용했다. GPU당2 worker는 새 출력 비교를 하지 않았으므로 본실험에 채택하지 않는다.',
         cost_note_ko='batch2는 재개 때문에 모델을4번 적재했다. 전체 cold 시간의 차이를 순수 batch 효과로 해석하지 않는다. warm 처리 구간의 합집합을 따로 제공한다.',
         artifacts={str(p):sha(p) for p in [OUT/'gen/tech_b1/completion.json',OUT/'gen/tech_b2/completion.json',OUT/'gen/tech_b2/prefix_preserved.json']},
         source_sha256=sha(__file__)))
    print('pilot token mismatches',len(token_mismatches),'state mismatches',len(state_mismatches),'adopt batch1/workers2')


if __name__=='__main__':main()
