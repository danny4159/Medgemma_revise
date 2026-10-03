# 요약

- **핵심 결과:** MSD Task01 뇌종양 FLAIR 6구간 판정(E48, 288구간)에서 MedGemma 1.5의 BA는 DENSE 0.776, U8 0.769, O8 0.753이었습니다. TEXT와 항상-PRESENT는 0.5입니다. 사전 규칙상 기본 신호는 "있음", Qwen 분기는 미발동, U8을 탐색 baseline으로 보존하는 쪽입니다.
- **근거:** 입력 구성, 요청 완전성, 독립 재계산(정답·BA·응답 해석)은 모두 통과했습니다. U8−DENSE BA 차이는 −0.008이고 case-cluster 95% CI는 [−0.057, 0.038]입니다.
- **미검증·주의:** "구간 위치만으로 푸는 prior"가 in-sample BA 0.719로 MedGemma 0.776에 가깝습니다. 신호의 상당 부분은 영상 병변 인식이 아니라 해부학적 위치일 수 있습니다. 이 결과는 임상 판독이나 방법 효과를 뜻하지 않습니다.
- **다음:** GPT 리뷰에서 위치-통제 평가가 필요한지 판단해야 합니다. 자세한 권고는 마지막 절에 있습니다.

# Work Performed

- **자료:** MSD 공식 archive를 MONAI 소스가 가리키는 URL로 받았습니다(7,608,266,240 bytes). md5 `240a19d7…872`가 기대값과 일치했습니다.
  - `dataset.json`에서 modality 0=FLAIR, labels 1/2/3=edema/non-enhancing/enhancing, license CC-BY-SA 4.0을 읽었습니다. 정답은 비배경 label의 합집합입니다.
  - 484개 training case의 image 파일 sha256 중복 그룹은 0입니다.
  - seed 56 고정 순서에서 FLAIR nonzero 범위만으로 적격(6구간 각 ≥8 slice)을 확인해 D6+E48을 뽑았습니다. mask는 사용하지 않았고 skip은 0건입니다.
  - 54개 case 모두 RAS, 240×240×155, 1mm입니다.
- **구간·조건:** 구간 324개 중 정답 present는 213개입니다. DENSE/U8/O8 PNG 7,456장을 만들었고, FLAIR volume 전체 min/max로 정규화했습니다.
- **시각 검사:** D6의 mask overlay와 U8 montage를 실제 이미지로 열어 확인했습니다. anterior가 위이고, mask는 고신호 병변과 맞았으며, slice 순서는 inferior→superior입니다. 좌우 방향은 영상과 mask에 동일 변환을 적용했다는 점만 확인했고, 좌우 자체는 독립 검증하지 않았습니다.
- **기술 검증:** 아래 검사는 모두 통과했습니다.
  - 독립 구성 대조: `input_ids`와 `pixel_values`가 일치했습니다(24/8/8장과 text).
  - image token 256/장, `<start_of_image>`·`<end_of_image>` 수, TEXT에 pixel 없음.
  - GT가 요청 행에 없음, 요청 행 내 slice 순서·단일 case 확인.
  - 강제 중단·재개: SIGKILL 후 torn row를 붙여 재개했습니다. 97/97 완료, 중복 0, 누락 0, D 본 실행 대비 token 불일치 0, 부분 행 별도 보존.
  - 독립 재계산 `msd56_verify.py`: mask에서 구간 정답 직접 재계산(불일치 0), PNG↔raw slice 36장 일치, 별도 파서 불일치 0, BA·paired 차이가 evaluator와 일치, 별도 seed bootstrap CI 일치.
- **실행:** D97 요청과 E766 요청을 GPU 0/1에 각 1 worker로 실행했습니다. E의 조건 행은 1152개입니다(U8/O8 공유와 TEXT 1회 재사용으로 고유 요청 766개).
- **Qwen3-VL:** 사전 분기 조건(DENSE·O8 모두 BA<0.65, 또는 둘 다 TEXT 대비 이득<0.05)이 E에서 충족되지 않아 실행하지 않았습니다. 실행 코드와 가중치만 준비했습니다.

# Files Changed

신규 코드는 모두 `research/` 루트의 `msd56_*.py`입니다. 기존 파일은 수정하지 않았습니다.

