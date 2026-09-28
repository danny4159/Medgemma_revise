# 요약

- **핵심 결과:** MedGemma 1.5(revision `91850547...`)에게 vertebra 인스턴스 두 개의 참조(reference) 위치를 알려주고 다른 슬라이스에서 같은 인스턴스를 찾게 하는 진단(D8→E48)을 실제 GPU에서 완료했다. E48(독립 48명, 실제 이번에 처음 생성된 출력)에서 **핵심 오라클 조건 O(정답 내부점 제공)의 pair success가 0/48(Wilson 95% CI [0, 0.074])**로 나타나 원 가설(H, 참조-인스턴스 오인식률 ≥15%)을 판정할 전제 자체가 무너졌다. 대신 "점(point) 하나를 vertebra 전체 bbox로 확장하는" 과제 자체가 이 모델에게 매우 취약하다는(success@0.5=2/96, 평균 IoU=0.107) 새로운 관찰을 얻었다. 반면 두 영상 참조-매칭 조건(J_TR 71%, A 67%)과 단순 위치 복사(C, 83%)는 오라클보다 오히려 더 잘 작동했다.
- **근거:** D8(96회)·E48(576회) 총 672회 실제 MedGemma 호출(계획한 규모와 정확히 일치). 형식 준수는 전 조건 100%(빈 응답·cap 도달 0%). 독립 재계산(별도 parser·IoU 구현)으로 저장 결과와 100% 일치 확인. 107개 fixture 전부 통과. images.zip(3.7GB) md5·zip 무결성 확인. D/E/F 195명 split 중복 없음.
- **주의:** D8 1~3차 시도는 prompt 형식 결함(참조 box를 bare list로 보여줘 모델이 답변 형식을 모사, 이후 예시에 넣은 placeholder 숫자를 그대로 복사)으로 게이트 실패했고, 이는 "정상 사용 확인"이라는 D8 취지에 맞게 프롬프트를 수정해 해결했다(3회 실패 기록은 `results/iter_021/prev_*`에 보존). O 실패로 F 확대는 계획대로 열리지 않았다(139명 F 보존).
- **다음:** 원 가설(H) 자체는 오라클 전제 실패로 미판정 상태다. "점→bbox 확장" 취약성이 재현되는지, 그리고 이것이 별도 연구 방향(단순 localization 신뢰성)으로서 가치가 있는지 GPT의 전략 판단이 필요하다.

# Work Performed

1. **iter_020에서 이어받은 코드 결함 수정** (모두 `research/rsna_diag/` 내):
   - `mi19_fetch.py`: Content-Range 검증, chunk별 sha256 저장·재검증, pwrite 길이 강제, 단일 소유권 lock(pid+starttime) 추가. 200 응답을 range chunk로 오인하지 않도록 거부.
   - `mi19_data.py`: 3D 6-connectivity 계산(scipy 없이 set 기반 BFS) 추가해 분리된 연결요소를 가진 label을 eligible에서 제외. pair 선택을 `hash % len(pairs)` 방식에서 후보별 SHA256 최솟값 선택으로 변경(열거 순서·개수 독립성 강화). SOURCE/DATA_DIR을 `results/iter_021/`로 변경.
   - `mi19_manifest.py`: 구현 버그와 자료 품질 문제를 분리하는 `DataQualityError` 도입(그 외 예외는 전체 gate를 막음). **실제 버그 발견 및 수정**: `check_coregistration`이 `direction` 필드를 부동소수 완전일치(`!=`)로 비교해 195명 중 21명(10.8%)이 부동소수 잡음(`0.9999999999999999 != 1.0`)만으로 잘못 제외되고 있었다. 1e-6 허용오차로 수정 후 재실행하니 195/195 전원 build 성공(n_errors: 21→0).
   - `mi19_protocol.py`: gate/manifest/split을 선택적 `--extra`가 아닌 항상 필수(`REQUIRED_DATA`)로 승격.
   - `mi19_pipeline.py`: 경로를 `results/iter_021/`로 변경, 기존 파일 존재만으로 건너뛰던 재사용을 요청 내용 재구성·대조(`_reuse_or_write_rows`)로 강화, S2 protocol이 S1 protocol·completion.json을 필수로 잠그도록 수정.
   - `mi19_requests.py`: S2 구성 시 S1 record 중복 request_id를 조용히 덮어쓰지 않고 거부하도록 수정.
