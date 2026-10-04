# 사고 라운드 1

## 핵심 판단

현재 MRI 결과만으로 새 결합 loss를 개발하는 것은 정당화되지 않는다. 다음 투자 우선순위를 **MRI 전문 모델을 통한 근거 인식 확보 가능성 확인**으로 좁혔다. 다만 AutoRG-Brain의 실제 annotation·원본 volume 연결과 공정한 대조 경로가 아직 확인되지 않아 구현 계획은 확정하지 않는다. 다음 라운드는 이 후보의 적합성만 판단하며 광범위한 방향 조사를 반복하지 않는다.

## 원본 기록에서 확인한 사실

- `agent/GOAL.md`, `agent/INDEX.md`, iter_061~065·068·069의 원 리뷰, iter_059의 review.json, iter_064/069 계획과 관련 자산 기록을 확인했다.
- iter_069: 두 모델 모두 ADC SA에서 LOW 20/20, BA 0.50이다. 일부 대상–성분 연결 문제도 있어 순수한 ADC 인식 결함으로 등록하지 않았다. 현재 후보 종료에는 blocker가 없다.
- iter_064: MedGemma S/R/C BA는 0.80208/0.77083/0.50000이다. R−C는 0.27083, 95% CI [0.20313, 0.33854]지만 S specificity는 30/48로 원 기준에 미달했다. Qwen에서는 동일 손실이 없었다. 중요한 관찰이지만 명시적 index routing 이후 남는 방법 필요성은 확보되지 않았다.
- iter_065: 질문별 고정 정책 이득은 MedGemma 2.81 pp, Qwen 1.60 pp였다. 리뷰의 사후 위치 prior가 MedGemma 정책보다 높았고, HD 의미·전체 비용 검증도 미완결이다. 이 결과를 충분한 인식 이후의 선택 실패로 해석하지 않는다.
- iter_068: Modic 순위 AUROC 약 0.73–0.74는 남지만 D 고정 threshold의 E12 BA는 0.579/0.540이다. 같은 자료의 보정·prompt·추가 모델 탐색 종료를 유지한다.
- iter_059: 기존 전문 모델+규칙의 E48 BA 0.950과 전체 비용 비율 0.601은 해당 입력·과제에서 유효하다. 따라서 단순 segmentation으로 끝나는 과제의 VLM 적응을 다시 발주할 이유는 부족하다.
- iter_061~063: 텍스트에 포함된 소견, 삭제 후 거절·형식 변화, key-image 충분성이 얽혀 있다. 이 자료에 모델 하나를 더 추가하는 것만으로 인식·결합을 분리하기 어렵다.

## Strategy Check / 연구 방향 판단

상위 질문은 여러 관측의 필요한 근거를 선택·결합하는 능력이다. 현재 해결된 질문은 일부 고정 조건에서의 출력 차이이며, 충분한 근거 인식을 확보했다는 결론은 아니다.

1. **기존 context 손실의 최소 개입:** observed·usage checks·blocking 없음은 확인했다. 그러나 routing과 타 계열 모델이라는 단순 대안 이후의 잔여 가치가 부족하다. method pilot의 형식적 진입 가능성과 실제 투자 가치를 구분해 보류한다.
2. **기본 인식을 확보할 전문 모델·적응:** 우선한다. 먼저 공개된 MRI 전문 모델이 해당 질문에 맞는지 확인하면, 자체 적응을 시작하기 전에 강한 기존 해결책의 범위를 알 수 있다. 새 학습을 통한 인식 개선은 현재 자동 승인하지 않는다.
3. **다른 실패 조건·새 자료:** 우선순위가 낮다. iter_069는 구현 세션 약 27분에 비해 본생성 약 62초였고, iter_064도 본생성은 약 3.3분이었다. 일부 반복에서 준비·검증 비용이 컸다는 실제 기록은 있으나 track 전체 비용 비율은 계산하지 않았다. 새 benchmark 탐색보다 이미 선택한 경쟁 설명에 맞는 모델–정답 연결을 먼저 확인한다.

## 새로 확인한 공식 모델·자료 근거

### AutoRG-Brain: 우선 확인 후보

