# 한계 주장과 검증 근거

초기 판단: LIMITATIONS.json. 이후 변경 근거: 각 반복의 review.json/limitation_updates.
validated는 명시한 조건에서 사용·평가 오류를 통제해 성능 문제를 재현했다는 뜻이며, 내부 원인 확정이 아니다.

## lesion-grounding-generalization — validated

MedGemma 1.5 revision 91850547d9f0b2fdd21aa7c5f4f3d1a8a52c243b의 정상 사용 조건에서 확인된 RSNA opacity grounding 위치 불일치는 유지된다(iter_009 양성 200명 중 공통 위치 불일치 134명). 다만 경량 적응으로 개선 가능한 문제임을 확인했다. iter_012의 별도 확인 양성 400명에서 미적응 official_long/concise의 F1@0.3은 0.165/0.081이고, 직접 언어층 rank16 LoRA SFT는 세 seed에서 0.631–0.653이었다. 이는 해당 데이터·학습 조건의 개선이며, 모든 병변의 일반화 실패나 내부 병목을 입증하지 않는다.

- 적용 목표 시작: iter_003
- 최신 리뷰: agent/runs/iter_012/review.json
- 근거: agent/runs/iter_009/review.json: 정상 사용 검증과 독립 양성 200명의 위치 불일치 근거.
- 근거: research/results/iter_012/confirm_base/gen_worker*.jsonl 및 confirm_sft_seed{17,29,43}/gen_worker*.jsonl: 확인 800명에 대한 4,000개 고유 요청.
- 근거: research/results/iter_012/final/confirm_result.json: prior_set 대비 평균 F1@0.3 차이 0.2155833, 환자 bootstrap 95% CI [0.1715271, 0.2591139]. 리뷰의 별도 parser·matching 재계산과 일치.
- 근거: SFT의 F1@0.5는 0.313–0.364이고 양성 빈 응답은 15.25–18.5%로 잔여 오류가 남는다.
- 사용·평가 검증: iter_009의 공식 예제·chat template·전처리 검증 범위를 재사용했다. 이번 리뷰에서 공식 GPU 예제를 재실행하지 않았다.
- 사용·평가 검증: iter_012 protocol에 잠긴 38개 파일 hash와 현재 파일이 모두 일치하고, tracked 파일은 리뷰 SHA 783d2d04671ae296f3dc0c700e575f8af8e021c9와 일치했다.
- 사용·평가 검증: 현재 영상 3,600개의 file/pixel hash 불일치 0, train/validation/confirm 간 환자 및 pixel hash 교집합 0을 확인했다.
- 사용·평가 검증: validation base와 confirm의 원시 4,800요청에서 파일·prompt·protocol·adapter 연결 및 EOS 판별 불일치 0을 확인했다.
- 사용·평가 검증: 20개 epoch의 validation 8,000요청을 재집계해 저장 점수와 일치함을 확인했다. 확인 주지표는 별도 구현으로 재계산했다.
- 미해결: 더 충분한 직접 SFT와 비교해도 위치 정밀도·작은 병변·미검출 개선을 위한 새 방법의 이득이 남는가?
- 미해결: 다른 데이터셋과 새 독립 확인 집단에서도 개선되는가?
- 미해결: 주석 경계 모호성, 사전학습 노출 및 legacy 익명 영상 중복의 불확실성은 남는다.
- 미해결: 이번 결과는 pooling 병목이나 anatomy 전이의 필요성을 확정하지 않는다.

## context-sensitivity — observed

3개 case의 GT 구성 pilot에서 context에 따른 점수 변화가 관찰됐다. context가 정답을 개선한 경우도 있어 변화 자체를 모델 결함으로 일반화할 수 없다.

- 적용 목표 시작: iter_003
- 근거: agent/runs/iter_003/review.md
- 사용·평가 검증: teacher-forced 대조와 일부 생성 답변 일치 확인 기록 있음. oracle 입력 구성·표본·해부학적 confound 한계가 남는다.
- 미해결: 동일 정답을 유지하는 유효한 context 변화가 독립 표본에서 실제 답변을 악화시키는가?

## pooling-causal-bottleneck — candidate

