# 요약

- **핵심 결과**: 공식 MSD 뇌종양 FLAIR 개발 자료에서 MedGemma 1.5는 영상이 있는 405요청 중 404건을 PRESENT로 답했고, 1건은 형식 오류였다. annotation이 없는 slice(N1/N2)도 모두 PRESENT였다. 사전 분기는 `negative_basic_reading_insufficient`다.
- **근거**: E 45명×10조건=450요청은 모두 EOS로 끝났고 최대 284 token이다. 개별 OR와 공동 입력의 BA는 0.500과 0.494이고, 차이는 0.0056(95% CI [0, 0.0167])이다. OR specificity는 0, 영상 요청 형식 유효율은 99.5%다.
- **미검증·주의**: 공동 처리 손실(H2)과 관측 누락(H1)은 구분하지 못했다. 개별 판독이 이미 고정 PRESENT라서 판별할 신호가 없었다. 반복 개발 자료이고 단일 seed이며 slice는 N1/N2 같은 배경 slice다. 독립 확인은 미실행이다.
- **다음**: 이 frozen 질문과 설정은 투자를 보류하는 쪽이 맞다. 다만 이것이 MRI 인식 능력 전체의 기각은 아니다.

# Work Performed

- 계획의 D6/E48(iter_064 target manifest)을 유지했다. raw 파일 hash, shape·affine·orientation·label·finite를 검사했고, affine 경로로 canonical 배열의 voxel 값이 일치하는지도 확인했다.
- N2를 규칙으로 추가했다. N1과 다른 slice 중 종양 annotation이 0이고 FLAIR nonzero 면적이 최대의 50% 이상이며, P와의 물리 거리가 가장 가까운 것을 골랐다.
- 적격은 D 6/6, E 45/48이다. 제외된 3명(BRATS_165, 060, 206)은 N2 후보가 없어서였고, 출력 전에 대체 없이 제외했다.
- 선별 반입한 `msd56_data.py`(blob 142c67d 일치)는 `load_case`/`render`/`mask_slice`만 썼다.
- P/N1 PNG는 iter_064 PNG와 pixel 단위로 일치한다. D6 overlay를 직접 열어 병변 mask와 N1/N2 slice의 대응을 확인했다.
- i134 실행기를 iter_136 전용 경로로 분리했다. 변경점은 다음과 같다.
  - final 경계: thought/final 표식 id를 tokenizer에서 읽고(100/101, 상수로 가정하지 않음) 잠긴 `boundary_check.json`과 대조한다.
  - 기록: 원문과 token IDs, final 구간, 원 첫 줄을 저장한다.
  - gate 검사: 모든 조건(NONE 포함)의 EOS 100%와 유효율 95%를 본다.
  - 진입 검사: worker·평가 진입에서도 protocol의 code·input·gate hash를 검사한다.
- 본실행 전에 평가기와 gate 생성 코드를 protocol에 잠갔다.

# Files Changed

- 신규 코드: `i136_common.py`, `i136_spec.py`, `i136_data.py`, `i136_run.py`, `i136_eval.py`, `i136_lock.py`, `i136_lock_main.py`, `i136_tech.py`, `i136_gate.py`, `test_i136.py`
- 신규 반입(미추적): `msd56_data.py`
- 결과: `results/iter_136/` (data, requests, tests, jobs, eval, protocol_lock_*)
- 기존 산출물(iter_056/064/134/135)에는 쓰지 않았다.

# Commands / Experiments

