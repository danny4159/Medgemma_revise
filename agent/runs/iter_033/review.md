# 요약

- **판정:** `execution_failed`, `valid_experiment=false`, `CONTINUE`. detector 탐색은 실행됐지만 계획한 SFT 비교는 미완료다.
- **핵심 근거:** train600의 450 update와 V100 양성 50명 F1@0.3 0→0.4113을 재확인했다. 본학습 로그는 리뷰 시 594/7,800 update였고 최종 비교 결과가 없다.
- **의미·한계:** detector 학습 신호는 있으나 기존 LoRA 대비 정확도·상보성·비용과 신규 기여는 미판정이다. 기존 한계 주장과 SFT 성과는 유지한다.
- **다음:** 실행 수명·실제 재개·provenance·평가를 보완하고 승인된 비교를 완료한다. VinDr 승인을 다시 묻거나 다른 연구로 전환할 근거는 아직 없다.

# Assessment

계획·plan.json·보고서·changes.patch·commit.json·reuse_manifest와 관련 소스·원시 결과·실패 로그를 직접 확인했다. 보고서는 완결된 연구 보고가 아니라 예약된 wakeup을 기다리겠다는 최종 응답이다. SELF_CHECK와 최종 비교 요약은 없다.

리뷰 SHA는 `a60224c1f7d54e4f59e8c4dc16285d62faf004b5`다. commit의 13개 파일은 현재 bytes와 일치하고 working tree diff는 비어 있다. 그러나 핵심 detector 구현과 검사 코드는 `results/iter_033/`에 있어 이 SHA에 포함되지 않는다. `git check-ignore`로 실행 코드의 제외 상태를 확인했다. 커밋 전체를 재사용 기반으로 승인하지 않는다.

이번 판정은 본비교 실행 미완료에 대한 것이다. GPU 실험 전체가 미실행된 것은 아니며, 개발 비교800·최종 비용 비교와 iter_031 보완 분석이 미실행 또는 미완료다. 실험·코드를 수정하거나 GPU 실험을 대신 실행하지 않았다.

# Key Findings

1. **탐색 수치는 재현된다.** `explore/v100_epoch{00,03,06}/raw_preds.json`의 환자 집합은 각각 고정 V100과 정확히 일치한다. 별도 IoU와 augmenting-path cardinality matching으로 양성 50명의 F1@0.3을 0/0.336667/0.411333, F1@0.5를 0/0.236667/0.253333으로 재현했다. utility는 0.500000/0.538333/0.545667이다. `explore/decision.json`의 수치상 확대 조건을 충족하지만 필수 구현 gate까지 통과했다는 뜻은 아니다.

2. **본학습은 완료되지 않았다.** 탐색 로그는 450 update, full_seed17은 리뷰 시 594 update이며 모두 기록상 finite다. 본학습 계획은 기본 26 epoch·7,800 update다. V400 선택·confirm800·latency·analysis_iter031의 최종 산출물이 없다.

3. **중단 경로가 확인된다.** `claude_stream.jsonl`의 본학습 호출은 약 2시간을 예상하면서 `subprocess.run(..., timeout=590)`을 사용했다. latency에는 115초 timeout 실패와 후속 580초 제한이 있다. ScheduleWakeup 뒤 최종 응답을 반환했고 로그 말미에서 학습과 latency background task가 모두 `stopped`다. 마지막 중단이 timeout 때문이라고 단정하지는 않지만, 짧은 timeout 자체도 본학습 완료를 막는 설정이다.

4. **처리량 비교는 일부 수행됐다.** 로그의 microbatch2/4는 각각 8.89/9.55 images/s, peak reserved 4,124/7,796 MiB다. batch4가 약 7.5% 빨랐지만 full 실행은 microbatch2였다. 동일 출력·평가 정합성과 전체 GPU 점유·안전 여유를 포함한 선택 근거를 보완해야 한다. 두 GPU에 detector와 MedGemma를 배정한 시도는 확인되므로 낮은 utilization 자체를 실패 사유로 삼지 않는다.

# Problems / Concerns

**현재 비교 결론을 막는 문제:** 충분한 detector 학습, validation 선택, 완전한 paired 비교가 없다. 필수 gate가 강제되지 않아 탐색 decision만으로 본학습에 진입했다. 따라서 detector나 SFT의 우위를 판정할 수 없다.

**재개와 실행 수명:** `resume_test.json`의 최대 loss 차이는 1.36082이고 반복 변동은 0.55219다. 코드는 반복 변동의 3배까지 허용하며 같은 프로세스에서 모델을 재구성한다. 실제 `cmd_train`의 effective batch·중간 epoch·scheduler·sample 순서를 검증하지 않는다. `cmd_train`은 매 update마다 augmentation RNG를 epoch seed로 초기화해 같은 위치의 flip 패턴을 반복한다. 단순 CUDA 잡음으로 설명하고 넘길 수 없다. 실제 재개 비교와 기존 checkpoint 호환성 판단이 필요하다.

