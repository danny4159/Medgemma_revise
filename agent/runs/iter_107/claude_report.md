# 요약

- **핵심 결과:** 사전 고정한 분기는 `negative`다. 두 판독자의 주석이 일치하는 핵심 10명 모두에서 CURE 공식 단일 phrase 출력이 분리된 두 근거를 보존했다(`both_retained` 10/10, 부분 누락 0). 사전 고정한 후속 투자 선택 중 "이 조건의 추가 투자 보류"에 해당한다.
- **비교 대상:** 적응 MedGrounder(`A_U_e5`, 저장된 출력)는 threshold 0.8과 0.4 모두 6명 `both_retained`, 4명 `ambiguous`였다. `ambiguous`는 coverage가 0.1~0.5 사이라서 누락으로도 보존으로도 판정되지 않는 경우다. 부분 누락은 없었다.
- **근거:**
  - CURE의 핵심 10개는 모두 예측 box 2개였고 주석 밖 면적 비율이 0.04~0.34라서, 큰 box 하나로 덮은 결과가 아니다.
  - 47개를 36명 단위로 집계하면 CURE의 union IoU(예측·정답 box 합집합의 겹침 비율)가 0.535 [0.459, 0.610], MedGrounder 0.8은 0.416 [0.349, 0.483]이다.
  - 독립 재계산으로 사건·분기가 모두 일치했다.
- **미검증·주의:**
  - 반복 사용한 개발 자료(PadChest-GR train V96)다. 독립 확인이 아니며 CURE의 학습 노출은 미확인이다.
  - 핵심 10명은 판독자 합의가 높은 사례에 한정되므로 다중 영역 소견 전체의 빈도로 일반화할 수 없다.
  - 자유 판독의 임상적 완전성은 측정하지 않았다.
  - 실행 조건은 NF4/bf16이라서 논문 수치의 재현이 아니다.
- **다음:** 이 한정 조건에서는 투자를 보류하고, 새 방법·학습은 근거가 없다. 연구 방향은 GPT 리뷰와 사용자 승인으로 정한다.

# Work Performed

- 반입 14개 파일을 `git hash-object`로 확인했다. manifest의 blob과 모두 일치하며 수정하지 않았다.
- **자료 적합성**
  - iter_039 manifest와 iter_046 V96 MedGrounder 출력 192건을 환자·target·문장 sha256·u8 pixel hash로 연결했다.
  - 공식 box 2개 이상 소견은 47개·36명, 핵심 집단은 10개·10명으로 계획과 일치했다. 개수가 달랐다면 중단하도록 해 두었다.
  - 분할 zip에서 36개 원본 uint16 PNG를 추출하고, CRC·raw sha256·u16 pixel hash를 모두 대조했다.
- **시각 확인:** 고정 첫 4개 overlay(GT·extra·MG)와 CURE overlay를 열어 보았다. 실제 영상에서 좌표 원점·정규화가 일치했다.
- **실행기:** `lk105_run.py`를 `nr107_run.py`로 CURE 전용으로 적용했다(A/B·M15·lenient parser 분기는 쓰지 않음). 아래를 보완했다.
  - 가중치 sha256+size+mtime 잠금: 이번에 새로 계산한 해시가 HF blob 파일명과 같았다.
  - launcher가 시작할 때마다 전체 hash를 재검증한다.
  - admission 실패도 `launch_NNN.json`에 기록한다.
- **기술 확인 T4:** 실제 CURE로 4건을 생성했다. 2 worker 결과와 중단 후 재개한 1 worker 결과가 token·입력·pixel까지 일치했다. 변조 거부는 의도한 검증 분기에서 걸렸다.
- **본비교 M47:** 47건 CURE PG를 생성했다. 평가 규칙은 결과를 보기 전에 고정했고, 독립 재계산으로 대조했다.

# Files Changed

신규:
- `nr107_geom.py`: 정확한 box 합집합·coverage·union IoU·matching
- `nr107_spec.py`: 엄격 parser, 핵심 규칙, 사건 정의
- `nr107_data.py`: 코호트 구성과 raw 추출
- `nr107_run.py`: runner와 launcher
- `nr107_test.py`: CPU fixture
- `nr107_tech.py`: 기술 확인
- `nr107_eval.py`: 평가
- `nr107_verify.py`: 독립 재계산

결과는 모두 `results/iter_107/` 아래에 새 파일로 저장했다.

# Commands / Experiments (실제 실행한 명령과 성공/실패)

| 명령 | 결과 |
|---|---|
| `python nr107_data.py` | 성공 (47/36/10) |
| `python nr107_run.py lock_weights` | 성공 |
| `python nr107_test.py` | 42/42 통과 |
| `launch --stage T4 --workers 2 --placement 0,1` | 성공, wall 60.9초 |
| T4 `--limit 2` 후 재개 | 성공 |
| `launch ... T4_admission_refuse --placement 0,0` | 의도한 admission 거부(AssertionError), 기록 저장 확인 |
| `python nr107_tech.py` | 19/19 통과(v2) |
| `launch --stage M47 --workers 2 --placement 0,1` | 성공, wall 352.3초 |
| `python nr107_eval.py` | 성공 |
| `python nr107_verify.py` | 1차 실패, 2차 통과 (아래) |

