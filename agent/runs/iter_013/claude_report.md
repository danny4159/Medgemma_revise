# 요약

- **핵심 결과:** 가능성 탐색 단계까지 실행했다. 추가 SFT(C), 좌표 가중 CE(H), DIST²Loss 이식(D)은 시작점 B0 대비 개선이 통계적으로 구분되지 않았다. 사전 확대 기준을 충족하지 못해 확대(train 2,400, LR 비교, seed 재현)는 실행하지 않았다.
- **근거:** V400 양성 200명 기준 S_loc은 B0 0.4977이다. epoch 3(최종) 값은 C 0.5221, H 0.5204, D 0.5253이다. 최종 checkpoint에서 D−C는 +0.0032(95% CI [−0.0136, +0.0203])이고 D−H는 +0.0048(CI [−0.0133, +0.0225])이다. CI 상한이 0.03 미만이라 어느 해석으로도 확대 기준(0.03)에 못 미친다.
- **주의:** V200 checkpoint 선택에서 D는 guardrail(운영 기준: 유효 출력률과 음성 valid_empty 유지) 통과 checkpoint가 없었다. 세 milestone(75/150/225 update) 모두 음성 유지 조건에서 탈락했다. 사전 규칙대로 규칙을 완화하지 않았고, 확대 판정은 "D violates operating guardrail"이다. C도 epoch 2·3이 V200 guardrail에서 탈락해 epoch 1이 선택됐다. 선택 checkpoint의 D−C paired CI는 D에 선택이 없어 계산되지 않았다.
- **다음:** 이번 설정(seed17, 추가 3 epoch, LR 2e-5, alpha 0.1)에서 D의 추가 이득은 약하다. 다른 LR·학습량으로 일반화하지 않는다.

# Work Performed

- 실행기 결함을 수정했다. `generate.py`의 부모 재사용 분기 `lock_protocol` NameError를 고쳤고, 부모 재사용 경로는 실제 실행으로 확인했다.
- 새 모듈을 추가했다.
  - `coord_loss.py`: JSON scanner로 `box_2d` 정수 구간을 얻고 chat sequence token 위치에 연결한다. 자리 가중 H/D loss도 여기 있다.
  - `adapt.py`: 추가 적응 학습기. 부모 adapter 검증, 새 AdamW, 단계 전체 warmup+cosine, 중단·재개, V200 milestone 검증을 담당한다.
  - `adapt_eval.py`: S_loc, guardrail, checkpoint 선택, paired bootstrap, 오류 분해.
  - `adapt_pipeline.py`, `adapt_decide.py`, `adapt_subsets.py`, `adapt_stages.py`: 실행·판정·subset·stage 설정.
- 기존 `train.py`, `sft_data.py`, `select.py` 등은 수정하지 않고 helper를 재사용했다. 계획의 "수정 후 사용" 대신 새 모듈에서 재사용했다.
- subset(train1200, V200 등)과 stage 설정은 결과를 보기 전에 고정했다.
- pilot protocol로 CPU·GPU 검사를 마친 뒤 main protocol을 잠그고 explore를 실행했다.

# Files Changed

- **수정:** `rsna_diag/generate.py` (NameError 수정 1줄).
- **신규 코드:** `rsna_diag/{coord_loss,adapt,adapt_eval,adapt_subsets,adapt_stages,adapt_pipeline,adapt_decide}.py`, `test_rsna_iter013.py`, `test_rsna_iter013_gpu.py`.
- **신규 결과(`results/iter_013/`):** `subsets/`, `stage/`, `protocols/{pilot,main}_protocol.json`, `decisions/exec_config.json`, `tests/`, `pilot/`, `explore/`.
- 미추적 `test_rsna_iter010_gpu.py`와 과거 결과는 그대로 뒀다.

# Commands / Experiments (실제 실행한 명령과 성공/실패)

- **`python test_rsna_iter013.py`:** 43/43 PASS.
- **`test_rsna_iter009.py`, `test_rsna_iter010.py`** (승인 모듈 재검사): 59/59, 70/70 PASS.
- **`python test_rsna_iter013_gpu.py`:** 27/29 PASS. 실패 2건은 전부 E 검사(loss 등가)다.
  - 원인 1: 검사기가 계산 그래프를 유지해 OOM이 났다.
  - 원인 2: gradient 기준 1e-6이 bf16 run-to-run noise보다 tight했다.
  - 두 문제를 고친 뒤 E 검사만 GPU1에서 단독 재실행해 통과했다(`tests/fixtures_iter013_gpu_equiv_rerun.json`). 전체 GPU 검사는 한 번에 통과한 기록이 아니다.
- **`python -m rsna_diag.adapt_pipeline --stage explore --trajs C:2e-5,D:2e-5,H:2e-5`:** 성공. 학습 wall 12,303s(약 3.4h), 보고까지 약 3.5h.
- **`python -m rsna_diag.adapt_decide explore`:** 성공.

# Results (수치와 결과 파일 경로)

**검사 결과** (`results/iter_013/tests/`)

