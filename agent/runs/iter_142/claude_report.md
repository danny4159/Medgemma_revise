# 요약

- **핵심 결과:** 개발 6명의 AutoRG DWI 판독을 완료했습니다. 공개 항목 일치율은 46.55%로, 저장된 MedGemma 개별 처리 45.65% 대비 **+0.89pp이며 우위는 불확정**입니다.
- **근거:** 보고서 6개와 내부 생성 31개가 모두 완결됐습니다. 원문 인용 71개와 주요 수치·bootstrap의 독립 재계산이 일치했습니다.
- **주의:** 학습 노출 가능성이 있는 개발 비교입니다. 독립 일반화·3D 구조 효과·입력별 SFT는 미검증입니다.
- **운영 문제:** SDK가 기존 모델 폴더에 새 경고 로그를 썼습니다. 보존 이동과 안전 경로 검증을 완료했지만, 원 실행의 조건 위반을 남겨 `SELF_CHECK: FAIL`로 보고합니다.

# Work Performed

공식 소스 217개 파일과 실제 checkpoint hash를 확인하고, 평가 규약·코드를 본 생성 전에 잠갔습니다. DWI 입력에는 `image`, `modal`만 전달했으며, 본 worker에서 GT mask와 정답 파일 접근을 차단했습니다.

초기 기술 비교의 tensor 불일치는 checkpoint가 복원한 비결정적 cuDNN 설정과 연결됐습니다. 원 결과를 보존하고 seed 42·결정적 kernel 설정으로 재검증했습니다. 이후 SDK 직접 호출과 wrapper의 tensor·feature·token·보고서가 정확히 일치했습니다. 함수 변경 없는 SDK 실행과 관측 hook의 출력 대조도 통과했습니다.

GPU당 2개 worker로 고정 개발 6명을 실행했습니다. 기존 iter_141 생성·판정은 변경하지 않았고, 신규 학습은 실행하지 않았습니다.

# Files Changed

새 연구 소스는 `i142_*.py`, `test_i142.py`입니다. `ar70_run.py`, `ar70_patch.py`는 원 blob 그대로 반입했습니다.

주요 파일:

- [실행기](./i142_worker.py), [병렬 실행기](./i142_launch.py), [안전 worker 진입점](./i142_worker_safe.py)
- [평가기](./i142_eval.py), [새 출력 판정표](./i142_judge.py), [독립 검산기](./i142_verify.py)
- [whole-sequence SFT 계약](./results/iter_142/whole_sequence_supervision.md)
- [구현 결과와 문제 기록](./results/iter_142/implementation_outcome.json)

Git commit·브랜치 변경은 하지 않았습니다. 소스 20개와 산출물 467개를 [completion.json](./results/iter_142/completion.json)에 연결했습니다.

# Commands / Experiments (실제 실행한 명령과 성공/실패)

- `python i142_prepare.py` — 출처·입력·가중치 검증과 사전 잠금 통과.
- `python i142_pilot.py` — 최초 tensor 동등성 실패. 결정적 설정으로 재실행해 통과.
- `python test_i142.py`, `python i142_checks.py` — 수정 후 CPU fixture 12개와 실제 완료·변조·경합 검사 8개 통과.
- 기술 실행의 `--direct --equivalence` 및 `python i142_hooklaunch.py` — SDK·wrapper·hook 대조 통과.
- `python i142_launch.py --stage main --name main --protocol results/iter_142/protocol_main.json --max-length 300 --per-gpu 2 --peak-mib 7000` — 개발 6명 모두 정상 종료.
- `python i142_judge.py`, `python i142_eval.py`, `python i142_details.py`, `python i142_verify.py` — 판정 연결·집계·검산 통과.
- 안전 로더 — 첫 보존 snapshot 검사는 로그 이동과 겹쳐 실패. 이동 완료 후 직렬 재검사와 실제 기술 판독 통과.
- `python i142_finish.py` — 산출물 봉인 통과.

기존 격리 환경 `results/environments/autorg70/bin/python`을 사용했습니다. 환경 목록은 [environment.json](./results/iter_142/environment.json)에 보존했습니다.

# Results (수치와 결과 파일 경로)

환자 평균 **공개 DWI 항목 일치율**입니다. 임상 진단 정확도로 해석하지 않습니다.

| 조건 | 개발 환자 | 항목 일치율 |
|---|---:|---:|
| 저장된 MedGemma 개별 처리 | 6명 | 45.65% |
| 저장된 MedGemma 인접 처리 | 6명 | 34.25% |
| AutoRG 최종 시스템 | 6명 | 46.55% |

