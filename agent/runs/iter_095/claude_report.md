# Work Performed

## 요약

- **핵심 결과:** 같은 CURE 모델·같은 폐 8영역에서 공식 `Describe`를 새로 생성(E32, 32명×8=256건)해 기존 `Locate and describe`·C-G와 비교했다. 좌표 요구를 없애도 영역 간 충돌은 줄지 않았다.
- **근거:**
  - 충돌 환자는 Describe 14/32, Locate 10/32였다(차이 +0.125, CI [-0.031, 0.281]).
  - strict 추가 회복(전체 영상 C-G가 놓친 현재 폐 소견을 세부 영역이 회복)은 2명뿐이다. 그중 세부 영역에만 있는 환자는 1명이다.
  - 좌우 폐 2영역(Describe/Locate)은 충돌이 0명이지만 strict 회복도 1명뿐이다.
- **미검증·주의:**
  - 개발 자료이고 assistant가 판정했다. 전문의 검증이 아니며 조건명 제거는 독립 눈가림이 아니다.
  - reference가 있는 양성 환자는 9명(사실 10개)뿐이다.
  - 사전 규칙에 따라 E64는 실행하지 않았다.
- **다음:** 사전 규칙상 이 폐 영역 회복 후보에 대한 방법 pilot은 보류, 확대도 보류가 맞다. 판단은 GPT 리뷰에 넘긴다.

## 수행한 일

- 직전 상황을 확인했다. 이전 호출은 D8 검사까지 끝났고 E32 생성은 시작 전이었다. 이번에 E32를 시작해 끝냈다.
- reference 폐 소견을 출력 생성 전에 규칙으로 잠그고, 32명(양성 9/명시적 음성 8/나머지 15)과 나머지 64명을 고정했다.
- 새 wrapper·launcher를 만들고 CPU 테스트, D8 기술 검사, 중단·재개 시험을 통과시킨 뒤 E32 256건을 생성했다.
- 조건명을 뺀 출력 id로 의미 판정을 하고, 평가와 독립 재계산 검증을 수행했다.

# Files Changed

새 파일만 만들었고 기존 파일은 수정하지 않았다.

- `report95_common.py`
- `report95_lock.py`
- `report95_gen.py`
- `report95_launch.py`
- `report95_view.py`
- `report95_eval.py`
- `report95_verify.py`
- `report95_d8check.py`
- `report95_resume_test.py`
- `report95_summary.py`
- `test_report95.py`

결과는 모두 `results/iter_095/` 아래에 있다.

- `lock/`
- `plans/`
- `D8/`
- `E32/main/`
- `launches/`
- `judging/`
- `eval/`
- `tests/`

# Commands / Experiments

| 단계 | 결과 |
|---|---|
| `python report95_lock.py` | 성공 |
| `python test_report95.py cpu_tests.json` | 첫 실행 20/21. D8 기존 행이 iter_085 계승 행에 있어서 실패. 결과 파일은 보존 |
| `python test_report95.py cpu_tests_v2.json` | 수정 후 21/21 |
| D8 4 worker (`report95_launch.py`) | rc 모두 0 |
| D8 2 worker | rc 모두 0 |
| `report95_d8check.py` | 통과 |
| `report95_resume_test.py 0` | 통과 |
| E32 4 worker | rc 모두 0, wall 456.9초 |
| `report95_eval.py E32 report_E32.json` | 1차. 보존 |
| `report95_eval.py E32 report_E32_v2.json` | `narrow_generic_lungs` 민감도를 추가한 최종본 |
| `report95_verify.py E32 report_E32_v2.json verify_E32.json` | 13/13 통과 |

- 대기는 `experiment_wait.py`와 background 완료 알림을 썼다.
- E64와 E96은 사전 규칙에 따라 실행하지 않았다.

# Results

## 기술 검사

**D8 (4명, 16요청)**

- 4 worker와 2 worker의 token·input이 완전히 일치했다.
- 기존 Locate and describe 8건은 token·input·pixel이 모두 재현됐다.
- 전부 EOS로 종료했고, Describe 출력의 자발적 좌표는 0건이었다.
- 처리량(생성 구간)은 4 worker 12.30, 2 worker 10.41 req/min이다. 4 worker를 채택했다.
- 4 worker 때 GPU별 최대 점유는 약 20.0GB다.
- worker당 reserved 최대는 9.43GiB다.

