# 요약

- **이번에 할 일:** AutoRG-Brain RGv2에서 FLAIR 병변 신호 기술을 예측 mask P와 annotation mask G로 비교한다.
- **필요한 이유:** 기존 MRI 실험은 충분한 기본 인식을 확보하지 못했다. 새 결합 방법보다 전문 baseline의 사용 가능성을 먼저 판단한다.
- **확인할 기준:** 원본 영상·정답 연결, 동일 생성 경로, 명시적 HIGH/MIXED_HIGH_LOW 기술의 정확도와 prior 대비 이득이다.
- **주의·다음:** G는 oracle이다. 자료 적합성 통과 시 같은 호출에서 실제 GPU 출력까지 진행하되, 설치 성공이나 mask 효과를 신규 기여로 보고하지 않는다.

# Current Understanding

기준 노트는 `agent/runs/iter_070/think/round_01.json`이다. 이번 계획은 새 후보의 조건부 진단이며 과거 실험의 기준을 변경하지 않는다.

iter_069에서는 두 일반 VLM의 ADC 단독 답변이 상수였고, 일부 대상 연결도 불확실했다. iter_064의 context 손실은 유효하지만 충분한 인식을 전제로 한 선택 실패는 미확정이다. iter_059에서는 전문 segmentation+규칙이 해당 과제의 강한 대안이었다. 이 사실들은 기본 인식을 확보할 전문 모델 검토를 지지한다.

이번 라운드에서 RadGenome 보고서의 실제 FLAIR 신호 변이와 공식 val 목록을 확인했다. 원본 NIfTI·mask·checkpoint 노출 관계는 아직 확인하지 않았다. 공개 보고서와 segmentation을 같은 임상 gold로 취급하지 않는다.

# Strategy Check / 연구 방향 판단

상위 질문은 여러 관측에서 필요한 근거를 선택하고 결합하는 능력이다. 현재 해결되지 않은 선행 질문은 해당 근거를 기본적으로 읽을 수 있는가다.

- **관찰:** 일반 VLM의 고정 MRI 과제에서 기본 신호 부족이 반복됐지만 MRI 전체의 불가능성은 입증되지 않았다.
- **남은 설명:** 영역 지원 부족, 내용 판독 부족, 보고서 정답의 모호성, 모델·자료 적합성이다.
- **최소 비교:** 전문 모델의 같은 영상·출력 경로에서 예측 병변 mask와 annotation mask만 교체한다.
- **바뀔 결정:** 전문 모델을 근거 추출 baseline으로 보존할지, 영역 지원 문제만 후속 검토할지, 현재 후보를 종료할지 정한다.

기존 observed context 손실의 개입은 단순 routing 이후의 가치가 부족해 보류한다. 직접 적응은 강한 baseline을 확인한 다음 판단한다. 새 데이터셋 순회보다 이번 좁은 비교가 우선이다. 라운드 1의 전략 판단을 유지하며 전면 재조사하지 않는다.

iter_069의 본생성은 약 62초였고 준비·검증 비용이 더 컸다. 이번에는 AutoRG와 무관한 기존 runner 수정이나 범용 benchmark 구축을 하지 않는다. 전체 track의 정확한 비용 비율은 미측정이다.

# Hypothesis

H1: 전문 모델이 annotation 영역을 사용할 때 명시적인 FLAIR 신호 기술을 prior보다 잘 판독할 수 있다.

H2: H1이 성립하는 경우, 예측 영역 사용 시의 저하는 영역 지원 차이와 연결될 수 있다.

P/G 차이는 공간 범위·형태·pooling 대상의 변화를 포함한다. 순수 위치 선택의 인과 효과나 상보적 sequence 결합 실패로 해석하지 않는다. 두 조건 모두 약하면 기본 판독·정답·입력 적합성이 남으며 새 결합 loss의 근거가 되지 않는다.

# Limitation Evidence / Correct Usage Checks

