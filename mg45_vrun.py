"""격리 venv(medgrounder_iter045)의 python으로 스크립트를 실행하는 얇은 실행기.

사용: python mg45_vrun.py <script.py> [args...]
CUDA_VISIBLE_DEVICES 등 환경은 상속한다. 전체 출력은 results/iter_045/logs/<script>_<ts>.log 에 보존하고 마지막 40줄만 보여 준다.
(긴 진행 막대·경고를 반복 출력하지 않기 위함.)
"""
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PY = os.path.join(HERE, "results", "environments", "medgrounder_iter045", "bin", "python")

if __name__ == "__main__":
    os.makedirs(os.path.join(HERE, "results", "iter_045", "logs"), exist_ok=True)
    log = os.path.join(HERE, "results", "iter_045", "logs", f"{os.path.basename(sys.argv[1])}_{int(time.time())}.log")
    with open(log, "wb") as f:
        rc = subprocess.call([PY] + sys.argv[1:], cwd=HERE, env=dict(os.environ), stdout=f, stderr=subprocess.STDOUT)
    lines = open(log, errors="replace").read().replace("\r", "\n").splitlines()
    print("\n".join(lines[-40:]))
    print(f"[vrun] rc={rc} log={log}")
    sys.exit(rc)
