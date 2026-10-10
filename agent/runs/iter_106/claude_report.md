# 요약

- **핵심 결과:** CURE에 두 소견을 한 요청에 합쳐 물으면 박스를 거의 내지 않았다. 독립 PG 두 출력을 합치면 위치 recall 0.875였고, 공동 요청은 J12 0.234, J21 0.109였다(E32, 환자 32명, IoU≥0.3, GT 2개).
- **근거:** I−J 평균 차이는 0.703이다(95% CI [0.594, 0.805]). 같은 소견을 반복한 대조도 I 대비 0.406 낮았다(CI [0.266, 0.531]). 손실의 대부분은 좌표 없는 문장 응답이다. 박스를 내는 비율은 I 91–97%, R 50–53%, J12 37.5%, J21 21.9%였다.
- **미검증·주의:** 사전 지표는 모두 충족했지만, 이 결과는 "복합 phrase를 지원하지 않는 인터페이스" 설명과 구분되지 않는다. 일반적인 공동 처리 결함이라고 말할 수 없다. 사전 계획의 clean subset은 no_box를 걸러내지 않아 형식 분리가 반영되지 않았다. 학습 노출은 미확인이고 개발 자료다.
- **다음:** 결과를 보고 사용자 승인을 기다린다. 추천 후속은 CURE의 지원 인터페이스(단일 phrase 반복 호출 또는 GRG)와 비용만 비교하는 것이다. 복합 prompt나 SFT 투자는 보류한다.

# Work Performed

- iter_105 코드를 `lk106_*`로 복사·수정했다(요청 집합, 출력 경로, 요청별 end-to-end timing). 가중치 lock은 iter_105 lock을 상속했고, 파일 크기와 작은 자산 digest가 모두 같은 경우에만 만들었다.
- 한정 자료 점검: D4+E32 36명을 원 PadChest-GR metadata와 대조했다(환자·study·split, S1/S2, main/extra box, 영상 hash). 불일치는 0이었다.
- 연결 가능성 확인:
  - iter_086 E96과의 ImageID 교집합은 0이다.
  - D8과는 2건이 겹치지만 GRG와 PG는 입력 정보가 달라 paired 비교를 하지 않았다.
- D4 24요청(I1/I2/J12/J21/R11/R22)을 실행한 뒤, 사전 gate(J 8요청의 malformed·비EOS)를 확인하고 E32 128요청을 실행했다.
- 평가와 독립 verifier를 구현했고, 좌표 형식과 박스 유무를 분리하는 사후 기술 분석을 추가했다.

# Files Changed

신규 파일은 아래와 같다.

- 코드: `lk106_spec.py`, `lk106_run.py`, `lk106_eval.py`, `lk106_verify.py`, `lk106_prov.py`, `lk106_tech.py`, `lk106_test.py`, `lk106_runtests.py`, `lk106_lock.py`, `lk106_supp.py`
- 결과: `results/iter_106/` 아래에만 저장했다.
- 반입한 iter_105 파일은 수정하지 않았다.

# Commands / Experiments

모두 성공했다.

- `lk106_prov.py`: 36명 연결 확인, 문제 0.
- `lk106_test.py`: CPU fixture 21/21.
- `lk106_run.py launch --stage D4 --workers 2`: exit 0, wall 110.9s.
- `lk106_tech.py`: 공식 `apply_chat_template` + `generate` 대조 24/24(input_ids, suffix token, pixel hash 일치).
- `lk106_runtests.py`: 통제 중단, torn tail 재개, baseline과 token 일치, 변조 거부(텍스트 수정, 행 삭제·중복, completion hash, prompt 변경) 11/11.
- `lk106_lock.py`: D4의 I1/I2가 iter_105 저장 출력과 8/8 token 동일. E32 직전 잠금 파일 생성.
- `lk106_run.py launch --stage E32 --workers 2`: exit 0, wall 422.8s.
- `lk106_eval.py`와 `lk106_verify.py`: E32 13/13, D4도 일치.
- 4 worker(GPU당 2개) 시도는 admission 거부로 실패했다(남은 메모리 11,988 / 8 MiB, 필요 12,048 MiB). 산출 행은 없다.
- 실패한 시도: 처음 `lk106_verify.py`를 실행했을 때 numpy bool을 JSON으로 저장하지 못해 실패했다. 이 한 곳만 `bool()`로 고쳐 다시 실행했다. 이 수정은 E32 잠금 이후에 이루어졌고, 계산 로직은 바뀌지 않았다.

