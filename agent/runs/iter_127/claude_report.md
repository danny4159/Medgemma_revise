# 요약

- **기술 입력 8명 중 2명에서 비뇌 T2 series가 선택되어 비교를 보류했습니다.**
- 보고서 98명을 검토해 60명을 재선정했고, 선정 검산 325/325개를 통과했습니다.
- 공식 SynthSeg 2.0 가중치·환경을 확보했지만, 잘못 연결된 입력의 zero mask를 뇌 MRI 모델 실패로 해석할 수 없습니다.
- MedGemma 생성·calibration·탐색 평가는 미실행입니다. `valid_experiment=false`로 기록했습니다.

# Work Performed

원 후보와 hash 순서를 CSV에서 재구성했습니다. 일반 normal과 수식 범위가 모호한 문장을 제외·unknown으로 기록했습니다. batch04 음성 4명을 교체하고 원 순서대로 역할을 재배정했습니다.

UCL 링크의 HTTP 404 이후 FreeSurfer 공식 저장소에서 segmentation·QC 가중치를 확보했습니다. 공식 SHA256을 검증하고 두 GPU에서 UCL 및 FreeSurfer 실행을 비교했습니다. [공식 문서](https://surfer.nmr.mgh.harvard.edu/fswiki/SynthSeg)의 `--vol`·`--qc` 경로를 사용했습니다.

실제 반환 영상을 확인하니 `7ISDTZ2JVG`는 복부·척추, `PCKMK46BRL`은 경부·척수 단면이었습니다. 같은 ZIP의 다른 T2 series에는 뇌 단면이 있었습니다. 작은 slice spacing 우선 규칙이 비뇌 series를 선택한 것입니다.

# Files Changed

새 소스 9개를 추가했습니다. 기존 소스·결과는 변경하지 않았습니다.

- 선정·판정: [mr127_select.py](/SSD1_1TB/home/milab/daniel/08_medgemma/research/mr127_select.py), [mr127_judgments.py](/SSD1_1TB/home/milab/daniel/08_medgemma/research/mr127_judgments.py), [mr127_verify_selection.py](/SSD1_1TB/home/milab/daniel/08_medgemma/research/mr127_verify_selection.py)
- 자산·입력: [mr127_assets.py](/SSD1_1TB/home/milab/daniel/08_medgemma/research/mr127_assets.py), [mr127_data.py](/SSD1_1TB/home/milab/daniel/08_medgemma/research/mr127_data.py)
- 실행·검증·봉인: [mr127_seg.py](/SSD1_1TB/home/milab/daniel/08_medgemma/research/mr127_seg.py), [mr127_seg_entry.py](/SSD1_1TB/home/milab/daniel/08_medgemma/research/mr127_seg_entry.py), [mr127_weight_check.py](/SSD1_1TB/home/milab/daniel/08_medgemma/research/mr127_weight_check.py), [mr127_finish.py](/SSD1_1TB/home/milab/daniel/08_medgemma/research/mr127_finish.py)

# Commands / Experiments (실제 실행한 명령과 성공/실패)

- `python mr127_select.py prepare`, `python mr127_judgments.py`, `python mr127_select.py lock` → 성공.
- `python mr127_verify_selection.py` → 325/325 통과.
- `python mr127_assets.py`, `python mr127_data.py budget`, `python mr127_data.py tech` → 성공.
- `python mr127_seg.py pilot` → exit 2, zero mask·유효 부피 검사 실패.
- `python mr127_seg.py fs_pilot`, `fs_recovery_pilot` → 의존성 오류. 격리 환경에 `xxhash`·`tf-keras` 설치 후 import 검증 완료.
- `python mr127_seg.py fs_compat_pilot` → exit 2, 동일 입력에서 zero mask 재현.
- 격리 Python의 `mr127_weight_check.py` → 28개 layer·74개 weight 배열 일치.
- 소스 9개 `py_compile` → 성공.
- `python mr127_finish.py` → exit 2로 중단 상태 봉인. 별도 digest 검산 → 불일치 0.

설치 명령·버전·복구 내역은 [environment_record.json](/SSD1_1TB/home/milab/daniel/08_medgemma/research/results/iter_127/environment_record.json)에 보존했습니다.

# Results (수치와 결과 파일 경로)

| 항목 | 실제 결과 |
|---|---:|
| 원문 검토 | 98명 |
| 재선정 | 기술 8 / calibration 12 / 탐색 40명 |
| 시각 확인 | 기술 8명, 비뇌 입력 2명 |
| 신규 MRI 다운로드 | 0 bytes |
| 신규 모델 다운로드 | 102,957,156 bytes |
| 재산정 ZIP 합집합 | 114개, 15,552,030,509 bytes |
| 남은 ZIP | 52개, 7,159,760,618 bytes |
| MedGemma 완료 요청 | 0건 |

`7ISDTZ2JVG`의 mask는 두 공식 실행에서 전부 0이었습니다. ICV는 UCL 36.053mm³, FreeSurfer 36.054mm³였고 우측 측뇌실 부피는 0이었습니다. **비뇌 입력에서 나온 값이므로 전문 점수로 사용하지 않았습니다.**

초기 실행의 최소 GPU 여유는 1,512MiB로 기준에 미달했습니다. 20,000MiB 한도를 적용한 재실행에서는 최소 3,750/3,824MiB를 확보했습니다. 공식 추론이 진행된 두 단계의 wall-clock 합은 246.05초입니다. 초기 peak 집계 누락은 원 로그로 별도 교정했습니다.

- 전체 결과: [result.json](/SSD1_1TB/home/milab/daniel/08_medgemma/research/results/iter_127/result.json)
- 입력 결함 근거: [input_linkage_failure.json](/SSD1_1TB/home/milab/daniel/08_medgemma/research/results/iter_127/diagnostics/input_linkage_failure.json)
- 봉인: [completion.json](/SSD1_1TB/home/milab/daniel/08_medgemma/research/results/iter_127/completion.json)

봉인 산출물 74개·기존 결과 27개·소스 9개의 hash 불일치는 모두 0입니다. 소유 GPU 프로세스는 종료됐습니다.

# Goal Progress / Reused Assets (목표 진전·미검증 범위, 재사용 출처·검증)

현재 브랜치의 `mr125_select.py` 후보 검색 함수와 `mr123_data.py` 렌더링 함수를 제한적으로 재사용했습니다. 후보 재구성·원문 연결·ZIP 실제 SHA·영상 표시를 검증했습니다.

이번 진전은 선정·공식 자산 경로 복구와 입력 연결 결함 확인입니다. VLM의 한계, sampling 효과, 전문 대안 대비 가치에 관한 유효한 실험 결과는 없습니다. 기존 FLAIR 판정도 변경하지 않았습니다.

# Problems (현재 결론 무효 / 재사용 전 수정 / 추후 개선을 구분)

- **현재 결론 무효:** 기술 2명의 선택 series가 뇌 관측 전제를 충족하지 않습니다. calibration·BA·AUROC·paired CI를 계산하지 않았습니다.
- **재사용 전 수정:** 해부학적 입력 적합성을 series 선택에 연결해야 합니다. 생성·재개·처리량·좌표·평가 잠금 검사는 미완료입니다. peak 집계 수정본의 새 GPU 실행 검증도 미완료입니다.
- **판정 경계:** 결함을 SynthSeg 출력 이후 발견했습니다. 계획의 “모델 출력 전” 대체 조건 적용 여부가 명확하지 않아 표본·입력을 소급 교체하지 않았습니다.
- **추후 개선:** 무관한 실행기 정비는 수행하지 않았습니다.

# Recommendation to GPT

현재 series 선택 설계를 **입력 전제 실패로 보류**하십시오. MRI 능력이나 sampling 가설을 기각할 근거는 없습니다.

재개를 선택한다면, 기존 ZIP에서 실제 뇌 series만 대상으로 삼는 조건을 출력 전에 고정하고 공식 기술 비교로 바로 이어지는 별도 계획이 필요합니다. 반복 설치나 감사만을 위한 후속은 권고하지 않습니다.

SELF_CHECK: FAIL
SUMMARY: iter_127은 보고서 재선정과 공식 SynthSeg 2.0 자산 복구 후 기술2/8명의 비뇌 series 연결을 확인해 보류했으며, MedGemma 비교와 가설 판정은 미실행입니다.