**중단·재개**

- 6건 저장 후 정상 중단하고, torn row를 붙여 재개해 16건을 채웠다.
- 완료 후 재실행은 파일을 바꾸지 않았다. `--resume` 없는 시작은 거부됐다.
- w4 기준과 불일치는 0이다.

**E32**

- 256건이 전부 EOS로 종료했다. 요청 집합·digest·image hash가 모두 일치했다.
- 최대 점유는 GPU0 20,048MiB, GPU1 19,977MiB다.

## 자료 규모

- E96의 reference 양성 환자는 9명(사실 10개), 명시적 음성은 8명이다. 둘 다 모두 E32에 들어갔다.
- 나머지 64명에는 reference 양성도 명시적 음성도 0명이다. E64는 추가 회복 판정 기회를 주지 못한다.

## 번들 비교

단위는 환자다. 충돌은 32명 기준, 회복은 양성 9명(사실 10개) 기준이다. 비용은 E32 전체 합이다.

| 번들 | 요청 | 충돌 환자 (primary) | strict 회복 사실 | lenient 회복 사실 | 생성 token | 생성 초 합 |
|---|---|---|---|---|---|---|
| C-G | 32 | 0 | 0 | 3 | 762 | 157 |
| Locate 좌우 폐 (L2) | 64 | 0 | 1 | 1 | 7,246 | 2,135 |
| Describe 좌우 폐 (D2) | 64 | 0 | 1 | 1 | 1,510 | 332 |
| Locate 8영역 (L8) | 256 | 10 | 2 | 7 | 16,493 | 4,019 |
| Describe 8영역 (D8) | 256 | 14 | 2 | 7 | 6,435 | 1,397 |
| Locate 세부 6 (L6) | 192 | 2 | 2 | 7 | 9,247 | 1,884 |
| Describe 세부 6 (D6) | 192 | 3 | 2 | 7 | 4,925 | 1,065 |

- **충돌 차이 (primary):** D8−L8 +0.125 [-0.031, 0.281], D8−D2 +0.406 [0.25, 0.5625], L8−L2 +0.28 [0.125, 0.4375].
- **세부 영역의 추가 회복 (CG와 D2를 모두 제외):** strict 1명(P001, 우측 기저부 opacification), lenient 5명. strict 기준에서 이 1명을 빼면 0명이다.
- **lenient 5명의 성격:** lobe·시간·종류가 모호해서 W로 판정한 사례다.
- **충돌의 대부분은 일반 문구에서 나온다.** 일반 문구를 빼면 D8 1명, L8 2명이다.
  - 예: "The lungs are clear"와 "right lower lobe opacity"가 한 묶음에 함께 나온다.
- **L6, D6의 충돌은 2~3명뿐이다.** 대부분 세부 영역 주장과 좌우 폐 영역 정상 문구 사이에서 생긴다.
- **오류 비용 (양성 주장 중 reference로 확인 안 된 것):**
  - L8은 66개 중 unsupported 49, contradicted 2.
  - D8은 84개 중 unsupported 65, contradicted 2.
  - "new ... since prior" 같은 근거 없는 시간 표현이 L8 19, D8 22개다. 이 입력에는 이전 영상이 없다.

## 사전 규칙 대조 (판정은 GPT 리뷰 몫)

- **단순 대안 우선:** 조건은 "잃는 회복 환자 ≤1, 충돌 감소 ≥5"였다.
  - 숫자상 D2와 L2는 이 조건을 충족한다(strict lost 1, 충돌 감소 9~10).
  - 그러나 이는 세부 영역 주장을 아예 만들지 않아서 생긴 결과다. lenient lost는 5이므로 일관성 향상이 아니다.
  - D8은 충돌을 줄이지 못했다.
- **최소 방법 pilot 검토:** 조건은 "세부 영역에만 있는 명확한 회복 ≥3명, 충돌 ≥5명"이었다. strict로는 회복이 1명이라 충족하지 못한다. lenient 5명은 모호 대응 때문이다.
- **E64 확대:** 사전 조건(a), (b)를 strict로 충족하지 못했다(세부 영역 회복 1명, D2 보존 1명 <2). 조건(c)도 성립하지 않는다(나머지 64명에는 회복 평가 기회가 0이다). 그래서 실행하지 않았다.

