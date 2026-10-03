# 요약

- **핵심 결과:** 원본 NIfTI에서 여섯 구간 답변 파일 저장까지 경계를 맞추자 HD-GLIO+OR의 비용 우위가 유지됐다. loading 포함 HD/U8 wall 합 비율은 0.601이다.
- **근거:** HD 12 volume 124.76초, U8 72구간 요청 207.59초다. 6개 block 비율은 0.585–0.613이고 모두 1 이하다. steady-state 비율도 0.615(0.585–0.638)로 같은 방향이다. E48 정확도 세 조건도 그대로 재현됐다.
- **미검증·주의:** 정보 조건이 다른 비교다(HD는 네 sequence 전체 volume, U8는 FLAIR 구간당 8장). 개발 자료 D6/E48만 썼고 독립 일반화, 임상 성능, 신규성은 검증하지 않았다. 소표본이라 비용 CI는 두지 않았다.
- **다음:** 사전 계획대로 현재 네 sequence 개발 조건의 전문 대안 채택 쪽(양성)으로 종료한다. VLM 구간 적응 투자는 보류하고 timing 탐색은 더 하지 않는다. 판정은 GPT 리뷰에 맡긴다.

# Work Performed

- 기존 `hdglio58_timing/pred/prep/u8` 코드를 읽어 결함을 확인했다. HD 입력이 이미 분리된 채널이었고, 추론이 segmentation 저장에서 끝났으며, U8 case timer가 답변 저장 전에 끝났다. 기존 파일은 수정하지 않고 새 `hdglio59_*` 파일을 만들었다.
- **HD 실행기 (`hdglio59_hd.py`):**
  - 경로는 원본 4D 읽기 → channel 분리·쓰기(매 실행 새 경로) → 공식 `predict_from_folder`(fold0, TTA) → pred 읽기 → FLAIR 비영 범위 기반 6구간 OR → 답변 저장이다.
  - GT는 읽지 않는다.
  - 모델 loading은 `load_model_and_checkpoint_files`를 감싸 sync 후 직접 계측했다. 계산 인자는 바꾸지 않았다.
- **U8 실행기 (`hdglio59_u8.py`):**
  - iter_056의 prompt, revision, caps, 렌더를 그대로 쓴다.
  - 종료 timer를 답변 파일 저장 후로 옮겼다.
- **측정과 검증 코드:**
  - `hdglio59_common.py`: 허용 GPU 매핑, 메모리 admission, digest 잠금, 기존 run 경로 거부, 완료 검증, GT 검사.
  - `hdglio59_timing.py`: lock / tech / blocks. 완료 pair는 재사용하고, 미완료 pair는 새 attempt로 전체를 재측정하며 실패 attempt를 보존한다.
  - `hdglio59_report.py`, `hdglio59_regress.py`, `test_hdglio59.py`.
- 동시성 탐색은 하지 않았다. 측정 장치마다 worker 1개를 썼다. 근거는 iter_058에서 측정한 2 GPU×1 worker 21.282초 대 2×2 worker 23.206초이고, paired timing이라 경합을 통제해야 했기 때문이다.

# Files Changed

- 신규 코드(모두 `research/`, 아직 미추적): `hdglio59_hd.py`, `hdglio59_u8.py`, `hdglio59_common.py`, `hdglio59_timing.py`, `hdglio59_report.py`, `hdglio59_regress.py`, `test_hdglio59.py`.
- 결과: `results/iter_059/`
  - `protocol.json`, `tests/fixtures.json`
  - `tech/`, `timing/` (`pair_*.json`, `attempt_*.json`, `cost_report.json`)
  - `regress/` (`report.json`, `regress.json`)
- 기존 코드와 과거 결과는 수정하지 않았다.

# Commands / Experiments

