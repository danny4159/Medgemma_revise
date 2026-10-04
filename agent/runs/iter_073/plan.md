# 요약

- 이번에 할 일: 공개 train/validation annotation의 환자 연결·결측·연골 size grade 분포를 점검하고 자료 도착 후 최소 비교를 준비한다.
- 필요한 이유: 직접 SFT와 crop은 이미 선행에 있다. 정답 prior와 단순 영역 판독 대안 이후 남는 질문을 구체화해야 한다.
- 확인할 기준: 출처가 고정된 annotation 연결, 결측을 보존한 집계, 환자 단위 분리, 선행과 구별할 비교 및 자료 인수 기준이다.
- 주의·다음: 실제 영상 정합·모델 성능은 미검증이다. 준비 결과를 한 번 보고한 뒤 자료 도착을 기다린다.

# Current Understanding

이번은 setup이다. 모델 추론·학습을 발주하지 않는다. 사용자 보완 `20261005_032747_b802ff04`에 따라 iter_072의 전면 작업 보류를 공개 annotation 점검과 조건부 설계 허용으로 변경한다.

기준 기록은 `agent/runs/iter_072/plan.md`이며 SHA256은 `509e169c47901adb58adaddaa24cd0450b6a10f2f0d0c2a19f44a8e5bd6684ac`이다. think/round_01·02의 조사와 최종 GOAL, MRI 우선, 원본 보존은 유지한다. 원본 OAI 영상 확보·계정 확인 요청, 실제 출력·학습은 보류한다. 결측·환자 연결·등급 분포의 실제 계산은 아직 수행되지 않아 이번 작업으로 지정한다.

현재 research HEAD는 `973628fd9852fd558796cffb2dcb60ba24f87bc2`이며 clean 상태다. iter_072 결과 디렉터리와 구현 산출물은 확인되지 않았다. 기존 기록을 덮어쓰지 않고 이번 산출물은 `research/results/iter_073/`에 둔다.

# Strategy Check / 연구 방향 판단

상위 질문은 질문에 필요한 근거를 선택해 판독에 사용하는가이다. iter_071은 두-category 위치 출력의 강한 detector 대안을 확인했지만 부위 내부의 임상 등급 판독을 평가하지 않았다. iter_072는 이를 연골 size grade 후보로 좁혔다.

남은 경쟁 설명은 실제 영상 판독 부족, 부위별 label prior, 영역 지원의 효과와 해상도 변화다. 이번 최소 작업은 공개 정답이 이 설명들을 구분하는 비교를 지탱하는지 확인하는 것이다. 모델의 인식·선택·결합 중 어느 실패도 새로 관찰했다고 말하지 않는다.

현재 방법 개선이나 기존 context 재진단보다 미실행 annotation 점검의 정보 가치가 높다. 자료 없이 GPU를 쓰는 기존 실험 재개는 이번 선택을 바꿀 근거가 없다. 지배 비용은 이번에는 자료 조회·연결 검증이며 실제 전송량과 처리시간을 기록한다. 새 benchmark·범용 framework는 만들지 않는다.

바뀔 결정은 하나다. 자료 도착 후 동일 supervision의 부위별 판독 비교로 진입할 수 있는지, 아니면 정답 연결 보완부터 해야 하는지다. 준비 완료 뒤에는 같은 작업을 자동 반복하지 않는다.

# Hypothesis

후속 가설 후보는 직접 적응 후에도 질문 대상별 size grade 구별에서 부위 prior나 단순 영역 판독으로 설명되지 않는 잔여 문제가 있다는 것이다. 현재는 가설이며 실제 모델 근거가 없다.

이번에는 annotation의 구조가 그 가설 검증을 허용하는지 확인한다. 동일 무릎에서 부위별 등급이 다른 사례의 수와 분포는 후속 대상 구별 대조의 적합성 정보다. 이를 모델 실패나 여러 관측의 결합 필요성으로 해석하지 않는다.

# Limitation Evidence / Correct Usage Checks

`limitation_ids=[]`로 둔다. 기존 MRI context 한계는 다른 과제의 observed 근거이며 이번 method gate로 전용하지 않는다.

size와 depth를 분리하고 grade_dict의 초기값 0을 실제 정상 정답으로 사용하지 않는다. null·빈 문자열·미측정·범위 밖 코드와 실제 0을 구별한다. grade에서 생성된 CoT와 answer 문자열은 추론 입력에 들어갈 수 없다. 공개 box는 주로 예측 해부학 영역이며 수동 병변 oracle가 아니다.

