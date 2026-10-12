# 요약

- 이번에 할 일: BrainTRACE L2.4의 공개 원자료를 한 번 확보해 대상·정답·영상 연결을 검사한다.
- 필요한 이유: 질문 유형과 renderer는 확인했지만, 실제 행은 계획 환경의 접근 제한으로 읽지 못했다.
- 확인할 기준: 동일 대상의 sequence별 정답을 추측 없이 구성하고 동일 영상의 공동/독립 비교를 정의할 수 있는가?
- 주의·다음: 이번은 setup이다. 모델 한계를 검증하지 않으며, 연결이 미확인이면 후보를 보류하고 준비 반복을 종료한다.

## 알림 맥락

- 연구: MRI 다중 sequence 근거 연결 검토
- 데이터: 뇌 MRI MR-RATE와 연결된 BrainTRACE L2.4 질문·정답
- 모델: MedGemma 1.5 후속 후보, 이번에는 추론·학습 없음
- 과제: 같은 대상의 여러 sequence 신호를 독립·공동으로 비교할 수 있는지 확인
- 가설: 공개 정답과 실제 관측 연결이 개별 인식과 공동 답변 손실을 구분할 수 있다
- 질문: 여러 MRI 영상을 함께 읽을 때의 손실을 믿을 만한 정답으로 측정할 수 있는가?
- 변경: 구체화
- 연결: T2 정규화 변경은 판별을 회복하지 못했으므로 기존 frozen 설계는 종료하고 새 비교의 자료 조건을 확인한다
- 작업: 공개 원 행을 연결해 단일 실제 비교의 근거 확보 또는 후보 보류를 결정한다

# Current Understanding

기준 기록은 `agent/runs/iter_129/review.md`와 `agent/runs/iter_130/think/round_01.json`이다. 기존 T240명의 전원 양성·BA0.50 관찰은 유효하다. 정규화 설명 경로의 종료와 FLAIR 관찰의 조건별 보존을 유지한다. 같은 환자의 prompt·window·slice 순회, SynthSeg 누락 복구, 자동 LoRA는 이번 범위에 없다.

