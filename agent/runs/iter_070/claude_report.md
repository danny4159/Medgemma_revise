# 요약

- **핵심 결과:** AutoRG-Brain RGv2는 공식 val FLAIR의 HIGH / MIXED_HIGH_LOW 기술을 기준 이상으로 구분하지 못했다. 예측 mask P와 annotation mask G가 모두 사전 기준 미달이었고, G−P도 사실상 0이다.
- **근거:** 적격 15건(HIGH 4, MIXED 11)에서 P와 G는 BA 0.614, accuracy 0.667, UNKNOWN 0.20으로 같았다. 상수 prior B는 BA 0.50, accuracy 0.733이다. 오류는 모두 모델 내용 오류로 보이고 실행·parser 결함은 아니었다.
- **미검증·주의:** 표본이 작아 CI가 넓다(G−P BA 차 95% CI [−0.125, 0.136], P−B 차 [−0.19, 0.42]). P가 G와 거의 같아(Dice 평균 0.92) G−P는 영역 지원의 영향을 거의 구분하지 못한다. 이 SEG는 BraTS2021로 학습돼 노출이 있고, RGv2는 RadGenome train으로 학습됐다. mask 의미는 whole-lesion(`seg>0`) 가정이다.
- **다음:** 사전 규칙상 현재 AutoRG·FLAIR 신호 기술 후보를 종료하고 기본 능력 부족으로 기록한다. 영역 지원 투자는 근거가 없고, 다중 관측 결합 주장은 이번 결과로 열리지 않는다.

# Work Performed

1. **자료 gate (모델 다운로드 전)**
   - RadGenome-Brain_MRI revision `0348ba42…`의 split과 `BraTS_GLI/modal_wise_finding.json`을 확보했다. val BraTS_GLI는 92행 = 23 case × 4 sequence였고, t2f 보고서 23건이 계획과 일치했다.
   - 출력 전에 23건을 수동 판독해 근거 span과 함께 봉인했다: HIGH 4, MIXED_HIGH_LOW 11, 제외 8. 제외 사유는 "mixed high"만 있음, 참조-only 대상(aforementioned, same lesions), "mixed signal"만 있음이다. 자동 regex는 23/23이 수동과 일치했다.
   - train 161건에 같은 자동 규칙을 적용해 HIGH 36 / MIXED 92 / 제외 33이 나왔다. 따라서 B는 MIXED_HIGH_LOW다.
   - 원본 영상은 `MedOtter/brats2023-gli-dataset`(revision `b032d353…`, cc-by-4.0, 비게이트)에서 적격 15 case의 t2f와 seg만 받았다. shape·affine이 일치했고 sha256을 기록했다.
   - 첫 두 사례(00012 MIXED, 00456 HIGH)의 overlay를 직접 열어 확인했다: `results/iter_070/data/overlay_first2.png`. `seg>0`이 FLAIR 고신호 병변 전체(부종 포함)와 일치했고, 00012는 이질적이며 00456은 균일 고신호였다.
2. **격리 환경과 공식 코드**
   - `results/environments/autorg70`에 venv를 만들어 torch 2.5.1+cu124, nnunet 1.7.1 등을 설치했다. 실패와 복구는 `results/iter_070/env/install.log`에 남겼다.
   - 공식 소스를 SHA `9670703c…`로 고정해 patched 사본을 만들고 5곳만 수정했다: CUDA 덮어쓰기 제거, GPT-2 로컬 경로, `AR70_MAXLEN`, `BeamSearchScorer` import 경로. diff는 `results/iter_070/external/patched/ar70_patch.diff`에 있다.
   - 체크포인트는 `JiayuLei/AutoRG_Brain`(revision `da4ea5cb…`)의 SEG와 RGv2, 그리고 `healx/gpt-2-pubmed-medium`(revision `64952028…`)이다. digest는 `models/weights_manifest.json`에 있다.
3. **실행**
   - SEG를 한 번 실행해 anomaly·anatomy mask를 저장했다.
   - P는 `given_mask`에 예측 anomaly mask를, G는 GT whole-lesion mask(`seg>0`)를 넣었다. anatomy mask는 같은 예측본을 공유하고, 추론 입력에 정답 보고서는 넣지 않았다. 생성은 공식 greedy, max_length 300이다.
   - 동작 확인(단일 worker, 2 case)을 거친 뒤 4 worker(GPU당 2)로 본실행했다.
