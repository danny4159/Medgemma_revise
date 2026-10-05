# 요약

- **핵심 결과:** 참고 사례 영상 I(근접 영상+등급)은 E24 held 47개에서 대상 단독 Q, 등급만 준 L, 먼 영상 D, 단순 대안 M보다 낫지 않았다. 사전 정한 정확도 후보 기준을 하나도 넘지 못했다.
- **근거:** class-standardized MAE는 Q 0.7769, L 0.8748, I 0.8262, D 0.7962, M(C argmax) 0.7762다. I−M +0.050 [−0.073, 0.156], I−L −0.049 [−0.195, 0.062], I−D +0.030 [−0.069, 0.143]이고, 독립 재계산과 최대 차이는 0.0이다.
- **미검증·주의:** 반복 사용한 개발 환자 24명, 단일 checkpoint, oracle ROI 조건이다. 어느 비교도 CI가 0을 포함해 "참고 영상이 해롭다"와 "무관하다"를 구분하지 못한다. V8에서는 I가 가장 좋았지만(0.702) E24에서 뒤집혔다. 비용 측정은 정확도 후보 기준 미충족으로 하지 않았다.
- **다음:** 사전 계획의 "I와 L이 비슷하면 현재 영상 활용 방법 투자 종료"에 해당한다. 이 한정 범위의 투자는 종료하고, 새 loss나 참고 수·검색기 순회는 하지 않는 것을 권고한다.

# Work Performed

1. 반입 15개 파일의 `git hash-object`가 reuse_manifest의 blob과 모두 일치함을 확인했다. C selection에 기록된 `sp75_c/data/metrics` hash도 현재 파일과 일치한다.
2. `rf78_ref.py`에서 C(iter_075 epoch40) 세 crop 평균 penultimate feature(L2 정규화)를 T24 70 / V8 24 / E24 held 47개에 대해 추출했다. E24 47개의 C 예측은 iter_077 저장값과 47/47 일치했고 확률 최대 차이는 9.8e-5다.
3. 검색과 참고 구성: top3 서로 다른 환자(I), 같은 grade에서 I_j 환자와 D 내 중복 환자를 제외한 최저 cosine(D). `retrieve`는 query feature와 T24 bank만 받는다. 요청 파일에는 query grade가 없고, grade는 labels 파일에만 있다.
4. `rf78_vlm.py`와 `rf78_gen.py`에서 Q/L/I/D 입력과 생성 worker를 구현했다. 공식 chat template, bf16, greedy, 최대 32 token, 기존 whole-string parser를 유지했다. 대상 영상은 항상 마지막 3장이다.
5. request_id에는 query/ref pixel hash, ref id, ref grade, 순서, 조건, adapter digest, prompt digest, 실행 config를 모두 넣었다.
6. 기술 검사, CPU 검사, 실제 worker 재개·변조 검사를 수행했다. V8 생성과 M 선택을 거쳐 E24 잠금과 E24 생성·평가·독립 검증까지 진행했다.

# Files Changed

신규 코드는 `rf78_ref.py`, `rf78_vlm.py`, `rf78_gen.py`, `rf78_launch.py`, `rf78_tech.py`, `rf78_test.py`, `rf78_lock.py`, `rf78_eval.py`, `rf78_verify.py`다. 반입한 `sp75_*`, `g71_data.py`, `sp67_data.py`, `rsna_diag/*`는 수정하지 않았다. 결과는 모두 `results/iter_078/`에 저장했다.

# Commands / Experiments

모두 성공했다.

- `python rf78_ref.py features --gpu 0` → 141개 feature, `python rf78_ref.py build` → V8 24 / E24 47 요청.
- `python rf78_tech.py 0`: 프롬프트의 텍스트 블록이 개행 없이 붙어 있어 개행을 추가한 뒤 재실행했다. 최초 `tech.json`(개행 없음, 폐기)과 최종 `tech_v2.json`을 둘 다 보존했다.
- `python rf78_test.py cpu`, `python rf78_test.py proc 1`.
- 처리량 비교: `rf78_launch.py` cfgA(GPU당 1 worker)는 12개 I 요청을 32.5초에 처리했다. cfgB(GPU당 2 worker)는 사전 admission에서 거부됐다(필요 25,027 MiB > 여유 24,489 MiB).
- V8 본생성: `--tag V8_main`, L/I/D 72건, wall 121초.
- `python rf78_eval.py v8` → M 선택 → `python rf78_lock.py` → E24 생성(`--tag E24_main`, 141건, wall 190초) → `python rf78_eval.py e24 --lock ...` → `python rf78_verify.py E24` 및 `V8`.

