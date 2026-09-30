# 요약

- **핵심 결과:** 규칙이 정한 판정은 **불확정·투자 보류**다. 직접 SFT C는 train-only 문장 retrieval P보다 분명히 좋았다. 다만 영상 교환에 대한 C의 반응은 신뢰구간이 넓어 "prior 수준"과 "영상 구별 성공" 어느 쪽도 확정되지 않았다.
- **근거 (V96 96명·192문장, 개발 자료):**
  - 환자 평균 F1@0.3은 M0 0.0984, C 0.5780, P 0.4292다.
  - C−P는 +0.1488, 97.5% CI [0.0755, 0.2257]다.
  - C text-only는 0.3314로 실제 영상보다 −0.2465 낮다. text-only의 valid율 차이는 5pp 이내였다.
  - 동일 문장 21쌍(17 cluster)에서 C의 B(F1@0.5)는 0.1667, 97.5% CI [0.0147, 0.2917]이다. 사전 기준(상한 ≤0.10 / 하한 >0.10) 어느 쪽도 충족하지 못했다.
  - 같은 21쌍에서 C의 F1@0.5는 원래 영상 0.500, 교환 영상 vs recipient GT 0.333, 교환 영상 vs donor GT 0.500이다.
  - 독립 재계산 결과가 저장 수치와 일치했다(환자별 F1 차이 0).
- **미검증·주의:** V96과 21쌍은 개발 자료이고 단일 seed, 최소 방법 pilot 후보는 선정하지 않았다. B는 GT가 서로 다른 쌍에만 한정된 값이 아니어서, 위치 추적 능력의 지표로 단정하지 않는다. 자세한 내용은 Results와 Problems에 적었다.
- **다음:** 이 후보는 보류를 권고한다. 추가 표본·seed·reserve 개방은 하지 않는다. VinDr 승인 통지 전 외부 다운로드와 평가도 하지 않았다.

# Work Performed

1. 반입 12개 파일의 git blob 해시를 계획의 값과 대조했고 전부 일치했다.
2. `pg43_prep.py`로 T305/D24/V96 manifest를 만들었다.
   - 환자·study·영상·pixel 비중복과 H192/F120 비중복(각 0)을 확인했다.
   - 현재 영상의 file/pixel hash가 기존 요청 행과 일치했다.
3. 동일 문장 환자쌍(seed 4301)을 구성했다.
   - 21쌍·42명·17 cluster, T305 문장 일치 91/192로 계획과 같다.
   - D8은 층 비례로 5+3명을 골랐다.
4. `pg43_retrieval.py`는 TF-IDF를 numpy로 직접 구현했다(sklearn 없음, 설치 없음). D24로 4개 설정을 비교해 `word 1-2gram, k=1`로 잠갔다(F1@0.3 0.536). V96은 선택에 쓰지 않았다.
5. `pg43_run.py`는 `pg41_run`을 복사해 다음을 보완했다.
   - 요청에 modality(image/text)를 명시하고, text-only의 입력 검사와 record 검증을 넣었다.
   - 영상 교환 요청에 donor/recipient 필드를 따로 두었다(GT는 요청에 없음).
   - launcher가 허용 GPU를 실제 여유 메모리 순으로 배정하고, worker당 +2GiB를 GPU별로 합산해 검사한다.
   - `verify_completion`이 modality·image token·현재 영상 hash를 다시 검증한다.
6. D8 동작 확인 gate를 통과한 뒤, 평가 소스를 `pg43_eval.py`로 정하고 M0/C 본생성(각 text-only 192 + 영상 교환 42)을 실행했다.
7. `pg43_eval.py`로 평가하고 `pg43_verify.py`로 독립 재계산했다.

# Files Changed

새 파일(모두 `research/`):

- `pg43_prep.py`, `pg43_retrieval.py`, `pg43_select_retrieval.py`
- `pg43_requests.py`, `pg43_run.py`, `pg43_gate.py`
- `pg43_eval.py`, `pg43_verify.py`, `test_pg43.py`
- 반입 12개 파일은 수정하지 않았다.
- 결과는 `results/iter_043/` 아래 data, retrieval, requests, protocol, gen, decisions, eval, tests, `summary.json`에 있다.