이번 AutoRG 과제에는 observed/validated 한계가 아직 없으므로 `limitation_ids=[]`, `experiment_role=diagnostic`, `method_stage=none`이다. iter_064의 한계는 원 상태로 보존하고 이번 모델의 한계로 대체하지 않는다.

공식 입력·모델·정답 출처는 research_notes의 링크를 따른다. 구현 시 각 revision과 실제 파일 hash를 고정한다. 필요한 기술 검사는 다음과 같다.

- source case·sequence·보고서·mask의 일대일 연결, release 간 ID 대응과 이용 조건.
- RGv2 및 segmentation의 학습·validation 노출. 공식 val이라는 이유만으로 완전한 미노출을 주장하지 않는다.
- NIfTI shape·affine·orientation·mask label 의미와 전처리 후 tensor 연결.
- P/G의 영상 tensor·anatomy mask·생성 설정·후처리 일치.
- 추론 입력에서 정답 보고서와 평가 label 제거. SDK의 `report` 필드는 제공하지 않는다.
- 공식 코드의 자체 GPU 환경 설정이 상속된 허용 장치를 벗어나지 않도록 최소 수정하고 매핑을 기록한다.

oracle 100% 정답은 기술 gate가 아니다. G 오답은 내용 관찰로 기록한다.

# Contribution Path / Baselines / Reuse

AutoRG 자체가 영역 기반 보고서와 mask 지원을 제공하므로 P/G의 개선만으로 새 방법을 주장하지 않는다. 향후 가치 있는 실패 조건은 강한 기존 대안을 사용해도 남는 근거 사용 문제여야 한다.

비교군은 P, G, B다. B는 공식 train의 적격 FLAIR 보고서에서 정한 다수 class이며 동률이면 HIGH로 고정한다. train 영상의 새 추론은 하지 않는다. G에는 annotation 비용이 있으므로 P보다 저렴한 실용 방법으로 표시하지 않는다.

현재 브랜치의 AutoRG 전용 자산은 확인되지 않았다. 기존 `m65_run.py`, `msd56_run.py`, `dd69_*`는 이번 경로에 필요하지 않아 가져오거나 정비하지 않는다. `reuse_assets=[]`다. 구현 시작 시 선택된 기반의 파일 목록을 다시 확인하고, 동일 기능이 발견되면 원본·승인 범위·의존성을 확인해 중복 구현을 피한다. 공식 저장소는 결과 경로에 revision을 고정해 확보하고, 연구 코드에는 얇은 wrapper와 재현 설정만 둔다.

# Proposed Experiment

## 1. 자료 적합성: 모델 다운로드보다 먼저

공식 `train_val_test_split.json`과 `BraTS_GLI/modal_wise_finding.json`을 확보한다. 모집단은 현재 확인한 공식 val의 BraTS_GLI 23 case ID이며, 대상 sequence는 `t2f` 하나다. 실제 파일에서 수와 목록을 다시 검증한다. 목록이 다르면 조용히 새 모집단을 사용하지 말고 revision 차이를 보고한다.

정답은 병변 자체에 대해 명시된 두 기술이다.

- HIGH: 고신호를 명시하고 같은 병변에 저신호 성분을 기술하지 않는다.
- MIXED_HIGH_LOW: 같은 병변의 고신호와 저신호 성분을 함께 명시한다.

ISO/LOW-only, 신호 미언급, 주변 edema만의 신호, 여러 병변의 상충 기술, 참조 문구만으로 대상이 불명확한 행은 주평가에서 제외하고 이유를 남긴다. `heterogeneous`만 있는 문장은 고·저 혼합으로 자동 변환하지 않는다. 이 구분은 보고서 기술의 일치 평가이며 균질성 또는 병리 정답이 아니다.

원문 근거 span과 대상 범위를 표로 만들고 모델 출력 전에 확정한다. train에는 같은 규칙을 적용해 B를 정한다. val에서 제외율·class 분포·환자 또는 case cluster를 기록한다. 자동 추출은 보조로 사용하고 주평가 원문은 모두 확인한다.