# Results

**실행 무결성**
- Q 재현: V8 첫 4건에서 input_ids, pixel_values, suffix token, 입력 토큰 수가 iter_077 저장 출력과 모두 일치한다(`tests/tech_v2.json`).
- 입력 구조: I/D는 12영상, L은 3영상이다. 마지막 3장의 pixel tensor는 Q와 동일하고, 각 참고 블록은 단독 구성 tensor와 같다. adapter digest는 72417dc3…과 일치한다.
- CPU 검사(`cpu_tests.json`): all_pass.
  - 확인한 항목: query grade 비포함, T24와 query 환자 분리, 참고 영상이 query 영상과 중복되지 않음, D가 I의 grade 순서를 유지하며 환자가 서로 다름, request_id 8종 민감도.
  - D의 참고 환자가 I의 다른 슬롯 환자와 겹친 요청은 V8 9/24, E24 12/47이다. 계획 규칙(해당 위치의 I 환자만 제외)을 그대로 따른 결과다.
- 실제 worker 검사(`proc_tests.json`): 3건 후 중단, torn tail 복구, 재개해 6건이 되었고 token이 cfgA와 일치한다. 참고 pixel, grade, request_id 변조, 중복, 집합 밖 id는 모두 rc=1로 거부됐고 출력 파일은 변하지 않았다.
- 완전성: 조건별 V8 24건, E24 47건이 모두 고유하고 EOS로 끝났으며 parse 유효 100%다. 모든 자식 종료 코드는 0이다.
- 독립 재계산(`independent_verify_E24.json`, `_V8.json`): production 평가기를 쓰지 않고 계산해 최대 차이 0.0이다.

**V8 24개 (개발)**
- primary: Q 0.822, L 0.785, I 0.702, D 0.752.
- M은 V8에서만 선택해 C_argmax(0.6917)다. 동률 후보가 많아 사전 고정한 순서(VLM 호출 없음, 작은 k, 작은 λ)로 정해졌다.
- 진행 규칙(I와 D 모두 유효 12개 미만이면 보류)에는 해당하지 않아 E24로 진행했다.

**E24 held 47개, 24명 (개발)**

| | Q | L | I | D | M |
|---|---|---|---|---|---|
| class-std MAE | 0.7769 | 0.8748 | 0.8262 | 0.7962 | 0.7762 |
| MAE | 0.723 | 0.851 | 0.809 | 0.787 | 0.745 |
| 두 등급 이상 오류율 | 0.106 | 0.128 | 0.149 | 0.106 | 0.149 |

- 쌍별 비교(차이와 95% CI):
  - I−L −0.0486 [−0.1945, 0.0617]
  - I−D +0.0300 [−0.0686, 0.1432]
  - I−M +0.0500 [−0.0730, 0.1557]
  - I−Q +0.0493 [−0.1567, 0.2244]
  - 환자 bootstrap은 seed 7501, 10,000회이며, 비교마다 class 누락 replicate가 57회 있었다.
- Q 대비 I는 회복 5건, 악화 7건, 불변 35건이다. L은 회복 3·악화 8, D는 회복 4·악화 7이다.
- 기준 판정(`criteria`): I−M ≤ −0.15, I−L ≤ −0.10, I−D ≤ −0.10은 모두 미충족이고 오류율 조건만 충족해 `accuracy_candidate=false`다.
- 사후 설명용 분석: 참고 grade 3개가 모두 대상과 일치한 21건에서 I의 MAE는 0.190, D는 0.286, L은 0.381이다. 일치가 없는 24건에서는 1.333, 1.292, 1.250으로 세 조건이 비슷하다. 이는 출력 후 설명용이며 성공 판정에 쓰지 않았다.

산출물: `results/iter_078/eval/report_V8.json`, `report_E24.json`, `select_M.json`, `eval_lock_E24.json`, `independent_verify_{V8,E24}.json`, `gen/V8_main`, `gen/E24_main`.

# Goal Progress / Reused Assets

