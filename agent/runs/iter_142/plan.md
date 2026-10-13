# 요약

- 이번에 할 일: 기존 DWI 기술 2명·개발 6명에서 AutoRG의 예측 영역 기반 판독을 실행한다.
- 필요한 이유: frozen MedGemma의 개별·인접 비교는 불확정이다. 전문 시스템이 같은 소견을 회복하는지 확인해야 적응 이후의 잔여 문제를 정할 수 있다.
- 확인할 기준: 공개 DWI 항목 회복, 명시 모순, 미판정·절단, 학습 노출 및 실제 처리 비용을 함께 비교한다.
- 주의·다음: 개발 사례 비교이며 3D 구조 효과나 독립 일반화를 증명하지 않는다. 기존 MedGemma 출력은 보존하고 whole-sequence supervision의 SFT 설계로 연결한다.

## 알림 맥락

- 연구: MRI 동일 관측 범위의 판독 대조
- 데이터: 뇌졸중 DWI MRI, RadGenome ISLES22와 공식 ISLES2022 원영상
- 모델: 기존 frozen MedGemma 1.5 출력과 AutoRG-Brain RGv2·예측 segmentation
- 과제: 같은 DWI 검사 범위에서 소견·위치·신호 설명을 생성한다
- 가설: 전문 영역 판독 시스템은 현재 MedGemma가 놓친 공개 소견을 회복할 수 있다
- 질문: 같은 MRI를 본 전문 3D 시스템은 소견 누락을 줄이는가?
- 변경: 이어감
- 연결: iter_141의 인접 처리 우열은 절단·미판정으로 불확정이어서 기존 전문 대안의 실제 해결 범위를 확인한다
- 작업: AutoRG 판독을 한 번 비교하고 입력별 SFT의 학습 단위와 다음 투자 기준을 정한다

# Current Understanding

iter_141의 실제 463요청과 원 판정은 유지한다. 6명의 환자 평균 항목 일치율은 개별 45.65%, 인접 34.25%지만 차이 범위는 −46.39~+54.35pp다. 이 결과는 인접 처리의 확정적 열위나 MRI 인식 실패가 아니다.

현재 정답은 같은 patient/session의 global 문장에 명시된 DWI 소견이다. ADC 저신호·병인·시기를 DWI 정답으로 옮기지 않는다. 원영상 연결과 mask 기하는 기존 검증을 계승하며 새 실행에 필요한 hash·입력 연결만 확인한다.

유지: RadGenome 중심, 동일 판독 범위, 기본 모델→입력별 적응→전문 3D 비교의 연결, Codex 구현과 독립 리뷰.
보류: iter_139 MSD 유무 LoRA, iter_138 인터페이스 실험, BraTS 접근 재감사.
변경: 새 생성은 AutoRG 예측 영역 경로에만 추가한다. iter_141 재생성·재채점은 없다.
미완료: 입력별 SFT, 적응 후 잔여 오류, 독립 환자 확인.

# Strategy Check / 연구 방향 판단

직전 카드 출처는 `agent/runs/iter_141/review.json`이다. 같은 `mri-volume-evidence-use` 질문과 현재 branch를 유지한다.

1. 중요한 문제: 같은 관측과 학습 자료에서 공간적으로 묶어 처리하는 방식이 소견 누락·위치 오류를 줄이는가?
2. 현재 근거: 실제 MedGemma 비교는 완료됐으나 반복·절단이 커 우열은 불확정이다. AutoRG 공식 DWI 입력 경로와 기존 실행 자산은 확인했다.
3. 쉬운 해결책: 전문 segmentation·영역 판독·규칙 후처리 시스템이 충분할 수 있다. 실제 해결 범위를 먼저 확인한다.
4. 남은 설명: 기본 과제 적응 부족, 출력 반복, 영역 추출 부족, 공간 통합 효과가 남는다. 이번에는 전문 시스템의 해결 가능성만 구분한다.
5. 다음 결정: 전문 대안 회복 여부와 잔여 오류를 근거로 직접 SFT pilot의 목표를 정한다. 같은 frozen prompt 순회는 종료한다.

SFT를 바로 시작하는 대안은 중요하지만 현재 whole-sequence 정답을 개별 slice/구간에 잘못 배분할 위험이 있다. 기존 전문 모델 한 조건의 실제 비교가 더 작은 비용으로 다음 baseline을 정한다. 이 선택은 SFT 취소나 무기한 자료 준비를 뜻하지 않는다.

# Hypothesis

H1: 예측 mask와 공식 판독 경로를 갖춘 AutoRG가 공개 DWI 소견을 회복하면, 현재 MedGemma 결과는 자료 자체의 판독 불가능성만으로 설명되지 않는다.