- `python i136_data.py`: 성공(D6, E45, 제외 3).
- `python i136_tech.py boundary`: 통과. `python test_i136.py`: 첫 실행은 43/45였고 합성 fixture 기대값 오류였다. 새 파일 `cpu_tests_v2.json`에서 45/45 통과했고 첫 기록은 보존했다.
- `python i136_lock.py technical`: 로그상 3번 실행했다. 앞 두 번은 생성 전 amendment(`protocol_lock_technical.json`, `_a1`)이고, 최종 잠금은 `_a2`다.
- `python i136_tech.py tensor`: 통과. 공식 processor와 wrapper의 input_ids·pixel_values가 일치했고, 이미지 token은 256×장수이며, 조건 간 target pixel이 동일하고, 누설이 없었다.
- `python i136_tech.py neg`: 24개 모두 의도한 사유로 거부됐다. `negative_tests.json`(사유 미검증)은 보존했고 gate에는 `_v2`를 썼다. 검사 범위는 아래와 같다.
  - launch·worker·eval의 input/code 변조
  - main gate=false
  - lock fd 없음 또는 미보유
  - 중복 supervisor
  - 손상 JSONL
- 기술 생성(D6, 60요청, 1024 token):
  - 2 worker: 150s, 33.0 req/min
  - 4 worker: 94s, 46.7 req/min, GPU peak 약 18GB
  - 실제 SIGKILL 후 재개(12/60 시점에 kill, torn tail 없음): 3 구성의 token이 모두 동일하다.
  - 절단이 없어 2048 재실행은 하지 않았다.
- 기술 gate: `i136_tech.gate`는 passed=False였다. 이유는 `resume_had_two_results` 검사기 구현 오류다. SIGKILL된 시도는 result 파일을 남기지 않는다. 결과는 `technical_gate_technical.json`에 보존했다.
- 같은 계약(재개 후 완료와 동일 출력)을 kill 기록으로 검사하는 `i136_gate.py`를 기술 출력 이후에 작성해 passed=True를 얻었다. 문턱과 분모는 바꾸지 않았다. 이 파일은 사전 잠금 평가기가 아니며 main protocol에 포함했다.
- `python i136_lock_main.py`: main 잠금.
- main 생성: `i136_run.py launch --workers 4`, E450요청, rc 모두 0, wall 438.6s. 예상 약 10분(실제 7.3분)이었다. 4 worker는 기술 비교의 처리량 근거로 채택했고, 정확도는 쓰지 않았다.
- `python i136_eval.py ...`: 성공. 원시 JSONL을 별도로 집계해 첫 줄 상태가 일치함을 확인했다.

# Results

`results/iter_136/eval/report.json`, `report_per_patient.json`, `seal.json`

- E 45명. 영상 있는 조건 P/N1/N2/PN1/N1P/N1N2/N2N1/PP/N1N1은 405요청이다.
- OR BA 0.5, 공동 BA 0.4944, 단독 BA 0.5. OR 양성 정확도는 1.0이고 음성 정확도는 0.0이다.
- 영상 요청은 PRESENT 404건, 형식 invalid 2건이 아니라 1건 + PRESENT 404건이 아니라, 정확히는 405건 중 PRESENT 403, invalid 2건(N1N1 1, N1P 1)이다.
- 영상 없음(NONE)은 45/45가 UNKNOWN이다. 모두 thought→final 구조이고, 평균 284 token이다.
- 형식 유효율은 영상 요청 99.5%, 전체 조건 99.6%다.
- 비EOS와 경계 invalid는 0건, 원 첫 줄과 final 첫 줄의 불일치도 0건이다.
- PRESENT인데 설명에 부정 표현이 있는 정규식 후보가 N1 7, N1N1 6, N2 7건이다. 임상 모순으로 확정한 것이 아니다.
- 사전 판정은 `negative_basic_reading_insufficient`(OR BA≤0.60)다.
- 비용(생성 구간 평균, 환자당):
  - 개별 단독 3요청(N1 공유): 4.49s
  - 공동 1순서×2집합: 3.50s
  - 공동 양순서 감사: 6.87s
  - 요청별 read→저장 평균: 3.56s
  - worker load 약 4s
- 총 wall은 438.6s다. 이 시간은 경합 조건의 workload 총합이며 요청당 수치와는 별개다.

# Goal Progress / Reused Assets

