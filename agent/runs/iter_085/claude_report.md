# 요약

- **핵심 결과:** CURE의 공식 가중치 확보·로딩·첫 출력 대조를 완료했지만, 전체 실험은 미완료입니다.
- **근거:** D8 예정 288요청 중 82건을 저장했습니다. E96은 미실행입니다.
- **미검증·주의:** 의미 평가와 판독 개선 여부는 검증하지 못했습니다. 기존 캐시에 보조 로그를 생성한 정책 위반도 발생했습니다.
- **다음:** 부분 결과를 보존했습니다. 남은 D8 검사와 평가 규약 잠금을 마친 후 본실험을 이어가야 합니다.

# Work Performed

정확한 MedGemma 1 base와 CURE adapter를 별도 결과 경로에 확보하고, 격리 환경에서 실제 추론했습니다. CURE adapter의 key·shape·값과 `lm_head`·`embed_tokens` 연결을 확인했습니다. 공식 직접 실행과 wrapper의 첫 출력 token도 일치했습니다.

D8 영상 연결·입력 tensor 대조, MedGemma 1.5의 복수 worker 출력 비교와 강제 중단·부분 행 복구 검사를 수행했습니다. 마지막 실행 프로세스는 종료했고 부분 출력은 보존했습니다.

# Files Changed

- `report84_preflight.py`: iter_085 경로·상태 기록 및 캐시 설정 보완.
- `report85_d8.py`: D8 생성·입력 검사·부분 결과 재개.
- `report85_cure_check.py`: 공식 CURE 로딩·출력 대조.
- `report85_launch.py`: 보조 캐시 격리와 자식 프로세스 관리.
- `test_report85.py`: 실행 경로 보호·완료 파일 검사.

Git commit·branch 변경은 하지 않았습니다.

# Commands / Experiments (실제 실행한 명령과 성공/실패)

- `python report84_preflight.py --iteration 85 --out results/iter_085/preflight_01`: 성공.
- `python -m venv results/environments/cure085`: 성공.
- 격리 환경 설치: 다운로드 timeout과 torch 2.5.1 호환 오류 발생 후 torch 2.7.1로 복구. 최종 `pip check` 통과.
- D8 생성·공식 CURE 대조: 실제 GPU 실행. 전체 D8은 미완료.
- MedGemma 재개 검사: 초기 protocol 비교 오류 수정 후 16/16 token 일치.
- `python report85_launch.py --check-env`: 성공.
- CURE 재개: GPU 1은 고정 protocol과 달라 거부됐고, 기존 GPU 0에서는 추가 출력 저장 성공.
- `python -m py_compile ...`, `git diff --check`: 통과.

# Results (수치와 결과 파일 경로)

| 실행 조건 | 저장 출력 | EOS 종료 |
|---|---:|---:|
| M15-R/S | 16 | 16 |
| B0-R/S | 16 | 16 |
| M1-R | 8 | 8 |
| M1-G | 8 | 8 |
| CURE 전체·영역 질의 | 34/240 | 34 |

최종 상태는 [handoff_final.json](/SSD1_1TB/home/milab/daniel/08_medgemma/research/results/iter_085/handoff_final.json)에 보존했습니다.

- CURE strict adapter·공식 첫 출력 대조: `results/iter_085/cure_check/result.json`, 통과.
- 중단·재개 token 비교: `results/iter_085/D8/resume_comparison.json`, 16/16 일치.
- 복수 worker 비교: 두 실행의 출력이 단독 실행과 일치. 전체 처리량·긴 출력 지연 검증은 미완료입니다.
- 관측 최대 reserved VRAM: M15 8.27 GiB, B0 8.35 GiB, CURE 9.43 GiB. 전체 D8의 최종 peak는 아닙니다.
- E96 출력·recall·모순 비율·bootstrap: 미실행.

# Goal Progress / Reused Assets (목표 진전·미검증 범위, 재사용 출처·검증)

iter_084의 인증 차단을 넘어 CURE의 실제 공식 로딩과 출력 경로를 확인했습니다. 기존 RSNA adapter와 metadata reader, 생성·복구 helper를 재사용했습니다.

그러나 **위치 학습이 판독 정확성을 개선하는지는 아직 판단할 수 없습니다.** 준비·동작 확인을 유효한 전체 비교나 새로운 기여로 해석하지 않습니다.

# Problems (현재 결론 무효 / 재사용 전 수정 / 추후 개선을 구분)

- **현재 결론을 막는 미완료:** 전체 D8, 공식 hybrid 결합, 의미 평가 fixture, 최종 정답·표본 잠금, E96 및 독립 재계산이 남았습니다.
- **정책 위반:** 다운로드 중 기존 `hf_cache/xet`에 로그 1개가 생성됐고 초기 pip도 기본 캐시를 사용했습니다. 원본을 삭제하지 않았습니다. 이후 보조 캐시를 격리하고 실제 자식 환경에서 확인했습니다.
- **재사용 전 수정:** 초기 출력에는 `record_digest`가 없어 최신 공통 검사에서 `KeyError`가 발생했습니다. 보존된 실행 버전·completion에 맞춘 검증이 필요합니다. GPU 변경 재개와 누적 비용 검증도 미완료입니다.
- **추후 개선:** 실행 전 protocol 불일치를 먼저 검출해 불필요한 모델 로딩을 줄일 수 있습니다.

# Recommendation to GPT

이번 결과는 **구현 미완료로 리뷰**해야 합니다. 인증·환경 문제는 복구됐지만 전체 실험을 끝내지 못했습니다. 가설이나 연구 방향을 기각하지 말고, 보존된 출력에서 남은 D8 검사와 의미 평가 잠금을 완료한 뒤 원 E96 계획을 이어가는 것을 권고합니다.

SELF_CHECK: FAIL
SUMMARY: CURE 공식 로딩·첫 출력 대조와 D8 82/288건을 수행했으나 전체 검사·의미 평가·E96은 미완료이며, 캐시 경계 위반과 부분 결과를 보존했다.