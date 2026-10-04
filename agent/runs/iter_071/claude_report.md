# 요약

- **핵심 결과:** RSNA source adapter(R)로 시작한 MRI 직접 SFT는 base에서 시작한 SFT(D)보다 낫지 않았다. E24에서 F1@0.5는 R8 0.130, D8 0.158이다. 둘 다 train-only template(0.153)과 구분되지 않고, 두 VLM 모두 detector M8(0.817)보다 훨씬 낮다.
- **근거:**
  - R8−D8은 −0.028이고 95% CI는 [−0.065, 0.006]이다. H1의 양성 기준(≥0.05, CI 하한>0)은 충족하지 못했다.
  - D8−D8_swap은 +0.017, R8−R8_swap은 +0.016이고 CI가 0을 포함한다. 영상 의존성을 구분할 수 없다.
  - 겹쳐 그린 예측에서 D8/R8은 영상과 무관한 비슷한 박스 묶음을 낸다.
  - M8−D8은 +0.660 [0.531, 0.775]다. 비용은 48요청 workload 기준으로 detector가 약 7.5초(적재 포함), VLM이 1,530–2,007초다. 4개 block 모두 비율 약 0.004–0.005이고 방향이 같다.
- **주의:**
  - T24는 진입 gate 미달로 실행하지 않았다. 이 결과는 T8(8명, 48 예제) 한 학습 조건과 seed17에 한정된다. 일반적인 "전이 없음"이나 MRI에서 VLM이 불가능하다는 결론이 아니다.
  - E24는 개발 평가 자료이며 독립 확인이 아니다. 새 방법·임상 성능·VLM 우위는 어느 것도 검증되지 않았다.
- **다음:** 이 과제(두 category bbox)에서는 detector가 정확도와 비용 모두 충분하다. 여기서 VLM 방법에 더 투자하는 것은 보류를 권고한다.

# Work Performed

- 반입 3묶음을 확인했다. `rsna_diag` 16개 파일, `det_lib`/`det_match`, `sp67_data` 와 SPIDER MHA 보조 함수다. 새 wrapper 위에서 필요한 함수만 호출했고, 과거 RSNA CLI와 parent 재사용 분기는 호출하지 않았다.
- 격리 환경을 준비했다.
  - torchvision 0.29.0+cu130을 `results/environments/tv071`에 설치했다.
  - SimpleITK는 기존 `sitk67`을 재사용했다.
  - COCO_V1 가중치(sha256 `dd69338a…`)는 `results/environments/torch_home071`에 받았다.
- 자료는 기존 D8과 E48에서 만들었다. F139는 열지 않았고(`guard`로 차단), 분할 후 56명이다.
  - T8 8명, 추가 train 16명, V8 8명(V4는 그중 4명), E24 24명이다.
  - 기관 metadata가 없어 층화 없이 hash 순으로 나눴다.
  - 중앙 slice(j−1, j, j+1)는 mask 없이 선택했다. 총 336 요청(56명 × 3 slice × 2 category)이다.
- 학습·평가·비용 코드를 새로 작성하거나 연결했다. `g71_*.py` 21개 파일이다.
- 실행 결과는 다음과 같다.
  - VLM 학습: T8 D/R × LR {2e-4, 2e-5}, 16 epoch.
  - 연장: LR 2e-5 두 trajectory를 32 epoch까지.
  - 생성 평가: V4 12+4개, V8 epoch0 2개와 후보 7개, E24 4 worker.
  - detector: T8, LR 0.005/0.001, 32 epoch.
  - 비용 paired block 4개.

# Files Changed

