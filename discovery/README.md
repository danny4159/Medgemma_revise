# 의료 AI 연구 문제 탐색기

기존 `orchestrator.py`와 독립된 문헌·산업 수요 탐색기다. 기존 GOAL·실험·branch·Telegram을 변경하지 않는다.
모든 연구 호출은 `gpt-6-astra/high`와 live web search다. 연구 코드 구현·GPU 실험은 하지 않는다.
후보 추천은 **문헌상 유망**을 뜻하며 효과·임상 안전성·학회 채택을 보장하지 않는다.

## 실행

프로젝트 루트에서:

```bash
python discovery_orchestrator.py --check
python discovery_orchestrator.py --status
python discovery_orchestrator.py --run --max-rounds 1  # 초기 한 회차 확인
python discovery_orchestrator.py --run                 # 이후 지속 탐색
python discovery_orchestrator.py --stop                # 현재 회차·심사·저장 후 정지
python discovery_orchestrator.py --run --resume        # 정지/보류 해제 후 재개
```

기본 실행은 조회만 한다. 실제 모델 호출에는 `--run`이 필요하다. `--max-rounds 0`은 무제한이다.
Ctrl+C/SIGTERM은 진행 중 호출을 종료하고 원본 로그를 보존한다. 완료된 호출은 재개 시 다시 실행하지 않는다.
한도는 기본 30분마다 최대 8시간 확인한다. 이는 초기화 시각의 추정이 아니다. 결제·인증 오류나
명확하지 않은 오류는 자동 결제/권한 확대 없이 멈춘다. `--limit-poll-minutes`, `--limit-wait-hours`로 조절한다.
통신 오류는 최대 3회 재시도하며, 호출 timeout 기본 2400초다. 한도 대기 중 `--stop`은 조기 종료한다.
새 근거/판단 변화가 없는 3회 연속 결과는 비용 안전장치로 보류한다. 과학적 기각이나 영구 종료가 아니다.

## 흐름과 기록

탐색 질문 → 원문·수요·반론 조사 → 후보 갱신 → 추천 요청이 있을 때만 별도 fresh 심사 → 저장/알림.
추천 뒤에는 다른 후보를 조사한다. 매 회차 next_question과 선택 이유가 다음 입력으로 전달된다.
새로운 근거가 없는 보류/제외 후보의 이름 바꾸기 재탐색을 막는다.

- `GOAL.md`: 독립된 목표
- `POLICY.md`, `prompts/`: 근거·추천·반론·질문 연속성 기준
- `runtime/INDEX.md`: 후보 전체 요약
- `runtime/candidates/<id>.md`: 후보별 상세 근거와 최근 심사
- `runtime/rounds/round_NNNN/research.md`, `review.md`: 회차별 조사·심사
- `runtime/rounds/round_NNNN/done.json`: 완료 원장. 이를 재생해 색인과 상태를 복원
- `runtime/rounds/.../explore|critic/`: prompt, schema, 응답, 시도별 stream/usage. 덮어쓰지 않음
- `runtime/outbox/`: 미전송/전송 알림. 통신 실패는 다음 전송/재개에서 다시 시도

`runtime/`은 자동 Git 제외다. 로컬 결과는 남지만 push가 결과 백업은 아니다. 필요 시 보고서만 검토 후
선별 커밋한다. CLI stream은 세션·검색 근거·사용량 감사용이며 내부 사고 전문의 과학적 증명이 아니다.
동일 problem_key 중복은 기계적으로 검사하지만 의미상 중복은 모델의 색인 대조·심사가 필요하다.
출처 연결 검사는 사실성 검증을 대체하지 않는다. 원문 접근 불가/초록만 확인은 명시하고 추천을 보류한다.

## 별도 Telegram

기존 MedGemma 봇을 재사용하지 않는다. 설정 파일이 없으면 로컬 기록만 사용한다.
Telegram의 BotFather에서 새 봇(예: Medical AI Research Scout)을 만든 뒤 새 봇에 /start를 보낸다.
`.notify.env.example` 형식으로 `discovery/.notify.env`에 토큰과 목적지 chat id를 저장한다.
파일 권한은 `chmod 600 discovery/.notify.env`로 제한한다. 토큰을 채팅·Git에 붙여넣지 않는다.
기존 봇과 같은 토큰이면 탐색을 시작하기 전에 거부한다. 같은 개인 대화 수신자라도 새 봇이면 구분된다.

연결 후 명령은 `status`/`상태`, `stop`/`정지`다. 원격 재시작·셸 실행은 지원하지 않는다.
추천·추천 재검토·중단·오류·한도 대기/재개를 알리고 일상 진행은 3회차마다 묶는다.
전송 성공 직후 프로세스가 죽으면 재전송될 수 있으므로 완전한 exactly-once 전송을 보장하지 않는다.
이전 미전송 알림은 연결 후 순차 발송된다. `--no-telegram`은 알림/수신을 모두 끈다.

## 격리와 테스트

기존 호출 이벤트 판독(`codex_engineer.Stream`)과 Telegram 통신(`notifier.Human`)만 재사용한다.
기존 실험 루프/정책 프롬프트는 import하지 않는다. Codex는 임시 독립 cwd, 사용자 설정 무시,
프로젝트 AGENTS 읽기 비활성화, read-only, 셸/다중 에이전트/앱/컴퓨터 조작 비활성화로 실행한다.
저장된 ChatGPT CLI 인증만 사용하며 API 키 대체를 하지 않는다. 전역 설정은 바꾸지 않는다.

```bash
python -m unittest discover -s tests -p 'test_discovery.py'
```

공식 실행/설정 근거:
- https://learn.chatgpt.com/docs/non-interactive-mode
- https://learn.chatgpt.com/docs/config-file/config-reference
