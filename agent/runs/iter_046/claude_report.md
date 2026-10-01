# 요약

- **핵심 결과:** MedGrounder-P를 C와 같은 T305(305명·610문장·765 box)로 직접 적응시켰다. V96에서 F1@0.3은 0.395(미적응 P)에서 0.579(A@0.4)와 0.594(A@sel)로 올랐고, C는 0.578이다. 사전 기준은 모듈형 대안 충분도, C 잔여 이점도 충족하지 못해 `scientifically_inconclusive`다.
- **근거:** A@0.4−P의 F1@0.3은 +0.183(97.5% CI [0.113, 0.255])로 H_adaptation 기준(≥0.05, 하한>0)을 충족했다. A@sel−C의 F1@0.3은 +0.017(CI [−0.072, 0.109])이다. 모듈형 대안 충분 기준에서는 F1@0.3 하한(−0.03)과 FP 상한(0.10)이 미달했다. 비용은 A/P device-seconds 1.009(95% CI [0.984, 1.035])로 거의 같다.
- **미검증·주의:**
  - 단일 seed, 반복 사용한 개발 자료 V96, D24 24명 기반 선택이다.
  - 독립 확인이 아니다.
  - 신규 C 대비 end-to-end 비용은 측정하지 않았다.
  - 변조 거부·barrier 전 child 실패 fixture를 모두 수행하지 못했다. 그래서 SELF_CHECK는 FAIL이다.
- **다음:** 정확도 격차는 적응 예산으로 대부분 설명된다. 잔여 문장별 비교 투자는 보류를 권고하고, 공동 요청·부재 거부는 별도 관찰로 남긴다.

# Work Performed

- 현재 branch·외부 자산·환경·입력 provenance를 검증했다. 환경은 torch 2.5.1+cu124이고 GPU 2장이 보인다.
- 격리 환경의 공식 소스(rev a0aad98d)를 호출하는 T305 학습기 `mg46_train.py`를 구현했다.
  - 공식 `build_medgrounder`, `loss_groundability`, `loss_boxes`, 공식 train augmentation을 그대로 쓴다.
  - strict matcher는 GIoU 예외 fallback만 제거했다.
  - microbatch 누적은 batch 전체 분모(num_boxes, CE class-weight 합)로 재가중한다.
  - augmentation은 (seed, epoch, sample)에 연결해 재현한다.
  - 원자적 checkpoint, digest, flock 단일 소유 lock, 중간 step 재개를 갖췄다.
- 기술 gate를 수행했다.
  - 데이터: 610문장, 765 box, 최대 4 box, 평가 집단과 환자·study·영상·pixel hash 교집합 0.
  - matcher: 공식 matcher와 assignment 200/200 일치, 비유한 값·0 크기 입력은 예외 처리.
  - 누적 정합성: fp64에서 loss 차이 0, grad 상대차 2.1e-8.
  - 처리량: fp32 microbatch 8을 채택(bf16은 이득 없음).
  - overfit 추세, 재개, lock 거부도 확인했다.
- `mg45_*` 추론 wrapper에 `--ckpt-path`와 `t_orig_done` 필드를 추가했다. P 경로 회귀는 D24 logits 차이 0(w2b4)이다.
- 두 LR 설정(S, U)을 병렬로 5 epoch 학습하고 D24로 trajectory를 선택했다. 선택된 U는 15 epoch까지 이어갔고, 사전 규칙상 보완이 필요 없었다.
- 최종 checkpoint(A_U_e5, threshold 0.8)로 V96을 추론하고 6개 paired timing block을 측정했다.
- 보고서, 독립 verifier, completion까지 마쳤다.

# Files Changed

- 신규: `mg46_train.py`, `mg46_gates.py`, `mg46_run.py`, `mg46_eval.py`, `mg46_report.py`, `mg46_verify.py`, `mg46_timing.py`, `mg46_vrun.py`
- 수정: `mg45_mg.py`, `mg45_worker.py`, `mg45_launch.py`
  - 변경은 `--ckpt-path`와 `t_orig_done` 추가뿐이다.
  - 전후 hash와 diff는 `results/iter_046/protocol/mg45_amendment_v2.json`에 있다.
- 결과: 전부 `results/iter_046/` 아래.

# Commands / Experiments (실제 실행한 명령과 성공/실패)