4. **평가와 검증**
   - `ar70_eval.py`는 보고서 텍스트만 입력으로 받는 blind 규칙 추출기다. 판정은 BA, accuracy, UNKNOWN, 정답 전환 수, seed70 · 10,000회 patient-cluster paired bootstrap이다.
   - `ar70_verify.py`는 eval을 import하지 않고 따로 구현한 labeler로 재계산했다.

# Files Changed

- 신규 코드(모두 untracked): `ar70_labels.py`, `ar70_patch.py`, `ar70_run.py`, `ar70_launch.py`, `ar70_eval.py`, `ar70_verify.py`, `ar70_cost.py`.
- 결과는 모두 `results/iter_070/` 아래에 있다: `data/`, `external/`, `models/`, `env/`, `tech/`, `main/`, `eval/`.
- 기존 파일은 수정하거나 삭제하지 않았다.

# Commands / Experiments

| 단계 | 결과 |
|---|---|
| HF/GitHub 파일·archive 확보, venv 생성 | 성공 |
| 의존성 설치 | 처음에 monai, surface_distance, elasticdeform 등이 빠져 실패 → 설치 |
| numpy 2.4.6 상승 | elasticdeform C 확장 깨짐 → numpy 1.26.4와 opencv-headless 4.10.0.84로 복구, `pip check` 통과 |
| `generation_beam_search` import 오류 | transformers 4.40.2 → 4.26.1 설치(4.30.2·4.26.1 모두 해당 shim 없음) 후 import 경로 패치 |
| 기술 확인(GPU0, 단일 worker, 2 case) | rc=0 |
| 본실행(`ar70_launch.py`, 4 worker) | wall 211.6초, 4개 worker rc=0 |
| `ar70_eval.py` 15건 및 개발 노출 제외 13건 | 성공 |
| `ar70_verify.py` | 12개 검사 모두 통과 |

- **cwd 사고:** 초기에 Bash cwd가 소스 하위로 어긋나 모델·env 로그가 `…/AutoRG_Brain/results/iter_070/`에 저장됐다. 정위치로 이동했고 삭제는 없다.
- **중복 사본:** patched 사본에 같은 7.7GB 사본이 하나 남았다(`external/patched/AutoRG_Brain/results`). rm 권한이 없어 그대로 두었고, 쓰이지 않는다.

# Results

**규모와 입력**
- 적격 15건 × P/G = 30건을 전부 실행했고 N=15 전체가 완료됐다. 환자 클러스터는 15개다.
- 모든 출력이 EOS로 끝났고 cap 도달은 0건이어서 길이 재시도는 없었다.
- 영상 sha256이 manifest와 일치했고, GT mask는 `seg>0`과 일치했다.
- 동작 확인과 본실행에서 00012·00456의 P/G 4개 텍스트가 동일했다(결정성 확인).

**성능 (`results/iter_070/eval/report_all15.json`)**

| | BA | recall HIGH | recall MIXED | acc | UNKNOWN |
|---|---|---|---|---|---|
| P | 0.614 | 0.50 | 0.727 | 0.667 | 0.20 |
| G | 0.614 | 0.50 | 0.727 | 0.667 | 0.20 |
| B (MIXED 상수) | 0.50 | 0 | 1.0 | 0.733 | 0 |

- **사전 기준:** P와 G 모두 BA≥0.70, UNKNOWN≤0.10, B 대비 accuracy +0.10에서 미달이다. 두 class recall≥0.60은 HIGH recall이 0.50이라 미달이다.
- **P/G 전환:** P만 정답 1건, G만 정답 1건이다. 텍스트가 동일한 사례는 3건이다.
- **오류 유형:**
  - HIGH 정답인 00778과 01456은 두 조건 모두 "mixed high and low"로 답했다.
  - UNKNOWN은 P 3건, G 3건이다. 03건 모두 "mixed signal intensity"만, "mixed high signal"만, "enhancement" 언급, "hypointense"만이었다.
  - 추출기가 틀린 경우는 사례별 대조에서 발견하지 못했다.
- **민감도(개발 노출 2건 제외, N=13):** P와 G 모두 BA 0.517, acc 0.615, UNKNOWN 0.231이다(`report_excl_dev2.json`). 결론은 같다.
- **Bootstrap 95% CI(퇴화 replicate 90회 제외):** G−P BA 차 [−0.125, 0.136], P−B 차 [−0.192, 0.417], G−B 차 [−0.192, 0.417].

