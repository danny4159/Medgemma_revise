# 요약

- **이번에 할 일:** RSNA의 지정 opacity에 대해 존재 판단이 잘못된 위치 근거를 추가로 식별하는지 비교한다.
- **필요한 이유:** 소견이 있다는 답과 box가 함께 나와도 위치가 맞다는 보장은 없다. 단순 존재 gate의 성공과 위치 검증의 가치를 분리해야 한다.
- **확인할 기준:** 같은 검토량에서 detector confidence보다 오류를 더 찾는지, 그 이득이 양성 영상의 위치 오류에도 남는지 본다.
- **주의·다음:** 저장 출력의 개발 분석이다. 새 학습·crop·parser 탐색은 없으며 결과 후 다음 반복은 사용자 승인을 기다린다.

## 알림 맥락

- 연구: 위치 근거와 의료 VLM 판단의 연결
- 데이터: 흉부 X-ray RSNA 개발 E600
- 모델: MedGemma 1.5 원본 영상 응답, 직접 grounding SFT, detector17의 저장 출력
- 과제: 지정 opacity의 존재 답변과 위치 출력을 공개 정답으로 함께 평가한다
- 가설: 존재 판단이 주는 오류 신호는 detector confidence로 설명되거나 부재 오류에 한정될 수 있다
- 질문: 소견이 있다는 판단은 잘못된 위치 근거를 걸러내는 데 실제로 도움이 되는가?
- 변경: 구체화
- 연결: 자유 생성 문장의 정답 연결 부족 → 사용자 승인에 따라 명시적인 존재·위치 정답으로 범위를 좁힌다
- 작업: 저장 실제 출력의 오류 분해와 동일 검토량 비교로 독립 확인에 투자할지 결정한다

# Current Understanding

iter_110은 계획 확인 단계에서 사용자 보완으로 전환됐다. 구현 실패나 모델 가설의 음성 결과가 아니다. 자유 판독문 전체의 정확성 검증은 보류한다. iter_108~109의 crop 투자 종료와 parser 분석 종료도 유지한다.

RSNA E600에는 opacity/normal/not_normal_no_opacity 각 200명이 있다. 표적은 pneumonia 자체가 아니라 기존 Q_O와 연결된 pulmonary opacity suspicious for pneumonia다. 음성 두 범주는 표적 음성이며 모두 임상적으로 정상이라는 뜻이 아니다.

iter_042의 presence gate 성공은 중요한 반대 근거다. 존재 확인이 음성 false-box를 줄인다는 사실을 새로 발견하려는 실험을 하지 않는다. 이번 질문은 그 신호가 위치 근거의 정확성까지 검증하는 데 유용한가이다.

# Strategy Check / 연구 방향 판단

**기술 질문 → 실패 조건 → 공개 정답 비교 → 주장 범위:** 전역 존재 판단의 추가 오류 식별력 → 존재 답과 nonempty box가 일치하지만 box가 주석에 맞지 않는 조건 → 명시적 표적 존재 라벨과 양성 box의 matching, 같은 검토량의 confidence 대조 → 현재 RSNA 출력에서의 오류 검토 가치에 한정한다. 근거의 인과적 사용이나 자유 판독 사실성을 주장하지 않는다.

후보는 두 개만 비교했다. 첫째는 이번 존재 판단의 위치 오류 식별 진단이다. 기존 자료로 존재 오류와 위치 오류를 분리하고 강한 단순 대조를 넣을 수 있다. 둘째는 공동 답변·좌표 생성이다. 그러나 iter_048은 공동 형식 직접 학습으로 큰 회복을 보였으며, 이번에 새 인터페이스를 만들면 같은 형식 혼선을 반복할 가능성이 크다. 첫째를 선택한다.

**시험 설정:** 모델과 입력을 바꾸지 않고 저장 출력을 비교한다. SFT나 새 검증기를 학습하지 않는다.

**연구 관찰:** iter_017의 인터페이스 의존성, iter_037의 위치 trade-off, iter_042의 단순 gate 성공을 계승한다. iter_082의 불일치 순위 실패는 강한 confidence 대조가 필요한 근거다. 서로 다른 과제의 결과를 같은 원인의 재현으로 합치지 않는다.

**연구 질문:** 단순 대안 이후 정보가 없다면 현재 전역 존재 확인 후보는 종료한다. 추가 정보가 남아도 새로운 방법으로 선언하지 않고 독립 확인의 가치만 판단한다. 반복 개발 자료의 재분석이라는 기회비용 때문에 같은 출력에서 순위를 최적화하지 않는다.

