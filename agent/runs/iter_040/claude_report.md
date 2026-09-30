# 요약

- **핵심 결과:** PadChest-GR V96에서 직접 SFT B의 F1@0.3은 0.556이고 M0 0.098 대비 크게 올랐다. CE만 추가 학습한 C 대비 문장 대조 M은 −0.005(97.5% CI [−0.038, +0.027])이고, 같은 비용의 C_compute 대비 +0.008([−0.035, +0.049])이다. 두 CI 상한이 모두 0.05 미만이라 사전 판정은 **negative**이고, H192는 실행하지 않았다.
- **근거:** 사전 기준 대로 실제 생성으로 판정했고, 별도 구현(`pg40_verify.py`)으로 재계산한 점수·CI는 저장 결과와 완전히 일치했다(차이 0). B가 이미 문장 구별을 충분히 하고 있어 대조항이 거의 작동하지 않았다.
- **미검증·주의:** V96은 모델 선택이 섞인 개발 자료다. seed는 17 하나이고, MedGrounder 비교는 실행하지 못했다.
- **다음:** 이 대조 설계의 추가 투자는 중단을 권고한다. 나머지 절반 학습 데이터(305명)의 직접 SFT 확대는 별도 계획으로 판단할 후보다.

# Work Performed

## 재사용과 제외

- **재사용:** 반입한 26개 파일은 모두 manifest blob과 일치했다. iter_039의 `pg39_spec`·`pg39_data`·`pg39_build.extract`와 `rsna_diag`의 `lora`·`sft_data`(target 직렬화·prefix 대조·collate)·`generate`·`queue_lock`, `train.py`의 `lr_at`·atomic 저장·RNG/optimizer digest를 사용했다.
- **제외:** `rsna_diag.train.main/run`(RSNA 전용 manifest·매 epoch 전체 validation·select·migration), GIoU/truncated 경로는 호출하지 않았다.

## 새로 만든 코드

- **`pg40_build.py`:** 사전 분할과 잠금.
- **`pg40_train.py`:** 문장별 학습기 하나로 B, C, M을 모두 처리한다. 대조 항은 계획식 그대로이고, 환자별 결정적 dropout seed를 쓴다.
- **`pg40_run.py`:** `pg39_run` 기반 생성 runner. adapter digest 잠금, 단계 gate, 부분 행 복구를 추가했다.
- **`pg40_requests.py`:** V96/V48 요청 생성. H192는 gate가 있어야만 생성한다.
- **`pg40_genjobs.py`, `pg40_eval.py`, `pg40_decide.py`:** 생성 실행, 평가, 사전 규칙 판정.
- **`pg40_verify.py`, `pg40_margin.py`, `pg40_summary.py`:** 독립 재계산, teacher-forced margin 진단, 결과 요약.
- **검사 코드:** `test_pg40.py`, `pg40_gpu_test.py`, `pg40_gen_test.py`.
- **보조:** `run_gpu.py`, `pg40_medgrounder_check.py`.

## 분할과 사전 조건

- T305는 train 적격 922명에서 D24·E288을 뺀 610명을 층별 비례로 절반 뽑았다.
- V96은 기존 E96, V48은 그 절반이다.
- H192는 요청 파일을 만들지 않았다.
- 모든 집합 쌍의 환자·영상·study·pixel 교집합이 0이다(40쌍 검사).
- 대조 적격은 194/305다.
- 문장 검토는 사람의 눈가림 검토가 아니라 규칙 기반 점검만 했다. 비ASCII, 시간 표현, 동일 문장 쌍이 모두 0이다.

# Files Changed

- **신규 코드:** 위 `pg40_*.py`, `test_pg40.py`, `run_gpu.py`.
- **수정한 반입 파일:** 없다(26개 blob 일치 확인).
- **결과:** `results/iter_040/`
  - `data`, `requests`, `protocol`
  - `train`, `train2`, `gen`
  - `eval`, `decisions`
  - `tests`, `medgrounder`
  - `summary.json`

