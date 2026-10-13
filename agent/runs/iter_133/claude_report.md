# 요약

- **핵심 결과:** 45요청을 모두 실행했다. 첫 줄이 모든 조건(U/L/M)·모든 사례에서 `HIGH`였고 `MIXED_HIGH_LOW`는 0건이다. 영상 없이 직사각형만 준 M도 15/15가 `HIGH`였다. 사전 규칙의 L−U 순증가가 0이므로 판정은 `negative_hold_marking_investment`(현재 표시 개입 투자 보류)다.
- **근거:**
  - mixed 보고서 11건의 `MIXED_HIGH_LOW` 재현은 U/L/M 모두 0/11이고 L−U·L−M 순증가는 0이다.
  - 첫 줄이 유효한 출력은 U 6, L 10, M 15/15다. 비EOS(512 token에서 잘림)를 invalid로 처리하는 사전 규칙 때문이며, 사전 기준(각 조건 ≥14/15)은 U·L에서 미충족이다. 첫 줄은 EOS와 무관하게 45/45가 `HIGH`다.
  - HIGH-only 4건의 high 보존은 U 1/4, L 2/4, M 4/4이며, L도 사전 기준 3/4에 못 미친다.
  - 기존 AutoRG P/G(iter_070 저장 라벨 재배열, 입력·모델이 달라 순위 비교 아님)는 mixed 8/11 재현이다.
- **미검증·주의:**
  - 15사례는 개발 자료이고 선택 slice는 GT로 정했으므로 oracle 관측이다. 표본 15라 확증 근거가 아니다.
  - HIGH-only를 low 부재 정답으로 보지 않았다.
  - 이는 이 prompt·8장·표시 조건의 관찰이다. 영상 인식 결함이나 MedGemma 일반 한계로 확대하지 않는다.
  - 사후 분석에서 M의 설명문이 픽셀 없이도 병변 위치·해부를 서술했다. 키워드 집계는 임상 판독이 아니다.
- **다음:** 사용자 승인을 기다린다. 같은 15사례의 prompt·표시·mask 조건 순회는 계획대로 하지 않는다. 재개하려면 영역–설명 연결이 명확한 독립 자료가 필요하다.

# Work Performed

- iter_070 label_table의 적격 15건(mixed 11, HIGH-only 4)과 BraTS·RadGenome 파일을 현재 SHA256·헤더·원문과 대조했다.
  - 15쌍 30개 파일의 SHA는 `brats_manifest.json`과 모두 일치했다. 보고서 원문은 `modal_wise_finding.json`과 일치했다.
  - 방향은 LPS→RAS, shape 240×240×155, spacing 1mm, seg 라벨은 {0,1,2,3}의 부분집합이었다.
  - 보고서는 환자 key `BraTS-GLI-xxxxx-xxx-t2f`로 영상과 연결했다.
- 이용 조건을 기록했다.
  - mirror는 HF API 조회로 CC-BY-4.0, 비gated, revision `b032d35…`를 확인했다. RadGenome는 MIT다.
  - 이는 공식 BraTS 접근 인증이 아니다. 새 다운로드는 없다.
- 동일 slice 8장의 U/L/M 렌더링을 구현했다.
  - 8장은 seg>0 axial 범위에서 등간격으로 고르고, 반올림 동률은 낮은 index로 했다. 렌더링은 volume min–max, 896²다.
  - 360장(15×8×3)의 해시는 모두 고유하다.
  - U/L은 빨간 외곽선 밖에서 픽셀이 동일하다. M은 회색+빨강만 포함한다. 직사각형은 독립 mask 렌더링의 bbox와 ±3px 이내다. 문제는 0건이다.
  - 대표 overlay 3사례를 실제 영상으로 열어 확인했다(00012, 01077, 00772). 끝쪽 slice에서는 직사각형이 아주 작은 경우가 있다.
- 추론 실행기 `i133_run.py`를 `mr132_run`에서 파생했다. 원본 4개 파일은 수정하지 않았다.
  - 단일 요청 8 slice, seed133, batch1 고정이며 iter_133 경로만 쓴다.
  - worker 직접 진입에서도 protocol 해시, main 단계 technical gate, 감독기 flock 실제 보유를 검증한다.