- **자료·검증:** `msd56_fetch.py`, `msd56_data.py`, `msd56_overlay.py`, `msd56_sanity.py`, `msd56_verify.py`.
- **실행·평가:** `msd56_run.py`, `msd56_resume_test.py`, `msd56_eval.py`, `msd56_breakdown.py`.
- **조건부 비교(미실행):** `msd56_qwen.py`.
- **결과:** `results/iter_056/` 아래 `source`, `data`, `gen`, `eval_D`, `eval_E`, `tests`.
- **Qwen 가중치:** `results/environments/qwen3vl_cache`(revision `ebb281ec…`, Apache-2.0).

# Commands / Experiments (실제 실행한 명령과 성공/실패)

- **다운로드:** `python msd56_fetch.py`를 세 번 이어서 실행했고 md5가 일치했습니다.
- **자료:** `python msd56_data.py select`, `extract`, `build`가 성공했습니다.
- **D 입력 검사:** `python msd56_sanity.py 0`을 두 번 실행했습니다.
  - 첫 번째는 검사 스크립트의 BOS 중복 버그로 `ids_equal=false`였습니다(결과 `sanity.json` 보존).
  - 수정 후 두 번째는 통과했습니다(`sanity_v2.json`).
- **D 실행:** `launch` 성공(wall 202s). 이어서 `verify`와 `msd56_eval.py --split D`를 실행했습니다.
- **재개 검사:** 첫 시도는 실패했습니다. torn row가 다른 worker 번호의 파일 읽기를 깨뜨렸습니다(`gen/D_resume_test` 보존).
  - 수정: 완전한 행만 읽도록 `read_jsonl`을 고쳤습니다.
  - 두 번째 시도(`resume_test2.json`)는 성공했습니다.
- **E 실행:** 코드 수정 후 `protocol_E`로 재잠금해 `launch`를 실행했고 성공했습니다(wall 1,145s). 이어서 `verify`, `msd56_eval.py --split E`, `msd56_verify.py --split E`, `msd56_breakdown.py`를 실행했습니다.
- **프로토콜 3종:**
  - D 본 실행은 v1 코드로 실행했고 사본을 `source/msd56_run_v1_used_for_D_main.py`에 보존했습니다. 이후 수정으로 `protocol_D.json`은 현재 코드와 digest가 일치하지 않습니다.
  - `protocol_D_v2`는 재개 검사에 사용했습니다.
  - `protocol_E`는 현재 코드와 일치합니다.
- **처리량 구성 비교:**
  - GPU당 2 worker는 시도하지 않았습니다. 실측 점유가 worker당 약 14–15.8GB(nvidia-smi 표본)이고, 2개면 24GB를 넘기 때문입니다.
  - batch2는 시도하지 않았습니다. E 전체가 19분이라 비교 비용이 절약보다 컸습니다.
  - 따라서 GPU별 1 worker를 유지했습니다.
- **시도하지 못한 것:** MedGemma 모델 카드는 gated(401)여서 공식 다중 영상 예제를 직접 확인하지 못했습니다. 표준 `apply_chat_template` 경로와 수동 processor 경로의 일치만 확인했습니다. 영상 앞에 "SLICE k" 텍스트를 붙이는 형식은 확인하지 못했고 사용하지 않았습니다.

# Results (수치와 결과 파일 경로)

E48, 구간 288개(양성 189, 음성 99). 모든 생성이 EOS로 종료했고 invalid는 0, 2048 재시도는 0건입니다.

| 조건 | sens | spec | BA | BA 95% CI (case-cluster) |
|---|---|---|---|---|
| DENSE | 0.937 | 0.616 | 0.776 | [0.732, 0.822] |
| U8 | 0.931 | 0.606 | 0.769 | [0.706, 0.828] |
| O8 | 0.899 | 0.606 | 0.753 | [0.696, 0.808] |
| TEXT / 항상-PRESENT | 1.0 | 0.0 | 0.5 | — |

- **paired BA 차이 (95% CI):**
  - DENSE−TEXT +0.276 [0.232, 0.322]
  - U8−DENSE −0.008 [−0.057, 0.038]
  - O8−DENSE −0.024 [−0.072, 0.023]
  - 차이가 나타난 사건은 U8−DENSE 22개 case, O8−DENSE 25개 case에 분포합니다.
