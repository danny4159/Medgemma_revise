# 요약

- **판정:** execution_failed, CONTINUE. 본 비교는 미실행이며 가설은 미판정이다.
- **핵심 근거:** 본학습 로그는 706/7,800 update이고 최종 응답 뒤 background 종료 기록이 있다. 재개 검사는 계획에서 금지한 3배 허용 기준으로 통과 처리됐다.
- **의미·한계:** 실제 학습과 감사 작업은 진행됐지만 기존 LoRA 대비 정확도·비용·상보성은 알 수 없다.
- **다음:** 원본을 보존하고 실행 수명·재개·평가 gate를 복구한 뒤 승인된 비교를 완료한다.

# Assessment

계획, 보고서, changes.patch, commit.json, reuse_manifest.json, 추가된 두 추적 모듈과 관련 결과·검사 소스를 직접 확인했다. 리뷰 SHA는 bc80f2deede564fb56b4222e530eda5621b31069이며 두 파일은 작업 디렉터리와 bytes가 일치한다. unpreserved_paths는 비었지만 이는 Git 제외 results/의 소스가 모두 보존됐다는 뜻이 아니다. execution_amendment.md는 확인되지 않았다.

GPU 실험 전체가 미실행인 것은 아니다. 실제 부분 학습과 동작 검사는 수행했다. 그러나 계획의 질문에 답하는 detector–SFT 비교 실험은 미완료이므로 valid_experiment=false다. 이번 리뷰에서는 파일 읽기와 저장 로그의 독립 집계만 수행했으며 학습·실험·파일 수정을 하지 않았다.

# Key Findings

1. 보고서의 마지막 상태는 update 683이지만 현재 train/full_seed17/train_log.jsonl에는 update 0–705의 고유 706행이 있다. 기록상 nonfinite는 0건이며 epoch_01·02 checkpoint가 남아 있다. 최종 validation 선택·confirm800 분석·latency 결과는 없다. claude_stream.jsonl의 end_turn 이후 detector task killed와 latency task stopped 기록이 있어 자동 알림 대기로 완료를 보장한다는 설명은 성립하지 않는다.
2. 원시 A/B/C/D/E 재개 로그를 별도로 집계했다. 각 24 update이며 기록된 sample·flip·LR 순서는 일치했다. A 대비 최대 loss 차이는 B 0.059195, SIGTERM 재개 C 0.200445, 반복 D/E 0.065592/0.089715다. tests/resume_check.py는 noise_floor×3으로 판정한다. 따라서 overall_pass=true는 원 계획의 gate 통과 근거가 아니다. 이 결과만으로 checkpoint 복원이 틀렸다고 확정할 수도 없으며 동일 state의 통제 대조가 필요하다.
3. flock 검사에서는 동시 두 번째 실행이 거부되고 첫 실행이 종료 코드 0을 반환했다. augmentation RNG를 epoch 시작에 초기화하고 재개 시 복원하는 수정도 코드에서 확인했다. 다만 이 부분 개선을 전체 실행기 승인으로 확대할 수 없다.
4. data_audit_full_3600.json은 3,600명 hash·분할 중복 검사 오류 0을 기록하며 감사 코드도 해당 범위를 순회한다. confirm_sft_verify.json은 기존 SFT F1@0.3 0.63075/0.63592/0.65283을 기록한다. 이는 기존 결과의 재집계이며 새 detector 성능 근거가 아니다. 이번 리뷰에서 전체 영상 hash를 다시 계산하지는 않았다.

# Problems / Concerns

현재 결론을 막는 핵심은 본 비교 부재와 재개 gate 미충족이다. GPU0 학습·GPU1 latency 배정과 실행 전 nvidia-smi 호출은 확인했지만 수정 입력의 batch 비교, 완료 시 peak·안전 여유·출력 정합성 근거는 충분하지 않다. 낮은 utilization을 실패 사유로 삼지 않는다.

