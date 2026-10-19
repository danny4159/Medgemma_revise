# 중단 → 점검 → 보완 → 재개

## 보완 없이 이어가기

orchestrator를 중단한 후 같은 명령으로 실행하면 미완료 단계부터 이어간다.
Claude 구현 중 중단됐다면 기존 세션을 재개한다. --reset은 필요하지 않다.

## 보완 내용을 반영해 GPT부터 다시 계획하기

### 장시간 iteration 도중 구현 담당 인계

사용자가 담당 변경을 승인하면 전체 iteration 종료까지 기다릴 필요는 없다. 소유 작업의 정상 중단
지원 여부를 먼저 확인하고 checkpoint(adapter·optimizer·RNG·다음 batch·pending validation)를 저장한다.
실험 프로세스가 종료되고 checkpoint digest가 확인된 뒤 관리 프로세스를 중단한다. 임의 프로세스 그룹이나
다른 사용자 작업은 건드리지 않는다. 저장 기능이 없으면 마지막 검증된 checkpoint와 손실 범위를 먼저 확인한다.

담당만 변경할 때 `--replan`을 쓰지 않는다. 아래처럼 원 계획·코드 SHA·부분 결과·미완료 작업을 전달한다.

```bash
python orchestrator.py --handoff-engineer claude --handoff-note "실험 종료 확인; checkpoint 경로·코드 SHA·남은 작업" --prepare-only
python orchestrator.py --gpus 0,1
```

**같은 반복 번호**를 유지한다. 이전 backend·세션·응답은 `iter_NNN/engineer_handoffs/<id>/`에
보관하고 현재 backend만 전환한다. 전체 실행 로그·원 계획·연구 코드·결과 경로는 그대로 남는다.
새 담당은 새 세션으로 기록을 확인한다. 중간에 인계 준비가 끊겨도 다음 실행에서 같은 전환을 마무리한다.
이 옵션은 실험 프로세스를 중단하거나 학습 checkpoint를 생성하지 않는다. 사전 종료 확인이 필수다.
완성된 구현 보고서가 있으면 인계하지 않고 해당 결과를 리뷰한다. 연구 질문/계획을 바꿀 때만 --replan을 쓴다.
새 구현자는 가능한 경우 원 경로의 append-only 재개를 사용하고 기존 checkpoint·출력은 보존한다.
새로 학습을 시작하거나 기완료 검증을 전부 반복하지 않는다. 필요 시 새 산출물 경로에 원 출처를 연결한다.

### Claude 구독 한도에서 자동 Codex 인계 (선택)

`--engineer claude --engineer-fallback codex`로 켠다. 기본은 none이며 선택은 저장된다.
5시간·주간 등 구독 소진이 확인되면 같은 iteration에서 코드·세션을 보존하고 Codex로 미완료 작업을 이어간다.
호출에서 상속한 소유 표식으로 잔존 실험을 확인하고 살아 있으면 종료를 기다린다. 작업을 강제 종료하거나
중복 실행하지 않는다. 진행 중 실험이 멈추지 않으면 status/stop으로 사람이 개입할 수 있다.
인계와 후속 담당은 기록되고 Telegram으로 알린다. 이후에도 Codex이며 자동 Claude 복귀는 설정하지 않는다.
`--engineer-fallback none`으로 끌 수 있다. 일반 서버 혼잡·네트워크·인증 오류·월간 지출 한도는 인계로 우회하지 않는다.
Codex 자체 소진은 기존 대기/재시도 정책을 따른다. 모델 등급·실험 기준·유료 API 설정은 바꾸지 않는다.

### 반복 종료 후 다음 방향 승인 (선택)

`python orchestrator.py --gpus 0,1 --confirm-each-iter`로 켠다. 기본은 기존 자동 진행이다.
이번 리뷰가 끝나면 Telegram으로 결과·한계·추천 후속·선택지를 보내고 다음 계획 전에 대기한다.
`ok`는 추천대로, `f 피드백`은 다음 GPT 계획에 우선 반영, `q`는 결과를 보존하고 정지한다.
승인 대기 중에는 done.json/다음 iter를 만들지 않는다. 승인/피드백은 해당 반복의
next_iteration_decision.json에 보존되며 같은 리뷰는 재승인하지 않는다.
--auto/부재 설정으로 확인을 생략하지 않는다. 기존에 요청한 확인은 재시작 때 옵션을 빼도 유지한다.
매회 확인을 계속하려면 새 실행에도 옵션을 붙인다. DONE은 다음 반복 없이 종료한다.

### 연구 방향/계획 자체를 보완하기

1. 터미널 Ctrl+C 또는 기존 stop 기능으로 중단하고 프로세스 종료를 확인한다.
   STOP 파일/Telegram stop은 현재 단계가 끝난 뒤 정지할 수 있으므로 즉시 종료와 구분한다.
2. `agent/RESUME.md`에 보완 지시를 작성한다. `RESUME_TEMPLATE.md`를 참고한다.
   비어 있는 RESUME.md는 오류로 처리하므로 대기용 빈 파일을 만들지 않는다.
3. 아래 명령으로 상태 전환만 준비하고 검토할 수 있다. 에이전트·GPU 실험·알림은 실행하지 않는다.

```bash
python orchestrator.py --prepare-only
python orchestrator.py --status
```

