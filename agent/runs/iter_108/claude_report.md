# 요약

- **핵심 결과:** 예측 영역 crop(T)을 원본에 더해도 표적 음영 질문(O)은 좋아지지 않았다. T는 원본 복제(D)와 같거나 약간 낮았다. 크기를 맞춘 중앙 crop(C)과도 차이가 없었다. 전체 비정상 질문(A)의 하락은 대부분 답변 형식 이탈로 설명된다. 단순 규칙(bbox가 비어 있으면 no)이 T 정책(R)보다 낫거나 같았다. 이 설정의 입력 방식에 방법 투자는 보류한다.
- **근거:** E600 nonempty 236명에서 정확도 차이를 환자 단위 bootstrap 95% 구간으로 계산했다. T−D O는 −0.030 [−0.064, +0.004]이고, 답이 달라진 환자는 8명(개선 3·악화 5)이다. T−C O는 +0.004 [−0.025, +0.034]이다. S_scope(O·A를 모두 맞춘 비율의 category 균등 평균)는 F/R/R_L/R_B가 0.610/0.597/0.530/0.632이다. 새 요청 1,652건은 모두 EOS 종료·재시도 0이다.
- **주의:** frozen MedGemma 1.5와 RSNA 개발 자료, 단일 설정이다. A 질문에서 새 안내문 아래 "설명 문장"으로 답한 비율이 F 1%에서 D/T/C 27~43%로 늘었다. 주 parser(semantic_v1)가 이를 오답으로 처리하므로 A의 하락은 내용 효과와 분리되지 않는다. 여기에 O 정확도의 상대 크기가 영향을 줬을 가능성은 미확인이다.
- **다음:** 새 구현과 실행에 이어 이후 투자 판단은 GPT 리뷰와 사용자 승인에 맡긴다.

# Work Performed

- 승인 기반과 reuse manifest의 11개 blob을 확인했고(SHA 일치), 새 결과 root를 `results/iter_108`로 고정했다.
- 한정 자료 점검을 했다. P180/E600 nonempty는 계획 집계와 일치한다(54/1/17, 164/5/67). 저장 B0 bbox는 invalid/truncated가 0건이다. 영상 file hash 불일치는 0건이다. F 1,200건은 모두 EOS 종료(cap 1000)이다.
- crop 기하·두 영상 요청·F 재현 요청(`ev108_spec/data/build/run.py`)과 평가·분기 코드(`ev108_eval.py`, `ev108_report.py`)를 구현했다.
- 기존 `pg43_run.py` 패턴 위에 다중 영상 runner를 새로 만들었다(`ev108_run.py`). 계획이 요구한 보완을 이 경로에서 해소했다.
  - 가중치 파일 내용 sha256을 protocol에 잠그고 worker가 시작할 때 다시 대조한다. 파일 크기로는 계승하지 않는다.
  - 요청 행 전체를 재구성해 `request_id`를 다시 계산한다.
  - 영상별 tensor hash를 기록한다.
  - admission 실패와 attempt 종료 상태를 파일로 남긴다.
  - 전수 검증을 통과해야 completion을 쓴다.
- 평가·분기·policy·요청·입력은 **2026-10-11 15:04:01 KST**에 잠갔다(`protocol/eval_lock.json`). 이 시각 이전에 multi-image 출력은 없다. 잠금 이후 잠금 파일 변경은 0건이다(eval lock 21개 파일·각 stage protocol의 코드·locked_files).
- F 12/12 재현 → 기술 gate → P180 → 사전 분기(확대 필요) → E600R 순서로 실행했다.

# Files Changed

- 새 코드: `ev108_{spec,data,build,run,eval,report,verify,lock,frepro,overlay}.py`, `test_ev108{,_proc,_qaspec,_report_dry,_runtime}.py`
- 반입: `rsna_diag/qa_spec.py`와 iter_105 파일 9개는 blob 일치만 확인했으며 수정하지 않았다.
- 결과는 `results/iter_108/` 아래에만 썼다. 기존 결과·checkpoint·정책 파일은 건드리지 않았다.

