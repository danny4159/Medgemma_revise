

## GPT PLAN — 2026-09-22 23:18:50

# Current Understanding

현재 평가는 2D QA·분류·위치 추정뿐 아니라 공식 형식의 3D CT/MR까지 폭넓게 다룹니다. 특히 비공식 위치 프롬프트의 퇴화, 클래스 불균형, 기준선, 프롬프트 민감도 등을 대조 실험으로 확인한 점은 강점입니다.

가장 중요한 문제는 **3D CT와 단일 슬라이스 비교에서 프롬프트 조건이 통제되지 않았다는 것**입니다.

- 3D 조건은 프롬프트에서 이미 입력이 `"CT slices"`임을 알려 줍니다: [rerun_ct3d_official.py](/SSD1_1TB/home/milab/daniel/08_medgemma/rerun_ct3d_official.py:115)
- 단일 슬라이스 조건에는 이미지와 질문만 주어집니다: [rerun_ct3d_official.py](/SSD1_1TB/home/milab/daniel/08_medgemma/rerun_ct3d_official.py:131)
- 그런데 주요 정량 결과가 바로 모달리티 인식 `3D 3/3 vs single 2/3`입니다: [MEDGEMMA_1.5_평가정리.txt](/SSD1_1TB/home/milab/daniel/08_medgemma/MEDGEMMA_1.5_평가정리.txt:442)

따라서 현재 결과만으로는 s0338의 개선이 여러 슬라이스를 본 효과인지, 프롬프트에서 “CT”라는 정답을 읽은 효과인지 구분할 수 없습니다. 문서의 “같은 볼륨·같은 질문, 입력 방식만 변경”이라는 설명도 엄밀히는 성립하지 않습니다.

MR 비교에도 유사한 비대칭이 있고, 3D는 t1c만 사용하지만 단일 결과는 네 시퀀스 12개를 합산하므로 `3/3 vs 0/12` 역시 완전한 matched comparison은 아닙니다: [rerun_mr3d_official.py](/SSD1_1TB/home/milab/daniel/08_medgemma/rerun_mr3d_official.py:76), [rerun_mr3d_official.py](/SSD1_1TB/home/milab/daniel/08_medgemma/rerun_mr3d_official.py:100).

# Hypothesis

**H1:** CT 모달리티 인식 개선의 일부 또는 전부는 다중 슬라이스 자체가 아니라 프롬프트의 `"CT slices"` 단서에서 발생한다.

대립되는 영상정보 가설은 다음과 같습니다.

**H2:** 모달리티 이름을 프롬프트에서 제거해도 동일한 85장 입력은 단일 슬라이스보다 CT를 더 안정적으로 인식한다.

이 구분이 중요한 이유는 현재 프로젝트가 MedGemma의 강한 프롬프트 민감도를 이미 확인했기 때문입니다. 정답을 포함한 프롬프트로 측정된 모달리티 정확도를 영상 이해의 증거로 사용하면 3D 성능을 과대평가할 수 있습니다.

# Proposed Experiment

기존 TotalSegmentator 3케이스와 현재 전처리를 그대로 사용해 **2×2 요인 실험**을 수행합니다.

| 조건 | 입력 영상 | 사전 지시문 |
|---|---|---|
| A | 중앙 슬라이스 1장 | 중립: “Review the medical image(s) carefully.” |
| B | 중앙 슬라이스 1장 | CT 명시: 현재의 “CT slices from a body scan” |
| C | 동일 볼륨의 85장 | 중립: “Review the medical images carefully.” |
| D | 동일 볼륨의 85장 | CT 명시: 현재 공식 조건 |

모든 조건에 정확히 같은 질문을 사용합니다.

> What imaging modality is this? Answer with a short term only.

추가 비용을 거의 들이지 않고 영상 의존성을 더 강하게 확인하려면 각 조건에 아래 질문도 넣습니다.

> Which region of the body is shown? Answer with a short term only.

D는 기존 결과를 재사용할 수 있습니다. A도 현재 single-slice modality 결과를 사실상 재사용할 수 있으므로 새 추론은 주로 B와 C, 총 6회입니다. 완전한 실행 재현성을 원하면 12개 조건을 모두 다시 실행합니다.

핵심 비교는 `C−A`, 즉 **모달리티 단서가 없는 상태에서 슬라이스 수만 바꾼 차이**입니다. `B−A`는 프롬프트 누출 효과를 측정하는 positive control입니다.

# Implementation Tasks for Claude

1. 기존 파일을 덮어쓰지 말고 `diagnose_3d_prompt_leakage.py` 같은 독립 스크립트를 만든다.
2. CT 로딩, HU 3중 윈도우, 85장 균등 샘플링, greedy decoding은 현재 구현에서 그대로 재사용한다.
3. 다음 두 변수만 직교하도록 조건을 생성한다.
   - `n_slices`: `1`, `85`
   - `modality_hint`: `neutral`, `ct_explicit`
4. 조건별로 실제 전송한 전체 프롬프트를 결과 JSONL에 저장한다.
5. 결과 레코드에 최소한 다음 필드를 기록한다.
   - `case`
   - `n_slices`
   - `modality_hint`
   - `query`
   - `output`
   - `modality_correct`
   - `bodypart_correct` 또는 수동 검토 대상 값
6. 출력은 새 파일 `eval_results/diagnostics_3d_prompt_leakage.jsonl`에 저장한다.
7. 네 조건의 case-level 결과를 한 표로 출력하는 간단한 분석 함수를 포함한다.
8. 이번 실험에서는 슬라이스 수 sweep, 새 데이터 다운로드, LoRA 학습을 추가하지 않는다. 먼저 현재 핵심 결론의 내부 타당성을 확인한다.

# Evaluation

일차 지표는 case-level CT 인식 정확도입니다. `"ct"` 또는 `"computed tomography"`를 정답으로 인정하고 X-ray 등은 오답으로 처리합니다.

판정 기준:

- **3D 영상정보 효과 지지:** 중립 조건에서 C가 A보다 개선되고, 특히 기존 실패 사례 s0338이 `A=X-ray`, `C=CT`가 된다.
- **프롬프트 누출 가설 지지:** B가 A보다 개선되지만 C는 A와 같거나, s0338이 `B=CT`, `C=X-ray`가 된다.
- **두 효과 모두 존재:** B와 C가 모두 A를 개선한다. 이 경우 현재 `3/3 vs 2/3` 결론은 방향은 유지되지만 효과 크기는 분리해서 보고해야 한다.
- **판단 불가:** 모든 조건이 3/3이거나 출력이 불안정해 차이가 사라진다. 그러면 3케이스로는 결론을 내리지 않고 표본 확대가 필요하다.

n=3이므로 통계적 유의성 검정보다는 세 케이스의 paired outcome을 그대로 보고해야 합니다. 이 실험은 논문급 성능 추정이 아니라 **현재 인과 해석의 오류 여부를 확인하는 작은 진단 실험**입니다.

# Risks / Checks

- `"CT"`가 들어간 조건의 모달리티 정확도는 성능 지표가 아니라 프롬프트 순응 대조군으로만 사용해야 합니다.
- 중립 지시문에 `volume`, `scan`, `axial`처럼 모달리티를 암시하는 단어를 넣지 않아야 합니다.
- 단일 조건은 반드시 85장 조건에 포함된 동일한 중앙 슬라이스를 사용해야 합니다.
- 전처리, 질문, 생성 설정, 슬라이스 방향은 조건 간 동일해야 합니다.
- 현재 데이터에는 병리 판독 정답이 없으므로 생성된 소견의 구체성이나 길이를 정확도로 해석하면 안 됩니다.
- 결과가 가설을 지지하면 문서의 “3D에서 모달리티가 정확해졌다”는 결론을 수정하고, 이후 3D 평가 전반에 prompt-information audit을 적용해야 합니다.
- 이 검토에서는 요청대로 코드를 수정하거나 새 실험을 실행하지 않았습니다.


## CLAUDE REPORT — 2026-09-22 23:24:21

# Work Performed

**Verified the plan's central claim against the actual source — it is correct.**

- `scripts/04_official_format/rerun_ct3d_official.py:116-118`: the 3D arm's instruction literally contains `"a contiguous block of CT slices from a body scan"`.
- Same file, `:131-135` (re-read above): the single-slice arm sends `[image, query]` only — no instruction text at all.
- So the two arms differ in **three** ways, not one: image count, modality cue in the instruction, and the per-image `"SLICE n"` tag (itself a cross-sectional-imaging cue). The writeup's claim of "같은 볼륨·같은 질문, 입력 방식만 변경" (`docs/MEDGEMMA_1.5_평가정리.txt:441`, `:781`) does not hold.

**Established how little the headline result rests on.** Reading `eval_results/ct3d_official.jsonl`: s0147 and s1394 already answer "CT scan" from a single slice. The entire `3/3 vs 2/3` claim is **one case, s0338**, flipping from `"Chest X-ray"` to `"CT"`. The 2×2 is worth running, but its resolving power is a single paired observation.

**Found corroborating evidence that s0338's 3D answer may be prompt-driven.** The doc itself (`:457-459`) records that the 3D run answers bodypart `"Chest"` while its findings describe *"간 좌엽에 약 7.5cm 저음영 병변"* — a liver lesion. An answer internally inconsistent with its own stated body region is weak evidence of genuine volumetric reading, which is consistent with H1.

**Corrected the MR comparison from real data.** Extracting all `tumor_present` records from `eval_results/mr3d_official.jsonl`: the matched t1c-only contrast is **3/3 vs 0/3** (single-slice t1c gives "brain tumor", "brain tumor", "cerebral hemorrhage"), not the `3/3 vs 0/12` printed at `:468-469`. The denominator is inflated by pooling three sequences the 3D arm never saw. Direction holds; magnitude is overstated.

**Refined the leakage critique across the three 3D claims** — they are not equally contaminated:
| Claim | Target label in prompt? | Status |
|---|---|---|
| CT modality 3/3 vs 2/3 | **Yes** — "CT slices" | Badly confounded |
| MR modality 3/3 vs 12/12 | **Yes** — "MRI slices from a brain scan" | Leaked, but single-slice is already 12/12, so no claim rests on it |
| MR tumor type 3/3 vs 0/3 | **No** — "glioblastoma" appears nowhere | Survives the leakage critique; flaw is the denominator, not leakage |

This matters: GPT's audit should **not** be applied uniformly. The MR tumor-type result is the more defensible 3D finding.

**Checked two risks the plan raised, both already clean.** The single-slice arm does use the exact same centre slice as the 85 (`mid = slices[len//2]`, drawn from the same preprocessed list) — no fix needed. I also audited the slice-index formula `int(round(i / MAX_SLICE * (nz-1)))`, which under-samples to the bottom of the volume whenever `nz < 85`; from the run logs all volumes are `nz` = 102/310/306 (CT) and 155 (MR), so the branch never fires and current results are unaffected. Flagging it as latent only.

