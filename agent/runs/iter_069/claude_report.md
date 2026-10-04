# 요약

- **핵심 결과:** 영상으로 직접 확인한 20개 사례(LOW 15, NOT_LOW 5)에서 두 모델 모두 ADC 신호를 판독하지 못했다. SA(ADC 단독 신호 판독)는 MedGemma 1.5와 Qwen2.5-VL-7B 모두 20건을 전부 LOW로 답해 BA 0.50이다. 사전 기준(SA BA≥0.75)을 채우지 못해 "ADC는 읽지만 공동 입력에서 손실" 가설은 검증 대상이 되지 못했다.
- **근거:**
  - A−J는 MedGemma 0.000, Qwen +0.083이라 기준 0.10에 못 미쳤고, 조건부 R(ADC 복제 대조)은 실행하지 않았다.
  - Qwen의 oracle(O)은 BA 1.00이라 질문·parser 형식 문제가 아니다.
  - 원시 JSONL에서 별도 구현으로 다시 계산한 confusion과 BA가 보고서와 완전히 일치했다.
- **주의:** N=20이고 NOT_LOW는 5건이다. SA·A는 이 고정 질문 형식에서 YES/LOW 쪽으로 쏠렸다. 프롬프트를 내용 정확도에 맞춰 바꾸지 않았으므로 질문 형식의 영향은 분리하지 못했다. 이 결과로 DWI–ADC 결합 능력이나 방법 효과를 주장할 수 없다.
- **다음:** 이 DWI–ADC 후보는 기본 인식 부족으로 보류하고 방법 투자는 하지 않는다. 같은 자료에서 프롬프트나 모델을 추가로 바꾸는 시도는 계획상 금지다.

# Work Performed

- 180행 검색을 재현했다. non-longitudinal이고 캡션에 `\bADC\b`와 `\bDWI\b|diffusion[- ]weighted`가 모두 있는 행이 180개였다.
- 그중 DWI·ADC 영상이 분리 캡션으로 구분되는 74개 case를 원문 캡션으로 판정했다. 캡션 근거 후보 26쌍을 골라 영상 52장을 받아 contact sheet 7장을 직접 열어 확인했다.
- 6쌍을 영상 확인 후 제외했다. 수치 overlay, color map, 단면 level 불일치, 대상 불명 등이 사유다. 최종 20 case가 되었고 20개 모두 다른 원천 case이며 영상 file/pixel hash 중복은 0이다.
- 7개 조건(SD, SA, A, J_DA, J_AD, T, O)의 prompt와 parser를 고정했다. 기술 사례(7006, 14955)의 실제 출력에서 형식 오류가 없어 prompt를 수정하지 않았다.
- 입력 tensor 검사, 변조·경합·손상 재사용 거부 검사, 실제 강제 종료·재개 검사, 평가 fixture를 수행했다. 기술 사례 출력과 같은 조건을 두 모델로 돌려 처리량을 비교한 뒤 본실행을 했다.
- 본실행은 두 모델 × 140요청 = 280요청이다. MedGemma는 GPU0에서 worker 2개, Qwen은 GPU1에서 worker 1개로 돌렸고 wall 62초였다.

# Files Changed

- 신규 코드(`research/`):
  - `dd69_fetch.py`: 보완된 다운로더
  - `dd69_cases.py`, `dd69_acquire.py`, `dd69_build.py`, `dd69_spec.py`: 자료 선정·봉인·prompt 명세
  - `dd69_run.py`: 실행기
  - `dd69_eval.py`: 평가기
  - `dd69_test.py`, `dd69_resume_test.py`, `dd69_eval_test.py`: 검사
  - `dd69_verify_eval.py`, `dd69_show.py`: 독립 재계산·요약 출력
