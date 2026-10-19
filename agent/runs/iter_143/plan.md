# 요약

- 이번에 할 일: 전체 DWI 정답을 한 번 사용하는 개별·인접 attention SFT와 native 전체 sequence SFT를 비교한다.
- 필요한 이유: frozen 판독과 전문 시스템 비교는 완료됐지만 과제 적응 뒤에도 문맥 차이가 남는지는 미검증이다.
- 확인할 기준: 실제 생성의 항목 회복, 모순·절단, 영상 의존성과 비용을 함께 판단한다.
- 주의·다음: attention을 제한한 비교이며 native 2D 대 3D의 인과 실험은 아니다. pilot 결과로 후속 투자 하나를 선택한다.

## 알림 맥락

- 연구: MRI 동일 관측 범위의 판독 대조
- 데이터: RadGenome–ISLES22 뇌 DWI MRI와 연결된 공개 소견 문장
- 모델: MedGemma 1.5의 언어층 LoRA 직접 적응
- 과제: 같은 전체 DWI 영상을 받아 DWI 범위의 소견 보고서 하나를 생성한다
- 가설: 과제 적응 이후에도 인접 영상의 국소 문맥화가 세부 소견 보존에 도움이 될 수 있다
- 질문: 같은 영상과 정답으로 학습해도 인접 슬라이스를 함께 처리하면 누락이 줄어드는가?
- 변경: 구체화
- 연결: 전문 AutoRG의 우위도 불확정이어서 전체 정답을 사용하는 직접 적응으로 남은 설명을 구분한다
- 작업: 개별·인접·native attention을 같은 조건으로 학습하고 실제 생성으로 후속 투자 여부를 정한다

# Current Understanding

iter_141은 개발6명에서 개별/인접 입력의 항목 일치율 45.65%/34.25%를 관찰했으나 절단·미판정 때문에 우열이 불확정이었다. iter_142의 AutoRG는 46.55%로 개별 MedGemma 대비 +0.89pp이며 전문 대안의 충분성도 불확정이다. 두 원 판정과 출력은 유지한다.

공개 정답은 전체 DWI sequence에 연결된다. 전체 보고서를 각 slice의 정답으로 복제하지 않는다. 기존 8명은 이미 사용한 개발 이력이며 새 분할에서 제외한다. MSD 중심 유무 학습과 bbox supervision은 보류 상태를 유지한다.

이번에는 국소 판독문을 먼저 생성하고 고정 통합하던 경로에서, 국소 attention 표현을 공통 보고서 생성부가 읽는 경로로 바뀐다. 기존 141 점수와 새 점수의 차이를 순수 SFT 효과로 계산하지 않는다. 새 구조 안의 적응 전후 비교를 사용한다.

# Strategy Check / 연구 방향 판단

출처는 iter_142 review와 iter_143 think/round_01.json이다. research_track은 mri-volume-evidence-use를 유지한다.

1. 중요한 문제: 동일 관측·정답으로 학습한 뒤에도 공간 문맥 처리에 따라 세부 소견 보존이 달라지는가?
2. 현재 근거: 유효한 frozen 출력 문제와 전문 대조가 있다. 이번 조사에서는 mask 주입 지점과 생성 cache의 별도 검증 필요성을 확인했다.
3. 쉬운 해결책: native 전체 sequence 직접 SFT가 강한 직접 대안이다. 이를 빼고 제한 attention의 작은 차이를 기여로 주장하지 않는다.
4. 남은 설명: 적응 부족, 국소 문맥 효과, attention 제한 손상, 보고서 prior다. 동일 target의 S/A/N과 영상 교환으로 구분한다.
5. 다음 결정: 적응 효과 및 A의 잔여 가치가 있으면 한정 재현을 검토한다. N으로 충분하거나 제한 설계가 손상되면 해당 설계를 보류한다. 현재 학습 recipe의 실패와 MRI 질문의 가치는 별도로 판단한다.

# Hypothesis

