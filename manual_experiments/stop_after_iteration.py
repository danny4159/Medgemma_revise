"""현재 프로세스의 지정 반복 리뷰 뒤 기존 STOP 신호를 보낸다. 재실행은 하지 않는다."""
import argparse
import json
from pathlib import Path
import time


def process_identity(pid):
    try:
        # comm 안의 공백/괄호를 제외한 starttime(field 22).
        return Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[19]
    except FileNotFoundError:
        return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pid", type=int, required=True)
    parser.add_argument("--iteration", type=int, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    identity = process_identity(args.pid)
    if identity is None:
        raise SystemExit("대상 프로세스가 없어 정지 예약을 시작하지 않습니다.")
    run = root / "agent" / "runs" / f"iter_{args.iteration:03d}"
    print(f"iter_{args.iteration:03d} 리뷰 완료 대기, PID={args.pid}", flush=True)
    while process_identity(args.pid) == identity:
        if (run / "superseded.json").exists():
            raise SystemExit("대상 반복이 전환되어 예약을 종료합니다. 새 반복에는 적용하지 않습니다.")
        try:
            review = json.loads((run / "review.json").read_text())
        except (FileNotFoundError, json.JSONDecodeError):
            time.sleep(0.1)
            continue
        if review.get("verdict") not in {"CONTINUE", "DONE", "NEEDS_HUMAN"}:
            raise SystemExit("알 수 없는 리뷰 판정: 자동 신호를 보내지 않습니다.")
        # 현재 run_loop는 review 이후 후처리를 마친 뒤 다음 반복 입구에서 STOP을 확인한다.
        (root / "agent" / "STOP").touch()
        print("리뷰 완료: STOP 요청 저장. 후처리 뒤 다음 반복 진입을 차단합니다.", flush=True)
        return
    print("대상 프로세스 종료: 새 실행에 정지 요청을 남기지 않습니다.", flush=True)


if __name__ == "__main__":
    main()