[공식 저장소](https://github.com/ljy19970415/AutoRG-Brain)는 영역별 MRI 보고서 생성과 예측 segmentation 또는 제공 mask를 이용하는 실행 경로를 제공한다. RGv1은 내부 자료와 RadGenome, RGv2는 RadGenome으로 학습했다고 명시한다. 공개 데이터 평가 예시는 GT 병변 mask를 제공하는 `given_mask` 조건이다. 따라서 이를 mask-free 실용 성능으로 읽으면 안 된다.

[RadGenome 파일 목록](https://huggingface.co/datasets/JiayuLei/RadGenome-Brain_MRI/tree/main)은 약 1.64 MB의 보고서·split 배포다. 원본 MRI volume이 이 저장소에 함께 있다고 가정할 수 없다. [BraTS_GLI 목록](https://huggingface.co/datasets/JiayuLei/RadGenome-Brain_MRI/tree/main/BraTS_GLI)에서 `modal_wise_finding.json`, `global_finding.json`, `impression.json`을 확인했다. 실제 내용은 아직 읽지 못했다. 원 자료 ID와 기존 MSD 또는 OmniBrainBench 이미지의 이름이 비슷하다는 이유로 연결하지 않는다.

[공식 checkpoint 목록](https://huggingface.co/JiayuLei/AutoRG_Brain/tree/main)은 RGv1/RGv2와 segmentation 자산을 제공한다. 전체 목록 크기 12.8 GB와 segmentation 파일 582 MB는 다운로드 자산 크기이며 실행 VRAM 추정치가 아니다.

[공식 SDK 소스](https://raw.githubusercontent.com/ljy19970415/AutoRG-Brain/master/AutoRG_Brain/inference/inferenceSdk.py)를 확인했다. `region_segtool`에는 영역명 삽입, 좌우 문자열 교정, 일부 기본 문장 추가가 있다. `given_mask`는 다른 출력 조합 경로다. 두 mode의 점수 차이는 mask만의 효과가 아니다. 순수 위치 대조를 하려면 동일한 보고서 생성·후처리 경로에서 mask 출처만 바꿀 수 있는지 확인해야 한다. 이는 출력 실험으로 검증된 모델 한계가 아니라 코드에서 발견한 설계상 주의점이다.

### 다른 전문 모델을 바로 선택하지 않은 이유

[BrainVLM 공식 저장소](https://github.com/HKU-HealthAI/BrainVLM)는 다중 sequence 뇌종양 진단·보고서 checkpoint를 제공한다. README의 입력 설명은 sequence 조합과 환자 metadata를 포함한다. 그러나 [공식 example_test.json](https://raw.githubusercontent.com/HKU-HealthAI/BrainVLM/main/example_test.json)의 두 번째 사례에는 Age/Sex가 없다. metadata가 반드시 필요하다고 단정하지 않으며, 현재 자료의 부분 slice 질문에 바로 적용 가능한 범용 QA 모델로도 간주하지 않는다.

[NeuroVFM 공식 저장소](https://github.com/MLNeurosurg/neurovfm)는 3D encoder, 진단 head, findings LLM을 제공한다. [LLM model card](https://huggingface.co/mlinslab/neurovfm-llm/blob/main/README.md)는 Qwen3-14B 기반을 설명한다. [접근 페이지](https://huggingface.co/mlinslab/neurovfm-llm)는 연락처 공유·조건 동의를 요구한다. 현재 계정의 승인 여부는 확인하지 않았고 사용자를 대신해 동의하지 않았다. 이를 설치 불가능 또는 과학적 부적합으로 판단하지 않지만, 지금 이 후보를 기다리며 연구를 멈출 이유도 없다.

## 확인 시도와 남은 제한

RadGenome의 두 JSON에 대해 web의 raw/blob 조회가 실패했다. 읽기 전용 Python URL 조회도 DNS 오류 `Temporary failure in name resolution`로 실패했다. 이는 현재 조회 경로의 오류이며 자료 부재·접근권 부재의 증거가 아니다. 다음 라운드에서 같은 실패 URL만 반복하지 않는다. 직접 확인이 안 되는 archive 내부 점검은 사용자 정책에 따라 구현 단계의 한정 자료 점검과 통과 시 실제 출력으로 묶을 수 있다. 다만 먼저 평가하려는 소견·대조·종료 결정을 구체화해야 한다.

## 한계와 코드 재사용

`agent/LIMITATIONS.md`의 `mri-explicit-target-context-effect` 원문과 iter_064의 evidence·usage_checks·remaining_questions를 확인했다. 상태는 observed로 유지한다. AutoRG의 성능 문제를 이 id로 대신 등록하거나 방법 gate를 통과시키지 않는다.

현재 research HEAD는 `76eb1036df95478f889ee6bfd8e31ca43e82b415`이며 작업 트리는 깨끗하다. `git ls-files`와 현재 `m65_run.py`, `msd56_run.py`를 확인했다. 두 backend는 있지만 전체 실행·평가 경로는 승인되지 않았다. AutoRG 전용 자산은 이번 확인에서 확보하지 않았다. 다음 선택에 필요하지 않은 dd69 대상 수정·기존 runner 정비는 발주하지 않는다. `reuse_assets`가 빈 것은 새 실험의 재사용 구성을 아직 확정하지 않았기 때문이다.

## 대규모 GPU 필요 후보

MRI 3D encoder·언어 connector·LLM을 대규모 임상 보고서로 공동 적응하는 경로는 장기 후보로 보존한다. 전문 모델이 이미 제공하는 능력과 잔여 실패를 확인하기 전에는 이 투자를 정당화하지 않는다. 현재 두 GPU에서 가능한 frozen 전문 모델, 경량 connector·LoRA 적응과 구분한다.

코드 수정·파일 생성·모델 설치·실험 실행은 하지 않았다.

## 다음에 파고들 질문
- RadGenome의 sequence별 보고서에 동일 병변의 명시적인 신호·형태 정답과 사례 간 변이가 있는가? modal_wise_finding.json과 split 원문을 확인해 sequence prior를 넘는 인식 대조가 가능한지 판단한다.
- 선택할 보고서의 원본 volume·mask·환자 또는 case ID를 공개/기승인 경로로 연결할 수 있으며, AutoRG checkpoint의 학습·validation 노출을 어느 범위까지 확인할 수 있는가? 기존 MSD·OmniBrainBench 자산은 공식 대응이 있을 때만 연결한다.
- AutoRG의 동일 생성·후처리 경로에서 예측 mask와 GT mask만 바꾸는 비교가 가능한가? 가능하면 한정 자료 점검과 GPU 출력을 묶은 계획을 확정하고, 불가능하거나 내용 정답이 부적합하면 이 후보를 종료한다.