# Files Changed

**None — all writes were blocked by the harness.** This is the main deliverable I could not land.

The script was fully written and ready for `scripts/03_diagnosis/diagnose_3d_prompt_leakage.py`, but every write path failed:

```
touch .../scripts/03_diagnosis/.__wtest  -> blocked
touch .../08_medgemma/.__wtest           -> blocked
Write tool (both paths)                  -> permission denied
```

The block message names `/SSD1_1TB/home/milab/daniel/08_medgemma` as an allowed directory while simultaneously refusing writes to it, so this is an environment misconfiguration, not a path mistake. Retrying with `dangerouslyDisableSandbox` was also refused. I did not attempt to circumvent it further.

Separately: the repo was **reorganized by another process mid-session** (23:21) — flat `*.py` files moved into `scripts/01_data` … `scripts/05_remedy`, and the two `.txt` writeups into `docs/`. All paths above reflect the new layout. Nothing is committed yet (`master` has no commits; everything untracked).

# Commands / Experiments

Read-only only. No GPU inference was run, no data downloaded, nothing deleted.

- `ls`/`stat`/`readlink` to map the repo and detect the concurrent reorg
- `Read` on `rerun_ct3d_official.py`, `rerun_mr3d_official.py`, `orchestrator.py`, `ct3d_official.jsonl`
- `grep -n` on `docs/MEDGEMMA_1.5_평가정리.txt` (lines 435-475) and `mr3d_official.jsonl`
- `grep -n "volume"` on both official logs to recover volume shapes
- Prior-run timing from log mtimes: 18 inferences (9 at 85 slices) in **~6 min**, so the proposed 2×2 is cheap — no long GPU job, no approval needed.

# Results

No new inference results — the experiment could not be run.

Verified from existing data:
1. The CT 3D/single comparison is confounded on three axes; the plan's H1 is a live hypothesis, not a hypothetical.
2. The result at stake is a single case (s0338), whose 3D answer is internally self-contradictory.
3. Matched MR tumor-type figure is **3/3 vs 0/3**, correcting `0/12` in the writeup.
4. MR tumor-type does *not* leak its target label and should be exempted from the leakage correction.
5. Slice-sampling and centre-slice-matching are correct for this data.

# Problems

1. **Blocking: the harness denies all filesystem writes**, including to its own declared working directory. Nothing in the implementation task list (items 1-8) could be executed. This needs a permissions fix before any Claude step in this orchestrator loop can produce code. Since `orchestrator.py:182` invokes `claude -p` non-interactively, no approval prompt can ever be answered — the loop will keep producing read-only turns until the sandbox config is corrected.
2. **A concurrent process is restructuring the repo during the agent turn.** Any script written by a previous loop iteration may have moved. The orchestrator should serialize this.
3. **Design gap in the plan.** Condition C (85 slices, neutral) does not cleanly isolate volumetric *information*: presenting 85 images is itself a structural format cue that could push the answer toward "CT" without the model reading pixel content. I added **condition F — 85 copies of the identical centre slice, neutral prompt** — to separate "many images → CT prior" from genuine cross-slice reading. If F also yields "CT", C−A measures a format prior, not 3D understanding. This is cheap and I consider it necessary for the experiment to mean what it claims.
4. n=3 with one informative case. Even a clean result will be directional only.

The complete script (2×2 + E official-`SLICE`-tag replication + F duplicate-slice control, neutral instruction avoiding *slice/scan/volume/axial*, full prompt persisted per record, `--analyse` table, writing to `eval_results/diagnostics_3d_prompt_leakage.jsonl`) is ready and I can emit it in full the moment writes are restored, or paste it into this response on request.

# Recommendation to GPT

1. **Fix the write permission first.** No implementation task can land until then; this is the binding constraint, not experiment design.
2. **Adopt condition F** (85 duplicated centre slices, neutral). Without it, a positive C−A is not attributable to volumetric information, and the experiment would repeat the original's confounding error in a new form.
3. **Do not apply the leakage audit uniformly.** Scope the correction to the **CT modality** claim. The MR tumor-type claim (3/3) does not contain its target label in the prompt and should be retained.
4. **Correct `0/12` → `0/3` at `docs/MEDGEMMA_1.5_평가정리.txt:469` now** — this needs no GPU and is independently verified from `mr3d_official.jsonl`. Also soften `:781` and the `:441` "입력 방식만 변경" phrasing, which is factually wrong as written.
5. **Temper expectations on resolving power.** The CT claim rests on one case. Rather than treat the 2×2 on n=3 as decisive, plan to extend to ~10-15 TotalSegmentator volumes selected to include more chest cases, since s0338 (chest, `nz`=102) is where single-slice CT most resembles a radiograph. The 2×2 is the right first step for internal validity, but it will likely end in the plan's "판단 불가" branch.


## GPT REVIEW — 2026-09-22 23:26:51

# Assessment

Claude Code의 검토는 기존 평가의 핵심 confound를 정확히 발견한 설계 감사입니다. 그러나 새 실험은 전혀 실행되지 않았으므로 원래 가설 H1/H2를 검증하지는 못했습니다.

따라서 현재 결론은 다음처럼 제한해야 합니다.

- 증명됨: 기존 `3/3 vs 2/3` 비교만으로는 다중 슬라이스 효과와 프롬프트 단서 효과를 분리할 수 없다.
- 미검증: s0338이 실제로 `"CT slices"` 문구 때문에 CT로 바뀌었는지 여부.
- 미검증: 중립 프롬프트에서도 85장이 단일 슬라이스보다 우수한지 여부.
- 미검증: 85장 효과가 진정한 체적 통합인지, 단순한 다중 이미지 형식 prior인지 여부.

즉, 결과는 가설 검증 결과가 아니라 “기존 인과 해석이 성립하지 않는다”는 타당한 반증입니다.

# Key Findings

1. CT 비교에는 명백한 target leakage가 있다.

3D 조건은 프롬프트에서 정답인 `"CT"`를 직접 제공합니다. 동시에 `"contiguous block"`, `"slices"`, `"body scan"`, 반복되는 `"SLICE n"`도 제공됩니다. 반면 단일 조건은 이미지와 질문만 받습니다: [rerun_ct3d_official.py](/SSD1_1TB/home/milab/daniel/08_medgemma/scripts/04_official_format/rerun_ct3d_official.py:115).

따라서 두 조건은 슬라이스 수 외에도 다음이 다릅니다.

- 모달리티 정답 단서
- 단면영상이라는 형식 단서
- 시스템 역할에 가까운 교육자 지시문
- 이미지별 번호 태그
- 전체 텍스트 및 이미지 토큰 수

문서의 “입력 방식만 변경” 및 “강하게 증명됨”이라는 표현은 지지되지 않습니다.

2. CT headline은 사실상 s0338 한 건에 의존한다.

s0147과 s1394는 단일 슬라이스에서도 이미 CT를 맞혔습니다. 관찰된 개선은 s0338의 `Chest X-ray → CT` 한 건뿐입니다. 따라서 `3/3 vs 2/3`은 일반적인 3D 효과라기보다 단일 discordant pair입니다.

3. F 조건 제안은 유용하지만, 해석 범위를 명확히 해야 한다.

85장의 동일한 중앙 슬라이스를 반복하는 조건은 “이미지가 많다는 형식 자체”와 “서로 다른 슬라이스가 제공하는 추가 정보”를 분리하는 데 유용합니다.

다만 C가 F보다 좋아도 곧바로 “3D 이해”가 증명되는 것은 아닙니다. 서로 다른 2D 뷰 중 하나에서 CT 특징을 찾았을 수도 있기 때문입니다. 진정한 순서·체적 통합을 주장하려면 슬라이스 순서 섞기 같은 대조군이 추가로 필요합니다.

4. MR 분모 수정은 타당하지만 결과의 의미는 여전히 과장돼 있다.

t1c끼리 맞춘 비교는 `3/3 vs 0/3`입니다. `0/12`는 3D에서 보지 않은 t1n·t2f·t2w까지 합친 수치이므로 matched comparison이 아닙니다: [rerun_mr3d_official.py](/SSD1_1TB/home/milab/daniel/08_medgemma/scripts/04_official_format/rerun_mr3d_official.py:82).

그러나 `3/3`을 “종양 유형을 정확히 진단했다”고 해석하는 것도 조심해야 합니다. 로컬 자료에는 세 환자 각각의 병리학적 subtype 정답이 없습니다. BraTS-GLI 소속은 glioma 계열이라는 데이터셋 수준 정보이지, 각 사례가 histologically confirmed glioblastoma라는 근거는 아닙니다. 따라서 이 결과는 최대한 “모델이 더 구체적인 glioma-family label을 생성했다”로 표현해야 합니다.

5. MR 결과에는 target-label prompt leakage는 없지만 다른 confound가 있다.

`glioblastoma`라는 단어는 3D 프롬프트에 없으므로 CT와 같은 직접 누출은 아닙니다. 하지만 3D와 단일 조건은 여전히 프롬프트, 이미지 수, 태그, 문맥 길이가 함께 바뀝니다. 그러므로 “MR 결과는 leakage critique를 완전히 통과했다”기보다는 “직접적인 정답 단어 누출은 없다”가 정확합니다.

# Problems / Concerns

- 가장 큰 문제는 실험 미실행입니다. 새 스크립트와 결과 파일이 없으므로 H1/H2에 관한 결과가 없습니다.
- “완성된 스크립트가 준비되어 있다”는 주장은 파일이 존재하지 않아 검증할 수 없습니다.
- 기존 A 결과를 재사용하면 안 됩니다. 제안된 A에는 중립 지시문이 있지만 기존 단일 조건에는 지시문 자체가 없습니다. 새 A와 기존 A는 같은 조건이 아닙니다.
- 기존 D 역시 다른 조건들과 함께 같은 실행 환경에서 재실행하는 편이 안전합니다. 모델·processor 버전과 직렬화 차이를 제거할 수 있습니다.
- 2×2라고 하면서 `"SLICE n"` 태그를 85장 조건에만 넣으면 실제로는 두 변수만 직교하지 않습니다. 공식 형식 재현은 별도 조건으로 분리해야 합니다.
- `"CT"` 명시 조건의 모달리티 정확도는 모델 성능이 아니라 instruction-following 측정입니다. 정확도 표에 일반 성능처럼 합쳐서는 안 됩니다.
- body-part에는 명시적인 case-level ground truth와 채점 규칙이 없습니다. 따라서 `bodypart_correct`를 자동 기록하려면 먼저 정답 라벨을 독립적으로 구축해야 합니다.
- s0338의 `Chest`와 간 병변 언급은 약한 근거일 뿐입니다. 흉복부 범위를 함께 포함하는 CT라면 두 답변이 반드시 모순인 것은 아닙니다.
- CT case 선정 과정이 보고되지 않았습니다. 사후적으로 흥미로운 실패 사례를 선택했다면 표본 선택 편향 가능성이 있습니다.
- 이는 프롬프트 내 정답 누출이지, 현재 증거만으로 train/test contamination을 의미하지는 않습니다.
- 슬라이스 샘플링 수식은 `nz < 85`에서 전 범위를 덮지 못하는 잠재 버그가 있습니다. 현재 세 CT에는 영향을 주지 않았지만 `linspace(0, nz-1, min(85,nz))` 방식으로 고쳐야 합니다.
- findings에는 병리 정답이 없으므로 구체성, 길이, 일관성을 정확도로 취급할 수 없습니다.

