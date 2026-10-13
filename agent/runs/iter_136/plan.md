# 요약

- 이번에 할 일: 공식 MSD의 기존 MRI에서 개별 판독+OR와 공동 입력을 비교한다.
- 필요한 이유: RadGenome 연결 문제를 반복하지 않고, 관측 추가와 공동 처리 손실을 나눈다.
- 확인할 기준: 자료 무결성·완결 출력, 개별 판독 신호, 동일 관측의 paired 차이다.
- 주의·다음: 반복 개발 자료의 제한적 진단이다. 양성이어도 방법 개발·독립 일반화를 자동 승인하지 않는다.

## 알림 맥락
- 연구: MRI 관측 추가와 근거 통합
- 데이터: RadGenome–BraTS → 공식 MSD Task01 뇌종양 FLAIR MRI
- 모델: MedGemma 1.5, frozen 추론
- 과제: 한 장 또는 두 장에 병변이 보이는지 답한다
- 가설: 개별 판독의 정보를 공동 입력에서 잃는지 관측 누락과 구분할 수 있다
- 질문: 따로 읽어 얻은 병변 정보를 함께 보여줘도 보존하는가?
- 변경: 구체화
- 연결: iter_135에서 자료 연결이 미해결이므로 공식 배포가 확인된 기존 개발 자산으로 제한한다
- 작업: 동일 pixels의 개별·공동 답변을 비교해 후속 대조 또는 투자 보류를 결정한다

# Current Understanding

iter_135의 RadGenome 존재 설계는 보류한다. 원 gate·출력·판정은 수정하지 않는다. iter_064는 지정 slice 질문에서 MedGemma의 context 손실을 관찰했지만 전체 입력 존재 판단은 검증하지 않았다. iter_059의 전문 segmentation 대안은 강하며 새 검출 방법의 필요성을 현재 인정하지 않는다.

유지: MRI 관측·통합 질문, frozen MedGemma, 단독/공동/복제의 대조 논리. 변경: 공식 MSD의 반복 개발 D6/E48을 사용하고 신규 독립 환자·보고서 연결 주장을 제거한다. 보류: RadGenome 접근 감사, 같은 32명 재생성, 타 모델 전수 비교, 학습.

# Strategy Check / 연구 방향 판단

1. 중요한 문제: 추가 관측의 정보가 공동 판독에서도 보존되는가는 관측 선택과 추론 배치의 투자 위치를 바꾼다.
2. 현재 근거: iter_064의 지정 target 손실과 Qwen 반대 근거, iter_135의 자료 blocker를 계승한다. 이번에 MSD 공식 schema와 archive 검증 기록을 확인했다.
3. 쉬운 해결책: 개별 판독+OR 및 전문 segmentation+OR가 강한 대안이다. 두-slice OR 자체는 신규 방법이 아니다.
4. 남은 설명: 관측 누락, 기본 판독 부족, 입력 수 효과, 서로 다른 관측의 공동 처리 손실이다.
5. 다음 결정: 제한적 손실이 남으면 원인·범위 대조 하나를 선택한다. 기본 신호 부족 또는 충분한 단순 대안이면 현재 frozen 질문 투자를 보류한다.

준비 반복을 끝내기 위한 한 번의 유효 비교다. 단순 대안 이후 중요한 잔여 가치가 없으면 양성 성능 차이만으로 방법을 개발하지 않는다.

# Hypothesis

H1: 관측 누락이면 N1에 P를 추가할 때 개별 OR와 공동 입력 모두 양성 회복을 보인다.
H2: 공동 처리 손실이면 같은 P/N1 또는 N1/N2에서 개별 OR 정답이 공동 입력에서 손실된다.
H3: 복제에서도 손실이면 서로 다른 근거의 통합만이 아니라 입력 수·인터페이스 효과가 포함된다.
개별 판독이 부족하면 H2의 일반 해석을 보류한다.

# Limitation Evidence / Correct Usage Checks

대상은 observed `mri-explicit-target-context-effect`다. 원 리뷰의 정상 processor·target tensor·출력 연결 검증을 현재 입력에서 필요한 범위로 계승한다. 기존 S specificity 기준 미달은 그대로 유지한다.

MSD dataset.json은 FLAIR channel0, label1/2/3의 종양 관련 의미와 CC-BY-SA 4.0을 명시한다. 현재 raw를 기존 manifest SHA와 연결해야 한다. mask-free slice는 종양 주석이 없는 관측이며 임상 정상이라는 뜻이 아니다. annotation과 단일 FLAIR 가시성의 차이는 남는다. 보고서 정답은 사용하지 않는다.

# Contribution Path / Baselines / Reuse