H1: 과제 적응 부족이 주원인이면 S/A/N 모두 적응 전보다 생성이 개선되고 A−S 차이는 작아진다.

H2: 인접 slice의 국소 문맥화가 유용하면 같은 전체 관측·target에서 A가 S보다 위치·형상·분포 항목을 더 회복한다.

H3: attention 제한이 주된 손상이면 N이 개선되지만 S/A는 뒤처진다. 이때 결과는 국소 제한 설계의 문제이며 MRI 공간 정보의 무용성이 아니다.

H4: 보고서 prior가 개선의 주원인이면 환자 간 영상을 교환해도 정답 항목 회복이 거의 유지된다. 이 경우 영상 이용 개선 주장은 보류한다.

# Limitation Evidence / Correct Usage Checks

대상은 observed `radgenome-dwi-adjacent-report-output`이다. iter_141의 full review는 valid_experiment=true, blocking_issues=[]이며 공식 tensor, 입력 hash, 요청 누락·중복, 원문 인용 연결을 검증했다. method pilot 진입에 사용하되 validated나 내부 원인 증명으로 올리지 않는다.

새 학습에서 필수 검사는 다음과 같다.

- 원문 report–환자/session–DWI 연결, split 중복 및 이전 개발8명 제외.
- DWI target의 원문 span과 대상 범위. ADC·확산 제한·병인·시기 및 애매한 관계는 제외하거나 미판정으로 남긴다.
- 동일 image tensor·순서·position·target token·loss 가중치. mask나 파일명의 소견이 입력으로 누설되지 않게 한다.
- attention 허용 관계, 간접 정보 우회, target causal mask, 실제 gradient와 parameter update, 저장·재로딩·재개.
- 생성 cache와 no-cache의 logits 및 greedy token 동등성. 긴 입력에서의 실제 peak와 출력 종료 원인.

# Contribution Path / Baselines / Reuse

신규 방법 기여는 미확정이다. 이번 구조는 공정한 supervision 아래 국소 문맥의 정보 가치를 확인하는 pilot 장치다. native 직접 SFT N이 필수 baseline이며, N이 정확도·비용에서 충분하면 새 제한 구조의 개발을 확대하지 않는다.

train-only 고정 보고서 prior도 둔다. T24 target 가운데 다른 T24 target의 사전 고정 항목 집합과 평균 Jaccard가 가장 높은 보고서 하나를 선택하고 동률은 ID 순으로 정한다. 평가 자료로 문장을 선택하지 않는다. 이는 영상 없는 prior이며 임상적 대안으로 과장하지 않는다.

AutoRG의 기존 결과는 전문 대안이 모든 세부 소견을 회복하지 못했다는 참고 근거다. 노출·해상도·학습량이 다른 기존6명 결과를 새 E16의 직접 성능 대조로 사용하지 않는다. 이번에는 AutoRG 재실행이 없다.

현재 branch의 기반 SHA는 b6ba0f1d2312947199048f3e59772f91c9f7ff1b다. i141_common.py, i141_preflight.py, i141_select_download.py, i141_data.py의 필요한 자료 기능만 새 경로와 manifest를 받도록 분리한다. i141_data.py의 LOCATIONS·고정 환자 목록은 새 정답 생성에 사용하지 않는다. i141_run.py의 최대5장 요청·stage 의존성은 새 학습에 맞지 않으므로 일반 학습 실행기로 간주하지 않는다. i141_judge.py/i142_judge.py는 가져다 쓰는 평가기가 아니다.

iter_139 checkpoint의 보존 목록에는 이번 구조에 사용할 완성된 학습기가 확인되지 않았다. 외부 파일 반입 없이 새 attention·학습 경로를 구현한다. 기존 자산을 삭제하거나 원본을 수정해 과거 결과를 바꾸지 않는다.

# Proposed Experiment

## 1. 한정 자료 연결과 split 고정