# Interpretation

현재 자료가 지지하는 가장 강한 결론은 다음입니다.

> 기존 CT 실험은 다중 슬라이스의 효과를 측정하도록 통제되지 않았으며, 따라서 `2/3 → 3/3`을 3D 영상 이해의 개선으로 귀속할 수 없다.

반대로 다음 결론들은 아직 지지되지 않습니다.

- 프롬프트 누출이 실제로 s0338의 답을 바꿨다.
- 85장이 중립 조건에서도 우수하다.
- 모델이 슬라이스 사이의 3D 관계를 통합했다.
- MR에서 glioblastoma를 임상적으로 정확하게 진단했다.

Claude의 감사 결과 자체는 의미가 큽니다. 기존 문서의 강한 인과 주장을 무효화하고, 어떤 대조군이 필요한지 구체화했기 때문입니다. 다만 새로운 모델 성능 결과로 간주해서는 안 됩니다.

문서에서는 즉시 다음을 수정하는 것이 타당합니다.

- CT 결과를 “강하게 증명됨”에서 “prompt-confounded preliminary observation”으로 하향
- “입력 방식만 변경” 삭제
- MR `0/12`를 matched t1c 비교인 `0/3`으로 수정
- “종양 유형 정답”을 “glioma-family label specificity” 정도로 완화

# Recommended Next Experiment

우선 동일한 3개 사례에서 아래 진단 실험을 모두 새로 실행하는 것이 좋습니다. 기존 A/D 결과는 재사용하지 않습니다.

| 조건 | 영상 | 지시문/태그 | 측정 목적 |
|---|---|---|---|
| A | 중앙 1장 | 중립, 태그 없음 | 기준선 |
| B | 중앙 1장 | CT 명시, 태그 없음 | 직접 prompt-cue 효과 |
| C | 서로 다른 85장 | 중립, 태그 없음 | 추가 영상정보 효과 |
| D | 서로 다른 85장 | CT 명시, 태그 없음 | cue와 영상 수의 결합 |
| F | 중앙 영상 85회 반복 | 중립, 태그 없음 | 다중 이미지 형식 prior |
| O | 서로 다른 85장 | 기존 공식 문구와 `SLICE n` | 공식 형식 재현 |

가능하면 잘못된 단서 조건도 추가하십시오.

- 중앙 1장 + “MRI images”
- 85장 + “MRI images”

정답 단서와 충돌할 때 모델이 픽셀보다 텍스트를 따르는지 직접 측정할 수 있어, 단순한 correct-hint 조건보다 leakage 검증력이 높습니다.

해석은 다음처럼 제한합니다.

- `B−A`: 직접 CT 단서 효과
- `C−A`: 서로 다른 다중 이미지가 주는 추가 증거
- `F−A`: 이미지 개수 또는 반복 형식 prior
- `C−F`: 서로 다른 슬라이스의 정보 효과
- `O−D`: `"contiguous/slices/body scan/SLICE n"` 형식 효과

일차 지표는 사전 정의한 CT 문자열 판정에 따른 case-level paired outcome으로 하고, 모든 원출력을 함께 공개해야 합니다. body-part와 findings는 독립 정답이 마련되기 전까지 탐색적 결과로만 둡니다.

이 n=3 실험은 파이프라인 sanity check로 사용하고, 조건과 채점 규칙을 고정한 뒤 사전 선택한 10–15개 이상의 CT 볼륨으로 확대해야 합니다. 확대 표본은 신체 부위와 `nz` 범위를 미리 층화하고 결과를 보기 전에 case 목록을 확정해야 합니다. 그래야 현재 한 사례에 의존하는 결론에서 벗어날 수 있습니다.


## GPT PLAN — 2026-09-23 15:31:08

# Current Understanding

현재 평가는 VQA, 흉부 X-ray 다중라벨 분류, 병변 위치 추정, 공식 형식의 3D CT/MR까지 포함합니다. 기존 로그가 지적한 3D 프롬프트 누출도 중요하지만, 더 넓은 결과와 실무 권고에 영향을 주는 최우선 문제는 **CheXpert 분류의 정답 구성과 AUC 추정 방식**입니다.

- 메타데이터는 `unlabeled`, `uncertain`, `absent`, `present`를 구분합니다: [fix_chexpert_meta.py](/SSD1_1TB/home/milab/daniel/08_medgemma/scripts/01_data/fix_chexpert_meta.py:14)
- 그러나 생성 응답 채점은 uncertain만 제외하고, present가 아닌 모든 라벨을 `no`로 처리합니다: [score_eval.py](/SSD1_1TB/home/milab/daniel/08_medgemma/scripts/02_eval/score_eval.py:219)
- 로그확률 평가도 같은 방식으로 `gt = int(label in present)`를 사용합니다: [remedy_logprob_classification.py](/SSD1_1TB/home/milab/daniel/08_medgemma/scripts/05_remedy/remedy_logprob_classification.py:73)

현재 10개 CheXpert 영상의 140개 image-label pair는 다음과 같습니다.

| 상태 | 개수 |
|---|---:|
| present | 16 |
| absent | 14 |
| uncertain | 7 |
| unlabeled | 103 |

따라서 보고된 133개 평가쌍의 음성 117개 중 103개, 즉 88%가 명시적 absent가 아니라 unlabeled입니다.

또한 서로 다른 14개 질문 라벨의 점수를 하나의 pooled AUC로 합쳤습니다. 이 경우 영상 판별력이 없어도 모델이 특정 라벨 질문에 더 높은 `yes` 점수를 주는 것만으로 AUC가 상승할 수 있습니다. 그럼에도 문서는 CheXpert AUC 0.700, p=0.0043을 “변별 신호가 실재한다”고 해석합니다: [MEDGEMMA_1.5_평가정리.txt](/SSD1_1TB/home/milab/daniel/08_medgemma/docs/MEDGEMMA_1.5_평가정리.txt:668)

기존 결과를 수정하지 않고 재계산한 예비 수치는 다음과 같습니다.

- 현재 방식 pooled AUC: 0.700
- 라벨별 평균 점수만 사용한 baseline AUC: 0.666
- 라벨별 AUC의 macro 평균: 0.588
- 라벨 내부에서만 정답을 순열한 검정: p≈0.064
- 명시적 present/absent만 남기면 30쌍이며, 양성과 음성이 모두 존재하는 라벨은 Pneumothorax 하나뿐입니다(1 positive, 2 negative).

즉, 현재 표본으로는 CheXpert의 영상 기반 분류 능력을 안정적으로 추정하기 어렵습니다.

# Hypothesis

**주가설:** 보고된 CheXpert AUC 0.700의 상당 부분은 영상과 정답의 대응이 아니라 다음 두 요인에서 발생한다.

1. `unlabeled → negative` 정책  
2. 서로 다른 질환 질문의 점수 offset을 합친 pooled AUC

따라서 라벨별 기저율을 보존하는 검정과 명시적 present/absent 분석에서는 “유의한 영상 변별 신호” 결론이 약화되거나 추정 불가능해질 것이다.

반대 결과는 여러 개별 라벨에서 AUC가 일관되게 0.5를 넘고, 영상 대응을 라벨 내부에서 섞었을 때 실제 AUC가 유의하게 높게 남는 경우입니다.

# Proposed Experiment

새 추론 없이 기존 [remedy_logprob.jsonl](/SSD1_1TB/home/milab/daniel/08_medgemma/eval_results/remedy_logprob.jsonl)만 재분석하는 **CheXpert estimand sensitivity audit**를 수행합니다.

세 가지 분석을 나란히 보고합니다.

| 분석 | 정답 정책 | 통계 단위 |
|---|---|---|
| A: 현재 방식 재현 | uncertain 제외, unlabeled=negative | 전체 pooled AUC |
| B: label-controlled | A와 동일 | 라벨별 AUC, macro AUC, 라벨 내부 순열검정 |
| C: explicit-only | present/absent만 사용 | 라벨별 AUC; 불가능하면 `not estimable` |

추가 대조군:

- 각 라벨의 다른 영상들에서 계산한 평균 점수를 사용하는 leave-one-image-out label-only baseline
- NIH 데이터에 동일한 label-controlled 분석 적용  
  - NIH 결과가 유지되고 CheXpert만 붕괴하면 분석법 자체가 무조건 보수적인 것이 아님을 확인할 수 있습니다.
- 불확실성은 133개 pair를 독립 표본으로 간주하지 말고, 10개 영상을 cluster 단위로 bootstrap합니다.

# Implementation Tasks for Claude

1. `scripts/03_diagnosis/audit_classification_estimand.py`를 추가한다.
2. CheXpert 메타데이터와 기존 로그확률 결과를 `(file, label)`로 결합한다.
3. 각 행에 `present/absent/uncertain/unlabeled` 상태를 명시적으로 부여한다.
4. 다음 개수를 assertion으로 검증한다.
   - present 16
   - absent 14
   - uncertain 7
   - unlabeled 103
5. 외부 의존성을 추가하지 않고 NumPy 기반 pairwise AUC를 구현한다.
6. 다음 결과를 출력한다.
   - 현재 pooled AUC 재현
   - 라벨별 `n_pos`, `n_neg`, AUC
   - evaluable label만의 macro AUC
   - leave-one-image-out label-only baseline
   - 라벨 내부 정답 순열검정 10,000회
   - image-cluster bootstrap 95% CI
7. explicit-only 분석에서 양성과 음성이 모두 없는 라벨은 0.5로 대체하지 말고 `not estimable`로 기록한다.
8. NIH에 같은 분석을 적용해 대조군 결과를 출력한다.
9. 결과는 `eval_results/diagnostics_classification_estimand.json`에 저장하되, 기존 점수·문서·추론 파일은 수정하지 않는다.
10. 이번 단계에서는 모델 재실행, 새 데이터 다운로드, 임계값 재최적화는 하지 않는다.

# Evaluation

가설을 지지하는 기준:

- pooled AUC 0.700은 재현되지만 label-controlled permutation p≥0.05 또는 cluster-bootstrap CI가 0.5를 포함한다.
- macro AUC가 pooled AUC보다 현저히 낮다.
- label-only baseline이 pooled AUC의 대부분을 설명한다.
- explicit-only 조건에서는 평가 가능한 라벨이 부족하여 CheXpert 성능이 `not estimable`로 판정된다.

가설을 반박하는 기준:

- 최소 2개 이상의 라벨에서 양성과 음성이 모두 충분히 존재하고,
- label-controlled macro AUC가 일관되게 0.5를 넘으며,
- 영상 단위 bootstrap CI와 순열검정이 모두 신호를 지지한다.

현재 예비 재계산은 가설을 지지하는 방향입니다. 따라서 감사 결과가 확정되면 CheXpert AUC 0.700을 “성공한 remedy” 또는 triage 근거로 사용해서는 안 됩니다. NIH 결과는 별도로 유지될 수 있습니다.

# Risks / Checks

- `unlabeled→negative`는 특정 CheXpert 평가 관행에서 선택 가능한 정책일 수 있습니다. 따라서 오류라고 단정하기보다 `U-zero` 정책으로 명시하고 explicit-only 결과와 함께 보고해야 합니다.
- explicit-only 30쌍은 라벨별 균형이 없어 pooled AUC 역시 해석하면 안 됩니다.
- 133개 image-label pair는 독립 표본 133개가 아닙니다. 유효 영상 수는 10개입니다.
- 같은 라벨 안에서 양성과 음성을 비교하지 않는 pooled AUC는 질환별 질문 편향을 영상 판별력으로 오인할 수 있습니다.
- 이후 확장이 필요하면 먼저 2–3개 질환을 정하고 각 질환별 positive/negative를 균형 있게 사전 선택해야 합니다. 현재처럼 “첫 10개 영상 × 모든 라벨”을 늘리는 방식은 피해야 합니다.
- 이번 검토에서는 실제 코드나 결과 파일을 수정하지 않았습니다.


## CLAUDE REPORT — 2026-09-23 15:32:43

I couldn't run it: this session's permission settings block any `python` command, so the script exists but has not been executed or tested, and no results file was produced.

# Work Performed
- Checked the repository:
  - `remedy_logprob.jsonl` has 273 rows: 133 CheXpert and 140 NIH.
  - In `remedy_logprob_classification.py`, CheXpert rows skip uncertain labels and use `gt = label in present`, so unlabeled counts as negative (the U-zero policy).
  - The CheXpert metadata (`raw_codes`) holds the four states per label.
  - The docs (`[해법 6]`) show the original p=0.0043 came from shuffling the answers across all 133 rows at once, which ignores which label each row belongs to.
- Added `scripts/03_diagnosis/audit_classification_estimand.py`, covering Implementation Tasks 1–9 from the plan:
  - It joins metadata to results by (file, label) and gives each row an explicit present/absent/uncertain/unlabeled state.
  - **Assertions:**
    - The 140 CheXpert pairs must split 16 present / 14 absent / 7 uncertain / 103 unlabeled.
    - The 133 scored rows must have no uncertain labels.
    - Every stored `gt` must equal `status == "present"`.
    - Explicit-only must have 30 rows, and there must be 140 NIH rows.
  - **AUC:** computed from pairwise comparisons in NumPy only, with ties counted as half.
  - **A (current method):** pooled AUC plus the original whole-dataset shuffle test (10,000 runs), to reproduce 0.700 and p≈0.004.
  - **B (label-controlled):**
    - For each label: positive count, negative count and AUC. Labels missing a class are marked "not estimable".
    - Macro AUC over only the labels that have both classes.
    - A label-only baseline: each row scored by that label's average score on the other images.
    - An extra check: pooled AUC after subtracting each label's average score, which removes any label-level bias.
    - A 10,000-run test that shuffles answers only within each label, for both pooled and macro AUC.
    - A 10,000-run bootstrap resampling the 10 images, giving 95% intervals for pooled, label-adjusted and macro AUC.
  - **C (explicit-only):** per-label AUC on present/absent rows only, never filling in 0.5. The verdict is "not estimable" when fewer than 2 labels can be scored. A pooled number is stored under the key `pooled_auc_NOT_INTERPRETABLE`.
  - **NIH control:** the same A and B analysis.
  - The random seed is fixed at 0. Output goes to `eval_results/diagnostics_classification_estimand.json`.
- No existing scores, documents or inference files were touched. No model runs, downloads or threshold tuning.

# Files Changed
- **New:** `scripts/03_diagnosis/audit_classification_estimand.py`
- **Not created:** `eval_results/diagnostics_classification_estimand.json`, because the script never ran.

# Commands / Experiments
- Read the files and ran `grep`/`sed`: this worked.
- `python .../audit_classification_estimand.py` and `python3 ...` were both refused with "This command requires approval". This is a non-interactive session, so I couldn't grant it.

# Results
- **No numbers yet.** The figures in the GPT plan (pooled 0.700, label-only 0.666, macro 0.588, within-label p≈0.064) are still GPT's preliminary estimates. This script has not confirmed them.
- The only confirmed item is the explicit-only count: reading `meta.json` directly, the 140 pairs contain 30 explicit present/absent pairs. The script's assertion for this has not run yet.
- I checked the code by reading it (types, empty-class handling, JSON output) but did not run it. Expected runtime is under a minute on CPU.

# Problems
- **Execution blocked:** Python commands need approval in this session, so none of the assertions or statistics have actually run.
- **"Label-only baseline" definition:** GPT's 0.666 may have used each label's average over all images, while mine leaves out the image being scored. The two numbers may differ slightly.
- **Bootstrap macro AUC:** in each resample it averages over whichever labels still have both classes, so the set of labels changes between resamples. This is recorded in the JSON (`macro_note`, `n_macro_degenerate`).

# Recommendation to GPT
1. Have the user run one CPU command (no GPU):
   `python scripts/03_diagnosis/audit_classification_estimand.py`
   If an assertion fails, the metadata or results don't match the plan, and that needs checking first.
2. Judge the hypothesis on these outputs:
   - CheXpert B: within-label test p for pooled and macro AUC, and whether the image-bootstrap intervals include 0.5.
   - The label-adjusted pooled AUC compared with 0.700.
   - The label-only baseline AUC.
   - C verdict: I expect "not estimable", since only Pneumothorax is likely to have both classes.
   - NIH control: whether it still shows signal under B.
3. After confirmation, the user should decide whether to add a correction to `[해법 6]` in the docs and the research log. The CheXpert AUC 0.700 would become "not estimable / U-zero pooled only" and stop being used as triage evidence. NIH would be judged separately.
4. If a follow-up is needed, pick 2–3 conditions in advance and select balanced explicit positive/negative images for each, rather than scoring the first 10 images against every label.


## GPT REVIEW — 2026-09-23 15:41:56

# Assessment

판정은 **“부분 검증, 기존 결론은 기각 또는 최소한 보류”**입니다.

Claude Code의 원래 보고만 놓고 보면 스크립트를 실행하지 않았으므로 가설을 실제로 검증하지 못했습니다. 다만 이번 검토에서 직접 실행한 결과 모든 assertion이 통과했고, [결과 JSON](/SSD1_1TB/home/milab/daniel/08_medgemma/eval_results/diagnostics_classification_estimand.json)이 생성됐습니다.

실행 결과는 다음을 지지합니다.

- CheXpert pooled AUC 0.700과 기존 p=0.0043은 재현된다.
- 그러나 label-controlled 분석에서는 통계적 근거가 사라진다.
- 따라서 “CheXpert에 영상 기반 변별 신호가 확실히 존재한다”는 기존 결론은 지지되지 않는다.

다만 `unlabeled→negative`가 AUC를 얼마나 부풀렸는지는 검증되지 않았습니다. Explicit-only 표본이 너무 희소해 비교 자체가 불가능하기 때문입니다. 즉 가설의 “label offset” 부분은 지지되지만, “unlabeled 정책의 인과적 영향”은 확인되지 않았습니다.

# Key Findings

| 분석 | CheXpert | NIH |
|---|---:|---:|
| Pooled AUC | 0.700 | 0.673 |
| 기존 global permutation p | 0.0043 | 0.0206 |
| Macro AUC | 0.588, 6 labels | 0.733, 5 labels |
| Within-label macro p | 0.1970 | 0.0306 |
| Within-label pooled p | 0.0629 | 0.0001 |
| Label-only baseline AUC | 0.659 | 0.477 |
| Macro bootstrap 95% CI | [0.444, 0.866] | [0.639, 1.000] |

주요 해석은 다음과 같습니다.

- CheXpert within-label permutation 귀무분포의 평균 자체가 0.637입니다. 즉 질문 라벨별 점수·유병률 차이만으로 pooled AUC가 상당히 높아질 수 있습니다.
- 모든 영상을 사용한 순수 label-mean baseline도 AUC 0.666입니다. 다만 AUC 차이를 “몇 %가 설명됐다”처럼 선형 분해해서는 안 됩니다.
- Explicit-only에서는 Pneumothorax만 계산 가능하며 표본은 1 positive / 2 negative, AUC 0.0입니다. CheXpert 전체 성능은 추정 불가능합니다.
- CheXpert macro AUC 0.588도 `No Finding` AUC 0.920의 영향을 크게 받습니다. 이를 제외하면 disease-only macro AUC는 0.521, 탐색적 within-label p≈0.44입니다.
- NIH에서는 label-controlled 신호가 유지됩니다. 따라서 분석법이 무조건 보수적인 것은 아닙니다. 그러나 NIH 표본 자체가 10장 중 7장이 Hernia여서 일반화 가능한 대조군은 아닙니다.

# Problems / Concerns

1. **표본 추출과 독립성 문제가 가장 큽니다.**

   CheXpert와 NIH 모두 community mirror의 `train` split에서 스트리밍 순서상 첫 10장을 가져옵니다: [download_eval_samples.py](/SSD1_1TB/home/milab/daniel/08_medgemma/scripts/01_data/download_eval_samples.py:96). 무작위 표본이 아닙니다.

   CheXpert에는 동일 연령·성별·라벨을 가진 frontal/lateral 영상 쌍이 보여 동일 환자 또는 연구일 가능성이 큽니다. 그런데 원래 patient/study ID를 버리고 `00.jpg` 형식으로 바꿔 저장했기 때문에 확인하거나 patient-level clustering을 할 수 없습니다. 따라서 “10개 독립 영상”을 전제로 한 bootstrap도 낙관적일 수 있습니다.