H2: AutoRG도 회복하지 못하면 현재 checkpoint의 DWI target 적합성, 영역 예측, 텍스트 대응이 경쟁 설명으로 남는다. 이를 MRI 시스템 전체의 실패로 합치지 않는다.

AutoRG의 학습과 후처리가 MedGemma와 다르므로 H1 양성도 3D 구조의 인과 효과가 아니다. 공식 후처리 전후 기록은 시스템 효과의 출처를 설명하기 위한 분석이며 별도 최적화 조건이 아니다.

# Limitation Evidence / Correct Usage Checks

대상은 observed `radgenome-dwi-adjacent-report-output`이다. iter_141 full review는 valid_experiment=true, blocking 없음이다. 공식 tensor, 입력 hash, 요청 완결성 및 원문 연결 검사를 계승한다. 범용 임상 평가나 방법 full 진입 근거로 확대하지 않는다.

AutoRG는 다음을 새로 확인한다.

- 기존 source SHA, checkpoint revision·실제 파일 hash와 환경 Python을 고정한다.
- DWI 입력 dispatch와 checkpoint의 report 학습 지원을 구분한다. 공식 문서·배포 설정·학습 목록이 있으면 대조하고 없으면 미확인으로 남긴다.
- 8명은 RadGenome train임을 명시한다. SEG의 ISLES2022 노출과 RGv2의 RadGenome 노출을 모델별로 기록한다. 정확한 환자별 노출을 모르면 독립 집단이라고 쓰지 않는다.
- 입력은 같은 원본 DWI, modal=DWI만 제공한다. report·label·label2 및 GT mask는 일반 입력에서 제외한다.
- 공식 region_segtool 전처리·예측 mask·빈 mask 처리·생성·후처리를 사용한다. 빈 영역이나 오류 사례를 성능을 보고 제외하지 않는다.
- 공식 후처리의 위치 삽입·좌우 수정·기본 문장 추가를 기록한다. 원시 생성과 최종 시스템 출력을 모두 보존한다.

# Contribution Path / Baselines / Reuse

이번은 diagnostic이며 학습하지 않는다. 신규 기여는 미확정이다. 전문 시스템 비교 뒤에도 중요한 오류가 남으면 같은 환자·supervision·관측을 사용하는 직접 SFT가 다음 강한 기준선이다.

주 비교는 AutoRG 최종 시스템 대 저장된 MedGemma 개별 처리다. 인접 처리 결과는 보조 비교로 함께 제시한다. 원본 volume 대 256-pixel 렌더링, 자동 영역 추출, 학습 자료와 supervision, 내부 공간 재표집 차이를 표로 기록한다. 전체 판독 범위가 같아도 동일 tensor·정보 보존량 비교는 아니다.

현재 branch의 `i141_spec.py`는 출력·평가 규약의 참고로 유지한다. `reference_locked.json`, `data_manifest.json`, `eval/judgments.json`, `eval/report.json`은 읽기 전용 기존 근거다. `i141_judge.py`의 사례별 판정표를 새 출력 평가기로 호출하지 않는다.

선별 반입은 원 SHA `02a8adade58f7cea84638f9e96bf963a0fb64d55`의 `ar70_run.py`, `ar70_patch.py`다. 외부 환경·가중치·공식 소스는 기존 결과 경로에서 읽는다. 새 runner는 반입 코드에서 필요한 로딩·기록 경로를 파생하고 FLAIR/BraTS/GT/given_mask 고정을 제거한다. 기존 launcher·parser·cost 모듈은 이번에 사용하지 않으므로 전수 복구하지 않는다.

# Proposed Experiment

## 1. 한정 지원 확인과 동작 확인

기존 기술 2명 `sub-strokecase0001`, `sub-strokecase0003`을 사용한다. 나머지 개발 6명은 기존 manifest에서 역할을 읽어 고정하며 사례를 교체하지 않는다.

기존 격리 환경 `research/results/environments/autorg70/bin/python`으로 import·CUDA·실제 DWI 한 건의 공식 경로를 확인한다. 정상 DWI dispatch가 없거나 checkpoint와 구조가 맞지 않으면 중단한다. 학습 목록 부재만으로 실행을 막지는 않으며 제한된 전이/노출 미확인 비교로 명시한다.

기술 2명에서 공식 greedy max_length=300을 사용한다. 어느 영역이든 cap에 도달하면 두 기술 사례를 600으로 한 번 확인하고 본실행 전체 길이를 600으로 고정한다. 600에서도 절단되면 숨기지 않고 미완결 평가를 적용한다. 길이·prompt·checkpoint를 추가 탐색하지 않는다.