pooling이 병변 grounding 실패의 원인이라는 일반 가설은 미확인이다. iter_007의 제한된 head 비교에서는 pooling 전 feature의 추가 이득이 관찰되지 않았다.

- 적용 목표 시작: iter_003
- 근거: agent/runs/iter_007/review.md
- 사용·평가 검증: 공간 정렬·pooling·linear 대조는 기록상 통과. 실제 VLM 출력 비교·head 수렴·데이터 좌표 근거의 한계는 남는다.
- 미해결: 이 후보를 다시 조사할 새로운 근거가 있는가? 기존 음성 결과를 일반적인 정보 손실 부재나 decoder 병목 증명으로 바꾸지 않는다.

## no-localization-capability — rejected

MedGemma 1.5에는 좌표 출력/grounding 능력 자체가 없다는 과거 주장은 문서 버전과 사용 형식 오류로 철회됐다.

- 적용 목표 시작: iter_003
- 근거: legacy/docs/MEDGEMMA_평가_전체정리.txt의 중대 정정
- 근거: agent/runs/iter_003/think/round_03.md
- 사용·평가 검증: 공식 anatomy notebook 확인 기록: agent/runs/iter_003/think/round_03.md. 후속 계획은 이 출처를 다시 읽고 버전·사용 조건을 확인할 것.

## qa-format-compliance-after-grounding-sft — observed

고정 RSNA 개발 집단 E600에서 grounding SFT B0의 Q_A strict valid는 418/600으로 M0의 576/600보다 낮지만, 사전 고정한 semantic_v1 적용 후에는 각각 600/600, 584/600이다. B0−M0의 S_scope 차이는 strict −0.255에서 semantic −0.0317로 줄었다. 형식 차이가 평가상 저하의 상당 부분을 설명하지만, category별 잔여 변화까지 사라진 것은 아니다. 시각적 forgetting이나 일반적 의미 구분 능력 손실은 입증되지 않았다.

- 적용 목표 시작: iter_003
- 최신 리뷰: agent/runs/iter_016/review.json
- 근거: research/results/iter_016/gen/{e180_plain,e600x_plain}__{M0,B0,C}/gen_worker*.jsonl: primary QA 3,600건.
- 근거: research/results/iter_016/e600/report.json: semantic S_scope M0/B0/C=0.6100/0.5783/0.5883, B0−M0의 97.5% CI [−0.0667, 0.0050].
- 근거: 리뷰 독립 재계산: B0−M0의 category별 정답 쌍 정확도 차이는 opacity −0.105, Normal +0.095, NoOpacity/NotNormal −0.085.
- 사용·평가 검증: semantic_v1은 D36에서 결정한 whole-string 규칙이며 Normal/Abnormal 대응은 Q_A에만 적용한다.
- 사용·평가 검증: 리뷰에서 원시 응답에 별도 parser와 paired bootstrap을 적용해 주지표와 CI를 재현했다.
- 사용·평가 검증: 정식 신규 6,180건 모두 EOS 종료, 요청 중복·누락과 주요 provenance 불일치 0.
- 사용·평가 검증: 현재 영상 636개의 file/raw pixel hash 및 신규 출력의 padded input hash 불일치 0.
- 미해결: 다른 학습 seed와 독립 환자·기관에서도 category별 변화가 재현되는가?
- 미해결: 잔여 변화가 답변 prior, 질문 해석, 시각 정보 활용 중 무엇에서 비롯되는가?
- 미해결: E600은 개발 자료이며 이번 결과를 새 독립 확인으로 해석할 수 없다.

## rsna-evidence-interface-sensitivity — observed

고정 RSNA 개발 집단 E600에서 공통 문구의 검출 정보 B는 정보 미제공 U보다 S_scope가 0.0533 높았고, 개수 K의 추가 차이는 0.0150이었다. 좌표 L과 K의 정답 쌍 정확도는 600명 모두 같았지만 개별 질문 답변은 1/1,200건 달랐다. L−direct M0는 0.0117로 불확정이며, NoOpacity/NotNormal 정답 쌍 정확도는 direct 40/200에서 L 4/200으로 낮아졌다. 기존 모듈형 이득은 인터페이스에 의존하며, 현재 과제에서 좌표의 추가 성능 이득은 관찰되지 않았다. 일반적인 좌표 활용 능력이나 시각 정보 무사용을 입증하지 않는다.

