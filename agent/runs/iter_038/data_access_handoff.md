# PadChest-GR 접근 승인 및 metadata 우선 점검 인계

## 사용자 승인과 범위 — 2026-09-30

- 사용자는 BIMCV의 PadChest-GR 접근 승인 메일을 제공했고, 이용조건을 전제로 주석·metadata를 먼저 받은 뒤 적격성을 판단하는 제안에 “그래 그렇게 너가 진행해”라고 승인했다.
- 이는 접근 신청 중이 아니라 접근 승인이 확보된 상태다. VinDr 승인은 별개이며 여전히 사용자 통지 대기다.
- 현재 iter_038의 GOAL·계획·분할 보존·full review는 유지한다. 새 학습이나 과거 검사 영상 다운로드 승인이 아니다.
- 주석 적격성이 확인돼 실제 영상 확인이 다음 판단에 필요하면 본 영상 약 38.5GB의 다운로드·안전한 압축 해제까지 승인 범위다. 과거 검사 영상 약 9GB는 받지 않는다.
- 공유 링크·원본 문장·환자 식별 metadata는 Git/Telegram/공개 기록에 넣지 않는다. 공식 공유 위치는 사용자의 비공개 대화에 있고, 이번 raw metadata는 아래 로컬 경로에 있다.

## 받은 원본

디렉터리: `/SSD1_1TB/home/milab/daniel/08_medgemma/research/results/datasets/padchest_gr/raw/`

| 파일 | bytes | SHA256 |
|---|---:|---|
| grounded_reports_20240819.json | 6287733 | efa16513850dc10f87073debb9c4b3ae1d0a1ae611f01b5705e808179854b14b |
| master_table.csv.zip | 590517 | 3e1d27c603f7b89d36dec0b69d03b45714deb5e6aa866ba0e008987c2f40d9ba |

공식 공유 폴더의 서버 파일 크기와 일치. SHA는 로컬 무결성·재현용이며 제공자 공식 checksum과 대조한 것은 아니다. ZIP CRC 검사 통과, 내부 파일은 master_table.csv 하나다. 일반 웹 download 주소는 빈 응답을 반환해 공식 서버의 public WebDAV 파일 경로로 다시 받았다. 빈 파일은 위 검증된 다운로드로 대체했다. 원본 영상·과거 검사 영상은 미다운로드다.

## 예비 집계 — 독립 검증 필요

- report JSON: 4,555개, ImageID 중복 0. metadata CSV: 8,787행(영상 수가 아님).
- ImageID로 split을 연결했을 때 report 미연결 0, 영상별 split 충돌 0, PatientID별 split 충돌 0.
- report의 split 개수: train 3,185 / validation 455 / test 915. validation/test의 findings 내용은 분석하지 않았으며 ID·split 연결만 확인했다.
- train에서 abnormal이 참이고 boxes가 비어 있지 않은 finding: 4,341개.
- 이런 finding이 2개 이상인 train 영상: 1,163개.
- 이런 finding의 정렬된 labels 전체 tuple이 영상 내 반복되는 영상: 20개.
- 정렬된 labels 전체 tuple과 정렬된 locations 전체 tuple이 모두 같은 finding이 반복되는 train 영상: 0개.

이 집계는 exact label-set 기준이다. broad category 공유, label 부분 중첩, annotation 누락·중복·경계 불확실성, 문장에서 실제 label/location을 추출하는 난도는 별도다. 0건을 MedGemma의 결합 능력 성공이나 모든 문장-grounding 연구의 무가치로 해석하지 않는다. 메타데이터로 해당 계획의 H_data를 식별할 수 있는지 재검토할 근거다.

## Claude에게 요청

1. 기존 plan.md를 유지하며 위 원본에서 출처·schema·split 연결과 train 집계를 독립 확인한다. ZIP은 안전하게 읽고 원본을 덮어쓰지 않는다.
2. broad label 공유와 exact label-set 반복의 차이를 분리하고, category+location oracle 이후 식별 가능한 대응 후보가 실제 남는지 확인한다. 새로 유리한 정의를 만들어 적격 사례를 억지로 늘리지 않는다.
3. metadata만으로 현재 질문의 식별력이 부족하다고 판단 가능하면 38.5GB를 받지 말고 유효한 자료 적격성 판단으로 보고한다. 영상 미확보를 실행 실패로 바꾸거나 빈 파이프라인 정비 반복을 만들지 않는다.
4. 영상 확인이 결정에 필요한 후보가 남을 때만 근거를 기록하고 본 영상 확보를 진행한다. 다운로드 시간·압축 해제 공간·파일 검증·재개를 확인한다. 과거 검사 영상은 제외한다.
5. 이번은 setup이다. 결과와 미검증 범위를 보고하고 GPT full review로 다음 판단을 받는다. 모델 실행·학습을 이번 승인만으로 시작하지 않는다.

비공개 데이터는 기존 Git 제외 경로 results/에 두며 원본 링크·임상 문장·식별자 행을 공개 로그로 옮기지 않는다.
