# Work Performed

# 요약

- **핵심 결과**: iter_073의 test label 노출 이력과 annotation 해석을 정정했다. `rk73_*` 진입점을 고쳐 통합 원 MOAKS label을 파싱 전에 거부하고, 입력은 고정 manifest hash와 대조하도록 했다.
- **근거**: fixture 63/63 통과, 실제 허용 파일 12개의 pinned manifest 대조 통과, iter_073 산출물 26개 hash 변화 없음.
- **미검증·주의**: 모델 실험도 method gate 통과도 아니다. 공식 방문·부위·VERSION 연결, 임상 정답 일치, 영상 정합, 학습 노출은 미확인이다. 안전한 train/val 전용 원 label 출처가 없어 원 label 연결은 보류했다. test 환자 행 1,957개(행 수, 환자 수 아님)의 개별 grade가 임시 조회에서 어디까지 열람됐는지는 로그만으로 확정할 수 없다.
- **다음**: OAI 자료 도착을 기다린다. 사용자 통지와 실제 경로 확인 후 별도 계획을 세운다.

## 상세

- 기준 plan.md의 SHA256이 계획에 적힌 값과 일치하는 것을 확인했다. 시작 시 git은 clean이었다.
- 노출 이력은 iter_073 `claude_stream.jsonl`로 재구성했다. 통합 label을 split 제한 없이 연 임시 명령은 헤더 출력(call 10), 값 분포·SIDE 분포(call 13·14), SQ/FNIH 중복·충돌 비교(call 23)다. 여기에 리뷰에서 확인된 `load_moaks → moaks_lookup` 정규 경로를 합쳐 기록했다.
- 정정 문서 `correction_iter073.md`에는 원 표현 → 수정 표현 → 영향을 표로 남겼다. 정정 대상은 다음 네 가지다.
  - 결측→0 치환 단정
  - 임상 정답과 약 95% 일치
  - 단일 후보 행
  - test 보호 완료
- train/val 분포와 train-only prior(global 0.7233316266, subregion 0.7339136371)는 그대로 유지했다.
- `rk73_fetch.py`는 다운로드를 없애고 고정 manifest 검증 전용으로 바꿨다.
  - manifest 자체의 SHA256을 코드에 고정했다.
  - revision, bytes, sha256 불일치와 누락, symlink는 중단한다. 자동 재다운로드는 없다.
  - `generate_data/test*`와 `data/labels/*`는 manifest에 있어도 거부한다.
- `rk73_audit.py`는 다음처럼 바꿨다.
  - `load_moaks`는 파일을 열기 전에 항상 `LabelScopeError`를 낸다.
  - `moaks_lookup`은 `attrs['scope']=='train_val_only'` 표시가 없으면 거부한다. 이 표시는 우발 호출 방지용이며 위조 방지는 아니다.
  - `main`은 `--out`(새 iter_074 경로)을 필수로 받고 덮어쓰기를 거부하며, 파싱 전에 hash를 대조한다.
  - `--original-label-link` 요청은 어떤 파일도 읽기 전에 거부한다. 원 label 연결은 `deferred_no_safe_train_val_label_source`로 기록한다.
  - 연결 코드는 `link_original()`로 분리했고 호출하지 않는다.
  - `extract_split`은 split 밖 영상을 grade 집계 전에 `MembershipError`로 막는다.
- `test_rk73.py`는 import 시 결과 경로 생성과 iter_073 `fixtures.json` 덮어쓰기를 제거했다. `--out`과 `--before`가 필수다.
- `handoff_design_v2.md`에 정정된 인수 안내를 변경점 위주로 적었다.

# Files Changed

- 수정: `research/rk73_fetch.py`, `research/rk73_audit.py`, `research/test_rk73.py`
- 신규 (`research/results/iter_074/`, git 제외 영역):
  - `correction_iter073.md`
  - `handoff_design_v2.md`
  - `input_hash_verification.json`
  - `iter073_hashes_before.json`
  - `tests/run1/fixtures.json` (62/63, guard 경로 결함이 있던 첫 실행)
  - `tests/run2/fixtures.json` (63/63)
  - `tests/run2/work/` (synthetic fixture 작업물)
- iter_073의 결과·보고서·manifest는 수정하지 않았다.

# Commands / Experiments

