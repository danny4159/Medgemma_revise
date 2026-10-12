# 외부 MRI 경로 접근 복구

승인된 /home/test/.local/share/medgemma/mr_rate는 실제 Claude CLI의 추가 작업 디렉터리에 반영됐다.
동일 설정의 Claude Bash/Read/Write 실측과 permission_denials=0을 확인했다.
근거: logs/claude_mrrate_access_20261013.jsonl, 현재 agent/claude_settings.json, orchestrator.py의 claude_command.
원자료·캐시·보호 경로는 보존한다. permission 우회를 쓰지 않는다.
같은 접근 감사를 한 iteration 전체로 반복하지 말고 기존 자료와 미완료 비교부터 진행한다.
이 복구는 연구 가설 검증이 아니며 모델·데이터·metric·판정 기준을 바꾸는 지시도 아니다.