**비용 (`eval/cost.json`)**
- 예측 mask와 GT mask의 Dice는 평균 0.920, 최소 0.835다. 이 때문에 P와 G의 입력이 거의 같다.
- SEG 평균 25.9초/case, report 평균 9.2초(P)·8.8초(G)다.
- torch 예약 최대 6.0GB, GPU 총 점유 최대 12.75GB/12.69GB(GPU당 2 worker)다.
- **병렬 구성 채택:** 단일 worker 기술 확인 2 case의 평균(약 42초/case)으로 15 case를 환산하면 약 633초(추정)다. 4 worker 실측은 211.6초로 약 3배 빨랐다. 두 구성의 직접 반복 비교는 하지 않았고, 이 추정과 실측 비교로 4 worker를 채택했다. 이 수치는 모델 로딩 시간을 제외한 값이다.
- annotation 획득 비용은 계산에 포함하지 않았다.

# Goal Progress / Reused Assets

- **재사용 자산:** 계획대로 `reuse_assets=[]`이며 기존 runner는 가져오지 않았다. 새 코드는 얇은 wrapper다.
- **연구 질문:**
  - 자료 적합성과 실제 출력까지 완료했다. 전문 모델은 현재 FLAIR 신호 기술의 유용한 baseline 후보 기준을 충족하지 못했다. 영역 지원(G) 효과는 이 자료에서 관찰되지 않았다.
  - 선택·결합 능력에 대해서는 새로 알게 된 것이 없다.
  - 이 결과는 "MRI 전체 불가능"도, "일반 VLM보다 못함"도 의미하지 않는다.
- **미검증:**
  - 원인 구분(보고서 정답의 모호성, mask 의미, 학습 모델의 판독 한계)은 하지 못했다.
  - 공식 test, 다른 sequence·질환, 학습 효과는 미검증이다.
  - 환자 독립성은 case ID 기반이다.
  - 사전 기준 대비 한 사례 제외로 판정이 뒤집히는지는 민감도 분석에서 변하지 않았다. 다만 N이 작아 정밀도는 낮다.
- **계획 대비 사용량:** 계획한 자료 gate, 동작 확인, 본실행(N=15 × 2)을 모두 수행했다. 학습, 확대, 모델 교체, 추가 prompt·parser 변경은 없었다.

# Problems

- **현재 결론 무효:** 없음. 기술 검사 12개가 모두 통과했다.
- **해석 한계 (결론에 영향):**
  - P≈G(Dice 0.92)여서 G−P는 영역 지원 효과를 구분하지 못한다.
  - SEG의 BraTS2021 학습 노출과 RGv2의 RadGenome 학습 노출 가능성이 있다. val이 체크포인트 선택에 쓰였는지는 확인하지 못했다.
  - RadGenome 원 mask 정의가 공개되지 않아 `seg>0`은 가정이다.
  - 보고서 정답은 방사선과 재판독이 아니라 공개 보고서 기술이다.
  - 평가 모집단은 val 15건으로 제한했다.
- **재사용 전 수정:**
  - 이번 실행 경로는 `ar70_*.py`와 patched 소스에 고정돼 있다.
  - 새 입력에 재사용하려면 transformers 4.26.1과 import 패치를 유지해야 한다.
  - 완료 case 재개 시 입력 hash 재검증은 구현하지 않았다. seal 비교만 한다.
- **추후 개선:** 사용하지 않는 중복 사본(`patched/AutoRG_Brain/results`, 7.7GB) 정리. rm 권한이 필요하다.

# Recommendation to GPT

- **결정:** 사전 contract의 "G도 기준 미달" 분기를 적용해 AutoRG·FLAIR 신호 기술 후보를 종료하는 것을 권고한다. 미충족 항목은 BA, UNKNOWN, B 대비 accuracy, HIGH recall이다. 기준 미달이지 연구 가치 부족의 판정은 아니다.
- **같은 자료의 prompt·parser·표본을 보충하거나 test를 열지 않는다.** 정밀도가 낮아 보충해도 결론이 바뀔 가능성이 작다고 판단한다.
- **다음 투자 후보(근거 없는 확대 아님):**
  - 이번 자료는 복수 관측이 필요한 정답이 아니므로 결합 능력 실험으로 넘기지 않는다.
  - 상위 질문으로 돌아가려면 "key image 하나로 답할 수 없는 volume/sequence 질문 + 단순 집계·전문 모듈 baseline"이 필요한 자료를 우선 검토한다. 접근성은 확인이 필요하다(MR-RATE는 HF 인증 권한 blocker가 남아 있다).
- **리뷰에서 확인할 점:** 사례별 원문과 추출 판정 대조(`eval/report_all15.json`의 `per_case`), mask 의미 가정, 노출 한계 기술이 적절한지.