- 적용 목표 시작: iter_003
- 최신 리뷰: agent/runs/iter_017/review.json
- 근거: research/results/iter_017/gen/{p180_ev17,e600x_ev17}__M0/gen_worker*.jsonl: 신규 본평가 4,800건, 600명.
- 근거: research/results/iter_017/e600/analysis_e600.json 및 리뷰 독립 재계산: U/B/K/L S_scope=0.553333/0.606667/0.621667/0.621667.
- 근거: B−U 97.5% CI [0.031667, 0.076667], K−B 95% CI [0.006667, 0.025000], L−direct M0 95% CI [−0.015000, 0.040000].
- 근거: 동일 P180의 L−기존 predicted 차이 −0.066667, 저장 95% CI [−0.105556, −0.033333]. 기존 조건의 성과는 보존하되 문구 변경에 대한 안정성은 지지되지 않는다.
- 근거: nonempty 236명의 L−K 정답 쌍 차이도 0이다. 개별 답변 차이는 con_00020008의 Q_A에서 확인됐다.
- 사용·평가 검증: 리뷰에서 신규 4,800개 요청을 B0 원본 bbox와 고정 template으로 재구성해 저장 요청과 완전히 일치함을 확인했다.
- 사용·평가 검증: 별도 parser와 category 내 환자 paired bootstrap 10,000회로 주지표·주요 CI를 재현했다.
- 사용·평가 검증: 신규 요청의 누락·중복·잉여, 주요 provenance 불일치와 비EOS 종료는 0이었다.
- 사용·평가 검증: 현재 영상 636개의 file/raw pixel hash와 신규 출력의 padded pixel hash 불일치 0을 확인했다.
- 사용·평가 검증: 세 protocol의 잠긴 파일 각 32개와 현재 파일이 일치하고, tracked 파일은 리뷰 SHA와 일치했다.
- 사용·평가 검증: E600은 기존 개발 집단이며 새 독립 확인이 아니다. X는 사전 실행 조건을 충족하지 않아 미실행했다.
- 미해결: NoOpacity/NotNormal 손실이 독립 환자와 다른 데이터에서도 재현되는가?
- 미해결: 손실은 질문 범위 해석, 문구에 따른 답변 prior, 검출 신호의 과도한 일반화 중 무엇으로 설명되는가?
- 미해결: 좌표가 필요한 다른 과제에서도 추가 이득이 없는가? 이번 결과로는 판단할 수 없다.
- 미해결: 현재 bootstrap의 [0,0]은 관찰된 정답 쌍 차이가 모두 0이어서 생긴 결과이며 모집단 효과의 정확한 영점을 의미하지 않는다.

## mri-reference-interface-sensitivity — observed

SPIDER T2의 동일 volume slice-pair를 사용하는 iter_021 최종 prompt와 개발 E48에서, 정답 내부점을 텍스트로 제공한 O의 pair success는 0/48, instance success@0.5는 2/96이었다. J_RT/J_TR은 각각 18/48, 34/48이지만 reference 좌표를 그대로 출력한 응답이 각각 57/96, 79/96이어서 영상 간 대상 매칭 능력의 증거로 해석할 수 없다. 정상 사용 대조와 독립 재현이 미완료이므로 일반적인 point grounding 결함이나 내부 원인은 미확인이다.