이번 조사에서 [공식 parquet](https://huggingface.co/datasets/lanqz7766/BrainTRACE/blob/main/data/test.parquet)의 경로와1.58MB 크기, SHA256 `9fb3d82729f4de24e3b9f794496c4bcc50edf45ce9ed0b7f2b9b23c0c731d737`을 확인했다. 실제 L2.4 행은 미확인이다. 공개 viewer의 부분 화면을 전체 자료 검사로 취급하지 않는다.

# Strategy Check / 연구 방향 판단

출처는 iter_129 리뷰와 이번 round_01이다. 변경 근거는 원자료 파일·무결성 기준의 확보다.

1. 중요한 문제: 개별 MRI 신호 인식과 여러 근거를 함께 사용할 때의 손실을 구분할 수 있는가?
2. 현재 근거: 기존 고정 응답은 실제 관찰이다. L2.4의 공동 근거 활용 실패는 아직 관찰되지 않았다.
3. 쉬운 해결책: sequence별 판독+결정적 결합이 직접 대조다. 이것으로 충분한 과제에 새 방법을 추가하지 않는다.
4. 남은 설명: 개별 인식, 대상 연결, 관측 부족, 보고서 reference의 불확실성이 남는다. 원 행이 이들을 분리할 수 있어야 한다.
5. 다음 결정: 한정 원자료 검사로 GPU diagnostic의 근거를 확보하거나 후보를 보류한다. 동일 조회를 위한 다음 setup은 발주하지 않는다.

# Hypothesis

후속 가설은 개별 신호를 읽을 수 있어도 공동 응답에서 연결을 잃는다는 것이다. 경쟁 설명은 개별 신호를 읽지 못하거나 해당 대상이 입력에 없다는 것이다. 이번에는 이 예측들을 비교할 자료 조건만 검사한다. 준비 성공을 가설 지지로 기록하지 않는다.

# Limitation Evidence / Correct Usage Checks

기존 limitation 세 항목은 연구 맥락이며 새 L2.4 한계의 근거가 아니다. method gate에 사용하지 않는다.

공식 renderer의 중앙 slice 또는 파일 선택 규칙은 해당 병변의 가시성을 보장하지 않는다. 원 rubric의 report 기술을 곧바로 slice 정답으로 바꾸지 않는다. 예측 해부학 segmentation을 병변 정답으로 사용하지 않으며, 새 LLM이나 구현자의 임상 추론으로 누락 정답을 채우지 않는다.

# Contribution Path / Baselines / Reuse

기여는 미확정이다. 자료가 지원해야 할 직접 비교는 같은 영상의 공동 답변과 sequence별 독립 답변의 고정 결합이다. 정답 선택지를 통해 독립 신호를 역추정하거나 질환의 전형적 MRI 신호를 환자 정답으로 만드는 것은 허용하지 않는다.

전문 모델·분류기+규칙의 지원 조건은 해당 실제 질문에 맞춰 짧은 표로 남긴다. 지원 모델이 미설치라는 이유로 제외하지 않지만 이번에는 설치하지 않는다. 직접 SFT도 이번 범위가 아니다.

현재 브랜치에는 `mr123_data.py`, `mr128_gen.py`, `mr129_control.py`, `mr129_finalize.py` 등이 있다. 이번 작업은 영상 생성·기존 평가기를 호출하지 않으므로 반입하거나 수정하지 않는다. `reuse_assets=[]`이며 기존 코드의 포괄 재사용 승인은 없다. 새 소스 작성 전 현재 브랜치에 동일 기능이 있는지 확인하고, 필요하면 작은 metadata 검사 스크립트만 추가한다.

# Proposed Experiment

## 1. 원자료 확보와 동작 확인

실행 담당은 공식 `lanqz7766/BrainTRACE`의 실제 revision을 고정하고 `data/test.parquet`, 필요한 cohort CSV와 설명 파일만 받는다. 저장 위치는 `/home/test/.local/share/medgemma/mr_rate/braintrace/` 아래 revision별 경로다. 전체 snapshot이나 MRI ZIP은 받지 않는다. 토큰이 필요하면 승인된 HF_TOKEN_PATH만 사용하고 내용을 출력하지 않는다.

공개 SHA256과 다운로드 byte를 대조한다. 다른 revision의 파일이면 차이를 기록하고 두 버전을 섞지 않는다. 명시적 네트워크/다운로드 오류의 한정 복구 후에도 실패하면 접근 미해결로 종료한다. 시스템 DNS·드라이버·기본 환경을 변경하지 않는다.

## 2. 가능성 확인

L2.4 전체 행에 대해 다음 항목을 기계 집계한다: item/환자/study 수, track, sequence 조합, 정답 분포, slice 규칙, 원 rubric의 정답 출처, 누락 필드. 환자·study 연결은 cohort와 로컬 MR-RATE splits의 명시 ID로만 한다. 익명 ID 사이의 대응을 추측하지 않는다.

각 고유 질문·rubric 구조별 대표 원 행과 반대 사례를 기록한다. 대상이 명시됐는지, sequence별 신호가 원 정답에 실제로 있는지, 선택지의 결합이 결정적인지, series·공간·slice 연결이 보장되는지 각각 별도 판정한다. 같은 study라는 사실만으로 같은 병변의 관측이 보장됐다고 하지 않는다.

공식 test의 정답을 읽은 범위를 기록한다. 이번에는 test를 개발 자료로 전환하지 않는다. MR-RATE train/validation과 겹치는 경우에도 BrainTRACE test 독립성이 자동 유지된다고 하지 않는다. 별도 개발 구성이 가능하다는 주장은 실제 공개 규칙과 ID 근거가 있을 때만 제시한다.

## 3. 규모 확대

이번에는 없다. 새 MRI·coreg 다운로드, 전체 renderer 실행, 모델 설치·생성·학습을 발주하지 않는다. 자료 조건이 확인되면 후속 GPU diagnostic에서 기술4–8명과 탐색 약40–60명의 적격 가능 수·class 구성·필요 byte를 제안하되, 이번 검사에서 수를 맞추기 위해 의미 기준을 완화하지 않는다.

## 4. 독립 확인

이번 결과는 자료 적합성 판단이다. 원 행과 join 집계는 독립 검산한다. 모델 효과의 독립 확인은 미실행으로 남긴다.

## 자원과 재개

공개 저장소 목록상 약3.85MB 중 필요한 metadata만 확보한다. CPU-only의 실제 blocker는 L2.4 정답·대상·관측 연결의 미확인이다. GPU 실험 진입에는 이 연결과 공정한 대조를 고정한 후속 계획이 필요하다. 이번 GPU 메모리·학습량·요청 수는0이다.

다운로드·검사 wall-clock을 실측하며 임의 시간 상한은 두지 않는다. revision·파일 hash·완료 단계 manifest로 재개하고 기존 결과를 덮어쓰지 않는다. 후속 GPU 계획에서는 두 GPU의 실여유와 worker당2GB 여유, batch 확대 또는 복수 worker 처리량 비교를 실제 입력으로 정해야 한다. iter_129의 처리량을 새 sequence 입력의 실측으로 복사하지 않는다.

# Implementation Tasks for Claude

현재 구현 담당 Codex에도 같은 지시를 적용한다.

1. 공식 파일만 확보하고 revision·SHA·라이선스·출처를 기록한다.
2. L2.4 원 행 추출과 cohort/splits 연결을 재현 가능한 작은 검사로 구현한다.
3. sequence별 정답, 대상 동일성, 실제 관측 연결, 개발/확인 분리의 네 판단표를 만든다. 미확인은 미확인으로 남긴다.
4. 대표 사례와 탈락 사유를 원 item ID에 연결한다. 다른 유형을 새 후보로 자동 탐색하지 않는다.
5. `research/results/iter_130/`에 결과와 자체 검증을 남기고, 단일 비교 제안 또는 보류로 보고서를 끝낸다. 소스는 research에 두며 커밋은 orchestrator가 관리한다.

# Evaluation (성공/실패 기준 포함)

- 양성 자료 결과: 추측 없는 sequence별 정답 분해, 동일 대상 연결, 접근 가능한 관측 경로, 환자 분리, 공정한 단순 대조가 실제 행으로 성립한다. 이는 후속 diagnostic 설계의 근거이지 모델 한계·신규 기여·method 승인으로 해석하지 않는다.
- 음성 자료 결과: 분해 불가능한 bucket, 대상 불명확, report와 제공 관측의 연결 부재 등 핵심 조건이 충족되지 않는다. 현재 L2.4 비교 설계를 보류한다.
- 불확정: 원자료 접근이나 ID 연결을 해결하지 못한다. 오류와 필요한 외부 변화만 기록하고 후보를 보류한다. 동일 준비 iteration을 반복하지 않는다.

이번은 모델 실험이 아니므로 `valid_experiment=true`의 근거로 사용하지 않는다. GPU 실행 여부로 setup의 적합성을 포장하지 않는다. 비용 대비 가치는1.58MB 원자료 검사가 불필요한 MRI 반입·모델 실행을 막는 데 있으며, 확인되지 않은 연구 유망성은 주장하지 않는다.

# Risks / Checks

원자료 존재와 실제 영상 정답 적합성을 구분한다. 중앙 slice에서 대상이 안 보일 가능성을 낮은 모델 성능으로 오인하지 않는다. 공식 benchmark test와 MR-RATE split의 역할을 혼동하지 않는다. 접근 제한은 과학적 반증이 아니다. 보고서 정답·파일명·rubric을 향후 모델 입력에 누설하지 않는다. 기존 T2/FLAIR 결과와 보류 연구는 수정하지 않는다.

## 대규모 GPU 필요 후보

MRI volume encoder와 언어 모델의 multi-sequence 공동 정렬은 장기 후보로 유지한다. 현재 자료 조건과 개별 인식도 미확인이므로 필요한 해결책이라고 단정하거나 학습을 발주하지 않는다.

# 계획의 근거 (GPT 조사 노트)

## 새로 확인한 것

`agent/runs/iter_130/think/round_01.json` 원문과 `agent/runs/iter_129/review.md`, `agent/GOAL.md`를 읽었다. 현재 브랜치의 관련 파일 목록과 깨끗한 working tree를 확인했다. 기존 정규화 비교의 유효한 음성과 frozen T2 설계 종료를 유지한다.

[공식 parquet 파일 페이지](https://huggingface.co/datasets/lanqz7766/BrainTRACE/blob/main/data/test.parquet)에서 `data/test.parquet`, 크기1.58MB, SHA256 `9fb3d82729f4de24e3b9f794496c4bcc50edf45ce9ed0b7f2b9b23c0c731d737`을 확인했다. [cohort 목록](https://huggingface.co/datasets/lanqz7766/BrainTRACE/tree/main/cohort)에는 환자1,778명 CSV와 study7,299개 CSV가 있다. 실제 L2.4 행과 MR-RATE split 연결은 아직 읽지 못했다.

[공식 renderer](https://raw.githubusercontent.com/lanqz7766/BrainTRACE/main/reproduction/render_images.py)의 `find_nifti`는 coreg 경로의 modality·plane 조건에 맞는 파일을 정렬 후 선택한다. 일반 slice 경로는 지정 index가 없으면 중앙 index를 사용한다. 따라서 renderer 존재만으로 병변 대상이 해당 slice에 보인다고 보장되지 않는다. 이는 코드 해석이며 실제 L2.4 입력의 부적합 판정은 아니다.

[공식 taxonomy](https://raw.githubusercontent.com/lanqz7766/BrainTRACE/main/docs/TAXONOMY.md)는 L2.4를 bucketed MCQ로 명시한다. sequence별 독립 정답이 있다는 뜻은 아니다. [공식 scoring](https://github.com/lanqz7766/BrainTRACE/blob/main/docs/SCORING.md)은 closed-form의 결정적 채점을 제공하지만, 채점 가능성과 영상 정답의 적합성은 별개다.

## 직전 질문의 답

1. 동일 대상·sequence별 정답 보장: 미확인이다. 실제 행 없이 공동/독립 비교를 확정할 수 없다.
2. 개발/test 분리: 배포 test를 개발에 사용하는 결정은 하지 않는다. study UID와 로컬 MR-RATE split을 연결하고 환자 단위 중복을 확인해야 한다. 이 자료에서 본 내용을 독립 확인 근거로 사용할 수 있는 범위도 별도 기록한다.
3. 단순 대조 이후의 잔여 가치: 아직 증거가 없다. 정답의 결정적 분해와 동일 영상 비교가 성립할 때만 실제 출력 진단을 검토한다.

## 접근 제한과 판단

Data Studio 기본 화면은 열렸지만 L2.4 검색·행 지정 조회는 실패했다. 공식 parquet를 파일 저장 없이 메모리에서 읽는 요청도 `Temporary failure in name resolution`으로 실패했다. 다운로드·파일 생성·모델 실행은 하지 않았다. 원 행을 확인했다고 보고하지 않는다.

현재 모델 진단 후보는 보류한다. 대신 정확한 공개 파일 하나를 구현 환경에서 확보하는 한정 setup을 선택한다. 이는 새로운 한계 관찰이나 유효한 모델 실험이 아니다. 이 경로도 실패하면 같은 준비 반복 없이 후보를 보류한다.

이전 사고 라운드 노트: agent/runs/iter_130/think/
