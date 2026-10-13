# 요약

- 고정 6명의 동일 DWI 전체 영상을 개별·인접 입력으로 비교해 **463요청을 완료**했습니다.
- 공개 소견 항목의 평균 일치율은 개별 **45.65%**, 인접 **34.25%**였습니다. 절단·모호한 대응을 포함한 차이 범위가 넓어 판정은 **inconclusive**입니다.
- 입력별 SFT와 AutoRG 실제 추론은 이번 계획대로 미실행입니다. 임상 정확도·3D 구조 효과는 아직 판단할 수 없습니다.
- 핵심 실행 검증은 통과했지만 전체 end-to-end 비용은 미계측이므로 SELF_CHECK는 보수적으로 FAIL입니다.

# Work Performed

RadGenome 고정 8명의 global 문장에서 DWI 소견을 연결했습니다. 공식 ISLES2022에서 DWI·mask·metadata 25개 파일을 선택 확보하고 CRC, 영상–mask 기하, 방향·물리좌표를 검사했습니다.

생성 전에 reference·평가 규약·코드·입력을 잠갔습니다. 공식 tensor 대조, 부분 재개, 중복 실행·변조 거부를 확인한 뒤 두 GPU에 각각 worker 2개를 배치했습니다.

# Files Changed

새 `i141_*.py` 소스 13개를 작성했습니다. 자료 확보·구성, 잠금, 생성·감독, 기술 검사, 원문 판정, 평가·검증을 포함합니다.

기존 소스·결과·환경·`hf_cache/`는 유지했습니다. Git 변경·커밋·push는 수행하지 않았습니다.

# Commands / Experiments (실제 실행한 명령과 성공/실패)

- `python i141_preflight.py fetch/inspect`: 성공.
- `python i141_select_download.py`: 선택 파일 25개 확보·CRC 검사 성공. 전체 ZIP 다운로드는 Range 지원 확인 후 중단하고 부분 파일을 보존했습니다.
- `python i141_data.py`: 초기 정밀도 검사 실패를 수정한 뒤 성공.
- `python i141_tech.py tensors/runtime`: 수동 BOS 대조 오류 수정 후 tensor 8건, 실행 검사 10건 통과.
- `python i141_cap_control.py`: 계획된 2048-token 재확인과 2/4-worker 비교 완료.
- `python i141_execute.py`: 463/463 완료, worker 종료 코드 모두 0.
- `python i141_judge.py`, `python i141_eval.py analyze`, `python i141_finish.py`: 원문 대응·집계·독립 산술 검증 완료.

# Results (수치와 결과 파일 경로)

| 항목 | 개별 S | 인접 A |
|---|---:|---:|
| 요청 수 | 385 | 78 |
| 공개 항목 평균 일치율 | 45.65% | 34.25% |
| 절단 | 2/385 | 32/78 |
| 명확한 위치 항목 일치 | 5/17 | 2/17 |
| 생성 token | 21,454 | 68,550 |

A−S 점추정은 **−11.41pp**, 미판정·절단을 포함한 범위는 **[−46.39, +54.35]pp**입니다. 추가 소견을 임상 허위로 판정하지 않았습니다.

4-worker 개발 처리량은 2-worker 대비 **1.43→2.80 요청/분**, 공통 8요청의 token은 모두 일치했습니다. 본생성 감독기 시간은 **2,026.55초**, GPU별 최소 여유는 **5,073/5,207MiB**였습니다.

[평가 보고서](/SSD1_1TB/home/milab/daniel/08_medgemma/research/results/iter_141/eval/report.json) · [비용 기록](/SSD1_1TB/home/milab/daniel/08_medgemma/research/results/iter_141/eval/cost.json) · [최종 검증](/SSD1_1TB/home/milab/daniel/08_medgemma/research/results/iter_141/final_verification_korean.json) · [리뷰 묶음](/SSD1_1TB/home/milab/daniel/08_medgemma/research/results/iter_141/review_bundle.json)

# Goal Progress / Reused Assets (목표 진전·미검증 범위, 재사용 출처·검증)

자료 준비에서 실제 MRI 판독 비교로 넘어갔습니다. 현재 frozen 구성에서는 인접 처리의 우위를 확보하지 못했고, 반복·절단이 판단을 크게 제한했습니다.

`9157bb31ca641fe720bd2d5203780df82635d53d`의 `i136_*`에서 실행·잠금·hash·출력 경계 부분을 파생했습니다. 기존 소스 불변, 모델 파일 15개 hash, 완료 파일 713개, 실제 입력 길이 463건을 확인했습니다.

적응 후 효과, 전문 3D 시스템의 해결 여부, 신규 기여는 미검증입니다.

# Problems (현재 결론 무효 / 재사용 전 수정 / 추후 개선을 구분)

- **현재 해석 제한:** 보고서 텍스트 대응이며 독립 임상 정확도 평가가 아닙니다. 절단·미판정 때문에 3D 효과를 확정할 수 없습니다.
- **검증 미완료:** NIfTI 반입·전처리부터 의미평가까지 전체 end-to-end 비용을 직접 계측하지 못했습니다.
- **재사용 전 수정:** 실행기는 절대경로·고정 실험 범위에 의존합니다. 일반 재사용 전 경로 처리와 미사용 진입점을 정리해야 합니다.
- **추후 확인:** 독립 환자·평가자 재현, 학습 노출, RGv2의 실제 DWI target·성능 지원이 필요합니다.

# Recommendation to GPT

같은 DWI global 항목으로 **AutoRG 예측 mask 경로의 소수 실제 대조**를 먼저 권고합니다. 입력별 SFT 연결은 유지하되 전체 sequence supervision으로 계획하고, 전체 보고서를 개별 slice에 복제하지 않아야 합니다. 이번 불확정을 MRI 연구 전체의 기각으로 확대하지 마십시오.

SELF_CHECK: FAIL
SUMMARY: MRI 개발 6명의 개별·인접 판독 463건을 완료했으나 절단·미판정으로 우위는 불확정이며, 전체 end-to-end 비용 검증은 미완료다.