- 적용 목표 시작: iter_003
- 최신 리뷰: agent/runs/iter_021/review.json
- 근거: research/results/iter_021/gen/E__phase1/gen_worker*.jsonl: O·J_RT·J_TR의 원시 응답을 별도 JSON 추출과 IoU 계산으로 재집계했다.
- 근거: research/results/iter_021/data/manifest.json 및 eval_raw_E.json: O 평균 IoU 0.1070435, J_RT/J_TR pair success 18/48·34/48을 재현했다.
- 근거: J_TR의 wrong-instance는 0/96이며, report_E.json의 H.detail에서 has_wrong도 0/48이다.
- 사용·평가 검증: 모델 revision 91850547d9f0b2fdd21aa7c5f4f3d1a8a52c243b와 저장된 processor·chat template 정보를 확인했다.
- 사용·평가 검증: 최종 672개 요청의 ID·prompt hash·조건·영상 순서 및 현재 영상의 file/pixel hash를 원시 record와 대조했다.
- 사용·평가 검증: O·J_RT·J_TR은 모두 EOS로 종료했으며 단일 bbox를 반환했다.
- 사용·평가 검증: 실제 D 입력의 공식 구성과 wrapper 간 input_ids·pixel_values 대조 완료 근거는 확인하지 못했다.
- 사용·평가 검증: prompt 수정 전에 E 환자 9명의 부분 출력 10건이 존재하므로 E48을 독립 확인 집단으로 취급하지 않는다.
- 미해결: O 저하가 점 좌표 해석, 대상 범위, prompt 표현 중 무엇으로 설명되는가?
- 미해결: 좌표 복사가 유리한 현재 동일-grid 과제가 실제 reference 정보 활용을 식별할 수 있는가?
- 미해결: 정상 사용 대조 후에도 중요한 잔여 실패가 독립 환자에서 재현되는가?

## rsna-quadrant-oracle-interface — observed

고정 RSNA D24 개발 환자에서 제공 목록만 사용하라는 지시와 중심 계산식을 추가해도 bbox oracle 정확도는 M0 영상/텍스트 41/96·42/96, B0 50/96·42/96으로 90% gate를 충족하지 못했다. 계산된 중심 제공도 충분하지 않았고, 사분면 이름 제공은 M0 90/96·B0 96/96이었다. 이 차이는 현재 인터페이스의 제한된 관찰이며 산술 원인, 일반적 공간 능력 결함 또는 SFT 전이 실패를 확정하지 않는다.

- 적용 목표 시작: iter_003
- 최신 리뷰: agent/runs/iter_025/review.json
- 근거: research/results/iter_025/gen/{D,AR}__{M0,B0}/gen_worker*.jsonl: D 768건·AR 192건을 독립 재집계했다.
- 근거: research/results/iter_025/eval/report_D.json: OC 영상/텍스트 정확도는 M0 39/96·49/96, B0 42/96·44/96이다.
- 근거: research/results/iter_025/decide/D_decision.json: passed=false이며 E60/E200은 미실행이다.
- 사용·평가 검증: 960건의 요청 집합 일치, 중복·누락 없음, 주요 request-record provenance 일치와 EOS 종료를 확인했다.
- 사용·평가 검증: D24 bbox는 iter_010 원본 주석 및 iter_023 labels와 일치했고, 현재 영상 24개의 file/raw pixel hash와 I/T의 동일 텍스트를 확인했다.
- 사용·평가 검증: sanity/sanity.json은 bbox 재생성 8건의 기존 token 일치와 B0 adapter digest 일치를 기록한다. 공식 구성과 실제 D tensor의 동등성 검사는 수행하지 않았다.
- 사용·평가 검증: M0 OB_T 24건·OC_T 3건은 완결된 thinking marker 뒤에 답이 있으나 기존 parser에서 invalid 처리됐다. 사전 계획한 marker 처리는 구현되지 않았다.
- 미해결: 표현·지시 해석·응답 prior·형식의 기여는 아직 분리되지 않았다.
- 미해결: 독립 환자·다른 seed에서의 재현과 직접 시각 질의 전이는 미검증이다.
- 미해결: 현재 사분면 yes/no 인터페이스보다 학습된 bbox 출력 형식을 유지하는 영역 선택 진단이 더 식별력 있는가?

## rsna-region-selection-transfer — observed

고정 RSNA 개발 E200의 primary 160명에서 seed17 grounding SFT B0는 M0보다 지정 사분면 bbox 선택 점수 S가 높았지만, 전체 bbox 복사 대비 사전 양성 기준은 충족하지 못했다. 다중 사분면 66명의 전체 선택 Q4_select는 직접 B0 0/66, B0 bbox+규칙 26/66으로 현재 인터페이스의 사전 음성 기준을 충족했다. 부분적인 질의 반응은 남으며, oracle 실패 때문에 일반적인 공간 전이 부재나 내부 원인은 확정하지 않는다.

