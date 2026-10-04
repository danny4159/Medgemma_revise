# Work Performed

**요약**

- **핵심 결과:** MSD MRI의 같은 구간에서 전체 병변(W)과 조영증강 병변(E)을 묻고 FLAIR(F), T1gd(T), 교차 16장(J)을 비교했다. D6 → E12 → E48까지 실행했다. 사전 규칙상 확대가 맞았다.
- **근거 (E48, 288구간, MedGemma):**
  - 질문별 고정 정책 Q(W=F, E=T) macro BA는 0.726, 질문 비조건 최선 B(F/F)는 0.698이다. Q−B는 +0.028 [0.004, 0.052]로 사전 기준 0.05에 못 미친다.
  - HD-GLIO는 macro BA 0.945이고 Q−HD는 −0.219 [−0.257, −0.180]이다.
  - 비용은 Q가 HD보다 큰 쪽이다. MedGemma는 약 17~23배, Qwen은 약 1.0~1.4배다.
- **미검증·주의:**
  - 이 결과는 "MRI 정보 선택 기여" 가설을 지지하지 않는다. 대신 sequence 선호가 질문에 따라 갈린다는 관찰만 남는다.
  - 기본 인식이 약하다. MedGemma F의 W 민감도는 0.51, E는 0.34이고, Qwen은 거의 ABSENT로 답한다.
  - E12 확대 후 E36을 합친 E48은 독립 확인이 아니다.
  - 중단·재개 시험, 처리량 비교, 비용 block 반복은 하지 않아 SELF_CHECK는 FAIL이다.
- **다음:** 현재 mask 기반 관측 선택 경로는 보류를 권한다. Q−B와 HD 대비 열세 때문이다.

**상세**

- 계획이 "현재 브랜치에 있다"고 한 `msd56_data.py`, `msd56_run.py`, `s64_*.py`가 작업 트리에 없었다. 커밋 c0166123에서 `git show`로 그대로 복구했고, 수정 없이 반입했다.
- 자료 구성 `m65_data.py`:
  - 기존 `cases.json`의 D6/E48과 6구간을 유지했다. E12는 `SHA256('iter065:'+case)` 순서의 앞 12 case이고, 나머지 36은 E36이다.
  - 구간마다 `equi(n,8)`로 8개 z를 고정했다.
  - F는 FLAIR 채널 0이고 case vmin/vmax로 렌더했다. T는 T1gd 채널 2이고 volume 전체 min-max로 렌더했다. J는 z별 F/T 교차 16장이다.
  - 정답은 W=label∈{1,2,3} 존재, E=label3 존재다. coverage는 8개 z에 해당 label이 있는지로 따로 저장했다.
  - 채널 순서와 label 의미는 `dataset.json`(t1gd=2, 3=enhancing tumour)으로 확인했다.
  - F/T 영상을 직접 열어 같은 기하임을 확인했다.
- 실행기 `m65_run.py`: s64 실행기를 이 과제용으로 바꾼 것이다.
  - 새 `tech` 검사를 넣었다. 공식 processor와 tensor 대조, token·grid, prompt 일치와 누출, 같은 png의 tensor 불변, J 교차 순서, W/E 동일 영상 확인이다.
  - 답변 저장 후 fsync까지의 `read_to_saved_s` 비용 sidecar를 추가했다.
  - 같은 out_dir에서 GPU별 shard를 돌릴 수 있게 launcher를 고쳤다(worker 번호와 lock 공유).
- 평가기 `m65_eval.py`:
  - verify clean과 기록 파일 hash를 확인한다.
  - 현재 requests/labels/manifest/model로 계산한 protocol digest가 verify·protocol과 같아야 한다.
  - 정책 선택 규칙은 D에서만 적용한다. B는 {F/F,T/T}, Q는 {F/T,T/F} 중 macro BA 최대이고, 동률이면 D 비용, 그다음 사전식이다.
  - case 단위 bootstrap은 10,000회, seed65다. 여러 split을 각자 검증한 뒤 합칠 수 있다.
- HD `m65_hd.py`: `hdglio59_hd.py`(blob 8f2435f)를 기반으로 W=pred>0, E=pred==2를 추가했다. `m65_cost.py`, `m65_test.py`, `m65_verify_eval.py`도 새로 만들었다.