- 새 파일(루트): `g71_data.py`, `g71_build.py`, `g71_overlay.py`, `g71_overlay_pred.py`, `g71_eval.py`, `g71_train.py`, `g71_gen.py`, `g71_det.py`, `g71_det_stage.py`, `g71_baseline.py`, `g71_analyze.py`, `g71_lock.py`, `g71_final.py`, `g71_verify.py`, `g71_verify_det.py`, `g71_cost.py`, `g71_costrun.py`, `g71_costcheck.py`, `g71_costreport.py`, `g71_launch.py`, `g71_jobs.py`, `g71_techcheck.py`, `g71_runtests.py`, `g71_bound.py`.
- 반입 파일(`rsna_diag/*`, `sp67_data.py`)은 수정하지 않았다.
- 결과: `results/iter_071/` 아래에 data, train, det, gen, eval, decide, cost, tests, launch.

# Commands / Experiments

| 단계 | 결과 |
|---|---|
| `g71_build.py` | 56명, 336행. 겹침 0, F139 교집합 0, 소스 hash 중복 0, bbox 왕복 오차 2e-13, 물리방향 56/56 |
| `g71_techcheck.py` | 11/12 PASS (아래 Problems 참고) |
| 재개 검사 | 중간 step 중단 후 재개. batch/RNG/lr 일치. loss 차이 ≤1.3e-3로 독립 두 실행 간 차이(1.2e-3)와 같은 크기 |
| `g71_runtests.py` | 생성 재개 + torn tail 복구 + token 일치, adapter 변조 거부, 학습 LR 변조 거부 모두 PASS |
| T8 VLM 학습 4개 | GPU당 2개 동시. 학습별 약 26분 wall. 사용 GPU 메모리 약 22.9GB/24.5GB(여유 거의 없음) |
| LR 2e-5 연장 | e8→e16에서 F1이 오른 두 trajectory를 e32까지 (약 17–18분) |
| 생성 평가 | V4 12개는 GPU당 2 worker로 약 13–15분/개. D lr2e-5 e4는 긴 반복 출력으로 중단(미완) |
| detector T8 | 약 190초/개 학습. V8에서 checkpoint와 threshold 선택 |
| E24 | D8/R8 각각 144 요청(2 worker, 약 40–48분 wall), detector 72 영상 |
| 비용 paired | 4 block, 약 1시간 |

- E24 평가 전에 `e24_lock.json`으로 checkpoint·threshold·template·코드를 잠갔다.

# Results

주요 결과 파일:
- `results/iter_071/eval/E24_report.json`
- `results/iter_071/eval/E24_per_patient.json`
- `results/iter_071/eval/cost_report.json`
- `results/iter_071/decide/*.json` (v4_stage, extension_decision, t24_gate, det_select_T8, v8_scores, e24_lock)

**V4 추세(동작 확인 단계):**
- LR 2e-4는 e4 이후 하락했고 val CE도 상승했다(D 0.53→1.35, R 0.52→1.49).
- LR 2e-5는 e8→e16에서 F1이 상승했다(D +0.054, R +0.214). 그래서 연장 기준을 충족했다.

**V8 선택:**
- D8은 `T8_D_lr2e-4_e4`, V8 F1@0.5 0.244다.
- R8은 `T8_R_lr2e-4_e4`, V8 F1@0.5 0.208이다.

**T24 gate: 미진입.**

| | actual | swap | template |
|---|---|---|---|
| D | 0.244 | 0.272 | 0.192 |
| R | 0.208 | 0.226 | 0.192 |

- 두 후보 모두 "실제 − swap ≥ 0.05"가 아니었다.
- D는 template 대비 +0.052 조건만 충족했다.

**E24 (24명, 환자 bootstrap 10,000회, seed 7101):**

| 시스템 | F1@0.5 | F1@0.3 |
|---|---|---|
| D8 | 0.158 | 0.426 |
| R8 | 0.130 | 0.420 |
| M8 (detector) | 0.817 | 0.834 |
| P (template) | 0.153 | 0.422 |

- VLM의 형식 유효율은 두 모델 모두 100%였다.
- category별 F1@0.5는 vertebra가 D 0.29/R 0.23, disc가 D 0.02/R 0.03이다. disc는 거의 못 한다.

**독립 재계산:**
- VLM: 새 parser와 Kuhn 최대 matching으로 환자별 점수 차이가 1e-16 이하다(D8, R8 각 144건). parser 불일치는 0이다.
- detector: 점수 차이가 2e-16이다.

