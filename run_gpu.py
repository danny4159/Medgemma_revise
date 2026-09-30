"""허용된 GPU(상속된 CUDA_VISIBLE_DEVICES 안)의 한 장을 지정해 명령을 실행한다. python run_gpu.py <gpu> <cmd...>
여러 개를 동시에 돌리려면 run_gpu.py를 여러 번 호출한다 (각각 별도 프로세스)."""
import os
import subprocess
import sys

allowed = [x for x in os.environ.get("CUDA_VISIBLE_DEVICES", "").split(",") if x]
gpu = sys.argv[1]
if gpu not in allowed:
    sys.exit(f"gpu {gpu} not in inherited allowed set {allowed}")
env = dict(os.environ, CUDA_VISIBLE_DEVICES=gpu)
sys.exit(subprocess.run(sys.argv[2:], env=env).returncode)
