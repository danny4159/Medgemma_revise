# 요약

- **핵심 결과:** iter_108 저장 답변에 명시적 Yes/No 추출을 한 번 적용했다. 표적 질문(O)에서는 crop 이득이 어떤 unresolved 배정에서도 10pp에 못 미쳤고, 현재 crop 후보 투자 보류는 유지된다. 원 T−D O −2.97pp는 −0.42pp로 약해져, 원래 음의 방향은 형식(invalid) 영향이 컸다.
- **근거:** 원 점수 회귀 차이 0건, 독립 검증 42/42. 새 추론·학습·GPU 사용은 0이다.
- **미검증·주의:** 전체 비정상 판단(A)은 unresolved가 많아 crop의 손상도 이득도 판정하지 못했다. 사후 분석이며 원 gate 재통과나 독립 확인이 아니다.
- **다음:** 사용자 승인 대기. 자동 parser 확장이나 새 생성은 시작하지 않았다.

# Work Performed

1. 사용한 출력의 출처 연결을 검증했다.
   - iter_108 D/T/C/L 1,652건은 `ev108_run.verify_completion`으로 재검증했다.
   - F 1,200건(iter_016 `e180_plain`/`e600x_plain` M0)은 `requests_sha256`, 요청 집합, record–request 연결, 행 수, 현재 영상 hash를 확인했다.
   - F의 원본 pixel hash는 iter_108 D/T/C의 첫 영상과 일치했다.
2. 명시적 답 추출 규칙(`ev109_extract.py`)을 GT 연결 전에 합성 fixture 31/31 통과 후 잠갔다.
   - 원 `semantic_v1`이 받던 응답은 그대로 유지했다.
   - 추가한 패턴은 문두의 `Yes.`/`No.`와 `Answer: Yes`, `Therefore, the answer is yes` 같은 결론형뿐이다. 같은 답의 반복은 허용했다.
   - 인용·코드, 질문 반복, 반대 yes/no 단어, 불확실성·조건 표현, 상충 답은 모두 unresolved로 뒀다.
3. 추출 ledger 2,852행을 만들고 잠근 뒤 GT를 연결했다.
   - 규칙 lock 시각, ledger 잠금 시각과 digest는 실제 시점으로 `results/iter_109/` 아래 파일에 기록했다.
4. 분석(`ev109_analyze.py`).
   - 원 strict/semantic_v1 평가기를 그대로 회귀 재현했다.
   - 같은 평가기에 명시적 답 평가를 적용해 나란히 비교했다.
   - unresolved를 환자별로 열거한 공동 배정 범위를 계산했다. F 응답은 정책 간 공유 변수로 묶었다.
   - bootstrap은 category 층화 10,000회, seed 10817이다.
5. 독립 검증(`ev109_verify.py`).
   - production 집계를 호출하지 않았다. 변수 전수 열거, 단순 루프 bootstrap, 추출 재현, 단조성 성질을 확인했다.
6. P180은 보조 표(`report_P180_aux.json`)로만 재현했고 E600과 합산하지 않았다.

# Files Changed

새 파일만 추가했고 기존 코드와 결과는 수정하지 않았다.

- `ev109_extract.py`: 명시적 답 추출 규칙
- `test_ev109_extract.py`: 합성 fixture와 규칙 잠금
- `ev109_prov.py`: 출처 검증과 추출 ledger 생성
- `ev109_analyze.py`: 회귀, 명시적 답 평가, 범위 계산, 전이 분해
- `ev109_verify.py`: 독립 검증
- 결과: `results/iter_109/{extract_lock.json, tests/, provenance/, eval/}`

# Commands / Experiments

- `python test_ev109_extract.py`: 성공, 31/31. 규칙 파일 hash를 잠갔다.
- `python ev109_prov.py`: 부분 실패 후 복구했다.
  - iter_108 검증과 ledger 잠금은 성공했다.
  - F 검증이 stage당 2건 불일치로 실패했다. 내 코드 버그였다. 원본 영상 기준으로 L(crop 단독) 행의 pixel hash를 잘못 포함했다.
  - 이미 잠근 ledger는 건드리지 않았다. `python ev109_prov.py F`로 F 전용 ledger와 `manifest_F.json`, `ledger_lock_F.json`을 추가했고 문제 0으로 통과했다. 첫 `manifest.json`(F 실패 기록)은 보존했다.