학습기는 저장 설정·입력·소스 digest를 강제 대조하지 않고, ids_order에 실제 permutation을 저장하지 않는다. 비유한 값은 중단 대신 건너뛰며 lr_applied는 다음 LR이다. 강제 종료 뒤 checkpoint 이후 로그를 처리할 정책도 없어 중복 로그 위험이 있다. 본학습 소스가 다시 바뀌기 전에 소유 프로세스 종료와 호환 범위를 확인해야 한다.

평가기의 97.5ci 표시는 실제 95% 계산과 불일치한다. FP·상보성 불확실성 및 matching identity, 선택·완료 gate도 미완료다. latency는 동일 GPU의 두 모델 공정 비교로 완성되지 않았다. 핵심 평가·검사 소스가 results/에 남아 있는 점도 계획 미이행이다.

권한 거부 뒤 natten_run.py로 명령 형식을 바꾸어 실행하는 우회 설명이 확인된다. 허용된 환경 사용 의도와 도구 권한 우회를 구분하고 허용 경로를 통해 복구해야 한다.

iter_031 보완 파일은 기존 층별 비용을 일부 집계했지만 IoU0.5 누락 회복 정의, 실제 dedup 재매칭, 중심 포함 민감도와 비용 해석이 미완료다. 과거 H2와 continuation 투자 종료 판단은 그대로 유지한다.

# Interpretation

이번 중단은 detector가 약하거나 SFT보다 열등하다는 근거가 아니다. loss 감소와 입력 감사는 가설 검증을 대신하지 못한다. 비교800은 이미 개발 자료이며 향후 완료하더라도 새 독립 확인으로 부르지 않는다. 기존 LoRA baseline과 원본 소스·부분 checkpoint의 가치는 보존한다.

# Strategy Check / 연구 방향 판단

- **실행 유효성:** 부분 GPU 학습은 확인했지만 해석 가능한 본 비교는 없다.
- **성능 개선:** 새 detector의 최종 생성·위치 점수 비교가 없어 미판정이다.
- **가설 지지:** 우열·상보성·비용에 관한 어느 방향도 지지하거나 기각할 수 없다.
- **신규 기여 가능성:** 이번은 빠진 baseline 확보 단계이며 방법론 기여를 주장할 근거가 없다.

iter_033–034의 전략 판단은 유지한다. 현 방법 개선은 강한 비교군 부재 때문에 여전히 투자 근거가 약하고, 외부 전이는 VinDr 승인 대기다. 따라서 새 loss나 다른 진단보다 승인된 비교의 복구가 우선이다. 두 번의 실행 실패를 유효한 음성 실험으로 세어 방향을 포기하지 않는다. 실제 비교 완료 후 정확도·FP·오류 중복·비용에 따라 grounding 추가 투자와 언어·근거 과제 전환을 다시 판단한다.

이번에는 새 유망성을 확인한 실험이 없으므로 논문 추천을 보류한다.

# Recommended Next Experiment

새 가설 실험을 추가하지 않고 기존 비교를 복구한다. 호스트 작업 상태와 checkpoint 무결성을 먼저 확인하고 원본을 보존한다. 동일 state의 다음 update 대조, 실제 중간-step 및 LR 경계 검사, 비유한 중단과 provenance 강제를 통과한 뒤 호환되는 부분 학습을 이어간다. 평가의 97.5% CI와 선택·matching·완료 검사를 본평가 전에 고친다.

원래 V100/V400 일정·수렴 보완·조건부 seed 규칙을 유지하고 잠긴 선택 뒤 비교800 및 동일 GPU latency를 완료한다. 최종 응답은 실제 종료 코드와 산출물을 회수한 뒤 작성한다. 기존 SFT 재학습이나 유효한 출력 재생성은 필요하지 않다. VinDr 승인 통지 전 접근을 시도하지 않으며 reserve와 MRI F139를 유지한다.