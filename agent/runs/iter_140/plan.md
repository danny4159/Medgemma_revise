# 요약

- 이번에 할 일: RadGenome의 실제 FLAIR–mask–sequence 보고서 연결을 한정 확인하고, 같은 전체 영상을 개별 또는 인접 묶음으로 판독한다.
- 필요한 이유: 기존 관찰은 지정 slice 판단이나 비배타적 범주 출력이며, 전체 관측을 맞춘 판독 비교가 아니다.
- 확인할 기준: 공개 보고서가 명시한 소견의 회복·누락·위치/속성 모순과 처리 비용을 비교한다.
- 주의·다음: 이번은 diagnostic이다. 입력별 SFT와 3D 대조는 정답 단위·노출 검토를 연결한 다음 단계이며, frozen 결과만으로 연구를 종료하지 않는다.

## 알림 맥락

- 연구: MRI 병변 근거와 판독 설명의 연결
- 데이터: RadGenome-Brain MRI의 뇌종양 FLAIR 영상과 sequence별 설명
- 모델: 기본 MedGemma 1.5; 입력별 적응과 AutoRG-Brain은 후속 비교
- 과제: 같은 전체 FLAIR 관측에서 소견 설명을 생성하고 통합한다
- 가설: 인접 정보를 함께 읽으면 개별 처리보다 소견 누락과 모순이 줄 수 있다
- 질문: 같은 뇌 MRI 전체를 볼 때 한 장씩 읽는 것과 이웃 영상을 함께 읽는 것 중 무엇이 판독 근거를 더 잘 보존하는가?
- 변경: 구체화
- 연결: MSD 중심 유무 학습 계획을 보존·보류하고 최신 사용자 지시에 따라 RadGenome 판독 범위를 우선한다
- 작업: 자료 연결이 성립하면 실제 paired 판독을 수행해 입력별 학습과 3D 대조의 다음 단위를 정한다

# Current Understanding

iter_139는 사용자 전환으로 중단됐으며 실패·완료가 아니다. `agent/runs/iter_139/`의 plan·세션과 checkpoint `3fb452dc0e53ebbbf26c0f9437afca348c18ea39`를 유지한다. 확인된 변경은 기존 추론 파일 5개 반입이며 새로운 학습 결과는 확인하지 못했다.

유지: MRI 공간 문맥 질문, MedGemma 1.5, 입력별 직접 적응과 3D 비교의 필요성, 두 GPU 활용, 독립 리뷰.

보류: MSD 중심 유무 LoRA, iter_138 설명 요구 제거 비교, 과거 HIGH/MIXED prompt 순회.

변경: 데이터 우선순위는 RadGenome, 출력은 소견 설명, 분석 단위는 연결된 sequence 전체다. 현재 로컬 보고서는 slice별 정답을 제공하지 않는다.

iter_083과 iter_135에서 mapping 접근·이용·release 대응이 미해결이었다. 기존 영상 파일명과 report key 일치는 연결 후보이지 해결 증거가 아니다.

# Strategy Check / 연구 방향 판단

직전 카드 출처는 iter_139 plan과 iter_135/136 원 리뷰다. 변경 근거는 사용자 정정과 실제 sequence별 보고서 schema 확인이다.

1. 중요한 문제: 같은 관측과 학습 자료에서도 처리 단위가 소견 보존에 영향을 주는지 알아야 MRI 공간 정보 활용 방법에 투자할 수 있다.
2. 현재 근거: 지정 target의 context 손실과 고정 범주 응답은 관찰됐다. 전체 범위 판독 및 입력별 판독 SFT의 효과는 미검증이다.
3. 쉬운 해결책: 개별 처리와 고정 통합, 직접 판독 SFT, AutoRG 전문 시스템이다. 먼저 약하게 만든 단일 slice baseline을 피한다.
4. 남은 설명: 관측 부족, 기본 인식·적응 부족, 공동 처리 효과, 보고서 범위 불일치다.
5. 다음 결정: 실제 오류와 정답 단위가 확인되면 직접 SFT pilot을 설계한다. 자료가 막히면 접근 문제를 명시해 종료한다. 단순 대안이 충분하면 새 공간 방법 투자를 보류한다.

이번 준비는 이미 실패한 익명 다운로드를 반복하는 작업이 아니다. 기존 인증된 승인 자산이나 공식 연결 증거의 추가 가능성만 확인한다.

# Hypothesis

