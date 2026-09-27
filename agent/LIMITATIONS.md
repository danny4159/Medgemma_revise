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

고정 RSNA P180에서 원본 영상과 B0 예측 bbox를 받은 M0 reader는 unavailable 안내 조건보다 S_scope가 0.1278 높았다. 그러나 Normal과 NoOpacity/NotNormal에서 효과 방향이 반대이고, oracle 조건의 Normal 정답 쌍 정확도는 0/60이었다. 현재 evidence 구성에 따른 답변 변화는 관찰됐지만, bbox 정보와 안내 문구의 인과 효과는 분리되지 않았다.

- 적용 목표 시작: iter_003
- 최신 리뷰: agent/runs/iter_016/review.json
- 근거: research/results/iter_016/gen/{p60_ev,p180x_ev}__M0/gen_worker*.jsonl: evidence QA 1,080건.
- 근거: research/results/iter_016/e600/report.json: predicted/unavailable/oracle S_scope=0.7000/0.5722/0.6444.
- 근거: 리뷰 독립 재계산: predicted−unavailable 95% CI [0.0556, 0.2000], 동일 P180 direct M0 대비 +0.0778 [0.0278, 0.1333].
- 사용·평가 검증: 세 evidence 조건 모두 원본 영상을 유지하고 동일 target·parser를 사용한다.
- 사용·평가 검증: evidence 1,080건 모두 의미 해석 가능하며 strict와 semantic 점수가 같다.
- 사용·평가 검증: oracle는 GT 정보가 포함된 원인 분리용 조건으로 실용 baseline과 구분한다.
- 사용·평가 검증: 원시 답변과 요청을 연결해 category별 정답 수 및 paired CI를 재계산했다.
- 미해결: 문구를 맞춘 조건에서도 예측 bbox의 이득이 유지되는가?
- 미해결: 좌표 없이 검출 유무만 전달해도 같은 이득이 발생하는가?
- 미해결: 정확한 좌표, 교란 좌표, 안내 문구가 각각 답변에 미치는 효과는 무엇인가?