원본 영상은 공식 출처 또는 이미 승인된 배포에서 대상 case만 확보한다. 로컬의 이름 유사 사례나 MSD를 대체 입력으로 사용하지 않는다. RadGenome 설명의 release와 실제 ID의 release가 다르면 공식 mapping 또는 동등성을 확인할 출처가 필요하다. 일부 영상만 접근 가능하면 출력 전에 가용 집단과 결측 이유를 고정하며, 전체 val의 결과처럼 보고하지 않는다.

첫 두 적격 사례에서 영상·mask·보고서의 연결을 직접 표시해 검사한다. annotation의 전체 병변 범위와 보고서의 신호 대상이 맞지 않으면 해당 행을 제외한다. 단일 mask가 임상적으로 완벽한 신호 ROI라고 가정하지 않는다.

**진입:** 실제 연결이 성립하고 두 class가 모두 있으면 조건부 출력 실험으로 진행한다. 표본이 작아도 탐색은 가능하나 정밀도에 따라 투자 판단을 제한한다. 원본 접근·대상 연결이 성립하지 않거나 한 class만 남으면 이번 인식 대조를 종료한다. test·다른 질환·다른 sequence로 자동 보충하지 않는다.

## 2. 동작 확인

격리 환경 `research/results/environments/autorg70`과 별도 모델 캐시를 사용한다. 기존 환경과 hf_cache는 수정하지 않는다. 공식 requirements·Python/PyTorch/CUDA 호환성과 디스크를 확인하고 설치 명령·버전·실패 복구를 남긴다.

RGv2와 공식 segmentation checkpoint만 준비한다. 두 class에서 ID 순으로 한 사례씩 선택해 공식 경로와 wrapper의 결과를 대조한다. 이 사례들은 개발 노출로 표시하고 전체 결과와 제외 민감도를 함께 보고한다.

공식 `given_mask`를 P/G에 공통 사용한다. 먼저 segmentation을 실행해 예측 병변 mask와 anatomy mask를 저장한다. P는 저장된 예측 병변 mask, G는 올바른 label 의미를 확인한 annotation 병변 mask를 쓴다. anatomy mask는 같은 예측본을 공유한다. 실용적 자동 경로를 재현하기 위해 P mask에 GT 기반 component 선택을 하지 않는다.

예측 mask가 비어도 사례를 제외하지 않는다. 공식 경로가 empty mask를 처리하지 못하면 P는 명시적인 무보고/누락 응답으로 기록해 주평가 오답에 포함한다. 이 경우 region_segtool의 임의 fallback 문장을 끼워 넣지 않는다.

생성은 공식 greedy 설정과 길이를 시작점으로 고정한다. cap 종료는 별도 기록하고, cap 도달 요청만 동일 규칙으로 한 번 길이를 두 배로 늘린다. 원 출력과 재시도 비용을 모두 보존한다.

## 3. 가능성 탐색과 본실행

기술 검사가 통과하면 적격 N의 고정 P/G를 모두 실행한다. 최대 N=23, 보고서 46건이다. 이는 공식 val의 작은 고정 모집단이므로 두 사례의 정확도만으로 조기 중단하거나 유리한 subset을 선택하지 않는다. 별도 학습·seed 탐색·모델 탐색은 없다.

생성 보고서는 정답과 condition을 가린 상태에서 같은 기술 규칙으로 추출한다. 미언급·상충·대상 불명확은 UNKNOWN으로 두고 주평가에서 오답으로 센다. 작은 출력 집합이므로 근거 문장과 판정을 전부 남겨 GPT 리뷰가 재검증할 수 있게 한다. 생성 결과를 본 뒤 유리한 parser를 선택하지 않는다.

## 4. 자원·비용·재개

실행 직전 nvidia-smi와 CUDA_VISIBLE_DEVICES를 확인한다. 두 GPU에 독립 case shard를 배정하고 P/G는 같은 worker에서 처리해 중간 segmentation을 공유한다. worker별 출력·임시 디렉터리를 분리한다.

