# 요약

- **핵심 결과:** MediConfusion 175쌍(공식 176쌍 중 1쌍 영상 미확보)에서 MedGemma 1.5의 단일 영상 MC·GD·PS를 모두 실행했고(3,150건), 사전 고정 판정은 **indeterminate**(불확정)입니다. 영상별 GD margin의 상대 순서 O는 0.617(95% CI [0.545, 0.716])로 기준 0.70에 못 미칩니다.
- **근거:**
  - 가장 좋은 단일 영상 baseline은 GD-cal이고 set accuracy가 0.166입니다.
  - 원래 순서 MC는 0.034입니다. 형식 오류가 큽니다(strict parser 기준 invalid 53%).
  - G=O−max S=0.451(CI [0.383, 0.535])로 G 기준은 충족했습니다. 다만 모든 baseline S가 낮아서 생긴 값이고, O가 기준 미달이라 양성은 아닙니다.
  - GD-avg의 개별 정확도는 text-only보다 0.0486 높습니다(CI [0.020, 0.083]). 사전 기준 0.05에 0.0014 못 미칩니다.
  - 단순 대안이 격차를 설명한다는 조건(ΔS≥0.10, CI 하한>0, O와의 차이≤0.05)은 어느 baseline도 충족하지 못했습니다.
- **미검증·주의:** 공식 176쌍 전체가 아니고, 개발 자료이며, 단일 seed입니다. 영상 확보 경로가 공식 다운로드와 다르고, 일부 검사는 기준 직전 수치로 통과했습니다(Problems 참조).
- **다음:** 사전 규칙상 자동 연장 없이 단일 영상 보정 후보를 보류합니다. 새 학습·prompt 탐색은 하지 않았습니다.

# Work Performed

1. **공식 자료 고정:** MediConfusion revision `70544ddd2da23fdb2403587e46e2d287ae2fb27b`의 `dataset.json`, `image_dict.json`, prompts, 평가 소스를 `results/iter_054/source/`에 sha256과 함께 저장했습니다.
2. **영상 확보:**
   - 공식 `download.py`가 쓰는 NCBI `oa_package` 경로는 2026-10 현재 404였습니다. 그래서 PMC OA AWS 공개 버킷(`pmc-oa-opendata`)에서 `image_dict`의 figure 파일만 받았습니다. 이때 ETag/MD5와 크기를 검증했고, 디렉터리 삭제 동작은 쓰지 않았습니다.
   - 228개 중 227개를 확보했습니다.
   - 영상 20115(PMC3094658, pair 10137)는 서로 다른 두 버전(`.1`/`.2`)이 있어 선택 근거가 없습니다. 대체 pair 없이 미확보로 두고, 결과는 최악/최선 범위로 보고했습니다.
3. **자료 정리 결과:**
   - 고유 영상 227장, 고유 PMC 219개, 동일 pixel 중복 0.
   - 가용 175쌍의 연결 성분(공유 영상/PMC/pixel) 57개, 최대 성분 비중 14.9%. 사전 기준(성분 ≥20, 최대 비중 ≤20%)을 충족해 추론 제한에 걸리지 않았습니다.
   - 영상 mode는 L 130·RGB 97이며, L은 3채널 복제로만 처리했습니다. 영상 2장(20186 최대 크기, 20004)은 직접 열어 정상 표시를 확인했습니다.
4. **요청 구성:** `mc54_requests.py`로 18건/쌍, 총 3,150건을 만들었습니다(MC 1,050 / GD 1,050 / PS 1,050, text-only 600건 포함). 추론 행에는 pair ID·정답·caption·category가 없습니다. prompt에 caption 문장이 들어간 행은 0건입니다.
5. **구현:**
   - `mc54_run.py`: MC 생성(cap 128→512→2048), GD(A/B logit 차이), PS(답변 token 평균 log likelihood). 영상은 padding 없이 RGB로 공식 processor에 직접 전달했습니다.
   - logits는 마지막 hidden state에서 fp32 lm_head로 계산합니다. bf16 logits는 0.125 간격으로 양자화되어 A/B margin에 가짜 동점이 생기기 때문입니다. native bf16 margin도 함께 저장했습니다.
   - protocol 잠금, 요청별 claim, worker별 파일, 부분 행 보존, attempt 이벤트 로그, launch gate를 구현했습니다.
