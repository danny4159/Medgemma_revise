# 요약

- **핵심 결과:** 탐색 40명의 U/A 80건이 모두 PRESENT였습니다. 두 입력의 BA는 0.50으로, 사전 기준상 현재 frozen 설계 종료에 해당합니다.
- **근거:** SynthSeg 완료 35명의 부피 기준 BA는 0.941이었습니다. 결과·fallback·비용·판정의 독립 검산 285/285가 통과했습니다.
- **미검증·주의:** SynthSeg 5명은 메모리 오류로 실패했습니다. 전체 대안 충분성과 임상 진단 정확도는 주장하지 않습니다.
- **다음:** 관찰을 보존하고 GPT 독립 리뷰로 넘깁니다. 모든 소유 프로세스는 종료됐습니다.

# Work Performed

고정 60명의 환자·역할·보고서 정답을 유지하면서 뇌 series 연결 3건을 수정했습니다. 전체 입력 검증 후 기술8명, calibration12명, 탐색40명을 실행했습니다. 학습과 추가 환자 실험은 수행하지 않았습니다.

# Files Changed

연구 폴더에 신규 소스 20개를 작성했습니다. 입력 구성, 공식 SynthSeg 실행, 안전한 생성·재개, 평가·독립 검산·보존을 포함합니다.

주요 파일은 [mr128_gen.py](/SSD1_1TB/home/milab/daniel/08_medgemma/research/mr128_gen.py), [mr128_analysis.py](/SSD1_1TB/home/milab/daniel/08_medgemma/research/mr128_analysis.py), [mr128_verify_results.py](/SSD1_1TB/home/milab/daniel/08_medgemma/research/mr128_verify_results.py)입니다. 전체 목록과 digest는 [completion.json](/SSD1_1TB/home/milab/daniel/08_medgemma/research/results/iter_128/completion.json)에 있습니다.

기존 소스 59개와 이전 결과 75개는 불변을 확인했습니다. Git commit·push는 하지 않았습니다.

# Commands / Experiments (실제 실행한 명령과 성공/실패)

- `python mr128_seg.py --inputs results/iter_128/remaining_inputs.json --stage remaining`: exit 2. 47명 완료, 5명 cuDNN scratch allocation 실패.
- 격리 Python으로 `mr128_finish_pipeline.py --pid 2279392 --prepare-pid 2295903`: exit 0. calibration 잠금 → 80건 생성 → 평가·독립 검산 완료.
- 격리 Python으로 `mr128_resources.py`, `mr128_archive.py`: 모두 exit 0.
- 자료·실행 검사 53/53, 평가 fixture 20/20, 재개·tensor 검사 19/19, 전체 입력 검산 605/605 통과.
- 기본 환경을 보존하고 격리 환경에 SciPy 1.15.3을 설치·실입력 검증했습니다. [환경 기록](/SSD1_1TB/home/milab/daniel/08_medgemma/research/results/iter_128/coordinate_environment.json)에 명령과 버전을 보존했습니다.

# Results (수치와 결과 파일 경로)

| 조건 | 평가 환자 | BA | sensitivity | specificity |
|---|---:|---:|---:|---:|
| U: 넓은 구간 8장 | 40 | 0.500 | 1.000 | 0.000 |
| A: 측뇌실 기반 선택 8장 | 40 | 0.500 | 1.000 | 0.000 |
| S: 전문 부피 기준, 완료 사례만 | 35 | 0.941 | 0.882 | 1.000 |

- A−U = 0, paired 95% CI [0, 0]. 모든 paired 상태가 같아서 생긴 퇴화 구간이며 모집단 효과의 정확한 영점을 뜻하지 않습니다.
- A는 12명에서 입력이 달라졌습니다. 23명은 고유 slice 부족, 5명은 segmentation 실패로 fallback했습니다.
- S available-case AUROC는 0.990입니다. 5명 누락 때문에 전체 40명의 대안 충분성은 미판정입니다.
- 본 생성은 **80/80 EOS**, 최대 27 token, wall-clock **194.84초**였습니다. 첫 줄 형식은 strict 40건·loose 40건으로 구분했습니다.
- GPU 전체 peak는 SynthSeg **20,375/20,303 MiB**, MedGemma 본실험 **9,775/9,703 MiB**였습니다.
- batch2는 기술 출력 token이 10/16 달라 채택하지 않았습니다. 본실험은 batch1·GPU당 worker1을 유지했습니다.

[평가 결과](/SSD1_1TB/home/milab/daniel/08_medgemma/research/results/iter_128/eval/report.json), [독립 검산](/SSD1_1TB/home/milab/daniel/08_medgemma/research/results/iter_128/eval/independent_verify.json), [자원·비용 기록](/SSD1_1TB/home/milab/daniel/08_medgemma/research/results/iter_128/resource_summary.json)에 상세 수치를 보존했습니다.

# Goal Progress / Reused Assets (목표 진전·미검증 범위, 재사용 출처·검증)

입력 연결 오류를 해결하고 실제 T2 출력 비교까지 완료했습니다. 현재 조건에서는 단순 slice 선택으로 고정 양성 응답이 회복되지 않았습니다. 높은 fallback과 약한 보고서 정답 때문에 일반 MRI 능력이나 내부 원인은 확정하지 않습니다.

기존 선정 기록, `mr123_data.py`의 렌더링·U 구성, 고정 parser, 공식 SynthSeg 자산을 필요한 범위에서 검증해 재사용했습니다.

# Problems (현재 결론 무효 / 재사용 전 수정 / 추후 개선을 구분)

- **현재 결론 제한:** U/A 한정 비교는 검산됐지만, S 5명 누락으로 전체 대안 충분성은 판단할 수 없습니다.
- **재사용 전 보완:** SynthSeg 메모리 실패 경로와 기술 batch 비교의 CPU·RAM·I/O 세부 계측이 남았습니다. 미계측 값을 본실험 기록으로 소급 대체하지 않았습니다.
- **미검증:** 전문의 영상 정답, 독립 환자, 타 모델·학습 방법의 결과는 없습니다.

# Recommendation to GPT

사전 음성 기준에 따라 **현재 frozen T2 이진 설계의 투자를 종료**하고 방법 개발 진입은 보류할 것을 권고합니다. S의 좋은 available-case 결과는 보존하되 전체 충분성으로 승인하지 말아야 합니다. 실행 실패와 미계측 항목이 있으므로 독립 리뷰가 필요합니다.

SELF_CHECK: FAIL
SUMMARY: MRI 40명에서 U/A 모두 BA 0.50; SynthSeg 완료 35명은 BA 0.941이나 5명 실패로 전체 대안 충분성은 미판정.