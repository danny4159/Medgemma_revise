"""모델 호출 없이 Linux 작업 종료를 기다린다. 종료는 실험 성공 판정이 아니다."""
import argparse
import json
from pathlib import Path
import time


def process_identity(pid):
    """PID 재사용을 구분하고 zombie는 종료로 취급한다."""
    if pid <= 0:
        raise ValueError("PID는 양수여야 합니다")
    try:
        raw = Path(f"/proc/{pid}/stat").read_text()
    except (FileNotFoundError, ProcessLookupError):
        return None
    fields = raw[raw.rfind(")") + 2:].split()
    return None if fields[0] in {"Z", "X"} else fields[19]


def wait_for_processes(identities, timeout=600, interval=15):
    if not identities or timeout <= 0 or interval <= 0:
        raise ValueError("감시 대상과 양수 timeout/interval이 필요합니다")
    started = time.monotonic()
    while True:
        pending = [pid for pid, start in identities.items()
                   if start is not None and process_identity(pid) == start]
        elapsed = time.monotonic() - started
        if not pending or elapsed >= timeout:
            return {"status": "pending" if pending else "processes_exited",
                    "pending_pids": pending, "elapsed_seconds": round(elapsed, 1),
                    "experiment_success": None,
                    "next": "완료·오류·checkpoint와 원시 결과를 확인하세요. 프로세스 종료만으로 성공 판정하지 않습니다."
                            if not pending else "작업 진행 중입니다. 새 판단 근거가 없으면 같은 대기를 이어가세요."}
        time.sleep(min(interval, timeout - elapsed))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pid", type=int, action="append", required=True)
    parser.add_argument("--timeout", type=float, default=600)
    parser.add_argument("--interval", type=float, default=15)
    args = parser.parse_args()
    result = wait_for_processes({p: process_identity(p) for p in args.pid}, args.timeout, args.interval)
    print(json.dumps(result, ensure_ascii=False))
    return 0  # pending은 모델/실험 실패가 아니다.


if __name__ == "__main__":
    raise SystemExit(main())