6. **평가:** 평가 코드·manifest·completion digest를 결과 확인 전에 잠갔습니다(`eval_lock.json`). 이어서 `mc54_eval.py`, 독립 verifier `mc54_verify.py`, 사전 규칙 `mc54_decide.py`, 최종 봉인 `mc54_seal.py` 순서로 실행했습니다.

# Files Changed

신규 코드(모두 `research/` 아래, 기존 파일 수정 없음):

- `mc54_fetch_source.py`, `mc54_fetch_images.py`, `mc54_build.py`
- `mc54_spec.py`, `mc54_requests.py`, `mc54_run.py`, `mc54_gate.py`
- `mc54_test_model.py`, `mc54_test_runtime.py`, `mc54_tech_runs.py`, `mc54_throughput_summary.py`, `mc54_reuse_check.py`
- `mc54_eval.py`, `mc54_verify.py`, `mc54_decide.py`, `mc54_make_eval_lock.py`, `mc54_seal.py`

반입된 6개 파일(`pg43_run.py`, `rsna_diag/{__init__,generate,geometry,prompts,queue_lock}.py`)은 수정하지 않았습니다.

결과 경로는 모두 `results/iter_054/` 아래입니다.

- `source/`, `data/`: 자료와 요청
- `protocol/`: protocol과 gate
- `tests/`: 검사 결과
- `raw/`: 원시 출력
- `eval/`: 평가·verifier·판정·봉인

# Commands / Experiments

| 단계 | 결과 |
|---|---|
| source 다운로드 | 성공 (8개 파일) |
| 영상 다운로드 | 227/228 성공, 1건 미확보(두 버전 모호) |
| `mc54_build.py` | 성공 (요청 3,150건, 기술 표본 252건) |
| `mc54_test_model.py` v1~v3 | 3회 FAIL, 모두 검사 코드 오류 (아래 참조) |
| `mc54_test_model.py` v4 | 9/9 PASS |
| 기술 단계 실행 `ref_w2` | 252건 완료, 100.7초 |
| 기술 단계 실행 `cmp_w4` | 252건 완료, 70.5초 |
| 기술 단계 실행 `resume` | SIGKILL 후 재개 완료 |
| `mc54_test_runtime.py` v1 | 1건 FAIL (검사의 예상 분기 오류) |
| `mc54_test_runtime.py` v2 | 30/30 PASS |
| 기술 gate 생성 → main protocol → main 실행 | 3,150건 완료, 755초, 종료 코드 모두 0 |
| `mc54_eval.py`, `mc54_verify.py`, `mc54_decide.py`, `mc54_seal.py` | 모두 성공, verifier 8/8 PASS |

- **test_model v1~v3의 실패 원인:**
  - v1: 직접 processor 호출에서 `add_special_tokens=False`를 빠뜨려 BOS가 이중으로 붙었습니다. 4번 fixture의 구분자도 잘못되어 있었습니다.
  - v2: `torch` import 누락.
  - v3: 모델 검사 자체는 통과했습니다. 이후 parser 보정을 반영해 v4로 다시 실행했습니다.
- **test_runtime v1:** alien request ID 검사가 완료 검증에서는 집합 불일치로 먼저 거부되는데, 예상 분기를 "unexpected record"로 잘못 적었습니다. v2에서는 두 분기를 모두 검사했습니다.
- v1 결과 파일(`runtime_checks.json`, `model_checks_v1~v3.json`)은 삭제하지 않고 보존했습니다.
- **기술 단계 worker 비교:** 같은 252건에서 2 worker는 100.7초, 4 worker(GPU당 2개)는 70.5초(214 req/min)였고 출력은 완전히 일치했습니다. 본실행은 4 worker(GPU 0·1에 각 2개)로 했습니다. batch>1은 시험하지 않았습니다.
- **재개 시험:** SIGKILL은 60 record 시점에 가했습니다. 이어서 개행 없는 부분 행(45바이트)을 주입하고 worker 수를 2→3으로 바꿔 재개했습니다. 부분 행은 `.partial.*.bin`으로 보존됐고(sha 일치), 중복 record는 0이며, 기준 실행과 출력이 모두 일치했습니다.
- **메모리:** 샘플링한 GPU 사용량 최대는 2 worker일 때 약 9.2GB, GPU당 2 worker일 때 18.3GB입니다. torch reserved 최대는 8.58GB입니다.

# Results

**전체 완료·비용** (`raw/main/completion.json`)

