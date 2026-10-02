"""잠금 source 변조·손상 record 및 동일 출력 경합의 실제 거부 검사."""
import json
import multiprocessing as mp
from mt52_prepare import ROOT,OUT,save,sha256_file
from mt52_run import verify_protocol,atomic
from mt52_d_report import union

def contend(path,barrier,q,value):
    barrier.wait()
    try:atomic(path,{'value':value});q.put('written')
    except FileExistsError:q.put('refused')

def main():
    dest=OUT/'tests/protocol_final';dest.mkdir(parents=True,exist_ok=False)
    p=json.loads((OUT/'pilot/D8_graph_v2/protocol.json').read_text());p['files']['mt52_run.py']='0'*64
    bad=dest/'wrong_source_protocol.json';save(bad,p)
    try:verify_protocol(bad)
    except ValueError as e:assert 'protocol file changed: mt52_run.py' in str(e)
    else:raise AssertionError('source mutation accepted')
    ctx=mp.get_context('spawn');q=ctx.Queue();bar=ctx.Barrier(2);path=dest/'contended.json'
    ps=[ctx.Process(target=contend,args=(path,bar,q,i)) for i in range(2)]
    for child in ps:child.start()
    for child in ps:child.join(30)
    assert all(child.exitcode==0 for child in ps)
    assert sorted([q.get(timeout=2),q.get(timeout=2)])==['refused','written']
    assert json.loads(path.read_text())['value'] in [0,1]
    assert union([(1,4),(2,3),(3,6),(9,10)])==6
    save(OUT/'tests/protocol_final.json',{'status':'PASS','checks':['changed locked source rejected at intended branch',
        'two concurrent atomic writers: one success, one refusal','overlap union not runtime sum'],'source':sha256_file(__file__)})
    print('PASS 3')

if __name__=='__main__':main()