# Commands / Experiments

성공한 실행:

- `pg43_prep.py`, `pg43_select_retrieval.py`, `pg43_requests.py`
- protocol 생성 4건(D8 M0/C, MAIN M0/C)
- D8 launch: M0 2w, C 2w, C 4w
- D8 gate
- 중단·재개 시험
  - 5건 제한 실행 후 worker 파일에 잘린 행을 붙였다.
  - 재개해서 40건을 완료했다.
- MAIN M0 4 worker(2,788초), MAIN C 4 worker(437초)
- `test_pg43.py` 11/11 PASS
- `pg43_eval.py`, `pg43_verify.py`

발견한 문제와 조치:

- 첫 protocol 생성이 출력 폴더 부재로 실패해 폴더를 만들도록 수정한 뒤 재실행했다.
- `verify.json`(첫 재계산)은 M0 응답을 strict JSON으로만 읽어 M0 대부분(188/192)이 invalid가 됐다. M0에는 thinking 표지가 붙기 때문이다.
  - 이 파일은 보존했다.
  - 별도 추출기를 추가해 `verify_v2.json`을 만들었고, M0 환자별 F1이 pipeline과 완전히 일치했다.
- OOM은 없었다.

# Results

D8 gate: `results/iter_043/decisions/D8_gate.json`, `run=true`.

- 실제 영상 D8이 기존 출력(M0 iter_039, C iter_041)과 token 일치했다(0 불일치).
- text-only는 image token 0개, `pixel_values` 없음, 입력 키는 `input_ids/attention_mask/token_type_ids`뿐이다.
- self-swap 8건은 실제 요청과 입력·출력이 일치했다.
- C 2w와 4w 40건은 token 일치했다.
- 교환 42행은 모두 다른 환자의 영상이며 manifest 영상과 일치한다.

worker 선택:

| 구성 | 처리량(req/min) | 비고 |
|---|---|---|
| C 2 worker | 15.9 | worker 수와 GPU 수가 같음 |
| C 4 worker(GPU당 2) | 26.5 | 채택 |

- 채택한 4 worker의 GPU별 peak 점유는 약 17.8GiB로, 남은 여유가 6.6GiB(기준 4GiB 이상)였다.
- worker당 peak reserved는 8.35GiB다.

V96 주지표(환자 평균 F1@0.3, 95% CI 포함):

| 시스템 | F1@0.3 | F1@0.5 | valid율 |
|---|---|---|---|
| M0 real | 0.0984 | 0.0130 | 0.984 |
| C real | 0.5780 | 0.2911 | 1.0 |
| P | 0.4292 | 0.1762 | 1.0 |
| M0 text | 0.1736 | 0.0087 | 0.990 |
| C text | 0.3314 | 0.0990 | 0.995 |

- 비교(F1@0.3, 97.5% CI):
  - C−M0 +0.480 [0.403, 0.559]
  - C text−P −0.098 [−0.180, −0.014]
- C 재실행(iter_041)과 iter_040 C는 192건 token이 모두 일치했다.
- 층별(문장 수준 평균, F1@0.3):
  - T305에 있는 문장 91개: C 0.716, P 0.599.
  - T305에 없는 문장 101개: C 0.453, P 0.276.
  - 작은 box(중앙값 미만) 96개: C 0.399, P 0.222.
  - 복수 box 47개: C 0.545, P 0.416.

동일 문장 쌍(F1@0.5, 97.5% CI, C):

- B 0.1667 [0.0147, 0.2917]
- GT 교차 분리도 0.5476 [0.341, 0.794]
- 참고로 F1@0.3에서는 B_03 0.0437 [−0.056, 0.127]로 작았다. C는 IoU 0.3에서는 영상 교환에 거의 반응하지 않고, 0.5에서만 반응이 관찰됐다.
- M0의 B는 −0.016이다. M0의 F1@0.5가 바닥이라서 정보가 없다.

