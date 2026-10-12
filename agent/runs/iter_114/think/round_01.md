# 사고 라운드 1

## 핵심

후속 질문과 접근법은 유지한다. 일반 대조를 의료 적응 MedGrounder MSPC로 좁혔고, 새 환자 후보의 실제 규모를 확인했다. 다만 기존 사용 환자 제외와 정밀도 설계가 미완료여서 구현 계획을 아직 확정하지 않는다. 코드·파일 수정, 모델 추론·학습은 수행하지 않았다.

## 원문에서 확인한 근거

- `agent/GOAL.md`, `agent/runs/iter_113/review.json` 및 `plan.json`, 관련 `agent/LIMITATIONS.md`와 `agent/CODE_ASSETS.md` 항목을 읽었다.
- iter_113은 valid_experiment=true, blocking_issues=[]다. 36명·47개 소견, K=12에서 CURE 불일치 9개 대 confidence 6개를 포착했다. 환자 bootstrap 구간 [-2,+6], 주석 민감도 [+2,+7], 환자 제거 [+2,+3]이라는 원 판정을 유지한다.
- 현재 `research/` status와 diff는 비어 있다. `nr113_core.py`, `nr113_run.py`, `nr113_tests.py`, `nr113_verify.py`, `nr107_geom.py`, `nr107_spec.py`가 현재 브랜치에 있다. 중복 반입은 필요 없다.
- `nr113_core.py`의 실제 규칙을 확인했다. D=1−union IoU, 양쪽 empty는 D=0, 한쪽 empty는 D=1; confidence 위험은 1−최소 유지 box score, MG empty는 1이다. 오류는 union IoU<0.3, K=ceil(N/4), 동률은 sha256(`iter113|item_key`)다. 후속에서도 동률 salt까지 유지해야 한다.
- iter_113의 seal은 검증 대상 digest 연결과 부분 분석 후 안전한 재개가 부족하다. 현재 결과는 유효하며 후속에서 사용하는 경로만 수정한다. verifier의 소수 12자리 반올림과 production 원 float 차이도 새 경계 동률에서 맞춰야 한다.
- `results/iter_046/decisions/final_selection.json`에서 대상은 A_U_e5, threshold 0.8, checkpoint `results/iter_046/train/U/weights_e5.pth`, SHA256 `b9c2bccd04dde8b7445aa5f60e082a0c93f1f2412af8a583a4ca5ee207c8718a`임을 확인했다.

## 일반 대조 선택