- 적용 목표 시작: iter_003
- 최신 리뷰: agent/runs/iter_027/review.json
- 근거: research/results/iter_026/gen/{E60,E200_extra}_{V__M0,V__B0,RD__M0}/gen_worker*.jsonl: 200명×4영역×3조건의 2,400건.
- 근거: research/results/iter_027/eval/report_E200.json: primary B0−M0 S=0.194292, 95% CI [0.163216, 0.226417]; B0−Copy_B0=0.018060, CI [-0.004103, 0.042368]. 리뷰의 별도 matching·bootstrap 계산과 일치.
- 근거: 다중 사분면 66명 직접 B0 0/66, exact CI [0, 0.054359]; 규칙 26/66, CI [0.275809, 0.521910]. 리뷰에서 성공 수를 별도 재계산.
- 근거: Rule_B0−direct B0 S=0.304984, 95% CI [0.252904, 0.356755]. 저장 C_query_B0=0.019755, CI 하한 0.006957.
- 사용·평가 검증: 리뷰에서 6개 job의 예상 환자×영역 행렬, 요청 ID와 원시 결과의 일치, 중복·누락·잉여 없음 및 completion 종료 코드 0을 확인했다.
- 사용·평가 검증: 요청과 원시 결과의 공통 필드 불일치 0, record와 completion의 protocol/adapter digest 불일치 0을 확인했다.
- 사용·평가 검증: 현재 영상 200개의 file/raw pixel hash 불일치 0을 확인했다. 최종 비EOS 19건은 parser에서 invalid로 처리한다.
- 사용·평가 검증: sanity/sanity.json의 V_TL·RD_TL 전체 tensor key/shape/dtype/value 비교, adapter digest, 기존 D 영역 질의 8건 재생성 통과를 확인했다. 이는 기존 전체 bbox baseline 재생성 검사는 아니다.
- 사용·평가 검증: 공통 parser를 적용한 뒤 별도 최대 matching과 환자 bootstrap으로 주요 S 차이·CI 및 Q4 성공 수를 재현했다.
- 미해결: oracle 목록 schema와 좌표·지시 해석을 바로잡은 조건에서도 같은 선택 단절이 남는가?
- 미해결: 부분적인 질의 반응과 신뢰할 만한 전체 선택을 구분하는 최소 진단이 다음 투자 판단을 바꾸는가?
- 미해결: 다른 seed·독립 환자·다른 원천 데이터에서의 재현은 미검증이다. E200은 개발 자료다.

## rsna-partial-omission-continuation — observed

RSNA seed17 grounding SFT의 nonempty 개발 출력 C201/E402에서 마지막 닫기 token을 한 번 continuation으로 바꾸면, 엄격한 부분 누락 사건의 8/20·11/27에서 누락 GT와 대응하는 추가 후보가 생성됐다. 그러나 E402 전체의 환자 평균 F1@0.3은 0.6276에서 0.4738로 하락했다. 후보 회복은 관찰됐지만 실용적 검출 개선, 종료의 유일한 인과 역할, 일반적인 능력 전이를 입증하지 않는다.

- 적용 목표 시작: iter_003
- 최신 리뷰: agent/runs/iter_031/review.json
- 근거: research/results/iter_031/{C201,E402}/attempt1/gen_worker*.jsonl: 원시 1,206건의 token과 별도 JSON 해석·최대 cardinality matching으로 회복 8/20·11/27을 재현했다.
- 근거: research/results/iter_031/E402/report.json: 회복률 0.4074, Wilson 95% CI 약 [0.245, 0.593]; F1@0.3 차이 -0.15377, 저장 paired 95% CI [-0.16951, -0.13735].
- 근거: E402의 추가 FP는 환자당 1.0373이며, Q−선택 token NLL AUROC 차이는 -0.001086, 독립 재계산한 97.5% CI [-0.005157, 0.002590]이다.
- 사용·평가 검증: C/E 603명의 원본 seed17 suffix, 현재 영상 file/RGB pixel hash, audit GT와 iter_010 GT manifest를 대조해 불일치 0을 확인했다.
- 사용·평가 검증: O token 재현·F 개입 전 token prefix·강제 token·기존 bbox 보존·EOS를 원시 출력에서 확인했다.
- 사용·평가 검증: sanity/sanity.json은 D 6명의 공식 chat 구성과 wrapper 전체 tensor 일치 및 adapter 활성 재생성 2건을 기록한다.
- 사용·평가 검증: 독립 float64 score 대조와 계획한 전체 재개·긴 출력 검증은 미완료다. C/E는 개발 자료다.
- 미해결: 추가 후보 수와 비용을 맞춘 단순 대안에서도 같은 회복이 나타나는가?
- 미해결: 추가 FP를 억제하면서 회복을 유지하는 선택 기준이 강한 단순 baseline보다 유리한가?
- 미해결: 다른 seed·환자·원천 데이터에서 재현되는가? 임상적 완전성과의 관계는 미확인이다.