공식 SDK 직접 호출과 새 wrapper의 같은 입력에서 전처리 tensor·token·최종 보고서 일치를 확인한다. 허용된 호환 patch 외 알고리즘 변경은 하지 않는다. 관측용 hook이 출력 token을 바꾸지 않는지 검사한다.

## 2. 가능성 탐색: 실제 개발 비교

고정 6명 각각에 원본 DWI→예측 병변/해부학 mask→region_segtool 보고서를 한 번 실행한다. GT mask는 사용하지 않는다. seed는 공식 SDK의 42를 유지하고 checkpoint·생성 설정을 잠근다.

저장 항목은 입력 SHA, 예측 mask와 geometry, 영역별 원시 token·EOS·문장·영역 연결, 최종 후처리 보고서, 처리 시간·메모리·오류다. segmentation과 generation을 포함한 end-to-end 경계를 계측한다. 사전에 정한 6명 전원을 분모로 유지하며 실패·빈 출력·미완결을 따로 보고한다.

## 3. 후속 입력별 SFT의 학습 단위

이번에는 학습·새 모델 forward를 실행하지 않는다. 기존 공개 보고서 schema를 근거로 다음 계약을 결과 문서에 명시한다.

- 한 학습 예제는 환자/session의 전체 DWI 관측과 그 범위에 명시적으로 대응하는 DWI 소견 target이다.
- 개별 slice와 인접 묶음은 같은 slice 집합을 분할하는 방식만 다르게 한다. 전체 target은 모든 관측이 합쳐지는 sequence 단계에 한 번만 부여한다.
- 지역별 정답 연결이 없는 한 slice/구간 출력에 전체 보고서 loss를 반복 부여하지 않는다. mask로 임의 속성·정상 판정을 만들지 않는다.
- 실현 후보는 개별/인접 시각 표현을 동일 sequence decoder에 통합하고 같은 target으로 직접 CE SFT하는 방식이다. 기존 2단계 텍스트 통합을 사용한다면 국소 생성기 자체가 적응된 비교가 아님을 명시한다.
- 다음 method pilot에는 sequence 수준 입력 구현·메모리 확인, 같은 train/validation 환자·시각 해상도·LoRA 범위·target 노출, 환자당 가중치, 생성 평가 일정이 필요하다. 본 반복의 8명은 개발 이력으로 유지한다.
- 구현자가 구간 정답을 추측하거나 새 학습 구조를 임의 선택해 학습을 시작하지 않는다. 실행 가능한 단위와 아직 필요한 설계 선택을 하나로 좁혀 다음 계획에 전달한다.

## 4. 규모 확대와 독립 확인

이번에는 6명 이상으로 자동 확대하지 않는다. 이는 이미 연결된 저장 비교에 전문 시스템 한 조건을 추가하는 결정 범위다. 독립 효과 크기를 추정할 표본 수가 아니다.

AutoRG 회복이 관찰돼도 다음 단계는 직접 SFT pilot의 별도 계획이다. full 개발·다중 seed·독립 test는 적응 가능성과 잔여 오류를 확인한 후 결정한다. 학습 노출이 없는 독립 검증이 필요하면 환자 split과 checkpoint 노출을 먼저 구분하고 정밀도에 맞춰 규모를 정한다.

## 자원·처리량·재개

실행 직전 nvidia-smi로 허용 GPU 0,1의 실제 여유를 확인한다. 초기 독립 사례를 두 GPU에 분산하고 논리·물리 대응을 남긴다. AutoRG의 실제 peak는 새 DWI 입력에서 측정하며 MedGemma의 8~10GB 수치를 대신 쓰지 않는다.

기술 사례에서 GPU당 worker 1개와, 안전 여유가 있으면 2개 구성을 비교한다. 전체 환자/분, peak VRAM, CPU·RAM·I/O 경합, 긴 생성 지연과 출력 정합성을 본다. 두 번째 구성이 안전하지 않거나 기술 비교 비용이 남은 6명에서 절약할 비용보다 크면 실측 근거로 기존 구성을 선택한다. 모든 worker의 peak와 기존 점유를 합하고 worker당 2GB 여유를 둔다.

예상 시간은 기술 2명의 loading·전처리·segmentation·영역별 생성 실측으로 산출한다. 과거 FLAIR launcher 211.6초는 경계가 달라 DWI 예상 시간으로 복사하지 않는다. 임의 device-minute 상한을 두지 않는다.

