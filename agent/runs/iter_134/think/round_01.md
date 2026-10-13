# 사고 라운드 1

# 새로 확인한 것

이번 라운드에서는 비교 구조를 좁혔지만, 공개 정답이 지지하는 질문 하나를 아직 확정하지 않았다. 구체적인 미확인 사항은 병변 위치 정답의 slice별 연결과, 병변 존재 질문에서 기존 전문 대안 이후 남는 정보 가치다.

## 원 실험이 실제로 말하는 범위

- `agent/GOAL.md`, `agent/runs/iter_064/review.md`, `agent/runs/iter_070/review.md`, `agent/runs/iter_133/review.md`를 직접 읽었다.
- iter_064의 MedGemma BA는 단독 0.80208, 복제 0.77083, 반대 annotation 상태 slice 추가 0.50000이었다. Qwen에서는 같은 손실이 없었다. 명시적 target index 과제이므로 상보적 관측의 전체 판독 이득에 대한 반증이 아니다. 원 리뷰도 이를 명시한다.
- iter_070의 AutoRG P/G BA는 모두 0.613636이며 mask Dice 평균은 0.920396이다. 높은 중첩과 보고서 대상·release 연결 불확실성 때문에 위치 지원 일반 효과는 미판정이다.
- iter_133은 첫 줄 HIGH 45/45지만 일부 설명은 high와 low를 함께 기술했다. 영상 조건의 비EOS는 14/30이다. 원 판정은 보존하며 혼합 신호 인식 실패로 해석하지 않는다.
- `agent/LIMITATIONS.md`의 두 관련 항목에서 evidence·usage_checks·remaining_questions를 확인했다. 두 항목 모두 observed이며 이번에 상태를 변경하지 않는다.

## 로컬 자료의 실제 schema와 규모

`research/results/iter_070/data/radgenome/`의 JSON을 읽기 전용으로 집계했다.

- `BraTS_GLI/global_finding.json`: case ID를 key로 하는 보고서 230건.
- `BraTS_GLI/modal_wise_finding.json`: case–sequence ID를 key로 하는 보고서 920건.
- `train_val_test_split.json`과 연결한 FLAIR case 수: train 161, val 23, test 46. 이는 case 수이며 환자 독립성 확인 전 환자 수로 쓰지 않는다.
- 로컬 FLAIR NIfTI는 기존 15개뿐이다. 독립적인 새 영상–mask 집단이 이미 확보됐다고 가정할 수 없다.
- train 보고서 첫 문장에서 `both`, `bilateral`, 또는 중선 횡단 표현이 나타나는 후보는 11건이었다. 이는 단순 검색 후보이며 양측 병변 정답 11건이 아니다. 예를 들어 `BraTS-GLI-00196-000`은 우측 전두엽과 양측 뇌량 몸통을 함께 언급해, 단순 LEFT/RIGHT/BOTH 변환에 해부학적 해석이 필요하다.
- 다른 후보에는 양측 전두엽, 양측 측두엽, 양측 뇌실주위 병변이 등장한다. 위치 집합 보존 질문의 가능성은 있지만, 서로 다른 slice가 실제로 상보적인 위치 근거를 제공하는지는 미확인이다.
- `research/results/iter_083/preflight_a1/release_evidence.json`에는 공식 설명상 BraTS2021/2023 영상 관계와 ET label 4→3 변경 근거가 보존돼 있다. 같은 파일은 mapping 다운로드 403, 개별 mirror voxel 동등성과 접근 조건 미인증도 명시한다. release 수준 설명을 개별 파일 연결 완료로 격상하지 않는다.
- 로컬 RadGenome README의 내용은 `license: mit`뿐이다. 이 문자열로 원 MRI의 이용 조건을 인증하지 않는다.

## 가까운 방법의 확인 범위

