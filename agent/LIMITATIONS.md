# 한계 주장과 검증 근거

초기 판단: LIMITATIONS.json. 이후 변경 근거: 각 반복의 review.json/limitation_updates.
validated는 명시한 조건에서 사용·평가 오류를 통제해 성능 문제를 재현했다는 뜻이며, 내부 원인 확정이 아니다.

## lesion-grounding-generalization — validated

MedGemma 1.5 revision 91850547d9f0b2fdd21aa7c5f4f3d1a8a52c243b의 값 보존 전처리·공식 chat template·충분한 생성 길이 조건에서, RSNA adjudicated 폐렴 의심 opacity 양성 200명 중 134명(67.0%, Wilson 95% CI 60.2–73.1%)은 사전 고정한 공식 긴 prompt와 간결 prompt 모두에서 유효하고 비어 있지 않은 예측의 모든 예측–GT IoU가 0.3 미만이었다. 이 특정 자료·prompt 조건의 위치 불일치를 검증한 것이며, 모든 병변의 일반화 실패나 내부 원인을 확정하지 않는다.

- 적용 목표 시작: iter_003
- 최신 리뷰: agent/runs/iter_009/review.json
- 근거: research/results/iter_009/eval/run/gen_shard*.jsonl: 900개 고유 요청, 중복 0; 리뷰에서 원시 응답을 별도로 파싱해 주지표 134/200 재확인.
- 근거: research/results/iter_009/eval/eval/metrics.json: 공식·간결 prompt 양성 유효 출력률 100%·96.5%; F1@0.3 0.147·0.066, development 단일 box prior 0.269.
- 근거: research/results/iter_009/data_audit/split_checks.json: development 80명과 평가 300명, 기록된 이전 환자와의 교집합 0.
- 근거: research/results/iter_009/eval/eval/cases/common_error_ind_00000103.png: GT와 전체 예측 overlay를 직접 확인.
- 사용·평가 검증: 보존된 공식 MedGemma 1.5 notebook의 prompt·전처리 코드를 읽고 runner와 대조했다. skimage 원문 실행 대신 numpy emulation을 사용했다는 범위를 유지한다.
- 사용·평가 검증: sanity/sanity.json에서 공식 예제·development 총 4건의 pipeline/runner input_ids 및 bf16 pixel_values 일치와 생성 결과 대조를 확인했다.
- 사용·평가 검증: tests/fixtures.json의 58개 통과 기록과 parser·전처리·matching·union IoU 구현을 확인했다. 리뷰에서 테스트나 GPU 실험을 재실행하지 않았다.
- 사용·평가 검증: locked_protocol.json의 모든 파일 hash, 체크포인트 SHA의 변경 파일, 380개 현재 영상 file/pixel hash 및 1,140개 생성 요청의 pixel/config digest를 대조해 불일치 0을 확인했다.
- 사용·평가 검증: 1000→2000→4000 cap 규칙과 EOS 판별을 확인했다. 간결 prompt의 양성 잘림 7건은 주지표의 위치 오류 분자에서 제외된다.
- 미해결: legacy 익명 NIH 10장의 환자 중복과 모델 사전학습 노출은 미확인이다. 완전한 미노출 평가라고 표현하지 않는다.
- 미해결: 간결 prompt는 x/y 교환 시 일부 개선되어 축 순서 혼동의 부분 기여를 배제할 수 없다.
- 미해결: GT 경계 모호성, 위치·크기 오류 및 미검출을 해결하는 방법과 다른 데이터셋의 재현성은 미검증이다.
- 미해결: pooling·decoder 병목이나 anatomy 전이의 필요성은 이 결과로 확정할 수 없다.

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

