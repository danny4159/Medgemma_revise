"""iter_118: 생성·detector 프로세스의 정답 파일 접근 거부 + 열린 파일 기록 (sys.addaudithook).

- install(deny, log_path): deny 경로(디렉터리/파일) 아래를 open하려 하면 PermissionError. 열린 경로 집합을 종료 시 log_path에 기록한다.
- 부모(감독기·평가기)는 이 hook을 설치하지 않으며 정답을 읽는다. worker/detector만 hook 아래에서 실행된다.
"""
import atexit
import json
import os
import sys

_state = {"opened": set(), "denied": [], "installed": False}


def _norm(p):
    try:
        return os.path.realpath(os.fspath(p))
    except TypeError:
        return None


def install(deny, log_path):
    deny = [os.path.realpath(d) for d in deny]
    if _state["installed"]:
        return

    def hook(event, args):
        if event != "open":
            return
        p = _norm(args[0]) if args and isinstance(args[0], (str, bytes, os.PathLike)) else None
        if p is None:
            return
        _state["opened"].add(p)
        for d in deny:
            if p == d or p.startswith(d + os.sep):
                _state["denied"].append(p)
                raise PermissionError(f"ed118_guard: 정답/평가 전용 경로 접근 거부 {p}")

    def dump():
        tmp = f"{log_path}.{os.getpid()}.tmp"
        with open(tmp, "w") as f:
            json.dump({"pid": os.getpid(), "argv": sys.argv, "deny": deny, "n_opened": len(_state["opened"]),
                       "denied": _state["denied"], "opened": sorted(_state["opened"])}, f)
        os.replace(tmp, log_path)

    sys.addaudithook(hook)
    atexit.register(dump)
    _state["installed"] = True
