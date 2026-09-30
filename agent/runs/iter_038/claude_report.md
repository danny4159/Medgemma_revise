# 요약

- **핵심 결과:** metadata 감사에서 세부 label과 location을 함께 쓰면 train의 다중 소견 영상 1,163개 전부에서 소견(finding) 대응이 유일해졌다. 즉 잔여 후보는 0이다.
- **근거:** handoff의 예비 집계 4개는 독립 재계산으로 모두 재현됐다.
- **미검증·주의:** 본 영상 38.5GB는 받지 않았다. 모델 실행·학습도 하지 않았다(setup). 영상 크기·bit depth·방향과 좌표 overlay는 미확인이다.
- **다음:** 남은 후보는 broad category만 공유하는 213영상이다. 이 층에 영상 확인이 필요한지는 GPT가 판단한다.

# Work Performed

- 원본 두 파일의 sha256을 handoff와 대조해 일치를 확인했고 ZIP CRC도 통과했다.
- 감사 스크립트 `padchest_audit038.py`를 작성해 실행했다. 원본은 읽기만 했고 내용 분석은 train에만 적용했다. validation/test는 ID·split 연결과 개수만 사용했다.
- 참고: 처음 schema를 볼 때 출력한 첫 레코드가 우연히 test split이었다. 집계와 선택에는 쓰지 않았다.
- 같은 감사에서 broad label 공유와 exact label-set 반복을 분리하고 category+location oracle 이후의 잔여를 계산했다. 유리한 정의를 새로 만들지는 않았다.

# Files Changed

- 신규 `padchest_audit038.py`
- 신규 `results/iter_038/audit/audit_checks.json`
- 신규 `results/iter_038/audit/source_manifest.json`
- 신규 `results/iter_038/audit/residual_pairs_private.json`(잔여 pair가 0개여서 빈 목록)

# Commands / Experiments

- `sha256sum` 두 파일: 성공, 일치.
- `python padchest_audit038.py`: 성공(rc 0).
- `python -c` label/location 열람: 성공. 문장 원문은 보지 않았다.
- `python -c` 소형 fixture(box 유효성, IoU, None 처리): 통과.
- GPU와 영상 다운로드는 사용하지 않았다.

# Results

**split 연결**

- 원본 규모: report 4,555개, master CSV 8,787행, 고유 ImageID 4,555개, 환자 4,459명.
- 중복과 충돌: ImageID 중복, 영상·환자·study별 split 충돌, report의 split 누락, 환자 중복이 모두 0이다.
- split별 영상 수: train 3,185 / validation 455 / test 915. 환자 수는 3,123 / 443 / 893명이다.
- 이전 영상(prior)을 참조하는 report는 1,446개다. 참조 존재만 확인했고 내용은 보지 않았다.

**train finding 집계**

- train finding은 총 7,315개다. 음성 2,401개, box 없는 양성 573개, 적격(abnormal이고 box가 있음) 4,341개다.
- 적격 finding이 2개 이상인 영상은 1,163개(환자 1,143명)이고, 이 영상에 속한 finding은 3,408개다.
- 스키마 문제, 유효하지 않은 box, label→broad group 매핑 오류는 모두 0이다.
- 정렬한 labels tuple이 영상 안에서 반복되는 영상은 20개, labels와 locations tuple이 모두 반복되는 영상은 0개로 handoff와 일치한다.

**oracle 이후 식별 가능성** (다중 소견 영상 1,163개 기준, 한 영상에 여러 소견이 있어도 각 소견이 서로 구별되는지를 본다)

| oracle 수준 | 구별 안 되는 finding | 영상 |
|---|---|---|
| broad category만 (26개 group) | 477 / 3,408 | 213 |
| 정확한 label 집합 | 41 | 20 |
| label + location | 0 | 0 |

**영상 안 finding 쌍의 관계** (총 4,100쌍)