공식 train metadata에서 이전8명을 제외하고 DWI에 명시적으로 연결된 target을 구성한다. 영상 반입 전에 target 변환 규칙과 제외 이유를 고정한다. 원문에 있는 DWI 신호 및 같은 병변의 위치·형상·분포만 사용한다. 문장을 임의로 완성하지 않으며 애매한 대상 연결은 제외 사유로 남긴다.

적격 목록을 위치의 단측/양측, 소견 분포의 단일/다중 기술 여부로 층화하고 seed17로 T24/V8/E16을 고정한다. 희귀 유형은 가능한 한 포함하되 환자 중복은 허용하지 않는다. 공식 val/test는 이번에 개방하지 않는다. E16은 이번 적응의 선택에서 보존한 집단이지 foundation model의 학습 미노출을 보장하는 외부 test가 아니다.

T24는 장시간 전체 sequence 학습의 신호를 확인할 탐색 규모다. V8은 생성 추세를 보며 E16은 큰 차이와 실패 유형을 확인한다. E16만으로 5pp 차이의 정밀한 확증을 기대하지 않는다. 적격48명이 확보되지 않으면 임의로 threshold를 낮추거나 다른 자료로 교체하지 말고 실제 부족 범위를 보고한다.

기존 선택 ZIP 반입 경로를 사용해 해당 환자의 DWI·sidecar·mask만 확보한다. 다운로드 전 선택 member 압축/해제 크기와 feature cache·checkpoint 공간을 합산한다. 전체 snapshot을 받지 않는다. 공식 이용 조건과 release 근거는 기존 기록에서 계승하고 변경 여부·새 환자 연결만 확인한다.

## 2. 실제 개입: 전체 sequence 아래 국소 attention

세 조건의 token sequence는 완전히 동일하다. 모든 유효 axial slice를 원 순서로 사용하고 동일한 중립 slice/물리 위치 표기와 공식 processor를 적용한다. 입력 렌더링은 기존256 정방형 규칙을 계승하며 processor 출력 해상도·crop 수를 기록한다. 관측 수를 줄이지 않는다.

S는 slice 하나를 국소 group으로, A는 첫 유효 slice부터 연속 최대5장을 하나의 group으로 둔다. N은 native attention을 유지한다. A 내부도 native 허용 관계를 유지하므로 image 간 완전 bidirectional attention을 새로 추가하지 않는다.

S/A의 layer별 mask는 native full/sliding mask와 다음 제한의 교집합이다.

- 영상 이전 공통 prefix는 prefix 내부에만 접근한다.
- image token, image delimiter, slice 표기 등 국소 token은 공통 prefix와 같은 group에만 접근한다.
- 구간 사이의 텍스트를 전역 중계 token으로 남기지 않는다. 모든 token을 prefix/local/report로 명시 분류한다.
- 마지막 보고서 지시·assistant header와 생성 target은 보고서 영역이다. 이 영역은 native full layer에서 전체 앞선 관측을 읽고 sliding layer에서는 기존 window를 유지한다.
- 국소 token은 보고서 영역이나 다른 group에 접근하지 못한다. target은 미래 target을 보지 못한다.

따라서 전체 sequence loss가 국소 시각 token을 문맥화하는 언어층 LoRA까지 연결되지만, 국소 표현 사이의 상호작용 범위만 달라진다. 보고서 영역에서 전역 통합은 S/A 모두 허용된다. 이 실험은 전역 통합 가능 여부가 아니라 그 이전 국소 문맥화의 추가 가치를 시험한다.

position_ids·RoPE·sliding/full layer 구성·정규화·logit 처리·기본 가중치는 동일하게 유지한다. 기본 환경의 transformers 파일은 수정하지 않고 연구 코드의 명시적 wrapper로 구현한다.

## 3. 동작 확인

T24 안의 두 환자로 학습·재로딩 경로를 확인하고, T24에서 token 길이가 가장 긴 환자로 메모리를 검사한다. 이 단계의 overfit은 일반화 근거가 아니다.

