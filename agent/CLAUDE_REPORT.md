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