SELF_CHECK: PASS
SUMMARY: AutoRG-Brain RGv2를 공식 val FLAIR 적격 15건에서 예측 mask(P)·정답 mask(G)·prior(B)로 비교한 결과, P와 G 모두 BA 0.614·UNKNOWN 0.20으로 사전 기준 미달이었고 G−P는 0이어서 이 후보를 종료한다. 단 P≈G(Dice 0.92)와 학습 노출 때문에 영역 지원 효과나 일반 능력은 판단하지 못했다.

# [orchestrator] 권한 거부된 도구 호출
- Bash: ls /SSD1_1TB/home/milab/daniel/08_medgemma/research/results | tail -5; nvidia-smi --query-gpu=index,memory.used,memory.total --format=csv; df -h /SSD1_1TB | tail -1; echo $CUDA_VISIBLE_DEVICES
- Bash: curl -q --fail --silent --show-error --location --proto =https --proto-redir =https -- https://raw.githubusercontent.com/ljy19970415/AutoRG-Brain/master/README.md | head -150
- Bash: cd /SSD1_1TB/home/milab/daniel/08_medgemma/research; ls results/environments/ 2>&1; conda env list 2>&1 | head; python --version; grep -n "bert_model_name\|_get_bert" results/iter_070/external/src/AutoRG-Brain-9670703c88e8f599c0c7edc472a5ffce4dd72b0e/AutoRG_Brain/inference/inferenceSdk.py | head
- Bash: conda env list
- Bash: /home/test/.conda/envs/medgemma/bin/python -m venv /SSD1_1TB/home/milab/daniel/08_medgemma/research/results/environments/autorg70
- Bash: /SSD1_1TB/home/milab/daniel/08_medgemma/research/results/environments/autorg70/bin/python -c "
import torch,transformers,nnunet,batchgenerators,SimpleITK,einops
print(torch.__version__,torch.cuda.is_available(),torch.cuda.device_count(),transformers.__version__)
"
- Bash: /SSD1_1TB/home/milab/daniel/08_medgemma/research/results/environments/autorg70/bin/python -m pip freeze > /SSD1_1TB/home/milab/daniel/08_medgemma/research/results/iter_070/env/pip_freeze.txt
- Bash: python -c "
import json,glob,numpy as np,nibabel as nib
M='results/iter_070/main/'
seal=json.load(open(M+'seal.json'))
rows=[];dice={}
for c in seal['cases']:
    a=np.asarray(nib.load(f'{M}masks/{c}-t2f_ab.nii.gz').dataobj)>0; g=np.asarray(nib.load(f'{M}gt/{c}_gt_whole.nii.gz').dataobj)>0
    dice[c]=round(float(2*(a&g).sum()/max(a.sum()+g.sum(),1)),4)
for f in sorted(glob.glob(M+'results/*.json')):
    r=json.load(open(f)); rows.append((r['case'],r['cond'],r['case_wall_s'],r['seg_s_case'],r['attempts'][0]['wall_s'],r['peak_reserved_MiB']))
P=[x for x in rows if x[1]=='P']; G=[x for x in rows if x[1]=='G']
L=json.load(open(M+'launch_result.json'))
T=[json.load(open(f)) for f in glob.glob('results/iter_070/tech/results/*__G.json')]
cost={'main_wall_s_4workers':L['wall_s'],'peak_gpu_used_MiB_total_per_gpu':L['peak_gpu_used_MiB'],
 'mean_seg_s':float(np.mean([x[3] for x in P])),'mean_report_wall_s_P':float(np.mean([x[4] for x in P])),'mean_report_wall_s_G':float(np.mean([x[4] for x in G])),
 'max_torch_reserved_MiB':max(x[5] for x in rows),
 'single_worker_tech_case_wall_s':[t['case_wall_s'] for t in T],'single_worker_est_15cases_s':float(np.mean([t['case_wall_s'] for t in T])*15),
 'speedup_est_vs_single':float(np.mean([t['case_wall_s'] for t in T])*15/L['wall_s']),
 'dice_pred_vs_gt_whole':dice,'dice_mean':float(np.mean(list(dice.values()))),'dice_min':min(dice.values())}
json.dump(cost,open('results/iter_070/eval/cost.json','w'),indent=1);print(json.dumps(cost,indent=1))
# determinism: tech single-worker vs main text
import os
for c in ['BraTS-GLI-00012-000','BraTS-GLI-00456-000']:
    for k in 'PG':
        a=json.load(open(f'results/iter_070/tech/results/{c}__{k}.json'))['attempts'][0]['report'];b=json.load(open(f'{M}results/{c}__{k}.json'))['attempts'][0]['report'];print(c,k,a==b)
"
