# 요약

- 이번에 할 일: 기존 MR-RATE T2 기술8명·탐색40명에서 정규화만 바꿔 실제 MedGemma 출력을 비교한다.
- 필요한 이유: 공식 기술 보고서의 volume min–max와 현재 brain percentile1–99가 다르며, 기술8명에서 강도 범위 차이를 직접 확인했다.
- 확인할 기준: 환자별 양·음성 판별의 회복, paired BA 차이, 입력·생성 재현성이다.
- 주의·다음: 새로운 방법의 개발이 아니다. 양성이면 입력 처리의 효과로 보존하고, 음성·불확정이면 이 설명 경로를 종료한다.

## 알림 맥락

- 연구: MRI 영상 근거 활용
- 데이터: 뇌 T2 MRI, MR-RATE 기존 기술8명·개발40명
- 모델: MedGemma 1.5 4B, 학습 없음
- 과제: 동일한 axial T2 8장을 받아 양측 측뇌실 확장 여부를 출력
- 가설: 현재 정규화와 공식 기술 보고서의 정규화 차이가 고정 양성 응답에 기여할 수 있음
- 질문: MRI 밝기 범위를 정하는 방식만 바꿔도 환자별 판단이 회복되는가?
- 변경: 구체화
- 연결: 이전 균등·해부학 선택은 모두 BA0.50이었다. 이번 조사에서 확인한 정규화 차이만 별도 개입으로 검증한다.
- 작업: 기존 환자·slice·질문을 유지한 단일 대조로 입력 처리의 설명력을 판단한다.

# Current Understanding

iter_128의 유효한 음성 결과와 U/A 설계 종료를 유지한다. 원 계획은 `agent/runs/iter_128/plan.md`, SHA256 `5bf718c155391aa7e07197f7d23af5aff77601422254411ef179fdaa2031b11b`다. 이번은 기존 sampling 가설의 복구가 아니라 정규화라는 새 요인에 대한 별도 진단이다.