원본 영상 없이 확인할 수 없는 항목은 명시적으로 남긴다: 원본 MOAKS와의 임상 정답 일치, 좌표·orientation 정합, DESS의 관측 충분성, slice 선택 손실, 모델 및 segmentation 학습 노출이다.

# Contribution Path / Baselines / Reuse

가장 가까운 선행은 [3DReasonKnee §4](https://arxiv.org/html/2510.20967v1)의 직접 SFT와 instruction zero-shot crop 비교다. 이 비교의 재현은 새 기여가 아니다. 같은 적응과 영상·등급 supervision에서 단순 영역 판독 이후에도 의미 있는 정확도·효율 문제가 남는지가 후속 투자 조건이다.

이번에는 전체 majority 및 부위별 majority를 train에서만 정한다. 동률은 낮은 grade로 결정한다. validation에 고정 적용해 support, accuracy, class별 recall, macro recall, MAE를 기술적으로 집계한다. class가 없는 경우 recall을 0으로 채우지 않고 미정의로 표시한다. 부위·환자별 가중 방식을 명시하고 pooled 수치만으로 결론내리지 않는다. 이는 label-only 대조이며 모델 관찰이 아니다.

자료 도착 후의 주대조 후보는 직접 grade SFT, 동일 예측 영역을 제공한 grade SFT, 같은 영역·등급으로 학습한 분류기다. 공개 영역의 추가 supervision과 해상도·영상 범위 차이를 드러낸다. 다른 계열 VLM은 Qwen 계열을 우선 비교 후보로 유지하되 이번에 가중치를 받거나 순위표를 만들지 않는다.

iter_071 code_assets 원문을 확인했다. bbox parser·matching은 현재 집계와 맞지 않고 학습·launcher는 needs_fix다. 이번에는 반입·수정하지 않는다. `reuse_assets=[]`는 코드 소실을 뜻하지 않는다. 후속 학습 경로가 확정될 때만 관련 실제 파일·의존성을 검토하고 CE 실패 처리·재개·GPU 배치·provenance 결함을 수정한다.

# Proposed Experiment

## 1. 공개 파일 범위 고정

이전 조사 revision `7a611f92fd3ad3954e8b62feef49ee12bfef725a`에서 필요한 파일의 존재·크기·형식을 먼저 확인한다. 사용 revision, URL, 파일 hash, bytes를 기록한다. revision 변경이 필요하면 차이를 기록하고 혼합하지 않는다.

대상은 questions, question_subregion_mapping, grade_dict, labels mapping, 필요한 CoT mapping, train/val split, 관련 train/val grade annotation이다. 공식 test 답변을 다운로드·파싱하지 않는다. test split은 답변 없는 ID metadata만 환자 교집합 검사에 사용할 수 있으며 식별자만 포함됐는지 먼저 확인한다. all_studies는 필요한 연결 metadata만 사용한다. 영상·mask archive·전체 저장소 snapshot은 받지 않는다.

생성 annotation이 split 혼합 파일이면 개별 train/val 자료 또는 split으로 지정된 원 label 파일을 우선한다. test 답변을 파싱해야만 분리 가능한 구조이면 그 파일 분석을 보류하고 제한을 보고한다.

## 2. 연결·결측·분포 점검

연골 size에 해당하는 질문 집합을 공식 mapping으로 결정한다. 특정 부위의 유리한 분포를 보고 주과제를 사후 선택하지 않는다.

각 항목에 patient_id, time, knee_side, study_folder, series_folder, question_id, subregion, size grade, grade 출처와 결측 상태를 연결한다. ID는 문자열로 보존하고 좌우·시점을 파일명 추정만으로 확정하지 않는다. row와 환자·무릎·study·series 수를 구별한다.

다대다 join, 중복 key, 충돌 grade, orphan 경로, train/validation 환자 교집합을 검사한다. 양쪽 무릎과 모든 시점은 동일 환자 cluster로 묶는다. 정당한 복수 판독이 있으면 임의 평균이나 첫 행 선택을 하지 않는다. 공식 해결 규칙이 없으면 별도 충돌로 보존한다.

원 label과 배포 정답이 둘 다 있으면 연골 size의 일치를 계산한다. 원 label이 없으면 배포 내부 일관성만 검증했다고 쓴다. 결측과 실제 0의 구분 가능성, 부위별 grade 0–3 support, 환자 수, 시점·좌우 편중과 같은 무릎 내 grade 차이를 보고한다. 전체 원자료는 보존하고 분석 제외 사유를 기록한다.

## 3. 조건부 최초 실행 설계

후속 인수 목록은 환자·시점·좌우·DESS series 식별자, 해당 전체 DICOM series 또는 변환 provenance가 있는 NIfTI, 연결 MOAKS 원표, 사용할 경우 mask/box와 좌표 정의다. 연구실 전체 영상이나 모든 OAI 자료를 요청하지 않는다.

환자·시점 선택은 모델 출력과 무관하게 정한다. 주 분석은 환자별 적격한 가장 이른 시점을 우선하고, 좌우는 연결 가능한 범위를 보존하되 환자로 군집화한다. 중복 series는 공식 지정과 acquisition metadata로 해결하고 해결 불가 사례는 제외 사유를 남긴다. 공식 train에서 기술 확인 사례를 고르고 validation은 개발 평가임을 유지한다. 독립 확인용 표본과 규모는 영상 확보 뒤 고정한다.

자료 도착 후 순서는 ID·정답 연결 → DICOM/volume 방향·spacing·좌우와 box overlay → 관측 범위·입력 tensor 검사 → 공식 모델 입력 및 정답 token/mask·gradient·재개 확인 → 실제 기본 출력 → 별도 승인 계획의 직접 적응·모듈형 비교다. 모델 100% oracle 정답은 보편적 gate로 요구하지 않는다.

동작 확인, 가능성 탐색, 규모 확대, 독립 확인은 별도 단계로 문서화한다. 이번에 환자 수·epoch·LR 탐색량·효과 문턱을 임의 확정하지 않는다. 실제 적격 수와 입력 처리량을 얻은 후 실행 전에 고정해야 한다. 유효 관찰 없이 새 loss 학습으로 넘어가지 않는다.

# Implementation Tasks for Claude

1. 기준 계획·round_01/02와 이번 보완을 읽고 유지·변경·미확인 사항을 보고서에 짧게 정리한다.
2. 공개 파일의 필요한 범위만 확보하고 provenance와 test 답변 차단 경계를 기록한다. 공식 파일 접근에 실패하면 확인한 URL·오류와 필요한 대체 경로만 한정 확인한다.
3. 이 자료 전용의 작은 annotation 점검 스크립트를 작성한다. 기존 동일 기능이 실제로 있으면 먼저 확인해 재사용하며 범용 로더나 학습기를 새로 만들지 않는다.
4. null 대 0, 잘못된 grade, 환자 시점·좌우 누수, 중복·충돌 join, test 답변 거부를 작은 fixture로 검증한다. fixture는 코드 검증이며 가짜 환자 성능 실험으로 보고하지 않는다.
5. `research/results/iter_073/`에 출처 manifest, 연결·결측·분포 집계, train-only prior 결과, 자료 인수 기준과 조건부 비교 설계를 저장한다. 원자료와 제외 목록을 보존한다.
6. `claude_report.md`에 확인한 사실·미확인 사항·자료 도착 후 최초 행동을 보고하고 종료한다. 원본 영상 접근 질문을 다시 하지 않는다.

# Evaluation (성공/실패 기준 포함)

준비 충족은 출처 고정, 누수 없는 집계, 결측 의미의 명시, 선행과 구별할 질문, 인수 기준과 최초 검증 순서가 연결됐다는 뜻이다. valid model experiment나 method 효과로 보고하지 않는다.

- 양성: 공개 자료가 부위별 grade 비교를 지탱하면 연결 manifest와 비교 설계를 보존한다. 실제 영상 점검 후 출력 diagnostic 계획을 확정할 준비가 된 것이다.
- 음성: 결측 정상화·환자 중복·정답 충돌이 발견되면 원 자료 결함과 해소 가능 범위를 기록한다. 해당 경로의 학습을 보류하며 모델 한계로 해석하지 않는다.
- 불확정: 원본 MOAKS 또는 영상 없이는 풀리지 않는 항목만 남기고 종료한다. annotation이 없다는 이유로 다른 dataset을 순회하지 않는다.

주요 count와 train-only prior는 별도 간단 집계로 대조한다. validation 결과에 맞춰 질문·grade 통합·prior 규칙을 바꾸지 않는다. 이번은 준비의 완료 판정이며 논문 기여나 GOAL 완료 판정은 없다.

# Risks / Checks

이번 모델 요청·학습·GPU 사용은 0이다. 실제 blocker는 원본 OAI 영상 부재이며 해결 작업은 사용자 자료 도착 후 실제 경로·입력 검증이다. CPU-only 준비를 반복할 이유로 사용하지 않는다. 파일 수와 크기를 확인해 전송·처리 예상 비용을 기록하고 실제 비용과 구분한다.

후속 GPU 실행에서는 시작 직전 nvidia-smi, 허용 장치의 logical/physical 대응, 작업별 peak와 worker당 2GB 여유를 확인한다. 두 GPU에 독립 작업을 배치하고 작은 batch 확대 또는 GPU당 복수 worker의 처리량·정합성을 실제 입력으로 비교한다. 현재는 메모리·wall-clock을 추정할 근거가 없어 확정하지 않는다. checkpoint와 validation 경계 재개 검증은 실제 선택된 경로에 포함한다.

공개 예측 영역의 정확도·학습 노출과 원본 영상 정합은 metadata로 증명할 수 없다. crop 효과를 순수한 선택 원인으로 단정하지 않는다. 준비 결과를 한 번 보고한 뒤 새 자료 통지·실제 경로가 올 때까지 대기하며 동일 조사·구현을 자동 연장하지 않는다.

## 대규모 GPU 필요 후보

다기관 MRI의 vision encoder–connector–language 공동 적응은 장기 후보로 보존한다. 현재 준비 결과는 그 필요성이나 새 방법의 효과를 입증하지 않는다.

# 계획의 근거 (GPT 조사 노트)

## 확인한 것

- `agent/GOAL.md`, iter_072의 `plan.json`과 think/round_01·02 원문, iter_071 review.md 및 review.json의 code_assets, 관련 LIMITATIONS·CODE_ASSETS 항목을 확인했다.
- iter_072에는 구현 보고서나 결과 디렉터리가 없었다. 현재 research HEAD는 `973628fd9852fd558796cffb2dcb60ba24f87bc2`이고 작업 트리는 clean이다. tracked 파일에서 OAI/knee 전용 구현은 확인되지 않았다.
- 이전 계획 `agent/runs/iter_072/plan.md`의 SHA256은 `509e169c47901adb58adaddaa24cd0450b6a10f2f0d0c2a19f44a8e5bd6684ac`이다. 이번 사용자 보완은 그 계획의 작업 전면 보류를 한정 준비 허용으로 바꾼다.

## 선행과의 차이를 좁힌 근거

[3DReasonKnee 원논문 §4](https://arxiv.org/html/2510.20967v1)을 다시 확인했다. 영역 crop 비교는 instruction zero-shot 조건이고 SFT와 동일 모델·적응 조건을 모두 맞춘 대조는 아니다. 논문의 연골 점수는 여러 attribute를 묶은 값이므로 이번 size-only 과제의 기준값으로 사용할 수 없다. 따라서 질문은 'crop이 도움이 되는가'의 반복보다, 동일 적응·supervision 아래 단순 영역 판독 이후 남는 문제로 좁혀야 한다.

[공식 README](https://huggingface.co/datasets/rajpurkarlab/3DReasonKnee/raw/main/README.md)는 split에 patient_id, time, study_folder, series_folder, knee_side, image_filepath, label_filepath가 있음을 설명한다. grade mapping과 생성 annotation 경로도 안내한다. 이는 연결 점검의 출발점이며 실제 파일 완전성이나 환자 분리 검증을 대신하지 않는다. 웹 도구의 data tree 열기는 실패했지만 README와 논문은 열렸다. 이 오류를 annotation 부재로 해석하지 않는다.

## 유지할 한계

iter_072에서 확인한 revision `7a611f92fd3ad3954e8b62feef49ee12bfef725a`를 우선 사용하되 구현 시 실제 파일을 같은 revision으로 고정한다. 원본 MOAKS와 배포 정답의 일치, 결측 처리, 좌표 연결은 아직 미검증이다. 기존 MRI context observed 한계는 이번 무릎 과제의 method 근거가 아니다.

## 재사용 판단

iter_071의 승인 자산은 bbox parser·matching 범위다. 이번 annotation 집계에는 필요하지 않다. 학습·생성·launcher의 needs_fix도 실제 사용할 경로가 아직 없어 이번에 수정하지 않는다. 원문 조사와 출처를 재사용하고 새 소스 반입은 하지 않는다.

## 대규모 GPU 필요 후보

다기관 MRI의 vision encoder–connector–language 공동 적응은 장기 후보로 보존한다. 현재 annotation 점검으로 필요성이나 효과를 주장하지 않는다.