# Files Changed

새 파일 (모두 `research/` 안):
- `m65_data.py`, `m65_run.py`, `m65_eval.py`, `m65_hd.py`, `m65_cost.py`, `m65_test.py`, `m65_verify_eval.py`
- 복구한 파일: `msd56_data.py`, `msd56_run.py`, `s64_data.py`, `s64_run.py`, `s64_eval.py`, `s64_test.py`. c0166123의 내용 그대로다.
- `hdglio59_hd.py`는 이미 untracked 상태였고 수정하지 않았다.

결과는 모두 `results/iter_065/`에 있다: data, protocol, tech, gen, hd, eval, tests.

# Commands / Experiments

- `m65_data.py build --split D|E12|E36`: 성공. 요청은 각각 216, 432, 1296건이다.
- `m65_test.py`: 21/21 PASS (`tests/cpu_tests.json`). 정답·coverage, J 교차, E12 순서, 요청·정답·manifest·png hash 일치, 변조 거부, 선택 규칙을 포함한다.
- 두 모델 모두 `lock` → `tech` → `launch` → `verify` 순으로 D, E12, E36을 처리했다.
- tech 검사 fails 0. 단 Qwen E36에서 1건이 실패했다. byte가 같은 근-빈 slice 2개의 tensor 공유를 오배치로 오판한 검사 과엄격이었다.
  - 검사를 "내용이 다른 png만 공유 금지"로 고쳤다.
  - E36을 새 코드 hash로 다시 lock해서 v2로 돌렸다.
  - 실패한 tech 기록(`tech_qwen_E36.json`)은 보존했다.
- 각 모델의 생성은 D 216, E12 432, E36 1296건이고 verify는 모두 문제 0, exit code 0이다.
- 생성 구성은 GPU 0과 1에 모델별 worker 1개씩이다.
  - MedGemma peak는 약 11.4GB, Qwen은 약 16.9GB이다.
  - 한 GPU에 MedGemma 2개를 두면 (11.4+2)×2가 24.5GB를 넘어 규칙상 불허라서 1개를 유지했다. 2-worker 처리량 비교는 하지 않았다.
- HD는 D 3 block(2 case씩), E12, E36에서 실행했다. 모두 rc 0이다.
- 분석:
  - `m65_eval.py`는 D, E12, E36, E48을 두 모델에 모두 실행했다.
  - 독립 재계산은 split별로 BA와 정책 macro가 일치했다(불일치 0).
  - Q−B CI의 독립 근사도 일치했다.
  - HD 회귀: 54 case 중 최대 3 voxel 차이이고 shape는 모두 같다.

# Results

HD label 의미: 고정 공식 readme에는 숫자 대응이 없다. D 6 case에서 MSD label과의 Dice로 확인했다 (`data/hd_label_semantics_D.json`).
- HD 2 ↔ MSD 3(enhancing): Dice 0.24~0.88
- HD 1 ↔ MSD 1·2: Dice 0.51~0.86
- HD 1 ↔ MSD 3: Dice 0.01~0.19

이것은 경험적 확인이며 공식 근거는 아니다. 이 대응은 VLM 성능을 보기 전에 정했고, VLM 성능으로 label을 고르지 않았다.

**D6 (36구간)**
- 선택: MedGemma는 B=F/F, Q=F/T이다. Qwen은 B=T/T, Q=F/T이다.
- MedGemma의 Q−B는 0.0이다.

**E12 → E48 확대**
- 확대 규칙 충족: MedGemma의 W 최고 BA 0.725, E 최고 BA 0.710이 모두 0.65 이상이고 Q−J macro가 0.05 이상이다.
- 주의: Q−J의 대부분은 J의 형식 실패에서 온 값이다. J의 invalid는 E48에서 329/576이다.

**E48 (48 case, 288구간, 576개 질문 항목)**

| 항목 | MedGemma | Qwen |
|---|---|---|
| 단독 최고 BA (W / E) | 0.729(F) / 0.723(T) | 0.601(F) / 0.583(T) |
| Q macro BA / B macro BA | 0.726 / 0.698 | 0.592 / 0.576 |
| Q−B macro | +0.028 [0.004, 0.052] | +0.016 [−0.003, 0.035] |
| Q−J macro | +0.370 | +0.044 |
| Q−HD macro | −0.219 [−0.257, −0.180] | −0.353 [−0.381, −0.325] |

