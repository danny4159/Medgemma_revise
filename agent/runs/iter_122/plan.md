# 요약

- **이번에 할 일:** MR-RATE의 명시적 뇌실주위 백질 FLAIR 고신호·정상 보고서를 연결하고, 기술6명 후 별도48명에서 공동 입력과 분할 집계를 비교한다.
- **필요한 이유:** iter_121의 DWI–ADC 설계는 자료 조건에서 중단됐다. 기존 두 batch에는 이번 질문의 보고서·sequence 후보가 실제로 있다.
- **확인할 기준:** 동일 영상의 분할 집계가 BA를 10pp 이상 개선하는지와 호출 비용·specificity 손실을 함께 확인한다.
- **주의·다음:** 보고서 기반 개발 탐색이다. 자료가 성립하지 않으면 해당 후보를 보류하고, 성립하면 준비 반복을 끝내고 실제 출력까지 얻는다.

## 알림 맥락

- 연구: MRI volume 근거 활용
- 데이터: MR-RATE 뇌 MRI, DWI–ADC 후보에서 제공된 axial FLAIR로 구체화
- 모델: MedGemma 1.5 4B, frozen 추론
- 과제: FLAIR 단면에서 뇌실주위 백질 고신호 근거의 존재·부재·판단 불가 출력
- 가설: 관측 범위와 공동 처리 부담이 보고서 일치도에 서로 다른 영향을 줄 수 있음
- 질문: 같은 MRI 단면을 함께 보거나 나눠 판단하면 답이 달라지는가?
- 변경: 구체화
- 연결: iter_121은 DWI–ADC metadata 연결 실패로 모델 미실행이며, 기존 보고서에서 직접 기술된 FLAIR 소견을 확인해 평가 범위를 좁힘
- 작업: 명시적 정답과 영상 연결 후 paired 추론으로 단순 대안 보존·한정 후속·투자 보류를 결정

# Current Understanding

최종 GOAL과 기존 보류 연구는 유지한다. 같은 research_track과 approach를 잇지만 정답·sequence·주비교가 바뀌므로 단순 실행 복구가 아닌 별도 진단 계획이다. iter_121 원 계획의 SHA256은 `c32e4d9cc49bd8ce05ae6ec6e0e1b71025a287f98f57a5bae8b3011b876dd6e5`다.

유지: 환자 분리, 명시적 보고서 근거, 동일 영상 예산, 고정 집계, 공식 입력 검사, 비용·출력 보존. 보류: 급성 경색 및 DWI–ADC 연결. 변경: 뇌실주위 백질 FLAIR 고신호의 존재 판단, 단일 sequence 8장, 주비교 분할−공동. 미완료: 최종 적격 환자, 실제 ZIP·영상 품질, 모든 모델 출력.

로컬 후보 검색은 양성·음성 문장의 존재만 확인했다. 자동 병리 라벨이나 키워드 hit 수는 정답·독립 환자 수가 아니다. iter_064의 MedGemma context 손실과 Qwen 반대 근거는 유지하지만 새 과제의 한계로 이전하지 않는다.

# Strategy Check / 연구 방향 판단

1. **중요한 문제:** 제한된 MRI 영상 예산을 어떤 범위와 요청 단위로 사용하는지가 정확도와 비용에 미치는 영향이다.
2. **현재 근거:** 직전 카드 출처는 iter_121 review.md다. 추가 근거는 기존 보고서의 명시적 FLAIR 고신호·정상 문장과 axial FLAIR metadata 연결이다. 모델의 새 실패 관찰은 없다.
3. **쉬운 해결책:** 넓은 sampling, 분할 OR, 전문 WMH segmentation이 있다. 앞의 두 대안부터 직접 비교한다.
4. **남은 설명:** sampling으로 빠진 소견, 기본 인식 부족, 공동 처리 부담, OR 편향, 구조화 보고서 오류가 남는다.
5. **다음 결정:** 실제 출력에서 중요한 차이가 남으면 전문 대조·타 계열·독립 환자 후속 하나를 검토한다. 단순 대안으로 충분하거나 정답 의미가 불안정하면 새 방법 투자를 보류한다.

