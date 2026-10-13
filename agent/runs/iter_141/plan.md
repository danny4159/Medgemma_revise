# 요약

- 이번에 할 일: RadGenome ISLES22의 DWI 영상–보고서 연결을 확인하고, 성립하면 같은 전체 영상을 개별·인접 묶음으로 판독한다.
- 필요한 이유: 실제 split에는 DWI/ADC만 있어 이전 FLAIR 설계를 그대로 적용할 수 없다. 동일 관측의 판독 효과는 아직 미검증이다.
- 확인할 기준: 명시 소견 recall, 위치·속성 모순, 미판정·절단과 전체 처리 비용을 함께 비교한다.
- 주의·다음: 신규 학습은 하지 않는다. 실제 오류와 supervision 단위를 확보해 입력별 SFT 및 AutoRG 대조로 연결하며, 준비만으로 연구 진전을 주장하지 않는다.

## 알림 맥락

- 연구: MRI 병변 근거와 판독 설명의 연결
- 데이터: RadGenome ISLES22의 뇌졸중 DWI MRI와 sequence별 설명
- 모델: 기본 MedGemma 1.5; 입력별 SFT와 AutoRG는 후속 비교
- 과제: 같은 전체 DWI 영상에서 소견 설명을 생성하고 고정 규칙으로 통합한다
- 가설: 인접 영상을 함께 읽으면 소견 누락을 줄일 수 있다
- 질문: 같은 MRI 전체를 볼 때 한 장씩 읽는 것보다 이웃 영상을 함께 읽는 것이 소견을 더 잘 보존하는가?
- 변경: 구체화
- 연결: BraTS 뇌종양 자료의 이용·release 연결이 막혀, 공식 공개 원영상과 보고서가 있는 ISLES22 뇌졸중 자료를 한정 검토한다
- 작업: 실제 DWI 연결이 성립하면 두 입력 방식의 판독을 비교해 후속 적응의 필요성을 판단한다

# Current Understanding

최종 GOAL과 `mri-volume-evidence-use`를 유지한다. iter_140은 자료 gate에서 종료한 실행 실패이며 모델 능력의 반증이 아니다. iter_139의 MSD 중심 학습과 iter_138의 인터페이스 실험은 보존·보류한다.

기준 문서는 `agent/runs/iter_140/plan.md`, SHA256 `f44817db8327b2da5a0e1a17462eb56b91c8d8c4db5dd1272028947495e562ed`다. 동일 관측·고정 통합·미언급과 음성 구분·5pp 탐색 기준을 유지한다. 이번 변경은 BraTS→ISLES22, FLAIR→DWI, 고정 환자 목록과 결과 경로다. 자료·sequence가 바뀌므로 새 입력·정답 연결은 다시 검증한다.

로컬 공식 split에는 ISLES22 train 175명, val 25명, test 50명의 DWI/ADC key가 있다. FLAIR 보고서가 있다고 가정하지 않는다. modal 보고서 본문과 원영상 대응은 아직 미확인이므로 아래 자료 확인을 통과할 때만 생성한다.

# Strategy Check / 연구 방향 판단

직전 카드 출처는 iter_140 원 리뷰다. 새 근거는 공식 split의 DWI/ADC 구성이며 새 모델 관찰은 없다.

1. 중요한 문제: 같은 관측 범위에서도 공간적으로 묶는 처리 방식이 소견 보존을 개선하는가?
2. 현재 근거: 과거 지정 target·고정 범주 관찰은 제한적으로 유효하지만 전체 판독 및 적응 후 효과는 미검증이다.
3. 쉬운 해결책: 개별 처리+고정 통합, 입력별 직접 SFT, AutoRG 예측 영역 판독이다. 어느 것도 이번 DWI 과제의 충분성이 확인되지 않았다.
4. 남은 설명: sequence 보고서 연결, 기본 인식·적응 부족, 인접 처리 효과를 구분해야 한다.
5. 다음 결정: 자료가 성립하면 실제 비교를 완료하고 적응 필요성을 판단한다. 연결이 막히면 추가 자료 순회를 끝내고 필요한 접근 근거를 구체적으로 요청한다.

