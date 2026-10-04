# 요약

- **핵심 결과:** 두 모델 모두 E12 확대 기준을 통과하지 못했다. 사전 규칙대로 E 전체(42명·289 IVD)는 실행하지 않았다. 결정은 "기본 신호 부족, 현재 frozen Modic 경로 종료"이고, 원인은 미확정이다.
- **근거:** E12는 12명·81 IVD(0=53, II=28, I/III 없음)다. BA02(0/II 두 class의 평균 recall)는 MedGemma J 0.094, S1 0.000, S2 0.038이고 Qwen은 S1·S2·J·LF·R 모두 0.5다. 비교군은 text-only(MedGemma 0.434, Qwen 0.0)와 위치 prior 0.5다.
- **미검증·주의:** MedGemma의 단일 sequence 입력에서는 첫 token이 후보 밖 "Based"인 경우가 많았다(D 기준 단일 sequence 입력의 약 65–69%). Qwen은 항상 A(Modic 0)를 예측했다. 즉 인터페이스·calibration 문제와 영상 인식 부족이 분리되지 않았다. 후보 확률 p(C)(II 후보 확률)의 행 단위 AUROC는 0.56–0.77이라 순위 신호가 일부 있어 보인다. 이는 사후 탐색이고 환자 cluster·위치 교란을 통제하지 않았다.
- **다음:** 적응이나 prompt 변경은 자동으로 시작하지 않는다. GPT가 후보 확률 순위 신호의 투자 가치를 검토한다.

# Work Performed

- 반입 모듈(`mi19_mha`, `mi19_render`, geometry, `m65_run`, `msd56_run`)의 사용 경로를 검증하고 SPIDER Modic 과제용 모듈을 새로 작성했다.
  - `sp67_data.py`: SimpleITK 기준 canonical 기하, IVD crop, sagittal stack 렌더.
  - `sp67_audit.py`, `sp67_render.py`: D/E 자료 연결 audit과 렌더.
  - `sp67_run.py`: 후보 점수 runner, protocol 잠금, worker, launcher.
  - `sp67_eval.py`, `sp67_select.py`, `sp67_verify.py`: 평가, baseline 선택, 독립 재계산.
  - `sp67_tech.py`, `sp67_test.py`, `sp67_resume_test.py`: 기술·재개·변조 검사.
- **자료 audit:** D는 8명 중 7명(51 IVD: 0=42, II=9), E는 48명 중 42명(289 IVD: 0=178, I=1, II=109, III=1)이 적격이다.
  - 계획의 "E 43명·298 IVD"와 다르다. 환자 35에서 T1/T2 mask label 집합이 다르고 ordinal별 S 중심이 158 mm 어긋나, 사전 gate가 제외했다.
  - T1이 없는 환자 6명도 제외했다. F139는 열지 않았다.
- **기하 검증:**
  - RAI 85개, ASL 13개 volume(최대 기울기 6°)이다. 방향은 header 문자열이 아니라 direction 행렬의 지배 성분으로 정했다.
  - SimpleITK physical 대조 최대 상대 오차는 0.0055이다.
  - 영상과 mask의 grid는 일치했고 mask 안 voxel 값도 원 배열과 일치했다.
  - D 7명(RAI)의 중앙 slice montage를 직접 봤다. 전방 좌측, 상방 위, crop이 disc 중심으로 맞았다. ASL은 E 환자 162의 montage에서 같은 방향을 확인했다.
- **입력·점수:**
  - 입력은 native sagittal stack 전체를 같은 crop·window로 렌더한 448² 영상이다.
  - 후보 A/B/C/D는 두 모델 모두 한 token이다. 점수는 공식 `model.forward`의 마지막 위치 logits에서 얻었다.
  - batch1로 실행했고 batch 확대와 GPU당 2 worker는 채택하지 않았다. 근거는 아래 기술 검사 항목에 적었다.

# Files Changed

- **새 코드(`research/`):**
  - `sp67_data.py`, `sp67_audit.py`, `sp67_render.py`, `sp67_montage.py`
  - `sp67_run.py`, `sp67_tech.py`, `sp67_eval.py`, `sp67_select.py`, `sp67_verify.py`
  - `sp67_test.py`, `sp67_resume_test.py`
- **반입 파일(`rsna_diag/` 4개, `m65_run.py`, `msd56_run.py`):** 수정하지 않았다.
- **결과:** `results/iter_067/`에 다음을 저장했다.
  - `data/`: audit, pairs, render manifest, requests, protocol, select_D, check montage 3종
  - `tech/`, `gen_D/`, `gen_E12/`
  - `eval/D/`, `eval/E12/`(`report.json`, `independent_verify.json`)
  - `tests/`: `cpu_tests.json`, `resume_test.json`
- **환경:** `results/environments/sitk67/site`에 SimpleITK 2.5.6을 `python -m pip --target`으로 격리 설치했다. 처음 시도한 venv 안의 pip 설치는 권한 승인이 필요해 쓰지 않았다.

