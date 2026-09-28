# 요약

- **판정:** CONTINUE / improve. 실제 실험과 token 위험 신호는 유효하다. Presence 평가 오류 때문에 전체 비교의 성공 승인은 보류한다.
- **핵심 근거:** E 빈 출력 398명·미검출 70명에서 entropy AUROC 0.8225, 상위 80명 검토 시 43명 포착을 독립 재현했다.
- **의미·한계:** 동일한 빈 문자열도 위험 정보는 다르다. Presence의 보고된 역상관은 부호 오류이며 새 방법·독립 일반화·임상 안전성은 미증명이다.
- **다음:** 기존 raw logits로 방향·대표 선택·calibration·비교를 교정한다. 새 학습이나 GPU 본실험 확대는 예약하지 않는다.

# Assessment

계획·구조화 계획·보고서·changes.patch·reuse_manifest 및 관련 소스와 결과를 직접 검토했다. 리뷰 대상은 9d5739203730647fd401caccc3deccd6ecbab317이다. 소유 파일 전체가 해당 SHA와 일치하며 unpreserved_paths는 없다. 현재 git status와 diff는 비어 있지만 신규 구현은 커밋에 보존돼 있다.

valid_experiment=true는 동일 빈 출력에서 위험을 구분할 수 있는지에 대한 H1의 실제 검증에 적용한다. 실행 실패나 실험 미실행으로 판정할 근거는 없다. 다만 H2의 대표 비교 및 Presence 해석에는 평가 오류가 있어 수정이 필요하다. 전체 스냅샷의 재사용은 승인하지 않는다.

# Key Findings

1. **실제 실행과 표본:** C는 계획보다 많은 400명·2,000요청을 생성했으나 평가는 사전 대상인 빈 출력 199명·사건 36명으로 제한됐다. E는 빈 출력 398명에 대한 1,990요청을 생성했다. 각 실행의 고유 요청 수는 원시 행 수와 같고 자식 종료 코드는 모두 0이었다. C/E 빈 출력 597건은 모두 기존 [3805,106]과 일치하고 EOS로 종료했다.
2. **입력 연결:** C/E ID 교집합은 0이며 manifest의 GT box·category는 iter_010 GT와 일치한다. 세 seed의 source 상태는 valid_empty 또는 valid_nonempty다. 현재 영상 1,200개의 file/padded pixel hash 불일치는 0이고 신규 record의 source pixel·adapter 연결 불일치도 0이었다. 이는 foundation model 사전학습 미노출 증명은 아니다.
3. **token 결과 재현:** 저장 표와 원시 entropy·사건 연결을 대조했다. 별도 rank 기반 AUROC와 seed 28017 환자 bootstrap 10,000회에서 E entropy AUROC 0.8224739, 95% CI [0.7592101,0.8795061]을 재현했다. Capture@20%는 0.6142857, CI [0.5076923,0.7142857]이다. 실제 검토 비율은 80/398=20.10%이며 미검출 27/70명이 남는다.
4. **Presence 오류와 교정:** 질문은 opacity 존재 여부이므로 위험은 Yes−No다. 코드가 No−Yes를 사용해 음성처럼 보였다. 방향을 바로잡으면 E Presence M0/B0 AUROC는 0.7879791/0.8153746, Capture@20%는 0.4761905/0.5755102다. 모델의 역상관 현상이라는 해석은 철회해야 한다.
5. **대표 선택 변경:** C의 교정된 Presence B0 AUROC 0.7493183은 P(True) B0의 0.7060327보다 높다. 따라서 계획대로 선택할 대표 V는 presence_b0다. 리뷰의 별도 계산에서 E의 교정 V−entropy는 −0.0070993, 97.5% CI [−0.0304403,0.0151615]이며 V−seed는 CI [0.1251737,0.2729738]이다. 새 결과 파일과 calibration은 구현 단계에서 교정해야 한다.
6. **실행 검증:** d24_sanity.json은 24/24 suffix·EOS·argmax 재현과 6명 FP32/FP64 수치 대조를 기록한다. 리뷰에서 2/4 worker 120요청의 token·score 불일치 0, resume_test 72요청의 기준 실행 대비 불일치 0을 확인했다. 전체 공식 입력 tensor 및 모든 변조·단계 gate 검사를 완료한 근거는 없다.

# Problems / Concerns

**현재 비교 결론을 막는 문제:** Presence 부호 오류가 C 대표 선택과 양의 기울기 calibration까지 전파됐다. P(True) 자체의 저장 수치는 계산 가능하지만 이를 계획의 대표 V로 부르는 것은 잘못이다. 기존 entropy 관찰과 C→E 확대의 token 기준은 영향을 받지 않는다.

**재사용 전 문제:** risk28.existing_done은 protocol_digest·request_id·현재 manifest의 예상 입력을 충분히 확인하지 않는다. check_completion은 행렬 개수만 검사하며 평가기는 이를 호출하지 않는다. load_all은 중복을 덮어쓴다. E 진입 gate와 immutable completion도 없다. 동시 JSONL 읽기·tail 복구·launcher 수명 관리 및 허용 GPU 집합 검증을 보완해야 한다.