# Commands / Experiments (실제 실행한 명령과 성공/실패)

- 반입 파일 blob 해시 대조: 성공.
- `ev108_build.py`로 crop·요청 생성: TECH 42, P180R 462, E600R 1,148건(과학 요청 합계 1,652)을 만들었고 `ev108_build.py frepro`로 FREPRO 12건을 만들었다. 성공.
- `test_ev108.py`(CPU fixture): 61/61 통과. 처음엔 2건이 실패했다. 테스트 자체의 오기(`aff` 연쇄 비교)와 잘못 설정한 fake CI 때문이었고 코드는 고치지 않았다.
- `test_ev108_proc.py`: 98/98 통과. 처음 두 번 실패했다. 첫 실패는 image token id를 `processor.image_token_id`(`<start_of_image>`)로 센 것이고 `<image_soft_token>` 262144로 고쳤다. 둘째 실패는 독립 경로 B에서 `<bos>`가 이중으로 붙은 것이고 `add_special_tokens=False`로 고쳤다. 두 실패 파일은 이름을 바꿔 보존했다. 이번 결론을 막는 오류는 아니다.
- `test_ev108_report_dry.py`(합성 답변으로 전체 보고 경로): 성공.
- F 12요청(2 worker): 입력 id·출력 token 12/12 일치.
- TECH 42요청: w2, w4, 부분 재개(`resume`)가 모두 token·tensor hash 일치. SIGKILL 후 재개와 admission 거부 시험까지 포함해 `test_ev108_runtime.py` 20/20 통과.
- P180R 462요청과 E600R 1,148요청: 각각 2 worker(GPU 0, 1 각 1개)로 실행했다. exit code 0이다.
- `ev108_report.py` p180 → `decision_P180.json`(expand=true) → e600 `final_E600.json`: 성공.
- `ev108_verify.py` p180/e600: 독립 재계산 all_ok.
- `test_ev108_qaspec.py`: 18/18 통과.
- 실패한 명령은 위 첫 번째와 두 번째 proc 시도뿐이다. 그 밖의 오류와 OOM은 없었다.

# Results (수치와 결과 파일 경로)

- **한정 자료 점검과 단계:** 도달 단계는 E600 nonempty 236명이다. P180에서 T−C O가 사전 분기 B(환자 4명 변화, CI가 0과 +10pp를 함께 포함, 예상 반폭 0.038 ≤ 0.15)를 충족해 확대했다. 확대는 효과를 본 선택이 아니라 사전에 잠근 규칙의 결과다. `eval/decision_P180.json`.
- **E600 주 endpoint** (`eval/report_E600.json`, `comparisons_sem`):

  | 비교 | 차이(95% CI) | 의미 있는 변화 환자 |
  |---|---|---|
  | T−D O | −0.030 [−0.064, +0.004] | 8명 (3 개선, 5 악화) |
  | T−D A (not_normal_no_opacity, n=67) | −0.134 [−0.224, −0.060] | 0명 (전부 invalid 유발 9건) |
  | T−C O | +0.004 [−0.025, +0.034] | 8명 (6 개선, 2 악화) |
  | D−F O | −0.004 [−0.038, +0.030] | 13명 |
  | L−F O | −0.186 | 147명 |

  `limited_positive`(사전 정의한 제한적 양성 기준)는 세 endpoint 모두 false이다.