# Goal Progress / Reused Assets

## 연구 관찰

- **Describe로도 영역 간 충돌은 줄지 않았다.**
  - 좌표를 없앤 Describe가 오히려 약간 더 많이 충돌했다. 좌표 출력 요구만으로는 충돌이 설명되지 않는다.
  - 충돌은 주로 일반 문구와 세부 영역 주장의 불일치에서 나온다.
- **중간 영역 질문의 반복 패턴이 있다.** "mid lung zone" 질문에 "lower/upper lobe opacity"가 반복해서 나온다. "new since prior" 같은 환각성 시간 표현이 많다. 이는 시간·원인 주장 오류 비용의 일부다.
- **C-G 단독으로도 일부 소견이 있다.** P007·P008에서 C-G가 이미 좌측 기저부 소견을 언급했다. 따라서 추가 회복의 크기는 판정 규칙에 민감하다.

## 구분

- **시험 설정:** 이번 비교(E32, 이 모델과 E96 개발 자료)는 사전 규칙상 확대 근거가 부족하다.
- **연구 질문:** 영역 판독의 소견 보존과 부정 범위 일관성은 아직 미해결이다. 이번 결과가 기각한 것은 "좌표 요구가 충돌의 원인"이라는 설명 하나다. 위치 학습 일반이나 다른 데이터·모델은 판단하지 않았다.

## 재사용 자산

`reuse_assets`는 비어 있었다. 기존 `report86_common.py`와 `report86_inherit.py`, `rsna_diag/*`, `pg43_run.repair_tail`을 import해 썼다.

- 기존 Locate and describe 출력은 completion hash와 record digest를 검증한 뒤 읽었다.
- D8 일부 행은 iter_085 계승 행(`load_verified`)에서 가져왔다.
- 모델·전처리·생성 경로는 `report86_gen.py`와 동일하게 유지했다. D8 회귀 8/8이 일치했다.

# Problems

## 현재 결론 무효: 없음

## 해석 제한 (결론에 영향 가능)

- **판정 방식.**
  - assistant가 규칙 기반 초안을 원문과 대조하며 작성했다. 조건명 제거는 독립 눈가림이 아니고, 전문의 검증도 아니다.
  - 초안 규칙 정제는 사실상 선택에 영향을 줄 수 있다. 전체 N 판정은 개별로 읽지 않고, 고유 문장 집계와 양성 주장 전수 목록으로 확인했다. 초기 P000~P005는 전체를 읽었다.
- **회복 판정 규칙.** match 등급(S/W)은 사후 보완 없이 사전 규약에 따라 reference를 본 뒤 작성했다. lobe 표현을 W로 처리한 규칙에 결과가 민감하다. lenient와 notime 분석을 함께 실었다.
- **"나머지 12명 재점검"을 요구한 부분.** reference가 없는 15명의 양성 주장과 neg 8명의 양성 주장은 원문 목록으로 읽고 확인했다. 요청한 "고정 12명 전수 재점검"과 정확히 같지는 않다.
- **개발 자료.** E96 개발 자료이고 CURE 학습 노출 가능성이 있다. 양성 9명이라 CI가 넓다.
- **verify의 한 항목.** 13개 중 `claims_in_judgment_quotes_exist`는 placeholder다. 실제 quote 존재 검증은 `report95_eval.load_judgments`의 assert이며 실행에 성공했다.

## 재사용 전 수정

- 독립 검증은 같은 judgments 파일을 읽으므로 의미 판정의 독립 검증이 아니다. 산술·연결만 독립이다.
- `report95_gen`: 같은 protocol의 다른 shard 출력은 수용하지 않지만, 한 shard의 부분 실행만 지원한다. 재사용은 현재 고정 자료에 한정한다.

## 추후 개선

- 첫 `cpu_tests.json`(20/21, 원인: D8 기존 행 연결)과 `report_E32.json`(1차)은 보존하고, 수정본은 `*_v2`로 별도 저장했다.

# Recommendation to GPT