- gate:
  - `data` v1은 실패했다. 업로드 PNG의 파일 hash와 ZIP 원본 raw hash를 잘못 대조한 것이 원인이다. v2에서 정정해 성공했다. v1 결과 파일은 보존했다.
  - `accum` v1·v2는 기준(1e-4) 초과로 실패했다. 원인은 cuDNN 기본 TF32 conv로 확인했고, v3(TF32 끔)에서 통과했다. fp64 확인으로 누적 산식이 정확함을 별도로 확인했다.
  - `matcher`, `aug`, `step`, `overfit`, `throughput`(bf16·fp32), 재개 3종(ref1/ref2/kill)은 성공했다.
- 학습:
  - `mg46_run.py train --trajs S,U --to 5`는 wall 558초에 rc 0이었다.
  - `--trajs U --to 15`는 600초 timeout으로 백그라운드로 넘어갔지만 정상 완료했다.
- D24 평가 6회(S/U e2·e5, U e10·e15)와 구성 비교 3회(w2b4/w2b8/w4b4)는 모두 성공했다. 구성은 w2b4를 채택했다.
- V96 A 추론은 192건에 exit [0,0]이었다. timing block 6개는 모두 attempt 1로 완료했고 재측정은 없었다.
- `mg46_report.py report`와 `mg46_verify.py`는 PASS했고, completion을 생성했다.
- 결정 파일 오류 1건: `mg46_eval.py supp`가 존재하지 않는 `reached_epoch10.json`을 참조해 FileNotFoundError가 났다. 결정이 쓰이기 전이었고 규칙은 바꾸지 않았다. 수정 전후 hash를 `protocol/mg46_eval_amendment.json`에 남겼다. 이 수정으로 잠금 목록의 `mg46_eval.py` hash가 달라졌다.
- OOM은 없었다. 학습 peak는 7.8GB/프로세스였다.

# Results (수치와 결과 파일 경로)

D24 선택 결과(`results/iter_046/decisions/`):

| 후보 | threshold | F1@0.3 | F1@0.5 | FP/문장 |
|---|---|---|---|---|
| U e5 (최종 선택) | 0.8 | 0.7049 | 0.4063 | 0.375 |
| U e2 | 0.6 | 0.6646 | 0.3889 | 0.458 |
| S e5 | 0.6 | 0.6597 | 0.3785 | 0.479 |
| S e2 | 0.2 | 0.5618 | 0.2736 | 1.0 |

- U e10과 U e15는 둘 다 F1@0.3 0.684로 같았다. 보완(supp) 조건 두 가지가 모두 미충족이라 supp는 실행하지 않았다(`supp_decision.json`).
- 선택 threshold 0.8은 후보 격자의 최댓값이다.

V96 (`results/iter_046/eval/report.json`, `verify.json`: PASS):

| 시스템 | F1@0.3 | F1@0.5 | FP/문장 |
|---|---|---|---|
| C | 0.5780 | 0.2911 | 0.552 |
| P@sel | 0.3953 | 0.2335 | 0.604 |
| A@0.4 | 0.5786 | 0.3472 | 0.703 |
| A@sel | 0.5944 | 0.3941 | 0.5625 |

paired 차이(97.5% CI):

- A@0.4−P: F1@0.3 +0.183 [0.113, 0.255]
- A@sel−C: F1@0.3 +0.017 [−0.072, 0.109], F1@0.5 +0.103 [0.027, 0.181], FP +0.010 [−0.109, 0.130]
- C−A@sel: F1@0.3 −0.017 [−0.109, 0.072] → 잔여 이점 기준(≥0.05) 미충족

비용(A/P, 6 paired block, t(5) 95% CI):

- device-seconds 1.009 [0.984, 1.035]
- throughput 0.992 [0.953, 1.033]
- p95 latency 0.997 [0.963, 1.032]

C 재현은 F1 0.5779514로 저장값과 일치했고, C 코드 hash는 git 보관본과 일치했다.

학습: 300 updates가 모두 유한값이고 step이 연속이며 중복이 없었다. step당 약 2.1초(1.45 학습 + 0.65 데이터), 총 12,200문장 노출을 계획했고 실제 실행했다.

# Goal Progress / Reused Assets (목표 진전·미검증 범위, 재사용 출처·검증)

- 새로 알게 된 것: 같은 T305 annotation으로 MG-P를 적응시키면 C와의 F1@0.3 격차(0.183)는 사라진다. 이번 V96에서 A@0.4는 C와 같았고(0.5786 vs 0.5780), A@sel은 +0.017로 C보다 점추정이 높다. 단 CI가 넓어(하한 −0.072) 동등성이나 우위를 확정하지는 못한다.
- 비용은 미적응 MG와 거의 같아 약 27배 비용 이점은 유지된다고 해석되지만, 신규 C 대비 end-to-end 비용은 측정하지 않았다.
- F1@0.5는 A@sel이 C보다 높다(+0.103, CI 하한 > 0).
- 판정 구분:
  - 구현 정합성: gate와 독립 verifier 통과.
  - 가설 지지: 적응 설명은 지지, 모듈형 대안 충분은 CI 폭 때문에 미충족.
  - 신규 기여: 아님. 기존 방법의 직접 적응 진단이다.
