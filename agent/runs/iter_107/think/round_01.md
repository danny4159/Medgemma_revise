# 사고 라운드 1

## 이번에 확인한 것

- `agent/GOAL.md`, `agent/runs/iter_106/review.md`와 review.json의 code_assets, `agent/LIMITATIONS.md`의 해당 한계, `agent/CODE_ASSETS.md`의 iter_105/106 항목을 읽었다. research 작업 트리는 clean이다. 코드 수정·파일 생성·실험 실행은 하지 않았다.
- iter_106의 독립 recall 0.875와 공동 0.234375/0.109375, 반복 손실 0.40625는 보존한다. 이 결과는 미지원 복합 입력의 관찰이며 다음 후보의 정상 사용 한계 근거로 승격하지 않는다.
- [CURE 공식 저장소](https://github.com/PabloMessina/CURE)는 PG, GRG, anatomy별 locate/describe 경로를 구분한다. 공식 hybrid는 anatomy별 독립 출력과 GRG를 결합한다. 여기서 동일한 정답 phrase 정보를 받는 복수 phrase 공동 grounding 경로는 확인하지 못했다. 이는 모든 모델에서 그런 경로가 없다는 뜻은 아니다.
- [CURE 논문](https://arxiv.org/html/2601.15408v1)의 PG 설명은 하나의 원문 phrase에 여러 box가 있으면 모두 응답에 포함한다고 명시한다. 따라서 자연 다중 영역 phrase는 iter_106의 문장 이어 붙이기와 지원 범위가 다르다.
- 로컬 `research/results/datasets/padchest_gr/raw/grounded_reports_20240819.json`과 master split을 읽었다. 공식 train에서 abnormal=true, progression=None, boxes가 2개 이상인 finding 행은 857개였다: 2개 798행, 3개 38행, 4개 17행, 5개 3행, 6개 1행. 이는 환자 수나 최종 적격 표본 수가 아니다. 시간 표현·환자 중복·주석 합의는 아직 적용하지 않았다.
- 실제 예에는 양측 흉막 비후, prominent hila 등이 있었다. 그러나 같은 finding의 boxes는 좌우 두 영역인데 extra_boxes는 하나의 넓은 영역인 사례도 있었다. 따라서 box 개수 불일치를 곧바로 근거 누락으로 판정할 수 없다.
- 공식 저장 코드 `research/results/iter_085/official/source/notebooks/evaluation/Evaluate_PadChest-GR_Phrase_Grounding.ipynb`는 `calculate_bbox_union_iou`를 사용한다. `vlm_research_kit/utils/bbox_utils.py`를 확인하니 shapely의 실제 polygon union이다. 외접 사각형 하나로 바꾸는 평가가 아니다. 면적 가중치와 작은 근거의 보존이라는 질문은 가능하지만 평가가 빈 공간을 무시한다는 주장은 성립하지 않는다.

## 두 후보의 현재 선택

1. **공식 독립 처리의 자연 다중 영역 근거 보존 — 우선 검토.** 지원 범위와 실제 공개 자료는 확인했다. 기술 질문은 여러 공간적 근거를 모두 보존하는가이며, 실패 조건은 일부 근거만 회복하는 경우다. 다만 공개 정답이 병변별 분할을 보장하는지와 단순 대안 이후의 중요성은 미확정이다. 이 둘이 성립해야 작은 실제 비교를 선택한다.
2. **지원되는 복수 소견 공동 경로의 동일 정보 비교 — 현재 실행 보류.** 확인한 CURE 경로만으로는 제공된 소견의 공동 위치 찾기와 소견 발견을 같은 정보 조건으로 비교할 수 없다. 새 모델 설치나 prompt 변형으로 이 빈틈을 메우지 않는다.

## 과거 설명과의 관계

`agent/runs/iter_043/review.md`를 읽었다. 직접 SFT가 retrieval보다 높았고, 환자별 영상 구별은 불확정이었다. 따라서 문장 prior 또는 영상 무사용을 새로 발견한 문제처럼 재개하지 않는다. iter_046/048의 강한 모듈형 대안과 형식 학습 회복도 유지한다. 이번 후보가 이들과 구별되려면 자연 다중 영역의 보존이라는 조건에서 구체적인 잔여 문제가 필요하다.

- 시험 설정: A/B 선택, 복합 phrase, LoRA 확대는 보류 유지.
- 연구 관찰: iter_106 출력 손실은 유지하지만 새 가설 검증은 이번 라운드에 없었다.
- 연구 질문: 자연 다중 영역 근거 보존을 후보로 좁혔으며 아직 중요한 미해결 한계로 확정하지 않았다.

## 재사용과 남은 확인

현재 브랜치에 `lk105_data.py`, `pg39_data.py`, `report86_common.py`, `lk105_run.py`, `lk106_run.py`, `lk106_spec.py` 등이 존재한다. iter_105 원 review.json은 데이터 연결과 한정 실행 경로를 승인하지만 전체 snapshot을 승인하지 않았다. iter_106 parser의 malformed 처리, 가중치 hash 계승, admission 실패 기록 문제는 유지한다. 구현이 결정되지 않았으므로 선별 반입이나 수정 범위를 아직 승인하지 않는다.

다음 확인은 공식 PadChest-GR 주석의 boxes/extra_boxes 의미, 기존 저장 출력의 해당 사례, 강한 대안의 같은 사례 연결로 제한한다. 현 단계의 지배 비용은 원문·자료 해석이며 정확한 소요 시간은 미측정이다.

## 대규모 GPU 필요 후보

다중 영역 근거의 완전성과 판독을 함께 학습하는 대규모 재학습은 가능한 장기 후보지만 현재 문제와 단순 대안의 부족함이 입증되지 않았다. 이번 투자 대상으로 선정하지 않는다.

## 다음에 파고들 질문
- 공식 PadChest-GR 배포 설명과 CURE dataset loader에서 boxes와 extra_boxes는 어떤 주석 관계인가? 영역 개수 대신 두 주석 모두에서 지지되는 공간적 근거 보존을 정의할 수 있는가?
- iter_085/086 및 기존 PG 저장 출력 중 자연 다중 영역 phrase와 정확히 연결되는 출력이 있는가? 대표 사례에서 실제 누락과 주석 분할 차이를 구별할 수 있는가?
- iter_046/048의 적응 MedGrounder 저장 출력 또는 공식 후처리가 같은 조건을 이미 충분히 해결하는가? 비교 가능한 자료가 없다면 신규 실행의 정보 가치가 비용을 정당화하는가?
