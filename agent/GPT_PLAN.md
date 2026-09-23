# Current Understanding

현재 평가는 2D QA·분류·위치 추정뿐 아니라 공식 형식의 3D CT/MR까지 폭넓게 다룹니다. 특히 비공식 위치 프롬프트의 퇴화, 클래스 불균형, 기준선, 프롬프트 민감도 등을 대조 실험으로 확인한 점은 강점입니다.

가장 중요한 문제는 **3D CT와 단일 슬라이스 비교에서 프롬프트 조건이 통제되지 않았다는 것**입니다.

- 3D 조건은 프롬프트에서 이미 입력이 `"CT slices"`임을 알려 줍니다: [rerun_ct3d_official.py](/SSD1_1TB/home/milab/daniel/08_medgemma/rerun_ct3d_official.py:115)
- 단일 슬라이스 조건에는 이미지와 질문만 주어집니다: [rerun_ct3d_official.py](/SSD1_1TB/home/milab/daniel/08_medgemma/rerun_ct3d_official.py:131)
- 그런데 주요 정량 결과가 바로 모달리티 인식 `3D 3/3 vs single 2/3`입니다: [MEDGEMMA_1.5_평가정리.txt](/SSD1_1TB/home/milab/daniel/08_medgemma/MEDGEMMA_1.5_평가정리.txt:442)

따라서 현재 결과만으로는 s0338의 개선이 여러 슬라이스를 본 효과인지, 프롬프트에서 “CT”라는 정답을 읽은 효과인지 구분할 수 없습니다. 문서의 “같은 볼륨·같은 질문, 입력 방식만 변경”이라는 설명도 엄밀히는 성립하지 않습니다.

MR 비교에도 유사한 비대칭이 있고, 3D는 t1c만 사용하지만 단일 결과는 네 시퀀스 12개를 합산하므로 `3/3 vs 0/12` 역시 완전한 matched comparison은 아닙니다: [rerun_mr3d_official.py](/SSD1_1TB/home/milab/daniel/08_medgemma/rerun_mr3d_official.py:76), [rerun_mr3d_official.py](/SSD1_1TB/home/milab/daniel/08_medgemma/rerun_mr3d_official.py:100).

# Hypothesis

**H1:** CT 모달리티 인식 개선의 일부 또는 전부는 다중 슬라이스 자체가 아니라 프롬프트의 `"CT slices"` 단서에서 발생한다.

대립되는 영상정보 가설은 다음과 같습니다.

**H2:** 모달리티 이름을 프롬프트에서 제거해도 동일한 85장 입력은 단일 슬라이스보다 CT를 더 안정적으로 인식한다.

이 구분이 중요한 이유는 현재 프로젝트가 MedGemma의 강한 프롬프트 민감도를 이미 확인했기 때문입니다. 정답을 포함한 프롬프트로 측정된 모달리티 정확도를 영상 이해의 증거로 사용하면 3D 성능을 과대평가할 수 있습니다.

# Proposed Experiment

기존 TotalSegmentator 3케이스와 현재 전처리를 그대로 사용해 **2×2 요인 실험**을 수행합니다.

| 조건 | 입력 영상 | 사전 지시문 |
|---|---|---|
| A | 중앙 슬라이스 1장 | 중립: “Review the medical image(s) carefully.” |
| B | 중앙 슬라이스 1장 | CT 명시: 현재의 “CT slices from a body scan” |
| C | 동일 볼륨의 85장 | 중립: “Review the medical images carefully.” |
| D | 동일 볼륨의 85장 | CT 명시: 현재 공식 조건 |

모든 조건에 정확히 같은 질문을 사용합니다.

> What imaging modality is this? Answer with a short term only.

추가 비용을 거의 들이지 않고 영상 의존성을 더 강하게 확인하려면 각 조건에 아래 질문도 넣습니다.

> Which region of the body is shown? Answer with a short term only.

