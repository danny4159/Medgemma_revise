"""iter_058 HD-GLIO 격리 환경 구성. 기존 medgemma/hf_cache는 건드리지 않는다.
사용: python hdglio58_env.py install | check
"""
import json
import os
import subprocess
import sys

ROOT = os.path.abspath("results/environments/hdglio58")
PY = f"{ROOT}/bin/python"
LOG = "results/iter_058/env"
SHA = "d1a37c79cfb0e5a253403b6e35cf66010950752b"
SRC = os.path.abspath(f"results/iter_058/external/HD-GLIO-{SHA}")
PKGS = ["torch==2.5.1", "torchvision==0.20.1"]


def run(args, name):
    os.makedirs(LOG, exist_ok=True)
    with open(f"{LOG}/{name}.log", "a") as f:
        f.write("$ " + " ".join(args) + "\n")
        f.flush()
        r = subprocess.run(args, stdout=f, stderr=subprocess.STDOUT)
        f.write(f"rc={r.returncode}\n")
    print(name, "rc", r.returncode)
    return r.returncode


def install():
    assert os.path.exists(PY)
    run([PY, "-m", "pip", "install", "--upgrade", "pip", "wheel", "setuptools<81"], "pip0")
    assert run([PY, "-m", "pip", "install"] + PKGS, "torch") == 0
    assert run([PY, "-m", "pip", "install", "nibabel", "numpy<2", "SimpleITK", "scikit-image", "batchgenerators", "nnunet==1.7.1", "pandas"], "deps") == 0
    assert run([PY, "-m", "pip", "install", "--no-deps", SRC], "hdglio") == 0
    run([PY, "-m", "pip", "freeze"], "freeze")


def check():
    code = ("import torch,nnunet,hd_glio;print(torch.__version__,torch.cuda.is_available(),torch.cuda.device_count());"
            "import SimpleITK,nibabel;print(SimpleITK.__version__,nibabel.__version__)")
    run([PY, "-c", code], "check")


if __name__ == "__main__":
    {"install": install, "check": check}[sys.argv[1]]()