# Results

수치는 `results/iter_106/eval/report_E32.json`, `report_D4.json`, `supplement_E32.json`, `RESULTS.md`에 있다.

- **GPU 구성 선택:** GPU당 worker 2개는 메모리 여유 때문에 불가능했다. 그래서 GPU당 1개(총 2 worker)로 고정했다. batch 확대는 비교하지 않았다. 추가 비용이 절감 예상보다 컸다.
- **GPU peak:** 10,069 / 9,997 MiB.
- **D4 gate:** malformed 0, 최종 비EOS 0 → E32 진입.
- **E32 주지표:**
  - recall: I 0.875, J12 0.234, J21 0.109. 의미 평가는 하지 않았다.
  - I−J12 0.641, I−J21 0.766.
  - 두 순서에서 모두 I의 정답 영역을 잃은 환자 수는 report의 `patients_lost_both_orders` 필드에 있다.
- **형식 상태(E32):**
  - no_box: J12 20/32, J21 25/32, R11 15/32, R22 16/32.
  - 좌표가 나온 J 요청 중 단일 박스 출력: J12 7/12, J21 6/7.
- **비용(D4 4명 end-to-end):** 독립 두 요청 14.9s, 공동 한 요청 6.5s(J12) / 5.0s(J21). 공동이 빠른 것은 좌표 token을 덜 내기 때문이며 같은 산출물 비교가 아니다.
- **iter_105 독립 PG 재사용:** 완료 검증을 통과했다. D4의 iter_105 D4_w1f는 소스 digest가 달라 재사용하지 않고 재생성했다.

# Goal Progress / Reused Assets

- **자료 점검:** 완료(36명, 불일치 0). 이는 자료 연결 확인이지 새 과학적 관찰이 아니다.
- **새 관찰(CURE 조건, 제한적):**
  - 복합 phrase에서는 위치 박스 자체가 줄어든다. 같은 소견 반복에서도 비슷한 양상이 나온다.
  - 좌표가 나온 경우도 부분적이다.
- **미검증:**
  - 복합 PG를 지원하는 모델에서의 결과.
  - 직접 SFT 이후의 결과.
  - 문장별 binding과 자유 판독.
- **재사용 검증:** 요청 집합과 digest 변경 거부를 확인했다. 새 결과 경로에서의 부분 재개와 completion 변조 거부도 확인했다.
- **재사용하지 않은 것:** `lk105_spec.py`의 A/B 평가와 lenient 분기는 쓰지 않았다.

# Problems

- **현재 결론에 영향:** 사전 flag의 `clean_subset`이 no_box를 분리하지 못한다. 그래서 flag가 모두 true인 것을 "복합 내용과 연결된 손실"로 읽을 수 없다. 사후 분석은 주판정과 분리했다.
- **재사용 전 수정:**
  - 대표 환자 수가 작다(3명만 두 순서 모두 박스 출력).
  - 반복 대조는 token 길이를 완전히 통제하지 않았다.
  - `lk106_verify.py`는 요청 완전성과 provenance를 직접 검증하지 않는다(`lk106_run.verify_completion` 몫).
- **후속 개선:** extra annotation 민감도는 report에 포함했지만 해석은 미완이다. 기계적 평가기를 더 손볼 필요는 없다.

# Recommendation to GPT

- **결과 해석:** "정답이 단순 결합으로 충분(단순 대안 충분) + 형식·인터페이스 설명" 쪽이다. 일반적인 공동 처리 결함이라고 말할 근거는 없다.
- **추천:** 복합 prompt 추가나 SFT는 하지 않는다. 다음은 CURE가 지원하는 인터페이스(GRG 한 번 vs 단일 phrase 반복)의 비용·위치 회복 비교로 좁히는 것을 권한다.
- **대안:** 복합 입력을 지원하는 다른 모델에서 같은 두 소견 비교를 하는 것.
- **보류 범위:** 이 CURE 복합 PG 인터페이스에서의 공동 요청 투자만 보류한다.
- **판단:** 계획은 완결 실행했지만, 위 해석 한계 때문에 FAIL로 둔다.

