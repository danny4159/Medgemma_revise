# 요약

- **핵심 결과:** 미사용 RSNA 환자 192명에서 영상·detector 근거·공통 지시를 고정하고 초안만 바꿨다. 틀린 초안(W)이 초안 없는 판단을 명시 오답으로 바꾼 정도는 **H_W = +0.193, 95% CI [0.135, 0.250]**이다. 사전 기준(H≥0.10, CI 하한>0)에 따라 `content_harm_signal`이다.
- **근거:** 초안 없이 맞힌 163명 중 W에서 39명이 명시 오답으로 바뀌었고 반대 전환은 2명이다. 정답 방향 초안(C)의 H_C는 −0.078이다. 차이는 유보 증가가 아니라 명시 오답 전환이다(W의 unknown은 E 대비 +1명).
- **미검증·주의:**
  - 합성 초안 개입의 개발 진단이다.
  - 같은 RSNA의 새 환자이며 독립 도메인이나 사전학습 미노출이 아니다.
  - 단순 대안 S_W는 정확도가 E보다 낮고(−0.031, CI [−0.057, −0.010]) 확정 답변만 보는 H_conf는 0.052다. 유보 표현이 함께 늘어난 점은 주의해야 한다.
  - 자연 오류 빈도, 임상 효용, 신규성은 주장하지 않는다.
- **다음:** 자동 후속은 없다. 아래 Recommendation에 후속 후보를 제안했다.

# Work Performed

- **자료:** `reserve_patients.json`(opacity 496 / normal 5,562 / NLONN 2,050명) 중 iter_009/010 분할·제외 manifest 4개와 겹치는 환자를 제외했다(4,147명). reserve 후보는 겹침 0이었다.
- **선별:** category별 `sha256('iter118|'+patient)` 순서로, 적격 영상이 있는 환자를 차례로 골랐다.
  - TECH 6명(2/2/2), MAIN 192명(96/48/48), 건너뛴 후보 0.
  - 공식 Calculated 라벨이 정확히 1개인 영상만 썼다. 미표기는 음성으로 바꾸지 않았다.
  - mapping 중복과 ZIP 충돌이 있으면 중단하는 조건이었고 둘 다 0이었다.
- **영상·detector:**
  - DICOM에서 값 보존 PNG로 변환해 왕복 일치를 확인했다.
  - detector17 epoch18(체크포인트 SHA256 `576b8d78…` 일치, threshold 0.70)로 198장을 추론했다. 입력은 정답 없는 loader이고 `ed118_guard`로 정답 경로 접근을 거부·기록했다.
- **요청:** 환자당 3개 대화(E/C/W)를 만들었다. 영상 hash·packet·공통 지시는 같고 draft 줄만 다르다. 요청에는 불투명 slot(s0~s2)만 있고, 정오 매핑은 `private/cond_map.json`에 있다. 실행 순서는 환자 hash로 회전했다.
- **평가 고정:**
  - `ed118_spec.classify`는 방향과 hedged/conditional/contradictory/refusal/parse_failure/non_eos flag를 분리한다.
  - fixture 62개는 생성 전에 고정했다.
  - 평가기(`ed118_eval`)와 독립 verifier(`ed118_verify`)는 생성 전에 작성했다.
- **생성:**
  - `pg43_run`을 복사한 `ed118_gen.py`를 썼다. 변경은 worker의 audit hook(정답 경로 접근 거부·기록)과 코드 목록·실행 파일명뿐이다. 생성 protocol에는 정답·평가 파일을 잠그지 않았다.
  - TECH는 w2/w4/재개 검사로 18+18+6요청을 돌렸다.
  - MAIN은 4 worker(GPU당 2)로 576요청을 돌렸다.
- **평가·봉인:** MAIN 평가와 verifier 19개 검사를 통과했다. `completion.json`으로 봉인했다.

# Files Changed

신규 파일(기존 파일 수정 없음):

- 코드: `ed118_data.py`, `ed118_det.py`, `ed118_guard.py`, `ed118_spec.py`, `ed118_build.py`, `ed118_gen.py`, `ed118_run.py`, `ed118_eval.py`, `ed118_verify.py`, `ed118_tests.py`
- 반입(미추적 상태 확인): `rsna_diag/det_lib.py`, `rsna_diag/dicom_min.py`, `rsna_diag/rsna_data.py`
- 결과: `results/iter_118/{data,det,private,requests,protocol,gen,tests,tech,eval,launch}/`, `events.jsonl`, `completion.json`

