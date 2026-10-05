# 사고 라운드 1

# 새로 확인한 것

OAI 대기 조건을 해제한다. `agent/runs/iter_074/review.md`와 `research/results/oai_intake_20261005_9HEIpm/README.md`를 확인했다. 세 ZIP은 표 자료이며 원본 MRI 확보를 뜻하지 않는다. 원본·정정·test 노출 기록을 보존하고, 추가 OAI 조회나 영상 경로 요청은 하지 않는다. 이번 라운드에서 OAI ZIP 내부 정답을 열지 않았다.

`agent/GOAL.md`, iter_072 plan 및 think/round_01.json, iter_064 review.json, iter_067 plan·review.json, iter_068 review.md, iter_071 review.md, 관련 LIMITATIONS·CODE_ASSETS 항목을 읽었다. 현재 research HEAD는 `5f2affbdd1d63328d6dbe1220725b41d04ded4d6`이고 작업 트리는 clean이다.

# 기존 관찰이 허용하는 판단

- iter_064의 MedGemma R→C BA 0.7708→0.5000 손실은 유효하다. 그러나 기본 신호 기준 미달, Qwen에서 동일 손실 부재, 명시적 index routing 대안 때문에 현재 context 안정화 방법을 자동 재개하지 않는다. 이 관찰은 인식이 통제된 선택 실패나 결합 실패의 증명이 아니다.
- iter_071의 E24 F1@0.5는 D8 0.1577, R8 0.1295, detector 0.8175였다. 현재 두-category 위치 과제와 RSNA 초기값의 확대는 종료된 범위로 유지한다. 이 비교는 영역 내부 임상 판독을 평가하지 않았다.
- iter_067~068은 SPIDER Modic frozen 출력과 고정 보정의 제한된 음성 결과다. 임상 판독 적응 전체의 반증은 아니지만, 학습을 시작하면 유망할 것이라는 근거도 아니다.
- iter_072에서 이미 검토한 SGMRI-VQA counting은 slice별 box 수와 고유 3D 병변 수가 구분되지 않아 채택하지 않았다는 원문을 재사용했다. 같은 후보를 재검색하거나 counting 실험을 발주하지 않는다.

# 자료 후보를 하나로 좁힌 확인

기존 SPIDER 자산은 `research/results/iter_021/source/`에 있다. 이번에는 파일 존재·크기, 기존 무결성 기록, grading CSV header만 확인했다. F139 영상·정답 분포를 새로 열지 않았다.