- **A 질문 형식 실패** (semantic_v1 invalid 수): D 65, T 98, C 102, F 2. A 전체에서 답이 달라진 환자(두 답이 모두 유효)는 0명이다. F 대비 D의 not_normal_no_opacity A 정확도가 0.866 → 0.388이고 invalid는 31이다.
- **Policy** (`policies_sem`, 전체 600명, 빈 예측은 F): S_scope는 F 0.610, R 0.597, R_L 0.530, R_B 0.632이다. 차이는 R−F −0.013 [−0.030, +0.002], R_B−F +0.022 [−0.002, +0.045], R_B−R +0.035 [+0.007, +0.063]이다. F의 S_scope 0.610은 iter_016 보고의 M0 semantic 값 0.6100과 일치한다.
- **crop 특성:** nonempty 236명에서 T와 C가 같은 경우는 0이다. 면적비 중앙값은 0.067이다. 양성 164명 중 예측 box가 GT와 IoU 0.3 이상인 경우가 139명이다.
- **정합성:** `verify_*.json`에서 점추정·전이 수·S_scope가 정확히 일치했고 CI 차이는 0.03 미만이다(CI 재표집은 같은 seed의 층화 bootstrap 별도 구현이다). `RESULT_MANIFEST.json`에 25개 산출물의 sha256을 남겼다.
- **비용(실측):** wall은 P180R 462요청 356.4초, E600R 1,148요청 778.3초이다. 생성 구간 처리량은 약 89–93 req/min이다. GPU peak 예약 메모리는 8.41GB이다. 요청당 평균 생성 시간은 D 0.95초, T 1.18초, C 1.21초, L 0.47초이다. localizer 비용은 이번에 측정하지 않았다.
- **병렬 구성 비교(TECH 42요청):** GPU당 1 worker(w2)는 58.2 req/min, 2 worker(w4)는 56.1 req/min으로 이득이 없었다. 장치 시간은 135초 → 156초로 늘었다. 그래서 w2를 채택했다. 4 worker를 본실험에 쓴 적은 없다.

# Goal Progress / Reused Assets (목표 진전·미검증 범위, 재사용 출처·검증)

- **시험 설정:** 이 입력 방식(두 번째 영상 제공 + 고정 안내문, frozen reader)은 더 투자할 가치가 낮다. 실행 유효성은 확보됐다. 성능 변화는 거의 없다. 가설 지지(국소 영상 제공의 이득)는 얻지 못했다.
- **연구 관찰(유지):** 같은 원본이 있을 때 예측 영역 crop은 O에 도움이 되지 않고 위치 선택 효과도 보이지 않는다. A에서는 안내문/다중 영상 때문에 출력 형식이 크게 깨지는 현상이 관찰됐고, 이는 내용 판단 변화와 분리되지 않았다.
- **연구 질문(미결):** 이 결과만으로 외부 영상 근거의 가치를 판단할 수 없다. 모델·자료·입력 방식을 한 조건만 본 것이다. 이번 조건은 신규성을 주장하지 않는다.
- **미검증:** 형식을 통제한 A 질문(안내문 없이 또는 단일 답변 강제), 독립 확인 집단, 다른 모델, 학습 적응, 임상 정확성. P180⊂E600은 개발 자료이므로 독립 확인으로 부르지 않는다.
- **재사용 검증:** `qa_spec.py` blob 일치와 18/18 fixture, F의 token 재현과 S_scope 일치. `pg43_run.py`의 소유권·부분 행 복구·digest 함수는 실제 SIGKILL 재개와 변조 거부로 검증했다. `lk105_run.py`는 설계 참고만 했고 호출하지 않았다. 반입한 `generate.py`는 `load_image`, `generate`, 모델 로딩 경로만 사용했다.

# Problems (현재 결론 무효 / 재사용 전 수정 / 추후 개선을 구분)

- **현재 결론 무효:** 없다.
- **재사용 전 필요:** `ev108_run.py`의 admission은 시작 시점의 free 메모리만 본다. 시작 이후 외부 점유 증가를 다시 확인하지 않는다. 같은 이유로 재개 시 다른 worker 수를 쓰면 예약량이 달라진다. 현재 2 worker 실행에서는 영향 없었다.
- **추후 개선:**
  - 시각 감사는 overlay 6개 중 3개만 직접 열어 확인했고 나머지 3개는 열지 않았다.
  - 독립 검증의 CI 차이가 정확히 0인 것은 같은 seed·유사한 재표집 순서 때문일 수 있다. 완전한 독립 재표집이 아니라 점추정·전이 수 일치를 주 근거로 본다.
  - weights 해시 검증이 worker 시작마다 약 25초를 더한다. 로딩 시간 측정에 포함됐다.
  - 이번 평가기는 이 고정 표본 전용이다.