같은 MedGemma 단독 출력의 고정 OR가 주대조다. OR는 하나라도 PRESENT면 PRESENT, 모두 ABSENT면 ABSENT, 나머지는 UNKNOWN이며 invalid가 하나라도 있으면 invalid다. 공동 양순서를 평균하되 독립 환자로 세지 않는다.

GT 선택은 원인 분리용 oracle다. 실제 대표영상 선택의 성능은 평가하지 않는다. Vote-MI는 관측 선택, AutoRG는 전문 영역 보고서 생성이라는 다른 지원 조건을 갖는다. iter_059의 HD-GLIO 결과를 동일 정보량 baseline으로 옮기지 않는다. 직접 SFT는 이번에 실행하지 않는다.

현재 브랜치의 i134_common/spec/run/lock/tech/eval 및 test_i134.py를 참고해 iter_136 전용 경로로 분리한다. 기존 원본은 보존한다. gate 생성 코드까지 잠금에 포함하고 worker·평가 직접 진입에도 동일 검사를 연결한다. i135 parser는 그대로 사용하지 않는다. 선별 반입한 msd56_data.py에서는 load_case/render/mask_slice만 사용한다. 의존성은 numpy, nibabel 및 표준 라이브러리이며 실제 환경 import를 확인한다.

# Proposed Experiment

## 1. 자료와 사전 고정

기존 iter_064 target_manifest_D/E의 D6/E48 case 목록을 그대로 사용한다. 신규 환자나 독립 test로 부르지 않는다. D/E case 중복이 없어야 한다. RadGenome·사전학습과의 중복 미확인은 명시한다.

P와 N1은 기존 manifest의 z를 유지한다. N2는 N1과 다른 slice 중 전체 종양 annotation=0, FLAIR nonzero 면적≥해당 volume 최대값의 50%를 만족하는 후보에서 P와 물리 거리가 가장 가까운 것을 고른다. 동률이면 낮은 z다. 후보가 없으면 출력 전에 제외하고 대체하지 않는다. D 적격이 4명 미만 또는 E 적격이 32명 미만이면 이번 설계를 보류한다. 이는 각각 기술 조건 점검과 큰 paired 차이 탐색을 위한 최소 운영 규모이며 충분한 통계 검정력을 보장하지 않는다.

원본·mask hash, affine·shape·orientation·spacing·label·finite, P/N annotation 상태를 검사한다. 공식 archive에서 추출된 파일과 기존 source 기록의 연결을 확인한다. representative D overlay를 직접 표시한다. 기존 raw의 hash가 다르면 임의 재연결하지 않는다.

volume min–max와 MSD 기존 render 방향을 사용한다. 모든 조건은 동일 RGB 파일을 공유한다. 실제 PNG 크기와 processor resize·soft tokens를 기록한다. GT·case명·report·mask는 모델 입력에 넣지 않는다.

## 2. 조건과 출력 계약

환자당 P, N1, N2 단독 3건; P+N1와 N1+P 2건; N1+N2와 N2+N1 2건; P+P와 N1+N1 2건; 영상 없음 1건이다. 총 10요청이다.

i134_spec.py의 QUESTION과 NOIMG 문구를 그대로 사용한다. 답은 PRESENT/ABSENT/UNKNOWN과 한 문장 근거다. 질문은 제공 영상 전체에 적용하며 target index를 지정하지 않는다. seed136, greedy, bf16, 기존 MedGemma revision을 고정한다.

출력 전에 tokenizer의 실제 special-token mapping과 chat template를 확인한다. final 경계 표식이 있으면 token 구조상 완결된 final 구간의 첫 줄을 읽고, 없으면 생성문 첫 줄을 읽는다. 복수·불완전 경계는 invalid다. ID100/101을 상수로 가정하지 않는다. 원문 전체·token IDs·추출 구간·원 첫 줄을 모두 저장한다. 형식 parser는 i134의 세 상태 규칙을 유지하고 설명으로 답을 교체하지 않는다. 경계 포함/미포함·불완전 경계·반복·절단 fixture를 본실행 전에 고정한다.

## 3. 동작 확인

적격 D6에서 최대60요청을 수행한다. max_new_tokens1024로 시작한다. 절단이 있으면 같은 기술 집단 전체를2048로 한 번 재실행한다. prompt나 분모는 바꾸지 않는다. 최종 기술 집단의 모든 조건을 포함해 EOS100%, 형식 유효율≥95%, 입력·tensor·메모리·재개 검사를 통과해야 E에 진입한다. 기술 정확도는 gate가 아니다. 영상 없음도 분모에 포함한다.

## 4. 가능성 탐색과 본비교

기술 통과 후 적격 E 최대48명·480요청을 한 번 실행한다. 조건 순서는 seed136으로 균형화한다. 환자·조건·평가기·출력 계약을 실행 전에 잠근다. 결과에 따른 표본 교체나 조건 추가는 없다.

