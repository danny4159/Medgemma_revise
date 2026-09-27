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

在本次固定 RSNA D36 开发样本中，MedGemma 1.5 的 grounding SFT checkpoint B0/C 对 Q_A 的 plain yes/no 格式遵循率为 29/36、26/36，低于 base 的 35/36；JSON 格式也未通过预设 gate。这是特定问题、checkpoint 和严格 parser 条件下的有限观察，不能据此认定视觉能力或 target 语义区分能力下降。

- 적용 목표 시작: iter_003
- 최신 리뷰: agent/runs/iter_015/review.json
- 근거: research/results/iter_015/gen/d36_{plain,json}__{M0,B0,C}/gen_worker*.jsonl：432 个实际 QA 输出。
- 근거: research/results/iter_015/d36/format_decision.json：两种格式均未通过所有 checkpoint×target 的 valid rate≥0.95 条件。
- 근거: 独立原始输出复核：B0/C 的 plain Q_A 分别有 7/10 个回答为 Normal；JSON 条件下大量回答为 bare yes/no。
- 사용·평가 검증: 实际问题和 parser 与计划固定规则一致；未将 [] 解释为 no。
- 사용·평가 검증: 432 个 QA 输出均以 EOS 结束，独立格式计数与保存结果一致。
- 사용·평가 검증: 当前 636 张图像的 file/pixel hash 与 manifest 一致，labels 与原始 gt_manifest 的 category、patient、boxes 一致。
- 사용·평가 검증: 官方使用方式采用 iter_009 已验证范围；本次未重新运行官方 GPU 示例。
- 미해결: 在开发资料上固定仅适用于 Q_A 的精确 Normal/Abnormal 映射后，target 别性能差异是否仍然存在？
- 미해결: 独立患者和其他训练 seed 是否复现该现象？
- 미해결: 格式变化是否足以解释表面性能下降，尚未验证。