- [Vote-MI 공식 저장소](https://github.com/YuliWanghust/BrainMD)는 대표 slice 선택 코드가 `patch_vae`와 `representative_select`에 있음을 명시한다. 공개 안내의 실행 예시는 Med-Flamingo 기반이며 전체 BrainMD에는 별도 data user agreement가 필요하다. 따라서 공개 예제와 전체 자료 접근을 구분해야 한다.
- [공식 Patch VAE 안내](https://raw.githubusercontent.com/YuliWanghust/BrainMD/main/patch_vae/README.md)는 일반 VAE 학습 환경·설정을 제공한다. 이 문서만으로 BraTS용 즉시 실행 가능한 pretrained 선택기가 확인된 것은 아니다. `representative_select` 상세 페이지 조회는 실패했으며 실제 지원 입력·checkpoint·선택 비용은 남은 확인 사항이다.
- [AutoRG-Brain 공식 구현](https://github.com/ljy19970415/AutoRG-Brain)은 NIfTI와 modality를 입력받고 `label`에 anomaly mask를 제공할 수 있다. RadGenome 비교에서는 `given_mask`와 `modal_wise_finding.json`을 사용한다. RGv2는 RadGenome 사전학습 모델이므로 공식 train의 새 사례라도 미노출 대조로 부를 수 없다. 공식 지원 modality에 T2FLAIR가 포함된다.
- 이 문헌들은 조사 근거이며 사용자 논문 추천은 아니다. 이번 라운드에는 새로운 실제 실험 근거가 없다.

## 재사용 확인

- 현재 `research/`의 `git status --short` 출력은 비어 있었다. `git ls-files`에서 i133 파일들의 현재 존재를 확인했다.
- `agent/CODE_ASSETS.md`의 iter_133 항목과 원 `review.json/code_assets`를 읽었다. 승인된 렌더링은 기존 15사례 조건에 한정된다.
- `i133_data.py`를 읽어 `seg>0`, canonical RAS, GT 양성 z 범위의 8장 선택, volume min–max 사용을 확인했다. 이 코드는 보고서의 신호 ROI나 임상 반구 침범을 인증하지 않는다.
- `i133_common.py`는 iter_070 자료와 iter_133 결과 경로를 고정한다. 그대로 새 과제에 연결하면 안 된다.
- 추론 경로는 worker 직접 진입의 inputs hash 검사, EOS gate, 시작 직전 GPU 여유와 비용 계측 보완이 필요하다. 기존 evaluator의 HIGH/MIXED 규칙은 새 질문에 재사용하지 않는다.
- 이번에는 구현 과제가 미확정이므로 선별 반입을 요청하지 않는다. 최종 계획에서 실제 기반과 필요한 파일·의존성을 확인해 지정한다.

# Strategy Check / 연구 방향 판단

1. 중요한 문제: 추가 관측으로 확보한 병변 정보가 최종 답에 보존되는지 알아야 slice 선택과 통합 중 어디에 투자할지 정할 수 있다.
2. 현재 근거: iter_064의 지정 target 손실과 iter_133의 범주·절단 문제를 계승한다. 새 근거는 실제 보고서 schema, train의 위치 후보 11건, 신규 로컬 영상 부재다.
3. 쉬운 해결책: 개별 판독 후 고정 통합, 대표 slice 선택, 전문 segmentation+규칙이다. 이들 이후 남는 부족함이 있어야 새 방법 투자가 가능하다.
4. 남은 설명: 관측 부족, 단일 관측 기본 인식 부족, 공동 입력 손실, 정답 대상 불일치다. 같은 영상 집합의 개별/공동 비교는 앞의 두 요인과 공동 처리 효과를 나누는 데 필요하다.
5. 다음 결정: 위치 집합 질문의 정답 연결 가능성과 존재 질문의 기존 대안 이후 가치를 비교해 한 후보만 확정한다. 데이터가 편리하다는 이유로 단순 위치 분류를 선택하지 않는다.

# 대안 비교와 남은 판단

우선순위는 동일 관측 집합의 개별 통합/공동 입력이다. 단일 대표 영상은 관측 추가 효과를 해석하는 기준으로 포함할 수 있다. 양측 위치 집합은 단일 장에서 빠진 정보를 확인하기 좋을 수 있지만 실제 상보적 사례와 정답 관계가 아직 없다. 병변 존재는 mask로 더 직접 정의할 수 있으나 iter_059의 구간 판정과 전문 OR 대조를 반복할 위험이 있다. 해당 원 리뷰를 확인해 동일 정보량에서 아직 검증하지 않은 중요한 차이가 있는지 판단해야 한다.

다음 라운드는 문구 다듬기나 같은 문헌의 전수 재조사가 아니다. 위치 후보의 정답 성립과 기존 존재 과제 대비 정보 이득이라는 두 선택 근거를 확인한다. 실제 영상 확인이 필요한 부분은 구현의 한정 자료 확인으로 넘길 수 있지만, 질문 자체와 조건부 실행 기준은 먼저 고정해야 한다.

## 대규모 GPU 필요 후보

3D encoder와 언어 모델의 공동 적응은 관측 보존 문제의 후보로만 유지한다. 현재는 원인과 새 방법 필요성이 미확인이고, 두 24GB GPU에서의 경량 대조도 설계 전이므로 실행하지 않는다.

## 다음에 파고들 질문
- RadGenome의 위치 후보에서 보고서가 지정한 병변과 mask의 의미를 임상 추측 없이 연결할 수 있는가? 공식 데이터 설명·mapping과 후보 원문을 확인해 위치 집합 질문을 채택하거나 보류한다.
- iter_059 원 리뷰·계획에서 전문 segmentation+OR가 해결한 범위와 동일 정보량의 미검증 범위는 무엇인가? 존재 질문을 택할 경우 기존 구간 판정을 반복하지 않는 최소 비교와 잔여 가치를 명시한다.
- 선택한 질문에서 Vote-MI의 실제 입력·checkpoint·선택 비용이 직접 대조에 필요한가, 아니면 동일 영상 집합의 고정 통합만으로 첫 투자 판단이 가능한가? 공식 representative_select 구현의 필요한 경로만 확인한다.
