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

iter_026의 고정 RSNA 개발 E60 중 primary 48명에서 seed17 grounding SFT B0의 지정 사분면 bbox 선택 점수 S는 M0보다 높았지만, 전체 bbox 복사 baseline보다 낫다는 근거는 없었다. 다중 사분면 22명의 Q4_select는 직접 B0 0/22, B0 bbox+규칙 11/22였다. 현재 인터페이스의 제한된 관찰이며, oracle 선택 실패와 E200 미완료 때문에 일반적인 공간 능력 전이 부재나 내부 원인을 확정하지 않는다.

- 적용 목표 시작: iter_003
- 최신 리뷰: agent/runs/iter_026/review.json
- 근거: research/results/iter_026/gen/E60_{V__M0,V__B0,RD__M0}/gen_worker*.jsonl: 720건 실제 출력.
- 근거: 리뷰 독립 parser·matching 재계산: primary 48명의 B0−M0 S=0.228624, 95% CI [0.171281, 0.284445]; B0−Copy_B0=0.000218, CI [-0.030970, 0.032546].
- 근거: 동일 primary에서 Rule_B0−direct B0=0.403320, CI [0.318012, 0.482821]; 다중 사분면 22명은 직접 0명·규칙 11명 성공.
- 근거: D24 oracle은 M0/B0 각각 Q4_select 1/24이며, 다중 사분면 14명에서는 두 모델 모두 0/14.
- 사용·평가 검증: 완료된 D488·E720의 예상 환자×영역 행렬, 요청 중복·누락, 주요 request-record provenance 불일치 0을 독립 확인했다.
- 사용·평가 검증: 현재 영상 84개의 file/raw pixel/padded input hash 불일치 0, 별도 parser와 기존 parser의 판정·box 불일치 0을 확인했다.
- 사용·평가 검증: sanity_post.json의 tensor 대조와 adapter digest 및 8건 재생성 일치를 확인했다. tensor 대조는 D의 한 영상·V_TL prompt 범위이며 과거 bbox baseline 재현 검사는 아니다.
- 사용·평가 검증: 저장 평가의 primary/boundary 혼합을 리뷰에서 분리 재계산했다. 정식 평가기 수정과 재개·변조 검증은 남아 있다.
- 미해결: E200 primary 160명·다중 사분면 66명에서도 같은 패턴이 유지되는가?
- 미해결: oracle 실패에 좌표 지시 해석과 제공 목록의 schema 불일치가 얼마나 기여하는가?
- 미해결: 부분적인 질의 조건화와 신뢰할 만한 전체 선택을 구분해야 하며, 다른 seed·독립 원천 데이터의 재현은 미검증이다.