## rsna-detector-sft-localization-tradeoff — observed

고정 RSNA 개발800명(양성400명·GT589개)에서 detector–SFT의 상보성은 주로 threshold 제외와 연결되지만, 낮은 threshold의 후보 회복에는 FP 비용이 따른다. detector17의 선택점→budget1.0에서 SFT17-only GT는 77→23개로 감소하고 FP/환자는 0.295→1.0075로 증가했다. F1@0.3은 0.58164→0.58443으로 SFT17의 0.63075보다 낮고, F1@0.5는 0.41555→0.43852로 SFT17의 0.34867보다 높았다. 두 detector 모두 검토한 운영점에서 F1@0.3 점추정치는 SFT17보다 낮았다. 이는 반복 분석된 개발 자료·고정 운영점의 trade-off이며, 일반적인 detector 우위나 VLM 고유 능력·외부 일반화를 입증하지 않는다.

- 적용 목표 시작: iter_003
- 최신 리뷰: agent/runs/iter_037/review.json
- 근거: research/results/iter_037/a1/confirm800/report.json: 두 detector의 선택점 및 FP budget0.25/0.5/1.0 성능·FP·상보성 표.
- 근거: detector17/SFT17 선택점의 threshold 제외75/77개, detector29/SFT17은80/87개이며 R은1/589·7/589로 기존 결과와 일치한다.
- 근거: 리뷰에서 V400 533항목·개발800 943항목을 원시 출력으로 재계산했고 불일치0이었다. 개발800의 두 detector×4운영점×2 IoU에 대한 SFT17 대비 paired F1 CI 16개도 독립 재계산해 일치했다.
- 근거: IoU0.3 원래 대응쌍의 IoU0.5 통과율은 detector17 268/375, SFT17 216/381이다. 저장된 pair 행에서는 통과 여부와 독립 재매칭 검출 여부의 불일치가 없다.
- 사용·평가 검증: 리뷰 대상 SHA 755ec06e17606936422f1595f7bf62dc53085e59의 신규5파일과 작업 파일이 일치했고, V400·개발800 manifest의 분석 소스 hash도 일치했다.
- 사용·평가 검증: 선택 LOCK의5파일 hash, 현재 V400·개발800 영상1,200개의 file hash를 확인했으며 불일치0, 두 집단의 환자 ID 교집합0이었다.
- 사용·평가 검증: iter_012 protocol 중 현재 분석에 관련된 manifest·parser·geometry·metrics 13파일의 hash가 일치했다. 전체 과거 실행 소스 재검증이나 공식 GPU 예제 재실행은 하지 않았다.
- 사용·평가 검증: V400 검사는 iter_036 이후 사후 회귀 검사로 기록됐으며, threshold나 checkpoint를 재선택하지 않았다.
- 사용·평가 검증: 새 GPU 생성·학습·외부 평가는 수행하지 않았다. 현재 입력의 cap100 도달0건과 작은 R은 GPU trace 미진입을 지지한다.
- 미해결: 검증된 외부 자료에서도 위치 정밀도·미검출·FP의 trade-off가 유지되는가?
- 미해결: 표준 calibration이나 선택 방법이 고정된 강한 기준점보다 실제 효용을 높이는지는 미검증이다.
- 미해결: 언어와 영상 근거를 연결해야 하는 실제 과제에서 직접 SFT와 detector+VLM의 차별적 가치가 있는가?
- 미해결: 후처리 전 후보, annotation 경계 모호성, 사전학습 노출, SOP 수준 독립성 및 seed29 완전 수렴은 미확인이다.