# Commands / Experiments (실제 실행한 명령과 성공/실패)

- **분할·요청:** `pg40_build.py`, `pg40_requests.py val` 성공.
- **CPU 검사:** `test_pg40.py`. 첫 실행 28/29는 테스트 임계값 오류였고, 수정 후 v2 29/29, 회귀 테스트 추가 후 v3 30/30이다.
- **GPU 검사:** `pg40_gpu_test.py`(inproc), `pg40_gpu_test.py`(resume), `pg40_gen_test.py`.
  - inproc 첫 실행은 OOM으로 실패했다. 원인은 검사 코드가 no_grad를 쓰지 않은 것이라 수정했다.
  - inproc 두 번째는 19/21이었다. 실패 2건은 비결정 kernel 잡음이라 결정적 모드 재실행으로 분리했다.
  - inproc 결정적 모드 22/22 통과, resume 12/12 통과, gen 10/10 통과.
- **실패한 학습 실행:** 첫 B 학습(`results/iter_040/train`)은 epoch 2 valce에서 `KeyError`로 실패했다. 평가 manifest에는 `gt_canvas_yxyx`가 없었기 때문이다. 코드를 고치고 protocol v2로 `train2/`에서 처음부터 다시 실행했다. 실패한 dir은 보존했다.
- **학습(train2):**
  - B의 LR 1e-4와 2e-4를 seed 17로 5 epoch, 195 update씩 두 GPU에 병렬로 학습했다.
  - M과 C는 B epoch5에서 LR 1e-5 상수로 학습했고 M은 117 update, C는 173 update까지 갔다. C의 117 update가 C, 173 update가 C_compute다.
- **생성:** V48 4건, B의 V96, M/C/C_compute의 V96 모두 4 worker(GPU당 2)로 실행했고, completion 검증을 통과했다.
- **평가·판정:** `pg40_eval`, `pg40_decide`(ext, select, bgate, ratio, cost, v96), `pg40_verify`, `pg40_margin`.
- **MedGrounder:** 실행하지 않았다. 필수 패키지 9개(albumentations, ensemble-boxes, omegaconf, opencv, scipy, torchvision, nltk, opt-einsum, matplotlib)가 medgemma 환경에 없고, 가중치가 Google Drive 폴더에만 있다. pip install·재구현 금지라 `feasibility.json`에 원인만 기록했다.

# Results (수치와 결과 파일 경로)

## 병렬 구성 (`results/iter_040/tests/gen_throughput.json`)

- 같은 24요청에서 4 worker는 75.3초, 2 worker는 135.6초로 1.80배였고 token이 전부 일치했다.
- peak는 GPU당 17.8GB로, 남는 여유가 worker당 2GB 기준을 넘는다. 4 worker를 채택했다.
- 학습은 프로세스당 peak 9.8GB라 GPU당 1개로 유지했다.

## 학습·선택

- **B의 V48 F1@0.3:**

  | LR | epoch 2 | epoch 5 |
  |---|---|---|
  | 1e-4 | 0.432 | 0.599 |
  | 2e-4 | 0.512 | 0.582 |

- **V48 CE:** LR 1e-4는 0.636→0.644, LR 2e-4는 0.636→0.668로 오히려 늘었다.
- **연장 규칙:** CE가 5% 감소해야 하는 조건 때문에 연장하지 않았다(`decisions/ext.json`).
- **선택:** V48 기준으로 LR 1e-4 epoch 5를 B로 골랐다. 2e-4 epoch 5와 0.017 차이라 잡음 수준이다.
- **B의 V96:** valid 100%, 미해결 truncation 0%로 게이트를 통과했다.
- **비용 비율 r:** 사전 측정값 1.47로 C_compute를 173 update로 잡았다. 실제 누적 학습 시간은 C_compute가 M의 0.9715라 5% 이내다. M의 학습 시간은 C(117 update)의 1.53배다.