[MedGemma 1.5 기술 보고서](https://arxiv.org/html/2604.05081v1#S2.SS3.SSS1)는 MRI에 volume min–max를 기술한다. 현재 코드는 brain 내부 percentile1–99를 사용한다. 이를 현재 결과의 원인으로 단정하지 않는다. 공식 방식으로 강도 정규화만 맞추며 모든 학습·평가 조건을 재현했다고 부르지 않는다.

유지: 기존 환자·역할·보고서 정답·series·U index·방향·896 canvas·prompt·모델 revision·greedy 생성·parser. 변경: M 조건의 강도 정규화 하나. 보류: A selector, SynthSeg 실패5명 복구, 새 환자, prompt 탐색, SFT와 head 학습. 과거 결과·소스·판정은 보존한다.

# Strategy Check / 연구 방향 판단

카드 출처는 iter_128 리뷰다. `mri-volume-evidence-use`를 유지한다.

1. 중요한 문제: 고정 응답을 모델의 근거 활용 한계로 해석하기 전에 실제 입력 처리의 기여를 분리해야 한다.
2. 현재 근거: 올바른 뇌 입력의 U/A는 전원 양성이다. 새 근거는 공식 문서와 실제 정규화의 차이 및 기술8명의 강도 범위 차이다. 성능 영향은 미검증이다.
3. 쉬운 해결책: 정규화는 추가 학습 없는 대안이다. 과거 직접 적응의 성공은 단순 분류기 이후의 VLM 가치를 보장하지 않았으므로 학습을 먼저 발주하지 않는다.
4. 남은 설명: 정규화 영향, 제한된 관측, 기본 인식, 질문 인터페이스, 보고서 정답의 한계다. 이번에는 첫 설명만 조작한다.
5. 다음 결정: 양성이면 입력 처리 효과를 보존하고 방법 투자를 보류한다. 음성·불확정이면 이 경로를 종료하고 전문 대안 이후의 잔여 조건을 갖춘 질문에만 후속 투자한다.

선택 이유는 반복 횟수나 GPU 비용 절감이 아니라 확인된 차이를 직접 조작할 수 있다는 점이다. 새 MRI 과제의 준비나 전체 모델 설치보다 현재 판단에 가까운 증거를 제공한다.

# Hypothesis

H1: percentile clipping·재스케일링이 환자별 판별을 손상시켰다면 M에서 명시적 음성의 올바른 회복과 양성 보존이 함께 나타난다.

H2: 다른 요인이 지배적이면 M에서도 고정 응답이 유지되거나 BA가 의미 있게 회복되지 않는다. 단지 PRESENT가 ABSENT 또는 UNCERTAIN으로 일괄 이동하는 것은 H1의 충분한 근거가 아니다.

M은 전체 원 T2 volume의 finite voxel 최솟값과 최댓값으로 `255*(x-min)/(max-min)`을 계산하고 기존 반올림·uint8·동일 RGB 렌더링을 적용한다. brain mask로 min/max를 제한하거나 percentile·slice별 normalization·z-score를 추가하지 않는다. 상수·비finite volume은 입력 오류로 처리하며 다른 방식으로 조용히 대체하지 않는다.

# Limitation Evidence / Correct Usage Checks

대상은 `mrrate-t2-ventricle-fixed-positive-response`, observed다. 원 리뷰는 blocking issue가 없고 processor·revision·뇌 연결·EOS·내용 응답을 검증했다. 정규화 차이는 새로운 확인 사항이며 원 관찰을 무효화하지 않는다.

기술8명의 percentile 범위/전체 범위는0.5003–0.6541이었다. 이는 모델 입력 차이의 근거이지 임상 소견 가시성이나 원인의 증명은 아니다.

이번에도 보고서 기반 일치도만 평가한다. 영상 판독으로 임상 정답을 새로 만들거나 전문 segmentation을 병변 정답으로 쓰지 않는다. FLAIR 관찰은 별도 조건이며 이번 T2 결과로 정정하지 않는다.

# Contribution Path / Baselines / Reuse

새 기여는 미확정이다. 양성 결과는 단순 사용 조건의 중요성을 설명한다. 이 결과만으로 새 방법 pilot 또는 full 개발을 승인하지 않는다.

주대조 P는 원 U8장의 percentile 입력이다. M은 강도만 다르다. 정보량·모델·생성 예산은 같다. 전문 S의 기존35명 결과는 참고치로만 유지하며 누락5명과 전체 volume 입력 이점을 명시한다.

현재 브랜치 HEAD와 실제 파일을 확인했고 관련 code_assets를 읽었다. 구조화 `reuse_assets`의10개 파일을 선별 반입한다. 승인 범위는 현재 manifest의 렌더링·parser·metric에 한정된다. 기존 `mr128_gen.py`를 한정 확장하여 재사용하고 새 실행기를 통째로 중복 작성하지 않는다. OUT·요청 조건·정규화를 명시적 설정으로 분리하되 과거 기본 동작을 유지한다. 전이 import용 mr127 파일의 선정·설치·segmentation entrypoint는 실행하지 않는다.

# Proposed Experiment

## 1. 동작 확인: 기존 기술8명

`results/iter_128/evaluation_manifest.json`과 `all_inputs.json` 및 각 build 기록으로 환자·series·U index·원 NIfTI·보고서 정답 출처를 잠근다. 환자와 역할을 재배정하지 않는다.

P/M 각8건, 총16건을 생성한다. P PNG는 기존 U와 pixel/hash가 같아야 한다. M은 서로 독립적인 NumPy 계산으로 min/max와 정규화 값을 검산한다. 같은 영상의 방향·물리 비율·canvas·slice 순서가 유지되는지 검사하고 양 조건 montage를 기술 검사용으로 남긴다. contrast를 보고 조건·환자를 선택하지 않는다.

모델은 `google/medgemma-1.5-4b-it`, revision `91850547d9f0b2fdd21aa7c5f4f3d24d15fed62f4fc9d`가 아니라 기존 검증값 `91850547d9f0b2fdd21aa7c5f4f3d1a8a52c243b`를 정확히 사용한다. bf16, eval, greedy, seed125, batch1, max_new_tokens512와 원 U prompt를 유지한다. 구현 config에는 검증된 revision 하나만 기록한다.

정확도는 기술 통과 조건이 아니다. 입력 연결·정규화·processor·출력 저장·EOS·재개만 확인한다. cap에 닿은 기술 응답이 있으면 양 조건 전체를1024로 한 번 재검사하고 새 결과로 보존한다. 계속 truncation이면 설계를 중단한다.

P 기술8명의 재생성 token이 원 기술 U와 같으면 탐색 P40 저장 출력을 재사용한다. 다르면 먼저 tensor·package·generation config·provenance를 확인한다. 오류를 해소하지 못하면 중단한다. 오류 없이 수치적 재현 차이가 남는다면 탐색 P/M을 같은 환경에서 모두 새로 생성하며 원 출력은 참고로 유지한다. 한 조건만 유리한 실행 결과를 골라 쓰지 않는다.

## 2. 가능성 탐색: 기존40명

기술 무결성 통과 후 양성20·음성20 전원을 평가한다. 이 집단은 반복 개발 집단이며 독립 test가 아니다. 기본 신규 생성은 M40건이다. 중간 정확도에 따른 조기 중단·표본 선택·정규화 변경은 없다. A·calibration12명·새 모델은 실행하지 않는다.

## 3. 규모 확대

이번에는 추가 환자·학습·다중 seed로 확대하지 않는다. 기존40명 전체의 paired 비교가 이번 결정을 위한 본실험이다. 양성일 때도 자동 확대하지 않는다.

## 4. 독립 확인

이번 범위에는 없다. 양성 결과가 후속 투자 결정을 바꿀 만큼 중요하고 전문 대안 이후의 잔여 가치가 구체적이면 미사용 환자 확인을 별도 계획으로 제안한다.

## 자원·시간·재개

실행 직전 nvidia-smi로 허용 GPU0,1의 여유를 확인한다. 기본은 각 GPU batch1 worker1개다. iter_128의 GPU 전체 peak9,775/9,703MiB는 참고이며 이번 peak를 다시 측정한다. 다른 점유와 worker별 최소2GiB 여유를 포함해 안전하게 들어갈 때만 GPU당2 worker를 검토한다.

iter_128의 batch2는 token10/16 불일치가 있어 이번 batch 확대의 근거로 쓰지 않는다. 작은 본실험에서는 추가 처리량 비교의 적재 비용이 절약 시간보다 클 수 있으므로 기존 실측과 기술16건으로 이를 계산한다. 이득이 예상되면 같은 기술 요청 최대16건으로2-worker/GPU 구성을 비교한다. token 정합성·전체 요청/분·peak·긴 응답 지연·CPU/RAM/I/O·OOM을 확인해 선택한다. 이득이 없거나 여유가 부족하면 구체적 근거와 함께 기본 배치를 유지한다.

원 실측80요청194.84초를 선형 적용한56요청의 생성 구간은 약136초라는 참고 추정이다. 적재·렌더링·검증은 포함되지 않는다. 실제 기술 처리량으로 전체 wall-clock 예측을 갱신하고 임의 시간 상한은 두지 않는다.

고유 request ID, 조건별 pixel/config hash, worker별 JSONL, 원자적 claim과 완료 봉인을 사용한다. 중단 시 완료 출력은 보존하고 미완료 ID만 재개한다. 새 결과는 `research/results/iter_129/`, 필요 영상 산출물은 `/home/test/.local/share/medgemma/mr_rate/iter129/`에 둔다.

# Implementation Tasks for Claude

현재 구현 담당은 Codex이며 이 섹션명은 호환용이다.

1. 기준 계획·리뷰·reuse_manifest를 읽고 지정 파일만 재사용한다. 과거 입력·출력·설정의 hash를 잠근다.
2. 기존 렌더러에 명시적 정규화 선택을 연결한다. P의 원 동작을 보존하며 M의 min/max·출력 hash·강도 통계를 기록한다.
3. 기존 실행기의 이번 결과 경로와 요청 수를 설정화한다. 기존 segmentation·선정·설치 경로를 호출하지 않는다.
4. 입력 차이 검산, 공식 processor tensor 연결, 기술 재현, config 변경 거부, 중복·누락 및 부분 재개 검사를 실행한다. 필요한 회귀만 검사한다.
5. 기술8명 이후 고정40명 비교를 완료하고 원시 응답에서 BA·전환표·CI를 계산한다. 기존 `mr128_eval.decision`의 sampling 판정은 호출하지 않고 이번 계약을 별도 적용한다.
6. 출처·실제 요청량·실행 시간·비용·미완료·판정 범위를 보고하고 소스 체크포인트는 orchestrator가 보존하도록 넘긴다.

# Evaluation (성공/실패 기준 포함)

Primary는 report-agreement BA와 M−P다. UNCERTAIN·INVALID·거부는 각 정답 class의 분모에 남겨 오답으로 센다. sensitivity·specificity·strict/loose·EOS·상태 전환표와 양방향 정오 전환을 모두 보고한다. batch×label 층화 환자 bootstrap10,000회, seed125를 유지한다.

- 양성: ΔBA≥0.15, paired95% CI 하한>0, M BA≥0.75, sensitivity·specificity 각각≥0.65. 입력 정규화의 제한된 회복 근거로 판단한다. 단순 답변 성향 이동만으로는 충족하지 않는다.
- 음성: M BA≤0.60이고 ΔBA CI 상한<0.15. 현재 조건의 의미 있는 회복 설명을 기각하고 이 경로를 종료한다.
- 불확정: 나머지 유효 결과. 차이·정밀도를 보존하고 투자 보류한다. 같은 집단의 추가 조건 탐색은 하지 않는다.
- 실행 실패: 입력·출처·processor·완료 무결성이 해결되지 않음. 이를 가설의 음성 결과로 바꾸지 않는다.

최소 가치 있는 개선 폭15pp는 작은 전처리 반응과 실용적 판별 회복을 구분하기 위한 사전 기준이다. 비용은 원 NIfTI 읽기부터 답 저장까지 비교하며 모델 적재를 별도 보고한다. 전문 S와의 전체 비용 우위는 이번에 주장하지 않는다.

# Risks / Checks

- 공식 min–max의 기술은 이 데이터에서의 최적성 증거가 아니다. 이번은 한 전처리 요인의 개입이다.
- 기존 보고서 약한 정답과 일부 slice의 관측 충분성은 남는다. 효과를 임상 정확도·MRI 전체 능력으로 일반화하지 않는다.
- 기술8명의 강도 차이는 성능을 보고 선정한 근거가 아니다. 본 비교 환자·질문·index는 바꾸지 않는다.
- 저장 대조의 재현성 검사가 실패하면 이유 없이 그대로 비교하지 않는다. 필요 시 같은 환경의 P/M 동시 재측정을 사용한다.
- 현재 SynthSeg 누락·admission 결함은 사용하지 않는 경로다. 이를 고치기 위한 별도 반복을 만들지 않는다.
- HF cache·기존 결과·기본 환경을 수정하지 않는다. 새 설치가 필요하면 승인된 격리 환경 원칙을 따른다.

## 대규모 GPU 필요 후보

여러 MRI sequence·기관의 volume–report 자료로 vision encoder와 언어 연결부를 공동 적응하는 후보는 보존한다. 3D 관측과 시각 표현을 함께 조정하려면 현재 단일 요인 비교보다 큰 자료·메모리·학습 비용이 필요하다. 이번 진단으로 필요성이 입증되는 것은 아니며 실행하지 않는다.

# 계획의 근거 (GPT 조사 노트)

## 새로 확인한 것

- `agent/runs/iter_128/review.md`와 원 `review.json`을 확인했다. U/A80건 모두 PRESENT·EOS이며 BA0.50이다. 선택 변경은12명, fallback은28명이다. SynthSeg BA0.941176은 완료35명에 한정되며 전체 대안 충분성은 미확정이다.
- `agent/LIMITATIONS.md`의 `mrrate-t2-ventricle-fixed-positive-response`는 observed이며 현재 결론의 blocking issue는 없다. 정상 사용 검사는 processor·revision·생성·뇌 연결을 포함하지만 정규화와 학습 전처리의 일치까지 입증하지는 않는다.
- [MedGemma 1.5 Technical Report §2.3.1](https://arxiv.org/html/2604.05081v1#S2.SS3.SSS1)은 MRI에 volume별 min–max 정규화와 동일 RGB 채널을 기술한다. 이는 모든 MR-RATE 입력에서 이 방식이 최적이라는 증거는 아니다.
- 실제 `research/mr123_data.py:intensity_window`는 `a[brain_mask]`의1·99 percentile을 사용하며 `render_slice`에서 clipping한다. iter_123·125~128 계획에도 이 조건이 명시돼 있다. 기존 기록을 소급 오류 처리하지 않는다.
- 파일 생성·모델 실행 없이 기존 기술8명의 NIfTI를 읽어 집계했다. percentile 범위/volume 전체 min–max 범위는 5SWPQWD3DD0.6541, CBMKOIU2HE0.5094, PCKMK46BRL0.6274, A7Y34TEQFY0.5003, 7ISDTZ2JVG0.5428, M74CZWNJXJ0.6335, IW5AJJDVN70.5360, IMMJZDDMDC0.5189다. 영상 대비 차이는 확인됐지만 성능 영향은 가설이다.

## 대안 판단

- iter_077 원 리뷰에서 영역 직접 SFT는 prior보다 좋았지만 MAE0.77690으로 분류기0.77619 대비 이점이 미확정이었다. 따라서 고정 응답만을 근거로 새 LoRA를 발주하지 않는다.
- iter_066 원 리뷰에서 scoring은 공동 생성 BA0.08255를0.55319로 회복했지만 위치 prior0.76553보다 낮았다. 새로운 문자열·threshold 탐색의 일반적 가치는 입증되지 않았다.
- [MR-RATE 공식 contrastive-pretraining 안내](https://github.com/forithmus/MR-RATE/blob/main/contrastive-pretraining/README.md)는 MRI 분류·linear/MIL probe 경로를 제공한다. 이번 조사에서는 사용 가능한 적합 checkpoint·노출·동일 입력 비교를 확정하지 않았으므로 즉시 강한 대조군으로 실행 발주하지 않는다.
- [NeuroVFM 공식 저장소](https://github.com/MLNeurosurg/neurovfm)도 MRI 전문 대안 후보이나 이번 측뇌실 문구와 출력 ontology의 직접 대응은 미확인이다. 모델 설치 자체를 다음 연구 질문으로 삼지 않는다.

## 보존과 범위

현재 HEAD는 `252dd607ec046ec7123f78ae1a832e06c8561293`이며 작업 트리는 clean이다. `agent/CODE_ASSETS.md`와 iter_128·127 원 code_assets를 확인했다. 렌더링·metric의 제한 승인과 선정·segmentation의 needs_fix를 구분했다. 이번 입력 개입은 새로운 방법이 아니며 공식 학습 전처리 전체의 재현도 아니다. 같은 개발40명에서 얻는 한정 원인 비교이고 독립 확인·임상 정확도 주장은 없다.