- `nr107_tech.py`의 변조 거부 검사는 처음에 모두 completion hash에서만 걸렸다. completion을 재봉인해 다시 돌리니 의도한 분기(요청 집합 누락·중복 ID·record digest·prompt 대조)에서 거부됐다. 처음 결과는 `tech_T4.json`에 남아 있다.
- `nr107_verify.py` 1차는 작은 GT box에서 래스터 오차가 허용치(3e-3)를 넘어 실패했다. 모델이나 평가기 오류가 아니라 검증기의 해상도 문제였다. GT box 내부를 직접 샘플링하는 방식으로 바꿔 `verify_v2.json`에서 불일치 0(최대 차이 0.0019)으로 통과했다.
- 1차 결과 `verify.json`은 보존했다.

# Results (수치와 결과 파일 경로)

**핵심 10명의 사건** (`eval/report.json`)

| 시스템 | both_retained | ambiguous | partial_omission |
|---|---|---|---|
| CURE | 10 | 0 | 0 |
| MG 0.8 | 6 | 4 | 0 |
| MG 0.4 | 6 | 4 | 0 |

분기 규칙에서 N(CURE 부분 누락 수)=0이므로 `negative`다.

**47개 전체 기술통계** (36명 환자 bootstrap 10,000회, seed 107, 평균 [95% 구간])

| 지표 | CURE | MG 0.8 | MG 0.4 |
|---|---|---|---|
| union IoU (공식 주석) | 0.535 [0.459, 0.610] | 0.416 [0.349, 0.483] | 0.409 [0.343, 0.473] |
| 평균 coverage | 0.662 [0.570, 0.753] | 0.731 [0.673, 0.783] | 0.742 [0.686, 0.795] |
| recall@0.3 | 0.78 | 0.639 | 0.639 |
| 주석 밖 면적 비율 | 0.287 | 0.447 | 0.459 |

- CURE−MG0.8의 차이는 union IoU +0.119 [0.045, 0.192]였다. coverage 차이는 −0.068 [−0.171, 0.032]로 불확정이다.
- CURE의 47개는 모두 EOS로 끝났고 cap 재시도는 없었다. 상태는 45건 `valid_nonempty`, 2건 `no_box`다.
- `no_box` 2건은 "air trapping" 문장이며, 이 문장들은 대체 주석(`extra`)이 없는 비핵심 항목이다.
- 비핵심 37개는 주석 차이를 포함한 기술통계다. 공식 box가 2개인 42개 중 CURE가 box를 더 적게 낸 경우가 6건(1개 4, 0개 2)이다. 이는 사건 정의 밖의 기술 관찰이며 같은 방식으로 해석하지 않았다.

**자원**
- 신규 요청은 M47 47건과 T4 4건이다. M47은 두 GPU에 각 1 worker로 실행했다.
- worker당 peak reserved는 9.43 GiB, loading은 22~27초다. M47 wall은 352초이고 생성 합계는 310초와 242초다.
- GPU당 worker 2개는 필요 메모리 24,096 MiB가 가용 24,039 MiB를 넘어 허용되지 않아 비교하지 못했다. 작은 workload라서 추가 비교는 하지 않았다.
- 구현·검증 시간은 측정하지 않았다.

**주요 파일**
- `data/cohort_summary.json`, `items.json`
- `gen/M47/completion.json`
- `eval/report.json`, `eval/verify_v2.json`
- `tests/fixtures_cpu.json`, `tests/tech_T4_v2.json`
- `protocol/weights_lock.json`

# Goal Progress / Reused Assets (목표 진전·미검증 범위, 재사용 출처·검증)

**목표 진전**
- 새 과학적 관찰: 공식 지원되는 자연 단일 phrase에서 CURE는 주석이 일치하는 분리된 두 근거를 모두 출력했다. "일부 위치 근거만 제시되는 문제"는 이 조건에서 관찰되지 않았다.
- 이전 결과와의 연결: iter_106의 복합 phrase 손실은 입력 확장의 문제였고, 이번 결과는 그 확장을 쓰지 않은 공식 경로가 그 손실을 보이지 않음을 보여 준다. iter_106의 수치와 해석은 바꾸지 않았다.
- 연구 질문 보류의 한정: 이 조건(자연 다중 영역, 합의 10명)의 부분 누락 개입은 보류한다. 일반적인 grounding 충분성·위치 학습의 무용성·공동 처리 결함의 유무는 이번 비교로 판단하지 않는다.

**미검증**
- 독립 환자·기관, 더 큰 합의 집단, 비핵심 소견 중 CURE가 box를 덜 낸 6건의 원인, CURE의 학습 노출은 검증하지 않았다.
- 새 기여나 방법 필요성은 평가하지 않았다.