# Hypothesis

동일한 전체 DWI slice 집합에서 인접 묶음 처리가 유용하면 개별 설명의 통합보다 명시 소견 recall이 높아지고 모순은 크게 증가하지 않는다. 차이가 없고 양쪽 오류가 많으면 frozen 모델의 기본 인식·적응 부족이 남는다. 개별 처리도 충분하면 새 공간 방법의 필요성은 약해진다.

요청 수와 생성 길이 차이가 함께 발생하므로 양성 결과를 순수 3D 구조의 인과 효과로 부르지 않는다. 이번은 그 효과를 분리할 후속 개입의 가치가 있는지 확인하는 진단이다.

# Limitation Evidence / Correct Usage Checks

`radgenome-flair-fixed-category-response`의 45/45 HIGH 관찰은 보존한다. 영상 조건의 절단과 설명문 내 혼합 신호 때문에 이를 DWI 인식 실패로 전이하지 않는다. 이번 ISLES22의 한계는 아직 candidate이며 학습 method gate를 통과했다고 간주하지 않는다.

필수 검사는 이용 조건, 공식 환자·session·sequence 연결, report 범위, 방향·spacing·mask 공간, 공식 processor, 원시 출력 경계, 정답 누출 방지다. 높은 정확도나 EOS 100%는 기술 진입 조건이 아니다.

# Contribution Path / Baselines / Reuse

기여는 미확정이다. 동일 관측의 개별 판독이 직접 baseline이며 인접 조건과 입력 pixels·질문·통합을 맞춘다. 후속 직접 SFT는 같은 환자·target·적응 범위에서 비교한다. bbox supervision은 추가하지 않는다.