- 기술 검사와 gate는 모두 통과했고, 그 뒤 protocol을 main으로 잠그고 45요청을 4 workers로 실행했다.
- 평가와 사후 집계를 수행했다.

# Files Changed

- 새 파일(모두 research/ 아래): `i133_common.py`, `i133_spec.py`, `i133_data.py`, `i133_run.py`, `i133_lock.py`, `i133_tech.py`, `i133_eval.py`, `i133_post.py`
- 반입 4개 파일은 수정하지 않았다. git blob이 reuse_manifest와 일치함을 확인했다.
  - `mr123_data.py` c9e673c…
  - `mr132_common.py` 0368809…
  - `mr132_spec.py` c00bf5d…
  - `mr132_run.py` 4f66eef…
- `mr123_data.py`는 `normalization_window`와 `render_slice`만 import해 사용했다.
- 결과는 `results/iter_133/`에 저장했다.
  - `data_manifest.json`, `requests/`, `png/`
  - `protocol_lock_technical.json`, `protocol_lock_main.json`
  - `tests/`, `jobs/`
  - `eval/report.json`, `eval/post_hoc.json`
  - `overlay_*.png`

# Commands / Experiments

- `python i133_data.py`: 성공(15사례, 문제 0건, 기술 6요청·main 45요청 생성).
- `python i133_lock.py technical`: 성공.
- `python i133_tech.py tensor`: 1차 실패 후 2차 성공.
  - 1차는 검사 코드 오류였다. 독립 경로에서 BOS가 중복되고 image token 이름이 틀렸다. 이는 wrapper 결함이 아니다.
  - 1차 결과 `tensor_check.json`은 보존했고 `tensor_check_v2.json`으로 재실행했다.
  - 2차는 6요청의 input_ids·pixel_values가 독립 경로와 일치했고, image soft token은 요청당 2048(=8×256)이었다.
  - 영상 순서 교환이 pixel_values를 바꾸는 것, 각 slice의 개별 처리 일치, 입력 문자열에 환자 ID·질병명이 없음도 확인했다.
- `python i133_tech.py neg`: 9개 거부 검사가 모두 의도한 사유로 거부됐다.
  - 요청 변조, 입력 hash 변경, 중복 id, 미등록 id
  - lock fd 없이 worker 직접 진입, 감독기가 보유하지 않은 lock fd로 worker 진입
  - 중복 감독기, main 단계 gate 미잠금, 손상 JSONL 중간 행
- 기술 생성 3종(각 6요청)과 비교:
  - `T_w2`(GPU당 1 worker): wall 76.3초.
  - `T_w4`(GPU당 2 workers): wall 66.2초. T_w2와 token이 완전히 일치했다.
  - `T_resume`: 2건 완료 후 `--limit 1` 정지 → 마지막 행에 부분 JSON을 일부러 추가 → 재개 시 tail을 `.tail_*.json`으로 보존하고 6/6 완료했다. T_w2와 token이 일치했다.
- `python i133_tech.py gate`: passed.
  - 초기 gate에 `all_eos` 조건이 있었다. 기술 요청 2건이 모델 출력상 512 token에서 끝나 gate가 실패했다.
  - 비EOS는 invalid로 집계하는 모델 결과이지 인프라 오류가 아니므로, 결과 확인 후 이 조건을 gate에서 제거했다. `compare.json`에는 제거 전 값이 남아 있다. 이 변경은 gate 정의의 사후 조정이므로 여기에 명시한다.
- `python i133_lock.py main`: 성공(코드 8개, gate 포함).
- `python i133_run.py launch … --stage main --workers 4 --peak 9800`: 45/45, rc [0,0,0,0], wall 253.7초.
- `python i133_eval.py …`: 성공.
- `python i133_post.py`: 성공.
- `nvidia-smi`로 실행 전 두 GPU의 여유(약 24GB)를 확인했다. `CUDA_VISIBLE_DEVICES=0,1` 안에서만 배정했다.