- **목표 진전:** 이 개발 자료에서 참고 영상의 추가 정보는 확인되지 않았다. 이득의 방향도 L과 D 사이에서 일정하지 않고, 불확정이다. "일반적으로 참고 영상이 무관하다"는 결론은 아니다.
- **재사용:** 반입 15개 파일을 사용했고 sp77 stage/pipeline과 cost 실행기는 쓰지 않았다. `sp75_data/c/vlm/gen/metrics`는 원 리뷰의 제한 범위에서 썼고, Q 71건은 재생성 없이 iter_077 원시 출력을 그대로 읽어 재사용했다. 재사용 근거는 모델·adapter·pixel hash·V8 4건 token 일치다.
- **batch/worker:** batch 확대는 시도하지 않았다. GPU당 2 worker는 시작 전 admission 규칙으로 거부됐으며, 근거는 실측 peak 10.2 GiB(nvidia-smi 10,465 MiB)다. 실제 구성은 GPU당 1 worker, 총 2 worker다.
- **실제 사용량:** 새 학습·다운로드는 없다. V8 72건, E24 141건, 기술·처리량·재개 검사 소량을 생성했다. 비용 측정 block은 실행하지 않았다.
- **미검증:** 독립 확인, 다른 seed·참고 수·검색기, 타 계열 모델, 임상적 판독 충분성, 비용 비교.

# Problems

- **현재 결론 무효:** 없음.
- **재사용 전 수정이 필요한 것:**
  - `rf78_eval.py`의 M 후보 중 combo는 `rf78_verify.py`에서 재구현하지 않았다. 이번 M은 C_argmax라서 영향이 없다.
  - `rf78_launch.py`의 GPU 물리 인덱스 매핑은 상속 집합이 0,1일 때만 검증했다.
- **추후 개선:**
  - `tech.json`(개행 없는 구 프롬프트)은 폐기본으로 남아 있고 최종은 `tech_v2.json`이다.
  - 일부 개발 메모에는 임시 `ids6.json`이 있다.
  - V8의 I 이득은 24개 표본에서 나왔으며, E24에서 뒤집혔으므로 해석에 쓰지 않는다.

# Recommendation to GPT

계획의 사전 규칙대로 "참고 영상 활용을 방법 투자 대상으로 삼을 만큼의 추가 가치는 없다"로 이 한정 범위를 종료할 것을 권고한다. I는 L·D·M·Q 중 어느 것보다도 낫지 않았다. 새 loss, 참고 수·검색기 변경, 이 자료의 확대는 정당화되지 않는다. 같은 research_track에서는 다른 질문으로 전환하되, "I−L −0.05 [−0.19, 0.06]"을 영상 효과의 증거로 쓰지 않도록 리뷰에서 구분해 주길 바란다.

SELF_CHECK: PASS
SUMMARY: 척추 MRI에서 유사 참고 영상(I)은 E24 held 47개에서 등급만 준 L, 먼 영상 D, 단순 대안 M 대비 MAE 이득이 없었고(I 0.826 vs M 0.776, 모든 CI가 0 포함), 정확도 후보 기준 미충족으로 현재 참고영상 활용의 추가 투자를 종료하는 근거가 됐다.

# [orchestrator] 권한 거부된 도구 호출
- Bash: python rf78_ref.py build 2>&1 | tail -5; python - <<'E'
import json,numpy as np
ft=json.load(open('results/iter_078/features.json'))
p=json.load(open('results/iter_077/pred/pred_C_E24.json'))
print(p.keys() if isinstance(p,dict) else type(p))
preds=p['preds'] if 'preds' in p else p
m=0;md=0;n=0
for r in preds:
    i=r['id']
    if i in ft['items']:
        n+=1; m+= r['pred']==ft['items'][i]['pred']; md=max(md,np.abs(np.array(r['probs'])-np.array(ft['items'][i]['probs'])).max())
print(n,m,md)
for sp in ('V8','E24'):
    d=json.load(open(f'results/iter_078/data/refs_{sp}.json'))['requests']
    lab=json.load(open(f'results/iter_078/data/labels_{sp}.json'))['labels']
    import collections
    ov=sum(len({x['patient'] for x in r['I']}&{x['patient'] for x in r['D']})>0 for r in d)
    same_all=sum([x['ref_id'] for x in r['I']]==[x['ref_id'] for x in r['D']] for r in d)
    gm=np.mean([sum(x['grade']==lab[r['id']]['grade'] for x in r['I'])/3 for r in d])
    print(sp,len(d),'I∩D patient overlap',ov,'same',same_all,'frac I grade==query',gm, 'cos I',np.mean([x['cosine'] for r in d for x in r['I']]),'cos D',np.mean([x['cosine'] for r in d for x in r['D']]))
E
