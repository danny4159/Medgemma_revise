"""실행 lock과 원자적 작업 claim (iter_010). flock 기반: 소유 프로세스가 종료되어야만 커널이 lock을 놓는다.

- try_lock은 원자적이다 (경쟁하는 여러 프로세스 중 하나만 성공). 살아 있는 소유자의 lock은 절대 빼앗지 않는다.
- 소유자가 죽으면 커널이 lock을 해제하므로, 다음 acquire가 '종료가 확인된 소유자의 claim 회수'가 된다.
  파일에 남은 이전 소유자 정보(pid/host/시작시각)는 prev로 반환해 로그에 남긴다 (파일은 삭제하지 않는다).
- 같은 host의 로컬 파일시스템을 가정한다 (NFS 등 flock 의미가 다른 곳에서는 쓰지 않는다).
"""
import fcntl
import json
import os
import socket
import time


def proc_start(pid):
    """/proc/<pid>/stat의 starttime (clock ticks). 없으면 None."""
    try:
        with open(f"/proc/{pid}/stat") as f:
            s = f.read()
        return int(s[s.rindex(")") + 2:].split()[19])
    except (FileNotFoundError, ProcessLookupError, ValueError, IndexError):
        return None


def my_info(**extra):
    pid = os.getpid()
    return {"pid": pid, "start": proc_start(pid), "host": socket.gethostname(), "ts": time.time(), **extra}


def _read(fd):
    os.lseek(fd, 0, os.SEEK_SET)
    txt = os.read(fd, 65536).decode(errors="replace")
    try:
        return json.loads(txt) if txt.strip() else None
    except ValueError:
        return None


class Lock:
    def __init__(self, path, fd, info):
        self.path, self.fd, self.info = path, fd, info

    def release(self):
        if self.fd is not None:
            os.ftruncate(self.fd, 0)
            os.lseek(self.fd, 0, os.SEEK_SET)
            os.write(self.fd, json.dumps({"released": True, "by": self.info}).encode())
            fcntl.flock(self.fd, fcntl.LOCK_UN)
            os.close(self.fd)
            self.fd = None


def try_lock(path, info):
    """returns (Lock 또는 None, prev, reclaimed).

    None이면 다른 살아 있는 프로세스가 보유 중이다 (prev=현재 파일의 소유자 정보, 읽을 수 있으면).
    reclaimed=True: 이전 소유자가 release 없이 종료(kill 등)한 lock을 이어받았다 (prev=그 소유자 정보).
    """
    fd = os.open(path, os.O_CREAT | os.O_RDWR)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        prev = _read(fd)
        os.close(fd)
        return None, prev, False
    prev = _read(fd)
    reclaimed = isinstance(prev, dict) and not prev.get("released") and "pid" in prev
    os.ftruncate(fd, 0)
    os.lseek(fd, 0, os.SEEK_SET)
    os.write(fd, json.dumps(info).encode())
    os.fsync(fd)
    return Lock(path, fd, info), prev, reclaimed
