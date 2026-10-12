# 요약

- **핵심 결과:** volume min–max 정규화에서도 40명 전원 PRESENT였다. 사전 기준상 **음성 결과**다.
- **근거:** P/M 모두 BA 0.50, 차이 0.00, paired 95% CI [0.00, 0.00]. 보고서상 음성 20명의 회복은 없었다.
- **주의:** 반복 개발 집단·보고서 기반 평가다. MRI 전체 능력이나 경량 적응의 가능성을 기각하지 않는다.
- **다음:** 이번 정규화 설명 경로를 종료하고 GPT full review로 넘긴다.

# Work Performed

동일 환자·T2 series·8장·방향·prompt·모델 revision·생성을 유지하고 정규화만 비교했다. P는 기존 brain percentile1–99, M은 전체 volume min–max를 사용했다.

48명·768개 PNG의 연결과 정규화를 검산했다. 평가 코드와 입력은 **2026-10-12 22:14:10 UTC**, 생성 전에 잠갔다. 잠금 digest와 설정은 [evaluation_lock_v2.json](/SSD1_1TB/home/milab/daniel/08_medgemma/research/results/iter_129/evaluation_lock_v2.json)에 보존했다.

기술 P 8명의 기존 token을 8/8 재현하여 탐색 P40 출력을 재사용했다. 신규 생성은 기술16·재개검사16·탐색 M40으로 **총72건**이다.

# Files Changed

- `mr123_data.py`: 기존 percentile 동작을 보존하고 명시적 min–max 선택 추가.
- `mr128_gen.py`: 결과 경로 설정, 정규화 연결, tensor·요청·재개 검증 보강.
- 신규: `mr129_control.py`, `mr129_eval.py`, `mr129_tests.py`, `mr129_memory_pilot.py`, `mr129_finalize.py`.
- 기존 결과·환경·HF cache는 변경하지 않았다. Git 관리는 orchestrator에 맡겼다.

# Commands / Experiments (실제 실행한 명령과 성공/실패)

| 명령 | 결과 |
|---|---|
| `python -B mr129_control.py prepare` | 통과: 입력 검산·CPU 검사25건·사전 잠금 |
| `python -B mr129_control.py tech` | 통과: 16/16 완료, P 재현8/8 |
| `python -B mr129_tests.py runtime` | 초기 admission 거부: 10,000MiB 추정에서 여유 부족, child 미실행 |
| `python -B mr129_memory_pilot.py runtime` | 실측 기반9,900MiB 설정으로 통과: 재개 검사11건, token/tensor16/16 일치 |
| `python -B mr129_memory_pilot.py main` | 통과: M40/40 완료 |
| `python -B mr129_control.py eval` | NumPy bool의 JSON 저장 오류 |
| `python -B mr129_finalize.py` | 저장 자료형만 변환하여 평가·독립 검산·봉인 완료 |
| 최종 무결성 검사 및 `nvidia-smi` | 통과: 결과·출처·메모리 여유 확인, 잔여 GPU 작업 없음 |

# Results (수치와 결과 파일 경로)

| 조건 | BA | Sensitivity | Specificity | PRESENT | EOS |
|---|---:|---:|---:|---:|---:|
| P: percentile | 0.50 | 1.00 | 0.00 | 40/40 | 40/40 |
| M: volume min–max | 0.50 | 1.00 | 0.00 | 40/40 | 40/40 |

정오 전환은 양방향 모두 0명이었다. M의 40건은 모두 loose parser 응답이며, INVALID·UNCERTAIN은 없었다. 최대 출력은34 token으로512-token 상한에 도달하지 않았다.

- 본실험 wall: **108.14초**. GPU0/1 peak: **9,775/9,703MiB**.
- 4-worker 재개검사 peak: **19,460/19,389MiB**. 최소 여유 **4,665/4,739MiB**로 worker당2GiB 기준 충족.
- 원 NIfTI 읽기부터 답 저장까지 평균: P **4.350초**, M **4.596초**. 서로 다른 실행 시점의 참고 비용이며 paired timing은 아니다.
- 기존 결과700개와 모델 자산의 hash 불변을 확인했다.

주결과는 [report.json](/SSD1_1TB/home/milab/daniel/08_medgemma/research/results/iter_129/eval/report.json), 환자별 결과는 `results/iter_129/eval/per_patient.json`, 종료 검증은 [final_integrity.json](/SSD1_1TB/home/milab/daniel/08_medgemma/research/results/iter_129/final_integrity.json)에 있다.

# Goal Progress / Reused Assets (목표 진전·미검증 범위, 재사용 출처·검증)

커밋 `252dd607ec046ec7123f78ae1a832e06c8561293`의 지정10개 파일을 원 blob과 대조했다. 렌더링·parser·metric·생성 경로를 사용했고, 선정·SynthSeg·설치 entrypoint는 실행하지 않았다.

현재 T2 8장·고정 질문에서 **정규화 변경만으로 판별이 회복된다는 설명은 지지되지 않았다**. 새 방법의 필요성이나 contribution은 입증하지 않았다. 독립 환자·임상 영상 정답·다른 질문·학습 개입은 미검증이다.

# Problems (현재 결론 무효 / 재사용 전 수정 / 추후 개선을 구분)

- **현재 결론 무효:** 없음. 입력·출력·paired 집계·독립 검산을 완료했다.
- **재사용 전 수정:** 평가 종료는 `mr129_finalize.py`를 사용해야 한다. 원 `eval` 직접 호출에는 NumPy scalar 저장 문제가 남으며, 잠긴 계산 코드는 보존했다.
- **추후 개선:** 4-worker 비교에는 중단·재적재 비용이 포함됐다. 정상 상주 상태의 처리량 우열은 미확정이다. 이번 정확도 결론에는 영향을 주지 않는다.

# Recommendation to GPT

사전 음성 분기를 적용해 현재 frozen T2 이진 과제의 정규화 설명 경로를 종료하는 것을 권고한다. 같은40명에서 추가 window·prompt·slice 탐색을 이어가지 않는다. MRI 전체나 경량 적응을 기각하지 않고, 후속 투자는 전문 대안 이후의 구체적인 잔여 가치에 근거해 판단한다.

SELF_CHECK: PASS
SUMMARY: MR-RATE 개발40명에서 min–max 정규화도 전원 PRESENT·BA0.50으로 회복이 없었으며, 입력·재개·독립 검산과 기존 결과 보존을 완료했다.