AutoRG의 실제 peak VRAM은 미측정이다. MedGemma의 메모리 수치를 대신 쓰지 않는다. 기술 사례에서 한 worker의 peak와 처리량을 측정하고, 메모리가 허용하면 같은 GPU의 두 worker 구성을 짧게 비교한다. 두 worker의 peak 합계·다른 프로세스 점유·worker당 2GB 여유가 용량 안에 들어야 한다. 추가 비교 비용이 남은 최대 46건에서 절약 가능한 비용보다 크면 한 worker/GPU를 유지하고 실측 근거를 남긴다.

예상 wall-clock은 설치·다운로드 시간과 별도로 `미완료 segmentation 수/실측 segmentation 처리량 + 미완료 보고서 수/실측 생성 처리량 + 전처리·저장 시간`으로 본실행 전에 산출한다. 현재 숫자 추정치를 만들 근거는 없다. 임의 GPU 시간 상한은 두지 않는다.

case·condition별 원자적 결과와 비용을 저장하고 완료 ID를 manifest에 대조한다. 재개는 동일 protocol hash의 미완료 ID만 처리한다. 출력·비용 중복 및 누락은 평가에서 거부한다. 중간 mask·원시 보고서를 보존해 재분석에 새 모델 호출이 필요하지 않게 한다.

## 5. 규모 확대와 독립 확인

이번에는 고정 val 밖으로 확대하지 않는다. 학습과 공식 test는 미실행으로 유지한다. 긍정적 결과도 full review 후 별도 계획으로만 이어간다. 이 자료는 모델 개발 노출 가능성이 있는 탐색 자료이며 독립 일반화 근거가 아니다.

# Implementation Tasks for Claude

1. `research/results/iter_070/`에 자료 출처·revision·split·정답 span·접근 상태를 기록하고 자료 gate를 먼저 판정한다.
2. 통과 시 공식 AutoRG를 격리 구성한다. 필요한 wrapper 외의 모델 구조·loss·후처리는 변경하지 않는다.
3. P/G 공통 경로와 tensor 불변성을 검증하고 GPU 매핑·파일 충돌·누락 감지를 보완한다.
4. 고정 manifest와 label 표를 출력 전에 봉인한 뒤 기술 확인과 전체 적격 집단의 실제 출력을 실행한다.
5. 원시 보고서에서 독립적으로 재계산 가능한 평가표·비용·실패·재개 기록을 남긴다.
6. 보고서 맨 앞에 자료 적합성, 실제 출력 수, P/G/B 성능, 해석 한계, 종료 결정을 적는다. 실행 중 작업을 완료로 보고하지 않는다.

# Evaluation (성공/실패 기준 포함)

주지표는 두 class의 recall 평균인 BA다. accuracy, class별 recall, UNKNOWN 비율, P/G의 정답 전환 수, 각 case의 원문과 출력 근거를 함께 보고한다. 동일 환자의 여러 scan이 있으면 환자 단위로 묶으며 독립성 미확인은 명시한다. seed70·10,000회 cluster paired bootstrap 95% CI를 계산하되 작은 class의 퇴화 구간을 모집단 확실성으로 해석하지 않는다.

**기본 판독의 탐색 기준:** BA≥0.70, 두 class recall≥0.60, UNKNOWN≤0.10, B 대비 accuracy 이득≥0.10을 함께 사용한다. 이는 후속 후보 선별용 기준이며 임상 허용 성능이 아니다. class 균형만으로 얻는 BA=0.50을 넘고 한 class만 잘하는 모델을 구분하기 위한 기준이다. 소수 한 사례의 제외로 판정이 뒤집히면 불확정으로 처리한다.