- 반입 4개 파일(`mt49_fetch.py`, `mt49_images.py`, `m65_run.py`, `msd56_run.py`)은 수정하지 않았다. `git hash-object` blob이 manifest와 4개 모두 일치한다.
- `m65_run.py`와 `msd56_run.py`는 backend 함수(`load_model`, `env_info`, `build_inputs`, `generate` 등)만 호출했다.
- `mt49_fetch.py`와 `mt49_images.py`는 실행하지 않았다. 계획이 요구한 보완(크기/hash 검증, symlink 거부, iter_069 경로 제한)은 새 `dd69_fetch.py`에 구현했다.
- 결과 경로는 모두 `results/iter_069/` 아래다.

# Commands / Experiments

| 단계 | 결과 |
|---|---|
| `dd69_acquire.py` (영상 52장, 공식 listing 크기·oid 검증) | 성공 |
| `dd69_build.py` (20 case, 요청 140+R 20) | 성공, 요청에 label·caption 없음 |
| `dd69_run.py lock` v1 → tech | 실패 14/174. 원인은 내 누출 검사가 부분문자열로 매칭한 오탐(hypothalamic, yellow)이다. tensor·순서·prompt 검사는 전부 통과였다. |
| `lock` v2 → tech | 두 모델 174건 실패 0 |
| 기술 생성(2 case) | 28건 전부 EOS, 파싱 성공 |
| `dd69_test.py` | 첫 실행 32/35. 실패 3건은 테스트 오류(요청 수 오기재, 프롬프트에 없는 문자열 치환)였고 수정 후 35/35 |
| `dd69_resume_test.py` | 두 모델 PASS |
| `dd69_eval_test.py` | 첫 실행 21/22. 테스트 설계 결함을 고쳐 22/22 |
| 처리량 비교 (MedGemma 1 worker vs 2 worker) | 출력 token 불일치 0 |
| 본실행 launch + verify | 양쪽 exit 0, problems 0 |
| `dd69_eval.py run`, `dd69_verify_eval.py` | 성공, 독립 재계산 일치 |

- 실패한 첫 실행의 결과 파일은 보존했다. `tech_*.json`, `cpu_tests_run1_failed_test_bugs.json`, `eval_fixtures_run1_testdesign_flaw.json`, `protocol_*.json` v1이 그것이다.
- 재개 검사는 w0 3행 저장 직후 `os._exit`, 이어서 torn tail 종료, w1이 torn tail 파일을 읽으며 처리, w0 재시작으로 완료하는 순서였다.
  - 두 모델 모두 14건에 중복·누락이 없었고, 기준 기술 실행과 suffix token 불일치가 0이다.
  - 중간 손상 행은 worker가 거부했다. 답변은 저장됐지만 비용 행이 없는 경우도 verify가 1건 탐지했다.
- 처리량 비교: MedGemma 2 worker는 14요청 wall 18.6초로 1 worker 22.7초보다 짧았고, 요청 평균 지연은 0.63초에서 0.83초로 늘었다. 합산 peak는 17.95GiB로 24GiB GPU 안이다. Qwen은 한 worker가 16.4GiB라 GPU당 1개만 가능하다. 두 구성 모두 출력이 동일하다.

# Results

| 조건 (BA, 20 case) | MedGemma | Qwen |
|---|---|---|
| SA | 0.500 | 0.500 |
| A | 0.500 | 0.567 |
| J (두 순서 평균) | 0.500 | 0.483 |
| rule (SD+SA) | 0.500 | 0.500 |
| T (text-only) | 0.500 | 0.000 (UNCERTAIN 20/20) |
| O (oracle) | 0.567 | 1.000 |