- images.zip: 3,700,562,886 bytes.
- masks.zip: 58,222,897 bytes.
- radiological_gradings.csv: 34,417 bytes.
- 기존 images_zip_verify.json은 배포 MD5와 로컬 MD5 `7a9fa44aac0c72e2937bdef62cff88db` 일치, 447 members, ZIP 검증 완료를 기록한다. 이번에 전체 hash를 다시 계산한 것은 아니다.
- 실제 CSV header에는 Patient, IVD label, Modic, UP/LOW endplate, Spondylolisthesis, Disc herniation, Disc narrowing, Disc bulging, Pfirrman grade가 있다. 열 존재는 새 과제의 label 의미·결측·환자 연결 검증 완료가 아니다.
- [공식 SPIDER 배포 페이지](https://zenodo.org/records/10159290)를 열었다. Grand Challenge data 페이지는 이번 웹 도구에서 403, 원 Scientific Data 페이지는 redirect 오류였다. 이는 이미 보유한 영상의 접근 불가를 뜻하지 않는다.

이 자산은 OAI의 확보 부담을 피할 수 있는 후보이지, 채택할 과학적 이유 자체는 아니다. 단순히 무릎 등급을 척추 등급으로 바꿔 같은 준비 과정을 반복하지 않는다.

# 가까운 선행이 바꾸는 투자 판단

[SPIDER 임상 등급의 radiomics 연구](https://www.nature.com/articles/s41598-026-56056-w)는 환자 분리하에 Pfirrmann 5-class 분류를 평가하고 TabPFN macro-F1 0.621을 보고한다. 저자 분석에서는 radiomics가 주요 신호를 제공하고 frozen ResNet feature의 추가 판별 이득은 없었다. 이는 저자 결과이며 우리 split의 재현이나 충분한 대안 판정은 아니다. 다만 crop 기반 등급 분류의 낮은 VLM 점수만으로 새 방법 필요성을 주장할 수 없다는 구체적 근거다.

[CrossSpine 원문](https://arxiv.org/html/2607.22728v1)은 sequence fusion과 IVD 위치 정보를 결합한다. 자료는 SPIDER가 아니라 PhenMec 237명·1,185 IVD이며 중앙 영상 선택을 사용한다. 따라서 그 점수를 우리 비교군 성능으로 옮기지 않는다. 일반적인 multi-sequence attention 또는 위치 prior 추가 자체가 새로운 구별점이 되기 어렵다는 점에 관련된다.

두 문헌은 조사 근거로만 보존한다. 우리 유효 실험에서 새 방향의 긍정적 근거가 없으므로 사용자 논문 추천으로 등록하지 않는다.

# Strategy Check / 연구 방향 판단

상위 질문은 질문에 필요한 근거를 선택하고 사용하는 능력이다. 현재까지 해결된 부분은 명시적 index routing, 단순 anatomy 위치 출력, 일부 공동 출력 형식 적응에 강한 대안이 있다는 것이다. 부위 내부 임상 판독에서 언어 조건부 적응의 효율·전이는 미검증이다.

세 선택을 비교했다.

1. 기존 context 또는 bbox 방법 개선: 남은 오류는 있으나 이미 확인한 단순 대안 이후 추가 투자 근거가 약하다. 재개하지 않는다.
2. 기존 SPIDER 임상 등급으로 부위별 판독의 학습·전이 가치 검증: 자료 확보 비용은 작지만 전문 분류+질문별 조회가 충분할 수 있다. 가장 먼저 검토할 후보이나 아직 실행 우선순위로 확정하지 않았다.
3. 현재 부위별 판독 묶음 보류: 새 과제가 단순 분류에 언어 인터페이스를 붙인 수준이라면 타당하다. 다만 기존 frozen·bbox 결과를 근거로 임상 판독 적응까지 기각하는 것은 부당하다.

남은 판단은 문헌의 수나 자료의 존재가 아니라, 강한 모듈형 대안과 구별할 실제 사용 조건 및 최소 비교를 정할 수 있는지다. 동일 annotation 예산의 학습 전이나 정확도–비용 이점도 후보 가치가 될 수 있으며, 모듈형 모델로 절대 불가능한 기능을 요구하지 않는다. 반대로 그런 이점이 있을 것이라는 추측만으로 학습을 발주하지 않는다.

이 충돌은 학습 투자와 연구 주장 범위를 바꾸므로 다음 사고 등급을 deep_high로 요청한다. 새로운 실험이나 문헌 검색 자체가 상향 이유는 아니다. 다음 라운드는 위 후보의 채택/보류를 판단하며 새로운 데이터 목록을 전수 조사하지 않는다.

# 재사용 경계

현재 브랜치의 git ls-files 확인에서 rk73 파일은 있으나 sp67·g71·mi19 후보 파일은 없다. 보관본 소실로 해석하지 않는다. iter_067 review.json/code_assets는 geometry의 물리좌표 비교, 공식 입력 대조, 동시 재개, provenance, 비용 집계에 needs_fix를 명시한다. iter_071 학습 경로에도 CE 검사·validation 재개·GPU 안전 여유 문제가 남는다. 실행 경로를 선택하지 않은 상태에서 전체 반입·정비를 발주하지 않는다. 따라서 reuse_assets는 아직 비어 있다.

# 남은 질문과 종료점

다음 라운드는 SPIDER 임상 판독에서 언어 조건부 전이 또는 효율이라는 구별점을 구체화할 수 있는지 결정한다. 가능하면 그 결정을 바꿀 최소 실제 실험과 필요한 소스 반입을 확정한다. 성립하지 않으면 이 후보를 보류하며 새로운 frozen 모델·동일 준비 작업으로 연장하지 않는다. OAI 또는 MR-RATE 접근 대기로 돌아가지 않는다.

# 대규모 GPU 필요 후보

여러 MRI 과제의 영역–임상 속성을 함께 학습하는 vision encoder–connector–language 공동 적응은 장기 후보로 보존한다. 현재 자료에서 필요성이나 경량 적응 대비 이점은 미검증이다. 이번에는 실행하지 않는다.

## 다음에 파고들 질문
- SPIDER의 부위별 임상 속성을 활용할 때, 영역별 전문 분류+질문별 조회와 동일 annotation 예산의 직접 SFT를 넘어 검증할 가치가 있는 학습 전이 또는 정확도–비용 조건 하나를 정할 수 있는가? iter_071·072의 종료 근거와 이번 radiomics 선행을 함께 고려해 채택 또는 보류를 결정한다.
- 후보가 성립한다면, 기존 개발 환자와 ordinal anatomy 연결만으로 위치 선택·판독·prior를 구분하는 최소 비교가 가능한가? iter_067 plan/review와 SPIDER 공식 label 설명을 기준으로 F139를 열지 않고 설계 가능한 범위를 확정한다.
- 단순 대안이 충분한 경우와 기본 적응 자체가 부족한 경우에 서로 다른 종료 결정을 내릴 수 있는가? 그 결정에 필요한 최소 실제 출력·학습 비교와 재사용 수정 비용을 정하고, 구별할 투자 결정이 없다면 실험 발주를 보류한다.