# Commands / Experiments (실제 실행한 명령과 성공/실패)

| 단계 | 결과 |
|---|---|
| `python ed118_data.py build` | 성공, 82초. 단 중복 검사 비교 오류가 있었다(Problems 참조). |
| `conda run -p natten_py310 python ed118_det.py regress` | 성공. 기존 영상 2개의 box/score 차이 0.0, box 수 일치. |
| `ed118_det.py infer` | 성공. 198장 17초. |
| `ed118_build.py ledger / requests / weights` | 성공. 가중치 12개 파일이 iter_116 기준과 일치. |
| `python ed118_tests.py` | 62/62 통과. |
| `ed118_build.py lock` | 1회 실패성 재잠금(아래 설명), 최종 2026-10-12T12:23:43Z. |
| `ed118_run.py gen` TECH_w2 / TECH_w4 / RESUME6 | rc=0 / rc=0 / 부분 종료(rc=1, 의도됨) 후 재개 rc=0. |
| `ed118_run.py techreport` | all_pass=True. |
| `ed118_run.py gen --name MAIN --workers 4` | rc=0, wall 1,627초. |
| `ed118_run.py eval` / `seal` | 성공. |

**잠금 시각 정정:**

- 첫 잠금(12:23:10Z) 직후 `ed118_run.py`의 `event()` 인자 이름 충돌 버그가 났다. 생성은 한 건도 시작하지 않은 상태였다.
- 첫 잠금은 `eval_lock_v1_superseded_before_any_generation.json`으로 보존했다.
- 수정 후 재잠금한 시각은 12:23:43Z이며 TECH/MAIN 생성은 그 뒤에 시작됐다.
- classify 규칙 두 건(조건부 답 `If … then yes`, 거부+답의 flag 기대값)은 fixture 작성 중 **생성 전에** 고쳤다. 본출력으로 규칙을 고른 것이 아니다.

# Results (수치와 결과 파일 경로)

기준 파일: `results/iter_118/eval/report.json`, `per_patient.json`, `verify.json`(19/19 통과).

**규모와 설정**
- 본표본 192명(opacity 96 / normal 48 / not_normal_no_opacity 48), 576요청, 592 attempts(재시도 8건). TECH 18+18+6요청은 별도.
- 평가 잠금 hash는 `private/eval_lock.json`에 있다.

**조건별 결과** (N=192, direction 기준)

| 조건 | 명시 정답 | 명시 오답 | unknown | 확정 답변 | hedged | 평균 출력 토큰 |
|---|---|---|---|---|---|---|
| E(초안 없음) | 163 | 29 | 0 | 171 | 21 | 26.8 |
| C(맞는 초안) | 171 | 14 | 7(전부 non_eos) | 111 | 75 | 181 |
| W(틀린 초안) | 125 | 66 | 1(non_eos) | 106 | 85 | 59 |

**전이표**
- E→W: E 정답 163 중 W 오답 39, W 정답 123, W unknown 1. E 오답 29 중 W 정답 2.
- H_W = (39−2)/192 = **0.193**, bootstrap 95% CI [0.135, 0.250]. unknown을 어느 쪽으로 배정해도 범위는 [0.193, 0.198]이다.
- H_C = **−0.078** [−0.120, −0.042]. C는 E의 오답 16건을 고쳤고 E 정답 중 1건을 오답으로 바꿨다.
- 확정 답변만 본 H_conf(W) = 0.052 [0.021, 0.089]. 이 지표에서는 전환 일부가 hedged·unknown 쪽으로 이동하며, 확정 답변률은 E 171 → W 106이다.

**하위집단(설명용, 전체 분모 유지)**
- category별 H_W: opacity 0.271, NLONN 0.208, normal 0.021.
- detector가 맞은 166명의 H_W는 0.235이고 틀린 26명은 −0.077이다.
- E 정답이면서 detector도 정답인 157명 중 W 오답은 39명(전수 id는 `report.json`의 `conditional_on_E_ok`).