| 명령 | 결과 |
|---|---|
| `python test_hdglio59.py results/iter_059/tests/fixtures.json` | 성공, 26/26 |
| `python hdglio59_timing.py lock` | 성공 (exclusive). 코드 10개, checkpoint 6개 파일, 원본 영상 6개, iter_058 고정 산출물의 hash 잠금. |
| `python hdglio59_timing.py tech` | 성공 |
| `python hdglio59_timing.py blocks` | 성공. 6 pair 모두 complete, 실패 attempt 0. |
| `python hdglio59_report.py results/iter_059/timing/cost_report.json` | 성공 |
| `python hdglio59_regress.py results/iter_059/regress` | 성공, exit 0 |

- **fixture가 거부하는 항목:**
  - 허용 GPU 밖, `CUDA_VISIBLE_DEVICES` 미설정
  - 메모리 부족
  - 기존 run 경로 재사용
  - source, checkpoint, 요청 digest 불일치
  - 부분 출력, 누락·잉여·슬랩 수 오류
  - GT 중복 key, case/split 교환, 슬랩 누락
  - worker 실패 시 pair 중단과 새 attempt 경로 사용
  - 잠금 후 코드 변경
- **기술 검사 (tech, 첫 block):**
  - 새 channel 입력이 원본 4D 지정 channel과 voxel·affine·shape·유한값 모두 같다 (8/8).
  - HD pred foreground가 iter_058 pred와 voxel XOR 0이고, 12개 답변이 모두 같다.
  - U8 답변과 raw 출력이 iter_058 u8check와 같고 모두 EOS 종료다.
  - 외부 wall이 내부 event를 포함한다.
- **본측정 환경:**
  - 장치는 GPU 0/1에 block/order별로 번갈아 배정했고, CVD=0,1 안에서 논리·물리 index가 같다.
  - U8 peak reserved는 9312 MiB, HD는 1660 MiB다. 매 실행 전 admission(실제 점유 + peak + 2GiB)을 통과했다.
  - 모든 답변이 유효했고 U8의 비EOS는 0이다.

# Results

주 결과는 `results/iter_059/timing/cost_report.json`이다.

| 구분 | HD 합 | U8 합 | 비율 HD/U8 | block 범위 |
|---|---|---|---|---|
| loading 포함 (외부 subprocess wall) | 124.76초 | 207.59초 | 0.601 | 0.585–0.613 (6/6이 1 이하) |
| steady-state (같은 실행의 직접 event) | 84.07초 | 136.79초 | 0.615 | 0.585–0.638 (6/6이 1 이하) |

- 순서별 loading 포함 비율은 U8→HD 0.605, HD→U8 0.597로 방향이 같다.
- case당 wall은 HD 10.40초, U8 17.30초다.
- 단계 포함 효과: 같은 D6에서 누락 단계를 더하자 HD 2-case 실행이 약 16.4초에서 약 20.6초로 늘었다. 방향은 바뀌지 않았다.
- **정확도 회귀 (`regress/regress.json`):**
  - iter_058 입력·출력 hash가 모두 일치했다.
  - GT 중복 key와 case/split 오류는 D, E 모두 없었다.
  - 점추정과 bootstrap CI 5개가 iter_058과 동일하다.
  - BA는 U8 0.768639, HD 0.950457이다.
  - 차이는 0.181818, 95% CI [0.115776, 0.247666]이다.
  - sensitivity 차이는 0.0이다.
  - 세 조건(BA 차이 ≥0.05, CI 하한 >0, sens 차이 ≥−0.05)을 모두 충족한다.
- **정정값 (원자료로 계산해 기록, 과거 보고서는 미수정):**
  - FN은 13개이고 이 중 600 voxel 미만이 11개다.
  - 단일 worker D6 launch wall은 29.296초다.

# Goal Progress / Reused Assets