새 결과는 `research/results/iter_142/`에 저장한다. 작업 ID는 환자·설정 hash로 고정하고 원자적 claim, worker별 출력, 종료 상태, 중복·누락 검사를 갖춘다. 재개는 입력·설정·소스·가중치 hash가 일치하는 성공 결과만 건너뛴다. 오류나 손상 결과를 완료로 간주하지 않는다. 기존 파일과 다른 사용자 프로세스를 변경하지 않는다.

# Implementation Tasks for Claude

실제 담당은 Codex이며 호환용 제목이다.

1. 반입 파일과 원 review의 needs_fix 범위를 확인하고 새 결과 경로·DWI·region_segtool로 필요한 부분만 파생한다.
2. 외부 소스·checkpoint·환경·입력 manifest를 연결하고 출처·학습 노출 표를 작성한다. 기존 가중치와 hf_cache는 수정하지 않는다.
3. GT·report 비입력, 공식 SDK 대조, 실제 tensor·생성 기록, 재개·중복·오류 거부를 검사한다.
4. 기술 2명에서 길이와 병렬 구성을 고정한 뒤 개발 6명을 실행한다.
5. 새 AutoRG 출력의 항목 판정과 인용문을 별도 저장하고 기존 MedGemma 판정과 비교한다. 원시 출력·사전 규약·집계 코드와 독립 재계산 자료를 보존한다.
6. whole-sequence SFT 계약과 다음 pilot에 필요한 단일 설계 선택을 보고한다. 이번에는 학습하지 않는다.
7. 실행 완료/미완료, 실제 비용, 미해결 reuse 문제와 종료 행동을 보고한다. 소스 checkpoint는 orchestrator가 보존한다.

# Evaluation (성공/실패 기준 포함)

주 metric은 기존 공개 DWI positive atom에 대한 환자 평균 명확한 일치율이다. finding·signal·location·morphology/distribution을 분리 보고한다. 명시 reference contradiction, 내부 모순, report_unverified 추가 소견, unknown·unmentioned·unresolved 및 절단을 별도 집계한다. 미언급 추가 소견을 임상 허위로 부르지 않는다.

새 출력의 의미 대응은 원문 quote와 span을 남기는 제한적 텍스트 판정이다. LLM의 임상 추론·합의로 정답을 추가하지 않는다. 각 atom은 matched/contradicted/unmentioned/unresolved로 기록한다. 완결되지 않은 출력은 확인된 문장과 미확정 잔여를 나누고 recall·모순의 보수적 범위를 산출한다. 절단된 내용까지 모순이 없다고 가정하지 않는다.

기존 MedGemma의 판정표·불확실성 범위는 그대로 읽는다. 주 차이는 AutoRG−개별 MedGemma이고 인접 조건과의 차이는 보조다. 환자별 결과와 6명 paired bootstrap 95% 구간을 제시하되 작은 표본과 의미 판정 불확실성을 숨기지 않는다. 통계 구간이 의미 불확실성을 제거하지 않는다.

- 양성: AutoRG−개별의 보수적 recall 이득이 5pp 이상이고 모순 환자율 증가의 최악 범위가 5pp 이하이면 개발 사례의 회복 근거다. location만의 변화, 공식 후처리 전후 변화와 환자별 편중을 함께 보고한다. 다음은 전문 대안을 고정한 입력별 SFT pilot 설계다.
- 음성: 완결된 유효 비교에서 기준 미달이면 현재 RGv2 DWI 시스템의 확대를 보류한다. 적응 전체의 실패로 일반화하지 않고 같은 checkpoint·prompt 순회를 끝낸다.
- 불확정: 미판정·절단·환자 변동이 행동을 바꾸면 불확정으로 종료한다. 새 출력의 연결 결함만 한 번 보완할 수 있다. 기존 141 재채점은 하지 않는다.
- 실행 실패: 공식 경로 불성립·입력 오류·환경 장애로 실제 비교가 성립하지 않으면 가설을 판단하지 않는다. 확인한 오류와 승인 범위 내 복구 시도, 남은 blocker를 보고한다.

5pp는 현재 트랙의 최소 관심 효과를 계승한 탐색 투자 기준이며 임상 유효성 기준이 아니다. 비용은 AutoRG의 실제 end-to-end 값을 보고하되 기존 MedGemma의 전체 비용이 없으므로 비용 우위 비율을 확정하지 않는다.

# Risks / Checks