SELF_CHECK: FAIL
SUMMARY: CURE 복합 PG는 박스를 내는 비율 자체가 낮아(J12 37.5%, J21 21.9%) recall I 0.875 대 J 0.23/0.11이지만, 형식·인터페이스 설명과 구분되지 않아 일반적 공동 처리 결함으로 해석할 수 없다.

# [orchestrator] 권한 거부된 도구 호출
- Bash: sed -e 's/lk105_run as R/lk106_run as R/; s/lk105_spec as S/lk106_spec as S/; s/iter_105/iter_106/g; s/lk105_tech/lk106_tech/g' lk105_tech.py > lk106_tech.py
python - <<'E'
s=open('lk106_tech.py').read()
s=s.replace('PICK = ["img-N-o0", "img-W-o1", "txt-C-o0", "txt-N-o1", "pg-S1", "pg-S2"]','PICK = ["I1", "I2", "J12", "J21", "R11", "R22"]')
s=s.replace('--stage", default="D4")','--stage", default="D4")')
open('lk106_tech.py','w').write(s)
E
grep -n "PICK\|rec = recs\|rid =" lk106_tech.py
- Bash: python ../experiment_wait.py --pid $(pgrep -f "lk106_run.py launch" | head -1) --timeout 600
- Bash: CUDA_VISIBLE_DEVICES=0 HF_HUB_OFFLINE=1 TOKENIZERS_PARALLELISM=false results/environments/cure085/bin/python lk106_tech.py --system CURE --stage D4 --gen-dir results/iter_106/gen/D4_w2 --workers 2 --out results/iter_106/tests/tech_CURE.json --n-images 4 2>&1 | tail -5
- Bash: python - <<'E'
import json, time
from report86_common import read_jsonl_complete, sha, sha_obj, save, ROOT
import lk106_run as R
old={r['id']:r for r in read_jsonl_complete('results/iter_105/gen/D4_w1f/cure/shard0/outputs.jsonl') if r['kind']=='pg'}
new={}
for k in (0,1):
    for r in read_jsonl_complete(f'results/iter_106/gen/D4_w2/cure/shard{k}/outputs.jsonl'): new[r['id']]=r
cmp=[]
for i,r in old.items():
    n=new[i.replace('|pg-S1','|I1').replace('|pg-S2','|I2')]
    cmp.append({'id':i,'tokens_equal':r['attempts'][-1]['suffix_ids']==n['attempts'][-1]['suffix_ids'],'input_ids_equal':r['input_ids']==n['input_ids'],'pixel_equal':r['pixel_sha256']==n['pixel_sha256']})
print(all(c['tokens_equal'] and c['input_ids_equal'] and c['pixel_equal'] for c in cmp),len(cmp))
save(R.R106/'tests/reproduce_iter105_D4_independent.json',{'n':len(cmp),'all_equal':all(c['tokens_equal'] and c['input_ids_equal'] and c['pixel_equal'] for c in cmp),'checks':cmp})
lock={'time':time.time(),'iso':time.strftime('%Y-%m-%dT%H:%M:%S'),'purpose':'E32 생성 직전 잠금(D4 결과를 본 뒤, E32 출력 전). prompt·parser·문턱·표본 변경 없음',
 'd4_gate':'J 8요청 중 malformed(coord_invalid/truncated)=0, 최종 비EOS=0 → E32 진입(plan §3). no_box 다수는 형식 관찰이며 gate 아님',
 'e32_requests_sha256':sha_obj(R.requests('E32','CURE')),'sources':{f:sha(ROOT/f) for f in R.EXEC_SOURCES+['lk106_eval.py','lk106_verify.py','lk106_test.py','lk106_runtests.py','lk106_prov.py','lk106_tech.py']},
 'inputs_E32':sha(R.DATA/'inputs_E32.json'),'weights_lock':sha(R.LOCKFILE),'worker_config':'CURE 2 workers (1/GPU); 2 workers/GPU 메모리 admission 거부(D4_w4: 11988/8 MiB free vs need 12048)'}
save(R.R106/'protocol/lock_before_E32.json',lock)
E
