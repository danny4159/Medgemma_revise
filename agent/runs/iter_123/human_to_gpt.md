# 사용자 승인 운영 복구 — 2026-10-13

사용자가 "claude도 접근할수있게해서 다시" 진행하도록 요청했다.
관리 코드에서 agent/claude_settings.json의 permissions.additionalDirectories에
/home/test/.local/share/medgemma/mr_rate 하나만 추가했고, run_claude의 실제 신규/재개 명령에도
동일 목록을 --add-dir로 전달하도록 수정했다. 프로젝트 보호 경로·다른 사용자 작업 제한은 그대로다.

실제 동일 Claude 실행 설정으로 Bash(ls), Read(splits.csv 첫 줄), Write(전용 probe 파일)가 모두 성공했다.
permission_denials는 0이다. 생성 파일은 운영자가 별도 읽어 확인한다. Claude의 재읽기 단계는 생략됐으므로
그 단계까지 수행됐다고 주장하지 않는다. 근거: logs/claude_mrrate_access_20261013.jsonl.
관련 신규·재개·권한·fallback 회귀 테스트 42개가 통과했다.

123 번호에서 이어간다. 122의 계획·원 보고서·미실행 판정은 수정하지 않는다.
새 연구 방향이나 질환 탐색 대신 iter_122/plan.md의 미완료 비교를 기준으로 필요한 부분만 재계획한다.
추가 경로 허용을 다시 사용자에게 요청하거나 권한 조회만으로 iteration을 끝내지 않는다.
자료가 성립하면 원 계획의 기술6명·조건부 탐색48명·독립 리뷰까지 이어간다.
목표·질환·입력 비교·정답 규칙·평가·확대/중단 조건을 운영 오류 때문에 변경하지 않는다.
Claude 구현, 구독 소진 시 Codex 인계, 자동 반복·필수 리뷰 설정은 유지한다.