## 5. 규모 확대·독립 확인

이번 반복의 본실험은 위 E 비교까지다. 학습·추가 seed·신규 환자 확대는 없다. 독립 확인은 미실행으로 보고한다. 양성일 때에도 단순 OR의 비용과 전문 대안 이후의 잔여 가치를 검토한 뒤 별도 계획으로만 확대한다.

## 6. 자원·시간·재개

두 GPU 허용 집합을 유지하고 실행 직전 nvidia-smi에서 여유가 큰 장치부터 배치한다. 실제 모델·KV cache·동시 peak와 다른 점유에 worker당2GiB 여유를 더한다.

기술 workload에서 2 GPU×1 worker와 메모리가 허용하는 2 GPU×2 worker를 비교한다. 4-worker admission이 불가능하면 batch 확대 후보 하나를 검토하거나 구체적 근거로 2-worker를 유지한다. 유효 요청/분·p50/p95 지연·peak VRAM·CPU/RAM/I/O·오류·출력 정합성으로 선택하며 평가 정확도를 사용하지 않는다.

현재 긴 생성의 시간은 미계측이다. 본실행 전 조건별 기술 처리시간×남은 요청 수/실측 동시 처리량에 loading·render·저장·검증 시간을 더해 예상 wall-clock을 기록한다. iter_064의198.37초는 다른 생성 조건의 참고값일 뿐 현재 예산으로 쓰지 않는다. 임의 시간 상한은 없다.

고유 request ID, 원자적 할당, worker별 결과, 완료 hash를 사용한다. 실제 worker를 중단한 뒤 재개해 중복·누락·torn record 처리를 검사한다. 본실행 gate=false, 입력 변조, 잠긴 기술 코드 변조가 launch·worker·eval에서 거부되는지 확인한다. 완료된 출력을 검증한 뒤 미완료 요청만 재개한다.

# Implementation Tasks for Claude

1. 원 리뷰와 현재 계획을 읽고 기존 산출물의 불변성을 보존한다.
2. 선별 반입 모듈과 기존 raw를 검증하고 D/E 적격 manifest를 출력 전에 고정한다.
3. iter_136 전용 요청·출력 경계·평가·잠금 경로를 만들고 필수 회귀 검사를 연결한다.
4. 기술 생성·처리량 비교·실제 실패 주입 후 gate를 계산한다. 실패를 해석으로 통과시키지 않는다.
5. 통과 시 고정 E를 실행하고 독립 수치 재계산에 필요한 원시 출력과 provenance를 보존한다.
6. 계획 대비 요청·비용·제외·미완료와 결과별 투자 판단을 보고한다. Claude 구현·fallback none을 유지하고 커밋 관리는 orchestrator에 맡긴다.

# Evaluation (성공/실패 기준 포함)

주 metric은 annotation-defined 양성 집합 P+N1와 음성 집합 N1+N2에 대한 strict BA다. UNKNOWN·invalid는 해당 class의 오답이며 별도 비율도 보고한다. 주 차이는 개별 OR BA−공동 양순서 평균 BA다. 환자 cluster bootstrap10,000회·seed136의95% CI를 계산한다.

단독 sensitivity/specificity, OR specificity, 순서별 결과, OR 정답→공동 오답과 반대 전환, 복제−단독 차이를 보고한다. P 추가의 양성 회복과 N2 추가의 false-positive 증가를 따로 제시한다. 설명의 명시 모순 후보·unknown·반복·절단·원 첫 줄/final 첫 줄 불일치는 별도 집계한다. 정규식 후보를 임상 모순 확정으로 부르거나 LLM 합의로 재채점하지 않는다.

- 양성: OR BA≥0.75, specificity≥0.65, 차이≥0.15, CI 하한>0, 본출력 완결·형식 유효율≥95%를 모두 충족한다. 제한된 공동 처리 손실로 보존하며 후속 대조 하나를 검토한다.
- 음성: 두 BA≥0.75이고 차이 CI 상한<0.15이면 큰 손실 후보를 보류한다. OR BA≤0.60이면 기본 판독 부족으로 현재 frozen 질문을 종료한다.
- 불확정: 나머지. 기본 신호·정답 의미·환자 변동 중 지배 원인을 밝히고 이번 추가 실행은 하지 않는다.
- 실행 실패: 자료·무결성·기술 gate 실패는 가설 기각이 아니다. 한정 구현 결함 수정 후 같은 계약을 한 번 재검사하고, 남으면 설계를 보류한다.