- 미검증:
  - 독립 확인, 다른 seed·환자·기관 일반화.
  - 부재 거부와 공동 요청 손실(iter_041 관찰은 유지, 해제하지 않음).
  - 6-GT 문장 1건은 5-query 한계 사례로 평가에 포함했다(A는 최대 5개 예측).
  - 선택된 U e5는 이후 epoch보다 D24 점수가 높지만 D24가 24명뿐이다.
- 재사용: `mg45_mg/worker/launch`, `mg45_eval`, `mg45_report`(ratio_ci·bootstrap·C import), `pg39_spec`, `rsna_diag` helper는 모두 현재 branch에 있어 선별 반입 없이 썼다. P V96 출력은 iter_045 결과를 `allow_code_diff`로 검증해 재사용했다. 근거는 회귀 파일 `tests/regress_P_vs_iter045_final_worker.json`(logits 차이 0)이다.

# Problems (현재 결론 무효 / 재사용 전 수정 / 추후 개선을 구분)

- **현재 결론 무효: 없음.** provenance·무결성 검사와 독립 verifier는 모두 통과했다.
- **계획 항목 중 미완료(그래서 SELF_CHECK FAIL):**
  - 변조·중복·누락·wrong config 거부를 launcher·verify 경로에 직접 적용한 fixture를 수행하지 못했다. 현재는 재개·lock·변조 일부 검증만 있다.
  - barrier 전 child 실패 처리와 동시 launcher 배타성은 수정하지 못했다.
  - 학습 resume 검사는 validation 구간이 아닌 학습 step 중단만 확인했다. validation 경계는 driver가 completion 존재 기준으로 건너뛰는 방식이라 별도로 시험하지 않았다.
- **재사용 전 수정:** 위 launcher 결함, `mg46_eval.py`의 amendment(잠금 hash 불일치가 남음).
- **추후 개선:** 처리량 비교는 D24 48문장 규모라 모델 로딩이 지배한다. 학습 시 batch 증가 이득(microbatch 16)은 측정만 하고 채택하지 않았다.
- 학습 중 box 삭제는 0건이었다(800개 샘플 audit). 그래서 전체 삭제 경로는 합성 사례로만 확인했다.

# Recommendation to GPT

- 이번 결과로 문장별 모듈형 비교는 "적응 예산이 정확도 격차 대부분을 설명하고 비용 이점은 유지된다"는 방향으로 정리할 수 있다. 다만 A−C CI가 넓어 동등성은 확정하지 않는다.
- 이 문장별 양성 비교에는 추가 투자를 보류하고, 공동 요청·부재 거부 질문은 별도 계획으로 분리하길 권한다.
- 보류 범위는 이번에 검증한 양성 문장별 grounding·T305 적응 조건으로 한정한다.
- 리뷰에서는 SELF_CHECK FAIL의 원인인 변조·barrier fixture 미완료와 `mg46_eval.py` amendment를 확인하고, 필요하면 재사용 전 수정으로 분류해 달라.

SELF_CHECK: FAIL
SUMMARY: MG-P를 T305로 적응시켜 V96 F1@0.3이 0.395→0.579(A@0.4)·0.594(A@sel)로 올라 C(0.578)와 비슷해졌고(A@sel−C +0.017, CI [−0.072, 0.109]) 비용은 미적응 MG와 동일(device ratio 1.009)하나, 사전 기준상 불확정이며 변조·barrier fixture 일부는 미수행.