2. **자료 준비**: SPIDER Zenodo record 10159290의 images.zip(3.7GB, md5 검증)을 새로 완전 다운로드(iter_020 progress는 검증 불가능해 재사용하지 않음), masks.zip/overview.csv/radiological_gradings.csv는 기존 md5 일치를 재확인 후 연결. 210명 T2 환자 중 195명 mask 기반 적격, manifest 195/195 build 성공, D8/E48/F139 split 확정.
3. **실제 overlay 검증**: D8 8명 + 방향 다양성 확보용 1명(z-sagittal, `107_t2`)의 R/T 렌더링 위에 bbox·point를 그려 좌표 변환이 실제로 해부학적으로 올바른 위치(척추体)에 놓이는지 육안 확인.
4. **D8 동작 확인 3회 반복(prompt 결함 발견·수정)**과 **E48 가능성 탐색**을 실제 GPU에서 실행(`run_iter021.py`, 새로 작성한 stage-gate 오케스트레이터).
5. **독립 재계산**으로 O 조건의 IoU·pair success를 별도 JSON parser·별도 IoU 구현으로 재현.

# Files Changed

- 수정: `rsna_diag/mi19_manifest.py`(coregistration tolerance 버그 수정), `rsna_diag/mi19_spec.py`(prompt 형식 3차 수정)
- 신규(이번 세션에서 작성, 이전 세션에 이미 커밋된 부분 제외): `run_iter021.py`(D→E→조건부F 오케스트레이터), `make_d8_overlays.py`(overlay 생성), `test_rsna_iter021_manifest.py`, `test_rsna_iter021_spec.py`
- 이전 중단 세션에 이미 커밋됨(체크포인트 `5b68a31d`, 이번에 재검증만 함): `rsna_diag/mi19_fetch.py`, `rsna_diag/mi19_data.py`, `rsna_diag/mi19_pipeline.py`, `rsna_diag/mi19_protocol.py`, `rsna_diag/mi19_requests.py`, `test_rsna_iter021_fetch.py`, `test_rsna_iter021_data.py`, 5개 iter_019/020 테스트 경로 수정

# Commands / Experiments (성공/실패)

- `python -m rsna_diag.mi19_fetch`(images.zip 신규 다운로드, 16 worker) — 세션 중단 후 재개(72.75%→100%), 성공. md5/zip 무결성 확인 성공.
- `python -m rsna_diag.mi19_data` — 성공(195/210 eligible).
- `python -m rsna_diag.mi19_manifest` — 1차 성공(174/195, 21건 false-exclusion), coregistration 수정 후 재실행 성공(195/195).
- `python make_d8_overlays.py` — 성공, 9장 overlay 생성, 육안 확인 완료.
- `python run_iter021.py` D8 attempt 1(원본 prompt) — **실패**(J_RT/J_TR valid_rate 0%, bare list 출력). 보존: `results/iter_021/prev_d8_v1_badformat/`.
- attempt 2(box를 산문체로 표현) — **실패**(여전히 bare list). 보존: `prev_d8_v2_bareformat_still/`.
- attempt 3(예시에 구체적 placeholder 숫자 `[100,200,300,400]` 추가) — D8 게이트는 통과했으나 **O/S2 조건에서 placeholder 숫자를 그대로 복사**하는 오염 발견, E48도 오염된 채 시작되어 중단(`TaskStop`). 보존: `prev_d8_v3_placeholder_copied/`(D8) 및 `.../E__phase1_partial`(중단된 E48).
- attempt 4(placeholder를 `Y_MIN_FOR_THIS_IMAGE` 등 비숫자 이름으로 교체) — **D8 게이트 통과**(J_RT/J_TR/O valid_rate 100%, cap 0%), O 오염 없음 확인 후 E48 진행. 최종 성공: D 96회, E 576회 = 672회 실제 GPU 호출, 요청 누락·중복·비EOS 종료 0건.
- 독립 재계산(별도 IoU/parser 구현)으로 O의 n_valid=96/96, success@0.5=2/96, pair_success=0/48, mean_iou=0.107 — **저장 결과와 완전 일치**.
- `mi19_protocol.verify()` 4개 protocol(D_phase1/2, E_phase1/2) 전부 재검증 통과. 사용된 56명(D+E) 112개 영상 파일의 현재 sha256과 manifest 기록 불일치 0.

# Results (수치와 결과 파일 경로)

**D8(동작 확인, n=8, `results/iter_021/report_D.json`)**: J_RT/J_TR/O valid_rate 1.0, cap_rate 0.0 → 게이트 통과.

**E48(가능성 탐색, n=48, `results/iter_021/report_E.json`, `eval_raw_E.json`)**:

| 조건 | pair_success (Wilson 95%) | 비고 |
|---|---|---|
| O (oracle, 정답 내부점 제공) | 0/48 = 0.000 [0.000, 0.074] | success@0.5=2/96, 평균 IoU=0.107 |
| S2 (2단계: 설명 생성 후 grounding) | 0/48 = 0.000 [0.000, 0.074] | |
| J_RT (ref→target, ref 먼저 제시) | 18/48 = 0.375 [0.252, 0.516] | wrong_instance 5/96 |
| J_TR (target→ref, target 먼저 제시) | 34/48 = 0.708 [0.568, 0.818] | wrong_instance 0/96 |
| A (참조 pixel 제거, box만 제시) | 32/48 = 0.667 [0.525, 0.783] | |
| C (동일 좌표 그대로 복사) | 40/48 = 0.833 [0.704, 0.913] | |
| N (NCC 영상 매칭) | 7/48 = 0.146 [0.072, 0.272] | |

**H (원 가설 사건, `report_E.json`의 `H`)**: 0/48 = 0.000, Wilson 95% CI [0.000, 0.074]. O_ok=False가 48명 전원이라 H가 정의상 0이 됨 (H는 O 성공을 전제조건으로 함).

**F 확대 결정 (`results/iter_021/decision_F.json`)**: `expand_F=false`. 사유: "O pair_success 0.0000 < 0.75 (gate fails)", "H_E=0.0000<0.15 and Wilson upper 0.0741<0.15". F(139명) 미실행, 보존.

**데이터 무결성**: `results/iter_021/source/images_zip_verify.json`(md5 일치, zip CRC 통과), `data/manifest.json`(195/195, n_errors=0), `data/split.json`(D8/E48/F139, 중복 0), `overlays/`(9장 육안 확인).

# Goal Progress / Reused Assets

**목표 진전**: iter_019~iter_020이 실제 환자 출력 없이 execution_failed로 끝난 것과 달리, 이번에 처음으로 **실제 MedGemma 출력 672건**을 얻었다. 그러나 얻은 결과는 원래 설계한 "H(참조-인스턴스 오인식)" 가설을 판정하지 못한다 — 그 가설은 O(오라클) 조건이 먼저 성공해야 검증 가능한데, O 자체가 거의 완전히 실패했기 때문이다(pair_success 0/48, Wilson 상한 0.074, n=48 표본으로 상당히 정밀하게 확인됨). 이는 계획서에 사전 등록된 "O가 낮으면 localization·표시·주석 범위가 더 중요한 경쟁 설명이다"라는 시나리오에 정확히 해당하며, 실행 실패가 아니라 유효한 진단 결과다.

**미검증/미확인 범위**:
- O의 실패가 이 특정 prompt 문구(점을 `[y,x]` 형태로 제시)에 국한된 것인지, 다른 point-prompt 방식으로도 재현되는지는 검증하지 않았다(추가 prompt 변형을 계속 시도하지 않기로 판단 — "결과에 맞춰 계속 prompt를 바꾸지 않는다"는 원칙에 따름).
- J_RT(0.375) vs J_TR(0.708)의 뚜렷한 비대칭(같은 과제, 이미지 순서만 다름)은 흥미로운 2차 관찰이나 이번 계획의 확증 대상이 아니어서 별도 검정하지 않았다.
- MedSAM2는 계획대로 "기존 호환 설치가 있을 때만" 실행하는 조건이었고, 이번에 설치를 확인하지 않아 미실행이다(강한 신경망 baseline 비교는 없음).
- 사전학습 노출·legacy 익명 영상 중복의 잔여 불확실성은 이전 iteration과 동일하게 미해결로 남아있다.
- **필수 검증 미실행 항목**: 계획 task 3에서 요구한 "고정 D 요청으로 부모 SIGTERM·worker 중단·마지막 record 절단 후 재개"의 통제된(synthetic) 재현 테스트는 이번 세션에서 별도로 수행하지 않았다. 다만 실제로 E48-v1 실행 중 부모 프로세스를 강제 종료(TaskStop)했고, 재시작 시 (a) GPU 프로세스/메모리가 정상적으로 정리됐음을 확인했고 (b) 오염된 stale request 파일을 `_reuse_or_write_rows`가 정확히 감지해 조용한 재사용을 거부했음을 실제로 관찰했다 — 이는 계획 취지의 실전 검증이지만, 계획이 명시한 "마지막 record 절단 후 재개" 케이스(파일 중간이 잘린 경우)는 별도로 재현하지 않았다.

