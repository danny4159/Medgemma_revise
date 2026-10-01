"""iter_045: 격리 venv(results/environments/medgrounder_iter045)에 MedGrounder 의존성을 설치하고 기록한다.

기존 medgemma 환경은 변경하지 않는다. 설치 명령·freeze를 results/iter_045/env/ 에 남긴다.
사용: python mg45_env.py install | check
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ENV = os.path.join(HERE, "results", "environments", "medgrounder_iter045")
PY = os.path.join(ENV, "bin", "python")
OUT = os.path.join(HERE, "results", "iter_045", "env")

# 공식 requirements.txt(SHA a0aad98d) 그대로 + gdown(가중치 다운로드용 보조)
REQ = os.path.join(HERE, "results", "iter_045", "external", "MedGrounder", "requirements.txt")


def run(args, log):
    os.makedirs(OUT, exist_ok=True)
    p = subprocess.run(args, capture_output=True, text=True)
    with open(os.path.join(OUT, log), "a") as f:
        f.write("$ " + " ".join(args) + f"\nrc={p.returncode}\n{p.stdout[-20000:]}\n{p.stderr[-20000:]}\n")
    print(" ".join(args[:6]), "rc=", p.returncode)
    return p


def install():
    run([PY, "-m", "pip", "install", "--upgrade", "pip"], "install.log")
    p = run([PY, "-m", "pip", "install", "-r", REQ, "gdown"], "install.log")
    if p.returncode != 0:
        sys.exit(p.returncode)
    fr = run([PY, "-m", "pip", "freeze"], "freeze_cmd.log")
    with open(os.path.join(OUT, "pip_freeze.txt"), "w") as f:
        f.write(fr.stdout)


def extra():
    """공식 requirements.txt에 빠져 있지만 model/backbone.py가 import하는 패키지(timm). 사유: ModuleNotFoundError 대응."""
    p = run([PY, "-m", "pip", "install", "timm"], "install_extra.log")
    fr = run([PY, "-m", "pip", "freeze"], "freeze_cmd.log")
    with open(os.path.join(OUT, "pip_freeze_after_extra.txt"), "w") as f:
        f.write(fr.stdout)
    sys.exit(p.returncode)


def check():
    code = ("import torch,torchvision,transformers,json;"
            "print(json.dumps({'torch':torch.__version__,'tv':torchvision.__version__,"
            "'tf':transformers.__version__,'cuda':torch.cuda.is_available(),"
            "'n':torch.cuda.device_count(),'cap':torch.cuda.get_device_capability(0) if torch.cuda.is_available() else None}))")
    p = run([PY, "-c", code], "check.log")
    print(p.stdout, p.stderr[-2000:])


if __name__ == "__main__":
    {"install": install, "check": check, "extra": extra}[sys.argv[1]]()
