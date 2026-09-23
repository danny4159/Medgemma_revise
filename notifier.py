"""사람 입력/알림 채널: 터미널 + Telegram 봇.

- notify(text): Telegram으로 알림만 보낸다.
- ask(question, telegram_text): 터미널 입력과 Telegram 답장 중 먼저 온 것을 돌려준다.
- add_command(names, handler): 질문과 상관없이 언제든 받는 Telegram 명령 (예: status, stop).

agent/.notify.env 에 TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID가 있으면 Telegram을 쓰고,
없으면 터미널만 쓴다. 설정된 chat 외의 메시지는 무시한다.
Telegram 오류는 연구 루프를 멈추지 않도록 경고만 출력한다.
"""

from pathlib import Path
import json
import queue
import sys
import threading
import time
import urllib.parse
import urllib.request

MAX_TEXT = 3500  # Telegram 메시지 한도 4096자보다 여유 있게
POLL_SECONDS = 25


def load_env(path):
    values = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            key, sep, value = line.partition("=")
            if sep and not key.strip().startswith("#"):
                values[key.strip()] = value.strip()
    return values


class Human:
    def __init__(self, env_file=None):
        """env_file이 None이면 Telegram 없이 터미널만 쓴다."""
        env = load_env(Path(env_file)) if env_file else {}
        self.token = env.get("TELEGRAM_BOT_TOKEN")
        self.chat_id = env.get("TELEGRAM_CHAT_ID")
        self.telegram = bool(self.token and self.chat_id)
        self.offset = None
        self.warned = False

        # 터미널과 Telegram 입력을 각각 스레드가 계속 받아 inbox 하나에 넣는다.
        # 질문마다 input() 스레드를 새로 만들면, Telegram이 먼저 답했을 때
        # 남은 스레드가 다음 터미널 입력을 가로챈다.
        self.inbox = queue.Queue()
        self.waiting = threading.Event()
        self.commands = {}
        self.stdin_open = True
        threading.Thread(target=self._read_stdin, daemon=True).start()

        if self.telegram:
            self._skip_old_updates()
            threading.Thread(target=self._poll_telegram, daemon=True).start()

    # ---------------- 입력 스레드 ----------------

    def _read_stdin(self):
        for line in sys.stdin:
            self.inbox.put(("terminal", line.rstrip("\n").strip()))
        self.inbox.put(("terminal", None))

    def _poll_telegram(self):
        while True:
            params = {"timeout": POLL_SECONDS, "allowed_updates": '["message"]'}
            if self.offset is not None:
                params["offset"] = self.offset
            try:
                result = self._api("getUpdates", params, timeout=POLL_SECONDS + 10).get("result", [])
                self.warned = False
            except Exception as e:
                self._warn(e)
                time.sleep(10)
                continue

            for update in result:
                self.offset = update["update_id"] + 1
                message = update.get("message") or {}
                if str(message.get("chat", {}).get("id")) != str(self.chat_id):
                    continue
                text = (message.get("text") or "").strip()
                if not text or text.startswith("/"):
                    continue
                handler = self.commands.get(text.lower())
                if handler:
                    self.notify(handler())
                elif self.waiting.is_set():
                    self.inbox.put(("telegram", text))
                else:
                    self.notify("지금은 답을 기다리는 질문이 없습니다. 명령: status(상태), stop(현재 단계 후 정지), stop now(즉시 정지)")

    def add_command(self, names, handler):
        """Telegram에서 언제든 받는 명령. handler()의 반환 문자열을 답장으로 보낸다."""
        for name in names:
            self.commands[name.lower()] = handler

    def interrupt(self):
        """기다리는 ask()를 None으로 끝낸다 (정지 요청용)."""
        self.inbox.put(("stop", None))

    # ---------------- telegram ----------------

    def _api(self, method, params, timeout=10):
        url = f"https://api.telegram.org/bot{self.token}/{method}"
        data = urllib.parse.urlencode(params).encode()
        with urllib.request.urlopen(url, data=data, timeout=timeout) as resp:
            return json.loads(resp.read().decode())

    def _warn(self, error):
        if not self.warned:
            # 오류 메시지에 URL(토큰 포함)이 들어가지 않도록 종류만 출력한다.
            print(f"[WARN] Telegram 통신 실패: {type(error).__name__}", flush=True)
            self.warned = True

    def _skip_old_updates(self):
        """시작 전에 쌓인 메시지를 답으로 착각하지 않도록 건너뛴다."""
        try:
            result = self._api("getUpdates", {"offset": -1, "timeout": 0}).get("result", [])
            if result:
                self.offset = result[-1]["update_id"] + 1
        except Exception as e:
            self._warn(e)

    def notify(self, text):
        if not self.telegram:
            return
        if len(text) > MAX_TEXT:
            text = text[:MAX_TEXT] + "\n…(생략)"
        try:
            self._api("sendMessage", {"chat_id": self.chat_id, "text": text})
        except Exception as e:
            self._warn(e)

    # ---------------- ask ----------------

    def ask(self, question, telegram_text=None):
        """터미널/Telegram 중 먼저 온 답을 돌려준다. 받을 방법이 없으면 None.

        telegram_text가 없으면 터미널에서만 묻는다.
        """
        use_telegram = self.telegram and telegram_text is not None

        # 이전 질문에 늦게 도착한 Telegram 답은 버린다. 터미널 입력은 input()처럼 미리 쳐 둔 것도 쓴다.
        pending = []
        while True:
            try:
                item = self.inbox.get_nowait()
            except queue.Empty:
                break
            if item[0] == "terminal":
                pending.append(item)
        for item in pending:
            self.inbox.put(item)
        if pending and pending[0][1] is None:
            self.inbox.get_nowait()
            self.stdin_open = False

        if not self.stdin_open and not use_telegram:
            return None

        print(question, end="", flush=True)
        if use_telegram:
            self.notify(telegram_text)
            self.waiting.set()
        try:
            while True:
                source, text = self.inbox.get()
                if source == "stop":
                    return None
                if source == "terminal":
                    if text is None:
                        self.stdin_open = False
                        if not use_telegram:
                            return None
                        continue
                    if use_telegram:
                        self.notify(f"(터미널에서 응답됨: {text or 'ENTER'})")
                    return text
                if use_telegram:
                    print(f"{text}  ← Telegram", flush=True)
                    self.notify(f"받았습니다: {text}")
                    return text
        finally:
            self.waiting.clear()