**단순 대안** (정확도, unknown은 오답 처리)
- B(detector 규칙) 166/192, E 163/192. E−B = −0.016 [−0.052, 0.021].
- S_W 157/192. S_W−E = −0.031 [−0.057, −0.010]. S_C 172/192, S_C−E = +0.047 [0.021, 0.078].
- S_W−W = +0.167 [0.104, 0.234]. S_W의 초안 유지 fallback은 15명이다.
- 공동 성공(box 유지/제거 포함): B 121, E 113, C 118, W 90, S_W 112.

**비용**
- MAIN wall 1,627초, GPU별 생성 구간 합집합 3,208초. 처리량은 약 21.2요청/분이다.
- peak 8.42GiB, 4 worker(GPU당 2). 계획의 단순 추정(약 13분)보다 길었는데, C/W 응답이 길었기 때문이다(평균 토큰 위 표 참조).
- detector 198장 추론은 17초(로딩 포함). S의 자연 초안 생성 비용은 측정하지 않았다.

**기술 검사** (`tech/tech_report.json`)
- TECH w2=w4=RESUME6 token 일치.
- 영상 hash가 환자 내 동일.
- iter_117 대비 generate/geometry/prompts hash 불변.
- worker의 정답·private 경로 접근 0, 거부 시도 0 (TECH, MAIN 모두. `eval/main_file_access.json`).
- 병렬 선택: w4가 w2보다 TECH wall 60.7→45.6초로 빨랐고 token이 같아 4 worker를 채택했다. GPU별 예상 peak 합+2GiB가 24.5GB 이내였다.

# Goal Progress / Reused Assets (목표 진전·미검증 범위, 재사용 출처·검증)

**진전 구분**
- **실행 복구/구현:** worker의 정답 접근 분리, 재개 가능한 launch는 완료됐다. 이것은 과학적 증거가 아니다.
- **연구 관찰:** 합성 틀린 초안이 초안 없는 명시 판단을 오답으로 바꾸는 효과가 이 집단에서 사전 기준을 넘었다. 유보 증가(unknown +1명)로는 설명되지 않는다. iter_117의 R 관찰(교정 0, unknown 43/87)은 안내문·초안 차이가 얽혀 있었는데 이번에 초안 내용만 바꿔 분리한 방향에서 지지된다.
- **경쟁 설명:** 기본 인식 부족은 E 정확도 163/192와 B 166/192로 일부 완화했다. 틀린 초안에 의한 hedged 표현 증가는 남아 있다.
- **미검증:**
  - 자연 발생 초안 오류의 빈도와 효용.
  - 독립 도메인과 다른 모델·질문. 기존 선행(Anatomically-Grounded Fact Checking, To Agree or To Be Right?)이 다루는 초안 민감성과 구별되는 신규성.
  - 위치 근거의 인과적 사용. 합성 개입이 모델 내부 anchoring 때문인지도 미검증이다.

**재사용 자산과 required_checks**

- **`det_lib.py`**
  - 체크포인트 SHA256 확인 ✔.
  - 기존 영상 2개 회귀 차이 0.0 ✔.
  - GT 없는 loader 사용 ✔(`det_lib.RSNADetDataset`은 쓰지 않았다).
  - 현재 geometry의 값 보존 RGB 사용 ✔.
- **`rsna_data.py`/`dicom_min.py`**
  - mapping 중복·ZIP 충돌 중단 조건 확인 ✔(둘 다 0).
  - 선택 영상의 transfer syntax·display 태그 audit ✔(`audit_all` 경유).
  - 기존 영상 3개와 raw pixel hash가 manifest와 일치함을 확인했다(`manifest pixel_sha256`은 raw uint8 배열 hash).
  - patient/SOP/pixel 중복 제외 ✔(사후 raw 재검사 포함).
  - 기존 파일 변경 없음 ✔.
- **ed116/ed117 재사용:** `ed116_spec.packet_text`, `ev108/ev109`, `qa_spec`는 읽기 전용으로 사용했다. `pg43_run`은 원본을 보존하고 복사본만 수정했다.

# Problems (현재 결론 무효 / 재사용 전 수정 / 추후 개선을 구분)

**현재 결론 무효:** 없음.