급성 경색의 다른 batch 탐색은 새 제공 근거가 없어 선택하지 않는다. 수막종은 T1 조영 연결 문제가 있어 우선하지 않는다. 탈수초 원인 진단은 이번 소견 존재 질문으로 대체하지 않으며 별도 미검증 상태로 남긴다.

# Hypothesis

주가설은 동일한 넓은 범위 8장을 두 묶음으로 판정한 고정 집계가 공동 입력보다 보고서 일치도를 높일 수 있다는 것이다. 이득이 있더라도 내부 통합 결함의 증명은 아니다.

관측 부족이 주된 설명이면 넓은 입력이 중앙 입력보다 좋아지고, 분할의 추가 이득은 작을 수 있다. 공동 처리 방식이 중요하면 동일 pixel의 분할 집계가 넓은 공동 입력보다 좋아질 수 있다. 모든 조건이 낮으면 기본 인식·sampling·약한 정답을 구분하지 못한 것으로 판단한다. 분할 이득이 sensitivity 증가와 specificity 감소로만 나타나는지도 보고한다.

# Limitation Evidence / Correct Usage Checks

`mri-explicit-target-context-effect`의 원 리뷰는 정상 입력 검사를 거친 제한된 MedGemma 손실을 보존하지만 일반 결합 실패를 확정하지 않는다. 이번은 diagnostic이며 신규 학습이나 method gate 통과를 포함하지 않는다.

MedGemma 1.5의 실제 revision·processor·chat template·정밀도를 고정한다. 공식 다중 영상 호출과 wrapper의 input_ids·pixel_values를 소수 기술 입력에서 대조한다. 순서·placeholder·영상 크기·token 수·허용 GPU를 검사한다. 보고서·병리 라벨·원 파일명·clinical indication은 모델 입력에서 제거한다.

# Contribution Path / Baselines / Reuse

신규 contribution은 미확정이다. 이번은 단순 입력 대안의 가치와 이후 투자 필요성을 판단하는 단계다. 분할 OR 자체를 새로운 방법으로 주장하지 않는다.