[MedGrounder 공식 저장소](https://github.com/aehrc/MedGrounder)는 MS-CXR+PadChest 적응본 `medgrounder_finetune_mspc.pth`를 공개하고, zero/one/multiple region 출력을 지원한다고 설명한다. [원논문](https://arxiv.org/html/2512.01085v1)의 Table III에는 다중 영역 성능이 보고돼 있으며 §V-C2는 confidence 0.8과 WBF IoU 0.1을 설명한다. 따라서 의료 적응 없는 일반 자연영상 grounder나 단일 box 모델보다 이번 대조에 적합한 후보로 선택한다. 원논문의 성능을 우리의 union IoU 오류 검토 성능과 동일시하지 않는다.

로컬 공식 코드 `results/iter_045/external/MedGrounder/`에는 MSPC config가 있다. 현재 확인한 로컬 가중치는 pretrain과 MS 두 개이며 MSPC는 아직 확보 여부·digest를 확인하지 못했다. 미설치를 제외 근거로 삼지 않으며 구현 단계의 공식 다운로드·격리 환경 사용은 승인 범위다. 다만 실제 배포 checkpoint와 논문의 split 대응·이용 조건을 확인해야 한다.

MSPC는 대상 MG와 같은 구조·공통 사전학습을 공유하므로 독립적으로 학습된 다른 계열 전체를 대표하지 않는다. 이 대조가 충분하면 특수 VLM 투자를 보류할 근거가 되지만, CURE가 이겨도 VLM 고유성의 증명은 아니다. 모델 순회나 새 seed 학습을 자동 발주하지 않는다.

[CURE 원논문](https://arxiv.org/html/2601.15408v1)의 §3.2는 PadChest-GR의 phrase당 복수 box와 공식 PG 형식을 지원한다. train/validation의 label augmentation과 test의 비증강 조건도 구분한다. 공개 모델의 알려진 학습·선택 노출과 알 수 없는 base 사전학습 노출은 별개로 기록해야 한다.

## 자료 규모: 읽기 전용 예비 집계

`research/results/datasets/padchest_gr/raw/grounded_reports_20240819.json`의 4,555개 영상과 `master_table.csv.zip`의 8,787행을 연결했다. `abnormal=true`, 공식 boxes≥2, 비어 있지 않은 sentence_en, progression=None만 적용한 결과다.

- train: 669명·677영상·857개 소견.
- validation: 107명·107영상·130개 소견.
- test: 169명·170영상·217개 소견.

이는 시간 비교 문구, 좌표, 기존 학습/선택/반복 평가 환자, 영상 중복을 아직 제외하지 않은 상한이다. 최종 표본 수로 쓰면 안 된다. 환자당 영상 선택과 기존 두 문장 선택 모집단을 어떻게 유지할지도 확정해야 한다. test 후보의 개별 모델 출력이나 오류는 확인하지 않았다.

`iter_039/data/selection_summary.json`에는 train의 D24/E288와 validation F120, E96/E192 하위집단이 남아 있다. 기존 계획은 보호 집단을 개방하지 않았으므로 현재 승인된 새 환자 확인에 사용할 범위와 과거 보호 이력을 명시해야 한다. 과거 원본 보호 기록을 수정해서는 안 된다.

## 재사용 경로와 비용 근거

- `e2a66795876215937e1eda5b2c6e70d30474298d`의 `nr107_run.py`를 읽었다. CURE 공식 processor·CLAHE 448·greedy·cap 1024→2048→4096, 요청별 저장과 shard 완료 검사가 있다. 의존성으로 `report86_common.py`, `pg43_run.py`, `rsna_diag/generate.py`, `geometry.py`, `parse.py`, 데이터 연결 파일을 참조한다. 현재 브랜치에는 실행기 의존 파일이 모두 있지 않으므로 정확한 반입 목록과 각 재사용 결함을 다음 라운드에서 확정해야 한다.
- 같은 커밋의 `nr107_data.py`는 기존 V96 연결에 고정돼 있으므로 새 환자 선정에 그대로 호출할 수 없다. `pg39_data.py`의 원 metadata 연결과 분할 ZIP reader는 재사용 후보다. 이미지 ZIP은 `.001`~`.037`을 합치지 않고 읽는 방식이다.
- `bab147379dde1bcd68550e298cc596ee15091e99`의 `mg45_mg.py`를 확인했다. 공식 build_medgrounder/val transform/WBF를 호출하고 checkpoint strict loading 및 원 영상 좌표 역변환을 제공한다. MSPC config를 명시하는 최소 확장이 필요하다. 외부 코드 revision은 `a0aad98d67018838fe160acbe1f7c3851fddeacc`다.
- CURE base revision은 `290cda5eeccbee130f987c4ad74a59ae6f196408`, adapter revision은 `4bb5dc5a5025a854d1f25e475769949915b08b44`다. `results/iter_107/protocol/weights_lock.json`에서 확인했다. MedGemma 1.5에 CURE adapter를 로드하지 않는다.
- iter_107 리뷰의 M47 wall-clock은 352.33초다. 계획의 과거 PG 6.33초/요청은 별도 참고값이다. iter_046 계획에는 MG 약 944문장/분이라는 이전 실측이 있다. 새 workload·동시 구성의 처리량은 아니므로 그대로 예산 확정값으로 쓰지 않는다.

## 다음 라운드에서 결정할 것

방향 전수 재검토는 필요 없다. 위 원문과 출처를 재사용해 실제 환자 제외 ledger, MSPC 대조 적합성 조건, 표본·정밀도·단계별 종료, 최소 반입 파일만 확정한다. A와 B를 구분할 초기 비교 및 성립 시 한정 확대를 하나의 구현 계획에 포함한다. 169명 이하의 후보가 원하는 정밀도를 지원하지 못하면 그 한계를 사전에 명시하고, 작은 비교 자체를 금지하거나 확증으로 과장하지 않는다.

## 다음에 파고들 질문
- 기존 PadChest 학습·선택·반복 평가 manifest와 환자·study·영상 중복을 제외하면 공식 test에서 동일 다중 영역 과제에 몇 명·몇 항목이 남는가? 기존 보호 집단과의 관계 및 환자당 영상·소견 선택 규칙은 무엇인가?
- MSPC 공개 checkpoint의 실제 배포·split·이용 조건을 확인하고, 기존 개발 자료에서 어떤 기본 위치 성능과 입력 검사를 만족할 때 일반 ensemble 대조로 인정할 것인가? 실패하면 A/B 비교를 어디까지 보류할 것인가?
- iter_113 환자 변동과 최대 적격 규모에서 최소 유용 효과·정밀도 목표를 어떻게 설정할 것인가? 반복 유의성 확인 없이 초기 비교와 한정 확대를 연결하고 A/B의 불확실성을 어떻게 보고할 것인가?
- CURE/MG 실행기에 필요한 실제 의존 파일과 원 리뷰의 재사용 결함은 무엇인가? 최소 반입 목록, digest 연결·안전한 재개 검사, 실측 기반 요청량·비용을 어떻게 잠글 것인가?