# Goal Progress / Reused Assets

- **실행 유효성:** 자료·정답·좌표·누수 검사를 통과했다. 생성은 요청 단위로 provenance를 남겼다.
- **MRI 적응 효과(관찰):** 이 조건에서 SFT 후 VLM 출력은 template 수준이다.
- **source 전이 근거(H1):** 지지되지 않았다. R−D CI 상한이 0.006이라 사전 최소 가치 0.05보다 작다.
- **H2:** R 이득이 없어 해석 대상이 없다.
- **H3:** 지지됐다. detector가 정확도와 비용에서 모두 충분하므로 이 과제의 VLM 방법 투자 가치는 낮다.
- **신규 기여:** 확정되지 않았다. 알려진 표준 적응의 음성 진단이다.
- **재사용 검증:** `sft_data.build_example`/`collate`, `lora`, `generate`, `det_lib`, `det_match`, `mi19_*`를 실제 입력으로 검증했다. `rsna_diag/train.py`는 helper만 사용했고 실행기는 새로 만들었다.
- **미검증:** 독립 seed, 다른 source seed·epoch의 adapter, T24 이상의 학습량, 다른 prompt와 해상도.

# Problems

**현재 결론 무효: 없음.**

**재사용 전 수정이 필요한 것:**
- `g71_techcheck.py`에서 helper CE와 공식 forward CE의 상대 차이가 1.4e-4로 사전 임계 1e-4를 넘었다(FAIL).
  - lm_head를 label 위치에만 적용하는 경로와 전체 logits 경로의 bf16 수치 차이로 보인다.
  - gradient 상대 차이는 최대 2.1%로 5% 이내다.
- 학습 재개는 중간 step 중단 한 경로만 실제 검사했다. epoch 저장 직후 validation 전 중단과 detector 학습 재개는 실행하지 않았다.
- VLM 최종 adapter는 재개 후 bitwise로 같지 않다(비결정 kernel).

**추후 개선 / 한계:**
- V4 D lr2e-5 e4 생성은 반복 출력이 cap 4000까지 가서 20/24건에서 중단했다. 남은 항목을 전부 F1=1로 가정해도 상한이 0.167로 최고 후보(e32 0.327)보다 낮아 선택에는 영향이 없다. 이 항목은 미완료로 표시했다.
- detector 후보 cap(100) 도달 영상이 있으나 선택 threshold(0.85)가 높아 해석에는 영향이 없다고 판단했다. 완전히 배제하려면 별도 확인이 필요하다.
- VLM 비용 block은 두 GPU가 동시에 하나씩 돌았다. CPU/I/O 경합은 기록하지 않았다.
- 정확한 VRAM peak는 `nvidia-smi` 합 기준이다. 학습 중 사용량은 GPU 용량에 가까워 다른 작업과 겹치면 OOM 위험이 있었다.
- 병렬 구성은 GPU당 2개를 사용했다. 학습은 같은 GPU 2개에서 약 11s/step이었으며 단독 대비 정확한 이득 비교는 하지 않았다.

# Recommendation to GPT

- 계속/진단/전환 중 **전환(이 과제의 VLM 투자 보류)**을 권고한다. 근거는 같은 annotation의 detector가 F1@0.5 +0.66, 비용 약 0.5%이고, 두 VLM은 template과 구분되지 않기 때문이다.
- 보류 범위는 SPIDER T2 두 category bbox와 이 학습 조건이다. 언어 조건 근거 연결, 보고서 생성, 다중 sequence 결합 등 이번에 검증하지 않은 능력에는 해당하지 않는다.
- 같은 질문을 계속하려면 더 큰 학습량(T24)이나 source 변경보다는 VLM만 풀 수 있는 과제(예: 질문에 따라 영역이 달라지는 문항)를 먼저 정해, detector+규칙과 비교하는 설계가 필요하다.

