"""허용 GPU 집합 안에서 한 장을 골라 명령을 실행한다 (셸 환경변수 접두 없이). 사용: python -m rsna_diag.on_gpu --gpu 1 -- python -m rsna_diag.adapt_geo ...
상속된 CUDA_VISIBLE_DEVICES(정수 목록)의 원소만 허용하며 자식의 종료 코드를 그대로 반환한다. 실행 직전 GPU 여유 메모리를 기록한다."""
import argparse
import os
import subprocess
import sys

from .run_shards import gpu_snapshot


def allowed_gpus():
    raw = os.environ.get("CUDA_VISIBLE_DEVICES")
    if not raw:
        raise SystemExit("CUDA_VISIBLE_DEVICES not set (allowed GPU set unknown)")
    try:
        return [int(x) for x in raw.split(",")]
    except ValueError:
        raise SystemExit(f"non-integer CUDA_VISIBLE_DEVICES {raw!r}: this launcher supports integer ids only")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gpu", type=int, required=True)
    ap.add_argument("--min-free-mib", type=int, default=0, help="이 여유가 없으면 실행하지 않는다")
    ap.add_argument("cmd", nargs=argparse.REMAINDER)
    a = ap.parse_args()
    al = allowed_gpus()
    if a.gpu not in al:
        raise SystemExit(f"gpu {a.gpu} not within allowed {al}")
    cmd = a.cmd[1:] if a.cmd and a.cmd[0] == "--" else a.cmd
    rows, apps = gpu_snapshot({a.gpu})
    print(f"[on_gpu] gpu {a.gpu} before: {rows} apps={apps}", flush=True)
    if a.min_free_mib and rows and rows[0]["mem_total_mib"] - rows[0]["mem_used_mib"] < a.min_free_mib:
        raise SystemExit(f"gpu {a.gpu} free < {a.min_free_mib} MiB")
    sys.exit(subprocess.run(cmd, env=dict(os.environ, CUDA_VISIBLE_DEVICES=str(a.gpu))).returncode)


if __name__ == "__main__":
    main()
