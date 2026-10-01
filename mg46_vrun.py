"""iter_046 격리 venv(medgrounder_iter045) 실행기: python mg46_vrun.py <script.py> [args...]. 로그는 results/iter_046/logs/ 에 보존, 마지막 40줄만 출력."""
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PY = os.path.join(HERE, "results", "environments", "medgrounder_iter045", "bin", "python")

if __name__ == "__main__":
    os.makedirs(os.path.join(HERE, "results", "iter_046", "logs"), exist_ok=True)
    tag = "_".join(os.path.basename(x) for x in sys.argv[1:3]).replace("/", "_")[:60]
    log = os.path.join(HERE, "results", "iter_046", "logs", f"{tag}_{int(time.time())}_{os.getpid()}.log")
    with open(log, "wb") as f:
        rc = subprocess.call([PY] + sys.argv[1:], cwd=HERE, env=dict(os.environ), stdout=f, stderr=subprocess.STDOUT)
    lines = open(log, errors="replace").read().replace("\r", "\n").splitlines()
    print("\n".join(lines[-40:]))
    print(f"[vrun] rc={rc} log={log}")
    sys.exit(rc)