- `python ev109_analyze.py`: 성공, 약 13초. 200 bootstrap 반복은 0.012초이고 전체 분석은 약 9초였다.
- `python ev109_verify.py`: 성공, 42/42.
- GPU 사용 0, 새 요청 0, 학습 0이다. 따라서 worker/batch 처리량 비교는 하지 않았다.

# Results

경로: `results/iter_109/eval/report_E600.json`, `verify_E600.json`, `report_P180_aux.json`. 아래 수치는 E600 nonempty 236명(not_normal_no_opacity는 67명)의 paired 비교다.

**회귀:** 저장된 iter_108 report의 strict/semantic 비교와 정책 점수를 모두 재현했다(차이 0건). 경계를 열거로 낸 값과 `E.compare`의 `format_bound`도 일치했다. P180 보조 표도 회귀 0건이다.

**응답 구성**(unresolved 수는 236건 기준, F는 600건 기준):

| 조건·질문 | unresolved | 명시적 답으로 새로 해석 |
|---|---|---|
| T_O | 6 | 16 |
| D_O | 4 | 13 |
| C_O | 7 | 13 |
| T_A | 76 | 22 |
| D_A | 54 | 11 |
| C_A | 79 | 23 |
| F_O | 8 | 1 |
| F_A | 6 | 10 |

- unresolved 사유는 대부분 `hedge_or_conditional`(고정 목록의 불확실성·조건 표현)과 `no_explicit_answer`(설명만 있고 명시적 답 없음)다.
- 명시적 답 패턴은 있었지만 보수 규칙 때문에 unresolved가 된 응답은 125건이다.

**주 endpoint:**

| 비교 | 원 semantic | 명시적 답 점추정 [95% CI] | unresolved 공동 배정 범위 |
|---|---|---|---|
| T−D O | −0.0297 | −0.0042 [−0.034, 0.025] | [−0.021, +0.021] |
| T−C O | +0.0042 | +0.0254 [−0.004, 0.055] | [−0.004, +0.051] |
| T−D A (nno) | −0.1343 | −0.1194 [−0.194, −0.045] | [−0.522, +0.358] |
| T−C A (nno) | +0.0448 | +0.0746 [0.015, 0.149] | [−0.388, +0.552] |

- 점추정에서 unresolved는 오답으로 계산했다.
- O의 T−D 비교에서 원래 invalid가 관여한 9건을 분해하면, 6건은 정오 동일, 2건은 T가 맞고 D가 틀린 내용 차이, 1건은 unresolved였다.
- A의 T−D(nno) 9건은 3건 정오 동일, 6건 unresolved였고 내용 전이는 0건이다.

**단순 대안과 정책(S_scope):**

| 정책 | 점수 |
|---|---|
| F | 0.627 |
| R | 0.627 |
| R_L | 0.547 |
| R_B | 0.648 |

| 정책 차이 | 점추정 [95% CI] | 공동 배정 범위 |
|---|---|---|
| R−F | 0.000 [−0.015, 0.013] | [−0.003, +0.008] |
| R_B−R | +0.022 [−0.005, 0.048] | [+0.012, +0.022] |
| R_L−F | −0.080 [−0.110, −0.050] | [−0.085, −0.078] |

원본 영상 단독(F)이나 bbox 유무 규칙(R_B)을 넘는 crop 정책의 이득은 없었다.

# Goal Progress / Reused Assets

**시험 설정:** 현재 crop 설정의 추가 투자 보류를 유지한다. 이번에 설정을 개선하지는 않았다.

**연구 관찰:**
- 원 O 결과의 T−D 음의 방향은 대부분 형식(invalid) 때문이었다. 명시적 답을 읽으면 약 0이다(H1은 O에서 지지).
- 그래도 표적 이득은 어떤 배정에서도 10pp 미만이다(H2 지지).
- A에서는 `T_A` 236건 중 76건, `C_A` 79건, `D_A` 54건이 unresolved다. 보수적 범위가 ±수십 pp로 넓어 crop의 손상도 이득도 판정하지 못했다.
- A의 점추정 −11.9pp는 unresolved를 오답으로 센 값이다. 내용 손상으로 읽을 수 없다.

**연구 질문:** 국소 근거 활용 전체의 가치는 이번 분석으로 판단할 수 없다. 신규성도 미확정이다.