작은 token 예제에서 dense reference mask와 실행 backend의 forward 및 gradient를 비교한다. 다른 group의 pixel을 바꿨을 때 S/A의 해당 group 외 국소 hidden state가 변하지 않는지 확인한다. A에서는 같은 group의 이전 slice 변경이 허용된 경로로 전달될 수 있어야 한다. 모든 group에서 report loss로부터 국소 hidden state에 gradient가 연결되는지 검사한다. mask를 바꿔도 계산이 동일한 잘못된 구현을 배제한다.

기본 조건을 native로 설정했을 때 공식 forward와 수치 허용오차 내 일치를 확인한다. cache/no-cache 비교는 prefill과 여러 decode step을 포함한다. sliding cache의 자동 eviction으로 전체 관측 key가 잘못 사라지지 않게 cache 위치와 mask의 실제 key offset을 검증한다. 필요하면 명시적 cache 또는 느리지만 검증 가능한 no-cache 경로를 사용한다.

vision encoder와 projector는 동결하고 동일 feature를 cache할 수 있다. cache 전후 공식 image feature·embedding 연결을 검사한다. 언어층 gradient는 끊지 않는다. 입력 token 전체의 거대한 vocabulary logits를 보존하지 않고 target 위치 logits만 계산하되 shifted CE의 동등성을 검증한다.

## 4. 가능성 탐색

S/A/N 각각 base에서 시작한다. seed17, 언어 attention q/k/v/o의 rank16 LoRA, alpha32, dropout0, AdamW LR1e-4, weight_decay0.01, gradient clipping1.0, effective batch4를 공통 적용한다. epoch8까지48 updates, warmup은 전체 예정 update의10%, 이후 일정한 LR을 사용한다. 환자별 target 평균 CE를 다시 batch 평균해 긴 보고서가 큰 가중치를 갖지 않게 한다. vision/projector는 동결한다.

bf16과 gradient checkpointing을 우선한다. 메모리가 부족하면 동일 관측을 보존하는 정확한 query chunking 또는 group별 attention 계산을 적용하고 dense reference와 비교한다. 그래도 부족하면 세 조건 모두 동일 NF4 base·bf16 compute로 전환한 후 기술 검사를 다시 한다. 조건별 정밀도를 다르게 쓰거나 전체 slice를 표집으로 바꾸지 않는다. 두 GPU model sharding이 필요하면 한 trajectory씩 실행하고 이유를 기록한다.

V8 생성은 적응 전, epoch2/4/8에 수행한다. 생성은 greedy, 공통 prompt와 길이를 쓴다. 초기 max_new_tokens512를 기술 환자에서 확인하고 실제 cap 도달이 있으면1024로 한 번 늘린 뒤 V/E 전에 고정한다. repetition penalty 등 조건별 보정은 넣지 않는다. cap 도달 출력은 폐기하지 않는다.

## 5. 조건부 학습 연장과 선택

V8에서 epoch4→8 중 어느 조건이든 보수적 recall이2pp 이상 개선되거나, validation target NLL이5% 이상 감소하면서 명시 모순 환자 수가 늘지 않으면 세 조건을 함께 epoch16까지 연장한다. 이는 추가 학습의 정보 가치 기준이지 가설 성공 기준이 아니다. loss만 감소하고 생성이 나빠지는 경우는 연장하지 않는다.

연장 여부가 정해지면 최종 공통 epoch8 또는16을 사용한다. 조건마다 유리한 checkpoint를 따로 고르지 않는다. E16은 그 뒤 한 번 개방한다. LR·seed 순회는 없다.

## 6. 보존 평가와 영상 의존성

E16에서 S/A/N의 적응 전후 총96개 보고서를 생성한다. V8에서 적응 후 보수적 recall이 가장 높고 모순이 가장 적은 조건 하나를 사전 규칙으로 선택한다. 동률이면 N, S, A 순이다. 이 조건만 E16 환자의 전체 영상을 고정 derangement로 교환해16개를 추가 생성한다. 교환은 정상 사용 성능이 아니라 영상 의존성 진단이다.