`train.lock`은 원자 생성·starttime·소유 token 검증이 없고, checkpoint의 입력·protocol 검증도 없다. finite 검사는 update 후 기록만 하며 비정상 값을 즉시 중단하지 않는다. inference 재개 검사는 실제 부모 종료나 변조 거부 대신 파일 재작성·재추론 근사 비교를 수행한다. pilot_mb2의 update 0–74 반복은 attempt 분리도 필요함을 보여준다.

**자료·평가:** data_audit은 전체 환자 ID 교집합과 영상 60개 표본 hash만 확인했다. 전체 현재 입력·SOP/pixel 중복·source GT·저장 SFT provenance 검사는 완료되지 않았다. 이것이 누수 발견을 뜻하지는 않는다. 표본 생성은 category·GT 개수에 따르며 계획의 면적 층화는 구현되지 않았다. 현재 표본을 결과에 맞춰 교체하지 말고 대표성·계획 차이를 기록해야 한다.

`analyze_confirm800.py`는 계획한 97.5% 대신 기존 95% CI 함수를 호출한다. 중복 record를 덮어쓰고 수만 보고하며 source/completion 검증이 없다. FP 차이 CI와 일부 층별·budget·seed 평가도 미완료다. `select_threshold.py`는 FP 입력이 없으면 0으로 대체하므로 계획의 동점 규칙을 강제하지 못한다.

**코드 보존:** `commit.json`의 제외 목록이 비어 있다는 사실은 `results/` 내부 소스 보존을 보증하지 않는다. 원본을 유지하면서 추적되는 경로에 소스·검사를 편입하고 실행 버전과 checkpoint·출력을 연결해야 한다. geometry만 검사 근거가 있는 좁은 범위에서 승인한다.

**사용자 보완 준수:** RSNA detector를 선택하고 기존 SFT 출력을 재사용하려는 방향은 지시와 맞는다. 그러나 충분한 비교와 iter_031 잔여 분석은 끝내지 못했다. 이번 자료에서 VinDr 승인 전 외부 본평가나 reserve 개방을 확인하지 못했다. continuation 종료 판단을 되돌릴 근거도 없다.

# Interpretation

탐색에서 위치 출력이 개선됐으므로 detector 적응의 실행 가능성을 추가 검증할 이유는 있다. 하지만 V100은 개발 자료이고 annotation budget도 본학습과 다르다. 이 점수를 기존 SFT의 다른 평가 집단 점수와 직접 비교해서는 안 된다.

이번 미완료는 detector 계열의 실패, 의료 VLM의 우위 또는 기존 grounding SFT의 가치 상실을 의미하지 않는다. 한계 주장을 갱신할 새로운 완결된 근거가 없어 `limitation_updates`는 비운다. 논문 추천은 보류한다. 현재 확인된 탐색 학습 신호만으로 특정 연구 방향의 비교 우위나 재현되는 진단 결과가 확보되지는 않았다.

# Strategy Check / 연구 방향 판단

- **실행 유효성:** 탐색 출력은 확인했지만 원 계획의 비교 가설 검증은 미완료다.
- **성능 개선:** detector 내부의 epoch0 대비 개발 성능 상승만 확인했다. SFT 대비 개선은 미검증이다.
- **가설 지지:** 정확도·FP·비용 우열과 오류 상보성은 아직 판단할 수 없다.
- **신규 기여 가능성:** 알려진 detector baseline 확보 단계다. 새로운 방법이나 일반적 원리의 증거는 없다.

iter_033 계획의 전략 비교는 여전히 유효하다. 새 grounding loss 개선은 강한 대안 대비 필요성이 불명확하고, 다른 질문으로 전환하면 승인된 비교가 계속 빈칸으로 남는다. 현재는 실행·평가를 복구해 이 비교를 완료하는 정보 이득이 가장 크다. 새로운 대규모 탐색은 추가하지 않는다. 완료 후 detector의 우위·낮은 상보성, SFT의 조건별 이점, 불확정 결과를 원 계획의 분기대로 해석한다.

# Recommended Next Experiment

먼저 실행 호스트에서 기존 작업의 PID/starttime·lock·checkpoint·종료 코드를 확인한다. sandbox의 프로세스 목록만으로 호스트 작업 종료를 확정하지 않는다. 활성 작업을 중복 실행하거나 소스를 실행 중에 바꾸지 않는다.

짧은 subprocess timeout과 예약 wakeup에 의존한 조기 종료를 해결한다. 핵심 소스를 보존하고 실제 본학습 경로의 중간-step 재개·RNG·LR·입력 잠금·원자적 소유권·완료 검증을 통과시킨다. augmentation 수정이 필요하면 기존 checkpoint와의 호환 범위를 사전에 기록한다. 기존 SFT와 검증된 탐색 출력은 재생성하지 않는다.

그 뒤 원래 본학습·V100/V400·수렴 보완·조건부 seed 규칙을 수행하고 선택을 잠근 뒤 개발 비교800을 연다. 두 F1의 97.5% paired CI, FP 비용·상보성·작은/복수 병변·FP budget과 공정한 latency를 완료한다. iter_031 분석은 저장 출력으로 새 경로에 남긴다. VinDr 승인 통지 전 다운로드하지 않고 MRI F139·reserve·새 loss는 유지한다.