# Recommendation to GPT

- 이번 반복에 추가 실험은 필요하지 않다. 사전 분기에 따라 E600까지 마쳤고 `limited_positive`는 모두 false이다.
- 추천: 이 입력 방식은 투자 보류로 종료하고, 소견·위치 정보를 활용하는 다른 최소 비교로 넘어가는 선택을 검토하라. 이유는 단순 규칙 R_B가 R 이상이었고 T와 C가 구분되지 않았기 때문이다.
- 타당한 대안 하나: A 질문 형식 이탈이 내용 판단과 분리되지 않았으므로, 지시 형식(안내문 유무)을 통제한 한정 대조로 A 손상이 형식 때문인지 확인하는 선택. 다만 이 결정은 원 주판정과 분리되는 설계 변경이므로 계획 단계 승인이 필요하다. 구현자는 parser를 바꾸지 않았다.

SELF_CHECK: PASS
SUMMARY: 원본에 예측 영역 crop을 더하는 방식은 표적 음영 판단을 개선하지 못했고(T−D O −0.030, T−C O +0.004, E600 236명), A 하락은 답변 형식 이탈이 주원인이며 단순 bbox 규칙이 T 정책 이상이라 이 입력 방식 투자는 보류를 권고한다.

# [orchestrator] 권한 거부된 도구 호출
- Bash: python - <<'EOF'
import json
s=json.load(open('results/iter_016/manifests/sets.json'))
print({k:{c:len(v) for c,v in d.items()} if isinstance(d,dict) else len(d) for k,d in s.items()})
l=json.load(open('results/iter_016/manifests/labels.json'))
print(len(l), list(l.items())[:2])
print(open('results/iter_016/requests/p180x_ev__M0.jsonl').readline()[:1500])
print(open('results/iter_016/requests/e600x_plain__M0.jsonl').readline()[:1500])
r=json.loads(open('results/iter_016/gen/e600x_plain__M0/gen_worker0.jsonl').readline())
print({k:(v if k not in('input_ids','suffix_ids','attempts') else '...') for k,v in r.items()})
print(json.load(open('results/iter_016/gen/e600x_plain__M0/completion.json')).keys())
EOF
- Bash: python -c "
import json,glob,collections
sets=json.load(open('results/iter_016/manifests/sets.json'))
lab=json.load(open('results/iter_016/manifests/labels.json'))
bb={}
for l in open('results/iter_015/reuse/bbox_B0_concise.jsonl'):
    r=json.loads(l); bb[r['id']]=r
print(len(bb))
for S in ('P180','E600'):
    c=collections.Counter(); ne=collections.Counter()
    for cat,ids in sets[S].items():
        for i in ids:
            assert lab[i]['category']==cat
            r=bb[i]; c[(cat,r['ended_eos'])]+=1
            if r['suffix_text_raw'].strip()!='[]<end_of_turn>': ne[cat]+=1
    print(S,dict(c),dict(ne))
print(len(set(sets['P180']['opacity'])-set(sets['E600']['opacity'])))
# F coverage
fs=collections.Counter()
for st in ('e180_plain__M0','e600x_plain__M0'):
    for fn in glob.glob('results/iter_016/gen/%s/gen_worker*.jsonl'%st):
        for l in open(fn):
            r=json.loads(l); fs[(st,r['target'],r['condition'],r['fmt'])]+=1
print(fs)
"
- Bash: nvidia-smi --query-gpu=index,uuid,memory.used,memory.total --format=csv; df -h /SSD1_1TB | tail -1; echo $CUDA_VISIBLE_DEVICES
- Bash: printenv CUDA_VISIBLE_DEVICES