4. 준비 내용을 확인한 뒤 평소의 GPU·autonomy·timeout 옵션으로 실행한다.

```bash
python orchestrator.py --gpus 0,1
```

짧은 지시는 파일 대신 아래처럼 전달할 수도 있다. 대기 중인 RESUME.md가 있으면 덮어쓰지 않고 거부한다.

```bash
python orchestrator.py --replan "현재 목표와 코드는 유지하고, 새 방법 개발 전에 공식 사용 조건에서 성능 문제부터 검증해줘." --prepare-only
```

`--prepare-only`를 빼면 전환 후 바로 연구 루프를 실행한다. `--status`는 조회 전용이다.
--replan/--prepare-only는 --goal/--reset과 함께 쓰지 않는다.
계획 확인 화면에서는 `p 보완 지시`로 같은 재계획을 요청할 수 있다.
`f 지시`는 기존 계획을 유지한 채 Claude에게 보충하는 기능이므로 연구 방향 변경에는 p를 쓴다.

## 보존과 적용 방식

- 미완료 iter_NNN에 plan/세션/보고서 등 기록이 있으면 이를 그대로 두고 superseded.json을 추가한다.
  새 반복 번호에서 GPT가 새로 계획하고 Claude는 새 세션으로 시작한다. 이전 반복은 실패나 DONE이 아니다.
- 완료된 반복은 바꾸지 않는다. 아직 시작하지 않은 반복이면 그 번호에서 계획한다.
- 연구 작업 트리와 결과를 전환 준비 단계에서 수정하지 않는다. 새 계획이 선택한 접근법으로 브랜치를
  옮길 때 기존 코드 보존 정책을 적용한다. results/는 기존 경로에 남고 새 실험은 새 반복 경로를 쓴다.
- 요청 원문과 transaction은 agent/interventions/<id>/, 적용 표시는 새 반복의 intervention.json에 남는다.
  RESUME.md는 적용 후 이력 폴더로 이동한다. 새 보완 때는 새 RESUME.md를 작성한다.
- 적용 도중 중단돼도 같은 transaction을 마무리한다. 반복 번호를 다시 늘리거나 원본을 덮어쓰지 않는다.
- 여러 새 버전 orchestrator의 동시 실행은 lock으로 막는다. 이 기능 도입 전에 켠 프로세스에는
  lock이 없으므로 최초 전환 전에는 직접 종료 여부를 확인해야 한다.
- 실행 중 파일을 전달했다면 진행 중 에이전트를 강제 종료하지 않고 다음 단계 경계에서 반영한다.
  코드/정책 수정까지 한다면 먼저 중단하는 방식이 권장된다. prepare-only를 동시에 실행하면 거부된다.
- 새 보완 지시는 GPT 계획·Claude 구현·GPT 리뷰에 모두 전달되고 같은 목표의 후속 반복에도 참조된다.
  이미 끝낸 일회성 검증은 다시 수행하지 않는다. 목표를 바꾸면 이전 지시는 자동 적용하지 않는다.

## 공통 원칙·현재 질문·과거 지시의 구분

- `RESEARCH_POLICY.md`에는 반복해서 적용할 원칙, `RESEARCH_FOCUS.md`에는 현재 질문·범위만 둔다.
  완료된 반복의 일회성 지시를 두 문서에 계속 누적하지 않는다.
- 관련 원문은 `RESEARCH_HISTORY_INDEX.md`로 찾아 읽는다. 과거 정책·초점 원문은
  `interventions/archives/20261013_policy_consolidation/`에 해시와 함께 보존돼 있다.
  이력은 판단 근거이지 옛 실험을 다시 실행하라는 명령이 아니다.
- 다음 계획·리뷰는 기존 Strategy Check에서 중요한 문제 / 현재 근거 / 쉬운 해결책 /
  남은 설명 / 다음 결정을 이어받는다. 이후 승인·원 계획·최신 리뷰가 날짜 있는 초점 카드보다 우선한다.
- 공통 문서는 다음 모델 호출 때 다시 읽는다. 이미 저장된 계획·판정은 자동 재작성하지 않는다.
  계획 변경이 필요하면 위 보완 절차를 사용한다. 보완 적용만으로 실행하거나 반복 승인을 우회하지 않는다.

## 한계 검증 → 방법 개발

LIMITATIONS.md는 초기 LIMITATIONS.json과 review.json의 limitation_updates를 합성한 목록이다.
candidate/observed를 validated로 자동 승격하지 않는다. GPT 리뷰가 실제 출력의 독립 평가,
사용법·평가 검증과 오류 범위를 근거로 갱신하며 원본 리뷰에 이력이 남는다.

method full/confirmatory 계획은 현재 목표에서 validated인 limitation_ids를 지정해야 한다.
method pilot은 RESEARCH_POLICY의 최소 방법 실험 기준(이전 유효한 실험 리뷰·사용법 검사·blocking 없는
observed/validated 근거와 명시적 decision_contract)을 따른다. 본격 확대는 별도 리뷰·계획이 필요하다.
없으면 --auto에서도 구현 전에 중단한다. --replan으로 diagnostic 계획을 요청한다.
이 검사는 GPT 판단의 과학적 정확성을 보장하지는 않으며, 근거 없는 단계 진입을 막는 제어다.
CPU 준비·문헌 검색·head probe만으로 실제 MedGemma 한계를 검증했다고 판단하지 않는다.
