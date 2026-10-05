"""Codex read-only transport와 별도 Telegram. 연구 실행 흐름은 import하지 않는다."""
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import tempfile
import time

from codex_engineer import Stream, summarize_stream
from notifier import Human, load_env


def now():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
        temporary = Path(handle.name)
    os.replace(temporary, path)


def read_json(path, default=None):
    return json.loads(path.read_text()) if path.exists() else default


@contextmanager
def lock(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError("탐색기가 이미 실행 중입니다") from None
        yield


def codex_environment():
    env = os.environ.copy()
    executable = shutil.which("codex")
    if not executable:
        candidates = []
        if env.get("NVM_BIN"):
            candidates.append(Path(env["NVM_BIN"]) / "codex")
        folder = Path(env.get("NVM_DIR", str(Path.home() / ".nvm"))) / "versions/node"
        candidates += sorted(folder.glob("v*/bin/codex"),
                             key=lambda p: tuple(map(int, re.findall(r"\d+", p.parent.parent.name))), reverse=True)
        executable = next((str(p) for p in candidates if os.access(p, os.X_OK)), None)
    if not executable:
        raise RuntimeError("Codex CLI 경로를 찾지 못했습니다. 설치·계정 변경은 하지 않습니다")
    env["PATH"] = str(Path(executable).parent) + os.pathsep + env.get("PATH", "")
    for name in ("OPENAI_API_KEY", "CODEX_API_KEY"):
        env.pop(name, None)
    env["CUDA_VISIBLE_DEVICES"] = ""
    return executable, env


def command(executable, workspace, output, schema):
    cmd = [executable, "exec", "--ignore-user-config", "--skip-git-repo-check", "--json",
           "-C", str(workspace), "-s", "read-only", "-m", "gpt-6-astra",
           "-c", 'model_reasoning_effort="high"', "-c", 'web_search="live"',
           "-c", 'approval_policy="never"', "-c", 'forced_login_method="chatgpt"',
           "-c", "project_doc_max_bytes=0", "-c", "allow_login_shell=false"]
    for feature in ("shell_tool", "unified_exec", "shell_snapshot", "multi_agent", "multi_agent_v2",
                    "apps", "computer_use", "browser_use", "hooks", "skill_search",
                    "skill_mcp_dependency_install"):
        cmd += ["-c", f"features.{feature}=false"]
    return cmd + ["--output-schema", str(schema), "-o", str(output), "-"]


class CallError(RuntimeError):
    def __init__(self, kind, message):
        super().__init__(message)
        self.kind = kind


def classify_error(text):
    text = text.lower()
    if re.search(r"monthly spend|insufficient_quota|billing|invalid.api.key|unauthorized|not authenticated|401", text):
        return "blocked"
    if re.search(r"usage limit|rate.limit|weekly limit|quota|429|limit reached|try again.*(?:at|in)", text):
        return "limit"
    if re.search(r"reconnecting|connection|timed out|timeout|temporar|502|503|504|overloaded", text):
        return "transient"
    return "error"


def terminate(proc):
    if proc.poll() is None:
        os.killpg(proc.pid, signal.SIGTERM)
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.wait()


class Codex:
    def __init__(self, root, timeout=2400, max_wait=28800, retry_seconds=1800, inform=print):
        self.root, self.timeout, self.max_wait = root, timeout, max_wait
        self.retry_seconds, self.inform = retry_seconds, inform

    def preflight(self):
        exe, env = codex_environment()
        result = subprocess.run([exe, "--version"], env=env, capture_output=True, text=True, timeout=15)
        if result.returncode:
            raise RuntimeError("Codex CLI 실행 불가: Node/PATH를 확인하세요")
        return result.stdout.strip()

    def call(self, folder, prompt, schema):
        folder.mkdir(parents=True, exist_ok=True)
        # 재개 시 성공한 호출은 다시 결제/호출하지 않는다. 미완료 원본도 덮어쓰지 않는다.
        cached = folder / "answer.json"
        if cached.exists():
            return read_json(cached)
        if not (folder / "prompt.txt").exists():
            save(folder / "prompt.txt", prompt)
            save(folder / "schema.json", schema)
        prompt = (folder / "prompt.txt").read_text()
        started, transient = time.monotonic(), 0
        while True:
            attempt = len(list(folder.glob("attempt_*"))) + 1
            attempt_dir = folder / f"attempt_{attempt:03d}"
            attempt_dir.mkdir()
            try:
                answer = self._once(attempt_dir, folder, prompt)
                save(cached, answer)
                if attempt > 1:
                    self.inform("▶ 연구 탐색 | 호출 재개 성공")
                return answer
            except CallError as exc:
                save(attempt_dir / "failure.json", {"kind": exc.kind, "time": now()})
                if exc.kind not in {"limit", "transient"}:
                    raise
                if (self.root / "STOP").exists():
                    raise InterruptedError("정지 요청: 새 재시도 대기는 시작하지 않습니다")
                transient += exc.kind == "transient"
                if transient > 3 or time.monotonic() - started >= self.max_wait:
                    raise
                delay = min(self.retry_seconds if exc.kind == "limit" else 60 * transient,
                            self.max_wait - (time.monotonic() - started))
                retry_at = datetime.fromtimestamp(time.time() + delay, timezone.utc).astimezone().isoformat()
                save(self.root / "status.json", {"state": "waiting", "kind": exc.kind, "retry_at": retry_at,
                                               "call": str(folder), "time": now()})
                self.inform(f"⏳ 연구 탐색 | {'사용 한도' if exc.kind == 'limit' else '일시 통신 오류'}\n"
                            f"다음 확인: {retry_at}. 초기화 시각이 아닌 재시도 예정입니다.")
                deadline = time.monotonic() + delay
                while time.monotonic() < deadline:
                    if (self.root / "STOP").exists():
                        raise InterruptedError("대기 중 정지 요청")
                    time.sleep(min(1, max(0, deadline - time.monotonic())))

    def _once(self, attempt, folder, prompt):
        exe, env = codex_environment()
        output = attempt / "final.json"
        log = attempt / "stream.jsonl"
        # 기존 저장소/사용자 AGENTS와 완전히 분리된 실행 디렉터리. 웹 이외 실행 도구 비활성화.
        with tempfile.TemporaryDirectory(prefix="medical-literature-") as workspace:
            cmd = command(exe, Path(workspace), output.resolve(), (folder / "schema.json").resolve())
            save(attempt / "invocation.json", {"command": cmd, "started_at": now()})
            with (folder / "prompt.txt").open() as source, log.open("w") as target:
                proc = subprocess.Popen(cmd, stdin=source, stdout=target, stderr=subprocess.STDOUT,
                                        env=env, start_new_session=True, cwd=workspace)
                started = time.monotonic()
                try:
                    while proc.poll() is None:
                        if self.timeout and time.monotonic() - started > self.timeout:
                            terminate(proc)
                            raise CallError("transient", "Codex 호출 시간 초과")
                        time.sleep(0.2)
                except BaseException:
                    terminate(proc)
                    raise
        stream = Stream()
        web_actions = []
        for line in log.read_text(errors="replace").splitlines():
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if isinstance(event, dict):
                stream.feed(event)
                item = event.get("item") or {}
                if event.get("type") == "item.completed" and item.get("type") == "web_search":
                    web_actions.append({"action": item.get("action"), "query": item.get("query"),
                                        "results": item.get("results", [])})
        save(attempt / "usage.json", summarize_stream(log))
        save(attempt / "web_activity.json", web_actions)
        if proc.returncode or not stream.completed or not output.exists():
            text = stream.error or log.read_text(errors="replace")[-8000:]
            raise CallError(classify_error(text), f"Codex 호출 실패. 원문: {log}")
        if not web_actions:
            raise CallError("error", f"실제 웹 검색 기록 없이 종료했습니다. 근거 검토 필요: {log}")
        try:
            return read_json(output)
        except (ValueError, OSError):
            raise CallError("error", f"Codex 최종 JSON 오류: {output}") from None


def separate_telegram(env_path, old_env):
    if not env_path.exists():
        return None
    new = load_env(env_path)
    token, chat = new.get("TELEGRAM_BOT_TOKEN"), new.get("TELEGRAM_CHAT_ID")
    if not token or not chat:
        raise ValueError("새 Telegram 설정이 불완전합니다. 없으면 .notify.env 파일을 만들지 마세요")
    if token == load_env(old_env).get("TELEGRAM_BOT_TOKEN"):
        raise ValueError("기존 MedGemma 봇과 같은 토큰입니다. 별도 봇을 사용하세요")
    return env_path


class Channel:
    def __init__(self, root, env_path=None):
        self.root = root
        self.human = Human(env_path) if env_path else None

    def send(self, key, message):
        path = self.root / "outbox" / f"{key}.json"
        if not path.exists():
            save(path, {"message": message, "delivered": False, "created_at": now()})
            print(message, flush=True)
        self.flush()

    def flush(self):
        if not self.human or not self.human.telegram:
            return
        for path in sorted((self.root / "outbox").glob("*.json")):
            record = read_json(path)
            if record["delivered"]:
                continue
            try:
                result = self.human._api("sendMessage", {"chat_id": self.human.chat_id,
                                                         "text": record["message"][:3500]})
                if not result.get("ok"):
                    raise RuntimeError("sendMessage rejected")
            except Exception as exc:
                print(f"[알림 보류] {type(exc).__name__} — outbox 보존", flush=True)
                break
            record.update(delivered=True, delivered_at=now())
            save(path, record)

    def commands(self, status, stop):
        if self.human:
            self.human.add_command(["status", "상태"], status)
            self.human.add_command(["stop", "정지"], stop)