**기록해야 할 선별 시 결함(결론에 영향 없음 확인)**
- `ed118_data.py`의 pixel 중복 검사가 padded hash로 기존 manifest의 raw hash와 비교되어 사실상 무효였다.
- 선별 후 raw hash로 다시 검사했다(`data/dedup_raw_check.json`). 중복 0, 198 고유 hash였다. 코드는 사후에 고쳤고 이미 만든 결과는 보존했다.
- legacy 익명 영상과의 중복은 검사하지 않았다(미검증).

**재사용 전 수정 / 한계**
- `ed118_verify.py`의 방향 일관성 검사는 단순 규칙이다. 독립 의미 검증이 아니다.
- classifier 규칙은 본출력 이후 변경하지 않았다. 형식 처리는 고정된 문형만 인식하며 나머지는 unknown이다. 이번 본출력에서 parse_failure는 0이었다.
- 처리량 기록의 `device_seconds_incl_loading`은 비교 가능하지만 재개 구간이 섞이면 보정이 필요하다(이번 MAIN은 단일 launch).

**추후 개선:**
- 대표 6명 TECH overlay로 annotation·좌표를 확인했다. MAIN 192명 전수 시각 확인은 하지 않았다.
- 응답 텍스트는 환자별로 400자까지만 저장했다. 원문 전체는 gen 출력에 있다.

# Recommendation to GPT

1. **결과 해석:** 초안 영향은 "명시 오답 전환"으로 나타났다. 이 신호는 합성 개입의 개발 관찰이며 자연 오류 효용으로 확대하지 않는다. 확정 답변만 보면 효과가 약해(H_conf 0.052) 유보 표현 변화와 분리해 해석해야 한다.
2. **투자 판단:** 단순 대안으로 충분한지는 아직 판별되지 않았다. S_W는 E보다 낮고 S_C는 E보다 높다. 이는 정오 초안을 알고 구성한 대조라서 실용 비교가 아니다. "초안 무시(E)"가 정확도와 비용 면에서 이미 강한 대안이다(B와 비슷, 추가 호출 없음).
3. **후속 하나(제안만):** 위치 근거는 그대로 두고 초안 정보를 달리해 "초안을 무시하는 지시"만으로 W 효과가 사라지는지, 아니면 구조적으로 남는지 확인한다. 자연 발생 초안 오류의 빈도 추정은 외삽이 필요해 권하지 않는다. 학습·확대는 자동으로 하지 않는다.
4. 음성 판정이나 단순 대안으로 충분한 경우 iter_115의 CURE 특화 투자 보류로 복귀한다. 이번 결과가 그 복귀 기준을 바꾸지는 않는다.
5. 사용자 승인 대기를 유지한다(`--confirm-each-iter`).

SELF_CHECK: PASS
SUMMARY: 미사용 RSNA 192명에서 틀린 초안이 초안 없는 명시 판단을 오답으로 바꾼 정도 H_W=+0.193 [0.135, 0.250]를 사전 기준대로 확인했다(content_harm_signal, 유보 증가는 +1명). 합성 개입이며 자연 오류 효용·신규성은 미검증이다.

# [orchestrator] 권한 거부된 도구 호출
- Bash: ls /SSD1_1TB/home/milab/daniel/08_medgemma/research/results/environments 2>&1; conda env list 2>&1 | head
- Bash: /home/test/.conda/envs/natten_py310/bin/python -c "
import torch,torchvision;print(torch.__version__,torchvision.__version__,torch.cuda.is_available())
c=torch.load('results/iter_035/train/seed17/epoch_18/model.pt',map_location='cpu',weights_only=False);print(type(c), list(c)[:5] if isinstance(c,dict) else '')
"; ls results/iter_035/train/seed17/epoch_18; python -c "
import json;d=json.load(open('results/iter_111/../iter_116/provenance/provenance.json'));print(d['det'])"; ls results/iter_035/eval/seed17/V400_e18 | head
- Bash: /home/test/.conda/envs/natten_py310/bin/python -c "import torch,torchvision;print(torch.__version__,torchvision.__version__,torch.cuda.is_available());c=torch.load('results/iter_035/train/seed17/epoch_18/model.pt',map_location='cpu',weights_only=False);print(type(c), list(c)[:5] if isinstance(c,dict) else '')"
- Bash: python ../experiment_wait.py --pid $(pgrep -f "ed118_gen.py launch" | head -1) --timeout 600