**보존 문제:** stream에서 protocol.json을 삭제하고 재잠근 작업을 확인했다. C 기록 digest는 0f2deac…이고 E는 c13356e…로 다르다. 현재 잠긴 파일 hash는 모두 일치하지만 이것만으로 C 실행 당시 파일 전체를 증명할 수 없다. 과거 protocol 복구 가능 범위와 변경 호환성을 새 기록에 남겨야 한다. 보고서와 평가 JSON을 재실행 시 덮어쓰는 경로도 개선한다.

**사용법 검사 범위:** verify_input_ids.py의 20/20 검사는 input_ids 비교이며 pixel_values 전체 대조가 아니다. argmax 일치는 확률 분포의 raw/processed 동일성을 증명하지 않는다. 현재 generation 설정에는 별도 penalty 등이 기록되지 않았지만, scorer는 output_scores를 raw logits이라고 일반화하지 않아야 한다. 정상 사용·전처리의 기존 검증과 이번 재현 근거는 활용하되 미완료 검사를 완료로 보고하지 않는다.

**자원 정책:** 두 GPU에 총 4 worker를 사용했고 동일 120요청의 wall-clock은 52.144초에서 40.746초로 감소했다. 출력 정합성은 확인됐다. 시간 단축은 21.9%, 처리량 증가는 28.0%다. GPU 전체 peak는 직접 측정하지 않아 안전 여유의 실측 근거가 부족하다. 이는 현재 유효한 token 결과의 기각 사유가 아니라 다음 실행 전 보완 사항이다.

# Interpretation

사전 기준상 token baseline은 개발 조건의 유용한 위험 신호다. 같은 [] 문자열이라는 사실은 내부 확률까지 같음을 뜻하지 않는다. 다만 상위 약 20% 검토 후에도 미검출 38.6%가 남으므로 임상적 안전 보장이나 검출 복구로 해석할 수 없다.

C는 actor 선택에 사용됐고 E도 이미 노출된 개발 자료다. 보고서의 '확인 평가'는 새 독립 확인으로 부르면 안 된다. calibration ECE만으로 충분한 임상 calibration을 주장할 수도 없다. 추가 forward pass 없이 score를 얻을 수 있지만 softmax·entropy 계산, logits 보관·전송 등의 비용까지 0인 것은 아니다.

이번 결과는 기존 RSNA SFT 성과를 검토 우선순위에 연결하는 근거다. 사분면 선택 전이의 미해결 원인이나 일반적인 공간 이해를 해결한 결과는 아니다. 사용자 보완의 기존 checkpoint·동일 target 우선 활용은 유지됐고 MRI·reserve 확대는 수행하지 않았다.

# Strategy Check / 연구 방향 판단

- **실행 유효성:** C/E 실제 scoring과 H1의 주요 관찰을 확인했다. 전체 provenance·gate의 재사용 신뢰성과 H2 평가 교정은 남아 있다.
- **성능 개선:** entropy가 개발 집단의 미검출을 순위화한다. actor bbox 성능을 개선한 방법은 아니며 추가 영상 재질의의 우위도 확인되지 않았다.
- **가설 지지:** 동일한 빈 출력 사이에 위험 정보가 있다는 H1은 지지된다. Presence 역상관은 구현 오류로 정정한다. 교정된 주비교 역시 영상 재질의의 추가 우위를 지지하지 않는다.
- **신규 기여 가능성:** token uncertainty와 재질의 비교는 강한 baseline 확보다. 새로운 confidence 방법의 필요성이나 기존 방법과 구별되는 원리는 아직 없다.

현재 방법 개선보다 기존 결과의 평가 교정이 가장 적은 비용으로 판단을 복구한다. 그 뒤 외부 확인은 일반화 판단을 바꿀 사용 조건이 있을 때만 가치가 있다. 잔여 27건을 근거 없이 새 loss의 필요성으로 해석하지 말고, 중요한 잔여 실패의 최소 진단과 다른 질문으로의 전환을 비교한다. 반복 횟수나 success 여부로 자동 연장하지 않는다.

논문 추천은 보류한다. 유효한 token 관찰은 있지만 현재 비교 결론에 수정이 필요하고 후속 투자 방향을 확정하지 않았으며, 이번 리뷰에서 새로운 추천 논문의 원문 검증도 수행하지 않았다.

# Recommended Next Experiment

새 GPU 실험 대신 기존 raw logit의 평가를 교정한다. 질문 의미에 따른 score 방향 fixture를 추가하고 C에서 대표 V·calibration을 다시 적합한 뒤 E의 paired CI·포착률·decision을 새 경로에 저장한다. 원본과 교정본의 차이를 명시하고, expected matrix·source·checkpoint·protocol 연결을 확인한다. 새 영상 생성은 실제 입력 불일치가 발견된 범위에만 필요하다.

교정 후 단순 baseline 충분이라는 판단이 유지되면 새 confidence head나 loss 학습은 보류한다. 다음 큰 투자 전에 외부 재현·중요한 잔여 실패 진단·다른 질문의 정보 이득을 비교한다. 기존 reserve와 MRI F139는 자동 사용하지 않는다.