[AutoRG 공식 구현](https://github.com/ljy19970415/AutoRG-Brain)은 DWI와 예측 mask 경로를 지원하지만 SEG의 ISLES2022 학습 및 RGv2의 RadGenome 학습을 명시한다. 새 비교는 우선 개발 자료에서의 전문 시스템 작동 비교이며 독립 일반화나 구조 효과가 아니다. 개별 학습 split이 불명확하면 노출 불명으로 유지한다.

현재 브랜치와 `9157bb31ca641fe720bd2d5203780df82635d53d`의 연결을 확인한다. `i136_run.py`, `i136_common.py`, `i136_spec.py`, `i134_spec.py`는 이미 있으므로 reuse_assets 반입은 없다. 새 `i141_*`로 필요한 실행·hash·출력 경계 부분만 파생한다. iter_136 경로, 최대 2장 제한, presence parser를 제거한 새 경로를 검증한다. `i140_preflight.py`의 고정 gate를 새 자료 적격성 판정에 사용하지 않는다.

AutoRG 자산은 `results/iter_070/`의 source·환경·가중치 manifest를 읽어 후속 가능성을 기록한다. 이번에는 옛 wrapper를 실행하거나 재구현하지 않는다. 과거 HIGH/MIXED 평가기와 X-ray 전이 실험을 재실행하지 않는다.

# Proposed Experiment

## 1. 한정 자료 확인

RadGenome revision `0348ba42fad134da57b50e736ba858a8e73eb086`의 ISLES22 modal/global/impression 파일과 split을 확보한다. 원영상은 [공식 ISLES2022 v2.3.1](https://zenodo.org/records/7960856)만 사용한다. 새 결과·데이터는 `research/results/iter_141/`에 저장한다.

고정 후보는 공식 train의 환자 ID 정렬 첫 8명이다: `sub-strokecase0001`, `0003`, `0004`, `0006`, `0007`, `0008`, `0009`, `0010`, 모두 `ses-0001`. 각 ID의 DWI key를 정확히 연결한다. 첫 두 후보는 기술 개발, 나머지 여섯 후보는 탐색으로 고정하며 탈락자를 다른 환자로 채우지 않는다. 기술 후보가 모두 부적격이면 본생성을 진행하지 않는다.

보고서 JSON의 실제 타입·key·문장 원문, 원영상 BIDS ID, release 문서와 환자 대응을 보존한다. 이름 유사성만으로 다른 release를 연결하지 않는다. DWI modal 문장이 자체 완결적인 소견을 제공하는지 확인한다. global 문장이 필요하면 명시적인 참조 관계가 있는 항목만 연결하고 ADC에서만 판단 가능한 속성을 DWI 정답으로 옮기지 않는다. DWI 단독으로 확인할 수 없는 restricted diffusion·병인 확정은 주평가에서 제외한다.

원영상 ZIP의 파일 목록·크기와 실제 여유 디스크를 확인한다. 선택 파일 다운로드가 가능하면 8명의 DWI·관련 metadata·mask만 확보한다. 단일 ZIP만 제공되면 저장 metadata상 1,692,717,470 bytes인 archive 한 개를 받고 선택 파일만 추출한다. checksum을 확인하고 전체 자료는 풀지 않는다. 공간이 부족하면 삭제나 임의 외부 경로 사용으로 해결하지 말고 필요한 용량과 장애를 보고한다.

DWI의 3D/4D 여부·b-value 의미를 확인한다. 임의 channel 선택·평균은 하지 않는다. mask는 원래 공간·shape·affine·label 의미가 확인된 경우에만 보조 분석에 쓴다. DWI–mask 공간이 다르면 임의 registration으로 정답을 만들지 않는다. sequence 보고서 연결이 유효하면 mask 보조 분석 없이 판독 비교를 진행할 수 있고, 이때 가시성·병변별 localization 주장은 보류한다.

## 2. 관측·출력 계약 고정

두 조건 모두 동일 DWI volume의 전체 axial slice를 본다. 정확한 0 배경 padding이 확인된 경우에만 nonzero 범위 밖 빈 slice를 제외한다. 내부 slice는 모두 유지하고 GT mask로 선택하지 않는다. voxel index, canonical 변환, 물리 위치, 저장 spacing과 알려진 획득 spacing을 구분해 기록한다.

개별 조건 S는 각 slice를 한 번씩 처리한다. 인접 조건 A는 같은 목록을 물리적 순서로 연속 최대 5장씩 겹치지 않게 묶는다. 마지막 묶음은 실제 남은 장수를 사용한다. 두 조건의 slice multiset·pixel hash·해상도·volume 정규화가 같아야 한다. ADC와 DWI를 인접 slice처럼 섞지 않는다.

공통 질문은 제공된 DWI에서 보이는 소견·위치·신호를 짧게 설명하고, 제공되지 않은 영상이나 병인을 추측하지 않도록 한다. 환자 ID·데이터셋명·질병명·report·mask는 입력하지 않는다. 첫 생성 전에 문구를 잠근다.

통합은 물리적 순서의 원문 연결과 완전히 같은 문장 중복 제거뿐이다. 모순 삭제·다수결·추가 LLM 요약은 없다. 원문 전체와 중복 제거 결과를 모두 보존한다. 이는 완성된 임상 보고서 평가보다 소견 집합 보존 비교라는 한계를 명시한다.

## 3. 동작 확인

MedGemma 1.5 revision `91850547d9f0b2fdd21aa7c5f4f3d1a8a52c243b`, bf16, sdpa, greedy, seed141을 고정한다. 기술 후보에서 1장·5장·마지막 짧은 묶음의 공식 chat template tensor, image token 수, 순서·해상도·target pixels를 확인한다.

생성 한도는 1024다. 기술 출력이 cap에 도달하면 양쪽 모두 2048로 올려 기술 비교를 다시 하고 본실행 전에 잠근다. 본출력의 절단은 사후 재생성하지 않고 미완결로 표시한다. final 경계가 잘못되면 thought를 판독문으로 평가하지 않는다.

worker 직접 진입 hash 검사, 원자적 claim, 동시 실행 배타성, 중복·누락, 부분 재개와 완료 출력 불변성을 검사한다. 오류는 영향 경로만 수정하며 같은 실패가 남으면 실행 실패로 종료한다.

## 4. 가능성 탐색

기술 단계 후 나머지 고정 후보의 적격 사례를 모두 생성한다. reference의 명시 소견은 생성 전에 원문 span에 연결해 고정한다. 위치·신호·분포 등 DWI 문장이 직접 지원하는 항목만 포함한다. 문장에 없는 정상·음성은 만들지 않는다.

출력의 조건명을 가리고 동일 규약으로 명확한 일치, 명시적 모순, 미언급, 미판정을 구분한다. reference와 출력 양쪽 span을 저장한다. assistant의 대응 판정은 텍스트 근거 정리이며 새로운 임상 정답이 아니다. 애매한 동의어나 임상 추론은 미판정으로 둔다.

주 지표는 환자별 명시 양성 항목 recall의 평균이다. 양성 항목이 없는 환자는 recall 분모에서 제외하고 그 수와 다른 지표는 남긴다. 명시 reference와 충돌한 환자율, 출력 내부 모순, 위치·속성별 오류, 미판정률, 절단률을 별도 보고한다. reference에 없는 추가 소견은 보고서 미확인으로 분류하고 임상 허위라고 부르지 않는다. 미판정의 최선·최악 범위와 환자별 paired 차이를 함께 계산한다.

## 5. 규모 확대·독립 확인·학습 연결

이번은 최대 6명의 개발 탐색이며 신규 학습·추가 seed·독립 확인은 없다. 표본 수는 효과 확증이 아니라 자료 적합성과 실제 오류·평가 가능성을 확인하는 기존 8명 규모를 계승한다. CI의 넓음만으로 추가 환자를 자동 모집하지 않는다.

종료 보고서에는 기본 개별/인접 출력, 입력별 SFT, 3D 실용 비교의 실행 여부를 각각 적는다. 다음 method pilot은 현재 과제의 유효한 실제 오류와 blocking 없는 사용 검사를 확보한 뒤 판단한다. frozen 우위가 없다는 이유만으로 적응을 생략하지 않는다.

supervision은 먼저 공식 region/report가 관측 구간을 직접 지지하는지 판정한다. 지원되면 동일 target을 사용한 개별/인접 적응을 후속 후보로 둔다. sequence 전체 report만 있으면 각 slice에 report를 복제하지 않는다. 전체 sequence를 학습 단위로 처리할 실행 가능한 설계가 필요하다고 명시하고 이번에 임의 feature 압축 학습기를 만들지 않는다.

AutoRG는 기존 source·weights·환경 출처, DWI 지원, 예측 mask 실행 경로, 환자 노출을 정리한다. 다음 비교에서는 같은 sequence 보고서 항목으로 평가하고 입력 해상도·학습 노출·비용을 밝힌다. GT mask는 별도 oracle다. 이번 실제 오류와 supervision 연결에 따라 직접 SFT pilot 또는 먼저 전문 시스템 실제 대조 중 하나를 다음 투자로 권고한다.

## 6. GPU·비용·재개

실행 직전 nvidia-smi와 상속된 GPU 0,1의 논리·물리 대응을 확인한다. 여유가 큰 장치부터 사용하고 독립 요청을 두 GPU에 배정한다. 기술 입력에서 GPU당 1 worker와 batch 확대 또는 GPU당 2 worker 중 유망한 한 구성을 짧게 비교한다. 출력 조건·정합성이 유지되고 전체 처리량이 좋아질 때만 적용한다.

동시 peak 합계와 기존 점유에 worker당 최소 2GiB 여유가 필요하다. 8–10GB 참고값만으로 증설하지 않는다. 긴 출력 지연, peak VRAM, CPU/RAM/I/O 경합과 OOM을 기록한다. GPU당 1 worker를 선택하면 실측 이유를 남긴다.

총 요청은 `sum(Zi+ceil(Zi/5))`다. 현재 wall-clock은 미계측이며 기술 단계의 조건별 처리량과 loading·평가 비용으로 본실행 예상치를 산출한다. 임의 시간 상한은 두지 않는다. 요청별 완료 기록·worker별 원문·hash·자원 ledger로 재개하고 완료 요청을 다시 생성하지 않는다.

# Implementation Tasks for Claude

현재 구현 담당은 Codex다.

1. 현재 브랜치의 기존 파일과 리뷰 대상 SHA를 확인하고 원 결과를 보존한다.
2. 공식 DWI 보고서·원영상 연결을 고정 8명에서 확인한다. 불성립이면 큰 실행기를 만들지 않는다.
3. reference span, 후보 제외, slice 목록, prompt, 전처리·통합·평가 규약을 생성 전에 잠근다.
4. 현재 실행기를 새 결과 경로·1–5장·자유 소견 출력에 맞춰 한정 파생하고 tensor·재개 검사를 수행한다.
5. 기술 단계가 유효하면 두 GPU로 고정 탐색 비교를 완료하고 원문 근거와 비용을 보고한다.
6. 학습 가능한 정답 단위와 AutoRG의 실용 경로·노출을 명시한다. 신규 학습이나 3D 성능을 실행한 것처럼 보고하지 않는다.
7. SELF_CHECK, 출력 수·hash·중복·누락·독립 재계산용 파일을 남기고 소스 보존은 orchestrator에 맡긴다.

# Evaluation (성공/실패 기준 포함)

양성 탐색: A−S 환자 평균 recall ≥5pp, 명시 모순 환자율 증가 ≤5pp이며 미판정 범위에서도 유지된다. 소수 개발 관찰로 보존하고 method pilot의 근거를 검토한다. 신규성·일반화를 확정하지 않는다.

음성: 유효 비교에서 위 기준을 충족하지 못한다. frozen 인접 우위 미확보로 한정하고 양쪽 잔여 오류와 supervision 가능성에 따라 직접 적응의 필요성 또는 단순 처리 충분성을 판단한다.

불확정: 미판정·절단·환자 변동 때문에 다음 판단이 달라진다. 원문 기반 한정 보완 후 종료하고 같은 자료의 prompt·parser·장수 탐색으로 연장하지 않는다.

자료 연결 실패: execution_failed이며 모델 가설은 미판정이다. ISLES22 공식 연결이 불성립하면 다른 데이터 순회를 하지 않는다. BraTS 재개에 필요한 사용자 본인의 공식 접근 승인 또는 승인된 원천 자료·release 대응 증거를 구체적으로 요청한다.

# Risks / Checks

- ISLES22의 DWI 관찰은 뇌종양 FLAIR의 과거 결과와 합산하지 않는다.
- native-space 자료이므로 mask 공간 일치를 가정하지 않는다.
- DWI만으로 ADC 감소·확산 제한·병인을 확정하지 않는다.
- AutoRG 학습 노출과 MedGemma의 미확인 사전학습 노출을 기록한다.
- 개별 조건의 더 많은 요청·출력 기회가 recall과 모순을 함께 늘릴 수 있다. 비용과 출력량을 함께 보고한다.
- report의 미언급은 음성이 아니며, 평가 가능한 범위 밖 주장은 미판정으로 남긴다.
- 자료 감사·코드 검사만 완료되면 valid_experiment=true로 보고하지 않는다.

## 대규모 GPU 필요 후보

전체 3D encoder와 언어 모델을 공동 학습해 긴 volume의 공간 정보를 보존하는 방법은 후속 후보로 남긴다. 현재는 자료·학습 비용이 크고 필요성도 미검증이므로 두 24GB GPU에서 가능한 직접 적응과 기존 3D 시스템 비교를 우선한다.

# 계획의 근거 (GPT 조사 노트)

### 새로 확인한 사실

- `agent/runs/iter_140/review.json`과 원 plan을 읽었다. 보고서 8명·로컬 영상–mask 3쌍 확인은 자료 감사이며 생성·학습·3D 비교는 0건이다. 기준 plan SHA256은 `f44817db8327b2da5a0e1a17462eb56b91c8d8c4db5dd1272028947495e562ed`다.
- 저장된 `research/results/iter_070/data/radgenome/train_val_test_split.json`을 직접 집계했다. `sub-strokecase` key는 train 175명×DWI/ADC=350개, val 25명×2=50개, test 50명×2=100개다. FLAIR key는 없다. split 조회 중 test ID 일부가 표시됐으므로 test metadata 무노출을 주장하지 않는다. 보고서 내용과 영상은 열지 않았다.
- train 환자 ID 정렬의 첫 8명은 0001, 0003, 0004, 0006, 0007, 0008, 0009, 0010이고 session은 모두 0001이다. 모델 출력과 무관한 후보로 고정할 수 있다.
- [RadGenome ISLES22 공식 파일 목록](https://huggingface.co/datasets/JiayuLei/RadGenome-Brain_MRI/tree/main/ISLES22)에서 global_finding, impression, modal_wise_finding의 존재를 확인했다. 로컬 저장 metadata의 revision은 `0348ba42fad134da57b50e736ba858a8e73eb086`이다. 이번 조회에서는 modal JSON 본문 접근이 실패했으므로 실제 문장 schema·자기완결성·개별 영상 연결은 아직 확인하지 못했다.
- `research/results/iter_140/preflight_a2/isles_zenodo_metadata.json`의 저장 공식 응답은 ISLES2022 v2.3.1, 공개 CC-BY-4.0, 250명, DWI/ADC/FLAIR, native space 및 사전 registration 없음이라고 설명한다. 현재 웹 조회의 429는 데이터 권한 거절의 증거가 아니다. 원 출처는 [ISLES2022 공식 배포](https://zenodo.org/records/7960856)다.
- [AutoRG 공식 구현](https://github.com/ljy19970415/AutoRG-Brain)은 DWI 입력을 지원하고 SEG 학습에 ISLES2022, RGv2 학습에 RadGenome을 명시한다. mask 미제공 추론과 제공 mask 경로가 구분된다. 개별 checkpoint의 환자별 노출은 별도 확인이 필요하다.
- 현재 브랜치의 `i136_run.py`, `i136_common.py`, `i136_spec.py`를 읽었다. 결과 경로는 iter_136, 요청은 최대 2장, 평가 규약은 presence다. 이를 그대로 실행할 수 없다. `i140_preflight.py`의 승인은 고정 감사 보존에만 해당한다. 새 파일 반입 없이 현재 파일에서 필요한 실행 부분을 한정 파생한다.
- iter_070 원 리뷰의 높은 P/G mask 중첩, 노출 불확실성, wrapper 재개·공식 tensor 대조 결함을 확인했다. 과거 BA 0.614를 새 DWI 판독의 실패 근거로 사용하지 않는다.

### 의미

질환은 뇌종양에서 뇌졸중으로 바뀌지만 동일 관측 범위의 판독 질문은 유지한다. 실제 split은 FLAIR보다 DWI를 첫 후보로 지지한다. 보고서 내용 확인이 남아 있으므로 상세 학습 설계 대신 한정 연결 검사와 성립 시 실제 생성 비교를 묶는다. ISLES의 mask 공간을 FLAIR로 임의 이동시키는 작업은 필요하지 않다.
