# 요약

- **핵심 결과:** 원 계획의 V8 72건·E24 141건을 완료했다. 자동 등급에 영상을 추가한 이득은 불확정이며 사전 양성·method pilot 기준은 미충족이다.
- **근거:** E24의 A−M MAE 차이는 −0.0433, 95% CI [−0.1958, 0.0873]이다.
- **미검증·주의:** 반복 개발 자료의 결과다. 영상 무사용이나 MRI/VLM 전체의 한계로 일반화할 수 없다.
- **다음:** 현재 자동 등급 검증 후보의 추가 실행은 종료하고 독립 GPT 리뷰에 투자 판단을 넘긴다.

# Work Performed

iter_080의 가설·표본·checkpoint·판정 기준을 유지해 구현과 실제 GPU 실험을 완료했다.

- A: 대상 영상＋자동 등급, T: 무영상＋자동 등급, X: 환자 교환 영상＋동일 자동 등급을 구현했다.
- 정답을 생성 요청과 분리하고 donor·영상·기존 Q/C 출력의 연결을 검증했다.
- 시작 직전 GPU 메모리 검사, 원자적 출력 저장, 중복 방지와 강제 중단·재개를 구현·검증했다.
- V8에서 M=C argmax를 고정한 뒤 E24를 실행했다. 추가 학습은 없었다.

# Files Changed

- `rf78_vlm.py`, `rf78_gen.py`: A/T/X 입력과 무영상 처리.
- `a81_common.py`, `a81_prepare.py`, `a81_protocol.py`: 자료 연결·요청·출처 잠금.
- `a81_run.py`, `a81_launch.py`, `a81_monitor.py`: 생성·GPU 배정·자원 기록.
- `a81_tests.py`, `a81_checks.py`: 기술·재개·변조 검사.
- `a81_eval.py`, `a81_verify.py`, `a81_final.py`: 평가·독립 재계산·최종 봉인.

기존 결과와 `agent/`, `legacy/`, `hf_cache/`는 변경하지 않았다. Git 커밋·브랜치 변경은 하지 않았다.

# Commands / Experiments (실제 실행한 명령과 성공/실패)

주요 실행 명령은 다음과 같다.

- `python a81_prepare.py` — 자료·기존 출력 연결 통과.
- `python a81_tests.py cpu --dest results/iter_081/tests/cpu.json` — 12/12 통과.
- `python a81_eval.py select` — M=C argmax 선택.
- `python a81_launch.py --protocol results/iter_081/protocol_tech.json ...` — 2/4 worker 비교 및 강제 중단·재개 완료.
- `python a81_tests.py proc ...` — Q 재현·변조·중복·누락 검사 9/9 통과.
- `python a81_monitor.py ... -- python a81_launch.py ...` — V8/E24 각각 4 worker 정상 종료.
- `python a81_eval.py eval ...`, `python a81_verify.py ...` — 두 단계 평가와 독립 검사 각각 44/44 통과.
- `python a81_final.py`, `git diff --check` — 통과.

초기 보조 자원 조회는 기존 zombie 프로세스 조회 예외로 실패했다. 자식 프로세스만 관측하고 예외를 처리하는 wrapper로 교체해 본실험 자원 기록을 완료했다.

# Results (수치와 결과 파일 경로)

E24는 24명·47개 부위다. MAE는 낮을수록 좋다.

| 조건 | Class-standardized MAE | 일반 MAE | ≥2등급 오류 |
|---|---:|---:|---:|
| 대상 단독 Q | 0.77690 | 0.72340 | 5/47 |
| 분류기 M=C argmax | 0.77619 | 0.74468 | 7/47 |
| 대상 영상＋자동 등급 A | 0.73286 | 0.70213 | 5/47 |
| 무영상 T | 0.77619 | 0.74468 | 7/47 |
| 교환 영상 X | 1.56952 | 1.51064 | 21/47 |

환자 bootstrap 10,000회·seed7501 결과:

- **A−M 및 A−T:** −0.04333, 95% CI [−0.19584, 0.08730].
- **A−X:** −0.83667, 95% CI [−1.21818, −0.46350].
- Class 누락 replicate는 57/10,000회이며 present-class 평균을 적용했다.
- C 오차를 줄인 항목은 5개·5명, 완전 교정은 C 오답 23개 중 2개였다.
- C 정답 24개 중 4개를 훼손했다. Q가 더 정확한 항목에서 C 쪽으로 이동하며 악화된 환자는 2명이었다.
- T는 C와 47/47 일치했다. A는 C와 38/47 일치했고 A/X 답변은 32/47에서 달랐다.

신규 본출력 **213/213건이 EOS 종료·형식 유효**였다. 누락·중복은 없었다.

4 worker를 채택했다. 기술 요청 16건의 wall-clock은 33.88→25.96초로 줄었고 token은 모두 일치했다. 본실험 wall은 V8 33.47초, E24 49.26초였다. GPU 전체 peak는 18,312/18,229 MiB였으며 OOM은 없었다.

주요 산출물:

- [E24 평가](results/iter_081/eval/E24.json)
- [독립 재계산](results/iter_081/eval/E24_independent.json)
- [기술 검증](results/iter_081/tests/technical_gate.json)
- [최종 완료·출처 봉인](results/iter_081/completion.json)

# Goal Progress / Reused Assets (목표 진전·미검증 범위, 재사용 출처·검증)

iter_078 출처의 17개 반입 blob과 iter_077 R adapter, 고정 SPIDER 입력, 기존 Q/C 출력을 검증해 재사용했다. 기술 Q 4건의 기존 token 재현, 16건의 동시성·재개 출력 일치를 확인했다. 최종 봉인의 264개 파일 hash도 일치했다.

영상 교환에 따른 차이는 확인됐지만, 무영상 대비 정확도 이득과 단순 대안 이후의 실용 가치는 확보하지 못했다. 독립 환자·다른 seed·모델 일반화 및 신규 방법 효과는 검증하지 않았다.

# Problems (현재 결론 무효 / 재사용 전 수정 / 추후 개선을 구분)

- **현재 결론 무효:** 발견하지 않았다. 실행 중인 실험 자식 프로세스도 없다.
- **재사용 전 수정:** 이번 승인은 고정 iter_081 경로에 한정한다. 기존 `rf78_launch.py`의 과거 CLI 전체를 수정·검증한 것은 아니다.
- **추후 개선·해석 한계:** 반복 개발 자료, oracle anatomy, 단일 checkpoint 조건이다. 관측 출력은 최대 2 token이므로 긴 출력 처리량은 검증하지 않았다. Cached Q/C를 사용했으므로 온라인 전체 시스템 비용 우위는 주장하지 않는다.

# Recommendation to GPT

원 계획상 현재 후보는 **음성 종료 기준**에 해당한다. A−M 최소 개선폭 0.10과 A−T의 CI 기준을 충족하지 못했으며, method pilot 조건도 미충족이다.

다만 A−X 차이와 일부 오류 교정은 보존해야 한다. 이를 영상 무사용이나 연구 가치 전체의 부정으로 확대하지 말고, full review에서 기존 MRI 관찰들과 연결해 **집중 / 한정 보완 / 투자 보류·전환** 중 다음 투자를 선택해 달라. 이번 인계는 새 과학적 시도나 실패로 세지 않는다.

SELF_CHECK: PASS
SUMMARY: V8/E24 신규 213건과 필수 검증을 완료했으며, E24 A−M MAE −0.0433은 불확정으로 사전 양성·method pilot 기준에 미달했다.