#!/usr/bin/env python3
"""독립 문헌 탐색기. 기본 실행은 상태 조회, --run으로만 모델 호출을 시작한다."""
import argparse
import json
from pathlib import Path
import signal
import sys
import time

from discovery.core import PACKAGE, rebuild, render, replay_notifications, run_round
from discovery.runtime import Channel, Codex, lock, now, read_json, save, separate_telegram

ROOT = PACKAGE / "runtime"


def nonnegative(value):
    number = int(value)
    if number < 0:
        raise argparse.ArgumentTypeError("0 이상이어야 합니다")
    return number


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="의료 AI 문헌·산업 수요 탐색 (gpt-6-astra/high)")
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument("--run", action="store_true", help="새 회차를 계속 탐색; 기본은 상태 조회")
    actions.add_argument("--status", action="store_true")
    actions.add_argument("--check", action="store_true", help="설정/CLI 점검, 모델·Telegram 호출 없음")
    actions.add_argument("--stop", action="store_true", help="현재 회차 후 정지, 한도 대기면 조기 종료")
    parser.add_argument("--resume", action="store_true", help="정지/정체/탐색 보류를 명시적으로 해제 (--run 필요)")
    parser.add_argument("--max-rounds", type=nonnegative, default=0, help="이번 실행 완료 회차 수, 0은 무제한")
    parser.add_argument("--call-timeout", type=nonnegative, default=2400)
    parser.add_argument("--limit-wait-hours", type=nonnegative, default=8)
    parser.add_argument("--limit-poll-minutes", type=int, default=30)
    parser.add_argument("--no-telegram", action="store_true")
    args = parser.parse_args(argv)
    if args.resume and not args.run:
        parser.error("--resume은 --run과 함께 사용하세요")
    if args.limit_poll_minutes < 1:
        parser.error("--limit-poll-minutes는 1 이상")
    return args


def status(root=ROOT):
    state = rebuild(root)
    latest = read_json(root / "status.json", {"state": "not_started"})
    return (f"문헌 탐색 | 완료 {state['round']}회, 후보 {len(state['candidates'])}개\n"
            f"최근 기록 상태: {latest['state']} ({latest.get('time', '없음')})\n"
            f"정지 요청: {'있음' if (root / 'STOP').exists() else '없음'}\n"
            f"다음 질문: {state['next_question']}\n"
            "최근 기록 상태는 프로세스 생존 확인과 다릅니다.")


def stop(root=ROOT):
    save(root / "STOP", "사용자 요청: 현재 회차 후 정지\n")
    return "현재 탐색·후보 심사·저장을 마친 뒤 멈춥니다. 사용 한도 대기 중이면 조기에 멈춥니다."


def interrupt_signal(*_):
    raise KeyboardInterrupt


def main(argv=None):
    args = parse_args(argv)
    if args.stop:
        print(stop())
        return 0
    if not args.run and not args.check:
        print(status())
        return 0
    env = None if args.no_telegram else separate_telegram(PACKAGE / ".notify.env", PACKAGE.parent / "agent/.notify.env")
    model = Codex(ROOT, args.call_timeout, args.limit_wait_hours * 3600, args.limit_poll_minutes * 60)
    print(model.preflight())
    print("gpt-6-astra/high · live search · read-only · 구현/GPU 실행 없음")
    if args.check:
        print("Telegram: 별도 설정 있음" if env else "Telegram: 미연결 (기존 봇 사용 안 함)")
        return 0
    with lock(ROOT / ".lock"):
        state = rebuild(ROOT)
        if args.resume:
            (ROOT / "STOP").unlink(missing_ok=True)
        elif (ROOT / "STOP").exists() or state["paused"] or state["stalled"] >= 3:
            print("정지/보류 상태입니다. 검토 후 --run --resume으로 재개하세요.")
            return 0
        channel = Channel(ROOT, env)
        channel.commands(status, stop)
        model.inform = lambda message: channel.send(f"runtime-{time.time_ns()}", message)
        # SIGTERM도 호출 자식을 보존 가능한 로그와 함께 정리한다.
        previous = signal.signal(signal.SIGTERM, interrupt_signal)
        try:
            render(ROOT, state)
            replay_notifications(ROOT, channel)
            channel.send(f"start-{time.time_ns()}", "▶ 의료 AI 연구 탐색 시작\n문헌·산업 수요를 조사합니다. 실험은 실행하지 않습니다.")
            completed, stall_start = 0, state["stalled"] if args.resume else 0
            while not args.max_rounds or completed < args.max_rounds:
                if (ROOT / "STOP").exists():
                    break
                state = run_round(ROOT, state, model, channel)
                completed += 1
                if state["stalled"] == 0:
                    stall_start = 0
                if state["paused"] or state["stalled"] - stall_start >= 3:
                    channel.send(f"stalled-{state['round']}", "⏸ 탐색 보류\n새 근거 부족 또는 탐색 범위 재검토가 필요합니다. 후보를 과학적으로 기각한 것은 아닙니다.")
                    break
            save(ROOT / "status.json", {"state": "paused", "round": state["round"], "time": now()})
            channel.send(f"stop-{time.time_ns()}", f"⏸ 연구 탐색 종료 | {state['round']}회차까지 보존\n다음 질문: {state['next_question']}")
        except (KeyboardInterrupt, InterruptedError):
            save(ROOT / "status.json", {"state": "interrupted", "time": now()})
            channel.send(f"interrupt-{time.time_ns()}", "⏸ 연구 탐색 중단 | 호출 로그·완료 결과 보존. 재개 시 완료 호출을 재사용합니다.")
        except Exception as exc:
            save(ROOT / "status.json", {"state": "error", "kind": type(exc).__name__, "time": now()})
            channel.send(f"error-{time.time_ns()}", f"❌ 연구 탐색 오류 | {type(exc).__name__}\n완료 기록은 보존했습니다. 로컬 로그를 확인하세요.")
            raise
        finally:
            signal.signal(signal.SIGTERM, previous)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as error:
        print(f"[ERROR] {error}", file=sys.stderr)
        sys.exit(1)