실제 baseline은 중앙8장과 넓은8장의 직접 질의다. 전문 대안 [HyperMapp3r](https://github.com/AICONSlab/HyperMapp3r)은 T1·FLAIR·brain mask를 사용하므로 현재 단일 FLAIR와 정보량이 다르다. 이 차이를 숨기거나 설치 미실행을 대안 실패로 취급하지 않는다. 긍정적 잔여 관찰이 있으면 전문 모델 및 직접 SFT/encoder+head의 필요성과 공정한 비교 규모를 다음 계획에서 정한다.

현재 브랜치의 status·diff·tracked 목록을 확인했다. 직접 사용할 MRI 모듈을 선택하지 않았으므로 reuse_assets는 없다. 과거 실행기 보관본은 존재하지만 현재 과제와 다르고 provenance·재개·비용 결함이 있어 전수 복구하지 않는다. 공식 processor를 이용한 이번 자료 전용 최소 경로를 구현한다. 기존 파일을 임의 덮어쓰지 않는다.

# Proposed Experiment

## 1. 한정 자료 확인과 정답 고정

기존 batch04·batch23과 공식 train만 사용한다. splits의 실제 enum과 환자별 split 일관성을 다시 검사하되 test의 라벨·보고서는 새로 열지 않는다. iter_121의 test 집계 노출은 기록한다. 공식 validation을 쓴 것으로 보고하지 않는다.

주질문은 제공 영상에서 **뇌실주위 백질의 병적 FLAIR 고신호 근거가 있는가**다. 원인 질환·급성 여부·MS 진단을 묻지 않는다.

양성은 findings 또는 impression에서 periventricular white matter의 병적 고신호가 현재 관찰로 명시되고, 같은 소견에 FLAIR 고신호라는 연결이 직접 있는 경우다. T2만의 기술, 임상 병력만의 언급, 위치 연결 추측, 의심·상충·생리적 변이 설명은 unknown으로 둔다. 원인에 대한 불확실성이 있어도 고신호 존재 자체가 명시적이면 원인 부분을 정답에 포함하지 않는다.

음성은 periventricular white matter의 정상 신호 또는 병적 신호 부재가 직접 기술된 경우다. 범위가 없는 'brain MRI normal', 자동 라벨0, 소견 미언급은 사용하지 않는다. 같은 보고서의 다른 부분에 해당 범위의 병변·예외·상충이 있으면 unknown이다. 단순 정규식은 후보 검색용으로만 사용하고 각 선정 사례의 관련 원문 span과 전체 findings/impression 상충 검사를 남긴다. 새로운 LLM 자유 판정을 임상 정답으로 만들지 않는다. 애매하면 제외한다.

확정 양성·음성·unknown·제외를 구분한 manifest를 생성하고 source CSV SHA256, 규칙 버전, patient/study/series ID를 연결한다. 환자 중복을 제거하며 한 환자에 여러 적격 study가 있으면 seed122 hash 순서 첫 study를 쓴다. axial FLAIR, nonlocalizer, brain exam 연결을 요구한다. 여러 적격 series는 coverage 확인 후 가장 작은 through-plane spacing, 동률 series_id 순으로 고정한다. 병변을 가장 잘 보이게 하는 series 선택은 금지한다.

## 2. 동작 확인: 6명

양성3·음성3을 별도 기술 집단으로 고정한다. 원격 study ZIP 크기와 압축 해제 공간을 확인한 뒤 승인 경로에 받는다. ZIP 경로 이탈·symlink를 거부하고 사용 파일 hash를 남긴다. metadata와 실제 NIfTI의 study/series·shape·spacing·affine·방향·brain coverage를 대조한다.

제공 brain mask는 해부학 범위 확인에만 사용한다. 해당 ZIP의 실제 제공 여부를 먼저 확인하고, 병변 mask로 해석하지 않는다. 신뢰할 수 있는 뇌 범위가 없으면 임의 mask를 정답처럼 만들지 말고 해당 사례를 제외한다. native axial 영상의 물리적 inferior–superior 순서를 확인하며 불필요한 3D 보간을 피한다.

volume 전체의 brain 내 1–99 percentile을 이용한 고정 강도 표시를 사용하고 모든 조건에서 같은 slice는 동일 pixel tensor를 사용한다. 방향과 대표 단면을 직접 표시해 확인한다. 영상 검사는 라벨을 재판정하거나 쉬운 양성만 선택하기 위한 절차가 아니다.

생성은 greedy, max_new_tokens512에서 시작한다. 비EOS가 있으면 기술 집단에서1024로 올려 재검사하고 본실행 설정을 고정한다. 계속 잘리면 실행 문제를 해결하기 전 본탐색에 진입하지 않는다. 기술 성능으로 prompt·sampling을 최적화하지 않는다. 낮은 정확도 자체는 본탐색 금지 gate가 아니다.

## 3. 가능성 탐색: 별도48명

양성24·명시 음성24의 공식 train 환자를 seed122로 선택한다. batch별 양·음성을 가능한 한 균형 있게 배정하고 한 batch 부족분은 다른 기존 batch에서만 보충한다. 양성의 보고서상 punctate/focal와 multiple/confluent 표현 분포를 기록하고 작은·어려운 소견을 편의상 제외하지 않는다. 모델 출력 전 정답·제외·환자 목록·조건·parser를 잠근다.

적격이40–47명이면 두 클래스 각각20명 이상을 확보하는 범위에서 전체 적격 표본으로 축소하고 출력 전에 실제 N·정밀도 한계를 기록한다. 이 조건을 충족하지 못하면 기술 결과와 자료 범위만 보존하고 48명 탐색 완료로 보고하지 않는다. batch 추가·질환 전환은 없다.

- C: 유효 뇌 superior–inferior 범위의 중앙50%에서 등간격8개 axial slice.
- W: 같은 범위의5–95%에서 등간격8개 slice.
- P: W의 동일8장을 inferior4·superior4로 나눈 두 요청.

중복 index가 생기는 volume은8개 고유 위치를 만들 수 있는지 검사하고 불가능하면 사전 제외한다. C/W는 제공된 영상들에서 해당 근거가 있는지, P는 각 제공 묶음에서 있는지 묻는다. sequence명과 단면 순서 외 임상 정보는 주지 않는다.

출력 첫 줄은 PRESENT/ABSENT/UNCERTAIN 중 하나이고 뒤에 짧은 근거를 허용한다. 고정 parser는 첫 줄의 단일 상태만 읽는다. 복수 상태·상충·거부·형식 오류는 별도 코드로 보존하며 사후 의미 재채점하지 않는다. P는 하나라도 PRESENT면 PRESENT, 둘 다 ABSENT면 ABSENT, 나머지는 UNCERTAIN이다. invalid가 포함된 경우의 집계도 이 규칙에서 비PRESENT·비ABSENT로 처리하고 원 invalid를 별도로 보고한다.

환자당4요청, 기술24요청·탐색192요청으로 기본216요청이다. 주평가는 P−W, 보조는 W−C다. P의 각 묶음에는 slice-level 정답이 없으므로 개별 묶음의 임상 정확도를 산출하지 않는다.

## 4. 규모 확대·독립 확인

이번 표본은 개발 탐색이다. 추가 seed·다른 prompt·학습·타 모델·새 환자 확증은 자동 실행하지 않는다. 양성 또는 판별력 있는 불확정이면 full review에서 전문 대조·타 계열·독립 환자 후속 하나의 가치를 판단한다. 작은 동작 확인을 통과했다는 이유만으로 확대하지 않는다.

## 자원·예상 시간·재개

소스는 research/, 새 결과는 research/results/iter_122/, 데이터와 새 cache는 `/home/test/.local/share/medgemma/mr_rate`에 보존한다. 기존 원자료와 iter_121 결과는 변경하지 않는다. metadata 누적250MB·ZIP 누적10GiB와 실제 압축 해제 여유를 확인한다. 초과가 필요하면 필요한 표본·bytes를 실행 전에 별도 근거로 제시하고 조용히 전량 반입하지 않는다.

외부 경로는 이번 계획의 정상 읽기가 성공했다. 구현 실행기의 허용 경로도 정상 반영됐는지 먼저 확인한다. 거부되면 다른 도구로 우회하지 않고 정확한 운영 blocker를 보고한다.

실행 직전 nvidia-smi와 상속 CUDA_VISIBLE_DEVICES를 확인한다. 두 GPU에 독립 환자 shard를 배정한다. 기술 입력에서 batch1 대비 batch2를 우선 짧게 비교하고, 메모리가 허용되면 GPU당2 worker를 후보로 평가한다. 동시 peak·다른 점유·worker당2GiB 여유를 합쳐 판단한다. 요청/분·긴 출력 지연·OOM·CPU/I/O·출력 정합성으로 구성을 선택하며 GPU당1 worker 유지에는 실측 근거를 남긴다.

현재 새 입력의 시간·메모리는 미측정이다. bf16 모델 적재8–10GB는 참고 추정일 뿐이다. 기술 실측 처리량 r requests/min으로 추론 예상 시간을 남은 요청수/r로 계산하고 다운로드·전처리·model load를 별도 더한다. 임의 시간 상한은 없다.

patient/condition/input/prompt/model hash 기반 요청ID, 원자적 작업 할당, worker별 출력, 완료ID 검증과 안전 재개를 구현한다. 누락·중복·손상 출력·process 종료를 확인한다. 학습 checkpoint는 없고 추론 완료 ledger와 소스 checkpoint를 보존한다.

# Implementation Tasks for Claude

1. 현재 정책·iter_121 원 리뷰·현재 소스와 외부 경로 권한을 확인하고 필요한 입력의 출처·hash를 고정한다.
2. 두 batch train에서 명시적 정답 span과 FLAIR 연결 manifest를 만든다. unknown·상충·제외 규칙을 먼저 잠근다.
3. 기술6명의 ZIP·영상·공식 processor·출력 길이·처리량을 검사한다.
4. 조건이 성립하면 별도48명의 고정 paired 추론을 실행한다. 불성립이면 다른 후보로 자동 이동하지 않는다.
5. 독립 집계로 BA·전환 수·CI·coverage·전체 비용을 재계산하고 실제 단계와 다음 투자 선택을 보고한다. 소스 보존은 orchestrator 절차를 따른다.

# Evaluation (성공/실패 기준 포함)

주지표는 UNCERTAIN/invalid를 정답으로 세지 않는 BA다. sensitivity·specificity·명시 답 coverage·unknown·거부·비EOS·invalid와 confusion counts를 함께 보고한다. 명시 답만의 accuracy는 보조값이다.

환자 단위 paired bootstrap10,000회, seed122로95% CI를 산출한다. 양·음성 층 내 환자를 resample해 클래스가 사라지는 문제를 피한다. 주비교 P−W와 보조 W−C를 분리하고 유리한 최대값을 주결과로 고르지 않는다. 양방향 정오 전환 수, batch별 방향과 보고서 소견 범위를 함께 보고한다.

- **양성:** P−W BA≥10pp이고 CI 하한>0. 분할 처리의 제한적 이득으로 보존한다. 호출 증가·specificity 손실을 포함해 후속 가치를 판단한다.
- **관측 대안의 양성:** W−C가 같은 기준을 만족하면 넓은 sampling의 가치로만 해석한다.
- **단순 대안 충분성 후보:** W 또는 P의 BA≥0.80 및 sensitivity·specificity 각각≥0.75이면 현재 개발 조건의 단순 대안을 보존하고 새 방법 투자를 우선 보류한다. 임상 충분성은 확정하지 않는다.
- **음성:** 주차이 CI 상한<10pp이면 현재 분할 대조의 큰 이득 근거가 약하다. 모든 조건 BA≤0.60이면 현재 frozen 수행 부족으로 제한한다.
- **불확정:** 나머지는 표본 변동·unknown·정답 연결 중 지배 요인을 명시한다. 추가 환자가 결정을 바꿀 조건과 필요한 정밀도를 산출하되 자동 확대하지 않는다. 정답 재해석·prompt 탐색만 남으면 투자 보류한다.

비용은 원 NIfTI 읽기부터 최종 답 저장까지와 model load를 구분한다. P의2회 호출, 추가 prompt/output token, latency를 모두 포함한다. 10pp 미만 효과와 비용 증가를 새로운 방법 가치로 포장하지 않는다.

정답·입력·누수 무결성 실패는 execution_failed, 유효 출력의 넓은 CI는 inconclusive로 구분한다. 성능 저하를 실행 실패로 바꾸거나 실행 성공을 가설 지지로 보고하지 않는다.

# Risks / Checks

- 보고서 일치도는 영상 진단 정확도가 아니다. 뇌실주위 위치가 부분 단면에 실제 보인다는 병변 공간 정답도 없다.
- 정상 문장과 예외·병변 문장의 공존을 검사한다. 자동 라벨0과 정상 미언급을 음성으로 쓰지 않는다.
- FLAIR 고신호를 탈수초·혈관성 등 원인 질환으로 추측하지 않는다.
- 넓은 sampling은 coverage와 간격을 함께 바꾼다. P는 요청 범위·호출수·OR 편향도 바꾼다. 순수 내부 원인으로 단정하지 않는다.
- 영상 품질 제외는 출력 전에 고정하며 모델이 틀린 환자를 제외하지 않는다.
- 공식 이용 조건·학습 노출·데이터 revision을 기록한다. HF_TOKEN_PATH만 참조하고 토큰 내용을 출력하지 않는다.
- 두 batch의 train에 한정된 선택이며 외부·공식 test 일반화는 미검증이다.
- 종료 후 같은 자료의 정답 재판정·prompt 조정으로 준비 반복을 이어가지 않는다.

## 대규모 GPU 필요 후보

전체 volume의 다중 sequence encoder–언어모델 공동 적응과 대규모 영상–보고서 사전학습은 장기 후보로 보존한다. 긴 volume token과 많은 환자 학습 비용이 필요할 수 있다. 현재는 단순 대안 이후의 필요성이 미확인이므로 실행하지 않는다.

# 계획의 근거 (GPT 조사 노트)

## 새로 확인한 사실

- `agent/GOAL.md`, iter_121의 원 plan/review, `MR_RATE_DATA_NOTES.md`, iter_064 원 review.md 및 review.json의 limitation_updates, `LIMITATIONS.md` 해당 항목, `CODE_ASSETS.md` 관련 기록을 확인했다.
- 이번 계획 환경에서는 `/home/test/.local/share/medgemma/mr_rate/meta`의 정상적인 `ls`와 CSV 읽기가 성공했다. iter_121의 구현 실행기 권한 문제가 해결됐다는 뜻은 아니므로 구현 진입 시 해당 실행기의 허용 경로를 별도로 확인한다.
- 두 reports CSV의 실제 header는 `study_uid, report, clinical_information, technique, findings, impression`이다. 보고서에 diffusion 촬영이 기술돼도 배포 metadata의 제공 sequence와 일치한다고 가정할 수 없다.
- 공식 train, axial FLAIR metadata와 연결한 단순 후보 검색에서 batch04는 같은 findings 문장에 white matter·FLAIR·hyperintense가 있는 study286개, 제한된 정상 문장 후보126개였다. batch23은 각각105개·368개였다. 이는 환자 중복 제거·보고서 전체 상충 검사 전의 후보 study 수이며 최종 적격 수가 아니다. 이번 계획은 이 수치를 validation의 적격 수로 사용하지 않고 train만 선택한다.
- 양성 후보 예: `XWUBPHWIYR`는 periventricular deep white matter의 T2/FLAIR 고신호와 gliotic changes를 함께 기술한다. `ROQB6RZ4RG`는 supratentorial white matter의 T2/FLAIR 고신호를 기술하지만 최종 뇌실주위 범위 적격성은 추가 확인이 필요하다. 음성 후보에는 periventricular white matter·corona radiata·centrum semiovale가 정상이라는 직접 문장이 있다.
- 단순 검색에는 생리적 perivascular enlargement와 고신호가 함께 기술된 사례, '병변을 제외하면 정상'이라는 사례가 섞였다. 따라서 검색 결과를 정답으로 변환하지 않는다. 임상 원인 추론 없이 명시적 범위·신호·부재만 사용한다.
- `research/`의 status·diff는 깨끗하다. 현재 tracked 파일은 기존 qes/grounding 준비 및 review82 분석 등이므로 이번 MRI 실행기에 직접 사용할 모듈을 선택하지 않았다. 과거 MRI 실행기는 보존돼 있지만 iter_064의 provenance·비용·GPU 허용 집합 결함을 가진 전체 실행기를 반입하지 않는다.

## 원문과 가까운 대안

- [MR-RATE 공식 guide](https://github.com/forithmus/MR-RATE/blob/main/data-preprocessing/docs/dataset_guide.md)는 제공 sequence, study ZIP, series 식별자와 현재 T1 조영 라벨 부재를 설명한다. 보고서는 구조화된 자료이며 병변 공간 정답이 아니다.
- [MedGemma 1.5 모델 카드](https://huggingface.co/google/medgemma-1.5-4b-it)를 확인했다. 구현은 공식 processor·chat template·다중 영상 경로를 고정하고 실제 tensor를 검사한다.
- [HyperMapp3r 공식 구현](https://github.com/AICONSlab/HyperMapp3r)은 T1·FLAIR·brain mask를 입력받는 공개 WMH segmentation 대안이다. 단일 FLAIR와 동일 정보 대조로 부를 수 없고, 질병 원인 판정과 WMH 검출을 혼동하지 않는다.

## 선택의 의미와 한계

급성 경색 후보는 현재 DWI–ADC 연결 부재로 보류한다. 수막종은 조영 여부 연결이 추가로 필요하다. 탈수초 질환명 대신 영상에 직접 기술된 뇌실주위 FLAIR 고신호로 좁히면 원인 진단을 추측하지 않고 관측 비교를 구성할 수 있다. 아직 최종 적격 환자·실제 ZIP·영상 품질은 미검증이므로 한정 자료 검사와 조건부 GPU 실행으로 계획한다. 새로운 방법의 유망성은 가정하지 않는다.
