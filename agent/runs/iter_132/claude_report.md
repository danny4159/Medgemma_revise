# 요약

- 직접 비교 정확도는 **49.57%**로, 개별 점수 **65.38%**, MRIQC SNR_total **98.72%**보다 낮았습니다.
- 개발 40명의 360요청을 완료했습니다. 주평가 39명·비동점 92쌍의 결과와 CI를 독립 검산했습니다.
- 순서 일관성은 **6.67%**였습니다. 확대 조건 미충족으로 보존 20명은 실행하지 않았습니다.
- 비교·집계는 검증됐지만, batch2 출력 불일치·개발 1건 비EOS·I/O 사후 계측을 명시해 **SELF_CHECK: FAIL**로 보고합니다.

# Work Performed

공식 점수 436행, IQM 436행, 영상 객체를 연결해 적격 140명을 확인했습니다. 기술 6명·IQM 학습 60명·개발 40명·보존 20명을 분리하고, 평가 코드·입력·모델 digest를 생성 전에 잠갔습니다.

RAS 정렬·고정 axial 8장·volume min–max 입력을 구성했습니다. 두 GPU에서 처리량 비교, 부분 완료 후 재개, 기술 생성, 개발 평가와 독립 검산을 실행했습니다.

# Files Changed

`mr132_*.py` 15개를 새로 작성했습니다. 주요 파일은 입력 구성 `mr132_data.py`, IQM 학습 `mr132_baseline.py`, 실행·재개 `mr132_run.py`, 평가·검산 `mr132_eval.py`·`mr132_verify.py`입니다.

반입한 `mr123_data.py`는 수정하지 않았습니다. Git commit·branch 변경은 하지 않았으며, 소스 보존은 orchestrator에 맡깁니다.

# Commands / Experiments (실제 실행한 명령과 성공/실패)

- `python mr132_preflight.py`: metadata 연결 후 저장 하위 경로 조회 실패. 수정 후 `--select-only`로 선정 완료.
- `python mr132_data.py technical`, `python mr132_data.py development`: 성공.
- 격리 환경 Python으로 `mr132_baseline.py`: 환자별 5-fold CV와 baseline 선택 성공.
- `python mr132_tests.py cpu`: **35/35**. `runtime`: **10/10**.
- `python mr132_tech.py tensors`: 수동 대조의 BOS 중복 수정 후 **12/12** 통과.
- batch1/batch2 pilot: 각각 12요청 완료. batch2는 token **7/12 불일치**로 미채택.
- `python mr132_control.py`: 기술 54·개발 360요청, 평가·독립 검산 완료.
- `python mr132_resource_profile.py`: 사후 기술 6요청의 기존 token 재현 성공.
- `python mr132_finish.py`: 완료 봉인 성공. 연결된 **85파일·15소스 digest** 재검사 일치.

세부 명령 인수와 종료 코드는 `results/iter_132/control/`에 보존했습니다.

# Results (수치와 결과 파일 경로)

주지표는 전문가 등급이 다른 쌍의 **환자별 평균 pair accuracy**입니다.

| 대조 | 정확도 |
|---|---:|
| MedGemma 직접 비교 | 49.57% |
| MedGemma 개별 점수 | 65.38% |
| MRIQC SNR_total | 98.72% |
| MRIQC CJV / EFC | 각각 97.86% |
| IQM logistic regression | 96.58% |

직접−개별 차이는 **−15.81pp**, 95% CI **[−25.21, −6.41]pp**입니다. 직접−SNR_total은 **−49.15pp**, CI **[−53.42, −44.87]pp**입니다.

직접 비교 첫 줄은 A가 **232/240건**이었습니다. 순서 일관성은 **8/120쌍**입니다. 개발 출력 **359/360건**이 EOS로 종료했고, 나머지 1건은 사전 규칙대로 invalid=0으로 분모에 유지했습니다.

총 **456요청**을 실행했습니다. 정식 기술·개발 414건과 처리량·재개·자원 확인 42건입니다. 개발 실행은 **26.73분**이었고, GPU별 최대 실제 점유는 **11,521/11,449MiB**, 최소 여유는 **12,604/12,678MiB**였습니다. 모든 소유 GPU 프로세스가 종료됐습니다.

- [개발 결과](/SSD1_1TB/home/milab/daniel/08_medgemma/research/results/iter_132/eval/development_report.json)
- [독립 검산](/SSD1_1TB/home/milab/daniel/08_medgemma/research/results/iter_132/eval/development_independent_verify.json)
- [실행·자원 기록](/SSD1_1TB/home/milab/daniel/08_medgemma/research/results/iter_132/execution_ledger.json)
- [최종 점검](/SSD1_1TB/home/milab/daniel/08_medgemma/research/results/iter_132/completion_audit.json)

# Goal Progress / Reused Assets (목표 진전·미검증 범위, 재사용 출처·검증)

현재 frozen MedGemma·MR-ART·8장 입력에서는 직접 비교가 개별 채점을 회복시키거나 강한 IQM 대조 이후 추가 가치를 제공하지 않았습니다. **제시 순서에 따른 선택 변화**를 관찰했지만 내부 원인은 확정하지 않았습니다.

`4682b4…`의 `mr123_data.py`에서 `normalization_window`·`render_slice`만 사용했습니다. 반입 blob, 합성 물리좌표, 실제 방향·tensor, 138개 NIfTI·1,104개 PNG 연결과 재사용 경계를 검증했습니다.

정답은 전체 촬영의 거친 전문가 품질 등급입니다. 건강한 성인의 움직임 촬영 자료이므로 임상 재촬영·질병 진단·다른 sequence로 일반화할 수 없습니다. [MR-ART 원 논문](https://www.nature.com/articles/s41597-022-01694-8)

# Problems (현재 결론 무효 / 재사용 전 수정 / 추후 개선을 구분)

- **현재 결론 무효:** 발견하지 못했습니다. 주수치·CI·확대 분기의 독립 검산 53개가 통과했습니다.
- **검증 예외:** batch2 정합성 미통과, 개발 1건 비EOS, I/O 압력의 사후 보완 계측이 있습니다. 사전 측정으로 소급 주장하지 않았습니다.
- **재사용 전 수정:** 새 자료의 입력 의미와 단계 진입 gate를 다시 연결해야 합니다. 미실행 holdout 경로는 검증 범위 밖입니다.
- **추후 개선:** 타 모델·직접 적응·독립 확인과 IQM 생성 전체 비용은 미검증입니다.

# Recommendation to GPT

현재 **frozen MR-ART 품질 직접 비교 후보의 추가 투자를 보류**할 것을 권고합니다. 확대하지 않는 사전 분기는 지켰습니다. 이 결과를 MRI 전체의 실패나 적응 불가능성으로 확대하지 말고, 순서 선택 관찰과 검증 예외를 독립 리뷰에서 판단해 주십시오.

SELF_CHECK: FAIL
SUMMARY: MR-ART 개발40명에서 직접 비교49.57%가 개별65.38%·SNR_total98.72%보다 낮고 순서 일관성6.67%로 확대하지 않았다. 비교·집계는 검증됐으나 출력·계측 예외를 남겼다.