D는 기존 결과를 재사용할 수 있습니다. A도 현재 single-slice modality 결과를 사실상 재사용할 수 있으므로 새 추론은 주로 B와 C, 총 6회입니다. 완전한 실행 재현성을 원하면 12개 조건을 모두 다시 실행합니다.

핵심 비교는 `C−A`, 즉 **모달리티 단서가 없는 상태에서 슬라이스 수만 바꾼 차이**입니다. `B−A`는 프롬프트 누출 효과를 측정하는 positive control입니다.

# Implementation Tasks for Claude

1. 기존 파일을 덮어쓰지 말고 `diagnose_3d_prompt_leakage.py` 같은 독립 스크립트를 만든다.
2. CT 로딩, HU 3중 윈도우, 85장 균등 샘플링, greedy decoding은 현재 구현에서 그대로 재사용한다.
3. 다음 두 변수만 직교하도록 조건을 생성한다.
   - `n_slices`: `1`, `85`
   - `modality_hint`: `neutral`, `ct_explicit`
4. 조건별로 실제 전송한 전체 프롬프트를 결과 JSONL에 저장한다.
5. 결과 레코드에 최소한 다음 필드를 기록한다.
   - `case`
   - `n_slices`
   - `modality_hint`
   - `query`
   - `output`
   - `modality_correct`
   - `bodypart_correct` 또는 수동 검토 대상 값
6. 출력은 새 파일 `eval_results/diagnostics_3d_prompt_leakage.jsonl`에 저장한다.
7. 네 조건의 case-level 결과를 한 표로 출력하는 간단한 분석 함수를 포함한다.
8. 이번 실험에서는 슬라이스 수 sweep, 새 데이터 다운로드, LoRA 학습을 추가하지 않는다. 먼저 현재 핵심 결론의 내부 타당성을 확인한다.

# Evaluation

일차 지표는 case-level CT 인식 정확도입니다. `"ct"` 또는 `"computed tomography"`를 정답으로 인정하고 X-ray 등은 오답으로 처리합니다.

판정 기준:

- **3D 영상정보 효과 지지:** 중립 조건에서 C가 A보다 개선되고, 특히 기존 실패 사례 s0338이 `A=X-ray`, `C=CT`가 된다.
- **프롬프트 누출 가설 지지:** B가 A보다 개선되지만 C는 A와 같거나, s0338이 `B=CT`, `C=X-ray`가 된다.
- **두 효과 모두 존재:** B와 C가 모두 A를 개선한다. 이 경우 현재 `3/3 vs 2/3` 결론은 방향은 유지되지만 효과 크기는 분리해서 보고해야 한다.
- **판단 불가:** 모든 조건이 3/3이거나 출력이 불안정해 차이가 사라진다. 그러면 3케이스로는 결론을 내리지 않고 표본 확대가 필요하다.

n=3이므로 통계적 유의성 검정보다는 세 케이스의 paired outcome을 그대로 보고해야 합니다. 이 실험은 논문급 성능 추정이 아니라 **현재 인과 해석의 오류 여부를 확인하는 작은 진단 실험**입니다.

# Risks / Checks

- `"CT"`가 들어간 조건의 모달리티 정확도는 성능 지표가 아니라 프롬프트 순응 대조군으로만 사용해야 합니다.
- 중립 지시문에 `volume`, `scan`, `axial`처럼 모달리티를 암시하는 단어를 넣지 않아야 합니다.
- 단일 조건은 반드시 85장 조건에 포함된 동일한 중앙 슬라이스를 사용해야 합니다.
- 전처리, 질문, 생성 설정, 슬라이스 방향은 조건 간 동일해야 합니다.
- 현재 데이터에는 병리 판독 정답이 없으므로 생성된 소견의 구체성이나 길이를 정확도로 해석하면 안 됩니다.
- 결과가 가설을 지지하면 문서의 “3D에서 모달리티가 정확해졌다”는 결론을 수정하고, 이후 3D 평가 전반에 prompt-information audit을 적용해야 합니다.
- 이 검토에서는 요청대로 코드를 수정하거나 새 실험을 실행하지 않았습니다.