판정 조건표(`decision`):

| 조건 | 충족 |
|---|---|
| 양성: P−C 하한 ≥ −0.03 | 미충족 |
| 양성: B_C 상한 ≤ 0.10 | 미충족 |
| 음성: C−P 하한 > 0.03 | 충족 |
| 음성: B_C 하한 > 0.10 | 미충족 |

- 양성과 음성 조건이 모두 완결되지 않아 판정은 불확정이다.
- 사후 기술 분석(판정에 미사용): GT가 IoU 0.5에서 다른 12쌍만 봐도 C의 B는 0.167 [0.0, 0.333]이다. GT가 같은 9쌍에서도 0.167이었다. B는 위치 추적만이 아니라 영상별 난이도 차이도 반영한다.

주요 파일:

- 평가: `results/iter_043/eval/report.json`, `report_per_item.json`
- 재계산: `verify.json`(M0 strict, 참고용), `verify_v2.json`
- 검사: `results/iter_043/tests/fixtures_pg43.json`

# Goal Progress / Reused Assets

- **직접 확인한 것 (개발 자료·단일 seed·V96):** C의 문장 grounding 개선 중 train-only 문장 prior로 설명되는 몫은 크지만(P 0.429 대 C 0.578) 전부는 아니다. C는 P를 넘고, 영상을 빼면 크게 떨어진다(text-only −0.247).
- **미확인:** 환자별 위치 구별이 중요한 잔여 문제인지는 확정하지 못했다. 정밀도(21쌍·17 cluster)가 부족하고, 12쌍 위주로 GT가 분리되며, 문장이 쉬운 쪽으로 치우쳐 있다.
- **한 줄 결론:** 위치 구별을 위한 method pilot을 지금 시작할 근거는 부족하다. C의 prior 이상 영상 사용 근거는 부분적(IoU 0.5)으로만 있다.
- **재사용 출처와 검증:** 반입 12개는 blob이 일치했다.
  - `pg39_spec/pg39_data`: 순수 함수로 재사용했다. `pg43_prep`의 hash·연결 검사와 D8 기존 출력 재현으로 확인했다.
  - `pg41_verify`: 순수 함수로 독립 재계산에 재사용했다.
  - `pg41_run`: 수정하지 않고 `pg43_run.py`로 복사해 보완했다. 기존 `pg41_run`은 iter_041/042 산출물 검증용으로 보존한다.

# Problems

**현재 결론 무효:** 없다.

**재사용 전 수정 (`pg43_run.py`):**

- 중단 재개는 잘린 행 복구와 일부 완료 기록(10/40)으로 확인했다. 진짜 SIGKILL 시험은 하지 않았다.
- 계획 대비 요청 수가 늘었다. self-swap 회귀 8건×3회와 재개 시험 40건이 추가됐다. D8 총 152건(계획 96건). 본생성 468건은 계획과 같다.
- 두 protocol이 같은 코드 목록을 잠그므로, 실행기 수정 후 재사용하려면 새 protocol이 필요하다.

**추후 개선:**

- 평가 소스(`pg43_eval.py`)는 protocol이 아니라 report의 hash로 기록했다. 평가 시점의 별도 잠금 파일은 만들지 않았다.
- 판정 규칙 중 "교환 출력이 donor GT에 대응"의 조작적 정의(corr 평균>0, CI 하한>0)는 결과 확인 전에 코드로 고정했으나 plan에는 없던 해석이다.
- M0 응답은 pipeline parser와 별도 추출기 결과가 일치했지만, 일반 parser 대체 승인은 아니다.

# Recommendation to GPT

**보류 유지를 권한다.** 후속으로 무엇을 할지는 GPT 판단이다.