동일 slice 집합에서 인접 공동 처리가 유용하면 명시 소견 recall이 증가하고 위치·속성 모순은 증가하지 않는다. 개별 통합과 비슷하면 단일 처리의 충분성 또는 frozen 모델의 적응 부족이 남는다. 양쪽이 낮으면 인식·supervision 적합성을 검토해야 하며 일반적 3D 결합 실패로 부르지 않는다.

# Limitation Evidence / Correct Usage Checks

`radgenome-flair-fixed-category-response`는 iter_133의 유효한 제한적 관찰이다. 첫 줄 45/45 HIGH지만 영상 조건 30건 중 14건은 절단됐고 설명에는 high와 low가 함께 등장했다. 기존 범주와 parser를 재사용하지 않는다.

`mri-explicit-target-context-effect`는 iter_064의 지정 target 과제에 한정된다. 실제 인접 전체 판독 실패를 검증한 근거가 아니다. 이번은 새로운 진단이며 method gate를 우회하는 학습을 포함하지 않는다.

필수 검사는 이용 근거, 원천 환자/scan 연결, sequence, affine·방향·spacing, 실제 관측 목록, 공식 processor, 출력 경계·길이, 보고서 누출 방지다. 낮은 정확도는 기술 실행 중단 조건이 아니다.

# Contribution Path / Baselines / Reuse

기여는 미확정이다. 동일 관측의 개별 처리+고정 통합이 직접 baseline이다. 인접 조건과 차이가 있어도 계산량·요청 수 차이를 함께 보고한다.