정답은 원문에서 사전에 고정한 항목이고 새 임상 정답을 만들지 않는다. 출력 대응은 조건·checkpoint를 가린 텍스트 package와 원문 인용 span으로 기록한다. assistant의 텍스트 대응 판단을 전문의 평가라고 부르지 않으며 애매한 표현은 unresolved로 남긴다. 원문 정답 미언급 추가 소견은 임상 허위로 집계하지 않는다.

이번 E16은 단일 seed pilot의 선택 분리 평가다. 외부 자료·독립 임상 평가자·추가 seed 확인과 method full 확대는 이번 범위 밖이며 결과에 따라 별도 판단한다.

## 자원·시간·재개

학습은 우선 GPU별 한 trajectory를 실행하고 세 번째는 완료 장치에 배정한다. 실행 직전 허용 GPU의 실제 여유를 확인한다. 긴 sequence의 activation·KV cache·optimizer를 포함해 worker당 최소2GB 여유를 확보한다.

동작 확인에서 microbatch1 대비2가 가능한지 먼저 비교한다. 긴 sequence 학습 두 worker를 같은 GPU에 올리는 것은 실측 peak 합계와 여유가 성립할 때만 후보로 둔다. 생성은 batch 확대 또는 GPU당2 worker 중 메모리에 맞는 구성을 먼저 비교한다. 요청/분, peak, 긴 출력 지연, 오류와 동일 greedy 출력 여부로 고른다. 1 worker 유지 시 근거를 기록한다.

전체 학습량은 세 조건 합계144 updates, 연장 시288 updates다. wall-clock은 조건별 실측 update 시간과 생성 token 처리량, 배치 순서를 이용해 산출한다. 현재 정확한 시간·peak는 미측정이며 과거 짧은 추론의 수치를 대입하지 않는다. 수 시간 실행도 허용 범위이며 임의 시간 상한은 없다.

각 epoch에 adapter·optimizer·scheduler·RNG·환자 순서·config hash를 저장한다. 원자적 결과 저장, 고유 작업 ID, 중복·누락 검사와 완료 재진입 검사를 둔다. 신규 결과는 results/iter_143에만 저장하고 기존 checkpoint·출력은 보존한다.

# Implementation Tasks for Claude

현재 구현 담당은 Codex이며 필드명만 호환상 유지한다.

1. 현재 branch와 원본 SHA를 확인하고 필요한 자료 모듈의 고정 경로·환자·정답표 의존성만 분리한다.
2. DWI target의 원문 span, 적격 목록, T24/V8/E16 manifest와 source/hash를 출력 전에 고정한다.
3. S/A/N attention wrapper, token 역할 지도, 효율적인 target CE와 명시적 generation 경로를 구현한다.
4. native 동등성, group 차단·허용, target causality, gradient, cache, 재로딩·재개 및 GPU peak를 실제 검사한다.
5. gate 통과 후 세 trajectory를 학습하고 V8 기준으로 공통 연장 여부를 결정한다. 같은 반복에서 E16 실제 생성까지 완료한다.
6. 새 출력의 인용문 대응·불확실성 범위·비용을 기록하고 독립 리뷰가 재계산할 환자별 원자료를 제공한다.

기존 판정표의 재채점, AutoRG launcher 전수 복구, 관계없는 관리 코드 정비는 발주하지 않는다.

# Evaluation (성공/실패 기준 포함)

주 metric은 환자 평균 공개 항목 recall이다. finding/signal/location/morphology/distribution을 분리하고, 특히 세부 위치·속성의 회복을 함께 보고한다. 원문 정답과의 명시 모순 환자율, 내부 모순, unresolved, 반복·비EOS, 생성 길이와 전체 비용도 보고한다.