- **사전 규칙 판정:**
  - 기본 신호 true: DENSE와 O8 모두 BA≥0.70, sens·spec≥0.60, TEXT 대비 BA≥0.10.
  - 중요한 잔여 차이 false: 조건 간 최대 BA 격차가 0.024로 <0.10.
  - U8가 DENSE의 0.05 이내이고 runtime 비율 0.371(≤0.5)이어서 "uniform baseline 보존" 조건을 충족했습니다.
  - Qwen 분기는 미발동입니다.
- **사후 탐색(`eval_E/breakdown.json`, 판정에 사용하지 않음):**
  - 구간 위치별 prevalence가 크게 다릅니다(slab 0 양성 3/48, slab 3 양성 48/48).
  - 위치만 쓰는 in-sample 상한 BA는 0.719입니다. 이는 E 자체에서 맞춘 값이어서 실제 baseline이 아닙니다.
  - DENSE의 spec은 대부분 최하단 구간에서 나옵니다(slab 0에서 38/45, 최상단 slab 5에서는 3/22). U8은 slab 5에서 12/22입니다.
  - 양성 병변 voxel 하위 25%(≤5,399)에서 sens는 DENSE 37/48, U8 38/48, O8 31/48입니다.
  - 양성 구간 중 ≤10 voxel은 2개뿐이어서, 이 정도 극소 annotation이 전체 결과를 좌우하지는 않습니다.
  - DENSE에서 U8이 놓친 양성 5건 중 selection이 annotation을 전혀 보지 못한 경우는 0건입니다.
- **비용:**
  - 구간당 평균 generation runtime: DENSE 3.60s(평균 23.0장, 6,034 input token), U8/O8 1.33s(8장, 2,139 token), TEXT 0.19s.
  - E 고유 요청 766개의 runtime 합은 1,666s입니다.
  - 최대 메모리: allocated 10.7GB, reserved 15.1GB.
  - 이는 generation만의 비용입니다. 자료 준비와 PNG 렌더링은 포함하지 않았습니다.
- **파일:**
  - `results/iter_056/eval_E/report.json`, `per_slab.json`, `verify.json`, `breakdown.json`
  - `eval_D/report.json`, `verify.json`
  - `gen/E`, `gen/D`
  - `tests/sanity_v2.json`, `resume_test2.json`
  - `data/D6_overlay.png`, `U8_montage_BRATS_199_slabs0_3_5.png`

# Goal Progress / Reused Assets (목표 진전·미검증 범위, 재사용 출처·검증)

- **목표 진전:**
  - 선택한 과제: MSD 뇌종양 FLAIR 구간의 annotation 존재 판단. 정답은 공개 mask의 합집합입니다.
  - 기본 능력: MedGemma는 이 과제에서 TEXT보다 높은 BA를 보였습니다(+0.28). 입력 손실은 uniform 8장으로는 DENSE 대비 관찰되지 않았습니다(−0.008).
  - 남은 관찰 하나: 정확도의 상당 부분을 구간의 해부학적 위치가 설명할 가능성이 큽니다. 다음 비교가 정할 결정은 위치를 통제해도 영상 신호가 남는지입니다.
- **미검증:**
  - case와 환자의 일대일 여부는 확인하지 못했습니다. BraTS의 원 출처 기준은 공식 설명에서 확인하지 못했고, 분석 단위는 case(cluster)입니다.
  - 독립 환자 일반화는 확인하지 못했습니다. E는 개발 자료입니다.
  - 전문 segmentation+OR와 직접 SFT 대비 비교는 실행하지 않았습니다.
  - 공개 자료의 사전학습 노출 가능성은 배제하지 못했습니다.
  - Qwen 대조는 미실행입니다. `msd56_qwen.py`는 컴파일만 확인했고 모델 로드·`subset`·`lock`·`worker`는 실행하지 않았습니다.