- 질문별 sequence 선호는 방향이 두 모델에서 같다.
  - MedGemma의 F−T는 W에서 +0.222, E에서 −0.056이다.
  - Qwen의 F−T는 W에서 +0.032, E에서 −0.080이다.
  - H1은 방향이 일치하지만, 크기는 MedGemma의 W에서만 크다.
- HD macro BA는 0.945이다 (W 0.95, E 0.94). HD의 W는 MSD 전체 병변과 ontology가 다를 수 있다.
- 형식 실패(invalid): MedGemma는 F 39, T 120, J 329이다. Qwen은 0이다.
- coverage: 양성 FN 대부분이 coverage>0에서 발생했다. MedGemma F의 W FN은 93/189이다. 희소 표집 누락(coverage 0)은 E에서 1건뿐이다. 따라서 주된 원인은 기본 인식 부족이다.
- W/E 정답이 서로 다른 57구간에서 두 답변이 동시에 맞은 수는 MedGemma F/T 8, Qwen 2로 매우 낮다.
- 사례별 F/T oracle(낙관적 참고치)의 평균 BA는 MedGemma 0.732, Qwen 0.598로 선택 여지가 작다.
- 비용 (D6, `eval/D_cost.json`):
  - loading 제외로 비교하면 MedGemma Q/J는 0.296이고 Q/HD는 22.7배다.
  - loading 포함으로 비교하면 MedGemma Q/J는 0.303이고 Q/HD는 17.3배다.
  - Qwen은 loading 제외 시 Q/J 0.61, Q/HD 0.97배이고 loading 포함 시 Q/J 0.75, Q/HD 1.39배다.
  - HD는 block(24개 답변)당 loading 제외 약 15.3초, loading 포함 약 20.8초다.
  - 계획의 기준 "Q/J≤0.8"은 충족했다. 그러나 J의 정확도가 낮아 의미가 약하다.

사전 기준 판정(점추정 기준 / CI 포함 시 모호함):

| 기준 | 판정 |
|---|---|
| Q−B macro ≥ 0.05 | 미달 (MedGemma 0.028, Qwen 0.016) |
| 질문별 Q−B ≥ −0.03 | 충족 |
| Q−J ≥ −0.03 | 충족 (J 형식 실패의 영향) |
| Q/J 비용 ≤ 0.80 | 충족 |
| Q−HD 질문별 ≥ −0.03 | 미달 |
| Q/HD 비용 ≤ 0.80 | 미달 |

결과 파일: `results/iter_065/eval/{D,E12,E36,E48}_{medgemma,qwen}.json`, `D_cost.json`, `hd_regression_vs_iter058.json`, `verify_*_*.json`.

# Goal Progress / Reused Assets

- **목표 진전:** 이번 대조에서는 질문별 고정 정책이 질문 비조건 정책 대비 사전 기준(≥0.05)을 넘지 못했다. HD가 정확도와 비용 모두 앞섰다. 따라서 이 mask 기반 관측 선택 경로에는 새 방법 투자 근거가 없다.
- 이 판단의 범위는 MSD Task01, 8장 sparse 입력, MedGemma/Qwen 두 모델, 이 프롬프트, 이 비용 측정에 한정한다. MRI 전체나 일반적인 근거 선택·결합 능력에 대한 결론이 아니다.
- **재사용 검증:**
  - `hdglio59_hd.py` required_checks:
    - 구간 연결: `m65_hd.py`가 `meta[cid]["slabs"]`와 일치를 assert한다. 통과했다.
    - 채널 순서: 기존 기록과 `dataset.json`으로 확인했다.
    - 회귀: 54 case 최대 3 voxel 차이.
    - 숫자 label 의미: 경험적 Dice로만 확인했다. 공식 근거는 미확보다.
    - 비용 측정: HD 이벤트는 `time.time()`을 쓰고 `predict` 앞뒤에서 `torch.cuda.synchronize()`를 호출한다. monotonic clock이 아니다.
    - 새 출력 경로 사용과 GPU 허용 집합 준수: 확인했다.
  - s64 필수 수정 세 가지는 새 `m65_run.py`와 `m65_eval.py`에 반영했다. protocol 연결 검증, flush 후 비용 측정, GPU 허용 집합 admission 검사다. 재개 시험은 새 경로에서 다시 하지 않았다.

