# 요약

- **판정:** CONTINUE / execution_failed. 실험은 부분 실행됐지만 가설 검증을 완료하지 못했다. 방법의 효과를 기각한 결과가 아니다.
- **핵심 근거:** seed 17 두 LR의 학습 로그는 첫 epoch의 121·107 steps까지이며, base validation은 800개 예정 요청 중 133개다. 독립 확인 결과는 없다.
- **의미·한계:** 실제 LoRA 학습·생성 경로와 처리량 개선은 확인했다. 일반화 개선이나 새로운 contribution은 아직 판단할 수 없다.
- **다음:** 기존 실행 상태를 확인하고 재개·평가 검증을 보완한 뒤 원 계획을 완료한다. 기존 결과와 체크포인트는 보존한다.

# Assessment

계획, plan.json, Claude 보고서, changes.patch, commit.json, reuse_manifest.json, 관련 소스·fixture·원시 출력·자원 로그와 Claude 실행 종료 구간을 읽었다. execution_amendment.md는 발견되지 않았다. 코드 수정·파일 생성·테스트·GPU 실험은 수행하지 않았다. 기존 JSON과 파일 hash만 읽어 집계했다.

리뷰 대상은 `5581ed255a350e42a0ad422065edf13c56a33bf6`이다. commit.json의 저장 대상 파일은 현재 작업 파일과 모두 일치한다. `git diff`는 비어 있고 `test_rsna_iter010_gpu.py`만 미추적 상태다. 이 파일은 자동 저장에서 제외됐으므로 전체 스냅샷 재사용은 승인하지 않는다.

`claude_report.md`는 백그라운드 학습·생성을 기다린다는 안내이며 완료 보고서가 아니다. `claude_stream.jsonl` 마지막 구간에도 epoch 1 validation 대기와 `end_turn`이 기록돼 있다. 실행 호스트의 작업이 현재도 살아 있는지는 이 리뷰 환경에서 확정하지 못했다. 완료 전 단계 인계 문제로 판단하며 `valid_experiment=false`로 둔다.

# Key Findings

**데이터와 입력 검사:** `data_audit/split_checks.json`은 train/validation/confirm 2,400/400/800명, 고유 환자·SOP 각각 3,600개, 분할 간 환자 중복 0을 기록한다. 과거 환자와의 중복 및 iter_009 영상 pixel 중복도 0으로 기록돼 있다. 양성 reserve는 496명이다. source_hash_check.json에는 annotation·mapping·공식 ZIP hash 일치가 기록돼 있다. 이번 리뷰에서 대용량 ZIP 전체를 재해싱한 것은 아니다.

**학습 경로:** 저장 fixture는 기존 검사 59/59, iter_010 CPU 검사 70/70, GPU 검사 24/24 PASS다. GPU 기록에는 assistant-only masking, 생성 prefix 일치, 238개 LoRA 대상 모듈, 초기 adapter logits 차이 0, 유한 gradient, frozen base, adapter 재로드와 실제 생성 변화가 포함된다. 작은 두 표본의 loss는 0.927에서 0.163으로 감소했다. 이는 학습 경로의 동작 근거이며 일반화 성능이 아니다.

**실제 진행량:** `train/lr1e-4_s17/train_log.jsonl`과 `train/lr2e-4_s17/train_log.jsonl`은 각각 121·107 steps다. 계획상 한 epoch는 150 steps다. 저장된 마지막 loss는 각각 0.653·0.618이며 validation 결과는 없다. `base_val/gen_worker*.jsonl`의 133개 요청은 고유하고 중복은 없지만, 예정된 400명×2 prompts에는 미달한다. 부분 생성만으로 baseline 순위나 성능 결론을 내리지 않았다.

**처리량:** 고정 24명×2 prompts의 두 pilot은 각각 48/48개 요청을 완료했고 누락·중복·추가 요청이 없다. 2 worker는 2,078.79초, 4 worker는 1,054.74초로 약 1.39→2.73 요청/분, 1.97배 개선됐다. 리뷰에서 두 구성의 원시 suffix와 EOS를 대조해 48개 모두 일치를 확인했다. sampled GPU 최대 점유는 4 worker 구성에서 17,888·17,797MiB였다.

**버전 연결:** main protocol에 기록된 29개 파일 hash는 모두 현재 파일과 일치한다. 반면 pilot protocol은 현재 generate.py·lock_protocol.py와 다르므로 pilot 검사를 현 SHA 전체의 검증으로 확대할 수 없다.

# Problems / Concerns

