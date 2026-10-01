"""Codex 구현 담당의 CLI 계약과 JSONL 사용량. 연구 판정은 orchestrator가 담당한다."""

import json


def command(spec, resume_id=None, sandbox="workspace-write"):
    # 호스트 실행 권한은 사용자 명시 선택으로만. 실패 시 자동 승격하지 않는다.
    if sandbox not in ("workspace-write", "danger-full-access"):
        raise ValueError(f"지원하지 않는 Codex 구현 sandbox: {sandbox}")
    cmd = ["codex", "exec"]
    if resume_id:
        cmd += ["resume", resume_id]
    cmd += [
        "--json", "-m", spec["model"],
        "--ignore-user-config",
        "-c", f'model_reasoning_effort="{spec["effort"]}"',
        "-c", "allow_login_shell=false",
        "-c", 'approval_policy="never"',
        "-c", 'web_search="live"',
    ]
    cmd += ["-c", f'sandbox_mode="{sandbox}"',
            "-c", "sandbox_workspace_write.writable_roots=[]",
            "-c", "sandbox_workspace_write.network_access=true"]
    return cmd + ["-"]


class Stream:
    """호출마다 새로 만든다. 실패한 turn의 중간 답변을 완료 보고서로 오인하지 않는다."""

    def __init__(self):
        self.session = None
        self.message = ""
        self.completed = False
        self.error = ""
        self.usage = {}
        self.permission_denials = []

    def feed(self, event):
        kind = event.get("type")
        if kind == "thread.started":
            self.session = event.get("thread_id")
        elif kind == "turn.started":
            self.message, self.error, self.completed = "", "", False
        elif kind == "item.completed":
            item = event.get("item", {})
            if item.get("type") == "agent_message":
                self.message = item.get("text", "")
            elif item.get("type") == "command_execution" and item.get("exit_code"):
                output = str(item.get("aggregated_output", "")).lower()
                if any(s in output for s in ("permission denied", "operation not permitted",
                                             "read-only file system", "sandbox denied")):
                    self.permission_denials.append({"tool_name": "command_execution",
                                                   "tool_input": {"command": item.get("command", "")}})
        elif kind == "turn.completed":
            self.completed = True
            self.usage = event.get("usage") or {}
        elif kind == "turn.failed":
            error = event.get("error") or {}
            self.error = error.get("message", str(error)) if isinstance(error, dict) else str(error)
            self.completed = False
        elif kind == "error":
            self.error = event.get("message", "Codex error")


def summarize_stream(path):
    sessions = {}
    session = None
    completed = 0
    unreported = 0
    failures = 0
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if not isinstance(event, dict):
            continue
        if event.get("type") == "thread.started" and event.get("thread_id"):
            session = event["thread_id"]
            sessions.setdefault(session, {})
        elif event.get("type") == "turn.completed":
            completed += 1
            if session is None or not event.get("usage"):
                unreported += 1
                continue
            # 설치된 CLI는 resume 후에도 세션 누적 usage를 출력한다 (실제 rollout과 대조).
            # turn.completed 이벤트 개수와 토큰 합계를 구분해 반복 집계를 막는다.
            usage = event["usage"]
            for key in ("input_tokens", "cached_input_tokens", "output_tokens"):
                sessions[session][key] = max(sessions[session].get(key, 0), usage.get(key, 0) or 0)
        elif event.get("type") == "turn.failed":
            failures += 1
    return {
        "source": str(path), "sessions": sessions, "completed_turns": completed,
        "failed_turns": failures, "unreported_turns": unreported,
        "usage": {k: sum(s.get(k, 0) for s in sessions.values())
                  for k in ("input_tokens", "cached_input_tokens", "output_tokens")},
        "accounting": "CLI 세션별 누적 usage 최댓값 합계. cached_input_tokens는 input_tokens의 부분집합. "
                      "실패·중단 turn 사용량은 미집계일 수 있으며 비용·구독 소진율이 아님",
    }


def usage_report(runs_dir):
    lines = ["# Codex 구현 사용량", "", "계획·리뷰와 별도 집계하며, 비용·구독 소진율이 아닙니다.",
             "세션별 누적 최댓값을 사용해 resume 반복 표시값의 중복 합산을 막습니다.",
             "실패·중단 turn은 미집계일 수 있습니다. 캐시 입력은 전체 입력에 포함됩니다.", "",
             "| 반복 | 완료 turn | 입력 | 캐시 입력 | 출력 | 실패 turn |",
             "|---|---:|---:|---:|---:|---:|"]
    sessions = {}
    for path in sorted(runs_dir.glob("iter_*/codex_engineer_stream.jsonl")):
        data = summarize_stream(path)
        u = data["usage"]
        lines.append(f"| {path.parent.name} | {data['completed_turns']} | {u['input_tokens']:,} | "
                     f"{u['cached_input_tokens']:,} | {u['output_tokens']:,} | {data['failed_turns']} |")
        for sid, usage in data["sessions"].items():
            current = sessions.setdefault(sid, {})
            for key, value in usage.items():
                current[key] = max(current.get(key, 0), value)
        if data["unreported_turns"]:
            lines.append(f"\n{path.parent.name}: 세션 ID/usage 미기록 {data['unreported_turns']}건")
    totals = {k: sum(s.get(k, 0) for s in sessions.values())
              for k in ("input_tokens", "cached_input_tokens", "output_tokens")}
    lines += ["", f"세션 중복 제거 합계: 입력 {totals['input_tokens']:,} / "
              f"캐시 입력 {totals['cached_input_tokens']:,} / 출력 {totals['output_tokens']:,}"]
    return "\n".join(lines)