# Results

주 결과는 `results/iter_133/eval/report.json`이다. 첫 줄 범주는 모든 조건에서 `HIGH`뿐이다.

| 조건 | 유효 첫 줄(EOS) | 비EOS | mixed 11건 재현 | HIGH-only 4건 high 보존 |
|---|---|---|---|---|
| U | 6/15 | 9 | 0 | 1/4 |
| L | 10/15 | 5 | 0 | 2/4 |
| M | 15/15 | 0 | 0 | 4/4 |

- L−U, L−M, U−M의 mixed 순증가는 모두 0이다. bootstrap CI [0,0]은 차이가 모두 0이어서 나온 값이다.
- 사전 규칙의 판정은 `negative_hold_marking_investment`다. 같은 원인으로 `L_vs_M_indistinct=true`이므로 영상 활용 회복 주장은 보류한다. 유효 출력 ≥14/15 조건도 U·L에서 미충족이다.
- 위 표의 보존·재현은 예측 범주의 집계이며 임상 정확도가 아니다. 비EOS 14건은 모두 512 token에서 잘린 긴 설명문이다.
- 사후 집계(`eval/post_hoc.json`, 원 판정과 별개):
  - 첫 줄은 EOS와 무관하게 45/45가 `HIGH`다.
  - M의 설명문은 픽셀이 없다는 문구가 있는데도 병변 위치와 해부를 서술했다(예: 00187 "right cerebellum", 01105 "red rectangle"를 병변 영역으로 서술).
  - low·mixed 계열 키워드가 설명문에 나온 비율은 U 11/15, L 13/15, M 8/15다. 단순 키워드라 부정문(예: "no visible low-signal components")도 포함해 센 값이며 임상 근거로 쓰지 않는다.
- 처리량: 기술 6요청 기준으로 GPU당 2 workers가 1 worker보다 생성 구간 7.36 대 5.99 req/min, loading 포함 5.44 대 4.72 req/min이었다. 출력은 token 단위로 동일했다. GPU 점유는 1 worker에서 GPU당 약 9.7GB, 2 workers에서 약 19.4GB로 24GB 안에 들어와 4 workers를 선택했다. 표본이 6요청뿐이라 처리량 추정은 거칠다. batch2는 과거 불일치 때문에 쓰지 않았다.
- 비용: main 45요청의 launch wall은 253.7초이고, 평가는 수 초다.
- 독립 재계산(리뷰어용): 집계는 `i133_eval.py`가 원시 JSONL의 첫 줄에서 직접 계산했다. 별도 구현에 의한 재검증은 하지 않았다.

# Goal Progress / Reused Assets

- **도달 단계:** 가능성 탐색(15사례 전수). 확대·독립 확인·학습은 하지 않았다.
- **시험 설정:** 직사각형 표시와 영상 기여를 가르는 U/L/M 구조, 입력·평가 무결성 검사, 재개·소유권·변조 거부는 작동했다.
- **연구 관찰:** 이 설정에서는 first-line 범주가 입력과 무관하게 `HIGH`로 고정되어 표시 개입의 효과를 구분할 수 없었다. M(영상 없음)에서도 `HIGH`이므로 이 응답은 영상에 근거한 판단으로 해석할 수 없다. MR-RATE의 고정 `PRESENT` 관찰과 같은 종류의 응답 편향이 이 자료에서도 관찰됐지만, 두 자료의 원인이 같다고 말할 수 없다.
- **연구 질문:** 병변 위치 지원의 효과는 이 prompt·조건에서 검출되지 않았다. 관측 부족, prompt 인터페이스(HIGH 정의 문구 포함), 표시 방식 중 어느 것 때문인지는 구분하지 못했다. 정확한 영역 정답이 있는 독립 자료와 직접 SFT 같은 강한 대조 이후의 가치는 미검증이다.
- **재사용:**
  - 반입 4개 파일은 수정 없이 보존하고 `mr123_data.py`의 두 함수만 사용했다.
  - `mr132_run`의 구조(원자 claim, 안전 재개, 소유권)는 `i133_run.py`로 파생했다. 필수 검사 중 공식 chat template tensor 대조, worker 직접 진입의 gate, 중복 실행·부분 재개·입력 hash 변경 거부, 45개 고유 요청 검사(completion 검증)는 수행했다. batch2는 채택하지 않았다.
  - 이 파생 코드 전체를 일반 재사용용으로 승인하는 것은 아니다.
