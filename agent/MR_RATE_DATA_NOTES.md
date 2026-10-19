# MR-RATE 선택 다운로드 사전 확인 — 2026-10-13

이 기록은 접근·schema 확인이다. 영상 반입이나 모델 실험이 완료됐다는 뜻이 아니다.

## 확인한 출처

- 공식 카드: https://huggingface.co/datasets/Forithmus/MR-RATE/blob/main/README.md
- 공식 자료 안내: https://github.com/forithmus/MR-RATE/blob/main/data-preprocessing/docs/dataset_guide.md
- 공식 코드/공개 모델 상태: https://github.com/forithmus/MR-RATE
- 확인 revision: f6e39794e7820c96c18465231a30da424e6d1c69.
  CLI에서 저장된 인증으로 protected splits 파일과 아래 CSV header 접근이 성공했다.
  인증 내용은 기록하지 않았다. 라이선스·접근 조건은 실제 사용 전에 공식 원문으로 확인한다.

## 실제 파일·header

| 파일 | 원격 bytes | 확인한 식별자·내용 |
|---|---:|---|
| splits.csv | 3017101 | batch_id, patient_uid, study_uid, split |
| pathology_labels/mrrate_labels.csv | 8419869 | study_uid와 37개 병리 열 |
| metadata/batch00_metadata.csv | 75862076 | patient_uid, study_uid, series_id, classified_modality, is_derived, acquisition_plane, is_localizer, is_center_modality, array_shape, array_spacing_mm 등 |
| reports/batch00_reports.csv | 12486287 | study_uid, report, clinical_information, technique, findings, impression |

질병 열에는 Cerebral infarction, Cerebral hemorrhage, Intracranial meningioma, Demyelinating disease of
central nervous system, Glioma 등이 있다. 열의 존재만 확인했으며 0/1/결측의 의미·빈도·신뢰도는 아직 미검증이다.
원 연구 질환을 미리 확정하지 않는다. neurovfm용 별도 라벨 파일도 있으나 원 라벨과 혼용하지 않는다.
전체 batch metadata를 받으면 수 GB가 될 수 있다. splits와 labels로 환자를 먼저 고르고 필요한 batch만 조회한다.

## 평가 한계·반입

공식 카드상 구조화 report와 병리 라벨 생성에는 LLM이 사용됐으며 segmentation은 예측 해부학 mask다.
전문의 검증 병변 정답으로 간주하지 않는다. study-level report와 입력 일부 series/slice 사이의 범위를 확인한다.
공식 모델 가중치 공개 여부도 실행 시 확인한다. MR-RATE의 영상 생성 모델을 진단 VLM 대조군으로 혼동하지 않는다.

MRI는 mri/batchXX/<study_uid>.zip 단위다. ZIP 안 series 필터로 원격 전송량을 줄일 수 있다고 가정하지 않는다.
선택 파일 목록·revision·원격 크기·수신 hash·split manifest·제외 사유를 남긴다.
데이터/cache 전용 경로: /home/test/.local/share/medgemma/mr_rate (현재 약 1.6TB 여유인 별도 파일시스템).
프로젝트 SSD는 약 18GB 여유이므로 모델·데이터 전체 복제 금지. 기존 모델 cache는 읽기 전용으로 재사용한다.