## V96 (`eval/v96_MC.json`, `decisions/v96_decision.json`)

| 모델 | F1@0.3 [95% CI] | F1@0.5 | FP/문장 | invalid |
|---|---|---|---|---|
| M0 | 0.098 | 0.013 | 1.93 | 1.6% |
| B | 0.556 [0.487, 0.624] | 0.266 | 0.589 | 0 |
| C | 0.578 | 0.291 | 0.552 | 0 |
| C_compute | 0.565 | 0.294 | 0.568 | 0 |
| M | 0.573 | 0.278 | 0.547 | 0 |

- **M−C:** −0.0052, 97.5% CI [−0.038, 0.027].
- **M−C_compute:** +0.0078, 97.5% CI [−0.035, 0.049].
- **guardrail:** 모두 통과했다. 추론 GPU 시간 비율은 M/C = 0.995이다.
- **판정:** 두 CI 상한이 모두 0.05 미만이라 classification은 negative다.
- **H192 조건:** 두 차이가 각각 0.025 이상이어야 하는데 충족하지 못해 H192는 생성·실행하지 않았다.

## 진단

- **대조항 포화:** M 학습 시작 시 대조 hinge가 거의 0이었다(epoch 1 평균 0.002). B의 teacher-forced margin이 이미 margin 0.1을 넘었기 때문에 대조항이 거의 작동하지 않았다.
- **V96 margin:** B 0.284, C 0.336, C_compute 0.376, M 0.337이다(`eval/margin_v96.json`). M이 C보다 나은 증거는 없다.
- **생성 구별:** V96에서 자기 문장 F1 대비 다른 문장 GT의 F1 격차는 B 0.50, C 0.52, M 0.50으로 이미 높다.

## 독립 재계산

- **결과:** V96의 B/C/C_compute/M 점수와 M−C, M−C_compute CI가 저장 결과와 완전히 일치했다(`eval/verify_v96_MC.json`).
- **범위:** 좌표 변환·JSON 해석·최대 matching·bootstrap은 별도 구현이다. bootstrap의 seed와 index 생성 방식은 같은 것을 썼다. M0는 재계산 대상이 아니고 iter_039에서 저장 점수를 재현하는 데 그쳤다.

# Goal Progress / Reused Assets (목표 진전·미검증 범위, 재사용 출처·검증)

## 구분

- **실행 유효성:** 유효하다. 입력·mask·좌표·CE·gradient·재개·요청 완전성·독립 재계산을 모두 실제로 확인했다.
- **성능 개선:** 직접 SFT 자체는 크게 개선됐다(M0 0.098→B 0.556). 문장 대조의 추가 효과는 관찰되지 않았다.
- **가설 지지:** H_method는 이 조건에서 지지되지 않았다. H_adaptation(추가 CE·학습량이 설명)과 일관된다.
- **신규 기여 가능성:** 이번 결과로는 주장할 근거가 없다.

## 미검증

- **다른 seed·다른 대조 설정:** 확인하지 않았다.
- **T610 이상 학습량과 독립 평가:** H192는 실행하지 않았다. V96은 개발 자료다.
- **baseline 수렴:** B의 F1은 epoch 2→5에서 계속 올랐지만 V48 CE는 올랐다. 5→8 연장은 사전 규칙 때문에 하지 않았다. 따라서 "수렴한 baseline 대비 개선"이라고 말할 수 없다.
- **모듈형 비교:** MedGrounder는 미실행이다.

## 재사용 검증