**재사용 출처**: iter_009 승인 모듈(`geometry.py`, `parse.py`, `metrics.py`), iter_010 승인 모듈은 이번 반복에서 직접 사용하지 않음(MRI 진단은 별도 코드 계열). iter_019/020에서 needs_fix로 지적된 mi19_* 6개 모듈 전체를 이번에 수정하고 실제 실행으로 검증했다(위 "Work Performed" 참조). fixture 107/107 통과, GPU 실행 결과와 독립 재계산 일치.

# Problems

**현재 결론을 무효화하는 결함**: 없음. D8/E48은 유효하게 실행됐고 독립 재계산으로 확인했다.

**재사용 전 수정 필요(이번에 실제로 수정 완료)**:
- `mi19_fetch.py`의 Content-Range/체크섬 미검증 — 수정·fixture 12/12 확인.
- `mi19_data.py`의 pair 선택 방식·connectivity 미검사 — 수정·fixture 7/7 확인.
- `mi19_manifest.py`의 구현 버그/자료 문제 미분리, **그리고 이번에 새로 발견한 coregistration 부동소수 완전일치 버그**(21명 오탈락) — 수정·fixture 4/4, 실제 195/195 build로 확인.
- `mi19_protocol.py`의 자료 provenance 선택적 잠금 — 필수로 변경, 4개 protocol 실제 재검증 통과.
- `mi19_pipeline.py`의 존재-기반 재사용 — 요청 내용 대조로 강화, 실제로 오염된 재사용 시도를 정확히 차단하는 것을 관찰.

**추후 개선(현재 결론을 막지 않음)**:
- SIGTERM 중간 절단 재개의 synthetic 테스트 미실행(위 참조).
- O 실패의 원인(prompt 문구 vs 근본 능력)을 구분할 추가 진단은 하지 않았다 — 다음 계획에서 GPT가 가치 판단할 사안.
- MedSAM2 등 학습된 모듈형 대안 비교 미실행.

# Recommendation to GPT

O(오라클) 조건이 n=48에서 pair_success 0%(Wilson 상한 0.074)로 사실상 완전히 실패해, 원래 가설(H)을 판정할 전제 자체가 막혔다. 반면 J_TR(71%)·A(67%)·C(83%)는 상당히 잘 작동해, "점을 vertebra 전체 bbox로 확장"하는 이 특정 과제가 유독 취약하다는 것이 이번 결과의 핵심 신호다. 이는 RESEARCH_POLICY.md가 요구하는 전략 재검토 시점("강한 단순 baseline 확보, 불확정 결과의 반복, 새 투자 직전")에 해당한다고 판단한다. 다음 계획에서 다음을 비교해 판단해달라: (1) O의 prompt를 한 번 더 다르게 표현해 재현성을 좁히는 진단, (2) 원 가설(H)을 O 없이 판정 가능한 대체 설계(예: target 자체에서 직접 J 조건만으로 wrong-instance 비율을 보되 O 게이트를 없애거나 다른 전제 조건으로 대체)로 전환, (3) 이 "점→bbox 확장" 취약성 자체를 새로운 연구 질문으로 승격(F 139명·다른 데이터셋에서 재현성 확인 후). J_RT(37.5%)와 J_TR(70.8%)의 비대칭은 다음 판단에 참고할 부차 관찰로 남긴다.

SELF_CHECK: PASS
SUMMARY: D8→E48 진단을 3차례의 prompt 형식 수정 끝에 실제 GPU에서 완료(672회 호출, 독립 재계산 일치)했으나, 오라클 조건 O가 n=48에서 거의 완전히 실패(pair_success 0%, Wilson 상한 0.074)해 원 가설(H) 판정이 막혔고, F 확대는 계획대로 보류됐다 — 다음 투자 방향에 대한 GPT의 전략 판단이 필요하다.

# [orchestrator] 권한 거부된 도구 호출
- Bash: for f in test_rsna_iter019_baseline.py test_rsna_iter019_render.py test_rsna_iter019_eval.py test_rsna_iter019_mha.py test_rsna_iter020_mri.py test_rsna_iter021_fetch.py test_rsna_iter021_data.py test_rsna_iter021_manifest.py test_rsna_iter021_spec.py; do
  echo "== $f =="
  python "$f" > /tmp/testout_$f.log 2>&1
  echo "exit=$?"
done
- Bash: python test_rsna_iter019_baseline.py > /dev/null 2>/tmp/e1.log; echo baseline=$?
python test_rsna_iter019_render.py > /dev/null 2>/tmp/e2.log; echo render=$?