matched/unmatched/unresolved를 나누고 unresolved를 모두 불일치 또는 일치로 놓은 recall 범위를 계산한다. 절단된 출력의 후속 모순 가능성을0으로 두지 않는다. 관측된 명시 모순과 미완결 출력 때문에 남는 상한을 따로 보고한다. 환자 paired bootstrap10,000회로95% 구간을 산출하되 의미 불확실성 범위를 대체하지 않는다.

- 양성: A−S 보수적 recall 이득≥5pp, 명시 모순 환자율 증가≤5pp를 의미·절단 범위에서도 만족한다. 위치·속성 결과, N과의 차이, 영상 교환 결과를 함께 검토한다. 통계 구간이0을 넘지 못하면 유망하지만 불확정으로 구분한다. 후속은 독립 재현 또는 문맥 기전 대조 하나이며 full 자동 확대는 없다.
- 음성: 유효한 학습 후 A−S의95% 구간 상한이5pp 미만이면 현재 설계의 가치 있는 이득을 지지하지 않는다. N만 회복하면 제한 attention 설계를 보류한다. N과 동등 정확도에서 A의 전체 처리 비용이20% 이상 낮고 paired 실측이 일관되면 효율 후보로 별도 보존하되 정확도 가설 성공으로 바꾸지 않는다.
- 불확정: 표본 변동·의미 대응·절단 또는 부족한 학습 신호 때문에 판정이 남으면 범위를 적고 종료한다. E16 뒤의 추가 epoch·재채점·prompt 순회는 없다. 다음 투자가 달라질 핵심 증거와 비용을 보고한다.

S/A/N 적응 전후 회복과 영상 교환 결과로 과제 적응·영상 기여를 구분한다. 작은 pilot의 무개선을 언어층 LoRA 전체·MRI 전체의 실패로 확대하지 않는다. 반대로 train loss나 overfit 성공을 판독 개선으로 보고하지 않는다.

# Risks / Checks

- S/A의 global 보고서 생성부는 여러 slice를 통합할 수 있다. 따라서 실험은 국소 문맥화의 추가 가치이며 완전한 독립2D 시스템과3D 시스템의 비교가 아니다.
- A 내부는 native causal 관계와 sliding window의 영향을 받는다. 연속5장이 모든 layer에서 완전히 상호작용한다고 표현하지 않는다.
- 실제 학습 메모리와 backend 지원은 미측정이다. 동등 계산의 자원 보완 후에도 불가능하면 확인한 peak·오류·남은 경로를 보고하고 학습 미실행으로 종료한다. 새로운 계층형 구조로 몰래 대체하지 않는다.
- target 구성에서 원문 관계가 애매하면 임상 의미를 추측하지 않는다. 제외의 유형 분포와 평가 가능한 범위를 남긴다.
- 환자별 사전학습 노출은 미확인일 수 있다. 이번 split 독립성과 foundation model 미노출을 구분한다.
- 학습·생성·평가 실패는 가설의 음성 결과와 분리한다. 원본141/142 결과는 변경하지 않는다.

## 대규모 GPU 필요 후보

전체 고해상도 vision-language 공동 적응과3D encoder의 광범위한 학습을 후보로 보존한다. 이번 두24GB GPU에서의 실제 메모리·수렴 근거를 얻기 전에는 필요성을 확정하거나 full fine-tuning을 자동 처방하지 않는다.

# 계획의 근거 (GPT 조사 노트)

## 이번 라운드에서 해결한 질문

`agent/runs/iter_143/think/round_01.json` 원문과 `research/results/iter_142/whole_sequence_supervision.md`를 읽었다. 전체 sequence target을 한 번 사용하고 국소 표현까지 gradient를 연결한다는 계약을 유지한다.

로컬 `transformers/models/gemma3/modeling_gemma3.py`의 Gemma3Model.forward와 Gemma3TextModel.forward는 dict 형태의 full_attention/sliding_attention mask를 받아 자동 mask 생성을 건너뛴다. 따라서 이미지·구간 중간 텍스트의 접근 범위를 함께 제한하는 계산 그래프를 구성할 수 있다. attention은 q/k projection, q/k normalization, RoPE, cache update 뒤 backend를 호출한다. 단순 image feature 연결과 달리 언어층의 시각 token 문맥화가 실제로 달라진다.