- 개발 6명의 학습 노출 가능성이 높다. 좋은 점수만으로 실제 일반화나 공정한 모델 순위를 주장하지 않는다.
- 공식 DWI 입력 지원과 DWI 보고서 학습 지원은 다르다. 지원 불확실성을 반드시 별도 표기한다.
- region_segtool의 위치 삽입·좌우 수정·기본 문장 추가는 시스템 구성요소다. 최종 성능을 생성 모델 단독 능력으로 쓰지 않는다.
- 원 보고서는 병변 설명 중심이며 완전한 정상/비정상 목록이 아니다. 임상 허위 소견률은 현재 정답만으로 완전히 평가할 수 없다.
- 기존 GT mask는 입력에 넣지 않는다. 이번에 oracle을 추가하면 비교 조건이 달라지므로 자동 실행하지 않는다.
- 기존 사례의 결과를 보고 제외·교체하거나 metric·성공 기준을 바꾸지 않는다.
- 환경 문제가 생기면 승인된 격리 환경에서 필요한 호환 수정만 하고 기본 환경·기존 환경을 제자리 변경하지 않는다.

## 대규모 GPU 필요 후보

전체 volume의 고해상도 시각 표현과 언어 decoder를 공동 적응하는 3D report 모델은 향후 후보로 보존한다. 현재 두 GPU에서는 activation·sequence 길이·학습량 부담이 크며, 직접 경량 적응 이후 중요한 잔여 오류가 확인되기 전에는 개발하지 않는다.

# 계획의 근거 (GPT 조사 노트)

## 새로 확인한 것

- `agent/runs/iter_141/review.json`, 관련 LIMITATIONS 항목과 CODE_ASSETS를 읽었다. 유효한 개발 비교이며 blocking은 없다. 개별/인접 recall은 0.45655/0.34246, 비EOS는 2/385와 32/78이다. 우열은 불확정이고 기존 출력 재실행·반복 재채점은 금지한다.
- `agent/runs/iter_070/review.json`의 자산 판정과 원 commit의 `ar70_run.py`, `ar70_patch.py`를 확인했다. 기존 실행기는 FLAIR·BraTS 경로에 고정되고 GT mask를 생성하며 given_mask를 사용한다. 단순 modal 변경만으로 이번 실용 비교에 사용할 수 없다.
- 현재 research HEAD는 `19946deb6cccb3693713c1fb609b3cd3faec9dee`다. ar70 파일은 현재 tree에 없고 원 commit은 존재한다. 현재 i141 파일은 유지하며 필요한 ar70 두 파일만 반입한다.
- 기존 환경 `research/results/environments/autorg70/bin/python`, 모델 `research/results/iter_070/models/`, 공식 소스 `research/results/iter_070/external/src/AutoRG-Brain-9670703c88e8f599c0c7edc472a5ffce4dd72b0e/`가 존재한다. weights manifest의 모델 revision은 `da4ea5cb1058f66c370fab2e174af9c020fb0428`다. 실제 대형 가중치 hash 검사는 구현 단계에서 한다.
- [AutoRG 공식 저장소](https://github.com/ljy19970415/AutoRG-Brain)는 DWI 입력과 mask 없는 region_segtool 실행을 지원하고, SEG의 ISLES2022 및 RGv2의 RadGenome 학습을 명시한다. 다만 DWI 입력 지원과 해당 checkpoint의 실제 DWI 보고서 target 학습은 같은 사실이 아니다.
- 로컬 공식 SDK는 region_segtool에서 해부학 명칭 삽입, 좌우 문자열 수정, 일부 전역 문장 합성 및 기본 midline 문장 추가를 수행한다. 따라서 최종 보고서의 위치 정확도를 순수 생성 모델 능력으로 해석할 수 없다. 후처리 전후 출력 보존이 필요하다.
- `i141_data.py`와 `reference_locked.json` 연결 규약상 DWI modal key는 없고 global 문장의 명시 DWI 절만 사용한다. 정답 단위는 whole sequence이며 slice/구간 supervision은 확인되지 않았다.

## 의미와 남은 확인

현재 6명은 독립 test가 아니다. AutoRG의 성공은 학습 노출 가능성이 있는 개발 사례에서 시스템이 공개 소견을 회복한다는 근거이며, 실패도 DWI report 학습 지원을 고려해야 한다. 공식 checkpoint별 학습 목록이 없으면 unknown을 남기되 정상 DWI 실행 자체를 막는 사유로 삼지 않는다. 공개 학습 파일의 로컬 raw_data 디렉터리는 확인되지 않았으므로 공식 checkpoint 설명과 배포된 설정만 한정 조사한다.

이번에는 강한 시스템 비교를 실제 수행한다. SFT는 whole-sequence 단위의 설계 계약까지 연결하고 학습하지 않는다. 개별 slice에 global report를 복제하는 학습은 승인하지 않는다.