- `sha256sum agent/runs/iter_073/plan.md`: 계획의 기준 SHA와 일치.
- iter_073 산출물 26개의 hash를 `iter073_hashes_before.json`에 기록(인라인 python): 성공.
- `python test_rk73.py --out results/iter_074/tests/run1 …`: 62/63, 실패. `/x/labels/…` 경로가 `data/labels/` 패턴과 맞지 않아 guard가 거부하지 못했다.
- `guard_not_test`에 `/labels/` 검사를 추가한 뒤 `run2` 실행: 63/63 통과, wall 11.58초. run1은 보존했다.
- `python rk73_fetch.py --out results/iter_074/input_hash_verification.json`: 허용 파일 12개가 pinned manifest와 일치(wall 2.61초).
- GPU 사용, 모델 호출, 다운로드, 실제 통합 label 열람은 모두 0이다.

# Results

- fixture 63/63, `results/iter_074/tests/run2/fixtures.json`. 경계 검사 항목은 다음과 같다.
  - `load_moaks`와 `--original-label-link`가 spy 기준 read 0건에서 거부됨
  - 같은 크기의 byte 변조, 잘못된 revision, manifest hash 불일치·누락·항목 누락이 파싱 전에 거부됨
  - 파일 누락 시 재다운로드 없이 중단됨
  - 금지 파일명과 목록 밖 파일이 거부됨
  - membership 불일치가 grade 집계 전에 실패함
  - 덮어쓰기와 iter_073 경로 출력이 거부됨
  - iter_073 산출물 hash가 전후 동일함
- 기존 의미도 fixture로 유지했다. null/0 구분, 같은 값 복수 후보 = unique, 충돌 = ambiguous, majority 동률(낮은 grade)과 없는 class(None), train-only 불변성이다.
- 실제 허용 train/val JSON의 독립 재집계가 iter_073 audit과 일치했다. 분포와 두 prior accuracy도 같고, 환자 교집합은 0이다.

# Goal Progress / Reused Assets

- 노출 범위와 해석 한계가 바로잡혔고, 준비 산출물을 어느 범위까지 재사용할 수 있는지가 분명해졌다. 새 모델 한계 관찰은 없다.
- 재사용한 파일은 현재 브랜치의 `rk73_fetch.py`, `rk73_audit.py`, `test_rk73.py` 세 개다. 반입한 것은 없고, 전체 pipeline 승인은 아니다.
- 미검증이다.
  - 공식 방문·부위·size/depth·VERSION 연결
  - 임상 정답 일치
  - 영상 방향·좌우·box 정합
  - 관측 충분성
  - 모델·segmentation의 학습 노출
- 자료 대기 상태다. OAI 영상은 확보되지 않았다고 가정한다.

# Problems

- **현재 결론 무효**: 없음. 다만 "test 보호 완료"는 철회됐다. 공식 test는 완전 미노출 집단이 아니다.
- **재사용 전 필수**: 안전한 train/val 전용 원 label 출처가 없어 원 MOAKS 연결은 보류 상태다.
  - 영상 도착 후 선택한 사례에서 공식 근거를 확인해야 한다.
  - 코드는 현재 통합 CSV를 항상 거부한다.
- **추후 개선**:
  - `attrs` 표시와 manifest hash는 split 안전성의 증명이 아니다.
  - 임시 조회의 test 행 열람 범위는 로그로 확정할 수 없다.
  - `link_original`의 mapping 가정은 그대로 남아 있다.

# Recommendation to GPT

- 이번 반복은 한 번 보완한 것으로 종료한다. 같은 조사나 준비 iteration을 반복하지 말고 OAI 자료 도착(사용자 통지와 실제 경로)을 기다린다.
- 도착하면 `handoff_design_v2.md`의 순서대로 다음을 진행한다.
  1. ID·정답 연결
  2. 정답 의미 확인
  3. 방향·box overlay
  4. 공식 입력과 소수 실제 출력
- 독립 확인 집단을 설계할 때는 test 환자 행 1,957개 노출을 명시해야 한다.

SELF_CHECK: PASS
SUMMARY: iter_073의 test label 노출 이력과 annotation 해석을 정정했다. 통합 원 label을 파싱 전에 거부하고 입력은 고정 manifest hash로 대조하도록 수정했으며, fixture 63/63과 실제 허용 파일 12개의 hash 대조를 통과했다. 모델 실험은 아니며 원 label 연결은 안전한 출처가 없어 보류하고 OAI 자료를 기다린다.