- **P가 기준 충족:** 전문 모델이 현재 보고서 기술의 유용한 baseline 후보임을 기록한다. 현재 단일 sequence 신호 판독의 새 방법 투자는 종료한다. 선택·결합 과제의 필요성은 별도다.
- **G만 충족하고 G−P BA≥0.10:** annotation 영역 지원의 유용성을 제한적으로 관찰한다. 적어도 두 독립 case에서 순회복이 있어야 후속 후보로 남긴다. 원 저자가 이미 제공한 mask 지원 효과이므로 자동 method 진입은 없다. 실제 사용에서 영역을 얻는 기존 방법 이후의 잔여 가치가 있어야 다음 투자를 검토한다.
- **G도 기준 미달:** 충분한 인식 이후의 선택 실패를 주장하지 않고 현재 frozen 후보를 종료한다. caption 기술·mask 의미·영상 판독 중 무엇이 원인인지는 분리되지 않았다고 적는다.
- **불확정:** 고정 val 완료 후 CI·class 수·주석·학습 노출 때문에 해석이 약하면 범위를 명시해 보류한다. 기준 미달을 연구 가치 부재로 확대하지 않지만 같은 자료의 prompt·parser·표본 보충은 자동 연장하지 않는다.
- **기술 실패:** 자료나 실행 경로 오류는 모델 오답과 구분한다. 동일 규칙의 영향받은 요청만 복구하며 결과에 맞춰 대상·metric을 변경하지 않는다.

비용은 원본 NIfTI 읽기부터 저장까지의 wall-clock과 device time, segmentation·보고서별 구성 비용, peak VRAM을 보고한다. P/G의 mask 준비 비용 차이를 분리하고 annotation 획득 비용을 0으로 간주하지 않는다.

# Risks / Checks

- 보고서의 명시적 기술과 실제 영상의 임상적 충분성은 다르다. 이번 결과는 공개 보고서 기술의 일치 범위다.
- BraTS 전체 annotation에는 여러 조직 성분이 포함될 수 있다. 보고서의 병변 대상과 mask가 맞지 않으면 정확한 oracle로 해석하지 않는다.
- 같은 checkpoint·영상·후처리를 써도 mask 교체는 형태·범위 정보를 바꾼다. 순수 위치 원인을 주장하지 않는다.
- 공식 val의 checkpoint 선택 노출과 segmentation 사전학습 노출을 구분한다. test와 외부 일반화는 미검증이다.
- 자료 접근에 새 동의가 필요하면 대신 제출하지 않는다. 확인한 권한 blocker와 대안을 기록하고 해당 경로를 종료한다.
- 기존 iter_003·064·068·069의 결과·판정·코드는 덮어쓰지 않는다. 이번에 사용하지 않는 재사용 결함은 정비하지 않는다.

## 대규모 GPU 필요 후보

3D encoder·connector·LLM의 대규모 MRI 보고서 공동 적응은 장기 후보로 남긴다. 현재 두 GPU에서는 전문 frozen baseline의 실제 출력과 잔여 문제를 먼저 확인하며, 이번 계획은 그 학습 투자를 승인하지 않는다.

# 계획의 근거 (GPT 조사 노트)

## 새로 확인한 것

라운드 1 원문 `agent/runs/iter_070/think/round_01.json`을 읽었다. 이번에는 미확인 annotation·split·동일 출력 경로에 집중했다. 파일 수정·설치·실험 실행은 하지 않았다.