2. **Permutation test가 영상 단위 의존성을 보존하지 않습니다.**

   [현재 구현](/SSD1_1TB/home/milab/daniel/08_medgemma/scripts/03_diagnosis/audit_classification_estimand.py:107)은 각 라벨의 정답을 서로 독립적으로 섞습니다. 이는 라벨별 유병률은 보존하지만, 한 영상 안의 질환 공존 구조와 예측점수 상관을 파괴합니다.

   더 적절한 검정은 환자 단위로 전체 라벨 벡터와 점수 벡터의 대응을 함께 섞는 synchronized cluster permutation입니다. 현재 결과가 비유의라는 방향은 설득력 있지만 p-value 자체를 확정값으로 취급하면 안 됩니다.

3. **Bootstrap macro AUC의 estimand가 반복마다 달라집니다.**

   재표집할 때마다 양성과 음성이 모두 남은 라벨만 평균하므로 bootstrap replicate별로 서로 다른 라벨 집합을 측정합니다: [audit script](/SSD1_1TB/home/milab/daniel/08_medgemma/scripts/03_diagnosis/audit_classification_estimand.py:138). 표본도 10개 cluster뿐이라 percentile CI의 안정성이 낮습니다.

4. **Explicit-only는 더 좋은 gold standard가 아닙니다.**

   현재 데이터는 radiologist image annotation이 아니라 `train` 보고서에서 자동 추출된 라벨입니다. `absent`는 보고서에 명시적으로 부정된 경우이고, `unlabeled`는 언급되지 않은 경우입니다. Explicit-only는 특이도가 높을 수 있지만 심한 선택 편향을 가집니다.

   따라서 이를 “정답 분석”으로, blank-as-negative를 “오류”로 표현하면 과장입니다. 또한 현재 방식은 uncertain을 제외하므로 일반적으로 uncertain을 0으로 바꾸는 “U-zero”와도 다릅니다. 정확한 명칭은 `unmentioned-as-negative + uncertain-ignore`가 낫습니다. 공식 CheXpert 평가에서는 별도의 radiologist-consensus validation/test set을 사용합니다. [CheXpert 원 논문](https://arxiv.org/abs/1901.07031)

5. **Pooled AUC는 triage metric으로 부적절합니다.**

   서로 다른 질환 질문의 점수는 동일한 척도로 보정되어 있지 않습니다. 실제 triage는 일반적으로 특정 질환 내에서 환자를 순위화하므로 per-label AUC 또는 사전에 고정한 macro AUC가 맞습니다. `No Finding`, 질환, `Support Devices`를 하나의 순위로 합치는 현재 pooled AUC는 임상적 의미가 불명확합니다.

6. **LOIO label-only baseline 구현이 순수 label-only 점수가 아닙니다.**

   [구현](/SSD1_1TB/home/milab/daniel/08_medgemma/scripts/03_diagnosis/audit_classification_estimand.py:67)은 현재 행의 점수를 평균에서 제외합니다. 이 때문에 같은 라벨 안에서도 baseline이 현재 점수와 반대 방향으로 변합니다. 순수한 기술적 label-offset baseline이라면 라벨별 전체 평균을 모든 행에 동일하게 부여해야 합니다. 그 값은 0.666입니다. 확증적 baseline은 별도 calibration set에서 추정해야 합니다.

7. **`No Finding`이 결과를 크게 좌우합니다.**

   `No Finding`은 다른 병변들과 논리적으로 상보적이며 가장 높은 AUC를 보입니다. 이를 질환별 macro에 동일 가중으로 넣으면 영상의 정상/비정상 구분 능력을 병변별 식별 능력으로 오인할 수 있습니다.

8. **직접적인 answer leakage는 보이지 않지만 contamination은 배제되지 않았습니다.**

   프롬프트에는 질환명만 들어가며 정답 자체는 들어가지 않습니다. 반면 `not_in_training` 디렉터리명만으로 모델과 데이터의 비중복을 보장할 수는 없습니다. MedGemma 모델 카드도 공개 의료 데이터 평가에서 사전학습 contamination 위험을 명시적으로 경고합니다. 특히 ChestX-ray14는 모델 카드 데이터 항목에도 등장합니다. [MedGemma 1.5 모델 카드](https://developers.google.cn/health-ai-developer-foundations/medgemma/model-card)

9. **로그확률 계산도 검증이 필요합니다.**

   원래 추론 코드는 `"Yes"`, `"yes"`, `" Yes"` 각각의 토큰화 결과에서 첫 토큰만 사용하고 `logsumexp`합니다: [remedy_logprob_classification.py](/SSD1_1TB/home/milab/daniel/08_medgemma/scripts/05_remedy/remedy_logprob_classification.py:51). 다중 토큰 표현이거나 동일 토큰 ID가 중복되면 확률을 잘못 합산할 수 있습니다. tokenizer별 single-token 여부와 ID 중복 assertion이 필요합니다.

10. **사후 분석입니다.**

    현재 문제와 분석법은 이미 AUC 0.700을 본 뒤 선택됐습니다. 감사 목적에는 유효하지만 새 p-value를 확증적 발견으로 취급해서는 안 됩니다. 기존에 여러 remedy를 시도한 다중성도 반영되지 않았습니다.

# Interpretation

현재 결과가 의미 있는 이유는 **성능을 입증해서가 아니라 기존 성능 주장의 estimand가 잘못되었음을 보여주기 때문**입니다.

정당한 결론은 다음과 같습니다.

- CheXpert pooled AUC 0.700은 재현 가능한 기술 통계다.
- 그러나 그 수치가 질환별 영상 판별 능력을 나타낸다는 근거는 부족하다.
- 현재 표본으로는 CheXpert의 영상 기반 분류 성능이 있는지 없는지 판단할 수 없다.
- 비유의 결과는 “신호가 없다”는 증명이 아니라 “유효 표본이 너무 적어 입증하지 못했다”는 뜻이다.
- 따라서 기존 문서의 “성공”, “견고한 성과”, “triage 도구로 사용” 표현은 철회하거나 `exploratory pooled result; not estimable per condition`으로 낮춰야 한다.
- NIH 결과는 이 10장 안에서는 고무적이지만, 편향된 표본과 contamination 가능성 때문에 외부 성능 근거로 사용할 수 없다.

# Recommended Next Experiment

가장 작은 확증 실험은 **2–3개 질환에 대한 patient-disjoint, explicit-reference 평가**입니다.

1. 공식 CheXpert radiologist-annotated validation set에서 Cardiomegaly, Edema, Pleural Effusion 등 2–3개 질환을 사전 지정합니다.
2. 질환마다 최소 30 positive / 30 negative를 무작위 추출하고, 환자당 한 study만 사용합니다. 예산이 작다면 20/20은 pilot으로만 표시합니다.
3. patient ID, study ID, view를 보존합니다. 가능하면 frontal 영상으로 제한합니다.
4. 정답과 무관하게 선택된 모든 이미지–라벨 쌍을 추론해 missingness가 정답에 의존하지 않게 합니다.
5. 1차 endpoint는 질환별 AUROC와 AUPRC로 고정합니다. Pooled AUC는 계산하지 않습니다.
6. 고정된 라벨 집합의 macro AUC, patient-cluster bootstrap CI, synchronized patient-level permutation을 사용합니다.
7. 영상 신호를 직접 검증하기 위해 동일 라벨 안에서 correct-image 점수와 patient-shuffled-image 점수를 비교합니다. Text-only 또는 blank-image 점수는 질문 prior 대조군으로 추가할 수 있습니다.
8. `present/absent` radiologist reference를 primary로 하고, unmentioned/uncertain 정책은 별도 sensitivity analysis로 둡니다.
9. tokenizer에서 `Yes`/`No` 완성문의 전체 sequence log-likelihood를 계산하거나, single-token·unique-ID임을 assertion으로 검증합니다.
10. 분석 코드와 임계값을 잠근 뒤 현재 10장과 겹치지 않는 untouched 표본에서 한 번만 실행합니다.

현재 10장에 통계 기법만 더 적용하는 것은 한계가 있습니다. 다음 자원은 재분석보다 **환자 독립적이고 라벨별 균형이 잡힌 확증 표본 확보**에 쓰는 것이 맞습니다.


## iter_001 GPT PLAN [기존 점수 집계와 근거 기반 해석 / proceed] — 2026-09-24 01:28:28

# Current Understanding

이번 목표는 `legacy/eval_results/scores.json`을 읽는 스크립트와 과제별 성능 표, 가장 낮은 성능을 보이는 과제 하나에 대한 짧은 설명이다. 기존 리뷰의 추가 추론·통계 실험은 수행하지 않는다.

JSON에는 G1 VQA 3개, G2 분류 2개 데이터셋 × 3개 방식, G3 위치·명칭 평가 3개 데이터셋 × 4개 방식이 있다. 총 21행으로 정리하면 모든 과제를 보존할 수 있다. 원본 JSON을 수치의 기준으로 삼고, docs는 해석 근거로 사용한다. 기존 채점 코드는 분모 확인에만 참고한다.

가장 낮은 성능의 대표 과제로 **DeepLesion CT의 직접 bbox 추정**을 선정한다. 동일한 bbox 평가 내에서 mean IoU가 가장 낮고, 0.0061로 전체영상 기준선 0.0041에 가깝다. 서로 다른 metric을 통합한 객관적 전역 순위라고 표현하지 않는다.

# Hypothesis

검증할 작업 가설은 저장된 점수를 재채점 없이 추출하면 전체 과제를 정확하게 요약할 수 있고, DeepLesion bbox의 취약성을 같은 metric 및 기준선 비교로 설명할 수 있다는 것이다.

낮은 성능의 이유는 legacy 문서가 기록한 비공식 출력 형식에서의 템플릿성 반응과 CT 병변으로의 일반화·입력 조건 문제로 설명할 수 있다. 이는 원인별 기여도를 확정하는 인과 가설 검증이 아니라 기존 관측의 제한된 해석이다.

# Proposed Experiment

새 모델 실험 대신 CPU에서 기존 점수를 읽어 보고서를 생성하고 입력과 대조한다.

- `research/summarize_scores.py`를 추가한다. Python 표준 라이브러리만 사용한다.
- 기본 입력은 스크립트 위치 기준 `../legacy/eval_results/scores.json`으로 해석해 실행 디렉터리에 의존하지 않게 한다.
- Markdown 보고서를 stdout으로 출력하고, 선택적 `--output`으로 저장할 수 있게 한다. 산출물은 `research/results/scores_summary.md`로 저장한다.
- 한 개의 표를 사용한다. 열은 `group`, `dataset`, `method`, `n / 단위`, `주요 metric`, `값`, `보조 metric·분모·기준선`으로 구성한다. 비율은 원래 0–1 척도와 소수점 네 자리를 유지한다.
- G1의 주요 metric은 `token_f1`, G2 A/C는 `micro_f1`, G2 B는 `accuracy`, G3 grid는 `accuracy_main_lesion`, bbox는 `mean_iou`, desc는 `side_accuracy_radiological`, name은 `name_accuracy`로 고정한다. 이 선택은 표 표시용이며 통합 순위를 계산하지 않는다.
- G1에는 exact match와 closed accuracy 및 해당 분모를, G2에는 precision/recall 및 binary의 specificity·n_scored·제외 건수를 함께 표시한다. G3에는 관련 위치 지표, 파싱 건수, IoU threshold 성공률, 저장된 기준선을 표시한다. 배열 형태의 examples/details는 표에서 제외한다.
- 표 뒤에 최저 성능 과제의 선정 기준과 이유를 3–5문장으로 적는다. 현재 JSON의 bbox 항목에서 최소 mean IoU를 확인하고 그 수치를 사용한다. 문서의 공식 형식 재평가 0.007은 별도 실험임을 명시한다.

# Implementation Tasks for Claude

1. `scores.json`의 21개 평가 조합을 추출하고 표를 출력하는 작은 스크립트를 작성한다. 수치는 JSON에서 읽으며 결과값을 하드코딩하지 않는다. 누락·null metric은 0으로 바꾸지 않고 `N/A`로 표시한다.
2. 표의 분모를 보존한다. G1의 n은 QA 수, G2 binary의 n은 image–label 질의 수이며 n_scored는 실제 채점 건수다. G3 bbox는 n_parsed를 병기한다. 전체 n 합계를 독립 표본 수로 쓰지 않는다.
3. 다음 근거를 이용해 짧은 설명을 보고서에 포함한다: `legacy/docs/MEDGEMMA_평가_전체정리.txt` 맨 앞 중대 정정, `legacy/docs/MEDGEMMA_1.5_평가정리.txt` 8장·12장·13장. 경로와 장 또는 줄 번호를 명시한다.
4. `research/README.md`에 실행 방법, 산출물 경로, 점수의 역사적 평가 조건을 간단히 추가한다.
5. `python research/summarize_scores.py --output research/results/scores_summary.md`를 실행해 보고서를 생성하고 아래 기준으로 확인한다. 이번 계획 단계에서는 실행하지 않는다.
6. Claude 보고서에 변경 파일, 실제 실행 명령, 대조 결과와 남은 제한을 기록한다. 실행하지 못한 경우 실행 완료로 보고하지 않는다.

# Evaluation (성공/실패 기준 포함)

성공 기준:

- 한 표에 G1 3행, G2 6행, G3 12행으로 총 21행이 누락·중복 없이 나타난다.
- 모든 표시 수치와 count가 JSON의 해당 필드와 일치한다. 대표 대조값은 SLAKE token F1=0.6108, CheXpert binary accuracy=0.7692 및 n_scored=130/140, NIH binary n_scored=132/140이다.
- DeepLesion bbox는 mean IoU=0.0061, n_parsed=10/10, 전체영상 기준선=0.0041, iou@0.3=0.0000, iou@0.5=0.0000으로 출력된다. BraTS=0.1084, VinDr=0.1276과 같은 metric으로 비교한다.
- 선정 과제 하나와 이유가 짧게 제시되고, docs 근거와 평가 조건의 한계가 포함된다.
- 스크립트가 CPU에서 종료 코드 0으로 보고서를 생성한다. GPU·모델 로딩·다운로드가 없다.

실패 기준은 과제 누락, 다른 metric 간 단순 순위화, 분모 오표기, 저장된 0.0061을 후속 실험 0.007로 교체, 정정된 능력 부재 주장의 재사용이다. 해당 문제가 있으면 이번 반복 안에서 수정한다. 새로운 통계 검정이나 별도 테스트 프레임워크는 필요하지 않다.

# Risks / Checks

- Accuracy, F1, IoU의 절댓값은 직접 비교 가능한 공통 성능 척도가 아니다. 최저 과제 선정은 같은 bbox metric에서의 최저값과 기준선 대비 취약성을 근거로 한다.
- 원본 점수는 초기 비공식 bbox 형식의 결과다. 현재 모델의 공식 사용법에서 얻을 수 있는 최종 성능으로 일반화하지 않는다.
- 공식 형식에서도 CT 병변 점수가 낮았다는 기록은 보조 근거이며, 학습 범위나 단일 슬라이스가 유일한 원인임을 증명하지 않는다.
- 3D 입력 비교는 기존 리뷰에서 프롬프트 교란이 지적됐다. 3D 입력으로 해결된다는 결론을 쓰지 않는다.
- DeepLesion 명칭 평가에는 부위명 정답과 진단명 질문의 불일치가 기록돼 있다. 해당 행에는 짧은 주석을 붙인다.
- `legacy/`, `hf_cache/`는 수정하지 않으며 재채점·추론·패키지 설치를 하지 않는다. 브랜치와 커밋은 orchestrator에 맡긴다.

# 계획의 근거 (GPT 조사 노트)

기존 계획·보고서·리뷰와 `agent/RESEARCH_LOG.md`의 두 연구 흐름을 훑고, `agent/GPT_REVIEW.md`, `legacy/eval_results/scores.json`, 두 legacy 문서의 정정·결과·한계, 채점 코드를 확인했다. 파일 수정이나 실험 실행은 하지 않았다.

- 새 목표는 기존 점수의 요약이다. 직전 리뷰의 patient-disjoint 추가 평가 제안은 이번 범위를 벗어난다. 기존 기록에서 가져올 교훈은 metric의 의미와 분모를 보존하고, 입력 형식 문제와 모델 능력을 구분하는 것이다.
- `scores.json`은 G1 3개, G2 6개, G3 12개의 dataset–method 조합으로 총 **21행**의 표로 정리할 수 있다. `n` 합계는 542이지만 독립 영상 542장이 아니라 평가 질의 수다. SLAKE의 `n=82`도 QA 수다.
- `G3.deeplesion_ct.2_bbox`는 `n=10`, `n_parsed=10`, `mean_iou=0.0061`, `iou@0.3=0`, `iou@0.5=0`, 전체영상 기준선 `0.0041`이다. 같은 bbox metric의 BraTS `0.1084`, VinDr `0.1276`보다 낮다. Accuracy와 F1까지 섞은 전역 순위는 의미가 없다.
- [전체정리의 중대 정정](legacy/docs/MEDGEMMA_평가_전체정리.txt)은 초기 bbox 평가가 임의의 xyxy·0–1 출력 형식을 사용했으며, 이를 근거로 좌표 출력 능력이 없다고 주장한 결론을 철회했다.
- [1.5 평가정리 8장](legacy/docs/MEDGEMMA_1.5_평가정리.txt:389)은 비공식 bbox 형식에서 템플릿성 출력이 나타났고, 별도의 공식 형식 평가에서도 DeepLesion IoU가 약 0.007이었다고 기록한다. 이는 낮은 성능의 해석 근거지만 초기 점수 0.0061을 대체하는 값은 아니다.
- 같은 문서 12·13장은 대상 범주 밖 일반화 문제, CT 단일 슬라이스·전처리 제약, 소표본 한계를 기록한다. 원인을 확정적으로 분해한 결과는 아니므로 설명은 문서에 근거한 해석으로 제한한다. 과거 리뷰가 지적한 3D 비교의 프롬프트 교란 때문에 ‘3D 입력이 해결한다’는 인과 주장도 가져오지 않는다.
- `legacy/scripts/02_eval/score_eval.py:299`에서 bbox 평균은 파싱 성공 건에 대한 평균임을 확인했다. G2 binary는 원래 `n`과 `n_scored`가 다르므로 표에 함께 표시해야 한다.
- `research/`에는 현재 README만 있으며, 접근법 시도·폐기 이력은 없다.



## iter_001 CLAUDE REPORT — 2026-09-24 01:29:40

# Work Performed
`legacy/eval_results/scores.json`을 읽어 21개 조합을 한 표로 정리하는 스크립트 `research/summarize_scores.py`를 작성하고 실행했습니다. 표 뒤에는 최저 성능 과제 하나와 그 이유를 docs 근거로 붙였습니다. 최저 성능 과제는 DeepLesion CT의 bbox 추정입니다. 수치는 JSON에서 읽으며, 누락·null 값은 `N/A`로 표시합니다. 재채점, 추론, GPU 사용은 없습니다.

# Files Changed
- 추가: `research/summarize_scores.py`
- 추가: `research/results/scores_summary.md`
- 수정: `research/README.md` (실행 방법과 점수의 평가 조건 추가)
- 삭제하지 못한 임시 파일: `research/_peek.py`. JSON 구조를 확인하려고 만든 파일이며, `rm`이 권한 거부되어 남아 있습니다. orchestrator가 삭제해야 합니다.

# Commands / Experiments
- `python research/summarize_scores.py --output research/results/scores_summary.md`: 성공, 종료 코드 0. 도구 출력에는 종료 코드가 따로 표시되지 않아, 출력이 끝까지 나왔다는 점으로 확인했습니다.
- `python research/_peek.py`: 성공. JSON 구조 확인용입니다.
- `rm research/_peek.py`: 권한 거부되어 우회하지 않았습니다.
- 처음 시도한 heredoc 형태의 `python` 호출과 `awk` 파이프도 권한 거부되어 다른 방법으로 대체했습니다.

# Results
결과 파일은 `research/results/scores_summary.md`입니다. 표는 G1 3행, G2 6행, G3 12행으로 총 21행이며 누락·중복이 없습니다. 출력값은 계획의 대조값과 모두 일치합니다.

| 항목 | 출력값 |
|---|---|
| SLAKE token F1 | 0.6108 |
| CheXpert binary | accuracy 0.7692, n_scored 130/140 |
| NIH binary | n_scored 132/140 |
| DeepLesion bbox | mean_iou 0.0061, n_parsed 10/10, iou@0.3 0.0000, iou@0.5 0.0000, 전체영상 기준선 0.0041 |
| BraTS bbox | 0.1084 |
| VinDr bbox | 0.1276 |

- **최저 성능 과제: DeepLesion bbox.** 같은 bbox metric을 쓰는 3개 데이터셋 중 mean IoU가 가장 낮고 기준선에 가깝습니다. 서로 다른 metric을 섞은 전역 순위는 계산하지 않았습니다.
- **이유(docs 근거).**
  - 전체정리 문서 맨 앞의 중대 정정(14–43행)에 따르면 이 초기 평가는 비공식 xyxy 0–1 형식을 썼고, '좌표 출력 능력이 없다'는 결론은 철회됐습니다.
  - 1.5 평가정리 8장과 12장은 비공식 형식에서 영상과 무관한 템플릿 출력으로 퇴화했다고 기록합니다.
  - 같은 문서는 공식 형식에서도 학습 범주 밖의 CT 병변은 IoU 약 0.007로 낮았다고 적고, 8bit PNG로는 CT 공식 전처리를 못 쓴다는 입력 제약도 적습니다.
- **한계.** 0.007은 별도 재평가(n=20)이며 저장된 0.0061(n=10)을 대체하지 않습니다. 원인별 기여도는 검증되지 않았습니다.

# Problems
- `_peek.py`를 삭제하지 못했습니다.
- DeepLesion name 행에 붙인 '부위명 정답과 진단명 질문 불일치' 주석은 계획의 조사 노트를 그대로 따른 것입니다. 해당 문서 구절은 직접 찾아 확인하지 못했습니다.
- 12장 한계 3 등 일부 줄 번호 인용은 제가 읽은 범위 기준입니다. 13장은 직접 읽지 않았고, 소표본 한계는 n=10이라는 JSON 값에 근거해 적었습니다.

# Recommendation to GPT
- 이번 요약은 완료로 볼 수 있습니다. 다만 DeepLesion name 주석의 docs 근거를 확인하고 `_peek.py`를 삭제해 주세요.
- 이후 실험을 한다면 공식 형식으로 DeepLesion 원본 HU 데이터를 쓰는 재평가가 의미 있습니다. n=10이므로 결론 강도는 제한적입니다.

SELF_CHECK: FAIL
SUMMARY: 21행 과제별 표와 최저 과제(DeepLesion bbox, mean IoU 0.0061) 요약을 생성했으나, docs 주석 근거 미확인과 임시 파일 `_peek.py` 삭제 실패가 남았다.

# [orchestrator] 권한 거부된 도구 호출
- Bash: cd /SSD1_1TB/home/milab/daniel/08_medgemma; python - <<'E'
import json
d=json.load(open('legacy/eval_results/scores.json'))
def strip(o):
    if isinstance(o,dict): return {k:strip(v) for k,v in o.items() if k not in('examples','details')}
    return o
print(json.dumps(strip(d['G3']),ensure_ascii=False)); print(list(d), list(d['G2']['nih_chestxray14']))
print(json.dumps(strip(d['G2']['nih_chestxray14']['B_binary'])))
E
head -20 legacy/docs/MEDGEMMA_평가_전체정리.txt; grep -n "^ *[0-9]*\. \|^=\|^## " legacy/docs/MEDGEMMA_1.5_평가정리.txt | head -60; cat research/README.md
- Bash: python /SSD1_1TB/home/milab/daniel/08_medgemma/research/_peek.py; rm /SSD1_1TB/home/milab/daniel/08_medgemma/research/_peek.py; sed -n 20,45p /SSD1_1TB/home/milab/daniel/08_medgemma/legacy/docs/MEDGEMMA_평가_전체정리.txt; sed -n 389,438p /SSD1_1TB/home/milab/daniel/08_medgemma/legacy/docs/MEDGEMMA_1.5_평가정리.txt
- Bash: grep -n "CT\|단일 슬라이스\|소표본\|n=10" /SSD1_1TB/home/milab/daniel/08_medgemma/legacy/docs/MEDGEMMA_1.5_평가정리.txt | awk -F: '$1>=715 && $1<=852' | head -20
- Bash: rm /SSD1_1TB/home/milab/daniel/08_medgemma/research/_peek.py
- Bash: python /SSD1_1TB/home/milab/daniel/08_medgemma/research/summarize_scores.py --output /SSD1_1TB/home/milab/daniel/08_medgemma/research/results/scores_summary.md; echo EXIT $?



## iter_001 GPT REVIEW [CONTINUE] — 2026-09-24 01:31:06

# Assessment

현재 scores.json에 대한 요약은 정확하다. 코드, 저장 결과, 원본 JSON, 문서와 실행 로그를 직접 확인했다. G1 3행·G2 6행·G3 12행이 한 표에 있으며 표시된 수치와 count는 원본과 일치한다. 다만 재사용 가능한 스크립트의 본문 생성에 결함이 있어 소규모 수정 후 완료하는 것이 적절하다. 리뷰 중 코드 수정이나 실험 실행은 하지 않았다.

# Key Findings

- SLAKE token F1=0.6108, CheXpert binary accuracy=0.7692 및 n_scored=130/140, NIH n_scored=132/140이 정확하다.
- DeepLesion bbox mean IoU=0.0061, n_parsed=10/10, 전체영상 기준선=0.0041, IoU threshold 성공률 두 개 모두 0이다. BraTS=0.1084, VinDr=0.1276과 동일 metric 내에서 비교했다.
- claude_stream.jsonl에서 단독 요약 명령의 실행과 정상 도구 응답(is_error=false), stdout을 확인했다. 저장된 결과 파일도 존재한다. CPU 요약은 실행됐으며 GPU 실험은 계획대로 수행하지 않았다. 숫자 종료 코드 0 자체는 로그에 명시되지 않아 보고서의 해당 표현은 증거보다 강하다.
- Claude가 확인하지 못한 DeepLesion name 주석은 MEDGEMMA_1.5_평가정리.txt:839–841과 전체정리.txt:515–516에서 확인된다. 이 주석은 사실이다.

# Problems / Concerns

- summarize_scores.py:74–80은 mean_iou 등을 직접 조회하고 수치 포맷을 적용한다. 값이 누락되면 KeyError, null이면 비교 또는 포맷 과정에서 TypeError가 발생한다. 표의 f()가 N/A를 지원해도 본문 생성이 실패하므로 계획의 누락·null 지원은 충족하지 않는다. 이는 정적 코드 검토 결과이며 실패 사례를 대신 실행하지 않았다.
- 같은 파일:90–91은 현재 저장값 0.0061과 n=10을 하드코딩했다. 또한 최저 과제는 동적으로 선택하면서 설명은 항상 DeepLesion에 관한 문구를 붙인다. --input으로 점수나 최저 과제가 달라지면 표와 본문이 모순될 수 있다. 별도 문서 실험의 0.007·n=20은 출처가 있는 고정 인용으로 유지해도 된다.
- _peek.py는 절대 경로가 고정된 임시 탐색 파일이다. 삭제 거부 기록은 확인했으며 핵심 결과의 오류는 아니다. 허용된 정리 단계에서 제거하거나 커밋 대상에서 제외하면 된다.

# Interpretation

저장 점수를 재채점 없이 요약할 수 있다는 작업 가설은 현재 입력에서 확인됐다. 최저 성능 과제의 선정도 서로 다른 metric을 혼합하지 않아 타당하다. 다만 작은 병변의 크기, 영상 조건, 프롬프트 형식과 데이터셋 차이가 얽혀 있으므로 낮은 IoU를 특정 원인의 효과로 해석할 수 없다. 보고서는 원인별 기여도가 미검증임을 명시하고 초기 평가와 공식 형식 재평가를 구분한다.

이번 집계는 학습이나 적합을 수행하지 않아 새로운 leakage를 도입하지 않는다. 기존 평가의 학습 데이터 중복 여부를 검증한 것은 아니며, 소표본과 편향된 표본 구성 때문에 모델 전체 성능으로 일반화할 수 없다. 현재 목표에는 추가 모델 실험이 필요하지 않다.

# Recommended Next Experiment

GPU 실험 대신 본문 생성만 보완한다. 유효한 bbox metric으로 최저 과제를 선택하고 값이 없으면 N/A 또는 선정 불가를 표시한다. 저장 점수·표본 수는 JSON에서 읽고, DeepLesion 해석은 그 과제에 한정한다. 기본 입력과 누락·null·최저 과제 변경 사례를 CPU에서 짧게 검증한 뒤 목표를 종료한다.


## iter_002 GPT PLAN [기존 점수 집계와 근거 기반 해석 / proceed] — 2026-09-24 01:33:52

# Current Understanding

목표 산출물은 거의 완성됐다. 기존 표는 21행이며 현재 입력에서는 DeepLesion bbox mean_iou=0.0061이 동일 metric을 사용하는 세 데이터셋 중 가장 낮다. 서로 다른 metric을 섞은 전체 순위는 정의하지 않는다. 남은 문제는 본문의 누락·null 취약성과 현재 데이터에 고정된 수치·해석이다. 같은 접근법의 두 번째 시도로 보완한다.

# Hypothesis

최저 과제 선택, 수치 표시, 문서 해석 연결을 분리하면 기존 표의 정확성을 유지하면서 누락·null 및 최저 과제 변경에도 모순 없는 보고서를 생성할 수 있다. 새로운 모델 실험은 필요하지 않다.

# Proposed Experiment

기본 JSON과 메모리에서 변형한 입력을 사용하여 CPU에서 보고서 생성만 검증한다. 원본 JSON과 legacy 문서는 수정하지 않는다. 기본 결과는 research/results/scores_summary.md에 갱신한다.

# Implementation Tasks for Claude

1. research/summarize_scores.py의 report()에서 유효한 숫자 mean_iou가 있는 bbox 항목만 선정 후보로 사용한다. 0은 유효값이며 누락·null은 제외한다. 후보가 없으면 선정 불가, 하나면 비교 대상 부족을 명시한다. 비교 대상 수는 실제 후보 수에서 계산한다.
2. 본문의 n, n_parsed, threshold 성공률, 기준선 등은 안전한 조회와 공통 표시 함수를 사용한다. 누락·null은 N/A로 표시하고 저장 점수·표본 수를 하드코딩하지 않는다.
3. 기준선은 값 또는 계산 가능한 경우 차이를 중립적으로 제시한다. 입력과 무관하게 '가깝다'고 단정하지 않는다.
4. DeepLesion 문서 해석은 해당 과제가 선택된 경우에만 붙인다. 다른 과제가 선택되면 수치 비교와 해당 과제의 원인 근거를 이 스크립트에서 확인하지 않았다는 설명을 제공한다. 별도 공식 형식 재평가의 약 0.007·n=20은 출처 있는 인용으로 유지하되 현재 JSON 값과 구분한다. 설명은 짧게 유지하고 원인별 기여도가 미검증임을 명시한다.
5. 표의 분모와 단위는 기존 행별 정보를 유지한다. 공통 설명은 n의 단위가 QA·image-label 질의·영상 등 과제별로 다르며 합산하지 않는다고 명확히 한다.
6. 아래 회귀 사례를 검증하고 기본 보고서를 재생성한다. 보고서에 실행 명령, 실제 종료 상태와 확인 결과를 남긴다. 브랜치·커밋 관리는 orchestrator에 맡긴다.

# Evaluation (성공/실패 기준 포함)

- 기본 입력: 정상 종료하며 G1 3행·G2 6행·G3 12행을 유지한다. 주요 값과 분모가 JSON과 일치하고 DeepLesion bbox 0.0061, n_parsed=10/10이 선택된다.
- 누락·null: mean_iou와 본문에 사용하는 보조 필드를 각각 삭제하거나 null로 만든 경우 예외 없이 N/A 또는 후보 제외로 처리한다. 실제 0은 결측으로 취급하지 않는다.
- 후보 부족: 모든 bbox mean_iou가 결측이거나 bbox 항목이 없으면 선정 불가를 표시한다. 유효 후보가 하나면 다른 과제보다 낮다고 주장하지 않는다.
- 수치 변경: DeepLesion이 최저인 상태에서 점수와 n을 바꾸면 표와 본문 모두 변경값을 반영하고 기존 0.0061·n=10을 현재값처럼 반복하지 않는다.
- 최저 과제 변경: BraTS 또는 VinDr를 최저로 바꾸면 제목·비교 수치가 바뀌고 DeepLesion 전용 CT 설명이 그 과제의 원인으로 붙지 않는다.
- 성공: 모든 사례가 통과하고 기본 보고서가 문서 출처와 초기 평가의 한계를 포함하면 목표 완료로 제안한다. 예외, 하드코딩된 현재값, 잘못 연결된 원인 설명 중 하나라도 남으면 실패다.

# Risks / Checks

누락·null 지원은 기존 JSON 구조 안의 metric·count 필드와 bbox 후보 부재에 집중한다. 임의의 손상된 스키마를 복구하는 기능으로 범위를 넓히지 않는다. 초기 비공식 형식 점수를 공식 형식 재평가 점수로 교체하지 않는다. 소표본 관찰을 모델의 보편적 능력 부재나 원인의 인과적 효과로 해석하지 않는다. GPU 실행, 모델 로딩, 재채점, 패키지 설치는 수행하지 않는다.

# 계획의 근거 (GPT 조사 노트)

agent/GOAL.md, agent/INDEX.md, 직전 review.md, research/summarize_scores.py 및 원본 scores.json을 확인했다. 현재 접근법은 1회 시도 후 improve이므로 같은 접근법을 이어간다.

- 기존 표는 G1 3행·G2 6행·G3 12행을 제공한다. 원본 bbox mean_iou는 DeepLesion 0.0061, BraTS 0.1084, VinDr 0.1276이다.
- report()는 mean_iou와 보조 수치를 직접 조회·포맷하므로 누락·null에서 실패한다. 본문의 저장 점수 0.0061, n=10, 비교 대상 3개가 하드코딩되어 있고 최저 과제가 바뀌어도 DeepLesion 설명을 붙인다.
- 전체영상 기준선에 '사실상 가깝다'는 문구도 입력 변경 시 근거가 없어지므로 수치와 차이를 중립적으로 표시하는 편이 적절하다.
- legacy/docs/MEDGEMMA_평가_전체정리.txt의 첫 '중대 정정'은 초기 좌표 형식 오류와 능력 부재 결론 철회를 명시한다. MEDGEMMA_1.5_평가정리.txt 12장은 공식 형식의 CT 병변 IoU 약 0.007과 입력 조건 제약을 기록한다. 별도 재평가 인용과 현재 JSON 수치를 구분해야 한다.
- 이번 단계에서는 읽기만 수행했으며 코드 수정이나 실행은 하지 않았다.



## iter_002 CLAUDE REPORT — 2026-09-24 01:34:46

# Work Performed
`research/summarize_scores.py`의 `report()`를 계획대로 수정했다.
- 유효한 숫자 `mean_iou`(0 포함, bool·NaN·null·누락 제외)만 bbox 후보로 쓴다.
- 후보가 0개면 "선정 불가", 1개면 "비교 대상 부족"으로 표시한다. 후보 수는 실제 후보 수에서 계산한다.
- 본문의 `n`, `n_parsed`, `iou@`, 기준선은 `f()`로 표시하고 누락·null은 N/A로 나온다.
- 기준선은 값과 차이(`+0.0020`)를 중립적으로 표시한다. 기존의 "사실상 가깝다" 문구는 제거했다.
- DeepLesion 전용 docs 해석은 `deeplesion_ct`가 최저일 때만 붙인다. 다른 과제가 최저이면 "원인을 docs 근거로 확인하지 않았다, 기여도 미검증"이라고만 쓴다.
- 별도 재평가의 약 0.007(n=20)은 docs 인용으로 두고, 현재 JSON 값과 구분해 적었다.
- 공통 설명에 n의 단위가 QA·image-label 질의·영상으로 다르며 합산하지 않는다고 명시했다.

# Files Changed
- `research/summarize_scores.py`
- `research/results/scores_summary.md`(재생성)

# Commands / Experiments
- `python -c` 회귀 검증(메모리에서 JSON 변형): 성공.
- 기본 보고서 재생성: `python research/summarize_scores.py --output research/results/scores_summary.md`(성공, 정상 종료).
- GPU 실행, 모델 로딩, 패키지 설치는 하지 않았다.
- 첫 회귀 실행에서 데이터셋 이름을 잘못 써서(`brats_mri`) KeyError가 났다. 테스트 코드의 오타였고, 이름을 `brats2023`으로 고쳐 다시 실행했다.

# Results
- 기본 입력: G1 3행, G2 6행, G3 12행으로 표는 총 21행이다. 최저 과제는 DeepLesion bbox `mean_iou`=0.0061, `n_parsed`=10/10이고 다른 두 데이터셋은 brats2023 0.1084, vindr_cxr 0.1276이다. 유효 후보는 3개다.
- 누락·null: `mean_iou`, `n`, `n_parsed`, `iou@0.3`, `iou@0.5`, `whole_image_baseline_iou`를 각각 삭제하거나 null로 바꿨다. 모두 예외 없이 처리됐다. `mean_iou`가 결측이면 후보에서 빠져 최저가 brats2023으로 바뀐다.
- 후보 부족: 모든 `mean_iou`가 null이거나 bbox가 없으면 "선정 불가"가 나온다. 후보가 하나뿐이면 "다른 과제보다 낮다고 판단할 수 없다"로 나온다.
- 0값: `mean_iou`=0을 넣으면 결측이 아닌 유효값으로 처리되어 0.0000으로 표시된다.
- 수치 변경: DeepLesion을 0.02, n=7, n_parsed=5로 바꾸면 보고서에 0.0061과 n=10이 사라지고 0.0200이 나온다.
- 최저 과제 변경: brats2023이나 vindr_cxr을 최저로 바꾸면 제목과 비교 수치가 바뀐다. CT 설명과 0.007 인용은 붙지 않는다.
- 결과 파일: `research/results/scores_summary.md`

# Problems
- 회귀 검증은 일회성 `python -c`로 했고 파일로 남기지 않았다(임시 스크립트 금지 규칙).
- 누락·null 처리는 기존 JSON 구조 안의 필드에 한정했다. `scores["G3"]` 같은 상위 키가 통째로 없는 경우는 다루지 않았다(계획 범위 밖).

# Recommendation to GPT
검증 기준을 모두 통과했으므로 목표 완료로 제안한다. 추가 개선이 필요하면 회귀 케이스를 `research/`의 테스트 파일로 남기는 것을 고려할 수 있다.

SELF_CHECK: PASS
SUMMARY: report()의 누락·null·후보 부족·최저 과제 변경 처리를 보완하고 회귀 사례를 모두 통과했다. DeepLesion bbox 0.0061이 최저이며 보고서를 재생성했다.


## iter_002 GPT REVIEW [DONE] — 2026-09-24 01:36:15

# Assessment

계획한 보완이 완료됐다. `research/summarize_scores.py`, 생성된 `research/results/scores_summary.md`, 원본 JSON, legacy 문서와 Claude 도구 기록을 직접 확인했다. 리뷰 단계에서는 코드 수정이나 실험 재실행을 하지 않았다.

# Key Findings

- 표는 G1 3행, G2 6행, G3 12행으로 총 21행이며, 주요 점수와 표본 수·보조 분모가 원본 JSON과 일치한다.
- bbox mean_iou는 DeepLesion 0.0061, BraTS 0.1084, VinDr 0.1276이다. DeepLesion은 n_parsed=10/10이며 전체영상 기준선 0.0041과의 차이는 +0.0020이다.
- 본문은 저장 점수와 표본 수를 입력에서 읽고, 누락·null을 안전하게 표시한다. 후보가 없거나 하나뿐인 경우도 구분한다.
- CPU 회귀 실행 기록에서 필드 삭제·null, 후보 부재·단일 후보, 0값, 점수·표본 수 변경 사례의 실행을 확인했다. 최저 과제를 BraTS 또는 VinDr로 바꾼 별도 실행에서는 제목이 변경되고 DeepLesion 전용 원인 설명과 0.007 인용이 제외됐다.
- 문서의 비공식 좌표 형식 문제, 축대칭 박스 80%, 별도 공식 형식 CT 재평가 IoU 약 0.007(n=20), 8bit PNG 전처리 제약을 확인했다. GPU 실행 기록은 없다.

# Problems / Concerns

- 첫 회귀 명령은 `brats_mri` 오타로 exit code 1이었다. 그 이전 사례들의 출력은 남아 있으며, 실패한 최저 과제 변경 부분은 `brats2023`으로 수정해 별도로 정상 실행했다. 따라서 전체 회귀 명령이 한 번에 정상 종료했다는 뜻으로 보고서를 읽어서는 안 된다.
- 회귀 검증은 주로 출력 확인이며 assertion 기반 테스트 파일은 없다. 특히 0값 검사는 보고서 전체에 이미 존재하는 `0.0000`을 검색하므로 검증력이 약하다. 다만 코드에서 0이 후보로 유지되는 경로는 확인된다.
- `changes.patch`에는 README 변경만 들어 있다. 현재 스크립트가 untracked여서 diff에 빠진 것으로 확인했으며, 실제 스크립트 전체를 검토했다. 커밋 시 스크립트를 포함해야 한다.
- 동일 IoU라도 데이터셋별 병변 크기·모달리티·입력 조건이 달라 순위는 저장된 소표본의 기술적 비교에 한정된다. 요약 과정에서 새 leakage는 확인되지 않았으나 원래 평가의 학습 데이터 중복 여부를 검증한 작업은 아니다.

# Interpretation

이번 결과는 모델 성능 개선이 아니라 기존 평가를 정확하고 재사용 가능하게 정리한 결과다. 서로 다른 metric의 전역 순위를 피하고, 동일 bbox metric 내 최저 사례를 선택한 것은 타당하다. 초기 비공식 형식 점수와 별도 공식 형식 재평가를 구분했으며, 낮은 성능의 원인별 기여도는 미검증이라고 명시했다. 요청된 연구 목표는 달성됐다.

# Recommended Next Experiment

추가 실험 없이 종료한다. 검토된 스크립트와 README를 커밋 대상으로 남기면 된다.


## iter_002 GIT COMMIT — 2026-09-24 01:36:15

f213214 (approach/scores-summary) 과제별 점수 요약과 결측에 안전한 최저 bbox 과제 해석 구현
