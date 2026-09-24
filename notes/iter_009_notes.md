# iter_009 노트: 정상 사용 조건의 RSNA opacity grounding 진단

## 유지 / 보류 / 변경 (사용자 보완 `20260924_104125_9b1acb6f`)

- 유지: 연구 목표, iter_003~008 기록·결과·보관 ref, `grounding_data/*`(수정하지 않음), 승인 커밋 `68117cf` 기반.
- 보류: iter_008의 anatomy→lesion 학습, pooling 재실험. 실행하지 않았고 삭제·수정하지 않았다.
- 변경: 주평가 자료를 RSNA 2018 adjudicated 공개판(30,000 영상, NIH 유래)으로 바꿨다. 공식 anatomy notebook은 사용법 sanity로만 사용했다.

## 실제 확인한 사실

- 공식 배포 3개 파일은 S3에서 전부 받았다(ZIP 3,978,753,654 B, sha256 `96b97d81…3b50`). 파일별 sha256·ETag는 `results/iter_009/source/raw/*.provenance.json`.
- 라벨: labelGroup `Calculated`의 Normal 9,790 / No Lung Opacity·Not Normal 12,788 / Lung Opacity 7,106(bbox 11,390개, 모두 1024×1024 canvas·범위 유효). 316장은 Calculated 라벨 없음, 106장은 Exclude 라벨 → 제외. 주석 누락을 음성으로 취급하지 않았다.
- DICOM 30,000개 전부 1024×1024, 8-bit MONOCHROME2, PixelRepresentation 0, slope/VOI 없음, JPEG baseline(1.2.840.10008.1.2.4.50). pixel array를 그대로 사용했다(임의 정규화 없음). basename 충돌 0, mapping 중복 0.
- pydicom·skimage가 없고 pip가 거부돼 `rsna_diag/dicom_min.py`(최소 DICOM 리더)와 notebook 전처리 numpy emulation을 썼다. skimage 원문 실행이 아니다.
- 공식 notebook: `(pad_image_to_square(image)*255).astype(np.uint8)`는 RGBA 입력(float 경로)에서는 맞지만 uint8 L/RGB 입력에서는 uint8 wrap(예: 100→156)이 된다. 예제 영상은 RGBA(alpha 전부 255)라 emulation과 값 보존 경로의 입력이 동일했다(max abs diff 0). 본평가는 값 보존 경로를 썼다(L→채널 복제).
- pipeline("image-text-to-text")와 runner의 input_ids는 동일, pixel_values는 bf16 캐스팅 후 동일, 생성 텍스트는 예제 2건 + RSNA dev 2건 모두 일치.
- 공식 notebook은 MedGemma 1.5 release commit `7d9e43f9…`(2026-01-13)의 경로 최신 commit으로 확인(`notebook_commit.json`).

## 분석 결정 (사후 변경 아님, 사전 계획 그대로)

- patient는 mapping의 img_id 8자리 접두어(NIH Patient ID). 다중 category 환자 2,874명은 양성>Normal>NLONN 우선순위로 배정했으므로 Normal/NLONN 풀은 양성 영상이 없는 환자로 편향된다.
- 이전 반복에서 열어 본 NIH 환자 167명 제외(RSNA에 145명 존재). legacy `eval_samples`의 NIH 10장은 익명 파일명이라 제외 못 했다(미확인).
- concise prompt의 code fence(```json)는 허용하고 `fenced`/`marker_missing` flag만 남겼다.
- 유효 출력률 기준은 양성 200명 기준과 전체 300명 기준 둘 다 95% 이상일 때만 주가설을 판정하도록 구현했다.
- 독립 평가 전 `locked_protocol.json`으로 코드·prompt·manifest digest를 잠갔고 생성 후 `lock verified`를 확인했다. 잠금 이후 코드를 수정하지 않았다.
- 스케줄링 변경(사전 기재): dev 실행은 정적 shard, 독립 평가는 환자 단위 claim 큐. 출력 규약(입력·prompt·cap·greedy)은 동일하고 config_digest도 같다. dev 종료 후 큐 모드로 완료된 dev를 재개해 0건 재생성과 중복 없음을 확인했다.

## 한계

- RSNA는 NIH 기반의 특정 opacity 과제. 이 결과를 다른 병변·데이터셋·외부 기관으로 일반화하지 않는다.
- 사전학습 노출 여부는 알 수 없다. GT는 다중 판독 합의 bbox이며 임상 확진이 아니다.
- 음성(Normal/NLONN)의 추가 box는 annotation 대비 불일치이며 임상 오탐이 아니다.
- 좌표 연결 검사(overlay 16장)는 x/y 연결 확인이지 GT 재판독이 아니다.
- 원인(모델 내부·학습 데이터)에 대한 결론은 없다.

## 대규모 GPU 필요 후보 (유지)

고해상도 region–text alignment의 vision encoder/projector/decoder 공동 적응, anatomy·lesion·report 공동 학습. 이번 결과가 그 필요성을 입증하지는 않는다.