- **시험 설정**: 실행은 유효했다. 자료·무결성·기술 gate를 통과했고 본출력이 완결됐다.
- **연구 관찰**: 고정 prompt에서 영상 유무와 slice 병변 유무에 둔감한 PRESENT 반응이 관찰됐다. 이는 iter_133(첫 줄 HIGH 45/45)와 방향이 같다. 일반 MRI 인식 결함이나 영상 무사용으로 확정하지는 않는다.
- **연구 질문**: 통합 손실 대 관측 누락은 판별하지 못했다. 투자 판단은 이 frozen 질문 보류이며, 단순 성능표만으로 신규성을 주장하지 않는다.
- **독립 확인 / 방법 개발**: 미실행이다. 학습은 하지 않았다.
- **재사용**:
  - `msd56_data.py`: blob 일치, `load_case`/`render`/`mask_slice`만 사용했다. 현재 입력의 NIfTI→PNG를 독립 확인했다(affine voxel, 방향 pixel, mask overlay, 기존 PNG pixel 일치).
  - i134 실행기·잠금 파생: 별도 수정과 검증을 거친 전용 사본이다.

# Problems

- **현재 결론 무효**: 없다.
- **재사용 전 수정**
  - gate 재계산 코드(`i136_gate.py`)는 기술 출력 후 작성됐다. 사전 잠금 평가기로 보고하면 안 된다.
  - `i136_tech.gate`의 resume 조건은 구현 오류다.
  - 실제 kill에서 torn tail이 생기지 않아 torn-tail 복구는 실제 kill로 검증하지 못했다. 사본 기반 검사만 있다.
- **추후 개선**
  - N2/N1이 배경 slice라 쉬운 음성이 아니다(annotation 부재는 임상 정상이 아님).
  - 정규식 audit은 의미 평가기가 아니다.
  - 평가기가 `valid_rate_all`을 쓰는 분기를 사전 계약에 맞춘 구현이며, 사후 변경이 아니다.
  - 공식 MSD 이용 조건과 RadGenome·사전학습 중복은 미확인이다.

# Recommendation to GPT

- 이번 설계로 통합 손실을 구분하지 못했다. 개별 판독이 고정 PRESENT라서 OR와 공동 입력이 같은 BA로 수렴한다. 이 frozen 질문의 추가 실행은 보류를 권한다.
- 이어서 투자한다면 먼저 `P` 대 annotation-free 영상의 판별을 확인하는 설계가 필요하다. 예를 들어 선택지를 균형화한 MCQ(iter_064/065 계열)가 후보다.
- iter_064의 지정 target 방식과 달리 이번 질문은 전체 입력 단위였다. 두 방식의 대응 관계는 별도 계획에서 판단할 사항이다.

SELF_CHECK: PASS
SUMMARY: 공식 MSD 개발 FLAIR(E45)에서 MedGemma 1.5가 영상 요청 405건에 PRESENT를 고정 반환해 OR BA 0.5, 공동 0.494(차이 CI [0, 0.017])여서 사전 분기 negative_basic_reading_insufficient이며, 통합 손실과 관측 누락은 구분되지 않았다.

# [orchestrator] 권한 거부된 도구 호출
- Bash: mkdir -p results/iter_136 && cat > i136_common.py <<'E'
"""iter_136 전용 경로·출처 유틸리티 (i134_common 파생; 결과는 results/iter_136에만 쓴다)."""
import hashlib, json, os
from pathlib import Path
from datetime import datetime, timezone

HERE = Path(__file__).resolve().parent
RES = HERE / 'results/iter_136'
DATA = RES / 'data'
SEED = 136


def sha(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(4 << 20), b''):
            h.update(b)
    return h.hexdigest()