**재사용 자산:**
- `ev108_eval.py`, `ev108_spec.py`, `ev108_run.verify_completion`, `ev108_data.py`, `rsna_diag/qa_spec.py`는 수정 없이 재사용했다.
- 원 평가기는 회귀로 재현했다. 반입(reuse_assets)은 없었다.

# Problems

**현재 결론 무효화 문제:** 없음.

**한계:**
- 사후 분석이다. 이미 결과와 일부 원문을 본 뒤 규칙을 만들었고, 규칙은 GT 연결 전에 잠갔다. 새 사전등록이나 원 gate 재통과로 부르지 않는다.
- 추출 규칙이 보수적이다. 불확실성·조건 표현과 반대 token을 거부해서, 사실상 명확한 응답 일부도 unresolved로 남았다. 규칙은 결과를 보고 넓히지 않았다.
- F의 역사적 `protocol_digest` 재계산 모듈(`qa_protocol`)이 이 브랜치에 없어 재계산하지 못했다. `requests_sha256`·record 연결·현재 hash로 검증했고, 과거 무결성의 소급 증명은 아니다.
- E600은 반복 사용한 개발 자료이며 P180을 포함한다.
- normal nonempty는 5명뿐이라 해당 category 해석에 한계가 있다.
- `ev108_data.load_gen_dir`의 hash 미검사 문제는 이번 경로에서 쓰지 않았다. 고치지도 않았다.

**추후 개선(필수 아님):** 위 한계 외에 지금 처리할 항목은 없다.

# Recommendation to GPT

- 현재 crop 후보의 보류를 유지하고 이 평가 보완은 반복하지 않는 것을 권한다. O에서 이득이 없고, 단순 대안(F, R_B)이 crop 정책 이상이라는 점은 unresolved 배정과 무관하게 유지된다.
- 한 가지 선택지가 있다. A의 unresolved 비율이 높아서 전체 비정상 판단에서 crop이 어떤 영향을 주는지는 이번 저장 답변으로 알 수 없다. 이를 직접 보려면 고정 응답 형식과 독립 자료의 별도 승인 계획이 필요하다. 현재 O 결과를 근거로는 우선순위가 높지 않다.
- 이번 분석에서 새 parser·문장 재판정·GPU 실험은 자동 연장하지 않았다.

SELF_CHECK: PASS
SUMMARY: iter_108 저장 답변에 고정 명시적 Yes/No 추출을 적용하자 표적 질문의 crop 이득은 unresolved 배정과 무관하게 10pp 미만이라 투자 보류가 유지됐다(T−D O −2.97→−0.42pp). 전체 비정상 판단은 unresolved가 많아 판정 불가이며, 사후 분석이고 원 회귀 0건·독립 검증 42/42다.

# [orchestrator] 권한 거부된 도구 호출
- Bash: python - <<'E'
import json
r=json.loads(open('results/iter_016/gen/e600x_plain__M0/gen_worker0.jsonl').readline())
print({k:(v if k not in('input_ids',) else '...') for k,v in r.items() if k not in ('input_ids',)})
c=json.load(open('results/iter_108/gen/E600R/main/completion.json')); print({k:(v if len(str(v))<300 else '...') for k,v in c.items()})
E
ls results/iter_016/requests results/iter_016/protocol 2>/dev/null | head -30; grep -n "def verify_records" -A40 ev108_run.py | head -70
- Bash: python -c "
import json,glob
sets=json.load(open('results/iter_016/manifests/sets.json'))
e600={i for c in sets['E600'] for i in sets['E600'][c]}
p180={i for c in sets['P180'] for i in sets['P180'][c]}
st='e180_plain__M0'
ids=set()
for f in glob.glob('results/iter_016/gen/'+st+'/gen_worker*.jsonl'):
    for l in open(f): ids.add(json.loads(l)['id'])
print(len(ids),len(ids-e600),len(ids-p180),len(p180-e600),len(e600))
# pixel check
d=json.loads(open('results/iter_108/gen/E600R/main/gen_worker0.jsonl').readline())
print(d['patient'],d['input_pixel_sha256'][0])
for f in glob.glob('results/iter_016/gen/*/gen_worker*.jsonl')[:0]: pass
for f in glob.glob('results/iter_016/gen/e600x_plain__M0/gen_worker*.jsonl'):
    for l in open(f):
        r=json.loads(l)
        if r['id']==d['patient']: print(r['input_pixel_sha256']); break
"