비용은 두 단독 요청+OR 대 한 공동 요청의 동일 집합 처리비, 양순서 감사비, 단독 출력 공유를 포함한 전체 workload를 분리한다. read부터 답변 원자적 저장까지와 loading 포함 전체 wall을 기록한다. 양성 정확도 차이만으로 새로운 방법의 실용 가치를 선언하지 않는다.

# Risks / Checks

기존 개발 자료를 선택한 것은 독립성 문제의 해결이 아니라 주장 범위 축소다. MSD 원자료 이용·연결은 별도로 검증한다. annotation 부재는 정상 진단이 아니며 단일 FLAIR 관측의 충분성을 보증하지 않는다. P는 GT 최대 병변 slice로 쉬운 양성에 편향돼 있다. 이번은 2.5D/3D 전체 판독 우열이나 새로운 임상 보고서 능력의 검증이 아니다.

본출력 gate를 실패하면 NONE 제외, parser 완화, 표본 교체로 통과시키지 않는다. 과거 RadGenome 출력은 재채점하지 않는다. 처리량 개선 때문에 prompt·해상도·생성 길이·평가 조건을 바꾸지 않는다.

## 대규모 GPU 필요 후보

3D encoder–언어 모델 공동 적응과 관측 누락·장수 변화를 포함한 대규모 MRI instruction tuning은 장기 후보로 보존한다. 현재 제한적 손실과 단순 대안 이후의 필요성이 확인되기 전에는 투자하지 않는다.

# 계획의 근거 (GPT 조사 노트)

## 새로 확인한 것

- GOAL, iter_135·064·059·070 원 리뷰, iter_134 계획, LIMITATIONS의 관련 항목과 CODE_ASSETS의 관련 위치를 읽었다. iter_135는 준비 감사이며 통합 가설의 유효 실험이 아니다.
- `research/results/iter_056/source/fetch_verify.json`은 공식 MONAI 배포 archive 7,608,266,240 bytes의 MD5 `240a19d752f0d9e9101544901065d872` 일치를 기록한다. 로컬 `dataset.json`은 licence=CC-BY-SA 4.0, training484, modality0=FLAIR, labels1/2/3=edema/non-enhancing tumor/enhancing tumour다. image/label basename 연결을 직접 확인했다. 공식 이용 설명도 CC-BY-SA 4.0이다. [MSD 공식 안내](https://medicaldecathlon.com/)
- `iter_064/data/target_manifest_E.json`에는 case별 원본 image/label SHA, P/N z, annotation 면적, PNG SHA가 있다. 예를 들어 BRATS_374는 P z68·면적1590, N z87·면적0이다. 이는 임상 정상 정답이 아니다. 현재 raw 전체 hash와 N2 적격성은 구현에서 확인할 조건이다.
- iter_064의 MedGemma S/R/C BA는 0.80208/0.77083/0.50000이다. S specificity30/48은 원 기준 미달이었다. Qwen에서는 같은 context 손실이 없었다. 이를 충분한 인식 이후의 일반 통합 결함으로 해석하지 않는다.
- iter_059의 전문 대안은 FLAIR 부분 입력과 다른 네 sequence 전체 volume 조건이다. 기존 대안의 충분성과 입력 정보량 차이를 모두 유지한다.
- Vote-MI 공식 저장소에는 실제 디렉터리가 `representative-select`로 표시된다. 과거 노트의 `representative_select` 조회 실패는 구현 부재 근거가 아니다. 공식 설명은 비지도 대표 slice 선택이며 전체 BrainMD 이용에는 PI의 data user agreement가 필요하다고 적는다. 이번에는 새 BrainMD 확보나 선택기 실행을 발주하지 않는다. [공식 구현](https://github.com/YuliWanghust/BrainMD)
- AutoRG-Brain 공식 구현과 iter_070 리뷰를 확인했다. 전문 영역 보고서 생성과 현재 두-slice 존재 질문은 다르므로 같은 baseline처럼 수치를 비교하지 않는다. [공식 구현](https://github.com/ljy19970415/AutoRG-Brain)

## 재사용과 한계

현재 HEAD는 `abd065b34e59dd24e0e9c81d8d07488aec47ec15`, 작업 트리와 diff는 깨끗했다. i134 실행·잠금·자료·spec 소스를 확인했다. i134_lock의 CODE에는 기술 gate 생성 코드가 빠져 있고 기존 결과 경로가 고정돼 있다. 새 경로 분리·gate 코드 잠금·실제 실패 주입은 필수 수정이다. i135의 상수 token ID 기반 추출은 재사용 승인하지 않는다.

이번 계획은 파일 생성·다운로드·모델 실행 없이 작성했다. MSD는 반복 개발 자료이고 RadGenome 및 모델 학습과의 환자 중복은 미확인이다. 독립 일반화나 임상 정확도를 주장하지 않는다.