## padchest-sentence-grounding-and-joint-retention — observed

PadChest-GR 개발 V96의 공동 요청 손실은 직접 공동 형식 학습으로 상당 부분 회복되지만 완전히 해소되지는 않았다. 동일 C 초기 상태·T305 annotation 노출·seed17·8 epoch에서 추가 독립 SFT E와 공동 SFT J의 공동 F1@0.3은 0.333116/0.523251이었다. 선택적 회복 기준은 충족했으나 J의 독립 대비 공동 손실 0.067225가 남았고, 독립 성능 보존 충분성·적응 MedGrounder 대비 필요한 정확도 이점·공동 처리 비용 기회는 충족하지 못했다. 이는 학습 형식 개입의 제한적 효과이며 일반적인 결합 능력 결함이나 순수한 내부 원인을 확정하지 않는다. iter_046의 MedGrounder 적응 효과와 대안 충분성의 불확정 판정은 유지한다.

- 적용 목표 시작: iter_003
- 최신 리뷰: agent/runs/iter_048/review.json
- 근거: research/results/iter_048/eval/report.json 및 원시 C/E/J 출력 각 384건: 독립/공동 F1@0.3은 C 0.577951/0.367622, E 0.558883/0.333116, J 0.590476/0.523251이다.
- 근거: J_J−E_J=0.190135, 97.5% CI [0.138051, 0.243955]; 손실 감소 (E_I−E_J)−(J_I−J_J)=0.158542, CI [0.096577, 0.220512].
- 근거: J_I−E_I의 95% CI 하한은 약 −0.014로 −0.03 보존 기준을 충족한다. 그러나 J_AB/BA의 E_I 대비 복합 충분성 기준은 미달이다.
- 근거: 적응 MedGrounder A의 원시 192문장 재채점: F1@0.3=0.594444, F1@0.5=0.394097. J_J−A F1@0.3은 약 −0.071193이다.
- 근거: research/results/iter_048/timing/: 6 paired block의 J/E device-seconds 비율 0.963408 [0.922054, 1.006618], throughput 비율 1.033075 [0.990435, 1.077552].
- 근거: 원본 좌표 변환까지 포함해 리뷰에서 보정한 A/E device-seconds 비율은 0.031804 [0.030755, 0.032889]이다. 원 보고서의 작은 집계 누락을 보정해도 투자 판단은 변하지 않는다.
- 사용·평가 검증: 리뷰에서 production 평가기를 호출하지 않고 C/E/J 원시 JSON, 좌표 변환, 최대 일대일 matching을 재구현했다. 환자별 네 지표의 저장 벡터와 최대 차이는 5.56e-17이며 두 주비교 bootstrap을 독립 재현했다.
- 사용·평가 검증: A의 원시 192문장을 별도 matching 구현으로 재채점해 F1@0.3/0.5를 재현했다.
- 사용·평가 검증: T305/D24/V96의 환자·study·영상 ID 교집합은 모두 0이며 현재 V96 영상 file hash는 96/96 일치했다. 전체 pixel 검사는 tests/gate_data_final.json에 보존돼 있다.
- 사용·평가 검증: 공식 processor·assistant mask·EOS·GT 대조 32개 입력과 결정적 GPU 검사, 재개 검사 결과를 확인했다. 마지막 비EOS 출력은 평가 분모에 유지됐다.
- 사용·평가 검증: E/J 학습 로그에서 각 312개 연속 update, 각 2,440회 환자 노출, LR1e-5, 유한 loss/gradient를 확인했다.
- 사용·평가 검증: 리뷰 대상 SHA 54607a22c7046d0ab75fde09b2a5616edf0e2344의 변경 파일과 작업 파일이 일치하고, completion에 기록된 파일 digest 및 평가 verifier의 report/selection 연결을 확인했다.
- 미해결: 단일 seed·반복 사용한 개발 V96이며 독립 환자·기관 재현이 아니다.
- 미해결: 공동 학습은 prompt·직렬화·영상 반복 횟수를 함께 바꾸므로 순수한 syntax 효과나 내부 원인을 분리하지 못한다.
- 미해결: D24 생성 점수 상승과 teacher-forced CE 악화가 함께 있어 수렴한 공동 학습 전체의 한계로 일반화할 수 없다.
- 미해결: 부재 거부·보고서 생성·근거 기반 답변은 이번 비교로 설명하거나 기각하지 않는다.
- 미해결: iter_041의 원 비용 blocker는 유지한다. 이번 신규 측정은 과거 결과의 소급 확증이 아니다.