현재 성능 결론을 막는 것은 본실험 미완료다. 권한 거부 기록이 일부 있지만 이후 실제 학습·생성이 수행됐으므로 전면적인 실험 미실행이나 영구 권한 차단으로 해석하지 않는다.

재사용 전에는 다음을 해결해야 한다.

1. **epoch validation 복구:** train.py는 epoch adapter를 저장한 뒤 `save_ckpt(epoch + 1, 0)`를 실행하고 validation을 수행한다. 이 사이 또는 validation 도중 종료되면 재개 루프는 다음 epoch부터 시작한다. 마지막 epoch에서는 validation 없이 종료할 수도 있다. select.py도 존재하는 metric만으로 best epoch를 고르므로 누락을 차단해야 한다.
2. **학습 재개와 입력 검증:** train.py에는 run-dir 소유 lock이 없다. train/validation ID 파일은 protocol에 포함되지 않으며 train_digest는 선택 ID 자체를 검증하지 않는다. SFTDataset은 현재 image hash를 확인하지 않는다. 현재 자료가 변조됐다는 증거는 없지만 재개 안전성의 결함이다.
3. **최종 평가의 엄격한 중단 조건:** final_eval.py는 completion·protocol을 검증하지 않고 결과를 읽는다. 누락은 sft_eval에서 점수 0으로 처리되고, 정확한 3개 seed 집합도 강제하지 않는다. 누락과 모델의 실제 실패를 섞지 않도록 평가 전에 요청·seed·adapter 연결을 검증해야 한다.
4. **GPU 안전 여유:** 본학습과 base 추론을 함께 실행한 로그에서 GPU 전체 점유는 21,090·20,999MiB까지 올라갔다. 24,576MiB 중 여유는 3,486·3,577MiB로, GPU당 두 프로세스에 필요한 총 4GiB에 못 미친다. 관측된 OOM을 주장하는 것은 아니며 배치를 보완할 문제다. 이후 validation의 peak도 포함해야 한다.
5. **검증 소스 보존:** GPU fixture 소스가 비밀정보 패턴 검사로 커밋에서 제외됐는데 main protocol은 해당 파일에 의존한다. 실제 민감정보 여부를 확인하고 안전한 보존·검증 연결을 해결해야 한다.

기존 작은 모델 optimizer/RNG fixture는 tensor 일치를 확인하지만 실제 학습 실행기의 epoch 경계·DataLoader·validation 중단 복구를 검증하지 않는다. 필요한 보완 검사는 이 경로에 집중한다.

# Interpretation

사용자 보완 지시에 따라 iter_009의 validated 한계를 출발점으로 삼고 직접 병변 SFT를 먼저 구현한 방향은 타당하다. anatomy 전이를 자동 재개하거나 head 성능을 실제 VLM 개선으로 바꾸어 주장하지 않았다. 기존 한계 주장을 바꿀 새로운 성능 근거는 없으므로 limitation_updates는 비운다.

두 GPU를 사용한 학습과 처리량 비교가 실제로 수행됐다. CPU 준비나 작은 pilot만 반복한 사례는 아니다. 그러나 작업 착수와 학습 loss 감소를 직접 적응 성공으로 볼 수 없다. 현재 실패 범위는 실행 완료·인계 및 재사용 안전성에 한정한다.

iter_010에는 이후 도입된 단계별 표본 축소 기준을 소급 적용하지 않는다. 원래 계획의 학습량·평가 일정·seed·확인 표본을 유지한다. 기존 결과·검증된 모듈·체크포인트는 계속 보존한다.

# Recommended Next Experiment

새 방법을 추가하기 전에 기존 직접 SFT 비교를 완료한다. 먼저 실행 호스트에서 살아 있는 소유 작업과 종료된 작업을 구분하고, 살아 있는 claim이나 작업을 중복 실행하지 않는다. 종료된 작업은 checkpoint와 원시 결과에서 안전하게 이어간다.

재개·평가 결함을 수정할 때는 기존 protocol을 덮어쓰지 말고 변경 이유, 영향을 받는 코드, 기존 학습·출력의 호환 범위를 기록한다. 필요한 회귀 검사는 epoch 경계 및 validation 도중 중단 복구, 선택 ID·영상 변경 거부, 누락 요청·seed·adapter 불일치 거부에 집중한다.

그 뒤 안전한 GPU 배치에서 두 LR의 seed 17 학습, 사전 고정 확장 규칙, seed 29·43, 주 비교군 선택과 독립 확인 800명 평가를 완료한다. 효과 크기·paired CI·음성 층·출력 유효성·seed별 결과를 보고한 후에만 잔여 오류에 맞는 새 방법을 설계한다.