- **테스트 결과:** `tests/gpu_inproc_v2.json`(22/22), `gpu_resume.json`(12/12), `gen_test.json`(10/10), `fixtures_pg40_v3.json`(30/30).
- **문제 있는 기록도 보존:** `fixtures_pg40.json`(28/29, 임계값 오류), `gpu_inproc.json` 시도 결과는 덮어쓰지 않았다.
- **required_checks 대응:**
  - prefix/tensor·labels·padding: 통과.
  - LoRA 초기 항등, 238개 target, trainable 29,802,496개, base 동결 hash: 통과.
  - CE 독립 대조: 통과.
  - λ=0 환원: 결정적 모드에서 gradient·update가 정확히 일치했다.
  - 문장·ID 교체 fixture, effective-batch·accumulation·단일 그래프 대조: 통과.
  - 중간 optimizer step 재개: 대조 모드와 CE 모드에서 loss·adapter digest 일치.
  - 동시 실행 lock, protocol 변조 거부: 통과.
  - 부분 행 복구: 통과.
  - 단계 gate: decision 없이는 H192 요청과 protocol 생성이 모두 거부됐다.
  - adapter digest·completion 변조 거부, SIGKILL 후 재개: 통과.
  - M0 저장 점수 재현(E96 I-short 0.0984): 통과.
  - 재시도 token 집계와 실제 wall 분리는 `completion.json`의 `cost`에 반영했다.

# Problems (현재 결론 무효 / 재사용 전 수정 / 추후 개선을 구분)

## 현재 결론 무효

없다.

## 재사용 전 수정

- **`rsna_diag/train.py` 의존:** `pg40_train.py`가 이 파일에서 helper만 가져다 쓴다. 이 파일의 RSNA 전용 경로는 호출하지 않지만, 새 실험의 protocol에는 이 파일의 hash가 잠겨 있다. 완전히 분리하려면 helper를 옮기는 정비가 필요하다.
- **T305 표본:** 표본 파일에 유리한 선택은 없지만, 수동 눈가림 검토는 하지 않았다.
- **V48 선택:** 두 후보 차이가 잡음 수준(0.017)이다. B 선택을 독립 결과로 해석하지 않는다.
- **재개 수치 검사:** 결정적 모드에서만 정확 일치를 확인했다. 비결정 모드에서의 재개는 손실 수준으로만 확인했다.
- **M0 재계산:** M0의 복잡한 출력 형식은 iter_039 검증 범위 안에 있고 이번에 별도 독립 재계산은 하지 않았다.

## 추후 개선

- **MedGrounder:** 환경 변경 없이 실행할 수 없었다. 필요하면 별도 환경 승인이 필요하다.
- **처리량:** 4 worker 생성의 실제 처리량은 약 32 req/min(wall)이었다. 이 값은 24요청 검사의 추정과 다를 수 있으니 재사용 시 다시 확인한다.
- **알려진 한계:** 학습 후반에 held-out CE가 늘어난다(과적합). T305는 작아서 실험 결론을 T610 등으로 일반화할 수 없다.

# Recommendation to GPT

1. **계속·진단·전환 중 권고는 전환·보류다.** 이 문장 대조 설계는 중단하는 것이 맞다. B 이후 대조 hinge가 거의 포화돼 M과 C가 구별되지 않았고, 두 CI 상한이 모두 0.05 미만이다.
2. **직접 SFT 자체의 가치는 확인됐다.** M0 0.098→B 0.556, invalid 0, FP/문장은 1.93→0.59다. 단 B의 수렴 여부(F1은 계속 상승, CE는 상승)가 미확인이라, 학습량 확대(나머지 T305 또는 T610)나 5→8 epoch를 같은 baseline에서 검토할 가치가 있다. 이것은 새 loss 탐색이 아니다.
3. **모듈형 baseline이 미실행이다.** 다음 계획에서 MedGrounder를 쓰려면 환경 승인이 필요하다. 필요 없으면 이번 직접 SFT와 비교할 detector+문장 매칭 baseline을 정의하는 것이 우선이다.
4. **Strategy Check.** 이번 결과는 문장 조건부 대조가 직접 SFT 이후 추가 이득을 주지 않는다는 음성 근거다. V96은 개발 자료이고 seed 1개다.
5. 논문 추천 조건은 충족하지 못했다(긍정적 방법 효과 없음).