# Hypothesis

H1: 독립적인 존재 답변과 detector의 존재 출력 간 불일치는 detector confidence가 놓친 판단·위치 오류를 식별한다.

H0: 추가 신호가 없거나, 이득은 정답 음성 영상의 존재 오류에만 한정된다. 양성 영상의 위치 오류는 전역 존재 확인으로 구별되지 않는다.

H2: 관측 차이가 형식 미해결 응답이나 특정 표본에 의존한다. 이 경우 내용상 추가 정보와 분리해 불확정으로 보고한다.

# Limitation Evidence / Correct Usage Checks

관련 원문은 agent/LIMITATIONS.md, iter_037/review.json, iter_042/review.md다. 두 limitation은 observed이며 이번 설계는 diagnostic이다. method 진입 근거로 승격하지 않는다.

iter_042의 음성 false-box 39/40→1/40와 양성 보존 불확정을 함께 유지한다. iter_037의 detector17 선택점과 SFT의 서로 다른 IoU trade-off도 유지한다.

자료 점검에서는 E600 ID를 원 manifest·RSNA 원 라벨·원 box에 연결한다. 원 라벨이 음성을 명시하는지 확인하며 box 부재만으로 음성을 생성하지 않는다. 원본 영상 hash, 환자 대응, 좌표 canvas, checkpoint, 요청의 Q_O 문구와 GT 비노출을 확인한다. source 모델의 사전학습 노출은 미확인으로 기록한다.

# Contribution Path / Baselines / Reuse