생성 경로는 첫 단계 이후 token_type_ids를 제거하고 DynamicCache가 config를 사용한다. 기본 generate 호출만으로 사용자 정의 구간 mask가 유지된다고 가정할 수 없다. 따라서 명시적인 prefill/decode 경로와 cache/no-cache logits 동등성 검증이 필수다. 보고서 token은 native full layer에서 전체 관측에 접근하고 sliding layer에서는 기존 window를 유지하도록 한다. prefix와 국소 token이 보고서 또는 다른 구간의 텍스트를 통해 정보를 역으로 받지 못하게 한다.

추가 pooling·새 decoder가 필요한 계층형 통합보다 attention 범위 대조를 선택했다. 다만 S/A는 native MedGemma 입력법 자체가 아니라 attention을 제한한 직접 적응이다. 이를 통제하기 위해 native 전체 sequence SFT N을 세 번째 필수 대조로 추가한다. read-only 소스 확인은 전체 sequence의 GPU 실행 가능성 증명이 아니므로 실측 gate를 남긴다.

## 근거와 재사용

`agent/runs/iter_141/review.json`, `agent/runs/iter_142/review.json`, `agent/LIMITATIONS.md`의 해당 항목과 `agent/CODE_ASSETS.md`의 139–142 항목을 확인했다. iter_141은 valid_experiment=true, blocking 없음, observed 상태다. method pilot 근거이며 full 근거는 아니다.

현재 branch의 i141_data.py에는 환자별 LOCATIONS와 고정 8명 의존성이 있다. 이를 새 정답표로 재사용하지 않는다. i141_select_download.py의 선택 반입·CRC 검사와 i141_data.py의 orientation·물리 좌표·렌더링 검사를 필요한 범위에서 일반화한다. i141_run.py는 최대5장 요청과 고정 stage를 전제하므로 전체 sequence 학습 실행기로 그대로 쓰지 않는다. i141_judge.py/i142_judge.py는 기존 사례의 판정 기록으로만 보존한다.

iter_139 checkpoint `3fb452dc0e53ebbbf26c0f9437afca348c18ea39`의 owned_paths와 실제 tree를 확인했다. 보존된 것은 기존 추론·MSD 자료 모듈이며 이번에 가져올 완성된 학습 모듈은 확인되지 않았다. 새 attention 학습 경로를 구현하되 보관 코드를 소실로 간주하거나 MSD 실험을 재개하지 않는다. 현재 branch에 필요한 자료 모듈이 있으므로 외부 선별 반입은 없다.

## 자료와 해석

공식 global_finding.json의 실제 예시는 위치·형상을 기술한 뒤 같은 병변의 ADC 저신호와 DWI 고신호를 연결한다. DWI에 명시적으로 연결된 원문 span만 target에 사용하고 ADC·병인·시기는 제외한다. 새 환자별 영상 연결과 적격 target 수는 아직 확인되지 않았으므로 구현 초기에 한정 검사를 수행한다. 기존 train175/val25/test50은 metadata 수이지 적격 환자 수가 아니다.

이번 결과는 공개 텍스트 항목 회복과 출력 완결성을 판단한다. 보고서 미언급을 임상 음성으로 만들지 않고 새로운 LLM 합의로 임상 정답을 만들지 않는다.

## 대규모 GPU 필요 후보

전체 해상도의 vision encoder까지 공동 적응하거나 native 3D encoder와 언어 모델을 광범위하게 학습하는 후보는 보존한다. 현재 두 24GB GPU에서 언어층 LoRA의 실제 peak를 먼저 측정하며 대규모 장비 필요성을 미리 확정하지 않는다.

이전 사고 라운드 노트: agent/runs/iter_143/think/