# Commands / Experiments (실제 실행한 명령과 성공/실패)

- `sp67_audit.py`: 성공.
- `sp67_render.py D`, `sp67_render.py E 12`: 성공.
- **기술 검사(`sp67_tech.py`):**
  - 처음 실행은 MedGemma가 영상 100장을 한 번에 처리하다 OOM으로 실패했다.
  - vision tower를 8장씩 나눠 처리하도록 감쌌다(영상 수·해상도·순서는 그대로). 이후 두 모델 모두 `ok=True`다.
  - forward와 generate 첫 단계의 후보 확률 최대 차이는 0.0이다.
  - S1/S2 영상 tensor는 J의 앞/뒤 부분과 같다.
  - chunk 8 대 64의 후보 logit 차이는 MedGemma 0.25, Qwen 0.125였고 argmax는 같았다(bf16 수치 차이).
  - 최대 stack(영상 100장)의 peak reserved는 MedGemma 19.2 GiB, Qwen 22.8 GiB다. 한 GPU에 worker 2개는 불가능하고, batch는 입력 길이가 가변이라 채택하지 않았다.
- **D·E12 점수 실행:** GPU 0에 MedGemma, GPU 1에 Qwen을 두고 각 1 worker로 `launch`했다. 모두 rc=0이다.
  - protocol은 D에서 코드 수정 뒤 `protocol_D_v2.json`로 다시 잠갔다. 첫 launch는 Qwen admission이 24.0 GiB 필요로 계산돼 거부됐고, 점수는 생성되지 않았다.
  - 실행 시간은 D가 약 1시간, E12가 약 1시간 이내다(`launch_*.json`의 시각 기준 추정, 정밀 wall은 측정하지 않았다).
- **`sp67_select.py`:** 두 모델 모두 D의 S1/S2 BA02가 같아 B=T1이 됐다(동률 규칙).
- **`sp67_eval.py` D·E12:** 성공했다.
- **`sp67_verify.py`:** 원시 JSONL에서 독립 재계산한 BA02가 report와 모두 일치했다(최대 차이 0).
- **`sp67_test.py`:** 18/18 통과.
  - canonical RAI/ASL, 사선 거부, crop 경계, 지표 함수, protocol 변조 거부, J=S1+S2 순서, T 무영상을 확인했다.
- **`sp67_resume_test.py`:** 통과.
  - 3건 저장 뒤 torn tail을 붙이고 2 worker slot으로 재개했다.
  - 복구 13바이트는 `.corrupt_*`로 보존됐다.
  - 8/8 완료, 중복 0, 누락 0, 기존 D 점수와 logit 차이 0이다.
  - 요청 변조는 `protocol mismatch: requests`로 거부됐다.

# Results (수치와 결과 파일 경로)

BA02는 E12(12명·81 IVD), 환자 cluster bootstrap 95% CI(seed67, 10,000회)다. 전체는 `results/iter_067/eval/E12/report.json`에 있다.

| 조건 | MedGemma | Qwen2.5-VL |
|---|---|---|
| S1 | 0.000 | 0.5 |
| S2 | 0.038 | 0.5 |
| J | 0.094 [0.023, 0.182] | 0.5 |
| LF | 0.000 | 0.5 |
| R(T1 복제) | 0.019 | 0.5 |
| text-only | 0.434 | 0.0 |
| prior(global/ordinal) | 0.5 | 0.5 |

- **예측 분포:** MedGemma는 대부분 B(Modic I)를, Qwen은 모든 영상 조건에서 A(Modic 0)를 예측했다. Qwen의 II recall은 0이고 text-only는 모두 D다.
- **확대 기준:** 둘 다 "기본 신호 부족"으로 `stop`이다.
  - 영상 조건 중 BA02≥0.65이면서 prior·text-only·null을 5 pp 이상 넘는 것이 없다.
  - MedGemma의 J−B는 +0.094로 절대 5 pp 조건은 충족했지만, 기본 신호 조건이 앞서 실패했다.
- **null:** 같은 ordinal의 다른 환자 예측을 재배정하는 null은 80행을 쓰고 1행은 donor가 없어 제외했다.
- **후보 밖 최고 token 비율(D):**
  - MedGemma S1/S2 약 65–69%(top="Based"), T 100%.
  - MedGemma J는 2%로 낮다. 후보 질량 평균은 0.47–0.64이다.
  - Qwen은 영상 조건에서 0%이고 후보 질량이 0.998이다.
- **D 지표:** D는 baseline 선택용이며 확증이 아니다. BA02는 MedGemma S1·S2 0.024, J 0.119, Qwen 영상 조건 0.5다(`eval/D/report.json`).
- **사후 탐색(`eval/E12/independent_verify.json`):** 0 대 II 행의 p(C) 행 단위 AUROC는 MedGemma 영상 조건 0.72–0.77(text-only 0.47), Qwen S1 0.74, S2 0.59, J 0.56이다. 환자 cluster, 위치 교란, 사전 기준이 없는 값이다.
- **비용:** E12 영상 조건의 `t_total_s` 합계는 MedGemma S1/S2 약 400초, J 862초, Qwen S1/S2 약 260초, J 527초다. 환자·IVD 수는 같다.