SELF_CHECK: PASS
SUMMARY: PadChest-GR 문장별 직접 SFT B는 V96 F1@0.3 0.556(M0 0.098)이었지만 문장 대조 M은 CE만 추가한 C 대비 −0.005(CI [−0.038, 0.027])로 개선이 없어 사전 규칙상 negative이며 H192는 실행하지 않았고, MedGrounder는 환경 문제로 미실행이다.

# [orchestrator] 권한 거부된 도구 호출
- Bash: git hash-object pg39_data.py pg39_spec.py pg39_build.py pg39_run.py pg39_eval.py rsna_diag/train.py rsna_diag/lora.py rsna_diag/generate.py rsna_diag/sft_data.py
- Bash: git hash-object rsna_diag/train.py
- Bash: echo $CUDA_VISIBLE_DEVICES
- Bash: CUDA_VISIBLE_DEVICES=0 python pg40_train.py train --run-dir results/iter_040/tests/smoke_M --protocol results/iter_040/tests/protocol_smoke.json --mode ce_contrast --lr 2e-4 --schedule cosine8 --epochs 1 --max-patients 16 --mb 1 --workers 2 --ckpt-every 1000 2>&1 | tail -20
- Bash: CUDA_VISIBLE_DEVICES=1 python pg40_gpu_test.py resume --out results/iter_040/tests/gpu_resume.json
- Bash: sed -i 's/    if not backward:\n        with torch.no_grad/X/' pg40_train.py && python - <<'EOF'
p='pg40_train.py'
s=open(p).read()
s=s.replace("    if not backward:\n        with torch.no_grad():","    if backward is False:\n        with torch.no_grad():")
open(p,'w').write(s)
EOF
grep -n "backward is False" pg40_train.py
- Bash: python - <<'EOF'
import json, importlib, os, urllib.request
out={"checked_at":"2026-09-30","repo":"https://github.com/aehrc/MedGrounder","weights":"Google Drive folder (README): https://drive.google.com/drive/folders/1fwr-Bi2ICb26-MIJVKPxwhHVWGJaaBvz","github_reachable":True}
req=urllib.request.urlopen('https://raw.githubusercontent.com/aehrc/MedGrounder/main/requirements.txt',timeout=30).read().decode()
out["requirements_txt"]=req.split()
mods={'albumentations':'albumentations','ensemble-boxes':'ensemble_boxes','omegaconf':'omegaconf','opencv-python-headless':'cv2','scipy':'scipy','torchvision':'torchvision','nltk':'nltk','opt-einsum':'opt_einsum','matplotlib':'matplotlib','tqdm':'tqdm'}
miss={}
for k,m in mods.items():
    try: importlib.import_module(m); miss[k]="present"
    except Exception: miss[k]="MISSING"
out["execution_env_modules"]=miss
out["gdown_available"]=False
try: importlib.import_module("gdown"); out["gdown_available"]=True
except Exception: pass
# Google Drive folder listing without gdown/API is not available without interactive/no-credential access
try:
    r=urllib.request.urlopen('https://drive.google.com/drive/folders/1fwr-Bi2ICb26-MIJVKPxwhHVWGJaaBvz',timeout=20); out["drive_folder_http_status"]=r.status
except Exception as e: out["drive_folder_http_status"]=repr(e)[:150]
out["conclusion"]="NOT EXECUTED: required packages missing in the fixed medgemma env (pip install / env replacement forbidden by plan) and the Chest ImaGenome-only checkpoint is hosted only in a Google Drive folder; no re-implementation attempted."
os.makedirs("results/iter_040/medgrounder",exist_ok=True)
json.dump(out,open("results/iter_040/medgrounder/feasibility.json","w"),indent=1)
print(json.dumps(out,indent=1))
EOF
- Bash: ps -eo pid,etimes,cmd --sort=start_time