- 3,150/3,150건, MC 재시도 2건, 비EOS 최종 출력 0건.
- 본 attempt wall 755초.
- device-seconds: 이 디렉터리만 loading 포함 1,504초 / generation 1,367초. 기술 단계 부모 포함 모든 attempt 합산은 1,691초 / 1,527초.
- 요청당 평균 wall: MC 1.75초, GD 0.25초, PS 0.25초.

**시스템별 지표** (strict parser, 175쌍, `eval/report.json`)

| 시스템 | set acc S | 개별 acc | invalid/abstain | 전체 pair 분모 same-answer |
|---|---|---|---|---|
| MC 원래 순서 | 0.034 | 0.271 | 0.531 | 0.320 |
| MC 교환 | 0.011 | 0.263 | 0.549 | 0.303 |
| GD 원래 순서 | 0.120 | 0.546 | 0 | 0.851 |
| GD 교환 | 0.097 | 0.517 | 0 | 0.840 |
| GD-avg | 0.137 | 0.549 | 0 | 0.823 |
| GD-cal | 0.166 | 0.540 | 0 | 0.749 |
| PS | 0.063 | 0.520 | 0 | 0.914 |
| PS-cal | 0.063 | 0.517 | 0 | 0.909 |

- **MC 형식:** 공식 manual parser를 쓰면 MC 원래 순서의 S는 0.091이고 invalid는 0.166입니다.
  - strict 판정이 다른 응답은 1,050건 중 280건입니다.
  - 영상 MC 700건 중 378건은 한 글자 대신 설명문을 냈습니다. 그 가운데 268건은 공식 parser가 설명문 속 문자에서 답을 뽑았습니다. 이는 내용 오류가 아니라 형식·parser 효과입니다.
- **text-only:** 영상 없이 같은 질문만 주면 GD·PS는 개별 정확도 0.50(두 영상에 같은 답)이고, 모든 쌍에서 same-answer입니다.
- **정확한 동점:** 없었습니다. 0.125 이내의 near-tie 슬롯은 GD-avg 7개, GD-cal 10개, PS 19개, PS-cal 25개입니다.

**사전 고정 진단과 판정** (95% CI = 연결 성분 cluster bootstrap 10,000회, seed 54, 단위 57개)

| 항목 | 점추정 | 95% CI | 판정 기준 대비 |
|---|---|---|---|
| O (GD-avg 상대 순서) | 0.617 | [0.545, 0.716] | 기준 0.70 미달 |
| G = O − max S | 0.451 | [0.383, 0.535] | 충족 |
| GD-avg 개별 acc − text-only | 0.0486 | [0.020, 0.083] | 기준 0.05 미달 |
| ΔS GD-cal vs MC 원래 | 0.131 | [0.084, 0.188] | 단순 대안 조건 미충족 |

- GD-cal의 O−S는 0.451이라 단순 대안 조건 "O와의 차이 ≤0.05"를 만족하지 못했습니다.
- 보조 O: PS 0.571, text-only 0.5(정확히 0.5로 회귀 검사 통과). GD-cal과 GD-avg의 O가 쌍마다 같은 구현 회귀 검사도 통과했습니다.
- 민감도: 사전 의심 3쌍을 제외해도 방향은 유지됩니다(O 0.616, G 0.448). leave-one-component-out에서는 O 최소 0.610, G 최소 0.441입니다. 미확보 1쌍을 최악/최선으로 채우면 O ∈ [0.614, 0.619], G ∈ [0.443, 0.455]입니다.
- **최종 판정:** `indeterminate`, 행동은 `hold_no_automatic_extension`입니다. O의 CI 상한이 0.716으로 0.70을 넘기 때문에 negative도 아닙니다.
- 결과 파일: `eval/report.json`, `eval/per_pair.json`, `eval/verify.json`, `eval/decision.json`, `eval/final_seal.json`

# Goal Progress / Reused Assets

**목표 진전**

- 영상별 상대 점수에는 판별 신호가 일부 있지만(O 0.617), 사전 설정한 큰 신호(≥0.70)는 확인되지 않았습니다.
- MC가 낮은 가장 큰 이유는 형식·parser입니다. 같은 모델에서 GD로 바꾸면 invalid가 0이 되고 set accuracy가 0.034에서 0.12~0.17로 올라갑니다.
- 단일 영상 선택은 대부분 한쪽 문자로 쏠립니다. GD-avg의 same-answer 비율이 0.823이므로, 쏠림이 남아 있다는 것은 관찰되었습니다.
- 위 수치는 이 benchmark·이 prompt·한 모델 범위의 관찰입니다. 시각 encoder 병목이나 일반 의료 판독 결함의 증거가 아닙니다.
- 아직 하지 않은 것: 독립 확인, 다른 모델·prompt·seed, 학습 기반 비교(직접 SFT 등), DoubleTake류의 추가 입력 조건, 내부 원인 분석.