## padchest-presence-grounding-interface — observed

PadChest-GR의 새 개발 집단 흉수 양성 29명·보고서상 음성 40명에서, 직접 SFT C의 중립 grounding 출력은 음성 valid nonempty 20건·invalid 20건·valid empty 0건이었다. M0는 각각 7·0·33건이었다. 그러나 M0/C presence gate를 적용하면 C의 음성 nonempty는 각각 1/40로 감소했다. 양성 F1@0.3은 C_short 0.4080, C_neutral 및 P0 gate 0.3851, PC gate 0.3678이었다. 현재 인터페이스의 부재 거부 문제는 관찰됐지만 단순 gate 이후의 중요한 잔여 문제, 양성 성능 보존, 일반적인 SFT 유발 능력 손상은 확정하지 않는다.

- 적용 목표 시작: iter_003
- 최신 리뷰: agent/runs/iter_042/review.json
- 근거: research/results/iter_042/eval/report_E.json 및 report_E_per_patient.json: 리뷰에서 E_M0/E_C 원시 출력 414건의 환자별 F1@0.3·0.5, 음성 분류 및 paired CI를 독립 재계산해 일치 확인.
- 근거: 중립 질의의 C−M0 음성 false-box 차이 +0.325, 97.5% CI [0.150, 0.500]. 존재 전제 질의에서는 −0.025, CI [−0.100, 0.000].
- 근거: P0/PC gate의 C_short 대비 양성 F1 차이는 −0.02299/−0.04023이며 95% CI는 각각 [−0.13218, 0.07471]/[−0.15517, 0.06322].
- 근거: research/results/iter_042/data/review_private.json: 출력 전 적격성 검토와 제외 사유. 음성 reference는 영상 재판독이 아닌 제공 보고서의 명시적 부재 진술이다.
- 사용·평가 검증: 리뷰 SHA e7ee15464cf404a44a877997661b9f50dd8c3096의 대상 소스 21개가 작업 파일과 일치하고 반입 파일 12개의 blob이 원본 SHA와 일치했다.
- 사용·평가 검증: D/E 원본 ZIP 영상 75개의 PNG·uint16·uint8·padding 후 입력 hash를 검증했다. E의 환자·study·영상·원본 pixel hash는 기존 제외 manifest와 겹치지 않았다.
- 사용·평가 검증: 고정 prompt·caps 1000/2000/4000·요청/record/config/adapter 연결과 본실험 completion을 확인했다. 두 모델에서 각 1건의 G_short 비EOS 출력은 invalid로 유지했다.
- 사용·평가 검증: 공식 template와 전처리 경로는 iter_039 검증을 동일 소스 범위에서 재사용했다. E 이전에 고정한 parser를 유지했으며 label 오류와 정상 빈 출력을 구분했다.
- 사용·평가 검증: C_neutral의 음성 label 오류 20건도 label을 무시하면 nonempty였다. 형식 오류를 성공적인 부재 거부로 계산하지 않았다.
- 미해결: 단일 target·단일 SFT seed·작은 개발 집단이다. 독립 환자·기관·모델 재현과 사전학습 미노출은 확인하지 않았다.
- 미해결: 중립 질의의 적응 전후 차이가 미학습 지시·label 형식·양성-only 학습 분포 중 무엇에 기인하는지는 미확정이다.
- 미해결: presence gate의 양성 손실이 사전 허용 폭 0.05 이내인지와 실제 두 단계 latency는 미확정이다.
- 미해결: 현재 사전 규칙은 투자 보류다. 이 불확실성만으로 환자·prompt·seed·학습을 자동 추가하지 않는다.