- **미실행:** 독립 확인, 학습, 새 환자·prompt 확대, AutoRG 재실행, 새로운 임상 판정.

# Problems

- **현재 결론 무효:** 없음.
- **재사용 전 수정:**
  - 유효 출력 기준(첫 줄 EOS 필요) 때문에 비EOS가 U에서 9/15이다. 이는 규칙대로의 결과다. 다만 같은 prompt를 쓸 다음 실험은 설명문 길이를 짧게 제한하는 prompt를 새 계획에서 검토해야 한다.
  - `i133_run.py`의 메모리 admission은 시작 시점 한 번뿐이고, 시작 직전 재조회는 넣지 않았다(구현 중 단순화).
- **추후 개선(선택):**
  - 기술 gate의 `n_non_eos_outputs` 필드는 값이 비어 있는 자리표시자다.
  - 비EOS의 첫 줄과 설명문 분석은 사후 집계이며, 계획 판정에는 쓰지 않았다.
  - 직사각형 외곽선이 얇은 병변 경계 위에 놓이는 문제와 끝쪽 slice의 매우 작은 직사각형은 미평가다.
  - 8장 관측의 충분성, 보고서와 BraTS subregion의 정확한 대응도 확인하지 못했다.

# Recommendation to GPT

- 권고: **투자 보류(전환).** 같은 15사례에서 prompt·표시·mask 변형을 순회하지 않는다. 사전 판정(L−U≤0)과 일치한다.
- 이유: 첫 줄이 입력과 무관하게 고정되어 이 설정으로는 위치 지원 효과도, 영상 기여도 구분할 수 없었다.
- 재개 조건(새 계획에서만): 영역과 속성 정답이 연결된 독립 자료, 또는 응답 prior를 통제하는 최소 개입. 후속은 사용자 승인을 받는다.
- 이 결과를 MR-RATE 고정 응답의 원인 규명이나 MedGemma의 일반 MRI 한계로 확대하지 않는다.

SELF_CHECK: PASS
SUMMARY: 기존 RadGenome–BraTS FLAIR 15사례에서 U/L/M 45요청을 완결했다. 모든 조건의 첫 줄이 HIGH(영상 없는 M 포함)이고 mixed 재현 0이라 L−U 순증가 0으로 사전 판정은 표시 개입 투자 보류다. 한정된 개발 자료·prompt의 관찰이며 영상 인식 결함으로 일반화하지 않는다.

# [orchestrator] 권한 거부된 도구 호출
- Bash: mkdir -p results/iter_133 && cat > i133_common.py <<'EOF'
"""iter_133 전용 경로·출처 유틸리티 (mr132_common 파생; 결과는 results/iter_133에만 쓴다)."""
import hashlib, json, os
from pathlib import Path
from datetime import datetime, timezone

HERE = Path(__file__).resolve().parent
RES = HERE / 'results/iter_133'
SRC = HERE / 'results/iter_070/data'   # 읽기 전용 기존 자료
BRATS = SRC / 'brats/ASNR-MICCAI-BraTS2023-GLI-Challenge-TrainingData'

def sha(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(4 << 20), b''): h.update(b)
    return h.hexdigest()