- 좌표 span: 실제 학습 target 3,600개 전부(31,981 좌표 token)가 한 자리 숫자 token으로 분해된다.
- loss: C/H/D가 독립 float64 기준과 일치한다. 추가 항 gradient는 좌표 행에만 걸린다. alpha=0이면 gradient가 CE와 같다. 다음-token shift 검사도 통과했다.
- 실제 모델: C/H/D의 step1 CE와 batch가 동일하다. C가 기록한 H/D 추가 항이 H/D의 추가 항과 같다.
- 재개(D, 결정적): 무중단 U와 중단 후 재개 R을 비교했다. batch ID·token sha·LR·RNG·optimizer step이 정확히 일치했고, loss는 bitwise 일치했다. 최종 adapter digest도 같고, 미완료 validation 복구도 확인했다.
- gradient noise floor: 같은 함수를 두 번 평가해도 상대 L2 약 1.1% 차이가 난다. 비결정적 kernel에서는 gradient 수치 비교에 이 정도 noise가 있다.

**처리량**

- 학습 microbatch: mb2가 약 15.6s/step, mb4가 약 14.1s/step(약 9% 빠름)이다. peak alloc은 9.7GB와 10.8GB다.
- 결정: 재개를 mb2에서 검증했고 이득이 작아 mb2를 채택했다. 학습 worker는 GPU당 1개다. mb2 약 12GB 두 개는 24GB 여유 조건에 안 맞는다.
- 추론(thr48, 48요청): 1 worker/GPU는 12.7 req/min, 2 workers/GPU는 21.1 req/min이다. 두 구성의 greedy 출력은 48/48 토큰이 일치한다. GPU당 2 workers를 채택했다.

**explore 결과** (`results/iter_013/explore/report.json`, `decision.json`)

| 조건 | 선택 epoch(V200) | 최종(epoch 3) F1@0.3 / F1@0.5 / S_loc |
|---|---|---|
| B0 | – | 0.6405 / 0.3550 / 0.4977 |
| C | 1 | 0.6575 / 0.3867 / 0.5221 |
| H | 1 | 0.6625 / 0.3783 / 0.5204 |
| D | 없음 | 0.6705 / 0.3800 / 0.5253 |

- C/H는 epoch 1이 선택돼 선택 checkpoint의 S_loc이 0.4939/0.4916이다. 선택 기준에서는 C−B0 −0.0038이다.
- 최종 checkpoint 대비 B0: C +0.024, D +0.028, H +0.023. 모두 CI가 0을 포함한다.
- 세 조건 모두 최종 checkpoint의 형식·유효 출력률은 1.0이다. 양성 valid_empty는 세 조건 모두 최종에서 0.155다.
- 음성 층 valid_empty는 Normal 0.97, NoOpacity 0.62다. B0의 두 값(Normal·NoOpacity 각각)은 report.json의 `b0.v400`에 있다.
- 독립 brute-force matching으로 C/D 최종 S_loc을 재계산했고 일치했다(D 0.52525, C 0.52208). 재집계와 B0 재사용 검증은 `tests/fixtures_iter013.json`에 있다.

# Goal Progress / Reused Assets (목표 진전·미검증 범위, 재사용 출처·검증)

- **진전:** validated 한계(`lesion-grounding-generalization`)가 유지된다. SFT 이후에도 추가 SFT와 좌표 가중만으로는 위치 정밀도가 뚜렷이 오르지 않는다. 자리별 거리 loss도 이 설정에서 C·H와 구분되지 않는다. 즉 DIST²Loss 이식안의 확대 근거는 얻지 못했다.
- **도달 단계:** 2단계(가능성 탐색)다. train 1,200명, seed17, 225 updates, V200 milestone 3회, V400 최종·선택 checkpoint까지 실행했다.
- **미실행:** 확대(train 2,400, LR 2e-5/5e-5), H의 LR 선택 비교, seed 29/43 재현, 독립 확인(reserve), Kvasir-SEG는 하지 않았다. 확대 기준 미충족으로 계획대로 보류했다.
- **재사용:**
  - 승인 모듈 `geometry/parse/metrics/sft_eval/lora`는 iter_009·010 fixture(59/59, 70/70) 재실행으로 확인했다.
  - B0 V400 응답은 iter_012의 `epoch_05/val_gen`을 부모 경로로 재사용했다. adapter·입력·config를 검증했고 저장된 F1(0.6405/0.355)을 재계산으로 확인했다.
  - iter_012 protocol은 `generate.py` 변경으로 코드 hash 검증이 불가능하다. 그래서 digest와 생성 config digest 일치만 사용했다.
- **주의:** V200과 V400은 개발 subset이다. 독립 검증이 아니다. 선택 checkpoint의 CI는 탐색적 수치다.

# Problems (현재 결론 무효 / 재사용 전 수정 / 추후 개선을 구분)