| 가장 먼저 구별되는 수준 | 쌍 수 | 영상 |
|---|---|---|
| broad category가 다름 | 3,773 | 1,111 |
| broad category는 같고 label이 다름 | 305 | 213 |
| label은 같고 location이 다름 | 22 | 20 |
| label과 location이 모두 같음 | 0 | 0 |

- 영상별로 가장 어려운 쌍만 세면 각각 937 / 206 / 20영상이다.
- label을 하나라도 공유하는 쌍은 27개다.
- official과 extra annotation의 평균 최대 IoU는 0.488이다(3,684개 finding 기준). 경계 모호성이 크다는 뜻이다.
- 잔여 pair가 0이라 잔여 후보만의 일치도는 없다.

**20영상(22쌍)의 location 차이**

- label과 location 태그만 직접 열람했다.
- 깨끗한 좌/우 구분은 pleural effusion 좌/우, nodule 우상엽/좌상엽, 우상엽/우하엽, osteosynthesis 좌/우 등 소수다.
- 나머지는 aortic vs aortic button, nipple vs nipple 같은 태그 잡음이나 비어 있는 location이다. 이 부분은 눈으로 읽은 인상이며 정량 분류는 하지 않았다.
- 이 층에서 환자별 이항 오류율의 대략적 반폭은 `0.98/√20` ≈ ±22 pp다.

# Goal Progress / Reused Assets

- **자료 판단:** 계획의 음성 자료 결과 조건에 해당한다. 세부 label+location oracle로 대응이 모두 유일해진다.
- **남는 틈:** 그래도 broad category 공유 213영상(다중 소견 영상의 18%)과 location 단독 구분 20영상이 남는다. 앞의 213영상에서 세부 label을 문장에서 얻는 일은 언어 추출 문제일 가능성이 크지만, 이 감사는 그것을 검증하지 않았다.
- **재사용:** 기존 RSNA 코드는 쓰지 않았다(`reuse_assets=[]`). 감사 스크립트는 신규이며 duplicate key 검사, split 누락 검사, sha 고정 검사를 갖췄다.
- **결정한 것:** 영상 확인이 판단을 바꿀 근거가 metadata에서 나오지 않아 38.5GB는 받지 않았다.
- **미검증:** 영상 크기·bit depth·방향, 좌표 overlay(원본 영상 필요), 문장→label 추출 난도, 모델 성능이다. validation/test 내용은 열지 않았다. 과거 검사 영상도 받지 않았다.

# Problems

- **현재 결론 무효:** 없음.
- **재사용 전 수정:** 없음. 이번 스크립트는 결과를 매번 재계산하고 이전 결과를 재사용하지 않는다. 그래서 입력 변조 후 재사용 거부는 sha 고정 검사(불일치 시 종료)로 갈음했고, 변조 시나리오를 직접 실행하지는 않았다.
- **추후 개선:** synthetic 좌표 변환 fixture와 원본 overlay 검증은 영상이 있어야 가능하다. 영상 없이는 미완료다.

# Recommendation to GPT

- 세부 label+location 기준으로는 이 문장–영역 결합 후보를 우선순위에서 낮출 만하다. 잔여 후보가 0이다.
- 그래도 이어가려면 broad category 공유 213영상(train)을 평가 단위로 삼는 것이 유일한 후보다. 이 경우 영상 확인은 그 213영상 중심으로 필요하다. 실제 전체 압축 파일만 제공되는지, 개별 영상 접근이 가능한지는 확인하지 않았다.
- 이번 결과만으로 다른 질문으로 전환할지, 213영상 diagnostic을 진행할지는 GPT가 비교해 판단해 달라. 그 전까지 다운로드는 보류한다.

SELF_CHECK: PASS
SUMMARY: PadChest-GR metadata를 독립 검증해 handoff 집계를 재현했다. 세부 label+location oracle로는 다중 소견 영상 1,163개 전부에서 대응이 유일해(잔여 0) 본 영상 38.5GB는 받지 않았고, broad category만 공유하는 213영상은 GPT 판단 대상으로 남겼다.