SELF_CHECK: FAIL
SUMMARY: SPIDER T2 두 category bbox에서 RSNA source adapter로 시작한 MRI SFT(R)는 base SFT(D)보다 낫지 않았고(E24 F1@0.5 R −0.028, CI [−0.065, 0.006]), 두 VLM 모두 template·환자 교환 출력과 구분되지 않으며 detector(0.817)가 정확도와 비용(약 0.5%) 모두 우세해 T24 미진입·VLM 투자 보류를 권고한다. 단 CE 대조 사전 임계 1건 미달, epoch 경계 재개 미검사, 단일 seed·E24 개발 자료 한계로 SELF_CHECK는 FAIL.

# [orchestrator] 권한 거부된 도구 호출
- Bash: find /home/test/.conda/envs -maxdepth 1
- Bash: env PYTHONPATH=results/environments/tv071:results/environments/sitk67/site python -c "
import torch,torchvision,SimpleITK as s
from torchvision.ops import nms
print(torch.__version__,torchvision.__version__,s.Version())
import torchvision.models.detection as d
print(nms(torch.tensor([[0.,0,10,10],[1,1,10,10]]),torch.tensor([.9,.8]),0.5))
"
- Bash: ps -eo pid,etime,pcpu,rss,cmd | grep g71_gen | grep -v grep
- Bash: ps -eo pid,etime,pcpu,rss,cmd
- Bash: mkdir -p results/iter_071/tests/launch && python - <<'EOF'
import json
common=['g71_train.py','--init','base','--lr','2e-4','--train-key','T8','--epochs','2','--save-epochs','2','--ckpt-every','3']
jobs={"gpus":[0,1],"per_gpu":1,"jobs":[
 {"name":"resume_ref","gpu":0,"cmd":common+['--run-dir','results/iter_071/tests/resume_ref']},
 {"name":"resume_int_a","gpu":1,"cmd":common+['--run-dir','results/iter_071/tests/resume_int','--stop-after-step','3']}]}
json.dump(jobs,open('results/iter_071/tests/launch/jobs_resume1.json','w'))
EOF
python g71_launch.py results/iter_071/tests/launch/jobs_resume1.json results/iter_071/tests/launch/r1
- Bash: nvidia-smi --query-gpu=index,memory.used --format=csv,noheader; for d in results/iter_071/train/*; do echo $d; tail -n 1 $d/train_log.jsonl | cut -c1-120; done; cat /tmp/claude-1001/-SSD1-1TB-home-milab-daniel-08-medgemma-research/dc6efea1-eed0-4eeb-ab9a-e09761786dcb/tasks/b3e2d9gi8.output
- Bash: python - <<'EOF'
import g71_eval as E, g71_train as TR, g71_data as D
import numpy as np
rows={r['id']:r for r in TR.load_items('V4')}
recs=E.read_jsonl_dir('results/iter_071/gen/V4/T8_D_lr2e-5_e4')
by={r['id']:r for r in recs}
sc={}
for i,row in rows.items():
    if i in by:
        st,b=E.parse_record(by[i],row['category']); sc[i]=E.score_item(st,b,[g['yxyx_norm'] for g in row['gt']])
    else:
        sc[i]={'f1@0.5':1.0}
pats=sorted({r['patient'] for r in rows.values()},key=int)
print(len(by), 'upper bound', np.mean(list(E.per_patient(sc,pats).values())))
print([sc[i]['status'] for i in by])
EOF
- Bash: python - <<'EOF'
import json, numpy as np
import g71_baseline as B, g71_eval as E, g71_train as TR
t=B.train_template('T8')
print({c:(v['source_id'],round(v['train_selection_f1@0.5'],3),len(v['boxes'])) for c,v in t.items()})
rows={r['id']:r for r in TR.load_items('V8')}
sc=B.score_template(t,rows,sorted(rows))
pats=sorted({r['patient'] for r in rows.values()},key=int)
print('P V8 f1@0.5',np.mean(list(E.per_patient(sc,pats).values())),'f1@0.3',np.mean(list(E.per_patient(sc,pats,'f1@0.3').values())))
EOF