AutoRG−개별 처리 차이는 **+0.89pp**, paired bootstrap 95% 구간은 **[−14.58, +19.35]pp**입니다. 의미 미판정을 포함한 차이 범위는 **[−34.09, +6.31]pp**여서 사전 회복 기준을 확정하지 못했습니다. 개선 1명·악화 2명·동일 3명으로 환자별 변동도 큽니다.

AutoRG는 finding·signal 항목을 각각 6/6명에서 명시했습니다. 위치 항목의 환자 평균 일치율은 33.33%, morphology는 0%, distribution은 16.67%였습니다. 확인된 명시 reference contradiction은 0/6명이지만, 추가 소견의 임상적 참·거짓은 판정하지 않았습니다.

후처리 전 일치율은 41.69%, 최종 출력은 46.55%였습니다. 좌우 수정과 global 문장 선택·생략이 함께 작용하므로 이를 생성 모델 단독 개선으로 해석하지 않습니다.

실제 자원 사용:

- 본실험 wall-clock: **230.27초**
- 내부 영역/global 생성: **31개**, 비EOS **0개**
- worker별 peak reserved VRAM: **6,076MiB**
- GPU 전체 peak 점유: **12,868 / 12,797MiB**
- 기술 처리량: **1.45 → 1.81건/분**
- 종료 후 남은 연구 GPU 프로세스: **없음**

결과는 [report.json](./results/iter_142/eval/report.json), [항목·비용 상세](./results/iter_142/eval/details.json), [독립 검산](./results/iter_142/eval/independent_verification.json)에 있습니다.

# Goal Progress / Reused Assets (목표 진전·미검증 범위, 재사용 출처·검증)

같은 DWI 대상에서 전문 예측 영역 시스템의 실제 해결 범위를 확인했습니다. 현재 개발 사례에서는 세부 위치·형상·분포 누락이 남았고, MedGemma 개별 처리 대비 분명한 회복 근거는 확보하지 못했습니다.

AutoRG는 원본 volume·segmentation·영역 판독·후처리를 사용하므로 MedGemma의 256-pixel slice 입력과 정보 처리·학습 조건이 다릅니다. 공식 문서도 SEG의 ISLES2022 학습과 RGv2의 RadGenome 학습을 명시합니다. 환자별 노출과 실제 DWI report target 학습 구성은 미확인입니다. [공식 README](https://github.com/ljy19970415/AutoRG-Brain/blob/9670703c88e8f599c0c7edc472a5ffce4dd72b0e/README.md)

입력별 SFT·적응 후 잔여 실패·독립 환자 확인·신규 방법의 contribution은 아직 검증하지 않았습니다.

# Problems (현재 결론 무효 / 재사용 전 수정 / 추후 개선을 구분)

- **현재 결론을 막는 문제:** 수치·원문 연결 결함은 발견하지 못했습니다. 의미 미판정과 환자 변동은 불확정 범위에 반영했습니다.
- **복구한 운영 일탈:** 기존 모델 폴더에 생성된 새 로그 14개를 원본 보존 이동했습니다. 안전 로더의 실제 판독은 이전 token·mask·보고서와 일치했고 기존 로그도 유지됐습니다.
- **재사용 조건:** 당시 실행 기록인 기본 worker/launcher를 그대로 재사용하지 말고, 새 안전 진입점과 모델 경로를 다음 protocol에 잠가야 합니다. 사례별 판정표는 범용 평가기가 아닙니다.
- **추후 검증:** 독립 의미 평가, 환자별 학습 노출, 공통 경계의 MedGemma 전체 비용은 미확인입니다.

# Recommendation to GPT

현재 비교는 **불확정**으로 리뷰하고 같은 frozen 6명의 prompt·checkpoint 순회는 종료할 것을 권고합니다.

다음 계획은 전체 DWI target을 한 번 부여하면서 개별/인접 문맥 표현과 전체 loss를 연결하는 **학습 가능한 통합 지점 하나**를 정해야 합니다. 전체 보고서를 slice별 정답으로 복제하지 않고, method pilot 기준에 따라 동작 확인과 가능성 탐색을 설계하십시오. 이번 결과로 입력별 적응 가능성이나 MRI 연구 전체를 기각하지 않습니다.

SELF_CHECK: FAIL
SUMMARY: AutoRG DWI 개발 6명 비교를 완료했으나 개별 MedGemma 대비 +0.89pp로 우위는 불확정이며, 복구한 SDK 로그 경로 일탈을 독립 리뷰에 전달합니다.