# Problems

**현재 결론을 무효로 만드는 문제:** 없음.

**재사용 전 필수 수정·한계:**
- 중단·재개(SIGKILL, torn tail) 시험을 `m65_run.py`에서 새로 실행하지 않았다. s64의 시험 결과를 승계하지 않았다.
- 비용 측정 한계:
  - 사전 계획의 Q/J/HD 순환 배치 paired block은 하지 않았다.
  - VLM 비용은 D 생성 중 연속 측정값에서 block을 재구성했다. 두 GPU에서 동시에 실행됐다.
  - 반복은 1회뿐이고 CI가 없다.
- D·E12 protocol의 `m65_run.py` hash가 현재와 다르다. E36 앞에서 `cmd_tech`만 수정했기 때문이다. 평가는 `--allow-run-py-drift`로 그 파일의 hash 차이만 허용했고 나머지는 엄격히 확인했다. 생성 경로가 불변이라는 증거는 편집 이력 기록뿐이고, 자동 검증은 아니다.
- HD 숫자 label은 공식 문서로 확인하지 못했다. HD의 W는 MSD 전체 병변과 ontology 차이가 있을 수 있다.
- MedGemma의 verbose 출력(비EOS 후 2048 재시도)이 비용과 invalid의 주원인이다. 계획대로 생성 조건은 바꾸지 않았다.

**추후 개선:** 2-worker 처리량 비교, `m65_eval.py`의 drift 허용을 protocol amendment 기록으로 대체.

# Recommendation to GPT

- 이번 투자 결정은 "mask 기반 질문별 관측 선택 방법을 보류하고 기록을 보존"하는 쪽이다.
  - 보류 이유는 효과 부족(Q−B 0.028<0.05)과 HD 대비 열세(정확도 −0.219, 비용 17~23배)다.
  - 이것은 "기준 미달"이지, 평가하지 않은 능력까지 기각하는 판단이 아니다.
- 보존할 관찰은 sequence 선호가 질문에 따라 갈리는 방향이 두 모델에서 같다는 점이다(W는 FLAIR, E는 T1gd). 효과 크기는 MedGemma의 W에서만 크다.
- 보류가 아니라 질문 전환을 택한다면 연구 질문을 바꿔야 한다. 기본 인식(민감도 0.34~0.51)과 형식 순응이 병목이므로, 어느 모델로 어떤 과제에서 기본 신호가 충분한지부터 확인하는 것이 순서다.
- 이 경우 모델 교체는 후보 반복이 아니라 결정을 바꾸는 비교여야 한다.
- 사용자에게 MR-RATE 접근 권한 확인을 요청할지 여부는 GPT가 판단한다. 나는 채택하지 않았다.

SELF_CHECK: FAIL
SUMMARY: MSD MRI에서 질문(W/E)×입력(F/T/J)을 D6→E12→E48까지 실행해 평가했고, 질문별 고정 정책 Q의 이득(MedGemma Q−B +0.028)이 사전 기준 0.05에 못 미쳤다. HD-GLIO가 정확도(Q−HD −0.22)와 비용(VLM 17~23배) 모두 앞서 mask 기반 선택 투자는 보류를 권하지만, 새 경로의 재개 시험·처리량 비교·비용 paired 반복은 하지 못했다.

# [orchestrator] 권한 거부된 도구 호출
- Bash: mkdir -p results/iter_065/gen/E48_view && python -c "
import json,glob
# 독립 검증용: E12+E36 라벨과 레코드를 합친 임시 view는 만들지 않고 split별로 검증
import subprocess
R='results/iter_065/'
for m in ('medgemma','qwen'):
    for sp in ('D','E12','E36'):
        rep=R+f'eval/{sp}_{m}.json'
        import os
        if not os.path.exists(rep): continue
        r=subprocess.run(['python','m65_verify_eval.py',rep,R+f'gen/{sp}_{m}',R+f'data/labels_{sp}.json',R+f'eval/verify_{sp}_{m}.json'],capture_output=True,text=True)
        print(m,sp,r.returncode,r.stdout[-250:],r.stderr[-200:])
"