- **현재 결론 무효:** 없음.
- **해석상 한계**
  - D의 선택 checkpoint가 없어 계획의 선택 기준 D−C CI를 산출하지 못했다. 최종 checkpoint 기준 CI로 보완했다.
  - guardrail이 V200(음성 각 50명)의 valid_empty 변동에 민감하다. 이 탈락이 D의 본질적 결함인지 V200 표본 잡음인지 구분하지 못했다.
  - 학습 말기에도 S_loc이 조건마다 다르게 움직인다. C·H는 epoch 2에서 오르다 3에서 내려갔고, D는 epoch 3까지 계속 올랐다. 수렴은 선언하지 않는다. 짧은 학습(225 updates)의 무개선을 방법 실패로 일반화하지 않는다.
- **재사용 전 수정:** `test_rsna_iter013_gpu.py`는 로직을 고친 뒤 전체 재실행하지 않았다. E 검사만 단독 재실행했다. 새 stage(full)를 열려면 protocol에 잠긴 파일 hash 일치와 GPU 검사를 다시 확인해야 한다.
- **추후 개선:** 선택 checkpoint가 없을 때 `report`가 D−C CI를 최종 checkpoint로 자동 산출하지 않는다. 39↔40 같은 올림·내림 관계는 이번 loss가 표현하지 못한다(계획에 명시).

# Recommendation to GPT

- 판정 후보는 "유효한 음성 결과(현 설정) + 부분 inconclusive"다. 이득이 없다는 방향이지만, guardrail 탈락이 표본 잡음일 가능성이 남는다. 확대하려면 guardrail을 V400 기준으로 삼는 규칙 변경이 필요하고, 이는 이미 본 결과에 맞춘 사후 변경이라 별도 계획과 새 결과 경로가 필요하다.
- D의 최종 checkpoint가 epoch 3까지 오르는 추세를 확인하려면 더 긴 학습이 필요하다. 다만 이번 데이터에서는 D−C +0.003이라 정보 이득이 크지 않다.
- 후속 방법은 자리별 loss보다 R-VLM식 box 기하 supervision이나 미검출·작은 병변 대응을 검토할 만하다. 그전에 SFT 이후 잔여 오류의 빈도·크기 분해(`report.json`의 크기별 recall, 빈 응답)를 근거로 삼길 권한다.

SELF_CHECK: FAIL
SUMMARY: 추가 SFT·좌표 가중 CE·DIST²Loss를 같은 시작점에서 비교한 가능성 탐색을 마쳤고, 최종 S_loc이 B0 0.498에 대해 C 0.522·H 0.520·D 0.525로 서로 구분되지 않으며 D가 선택 guardrail을 통과하지 못해 확대하지 않음. GPU 검사는 27/29에 E 단독 재실행을 더한 기록이라 FAIL로 표기함.

# [orchestrator] 권한 거부된 도구 호출
- Bash: python -c "
import json,os
os.environ['HF_HOME']='/SSD1_1TB/home/milab/daniel/08_medgemma/hf_cache';os.environ['HF_HUB_OFFLINE']='1'
import transformers
from rsna_diag import coord_loss as CL, sft_data, generate
tok=transformers.AutoProcessor.from_pretrained(generate.MODEL_ID,revision=generate.MODEL_REVISION).tokenizer
dig=CL.digit_ids(tok);print(dig)
g=json.load(open('results/iter_010/manifests/gt_manifest.json'))
n=0;nc=0
for s in ('train','validation','confirm'):
    for i in json.load(open(f'results/iter_010/manifests/{s}_ids.json')):
        t=sft_data.target_text([b['yxyx_norm'] for b in g[i]['boxes']])
        enc=tok(t+'<end_of_turn>',add_special_tokens=False)['input_ids']
        # fake full ids: prefix of 5 dummy tokens
        full=[1,2,3,4,5]+enc+[107]
        w=CL.coord_weights(tok,t,full,5,dig)
        nc+=sum(1 for x in w if x>0);n+=1
print(n,'targets ok, coord tokens',nc)
print(sft_data.target_text([[10,20,30,40]]),CL.coord_spans(sft_data.target_text([[0,20,1000,999]])))
"
- Bash: python - <<'EOF'
p='test_rsna_iter013_gpu.py'
s=open(p).read()
s=s.replace('''    pos = [i for i in items if gt[i["id"]]["category"] == "opacity"][:2] + [i for i in items if gt[i["id"]]["category"] != "opacity"][:1]''','''    multi = [i for i in items if len(gt[i["id"]]["boxes"]) > 1][:1]  # 복수 box 양성 1 + 음성 1 (gradient 4회 계산이 24GB 안에 들어가도록 2개)
    pos = multi + [i for i in items if gt[i["id"]]["category"] != "opacity"][:1]''')
open(p,'w').write(s)
EOF
CUDA_VISIBLE_DEVICES=1 python test_rsna_iter013_gpu.py --equiv
- Bash: tail -4 results/iter_013/explore/pipeline.log; for c in C D; do tail -1 results/iter_013/explore/${c}_lr2e-05/train_log.jsonl | cut -c1-90; done; ls results/iter_013/explore/C_lr2e-05