**재사용 출처 (reuse_manifest `required_checks` 대조)**

- **blob·의존성·import:** 반입 6개 파일의 worktree blob이 manifest와 모두 일치합니다. import도 성공했고, AST 검사에서 승인 범위 밖 함수 호출은 0건입니다(`tests/reuse_check.json`). 구체적으로 `G.load_model/build_inputs/build_inputs_text/generate/env_info/static_env`와 `pg43_run`의 순수 helper만 썼고, `load_image`(padding)·`load_adapter`·기존 CLI·launcher는 호출하지 않았습니다.
- **공식 processor tensor 대조:** 영상 7건(최대 크기 영상 포함)은 `input_ids`·`pixel_values`·`token_type_ids`가 직접 processor 호출과 일치하고 image token이 256개입니다. 이 호출에는 `add_special_tokens=False`를 썼습니다. text-only 3건에는 image token과 pixel tensor가 없습니다(`tests/model_checks_v4.json`).
- **scoring 독립 대조:**
  - PS의 답변 token 경계는 1,050개 PS 행 전부에서 일치했습니다.
  - fp32 head 기준 token-by-token 독립 계산과 구현의 최대 평균 차이는 0.0185 nats이고, native bf16 대비는 0.15 nats 이내입니다.
  - 질문에 답변 문자열이 이미 등장하는 fixture에서도 실제 답변 위치가 맞았습니다.
  - GD의 마지막 위치 logit은 전체 forward와 일치합니다.
- **launch gate·재개·변조 거부:** 변조 사례 30개 검사가 모두 의도한 분기에서 거부됐습니다. 완료된 out-dir 재실행도 거부됐습니다. main 단계 protocol은 gate 없음/`run=false`/증거 hash 변경/증거 `all_pass=false`를 모두 거부합니다.
- **비용 집계:** 모든 launch attempt를 같은 범위로 집계했습니다. 강제 종료된 프로세스는 하한으로 표시하며, 재개 시험에서 2건이 하한으로 집계됐습니다.
- **최종 연결:** raw–report–verifier–decision은 `final_seal.json`에 digest로 봉인했습니다. verifier는 독립 구현으로 점추정, 10,000회 bootstrap CI(최대 차이 5.6e-17), record digest를 재계산해 일치했습니다.

# Problems

**현재 결론을 무효화하는 것:** 발견하지 못했습니다.

**재사용 전 수정 필요**

- 영상 출처가 공식 download.py가 쓰는 원본 tar.gz와 다릅니다. PMC OA 버킷의 현재 파일이며, 원 ROCO 2018 추출본과 byte 동일한지는 확인하지 못했습니다. 또 1장은 두 버전 중 선택 근거가 없어 pair 10137을 제외했습니다.
- 사전 의심 선별은 어휘 규칙입니다. 3쌍만 표시됐으며 임상 재판독이나 영상 기반 감사가 아닙니다.
- 기술 검사의 일부 수치가 허용 기준 가까이에 있습니다. PS 독립 계산의 평균 차이는 0.0185로, 기준 0.02 직전입니다. 이는 bf16 수치 잡음 수준입니다.
- batch>1과 MC 첫 단계 logits 재사용은 시험하지 않았습니다.
- `mc54_*.py` 일부는 protocol 잠금 코드(`CODE_FILES`)에 포함되고 일부는 평가 잠금에만 포함됩니다. 재사용하려면 이 구분을 정리해야 합니다.

**추후 개선**

- 기존 `rsna_diag/queue_lock` 계열의 일반 한계(과거 리뷰 지적)는 이번 범위에서 다루지 않았습니다.
- 영상 확보 경로를 원본 ROCO 기준으로 교차 확인하는 작업은 하지 않았습니다.

# Recommendation to GPT

- **리뷰할 점:** 판정이 O 기준 미달과 ACC 기준 0.0014 미달에 걸려 있습니다. 문턱은 사후 변경하지 않았습니다. MC의 낮은 성능은 형식 문제가 지배적입니다. 단순 baseline(GD-cal)이 MC를 크게 개선했지만, GD-cal의 same-answer 비율 0.749가 남는 쏠림으로 관찰됩니다.
- **권고:** 사전 규칙대로 단일 영상 보정 후보를 보류합니다. 자동 연장(prompt·seed·pair 추가)은 하지 않습니다. 이어서 조사한다면 별도 계획으로 "pair 정보 없이 쏠림을 줄이는 효과가 직접 SFT 대비 실제로 남는가"를 먼저 판단하는 쪽이 정보 가치가 큽니다.
- **연구 기여:** 새 기여는 주장하지 않습니다. 이번 비교로 확인된 사실은 baseline 수치와 쏠림 관찰까지입니다.