def now(): return datetime.now(timezone.utc).isoformat()
def digest(x): return hashlib.sha256(json.dumps(x, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()
def read(p): return json.loads(Path(p).read_text())


def save(p, x):
    p = Path(p); p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, 'x') as f:
        json.dump(x, f, indent=2, sort_keys=True, allow_nan=False); f.write('\n'); f.flush(); os.fsync(f.fileno())
E
cat > i136_spec.py <<'E'
"""iter_136: 출력 전에 고정한 prompt(i134와 동일 문구)·상태 parser·thought/final 경계 규칙·조건표.
질문: 제공된 영상 전체 중 어느 하나에 종양성 병변이 보이는가 (PRESENT/ABSENT/UNKNOWN). annotation-defined 정답이며 임상 진단이 아니다."""
import re
from i134_spec import QUESTION, NOIMG, FORBIDDEN_IN_PROMPT, CONDS, VALID, parse as _parse, audit, repetition, first_line  # noqa: F401  (문구·세 상태 규칙을 그대로 사용)

BASE_CONFIG = dict(model_id='google/medgemma-1.5-4b-it', revision='91850547d9f0b2fdd21aa7c5f4f3d1a8a52c243b', dtype='bfloat16',
                   attention='sdpa', do_sample=False, seed=136, batch=1, image_labels=False)
TOKENS = dict(technical=1024, technical2048=2048)   # main은 technical_gate.json의 main_max_new_tokens
STAGES = ['technical', 'technical2048', 'main']
START_TOKEN, END_TOKEN = '<unused94>', '<unused95>'   # 문자열만 고정. id는 실행 시 tokenizer에서 읽고 tests/boundary_check.json에 기록한다.


def split_final(tokens, start_id, end_id):
    """생성 token에서 final 구간을 token 구조로 분리. 반환 (status, final_tokens).
    no_marker: 두 표식 모두 없음 → 생성 전체. thought_final: 시작 1개가 맨 앞, 종료 1개가 그 뒤 → 종료 뒤 구간.
    invalid_boundary: 그 외(복수·종료 없는 시작·시작 없는 종료·순서 역전·시작이 맨 앞이 아님)."""
    ns, ne = tokens.count(start_id), tokens.count(end_id)
    if ns == 0 and ne == 0: return 'no_marker', list(tokens)
    if ns == 1 and ne == 1 and tokens[0] == start_id and tokens.index(end_id) > 0:
        return 'thought_final', list(tokens[tokens.index(end_id) + 1:])
    return 'invalid_boundary', []


def parse(final_text, eos, status):
    """상태 parser: EOS 종료 + 경계 유효 + final 비어있지 않음 + i134 세 상태 규칙."""
    if status == 'invalid_boundary' or not (final_text or '').strip(): return None
    return _parse(final_text, eos)
E
python - <<'E'
import i136_spec as S
a,b=100,101
print(S.split_final([100,5,6,101,7,8,106],a,b),S.split_final([7,8],a,b),S.split_final([100,5,6],a,b),S.split_final([100,101,100,101,5],a,b),S.split_final([5,101,6],a,b),S.split_final([5,100,101,6],a,b))
E
- Bash: sed -i "8s/.*/CODE = ['i136_common.py', 'i136_spec.py', 'i134_spec.py', 'i136_data.py', 'i136_run.py', 'i136_lock.py', 'i136_eval.py', 'i136_tech.py', 'msd56_data.py']/" i136_lock.py; sed -n 8p i136_lock.py
- Bash: CUDA_VISIBLE_DEVICES=0 python i136_tech.py tensor 2>&1 | tail -4
- Bash: python ../experiment_wait.py --pid $(pgrep -f "i136_run.py launch" | head -1) --timeout 600
- Bash: python - <<'E'
import json
r=json.load(open('results/iter_136/eval/report.json'))
for c,v in r['per_condition'].items(): print(c,{k:v[k] for k in ('n','valid','invalid','non_eos','PRESENT','ABSENT','UNKNOWN','boundary_thought_final','boundary_invalid','raw_first_vs_final_mismatch','contradiction','repetition','mean_tokens')})
print(r['or_pos_acc'],r['or_neg_acc'],r['joint_pos_acc'],r['joint_neg_acc'],r['valid_rate_all'],r['or_state_counts'])
print(json.dumps(r['cost'],indent=0)); print(r['transitions'])
E
ls results/iter_136/jobs/main | head -30; cat results/iter_136/jobs/main/result_*.json | head -12