기여는 미확정이다. [Phrase-grounded Fact-checking](https://arxiv.org/abs/2509.21356)은 소견·위치 오류 검증을, [MedGrounder](https://arxiv.org/abs/2512.01085)는 scored zero/one/multiple regions를 이미 다룬다. 이번 분석은 이 방법들을 이겼다는 비교가 아니다.

주대조는 detector17의 기존 epoch18·threshold0.70 출력이다. 원본 영상에 대한 MedGemma의 독립 존재 응답을 붙였을 때 검토 대상 선택이 좋아지는지 본다. 답변과 위치를 강제로 일치시키는 규칙을 정확성의 근거로 사용하지 않는다.

직접 grounding SFT의 bbox 유무 규칙과 presence gate를 보조 시스템으로 평가한다. 과거 학습량·데이터가 다른 detector와 SFT의 점수 차이를 위치 supervision의 인과 효과로 해석하지 않는다.

새 브랜치는 승인된 iter_082 기반을 요청한다. reuse_assets의 실제 SHA와 개별 파일만 반입한다. 현재 트리에 있는 파일도 새 기반에는 없음을 확인했다. metrics.py는 iter_037 원본에서 가져온다. ev109 분석 CLI와 detector 분석 CLI 전체를 복구하지 않는다. 승인된 순수 함수를 조합한 이번 연결·평가 경로만 작성한다.

# Proposed Experiment

## 1. 자료·응답 적합성 확인

입력은 다음으로 고정한다.

- E600: results/iter_016/manifests/sets.json, labels.json, infer_manifest.jsonl.
- 존재 응답: iter_016/gen/e180_plain__M0 및 e600x_plain__M0의 Q_O 원시 출력. iter_109의 F ledger는 대조용이다.
- 직접 SFT: iter_015/reuse/bbox_B0_concise.jsonl와 그 원본 출처.
- detector: iter_035/confirm800/det17/raw_preds.json, worker 원본·completion, select/LOCK.json 및 seed17/v400_selection.json.

E600 전체가 세 출력에 연결되는지 먼저 검사한다. 누락을 제외한 편의 표본으로 바꾸지 않는다. 환자별 원본 row·request·protocol·completion·현재 file hash를 이번 manifest에 연결한다. 과거 digest 문자열만 복사하지 않는다.

세 GT 범주에서 고정 ID hash 순으로 각 4명, 총 12명을 대표 점검한다. 영상·정답·좌표와 실제 응답을 확인한다. 모델 정답률은 진입 gate가 아니다. ID/좌표/표적 의미가 성립하면 같은 호출에서 전체 비교로 진행한다. 연결이 성립하지 않으면 누락 경로와 영향 범위를 보고하고 종료한다.

답 추출은 승인된 ev109_extract_v1을 변경 없이 사용한다. unresolved를 No로 바꾸거나 제외하지 않는다. strict 수치는 보조로 보존하되 새 parser 비교 실험을 만들지 않는다.

## 2. 고정된 오류 정의

주 IoU는 0.3, 보조는 0.5다. detector 좌표는 img_hw와 원 영상에 맞춰 공통 canvas로 변환한다. 최대 일대일 matching으로 TP·FP·FN을 계산한다.

판단·근거 공동 성공은 다음과 같다. 정답 음성은 No와 빈 box가 함께 있어야 한다. 정답 양성은 Yes이며 TP=n_GT=n_pred여야 한다. 이는 주석상 완전한 집합 대응이라는 엄격한 연구 지표이며 임상 안전의 정의가 아니다. 별도로 존재 정확도, 양성 F1, 최소 한 GT 포착, FP/환자, FN/환자, invalid를 보고한다.

오류는 정답 음성의 양성 주장, 정답 양성의 전체 미검출, 정답 양성에서 nonempty지만 FP 또는 FN이 남는 위치·coverage 오류로 분해한다. IoU 불일치를 순수 인식 실패로 부르지 않는다.

## 3. 주 비교: 같은 검토량의 오류 포착

대상 S는 E600 중 기존 threshold0.70에서 detector가 nonempty인 환자 전원이다. GT나 reader 응답으로 S를 고르지 않는다. detector의 원 예측은 고정한다.

주 오류 Y는 S에서 detector의 공동 성공이 실패한 경우다. reader가 명시적으로 No인 사례를 존재 불일치 경보로 삼는다. unresolved는 별도 검토 대상으로 두고, 양쪽 전략에 동일하게 먼저 배정한다.

내용 비교에서는 resolved S의 reader-No 수를 k로 정한다. VLM 전략은 그 k명을 선택한다. confidence 전략은 같은 resolved S에서 detector의 최대 box score가 낮은 k명을 선택한다. 경계 동률은 동률 집단의 균등 검토 기대값으로 계산한다. k=0 또는 k=전체이면 내용 선택의 추가 정보가 없는 퇴화 비교로 보고한다.

주 endpoint는 두 전략이 찾은 Y 수의 차이를 전체 S 수로 나눈 값이다. 같은 검토량, 제거한 올바른 출력 수, 오류 recall·precision도 보고한다. GT 음성 오류와 GT 양성 위치·coverage 오류의 기여를 따로 제시한다. confidence 보조 대조로 최소 box score 순위도 같은 k에서 고정 보고하며, 주대조를 사후 교체하지 않는다.

이것은 검토 우선순위 진단이다. 사람 검토가 오류를 실제 교정했다고 가정하거나 자동 교정된 정확도로 보고하지 않는다.

## 4. 보조 비교와 통계

E600 전체에서 detector bbox 유무, SFT bbox 유무, reader와 각 localizer의 독립 결합, 고정 presence gate의 판단·근거 공동 성공을 보고한다. gate는 reader-No면 빈 box, reader-Yes면 기존 box 유지, unresolved면 미해결이다. 비어 있는 box를 새로 만들지 않는다. 이 보조표만으로 주 투자 기준을 통과시키지 않는다.

환자 bootstrap 10,000회, seed11117을 사용한다. 매 resample에서 k와 confidence 경계를 다시 계산한다. 전체 공동 점수는 세 범주별 결과와 동일 가중 평균을 함께 보고한다. unresolved의 가능한 Yes/No 배정이 주 결정을 바꾸는지 보수적 범위를 계산하되 동일 응답을 조건별 독립 변수로 취급하지 않는다.

## 5. 단계와 자원

동작 확인은 12명 연결·fixture다. 가능성 탐색은 고정 E600의 저장 실제 출력 전체 비교다. 기존 출력이 모두 있으므로 효과를 본 뒤 작은 subset에서 E600으로 확대하는 선택을 만들지 않는다. 이것은 새 대량 생성이나 확증 실험이 아니다.

본격 확대·독립 확인·새 학습은 이번 범위에 없다. 양성일 때만 다음 승인용 독립 확인 설계를 제안한다. 작은 차이나 넓은 CI만으로 표본을 자동 늘리지 않는다.

새 GPU 요청은 0이다. GPU blocker 때문에 CPU에 머무르는 것이 아니라 질문에 필요한 실제 출력이 이미 존재하기 때문이다. 신규 추론이 불가피한 provenance 결함이 발견되면 임의 재생성하지 않고 해당 비교를 미실행으로 보고한다. 향후 승인된 새 생성에서는 nvidia-smi, 두 GPU의 실측 peak와 worker당 2GiB 여유, batch 확대 또는 GPU당 2 worker의 처리량 비교를 적용한다.

CPU wall-clock은 입력 읽기·hash와 최초 200 bootstrap을 측정해 산출한다. 임의 시간 상한은 없다. 단계별 manifest·입력 digest·산출물 hash를 results/iter_111에 보존하고, 동일 config에서만 안전하게 재개한다.

# Implementation Tasks for Claude

1. 기준 원문과 reuse_assets를 확인하고 승인 순수 함수만 연결한다. 기존 결과와 공통 정책은 수정하지 않는다.
2. 이번 입력 전용 provenance ledger를 작성한다. F의 원 protocol·원시 worker·completion을 내용 hash로 연결한다. detector도 checkpoint·선택 LOCK·worker 출력과 연결한다.
3. 대표 12명에서 실제 입력·정답·좌표·응답 적합성을 확인한다. 누락·충돌이면 조용히 제외하지 않는다.
4. 오류 정의·k 선택·동률 처리·bootstrap·unresolved 규칙을 과학 비교 집계 전에 잠근다. 전체 결과는 이미 개발 자료임을 명시한다.
5. 고정 전체 비교를 실행하고 환자별 사건·선택 여부·근거 row를 보존한다.
6. 독립 구현으로 matching, 주 포착 수, 동률 기대값, 공동 성공과 paired CI를 재계산한다. 원 raw JSON에서 출발한다.
7. 데이터·응답·출처 변조 거부, 빈 집합, k=0/전체, 복수 box, 동일 응답 공유, 중단 후 재개를 실제 검증한다. 과거 출력 파일을 덮어쓰지 않는다.
8. 보고서에 시험 설정·연구 관찰·연구 질문, 양성/음성/불확정과 추천 후속을 구분한다. 종료 후 full 리뷰와 사용자 승인을 기다린다.

# Evaluation (성공/실패 기준 포함)

**양성 탐색:** 주 endpoint가 0.05 이상이고 paired 95% CI 하한이 0보다 크며, GT 양성의 위치·coverage 오류에서도 추가 포착이 양수이고 최소 box score 대조보다도 순이득이 남아야 한다. 5pp는 S의 100명당 최소 5개 오류를 추가로 찾는 연구 투자 기준이며 임상 기준이 아니다. unresolved의 보수적 해석으로 방향이 뒤집히면 불확정이다. 통과하면 독립 확인을 제안한다.

**음성 투자 판단:** 주 endpoint가 0 이하이거나 추가 이득이 GT 음성의 존재 오류에만 한정되면 현재 전역 존재 확인을 위치 검증으로 확장하는 후보를 종료한다. 이는 gate의 기존 유용성을 부정하지 않는다.

**불확정:** 0보다 크지만 기준에 못 미치거나 표본·동률·unresolved에 의존하면 한계를 보고하고 이번 분석을 종료한다. 추가 표본이 어떤 결정을 바꿀지 관측 discordance로 설명할 수 있을 때만 별도 독립 확인을 권고한다. 같은 자료의 가중치·parser·검토량 최적화는 하지 않는다.

**실행 실패:** 표적 의미·환자·좌표·원 출력 연결이 성립하지 않으면 과학적 음성으로 판정하지 않는다. 허용된 한정 경로 수정 후에도 연결되지 않으면 원인과 필요한 자산을 보고한다. 별도 감사 반복을 자동 시작하지 않는다.

# Risks / Checks

- 동일 표적의 존재와 위치를 평가하지만 이것이 근거의 인과적 사용을 입증하지는 않는다.
- 존재가 맞고 위치가 틀린 사례의 발견만으로 새 contribution을 주장하지 않는다.
- RSNA 주석의 위치·coverage 오차를 임상적 오류 전체로 확대하지 않는다.
- E600은 반복 개발 자료다. 새 독립 test나 사전학습 미노출 자료로 부르지 않는다.
- detector와 SFT의 학습 예산 차이를 명시한다. 현재 모델 순위를 새로운 학습 효과로 해석하지 않는다.
- VLM 추가 호출의 비용이 존재한다. 이번 저장 분석의 CPU 비용과 실용 시스템의 추론 비용을 혼동하지 않는다.
- 과거 parser 분석은 종료 상태를 유지한다. 승인 규칙 재사용은 허용하지만 규칙 추가·의미 재판정은 하지 않는다.
- GOAL, 과거 판정·출력·checkpoint, Claude 구현 담당과 --confirm-each-iter를 유지한다.

## 대규모 GPU 필요 후보

다기관의 명시적 존재·부재와 위치 정답을 함께 사용하는 vision–language 공동 post-training은 장기 후보로 보존한다. 전역 존재 확인 이후의 중요한 잔여 문제와 강한 직접 SFT·모듈형 검증기 대비 필요성이 확인돼야 한다. 현재 진단만으로 대규모 학습이나 새 loss를 발주하지 않는다.

# 계획의 근거 (GPT 조사 노트)

## 확인한 사실과 선택

iter_110 plan.json 원문을 확인했다. 자유 생성 문장의 정답 연결 부족은 유지하며, 사용자 승인에 따라 사전 지정 소견으로 평가 범위를 바꾼다. 연구 목표 변경이나 이전 실험의 실패 판정은 아니다.

iter_042 원 리뷰에서 presence gate는 음성 false-box를 39/40에서 1/40로 줄였다. 양성 성능 보존은 불확정이고, 단순 gate 이후 큰 잔여 문제가 입증되지 않았다. 따라서 부재 거부를 같은 방식으로 다시 시험하지 않는다.

iter_037 원 리뷰와 LIMITATIONS.md는 detector–SFT의 위치 정밀도·coverage trade-off를 보존한다. detector17의 기존 선택은 epoch18, threshold0.70이다. iter_046/048 원 리뷰의 적응 모듈형 대안과 공동 형식 학습 회복도 받아들인다.

iter_082 원 리뷰에서 MRI 불일치 순위는 confidence보다 큰 오류를 적게 포착했다(3 대 5). 불일치 자체의 유용성을 가정하지 않으며, 이번에도 강한 confidence 대조와 같은 검토량을 요구한다. MRI 과제는 재개하지 않는다.

## 실제 자산 확인

현재 research HEAD는 ba6cdae9e66497b28cad778c02000b6543456f86이며 git status는 깨끗했다. ev108_data.py, ev108_spec.py, ev109_extract.py, rsna_diag/qa_spec.py와 관련 원 리뷰를 읽었다. E600은 600명이며 labels.json에 category·patient·원본 pixel box·정규화 box가 있다. Q_O는 pulmonary opacity suspicious for pneumonia를 묻고 환자 정답은 입력하지 않는다.

research/results/iter_035/confirm800/det17/raw_preds.json의 실제 행에서 boxes_xyxy_px, scores, labels, img_hw를 확인했다. select/LOCK.json과 seed17/v400_selection.json에 checkpoint·threshold가 보존돼 있다. E600 전체 연결과 원본 정답 출처의 재검증은 구현의 한정 점검에 남긴다. 이번 계획 단계에서는 새 joint metric이나 비교 결과를 계산하지 않았다.

iter_109의 F 추출 ledger 실제 행을 확인했다. 이를 편의상 새 정답으로 사용하지 않고 iter_016 원시 응답·요청·protocol·completion에 연결한다. iter_109의 ledger 분기 결함과 iter_037의 자동 provenance 결함 때문에 기존 분석 CLI를 그대로 실행하지 않는다. 승인된 순수 함수만 재사용한다.

## 가까운 선행

[Phrase-grounded Fact-checking](https://arxiv.org/abs/2509.21356)은 소견과 위치 오류 검증을 이미 다룬다. 따라서 판단·위치 공동 평가 자체를 새 기여로 주장하지 않는다. [Generalised Medical Phrase Grounding](https://arxiv.org/abs/2512.01085)은 zero/one/multiple scored regions와 모듈형 구성을 다룬다. 이번 확인은 논문 초록 범위이며 해당 방법의 전체 재현이나 우열 비교가 아니다.

## 비용과 한계

이번 질문은 보존된 실제 출력으로 직접 비교할 수 있다. 새 GPU 생성 없이도 가설을 검증할 수 있어 CPU 분석을 선택했다. GPU 접근 blocker가 있는 것은 아니다. 과거 출력의 재생성은 추가 정보가 없고, 주요 비용은 연결·검증 구현일 것으로 예상하나 실제 비중은 미측정이다. 반복 개발 자료의 탐색으로 보고한다.