- 사전 기준상 이번 비교는 최소 방법 pilot(영역별 회복을 보존하면서 부정 범위를 맞추는 개입)과 E64 확대 모두 근거가 부족하다고 본다. 이를 "현재 시험 설정·후보의 보류"로 분류하는 것을 권한다. 연구 질문 전체의 기각으로 확대하지 않는다.
- 근거: 세부 영역 추가 회복 strict 1명, 충돌은 Describe로 감소하지 않음, 나머지 64명에는 평가 기회 0.
- 독립 검토가 필요한 점:
  - lobe(W) 처리 규칙이 결과를 얼마나 좌우하는지.
  - "clear lungs"와 focal 주장의 충돌을 충돌로 세는 것이 타당한지.
  - 판정자 편향(assistant).
- 다음 후보: 같은 CURE 출력을 다른 질문 세트(PadChest 문장 단위 정답)에서 보거나, 강한 모듈형 판독 대조로 넘어가는 선택을 비교하면 좋다. 같은 E96에서 새 prompt나 영역을 추가하지 않는다.

SELF_CHECK: FAIL
SUMMARY: CURE 공식 Describe vs Locate and describe E32 256건 생성(전부 EOS)·평가·독립 재계산을 마쳤다. Describe로도 영역 충돌은 줄지 않았고(14 vs 10/32), strict 추가 회복은 1명뿐이라 E64 확대·pilot은 사전 기준 미달. assistant 판정·개발 자료·양성 9명 한계로 FAIL 표시.

# [orchestrator] 권한 거부된 도구 호출
- Bash: awk '/^## P002/,/^## P006/' results/iter_095/judging/draft_E32_v3.txt | cut -c1-175
- Bash: cp results/iter_095/judging/draft_E32_v5.txt results/iter_095/judging/judgments_E32.txt; grep "| N |" results/iter_095/judging/judgments_E32.txt | awk -F'|' '{print $3"|"$4"|"$6}' | sort | uniq -c | sort -rn | head -60
- Bash: python - <<'E'
import json
r=json.load(open('results/iter_095/eval/report_E32_v2.json'))
for k,v in r['compare'].items():
    if k.startswith('recall'): print(k, v and (round(v['mean'],3), [round(x,3) for x in v['ci95']]))
for b,v in r['bundles'].items(): print(b,v['n_requests'],v['tokens_last_attempt'],round(v['generation_seconds_sum']),{k:round(x,3) for k,x in v.items() if k.startswith('recall') or k.startswith('facts')})
print(r['describe_spontaneous_coords'])
E
cat results/iter_095/tests/d8_check.json | python -c "import json,sys;d=json.load(sys.stdin);print(d['w4']['req_per_min_generation_window'],d['w2']['req_per_min_generation_window'],d['w4']['smi_max_used_mib_per_gpu'])"; python -c "
import json,glob
for f in glob.glob('results/iter_095/launches/e32*/launch_result.json'): d=json.load(open(f));print(d['wall_s'],d['returncodes'])
import itertools
mx={}
for l in open(glob.glob('results/iter_095/launches/e32*/resource.jsonl')[0]):
    for g,(u,t) in json.loads(l)['smi'].items(): mx[g]=max(mx.get(g,0),u)
print(mx)"
- Bash: python - <<'E'
import json,glob
r=json.load(open('results/iter_095/eval/report_E32_v2.json'))
for k,v in r['compare'].items():
    if k.startswith('recall'): print(k, v and (round(v['mean'],3), [round(x,3) for x in v['ci95']]))
for b,v in r['bundles'].items(): print(b,v['n_requests'],v['tokens_last_attempt'],round(v['generation_seconds_sum']),{k:round(x,3) for k,x in v.items() if k.startswith('recall') or k.startswith('facts')})
print(r['describe_spontaneous_coords'])
d=json.load(open('results/iter_095/tests/d8_check.json'));print(d['w4']['req_per_min_generation_window'],d['w2']['req_per_min_generation_window'],d['w4']['smi_max_used_mib_per_gpu'])
for f in glob.glob('results/iter_095/launches/e32*/launch_result.json'):
    dd=json.load(open(f));print(dd['wall_s'],dd['returncodes'])
mx={}
for l in open(glob.glob('results/iter_095/launches/e32*/resource.jsonl')[0]):
    for g,(u,t) in json.loads(l)['smi'].items(): mx[g]=max(mx.get(g,0),u)
print(mx)
E