[AutoRG 공식 구현](https://github.com/ljy19970415/AutoRG-Brain)은 예측 segmentation 기반 판독과 제공 mask 경로를 지원한다. RGv2의 RadGenome 학습 노출 때문에 현재 train 출력은 독립 일반화 비교가 될 수 없다. 기존 환경·가중치는 `research/results/iter_070/`에서 출처와 hash를 재검증해 후속 사용한다.

선별 반입 파일은 JSON reuse_assets의 4개다. 새 `i140_*` 경로로 필요한 실행·경계 로직만 파생한다. 기존 결과 경로와 presence parser는 실행하지 않는다. AutoRG의 옛 HIGH/MIXED 평가기와 임상 의미를 추론하는 정규식은 가져오지 않는다.

iter_097의 직접 판독 적응 및 의미 평가 한계를 계승한다. bbox 학습 성과를 판독 전이로 간주하지 않고 X-ray를 재실행하지 않는다.

# Proposed Experiment

## 1. 한정 자료 확인

`research/results/iter_083/preflight_a1/train_review8.json`의 train 8명을 출력과 무관한 고정 후보로 사용한다. 보고서 전체를 다시 검색해 쉬운 사례를 고르지 않는다. 공식 split·환자 prefix·scan 중복·과거 노출을 기록하고 test는 추가로 열지 않는다.

먼저 기존 iter_070/083/135의 접근 기록과 source revision을 읽는다. 승인된 로컬 원천 자료 또는 저장 인증을 통한 공식 경로에서 이용 조건과 개별 release 대응을 확인한다. 토큰 내용은 출력하지 않는다. 익명 403을 동일하게 반복하거나 mirror MIT 문자열로 원천 이용 권한을 대신하지 않는다.

각 사례의 원천 ID, release, FLAIR 및 mask hash·shape·affine, report key, 보고서 작성 범위와 mask label 의미를 표로 연결한다. 서로 다른 release의 이름 일치만으로 통과시키지 않는다. 보고서가 다른 sequence 설명을 참조해 자체 의미가 불완전하면 해당 항목을 평가에서 제외하고 이유를 고정한다.

영상 다운로드는 필요한 FLAIR·mask에 한정한다. 원격 크기·압축 해제량·실제 여유 디스크를 먼저 합산한다. 기존 hf_cache와 기본 환경은 변경하지 않는다. 새 동의가 필요한 경우 요건과 공식 링크를 제시하고 사용자를 대신해 동의하지 않는다.

전체 sequence 보고서 연결은 성립하지만 region/slice 연결은 없을 수 있다. 이 경우 이번 전체 관측 진단은 가능하고 slice별 SFT는 불가하다고 구분한다. 이용 또는 sequence 연결이 실패하면 실제 비교를 중단하고 실패 범위를 자료 경로로 한정한다.

## 2. 동일 관측과 출력 계약

적격 후보를 원 후보 순서대로 정렬한다. 첫 2명은 기술·개발이며 나머지 최대 6명은 고정 탐색이다. 적격 부족을 다른 쉬운 환자로 채우지 않는다. 기술 2명만 남으면 결과는 사례 탐색으로 제한한다.

FLAIR의 뇌 영상이 포함된 모든 axial slice를 사용한다. 전처리된 배경이 정확히 0인 자료에서만 nonzero bounding range로 빈 padding을 제외하며 내부 slice는 제거하지 않는다. 이 전제가 안 맞으면 전체 z 범위를 사용한다. GT mask로 slice를 선택하지 않는다.

S는 각 slice를 한 번씩 개별 처리한다. A는 동일 목록을 inferior→superior 순서의 겹치지 않는 연속 최대 5장 묶음으로 처리한다. 마지막 묶음은 실제 남은 장수로 두고 복제하지 않는다. 두 조건의 slice multiset, pixel hash, 해상도와 정규화는 동일해야 한다. 원 index, canonical 변환, 물리 좌표·저장 spacing을 기록하고 원 획득 spacing과 구분한다.

공통 질문은 제공된 FLAIR 영상에서 보이는 비정상 소견·위치·신호 특성을 짧은 문장으로 기술하고, 보이지 않는 범위나 병인을 추측하지 말도록 한다. 환자명·질병 데이터셋 이름·정답 report·mask는 넣지 않는다. 문구는 첫 생성 전에 고정하며 내용 결과를 보고 변경하지 않는다.

통합은 slice/묶음 순서대로 원문을 보존하고 완전히 같은 문장만 중복 제거하는 비생성 규칙이다. 반대 소견을 삭제하거나 다수결로 고치지 않는다. 사건 평가는 전체 집합에서 중복을 한 번만 세되 모순은 유지한다. 이 결과는 완성된 임상 보고서보다 소견 집합 보존 비교에 가깝다는 한계를 명시한다.

## 3. 동작 확인

MedGemma revision `91850547d9f0b2fdd21aa7c5f4f3d1a8a52c243b`, bf16, sdpa, greedy, seed140을 고정한다. 기술 2명의 단일·5장·마지막 짧은 묶음에서 공식 processor 대조와 동일 pixels·순서를 확인한다.

생성 길이는 1024로 시작한다. 기술 출력에 cap 도달이 있으면 두 조건 모두 2048로 올려 해당 기술 비교를 다시 수행하고 본생성 전에 잠근다. 이후 본출력 절단은 보존하고 내용 평가에서 미완결로 표시한다. EOS 100%나 높은 정확도를 진입 gate로 강제하지 않는다.

출력 경계, 저장 원문·token ID·EOS, 중복·누락, 요청 변조 거부, 부분 중단 후 재개를 검사한다. 실패는 영향 경로만 한 번 수정하고 계속 실패하면 execution_failed로 종료한다.

## 4. 가능성 탐색과 평가

보고서 reference는 모델 출력 전에 문장 span과 연결해 원자적 항목을 만든다. 항목은 명시된 병변 위치, 고신호·저신호 각각, 부종, 구조 변위 등으로 제한한다. HIGH를 low 부재로 읽지 않는다. midline crossing과 midline shift를 구분한다. 보고서 미언급은 음성 정답이 아니다.

출력은 조건명을 가린 상태에서 같은 문장 규약으로 reference와 연결하고 양쪽 원문 span을 보존한다. 명확한 일치·명시적 모순·미언급·미판정을 구분한다. assistant 판정은 보고서 텍스트 대응의 보조이지 임상 정답이 아니다. 자유 LLM 점수와 문장 유사도를 주 endpoint로 쓰지 않는다.

주 지표는 환자별 명시 양성 항목 recall이다. 위치·속성 모순, 명시 음성의 반박, 출력 내부 모순, 미판정률, 절단률을 별도 보고한다. reference에 없는 추가 소견은 ‘보고서에서 확인되지 않음’으로 표시하며 임상 허위 소견으로 단정하지 않는다. 미판정 대응의 최선·최악 범위와 환자별 paired 차이를 함께 제시한다. 표본이 작으므로 CI를 확증 근거로 사용하지 않는다.

## 5. 입력별 SFT·3D 대조·확대의 연결

이번 학습은 0이다. 이는 기본 모델이 실패해서 적응을 생략한다는 뜻이 아니다. 실제 관측에 맞는 supervision이 확인되지 않아 잘못된 slice 정답을 만들지 않는 경계다.

후속 method pilot의 첫 후보는 같은 전체 sequence 보고서를 target으로 하고 전체 관측의 개별 feature 처리와 인접 묶음 처리를 비교하는 직접 적응이다. 전체 보고서를 각 slice에 복제하지 않는다. 공식 region/report에 근거한 국소 target이 실제 확인되면 그 범위에서 두 입력에 동일 target을 제공하는 대안이 가능하다. 어느 경로가 가능한지 자료 감사에서 명시하고 다음 계획에서 학습량·동작 확인·생성 milestone을 고정한다.

SFT는 base와 각 입력별 adapter를 분리하고 같은 환자·target 노출·적응 범위를 맞춰야 한다. 실제 weight update·loss mask·저장 재로딩·생성 개선을 확인한다. frozen 점수 미달이나 LoRA 한 설정의 무개선만으로 전체 질문을 종료하지 않는다.

AutoRG는 기존 환경·가중치 manifest와 공식 `region_segtool`의 예측 mask 경로를 우선 확인한다. 이번에는 source·checkpoint·학습 split·입출력 적합성까지만 기록하며 과거 val15 출력으로 새 성능을 대신하지 않는다. 다음 실제 3D 비교에서는 같은 sequence 범위의 보고서 항목을 사용하고 전체 volume 해상도·학습 노출 차이를 밝힌다. GT mask 경로는 별도 oracle다.

본격 확대·독립 확인은 이번 개발 결과와 자료 접근 비용으로 표본 규모를 산출한 별도 계획이다. 이번 최대 6명은 독립 test가 아니며 추가 seed·전체 데이터 실행을 자동 승인하지 않는다.

## 6. 자원·비용·재개

실행 직전 nvidia-smi와 상속 GPU 집합을 확인한다. 처음에는 두 GPU에 독립 요청을 분배한다. 기술 입력에서 GPU당 1 worker와 batch 확대 또는 GPU당 2 worker 중 유망한 구성을 비교한다. 동시 peak 합과 기존 점유에 worker당 2GiB 여유가 있어야 한다.

loading 포함 처리량, 조건별 요청 시간, 긴 출력 지연, GPU peak·CPU/RAM/I/O·OOM을 기록한다. 기존 8장 또는 presence 요청 속도를 이번 전체 판독 시간으로 대입하지 않는다. 환자별 Zi가 고정되면 총 요청 `sum(Zi+ceil(Zi/5))`를 산출하고 실측 처리량으로 예상 wall-clock을 갱신한다. 임의 시간 상한은 두지 않는다.

모든 새 결과는 `research/results/iter_140/`에 둔다. 요청별 고유 ID·원자적 claim·worker별 출력·completion hash를 사용하고 완료 요청은 재생성하지 않는다. 이전 큐·결과·checkpoint를 변경하지 않는다.

# Implementation Tasks for Claude

현재 구현 담당은 Codex다.

1. iter_139 보존 SHA와 선별 반입 파일을 확인하고 미실행 학습을 완료로 표시하지 않는다.
2. 기존 접근 실패의 원인을 읽은 뒤 현재 승인 경로의 추가 증거만 확인한다. 이용·release·sequence 연결 결과를 남긴다.
3. 연결이 성립하면 후보·reference spans·S/A slice 목록·질문·통합·평가 규약을 출력 전에 잠근다.
4. 새 입력에 필요한 실행 경로만 파생하고 공식 tensor·출력 경계·재개 검사를 수행한다.
5. 두 GPU로 실제 판독을 생성하고 원문 근거가 있는 paired 내용 평가와 비용을 보고한다.
6. 입력별 SFT의 가능한 supervision 단위와 AutoRG의 노출·지원 조건을 기록한다. 미실행 비교를 명시하고 독립 리뷰로 넘긴다.

# Evaluation (성공/실패 기준 포함)

양성 탐색은 A−S 환자 평균 recall ≥5pp이고 명시 모순 증가 ≤5pp인 경우다. 소수 환자 결과이므로 방법 효과나 신규성을 확정하지 않는다. 이 기준과 미판정 최선·최악 범위가 충돌하면 불확정이다.

음성은 유효한 비교에서 frozen 인접 처리 이득을 확보하지 못한 경우다. 두 조건의 잔여 오류와 supervision 가능성을 보고 직접 SFT pilot의 가치 또는 단순 대안 충분성을 판단한다. 모든 음성 결과를 새 loss로 연결하지 않는다.

자료·입력 연결 실패는 실행 실패다. 다음 조치는 실제 접근 요건 해결 또는 영상–소견 정답이 연결된 대안의 한정 제안이며 MSD 유무 학습으로 자동 복귀하지 않는다.

종료 시 이번 실제 실행, 미실행 SFT, 미실행 3D 성능 비교를 구분한다. 준비만 끝났다면 연구 관찰을 얻었다고 보고하지 않는다.

# Risks / Checks

- 공식 카드의 MIT 표기는 원천 MRI 이용 조건과 다르다.
- sequence 보고서와 병변 mask는 slice별 임상 정답을 제공하지 않는다.
- train의 AutoRG 노출과 기존 반복 개발 이력 때문에 독립 일반화를 주장하지 않는다.
- 개별/인접 설명의 길이·요청 수가 다르므로 소견 recall과 모순·비용을 함께 본다.
- 미언급과 실제 음성, reference 미확인과 임상 허위를 구분한다.
- 같은 접근 장애가 남으면 자료 감사만 반복하지 않고 필요한 권한·연결 증거를 구체적으로 보고한다.

## 대규모 GPU 필요 후보

전체 3D volume encoder와 언어 모델의 공동 판독 사전학습은 장거리 공간 정보 보존을 직접 다룰 수 있지만 현재 두 24GB GPU에서 전체 학습하기에는 메모리·자료 비용이 크다. 지금은 동일 관측의 직접 적응과 기존 3D 시스템을 비교하며, 이 후보는 잔여 실패 근거가 생길 때만 검토한다.

# 계획의 근거 (GPT 조사 노트)

### 새로 확인한 사실

- iter_139의 구현 보고서는 없고 `research/results/iter_139`도 없다. checkpoint `3fb452dc0e53ebbbf26c0f9437afca348c18ea39`는 추론 관련 5개 파일을 보존한 unreviewed 중단본이다. 학습 완료 근거가 아니다.
- `iter_083/review.md`는 train 161 scan·159 prefix, 8명 보고서 검토, 익명 mapping 다운로드 403 및 모델 미실행을 기록한다. `iter_135/review.md`에서도 공식 report key 연결과 영상 release 동등성·이용 근거를 명확히 구분했다. 현재 접근이 해결됐다고 주장할 근거는 없다.
- 로컬 `modal_wise_finding.json`은 920개 sequence key→문자열 사전이다. `train_review8.json`의 실제 FLAIR 문장은 병변 위치·신호·부종·구조 변위를 기술하지만 slice별 정답은 아니다. 일부 문장은 global 설명을 참조하거나 모호한 mixed 표현을 사용한다. 계획 조회 중 split 파일의 첫 test ID와 첫 modal 항목도 표시됐으므로 공식 test 무노출을 주장하지 않는다. 이번 선택은 저장된 train 8명으로 한정한다.
- [AutoRG 공식 구현](https://github.com/ljy19970415/AutoRG-Brain)은 sequence별 보고서 평가, 예측 segmentation을 사용하는 `region_segtool`, 제공 mask 경로를 구분한다. RGv2는 RadGenome 학습을 명시한다. 따라서 train에서의 전문 모델 출력은 독립 일반화 성능이 아니다.
- [RadGenome 공식 카드](https://huggingface.co/datasets/JiayuLei/RadGenome-Brain_MRI/blob/main/README.md)는 MIT metadata만 제공한다. 이것만으로 원천 BraTS 영상의 이용 조건을 대체할 수 없다.
- iter_070의 환경·가중치·공식 source는 results에 남아 있다. 기존 wrapper는 재개·배타성·공식 경로 대조 결함 때문에 그대로 승인되지 않았다. 현재 과제에서 사용하지 않는 HIGH/MIXED 평가기는 복구하지 않는다.
- iter_097 원 리뷰는 낮은 LR의 판독 SFT에서도 사전 확대 기준 미달과 의미 평가 불확실성을 기록한다. bbox 학습 성과를 판독 개선으로 간주하거나 같은 X-ray 실험을 반복할 근거가 없다.

### 의미

현재 확정 가능한 선택은 RadGenome 자료 연결과 동일 전체 관측의 첫 판독 비교를 묶는 것이다. slice별 보고서 SFT를 지금 구체화하면 잘못된 supervision을 만들 위험이 있다. 이번 진단의 성적이 낮다는 이유로 적응을 생략하지 않되, 학습 단위와 정답 연결을 검증한 별도 method pilot으로 이어간다.