- SD: 두 모델 모두 20/20을 HIGH로 답했다. 선택 집단이 DWI 고신호라 sensitivity 1.0이다.
- SA는 두 모델 모두 20/20이 LOW라 NOT_LOW 5건을 전부 놓쳤다(recall 1.0 / 0.0).
- MedGemma의 A와 J_DA·J_AD도 20/20 YES다.
- MedGemma의 oracle(O)은 LOW 15건 중 13건에서 NO로 답했다. 이는 oracle을 따르지 못한 모델 내용 관찰이며 실행 중단 조건이 아니다.
- A−J는 MedGemma 0.000, Qwen +0.083(95% CI [−0.156, 0.361])이다. J_DA−J_AD는 MedGemma 0, Qwen 0.033이다.
- 사전 기준 판정(`decision`):

  | 항목 | MedGemma | Qwen |
  |---|---|---|
  | recognition_SA_ok | false | false |
  | loss_candidate | false | false |
  | sufficient_A | false | false |
  | sufficient_SA_rule | false | false |
  | followup_method_candidate | false | false |

- 기술 사례 2건을 제외한 18 case(LOW 14, NOT_LOW 4)에서도 SA는 0.500이다. MedGemma의 A·J는 0.500이고, Qwen은 A 0.643, J 0.482였다.
- 비용 비율(rule SD+SA / J, 요청당 latency): MedGemma 1.87(CI [1.52, 2.49]), Qwen 1.54(CI [1.25, 2.10]). 정확도 이점이 없어 방법 검토 조건을 만들지 못했다.
- 한 class가 사라진 bootstrap replicate는 제외했고, 모델·대조별로 약 21~39회이며 JSON에 개수를 기록했다. 상수 응답이라 CI는 [0.5, 0.5]로 퇴화한다.
- 결과 파일:
  - `results/iter_069/eval/report_main.json`
  - `results/iter_069/eval/independent_verify.json`
  - `results/iter_069/gen/main_medgemma`, `gen/main_qwen`
  - `results/iter_069/tests/`
  - `results/iter_069/data/`
  - `results/iter_069/protocol/`

# Goal Progress / Reused Assets

- **도달 단계:** 동작 확인과 가능성 탐색까지다. 확증과 독립 확인은 하지 않았다.
- **실행 유효성:** 입력 tensor 대조, 변조 거부, 재개, 출력 seal, 독립 재계산이 통과했다.
- **설명·반박·미검증:**
  - 반박: 현재 고정 질문 형식에서는 두 모델이 ADC 신호 자체를 구분하지 못한다. 따라서 "인식 후 선택 실패"는 성립하지 않는다.
  - 미검증: 상수 응답이 ADC 인식 부족 때문인지, JPEG에서 정량 신호가 소실된 때문인지, "LOW인가?" 유도 질문의 YES 편향 때문인지는 분리하지 못했다.
  - 이 진단 범위를 넘어서는 일반화는 하지 않는다.
- **재사용:**
  - `m65_run.py`, `msd56_run.py`는 backend 함수 범위로만 사용했다. 공식 chat template·tensor 대조(medgemma/qwen 각 174건), 재개·변조·protocol 연결·GPU 허용 집합 검사를 했다.
  - GPU 허용 집합은 launch가 `CUDA_VISIBLE_DEVICES`(0,1) 밖의 GPU 7 지정을 거부함을 `dd69_test.py`로 확인했다. 논리/물리 대응은 launch 기록의 GPU uuid로 남겼다.
  - `hf_cache`는 `HF_HUB_OFFLINE=1`로 읽기만 했고, 수정 여부를 별도로 검사하지는 않았다.
  - `mt49_*.py`는 미사용이며 보완은 `dd69_fetch.py`로 대체했다. 계획에 적힌 "iter_049 산출물 미덮어쓰기"는 `safe_dest`로 거부함을 확인했다.

# Problems

- **현재 결론을 무효로 만드는 문제:** 없다.
- **해석 한계(결론 범위):**
  - N=20, NOT_LOW 5건이다.
  - 후보 선정과 제외 판정은 캡션과 내가 본 영상에 근거한 수동 판정이다(독립 판독자 없음).
  - 상수 응답 때문에 모델 간 차이와 CI의 정보량이 거의 없다.
  - ADC 신호 label은 caption의 서술(예: 18487의 "no significant decreased or increased")에 의존한다. 영상 지각 수준을 직접 확인한 것은 아니다.
  - 7006과 15611 영상에는 sequence 이름 텍스트가 일부 인쇄되어 있다.