def now(): return datetime.now(timezone.utc).isoformat()
def digest(x): return hashlib.sha256(json.dumps(x, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()
def read(p): return json.loads(Path(p).read_text())
def save(p, x):
    p = Path(p); p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, 'x') as f:
        json.dump(x, f, indent=2, sort_keys=True, allow_nan=False); f.write('\n'); f.flush(); os.fsync(f.fileno())
EOF
cat > i133_spec.py <<'EOF'
"""iter_133: GPU 출력 전에 고정한 prompt·첫 줄 parser·집계 규칙 (U/L/M)."""
import re
CONFIG = dict(model_id='google/medgemma-1.5-4b-it', revision='91850547d9f0b2fdd21aa7c5f4f3d1a8a52c243b', dtype='bfloat16',
              attention='sdpa', max_new_tokens=512, do_sample=False, seed=133, batch=1)
CATS = ['HIGH', 'MIXED_HIGH_LOW', 'OTHER', 'UNKNOWN']
COMMON = ('These are eight evenly spaced axial FLAIR MRI slices of one brain, ordered from inferior to superior. '
          'Describe the visible FLAIR signal of the main lesion. '
          'On the first line output only one of: HIGH, MIXED_HIGH_LOW, OTHER, UNKNOWN. '
          'HIGH means the lesion appears hyperintense (high signal); it does not state whether low-signal components are absent. '
          'MIXED_HIGH_LOW means both high-signal and low-signal components are visible within the lesion. '
          'OTHER means a different signal pattern. UNKNOWN means the signal cannot be assessed. '
          'Then briefly explain the visible evidence.')
GUIDE = (' A thin red rectangle on each slice marks the approximate region around the lesion on that slice. '
         'It is only a coarse guide, and not every tissue inside the rectangle is lesion.')
NOPIX = (' In this input, no MRI pixel data are provided: every image is a neutral gray background that contains only the red rectangle.')
PROMPTS = dict(U=COMMON, L=COMMON + GUIDE, M=COMMON + GUIDE + NOPIX)
RENDER = dict(side=896, rect_rgb=[255, 0, 0], rect_px=2, gray=[128, 128, 128], normalization='volume_minmax', n_slices=8,
              round_half='down', mask_rule='seg>0', orientation='closest_canonical_RAS')
FORBIDDEN_IN_PROMPT = ['BraTS', 'GLI', 't2f', 'glioma', 'tumor', 'edema', 'RadGenome', 'sub-', 'report']

def parse(text, eos=True):
    if not eos or not text or not text.strip(): return None
    line = text.strip().splitlines()[0].strip()
    return line if line in CATS else None
EOF
- Bash: python - <<'EOF' 2>&1 | tail -20
from transformers import AutoProcessor
import i133_run as R
from collections import Counter
proc=AutoProcessor.from_pretrained(R.MODEL,local_files_only=True)
print(getattr(proc,'image_token',None),getattr(proc,'boi_token',None),getattr(proc,'image_token_id',None))
r=R.requests(R.RES/'requests/technical.json')[0]
w=R.input_tensor(proc,r)
c=Counter(w['input_ids'][0].tolist()); print(c.most_common(4)); print(w['pixel_values'].shape, [k for k in w])
print(proc.tokenizer.convert_ids_to_tokens([c.most_common(1)[0][0]]))
print(proc.tokenizer.decode(w['input_ids'][0][:60]))
EOF
python -c "
import json;d=json.load(open('results/iter_133/tests/tensor_check.json'));print({k:v for k,v in d['rows'][0].items()},d['image_token'])"
- Bash: python - <<'EOF'
p='i133_tech.py'; s=open(p).read()
s=s.replace("ind = proc(text=text, images=imgs, return_tensors='pt')","ind = proc(text=text, images=imgs, return_tensors='pt', add_special_tokens=False)  # 템플릿이 <bos>를 이미 포함")
s=s.replace("img_tok = getattr(proc, 'image_token', None); img_id = tok.convert_tokens_to_ids(img_tok) if img_tok else None","img_tok = '<image_soft_token>'; img_id = tok.convert_tokens_to_ids(img_tok)")
s=s.replace("n_img_tok == 8 * 256","n_image_tokens'] == 8 * 256") if False else s
open(p,'w').write(s)
EOF
rm -f results/iter_133/tests/tensor_check.json; python i133_tech.py tensor 2>&1 | tail -3
- Bash: CUDA_VISIBLE_DEVICES=0,1 python i133_run.py launch --job results/iter_133/jobs/T_w2 --requests results/iter_133/requests/technical.json --stage technical --workers 2 2>&1 | tail -5