1. **정답 내용:** raw/resolve 조회는 실패했으나 Hugging Face의 blob 페이지에서 실제 JSON을 읽었다. `BraTS-GLI-00778-000-t2f`는 병변 고신호, `00801-000-t2f`와 `00772-000-t2f`는 고·저 혼합 신호를 기술한다. 주변 edema와 병변 자체를 구분해야 하며, 미언급을 음성으로 바꾸면 안 된다. 따라서 FLAIR의 두 명시적 기술에 한정한 대조는 후보로 성립한다. 전체 적격 수와 영상 충분성은 아직 확인하지 않았다. [보고서 원문](https://huggingface.co/datasets/JiayuLei/RadGenome-Brain_MRI/blob/main/BraTS_GLI/modal_wise_finding.json)

2. **split:** 실제 split JSON의 `val`에서 BraTS_GLI 23 case ID·각 네 sequence를 확인했다. train/val/test가 배포되어 있지만 checkpoint의 실제 학습 배제와 환자 단위 중복까지 증명한 것은 아니다. 이번에는 val만 개발 탐색에 사용한다. [공식 split](https://huggingface.co/datasets/JiayuLei/RadGenome-Brain_MRI/blob/main/train_val_test_split.json)

3. **공정한 mask 대조:** SDK는 제공 mask와 예측 mask를 같은 전처리로 넘길 수 있고 `given_mask`에서는 생성 문장을 연결한다. P/G 모두 이 경로를 쓰는 대조가 코드상 가능하다. 다만 하위 feature 추출과 전처리의 실제 불변성은 구현 단계에서 확인해야 한다. SDK가 CUDA_VISIBLE_DEVICES를 자체 설정하므로 상속된 허용 GPU 매핑도 보완해야 한다. [SDK 원문](https://raw.githubusercontent.com/ljy19970415/AutoRG-Brain/master/AutoRG_Brain/inference/inferenceSdk.py)

4. **원본 volume 연결은 남음:** 공식 README는 원 영상 출처를 설명하지만 보고서 ID와 확보할 release의 정확한 대응은 아직 미검증이다. 기존 iter_003 manifest는 `obi77/brats23-first-10-examples`의 세 case를 가리킨다. 이름이 비슷하다는 이유로 RadGenome val과 연결하지 않는다. 기존 MSD 자료도 대체하지 않는다. 필요한 원본 확보·대응은 설치보다 앞선 한정 gate다. [공식 사용법](https://github.com/ljy19970415/AutoRG-Brain)

5. **선행 대비 의미:** 저자의 보충 문서는 segmentation 오류 전파와 sequence별 병변 가시성 문제를 이미 설명한다. mask 제공 효과 자체는 신규성이 아니다. 이번 진단의 가치는 기존 해결책의 기본 능력과 후속 투자 가능성을 판단하는 데 있다. [공식 보충 문서](https://raw.githubusercontent.com/ljy19970415/AutoRG-Brain/master/Supplementary.md)

## 원본 기록·재사용

`agent/GOAL.md`, iter_069 review.md, iter_064 review.json, LIMITATIONS의 관련 항목, CODE_ASSETS의 관련 범위를 확인했다. `mri-explicit-target-context-effect`는 보존하지만 이번 AutoRG 과제의 한계 근거로 대체 사용하지 않아 limitation_ids는 비워 둔다. 이번 역할은 신규 현상의 diagnostic이다.

현재 research HEAD는 `76eb1036df95478f889ee6bfd8e31ca43e82b415`이며 작업 트리는 깨끗하다. 추적 파일에서 AutoRG 전용 구현은 찾지 못했다. 기존 일반 VLM runner·평가기의 미해결 문제를 승계할 필요가 없어 가져오지 않는다. 새 코드는 공식 AutoRG를 연결하는 얇은 실행·평가 경로로 한정하고 공식 구현을 재작성하지 않는다.

## 의미와 남은 제한

세 질문 중 annotation의 실제 변이와 동일 mask 대조의 코드상 가능성은 확인했다. 원본 영상·mask 대응과 checkpoint 노출은 구현 전 자료 gate로 남긴다. 공개 보고서를 임상적 재판독 정답으로 승격하지 않는다. 이 계획은 충분한 인식 이후의 선택·결합 실패를 검증하는 실험이 아니다.

## 대규모 GPU 필요 후보

MRI 3D encoder·connector·LLM의 대규모 공동 적응은 장기 후보로 보존한다. 이번 전문 baseline의 성능과 잔여 문제를 확인하기 전에는 투자하지 않는다.

이전 사고 라운드 노트: agent/runs/iter_070/think/