SELF_CHECK: PASS
SUMMARY: MediConfusion 175쌍에서 MedGemma 1.5의 MC·GD·PS 3,150건을 실행해 사전 판정 indeterminate를 얻었다. GD margin 상대 순서 O=0.617(95% CI [0.545, 0.716])로 기준 0.70에 못 미치고, 최고 단일 영상 baseline GD-cal은 set accuracy 0.166이다. 영상 1장은 미확보, 출처는 공식 다운로드와 다르다.

# [orchestrator] 권한 거부된 도구 호출
- Bash: curl -q --fail --silent --show-error --location --proto =https --proto-redir =https -- https://raw.githubusercontent.com/MShahabSepehri/MediConfusion/main/configs/prompts/answering.json
- Bash: CUDA_VISIBLE_DEVICES=0 python mc54_test_model.py results/iter_054/tests/model_checks_v1.json 2>&1 | tail -30
- Bash: grep -n "final_logit_softcapping\|logits_to_keep\|self.lm_head\|def forward\|class Gemma3ForConditionalGeneration" /home/test/.conda/envs/medgemma/lib/python3.11/site-packages/transformers/models/gemma3/modeling_gemma3.py | tail -30
- Bash: grep -n -e final_logit_softcapping -e logits_to_keep -e "self.lm_head" /home/test/.conda/envs/medgemma/lib/python3.11/site-packages/transformers/models/gemma3/modeling_gemma3.py
- Bash: python - <<'EOF'
import json,glob,os
import mc54_run as RUN
out={}
for name,d in (("ref_w2","results/iter_054/raw/tech_ref_w2"),("cmp_w4","results/iter_054/raw/tech_cmp_w4"),("resume","results/iter_054/raw/tech_resume")):
    comp=json.load(open(d+"/completion.json"))
    peak={}
    for l in open(d+"/resource_log.jsonl"):
        for g in json.loads(l)["gpu"]:
            i,u,_=g.split(",");peak[i.strip()]=max(peak.get(i.strip(),0),int(u))
    errs=[f for f in glob.glob(d+"/worker*.stderr") if "Error" in open(f).read() or "Traceback" in open(f).read()]
    c=comp["cost_this_dir_only"]
    out[name]={"workers":comp["workers"],"wall_s_launcher":comp["wall_s_this_attempt"],"n":comp["n_unique"],
      "device_s_incl_loading_union":c["device_seconds_incl_loading_union"],"device_s_generate_union":c["device_seconds_generate_union"],
      "requests_per_min_launcher_wall":comp["n_unique"]/comp["wall_s_this_attempt"]*60,
      "peak_gpu_mem_used_mib_nvidia_smi_sampled":peak,"peak_mem_reserved_gb_max_torch":comp["peak_mem_reserved_gb_max"],
      "stderr_files_with_error":errs,"mean_wall_s_by_kind":comp["by_kind_mean_wall_s"]}
out["note"]="resume wall is only the 3-worker resume attempt (192 remaining requests)"
out["decision"]={"main_workers":4,"gpus":"0,1","per_gpu_workers":2,"reason":"4 workers (2/GPU) finished the same 252 tech requests in less wall time than 2 workers with identical outputs; sampled peak GPU memory leaves >2GB per worker. Batch>1 not tested (padding/variable image count; not needed)."}
# peak check: per-GPU sampled peak + 2GB*workers/gpu within 24576
ok=all(max(v["peak_gpu_mem_used_mib_nvidia_smi_sampled"].values())+0<24576-2048 for k,v in out.items() if k in("ref_w2","cmp_w4","resume"))
out["all_pass"]=bool(ok and not any(v["stderr_files_with_error"] for k,v in out.items() if isinstance(v,dict) and "stderr_files_with_error" in v) and out["cmp_w4"]["wall_s_launcher"]<out["ref_w2"]["wall_s_launcher"])
json.dump(out,open("results/iter_054/tests/worker_throughput.json","x"),indent=1)
print(json.dumps(out,indent=1))
EOF
