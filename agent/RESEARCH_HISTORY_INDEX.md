# 연구 이력·보류 질문 색인

2026-10-13, iter_120 종료 후 MR-RATE 전환 기준의 조회 안내다. 자동 실행 목록·유망 후보 순위가 아니다.
현재 초점은 RESEARCH_FOCUS.md, 누적 최신 상태는 INDEX.md/LIMITATIONS.md와 해당 원 review.json을 확인한다.
이 색인과 이후 리뷰가 다르면 이후 원 기록을 우선한다. 관련 질문의 원문만 읽는다.

| 질문/자산 | 현재 읽을 근거 | 유지할 판단·재개 조건 |
|---|---|---|
| 영상 간 대상 정보 전달 | runs/iter_120/review.md, runs/iter_021/review.md, PAUSED_GROUNDING_TRACK.md | 사용자 우선순위로 보류·재개 가능. 관계쌍 0으로 모델 미실행. MRI 탐색 중 자동 복귀하지 않음 |
| 초안 내용의 영향·선택적 보존 | runs/iter_117/review.md, runs/iter_118/review.md, runs/iter_119/review.md | 합성 손상 관찰 보존. 자연 초안의 방법 필요성 부족으로 보류; 새 잔여 조건·개입 근거 필요 |
| CURE–grounder 불일치로 오류 검토 | runs/iter_113/review.md, runs/iter_114/review.md, runs/iter_115/review.md | 추가 가치 불확정·주석 민감성. 같은 점수/자료 순회 보류 |
| 공개 주석 기반 부분 누락 | runs/iter_105/review.md, runs/iter_107/review.md, runs/iter_110/review.md | 지원 조건의 대안 성공과 의미 평가 한계 보존; 정답이 구분하는 새 조건 없이 재개하지 않음 |
| 위치 학습→판독 전이 | runs/iter_092/review.md, runs/iter_097/review.md | 현재 적응 baseline 미달; 위치 학습 일반 무용성은 미판정. LR/seed 순회가 아닌 판별력 있는 설계 필요 |
| 공동 grounding·직접 SFT | runs/iter_041/review.md, runs/iter_046/review.md, runs/iter_048/review.md | 직접 적응 회복·강한 grounder 대안 계승. 형식 미학습을 일반 결합 실패로 주장하지 않음 |
| 초기 RSNA 위치 SFT 자산 | runs/iter_012/review.md, CODE_ASSETS.md | 위치 출력 개선 자산 보존; 판독 개선의 증명과 구분 |
| MRI 대상/문맥 질문 | runs/iter_064/review.md, runs/iter_083/review.md | 특정 입력·자료 연결의 한계. 과제별 반대 근거를 읽고 MRI 전체의 기각으로 확대하지 않음 |
| MRI key-image·타 계열 대조 | runs/iter_061/review.md, runs/iter_062/review.md | Qwen 비교도 불확정. 기본 인식·관측 충분성을 분리하지 못한 설계 한계를 새 MRI 설계에 반영 |
| MRI 부위 판독·참고영상 | runs/iter_077/review.md, runs/iter_078/review.md | SPIDER 분류기 대비 이점 미확보. MR-RATE의 같은 결과를 미리 가정하지 않으며 이전 학습을 자동 반복하지 않음 |
| MRI 자동 변화 근거 | runs/iter_079/review.md | LUMIERE 비교 검사/명시적 음성 연결 실패. 자료 부적합이지 MRI 인식 실패가 아님 |

## 보완 이력 원문

- 2026-10-13 구조 정리 직전 원문과 SHA256: interventions/archives/20261013_policy_consolidation/MANIFEST.json
- 같은 폴더의 RESEARCH_POLICY.md, RESEARCH_FOCUS.md, prompts/는 당시 지시 원문이다.
- 초기 초점 변경 원문: interventions/archives/RESEARCH_FOCUS_before_20261006_grounding_report.md
- 반복별 실제 계획·승인·출력·리뷰: runs/iter_NNN/; 전체 흐름: JOURNEY.md, INDEX.md, DECISIONS.md.
- 보관된 원문의 '현재 iter', '다음에 실행', 'CPU만'은 당시 적용 범위다. 새 계획의 자동 명령으로 사용하지 않는다.