- 이 후보는 확정 신호(하한 0.10 초과)도 prior 확정(상한 0.10 이하)도 아니다. 추가 표본을 늘리기 전에 표본 정밀도 문제가 어디까지 결정을 바꿀지 판단이 필요하다.
- 구별 학습 pilot(직접 추가 CE, 어려운 쌍 sampling CE)은 이번 결과만으로 정당화하지 않는다.
- 언어·근거 연결이 필요한 과제나 모듈형 비교(MedGrounder 등)로 방향을 바꾸는 쪽이 정보 이득이 커 보인다.
- 비용 참고: M0 text-only는 요청당 약 55초·약 635토큰이라 병목이었다. C 요청 하나는 약 6.4초, retrieval은 192문장에 CPU 3.3초다.
- VinDr 승인 통지 후에는 P와 C의 차이 경향(문장 반복이 많은 소견에서 P가 강함)을 외부 자료에서 확인할 후보로 삼을 수 있다.

SELF_CHECK: PASS
SUMMARY: 동일 문장 21쌍 영상 교환, text-only, train-only 문장 retrieval 대조에서 C는 retrieval보다 F1@0.3이 0.149 높았으나(0.578 대 0.429) 영상 교환 반응 B_C 0.167 [0.015, 0.292]는 사전 기준을 넘지 못해 불확정·투자 보류이며, 개발 자료 한정 관찰이다.

# [orchestrator] 권한 거부된 도구 호출
- Bash: python - <<'E'
import json
for p in ['results/iter_040/gen/C/completion.json','results/iter_040/gen/M/completion.json','results/iter_041/gen/V96_C_Icost/completion.json']:
    d=json.load(open(p)); print(p,{k:(v if k in('n_requests','n_unique','wall_s','exit_codes','workers') else '..') for k,v in d.items()})
for p in ['results/iter_040/protocol/protocol_C.json','results/iter_040/protocol/protocol_M.json','results/iter_041/protocol/protocol_V96_C_Icost.json']:
    d=json.load(open(p)); print(p,d['runner'],d['n_requests'],d['adapter'],d['requests_path'],d.get('extra'))
E
ls results/iter_040/eval results/iter_040/train2 | head -30; ls results/iter_040/train2/C_s17 2>/dev/null; head -c 800 results/iter_040/eval/m0_v96_repro.json; echo; python -c "
import json;d=json.load(open('results/iter_040/summary.json'));print(list(d)[:30])"
- Bash: git ls-tree --name-only e7ee15464cf404a44a877997661b9f50dd8c3096 | grep -E "^pg4[0-2]|^pg39"; git show e7ee15464cf404a44a877997661b9f50dd8c3096:pg42_eval.py | sed -n 1,140p
- Bash: git ls-tree --name-only e7ee15464cf404a44a877997661b9f50dd8c3096
- Bash: nvidia-smi --query-gpu=index,name,memory.used,memory.total --format=csv; echo $CUDA_VISIBLE_DEVICES; python -c "import sklearn,scipy;print(sklearn.__version__,scipy.__version__)"; python -c "import torch,transformers;print(torch.__version__,transformers.__version__)"; free -g | head -2; nproc
- Bash: HF_HOME=/SSD1_1TB/home/milab/daniel/08_medgemma/hf_cache HF_HUB_OFFLINE=1 python -c "
import transformers
c=transformers.AutoConfig.from_pretrained('google/medgemma-1.5-4b-it',revision='91850547d9f0b2fdd21aa7c5f4f3d1a8a52c243b')
print(getattr(c,'image_token_id',None),getattr(c,'image_token_index',None))
p=transformers.AutoProcessor.from_pretrained('google/medgemma-1.5-4b-it',revision='91850547d9f0b2fdd21aa7c5f4f3d1a8a52c243b')
m=[{'role':'user','content':[{'type':'text','text':'hi'}]}]
x=p.apply_chat_template(m,add_generation_prompt=True,tokenize=True,return_dict=True,return_tensors='pt')
print(list(x.keys()), x['input_ids'].shape)
"
- Bash: git hash-object pg39_data.py pg39_spec.py pg41_run.py pg41_verify.py rsna_diag/__init__.py rsna_diag/generate.py rsna_diag/geometry.py rsna_diag/metrics.py rsna_diag/parse.py rsna_diag/prompts.py rsna_diag/lora.py rsna_diag/queue_lock.py