**재사용 검증** (required_checks)
- blob 일치: 14/14 확인.
- 호출 경로: `nr107_run.py`는 CURE `load_model`·공식 transform·생성·재개만 쓰고 lk105의 A/B 평가·충분성 분기는 호출하지 않는다.
- 실제 입력 검증: 실제 4개 입력으로 공식 chat template과 builder의 입력 일치를 매 요청 assert했다.
- 자산 해시: 가중치 sha256을 새로 계산했고 processor·chat template·공식 transform 소스 digest(22개)를 protocol에 잠갔다.
- 변경 경로 검사: 요청 누락·중복·변조 거부, 부분 재개와 완료 출력 불변성, admission 실패 기록을 확인했다.

# Problems (현재 결론 무효 / 재사용 전 수정 / 추후 개선을 구분)

- **현재 결론 무효:** 없음.
- **재사용 전 수정:** 없음. 다만 `verify.json`(1차)은 래스터 해상도 한계로 실패한 기록이다.
- **추후 개선:**
  - 핵심 10명은 확증 표본이 아니다.
  - 분기 규칙의 `persist>=3` 문턱은 결과 확인 전에 고정했지만 plan 문구의 "같은 환자 누락 유지"를 이번에 조작화한 것이다. N=0이라 영향은 없었다.
  - `ambiguous` 4건은 MedGrounder가 두 근거 중 하나를 0.1~0.5 coverage로만 덮은 경우다. 확정 누락과 구분해 보고한다.

# Recommendation to GPT

- full review에서 원시 출력 47건과 핵심 10개의 coverage 대응을 직접 대조해 주기 바란다. MedGrounder `ambiguous` 4건(air trapping 2건, prominent hila 1건, bilateral effusion 1건)이 판정을 바꾸지 않는지도 확인해야 한다.
- 투자 선택: 이 조건의 부분 누락 개입은 보류를 권고한다. 근거는 CURE가 10/10에서 보존했고 큰 box 편법이 없었다는 점이다.
- 다음 후보는 다른 잔여 질문이어야 한다. 예로 비핵심에서 CURE가 box를 덜 낸 6건(대체 주석 부재 포함)이 판별 가능한지가 있다. 다만 공개 주석으로 설명할 수 없으면 새 비교 근거가 부족하다.
- 같은 자료의 threshold·prompt·parser 탐색은 하지 않았다.

SELF_CHECK: PASS
SUMMARY: 다중 영역 소견 47개·36명에 CURE 공식 단일 phrase를 적용한 결과, 두 판독자 주석이 일치하는 핵심 10명 모두에서 두 근거를 보존해(부분 누락 0) 사전 분기 negative이며 이 조건의 추가 투자는 보류를 권고한다. 반복 개발 자료의 한정 관찰이고 독립 재현·임상 판독 정확성은 미검증이다.

# [orchestrator] 권한 거부된 도구 호출
- Bash: git ls-tree -r --name-only HEAD | grep -E "lk10|rsna_diag" | head -30; ls results/iter_105 results/iter_106; ls results/iter_105/tests results/iter_106/tests 2>/dev/null
- Bash: git ls-tree --name-only HEAD | grep -E "lk10|nr107"
- Bash: python - <<'EOF'
import json
from pathlib import Path
R=Path('results/iter_046/mg/V96_A_w2b4')
recs=[json.loads(l) for w in (0,1) for l in (R/f'raw_worker{w}.jsonl').read_text().splitlines() if l]
print(len(recs), len({r['request_id'] for r in recs}))
r=recs[0]; print([k for k in r]); print(list(r['detections'].keys()))
print(json.dumps(json.load(open(R/'launch_protocol.json')))[:1500])
print(json.dumps(json.load(open(R/'completion.json')))[:800])
EOF
- Bash: ls results/environments/cure085/bin/python results/iter_085/official/minimal/vlm_research_kit | head; python -c "
import json
d=json.load(open('results/iter_106/protocol/weights_lock.json'))
print(d.keys()); print(json.dumps(d['CURE']['weights'])); print(len(d['CURE']['small']))
"; nvidia-smi --query-gpu=index,memory.used,memory.total --format=csv; echo $CUDA_VISIBLE_DEVICES; grep -n "def repair_tail" -A12 pg43_run.py
- Bash: ls results/environments/cure085/bin/python results/iter_085/official/minimal/vlm_research_kit
- Bash: cd results/iter_107/gen/T4_w2; ls; cat launch_000.json | head -c 1500; tail -3 launch0_cure0.stdout.log; tail -3 launch0_cure1.stderr.log; python -c "
import json
for k in (0,1):
    for l in open('cure/shard%d/outputs.jsonl'%k):
        r=json.loads(l); print(r['id'][-40:], repr(r['text']), [(a['ended_eos'],a['n_new'],round(a['runtime_s'],1),a['peak_mem_reserved_gb']) for a in r['attempts']])
"; cd ../../../..