# [orchestrator] 권한 거부된 도구 호출
- Bash: results/environments/medgrounder_iter045/bin/python -c "
import albumentations, torch, timm, transformers, scipy, numpy, cv2
print(albumentations.__version__, torch.__version__, timm.__version__, transformers.__version__, scipy.__version__, numpy.__version__, cv2.__version__)
import albumentations as A
print(hasattr(A.Compose,'set_random_seed'))
"
- Bash: CUDA_VISIBLE_DEVICES=0 python mg46_vrun.py mg46_gates.py data
- Bash: python mg46_vrun.py -c "
import torch, json
import mg46_train as T, mg46_gates as G
dev=torch.device('cuda:0')
torch.backends.cudnn.deterministic=True; torch.backends.cudnn.allow_tf32=False; torch.backends.cuda.matmul.allow_tf32=False
items=T.load_t305(); idx=G.pick8(items)[:4]
ts=T.TrainSet([items[i] for i in idx])
model,crit,_=T.build_model(dev); model.eval()
ss=[ts.get(i,1,17) for i in range(4)]
def run(dtype, mb):
    model.zero_grad(set_to_none=True)
    m=model.to(dtype)
    # inputs
    sam=[dict(s, image=s['image'].to(dtype), boxes=s['boxes'].to(dtype)) for s in ss]
    acc=T.accumulate(m, crit.to(dtype) if False else crit, sam, mb, dev, autocast=False)
    g=torch.cat([p.grad.detach().flatten().double().cpu() for p in m.parameters() if p.requires_grad and p.grad is not None])
    return acc['total'], g
try:
    l1,g1=run(torch.float64,1); l4,g4=run(torch.float64,4)
    print('fp64 mb1 vs mb4 loss diff',abs(l1-l4),'grad rel',float((g1-g4).norm()/g4.norm()))
    model.float()
    lf,gf=run(torch.float32,1); lg,gg=run(torch.float32,4)
    print('fp32 mb1 vs mb4', float((gf-gg).norm()/gg.norm()), 'fp32 mb4 vs fp64 mb4', float((gg-g4).norm()/g4.norm()), 'fp32 mb1 vs fp64 mb4', float((gf-g4).norm()/g4.norm()))
except Exception as e:
    import traceback; traceback.print_exc()
" 2>&1 | tail -15
- Bash: sed -i 's/step=a.steps_main \/\/ 2, steps_main=a.steps_main, supp=False)/step=a.steps_main \/\/ 2, steps_main=a.steps_main, supp=False, autocast=False)/' mg46_gates.py; grep -n "autocast=False)" mg46_gates.py | head; python mg46_vrun.py mg46_gates.py overfit --steps 30
- Bash: python -c "
import subprocess, hashlib, json
fs=['mg45_mg.py','mg45_worker.py','mg45_launch.py']
d=subprocess.run(['git','diff','--']+fs,capture_output=True,text=True).stdout
res={'purpose':'iter_046 amendment: arbitrary checkpoint path (--ckpt-path) for the approved mg45 inference wrapper; P/MS default path unchanged (regression: tests/regress_P_vs_iter045.json)',
 'before_sha256':{f:hashlib.sha256(subprocess.run(['git','show','HEAD:'+f],capture_output=True).stdout).hexdigest() for f in fs},
 'after_sha256':{f:hashlib.sha256(open(f,'rb').read()).hexdigest() for f in fs},'diff':d,
 'iter045_verifier_bool_fix_lock_note':'mg45_verify.py is NOT used by iter_046 unchanged; see mg46 report for the verification path'}
import os; os.makedirs('results/iter_046/protocol',exist_ok=True)
json.dump(res,open('results/iter_046/protocol/mg45_amendment.json','x'),indent=1); print(len(d))"
sed -i 's#"results/iter_046/tests/resume/resume_compare.json"\]#"results/iter_046/tests/resume/resume_compare.json", "results/iter_046/tests/regress_P_vs_iter045.json", "results/iter_046/tests/lock_test/lock_result.json", "results/iter_046/protocol/mg45_amendment.json"]#' mg46_run.py
- Bash: python - <<'EOF'
import hashlib,json
p='mg46_eval.py'
before=hashlib.sha256(open(p,'rb').read()).hexdigest()
s=open(p).read()
s=s.replace('reach = {n: json.load(open(f"{ROOT}/train/{tj}/reached_epoch{n}.json")) for n in (10, 15)}\n    l10 = reach[15]','reach = {15: json.load(open(f"{ROOT}/train/{tj}/reached_epoch15.json"))}  # amendment: reached_epoch10.json은 존재하지 않음(epoch_losses는 epoch15 파일에 모두 포함)\n    l10 = reach[15]')
open(p,'w').write(s)
after=hashlib.sha256(open(p,'rb').read()).hexdigest()
json.dump({'file':p,'before_sha256':before,'after_sha256':after,'reason':'cmd_supp referenced nonexistent reached_epoch10.json (FileNotFoundError before any decision was written); rule unchanged','locked_hash_in_protocol':'before'},open('results/iter_046/protocol/mg46_eval_amendment.json','x'),indent=1)
EOF
python mg46_eval.py supp