- **재사용 전 수정이 필요한 것:**
  - 이번 중단·재개 검사는 기술 요청 14건 규모다.
  - 비용은 MedGemma 2 worker 동시 실행 하의 요청 latency라 throughput과 같은 수치로 비교하면 안 된다.
- **추후 개선(선택):**
  - 본 프롬프트가 YES/LOW 쪽으로 쏠리는 것을 확인했지만, 계획이 금지한 프롬프트 변경은 하지 않았다.
  - `dd69_run.py`의 `cmd_tech`는 pixel 동일성을 file hash로 간접 확인한다.

# Recommendation to GPT

- DWI–ADC 신호 사용 경로는 "기본 인식 부족, 방법 투자 보류"로 종료하는 것을 권고한다. 이 판단은 이번 두 모델·고정 질문 범위로 제한해야 한다.
- 더 진행할 가치가 있다면 사용자 결정 사항이다.
  - 정량 값을 읽을 수 있는 MRI 입력, 또는 영상 대응이 명확한 다른 과제로 옮기거나 같은 질문을 더 확대하는 것이다.
  - 같은 자료에서 prompt나 모델을 더 바꾸는 것은 계획이 금지했다.
- 기본 신호가 약한 모델에 복잡한 근거 선택 loss를 설계하는 것은 정당화되지 않는다.

SELF_CHECK: PASS
SUMMARY: 영상 확인한 DWI–ADC 20 case에서 두 모델이 ADC 단독 신호를 구분하지 못해(SA BA 0.50, 20/20 LOW 응답) 사전 recognition 기준 미충족, 공동 입력 손실 검증은 성립하지 않아 이 후보 방법 투자는 보류한다(N=20·고정 질문 범위 한정).

# [orchestrator] 권한 거부된 도구 호출
- Bash: python - <<'EOF'
import json,os
man=json.load(open('results/iter_049/image_manifest.json'))
have={r['path'] for r in man['records']}
print(len(have))
out=json.load(open('results/iter_069/cand/cand180_raw_view.json'))
rows={}
for l in open('results/iter_049/raw/train.jsonl'):
    r=json.loads(l); rows[r['title']]=r
for t in ['Case number 14583','Case number 18487','Case number 16138']:
    r=rows[t]; print(t,[r['image_%02d_path'%i] in have for i in range(1,int(r['image_count'])+1)])
EOF
- Bash: CUDA_VISIBLE_DEVICES=0 python dd69_run.py tech --model medgemma --protocol results/iter_069/protocol/protocol_medgemma.json --out results/iter_069/tech/tech_medgemma.json 2>&1 | tail -5
- Bash: CUDA_VISIBLE_DEVICES=1 python dd69_run.py tech --model qwen --protocol results/iter_069/protocol/protocol_qwen.json --out results/iter_069/tech/tech_qwen.json 2>&1 | tail -5
- Bash: echo $CUDA_VISIBLE_DEVICES
- Bash: python - <<'EOF'
import json
d=json.load(open('results/iter_069/eval/report_main.json'))
for m,v in d['models'].items():
    a=v['all_20']
    print('==',m,'SD sens',a['sd_sensitivity_HIGH'])
    for c in ['SD','SA','A','J_DA','J_AD','T','O']: print(c,a['confusion'][c])
    print('rule',a['rule_confusion'])
    print({k:(round(x['diff'],3),[round(y,3) for y in x['CI95']]) for k,x in a['contrasts'].items()})
    print('cost',a['cost'],a['cost_s_mean_per_request'])
    print('notech BA',{k:round(x['BA'],3) for k,x in v['excluding_tech_cases']['conds'].items()})
    print(a['invalid_uncertain']['A'],a['order_disagreement_J'])
EOF