- **재사용:**
  - `reuse_assets`는 없었습니다. 작업 트리가 계획이 가정한 커밋(1d26362)이 아니라 68117cf였고 `pg43_run.py`와 `rsna_diag/generate.py`는 현재 트리에 없었습니다. 해당 blob은 `git show 1d26362:<path>`로 읽어 모델 로딩 패턴만 참고했습니다.
  - 실행기는 자체 구현했고 `pg43_run`·`rsna_diag`는 import하지 않았습니다. 그 모듈들의 승인 상태와 무관합니다.

# Problems (현재 결론 무효 / 재사용 전 수정 / 추후 개선을 구분)

- **현재 결론 무효: 없음.** 아래 두 버그는 발견 즉시 수정했고 증거 파일을 보존했습니다.
  - 검사 스크립트의 BOS 중복.
  - 재개 시 torn row 읽기 오류(재개 검사 중 발견, 수정 후 재검증).
- **해석상 주의:**
  - 위치 confound가 있습니다(위 사후 탐색).
  - 구간 정답이 present인데 annotation이 아주 작은 경우(최소 7 voxel)를 제외하지 않았습니다.
  - E48은 개발 자료이며 CI는 case-cluster입니다. 사전 규칙의 문턱은 확증 기준이 아닙니다.
- **재사용 전 수정:**
  - `msd56_run.py`의 `verify_protocol`은 코드 digest를 잠그므로, 코드가 바뀌면 이전 protocol은 검증할 수 없습니다.
  - D 본 실행 protocol은 현재 코드와 맞지 않습니다. 결과 자체는 `verify`가 아니라 독립 재계산으로 검증했습니다.
  - `launch`는 worker 종료 코드와 점유 표본을 기록하지만, 한 worker가 실패했을 때의 attempt별 비용 분리는 구현하지 않았습니다.
- **추후 개선:** 공식 모델 카드의 다중 영상 예제 대조(gated, 접근 필요), 위치 통제용 층화 평가.

# Recommendation to GPT

- **권고: 진단으로 계속하되 위치 통제를 먼저 한다.**
  - 사전 규칙상 기본 신호는 있고 U8로 충분해 복잡한 표집 방법 투자는 우선하지 않습니다.
  - 다만 위치-only prior(in-sample BA 0.719)와 MedGemma(0.776)의 차이가 작아 "영상 신호 있음"으로 확정하기엔 이릅니다.
- **결정을 바꿀 최소 비교(새 계획 필요):** 위치(slab index) 층화 BA 또는 같은 위치의 양성/음성 쌍만으로 DENSE/U8을 평가합니다. 기존 E 출력의 재분석으로 일부 답할 수 있어 비용이 작습니다.
- **분기:**
  - 위치 통제 후 신호가 남으면: 전문 segmentation+OR 대조를 포함한 method pilot을 검토합니다.
  - 신호가 사라지면: 이 FLAIR 구간 판단 과제의 VLM 투자를 보류하고 다른 MRI 과제로 전환합니다. MRI 전체를 기각하는 것은 아닙니다.
- **Qwen:** 지금은 불필요합니다. 필요해지면 `msd56_qwen.py`와 이미 받은 가중치를 쓰되, 먼저 D에서 로드·tensor 검증을 해야 합니다.

SELF_CHECK: FAIL
SUMMARY: MSD 뇌종양 FLAIR 구간 판정 E48에서 MedGemma BA는 DENSE 0.776, U8 0.769, O8 0.753으로 TEXT 0.5보다 높았고 U8≈DENSE이지만, 구간 위치만으로도 in-sample BA 0.719가 나와 영상 신호를 위치와 분리해 확인하는 추가 비교가 필요하다. 공식 모델 카드 대조는 접근 제한으로, Qwen 코드는 미실행으로 FAIL.

# [orchestrator] 권한 거부된 도구 호출
- Bash: git ls-tree -r --name-only 1d26362 -- pg43_run.py pg39_spec.py rsna_diag
- Bash: git ls-tree -r --name-only 1d26362
- Bash: curl -q --fail --silent --show-error --location --proto =https --proto-redir =https -- https://raw.githubusercontent.com/Project-MONAI/MONAI/dev/monai/apps/datasets.py
- Bash: CUDA_VISIBLE_DEVICES=0 python msd56_sanity.py 2>&1 | tail -30
- Bash: top -b -n1 -o %CPU
