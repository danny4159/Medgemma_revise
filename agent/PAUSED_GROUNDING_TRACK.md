# 위치·근거 활용 탐색 — 사용자 우선순위에 따른 보류

2026-10-13, iter_121 시작 전 사용자 요청으로 MR-RATE MRI 탐색을 우선한다.
기존 방향을 과학적으로 기각하거나 완료 처리하지 않는다. 기존 번호·GOAL·원 결과는 유지한다.

## 어디까지 했나

- 최신 원본: agent/runs/iter_120/plan.md, review.md, review.json, next_iteration_decision.json.
- 질문: 참고 영상의 대상 정보를 다른 영상의 대상 선택에 활용하는가?
- 상태: Task3 1,148행의 적격 관계쌍 0개로 모델 비교 미실행. 자료 조건 문제이지 능력 반증이 아니다.
- 코드: research/의 approach/cross-image-target-use,
  checkpoint 752fba411759a093129c05feadfdff75e4d9a1b3.
  보존은 재사용 승인과 다르다. commit.json/code_review.json 및 CODE_ASSETS.md를 먼저 확인한다.
- 결과: research/results/iter_120/ 및 원 보고서가 가리키는 경로. 삭제·덮어쓰기하지 않는다.
- 당시 초점 원문: agent/interventions/archives/20261013_mrrate_switch/RESEARCH_FOCUS.md.
- 이보다 앞선 위치학습/판독·초안 교정·CURE 관찰은 RESEARCH_HISTORY_INDEX.md의 원 리뷰로 이어진다.

## 나중에 재개할 때

사용자가 이 방향 재검토를 요청하면 새 순번에서 RESUME.md로 전환한다. 120을 다시 실행하거나 번호를 되돌리지 않는다.
위 원문·현재 코드 보관 상태·보류 이후 새 근거를 읽고, 필요한 공개 관계 정답을 실제로 확보할 수 있는지,
강한 단순 대조 이후에도 중요한 질문인지 먼저 선택한다. 기존 Task3 집계는 반복하지 않는다.
현재 MRI 연구에서 관련 근거를 얻더라도 자동 복귀하지 않으며 사용자에게 연결 가능성을 보고한다.
이 문서는 원 판단을 대체하는 새 과학적 결론이 아니라 재개 안내다.
