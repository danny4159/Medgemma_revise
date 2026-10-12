"""iter_112: 격리 환경(results/environments/medrega112)의 Python으로 인자를 그대로 실행하는 얇은 launcher.
사용: python mr112_envrun.py script.py args...  |  python mr112_envrun.py -c "code" """
import os
import subprocess
import sys

PY = os.path.abspath("results/environments/medrega112/bin/python")
env = dict(os.environ)
env["PYTHONPATH"] = os.getcwd() + (":" + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
env["HF_HOME"] = os.path.abspath("results/environments/medrega112_hfhome")
env["TRANSFORMERS_CACHE"] = env["HF_HOME"]
env["HF_HUB_OFFLINE"] = "1"
env["TOKENIZERS_PARALLELISM"] = "false"
sys.exit(subprocess.call([PY] + sys.argv[1:], env=env))
