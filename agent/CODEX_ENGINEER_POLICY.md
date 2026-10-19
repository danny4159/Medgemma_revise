# Codex 구현 담당 운영

- Claude를 대체하는 것은 구현·실험·자체 검증 역할 전체다. GPT 계획/리뷰는 독립 호출로 유지한다.
- 초기 권한은 workspace-write다. 이 서버에서 해당 sandbox의 NVIDIA 접근 실패와 device
  개별 허용 시 CLI 초기화 결함을 확인했다. GPU 실험은 사용자가
  `--codex-engineer-sandbox danger-full-access`를 명시한 경우에만 호스트 권한으로 실행한다.
  실패 시 자동 권한 확대·CPU-only 대체를 하지 않는다. 계획/리뷰는 계속 read-only다.
  호스트 실행에서는 research/ 외 쓰기 금지가 OS 강제가 아니라 작업 정책이라는 점을 구분한다.
  공통 연구 범위·Git 관리·다른 사용자 프로세스 보호·기본 환경 보존 기준은 변하지 않는다.
- 저장된 CLI 인증은 사용하되 사용자 config는 무시하고 이 호출의 모델·권한을 명시한다.
  shell login은 꺼서 medgemma Python PATH가 기본 Anaconda로 바뀌지 않게 한다.
- 작업 등급은 호환성을 위해 plan.json의 claude_tier를 그대로 사용한다.
  실제 모델은 agent/tiers.json의 codex_engineer 항목이다. 사용자 조정으로
  standard/light는 gpt-6.1-sol / high reasoning effort를 사용한다.
  heavy는 gpt-6-astra / low, creative는 gpt-6-astra / medium을 유지한다.
  GPT 계획·리뷰와 Claude 설정은 변경하지 않는다. 실행 중인 호출은 유지하고 다음 호출부터 적용한다.
- 관련 파일·변경점부터 확인하고 전체 기록 재독해와 중복 구현을 줄인다. 필요한 원문·검증은
  생략하지 않는다. GPU 활용·표본·seed·검증 기준은 기존 연구/자원 정책 그대로다.
- 장시간 작업은 공통 구현 프롬프트의 대기 규칙을 따른다. 프로그램이 작업을 감시하며 초기 확인 후
  기본 10분 대기 묶음을 사용한다. `experiment_wait.py` 또는 동등한 completion 대기를 사용하고
  같은 update 수 조회 명령을 반복 호출하지 않는다. 완료·오류·사전 판단 경계에서 모델이 검토한다.
- 구현용 세션 ID와 JSONL은 계획/리뷰와 분리한다. 한도·일시 오류는 같은 구현 세션으로
  재시도하고 기존 코드·부분 결과·checkpoint를 재사용한다. 자동 유료 API 전환은 하지 않는다.
- 진행 중인 구현의 backend는 고정한다. 담당만 바꿀 때는 완료 후 선택하거나 정상 중단·보존 뒤
  --handoff-engineer로 같은 반복을 인계한다. --replan으로 반복을 건너뛰지 않는다.
  사용자가 --engineer-fallback codex를 켠 경우 Claude 구독 소진 때 소유 실험 종료를 확인하고
  같은 반복을 자동 인계한다. 새 담당은 원 로그·checkpoint·남은 작업을 확인하며 중복 실행하지 않는다.
- `--engineer-return-at`과 `--engineer-return-to`로 한시적 담당 선택을 저장할 수 있다.
  예약 시각 이후 새로 시작하는 반복부터 복귀하며, 계획을 이미 시작한 반복도 기존 선택을 유지한다.
  시간 경과만으로 실행 중인 구현·실험을 종료하지 않는다. GPT 계획/리뷰·모델 등급은 바꾸지 않는다.
- 이전 기록·리뷰·자동화와의 호환을 위해 claude_report.md, claude_meta.json,
  claude_result.raw.json 및 claude_tier 필드명은 공통 구현 산출물로 유지한다.
  실제 담당은 engineer_backend.json 및 meta의 backend에 기록한다. 파일명으로 모델을 추정하지 않는다.
- --usage는 Codex 구현의 세션별 누적 입력·캐시 입력·출력을 따로 표시한다.
  설치된 CLI의 resume 출력은 누적값이므로 같은 세션의 최댓값만 반영한다.
  실패/중단 호출의 사용량은 미집계일 수 있다. 토큰을 구독 소진율로 환산하지 않는다.