# Goal Progress / Reused Assets (목표 진전·미검증 범위, 재사용 출처·검증)

**목표 진전**
- 임상의 Modic 등급(0/II) 과제에서 frozen MedGemma 1.5와 Qwen2.5-VL의 후보 분류 argmax는 기본 신호가 없다는 한정 관찰이 생겼다.
- J가 단일 sequence나 LF보다 낫다는 근거는 없고, J의 추가 이득이나 결합 능력은 판정하지 않는다.
- 미검증 범위: I/III 행, E 전체의 정밀도, 사례별 관측 필요성, 직접 SFT·전문 Modic classifier와의 비교, 후보 확률 순위 신호의 가치.
- 개발 split인 D/E만 사용했고 F139는 열지 않았다. 독립 확인이 아니다.

**재사용 자산**
- `mi19_mha`, `mi19_render`: 방향 해석에는 쓰지 않았다. `volume_window`와 `to_uint8`만 호출했고, 방향·물리좌표는 새 canonical 경로와 SimpleITK 대조로 대체했다.
- `rsna_diag/geometry.py`: 이번 경로에서 호출하지 않았다.
- `m65_run`: `load_model`, `build_inputs`, `per_image_pixels`, `read_jsonl`, `repair_tail`, `append_row`, `env_info`를 사용했다. MSD 전용 CLI와 sidecar 비용 경로는 사용하지 않았다.
- `msd56_run`: MedGemma 로딩에만 사용했다.
- import closure는 위와 같고, 공식 processor 구성은 두 모델에서 호출 방식 그대로 썼다.

# Problems (현재 결론 무효 / 재사용 전 수정 / 추후 개선을 구분)

**현재 결론 무효: 없음.**

**재사용 전 수정 필요**
- **MedGemma 인터페이스:** 첫 token이 "Based"인 비율이 높아 후보 내 softmax의 의미가 불확실하다. Qwen의 항상 A도 calibration 또는 prior 문제일 수 있다. 모델의 영상 능력 부재로 단정할 수 없다.
- **자료·protocol:**
  - `sp67_run.py`에 후속 수정을 하면 `protocol_D_v2`/`protocol_E12`의 code hash 검증이 깨진다.
  - 평가 코드(`sp67_eval.py` 등)는 protocol의 code hash에 포함되지 않았다.
- **입력 경로:**
  - ASL oblique(최대 6°)는 축 permutation만 적용하고 resampling은 하지 않았다.
  - PNG를 `results/`에서 읽는 구조이므로, E 전체로 확대하려면 나머지 E 환자의 렌더가 필요하다.
- **R 조건:** 비용 집계 키가 `RT1`/`R`로 달라 R의 비용 합계가 0으로 나왔다(예측·BA02에는 영향 없음).

**추후 개선**
- 기술 검사에서 chunk 크기를 바꾼 logit 차이(0.125–0.25)가 있었다. 모든 실행은 chunk 8로 고정했다.
- batch>1과 GPU당 2 worker는 비교하지 못했다. 근거는 메모리(최대 입력 19.2/22.8 GiB)와 입력 길이 편차뿐이다.

# Recommendation to GPT

- **결정:** 사전 규칙대로 현재 frozen Modic 후보 분류 경로는 "기본 신호 부족"으로 종료하는 것이 맞다. 새 prompt·적응·E 확대는 시작하지 않았다.
- **한정 판단:** 이 결론은 MedGemma 1.5와 Qwen2.5-VL-7B, 이 prompt·후보 인터페이스, 개발 split E12(12명·81 IVD)에만 적용한다. MRI VLM 전체나 공동 처리 가능성의 기각이 아니다.
- **잔여 질문:** p(C) 순위 신호는 argmax 퇴화(MedGemma "Based" 선행, Qwen 항상 A)와 구분해야 한다. 이를 판별하려면 환자 cluster 단위 AUROC와 위치·ordinal 교란 통제가 필요하다. 기존 출력을 한정 재분석하는 편이 새 실행보다 먼저다.
- **비용:** 새 자료와 새 GPU 실행은 필요하지 않다.
- **방향 전환 조건:** 순위 신호가 위치 교란과 text-only를 넘으면 후속 방법 pilot(최소 개입)을 검토한다. 그렇지 않으면 Modic 경로를 종료하고 다른 질문으로 옮긴다.

SELF_CHECK: FAIL
SUMMARY: SPIDER Modic에서 T1/T2 공동 입력은 두 모델 모두 E12에서 기본 신호가 없어(MedGemma J BA02 0.094, Qwen은 항상 A로 0.5, 위치 prior 0.5) 사전 규칙대로 E 확대 없이 종료했고, 인터페이스 퇴화와 후보 확률 순위 신호(사후 AUROC 0.56–0.77)는 미분리다.