- **판정 (사전 정의 기준):** 정확도 세 조건과 loading 포함 비용 비율 ≤1이 충족됐고 block별 방향이 안정적이며 steady-state도 반대 결론이 아니다. 양성 분기에 해당한다. 네 sequence 개발 조건에서 전문 대안(HD-GLIO+OR)이 충분하다는 판정이며, VLM 구간 적응 투자는 이 과제 범위에서 보류한다.
- **새로 알게 된 것:** iter_058의 비용 blocker(누락 경계)는 이번 새 결과에서 해소됐다. 과거 review는 지우지 않았다.
- **재사용:**
  - 환경: `results/environments/hdglio58`. 코드·가중치: HD-GLIO d1a37c7 및 Zenodo v2 params (checkpoint hash 일치 확인).
  - 모듈: `hdglio58_eval.py`, `msd57_analysis.py`, `msd56_run.py`, `msd56_data.py`. `reuse_assets`는 비어 있었다.
  - 이들의 다른 미승인 reuse_issues는 해제하지 않았다. 사용한 경로의 검증은 위 fixture와 회귀로 갈음한다.
- **미검증:**
  - 독립 데이터 일반화, 임상 성능, 동일 정보·동일 annotation 조건 비교
  - HD-GLIO의 환자 단위 학습 중복(확인 불가)
  - 직접 SFT나 FLAIR-only 전문 모델과의 비교
  - 비용 CI(소표본이라 사전 계획대로 gate로 두지 않았다)

# Problems

- **현재 결론 무효 사유:** 없음.
- **참고:**
  - HD 실행기의 `msd56_data` 슬랩 정의는 FLAIR만 쓰고 GT를 읽지 않는다. 단, `cases.json`의 기존 슬랩 값을 assert로 대조한다.
  - `hdglio59_pred.py`류 기존 파일의 overwrite 문제는 새 경로에서 `FileExistsError`로 차단했다.
  - HD가 공식 기본 경로처럼 loading과 preprocessing을 겹치지 않는지는 확인했다. loading은 predict 호출 앞부분에서 직렬이라 계측 위치가 맞다.
  - `msd56_run`의 sanity, 재개 검사 같은 미해결 reuse 항목은 이번 경로에서 쓰지 않아 손대지 않았다.
- **추후 개선 (현 결론과 무관):** U8·HD 모두 fsync 없이 rename 기준으로 맞췄다. durable fsync 비용은 측정하지 않았다.

# Recommendation to GPT

- 양성 분기로 이 timing 탐색을 종료하고, 네 sequence 개발 조건의 전문 대안 채택 및 VLM 구간 적응 투자 보류를 리뷰에서 판정해 주기 바란다.
- 이 범위에서는 신규 기여나 VLM 우위를 주장하지 않는다.
- 다음은 새 MRI 질문이 사용 가치와 정보 이득으로 정당화될 때만 별도 계획으로 고려하는 것을 권고한다.

SELF_CHECK: PASS
SUMMARY: 원본 NIfTI→답변 저장 전체 경계로 D6를 재측정해 HD-GLIO+OR/U8 비용 비율 0.601(6개 block 모두 ≤1, steady-state 0.615)을 확인했고, E48 정확도 세 조건도 그대로 재현했다. 개발 자료 한정이며 독립 일반화와 임상 성능은 미검증이다.

# [orchestrator] 권한 거부된 도구 호출
- Bash: nvidia-smi --query-gpu=index,uuid,memory.used,memory.total --format=csv,noheader; echo $CUDA_VISIBLE_DEVICES; ls results/iter_058/hd results/iter_058/eval_E results/iter_058/tests; ls results/iter_059 2>&1 | head
- Bash: echo "CVD=$CUDA_VISIBLE_DEVICES"; sed -n 1,80p msd56_run.py | head -120; grep -n "^def " msd56_data.py msd56_run.py
- Bash: sed -n 131,200p results/environments/hdglio58/lib/python3*/site-packages/nnunet/inference/predict.py; sed -n 640,665p results/environments/hdglio58/lib/python3*/site-packages/nnunet/inference/predict.py
