"""iter_040 MedGrounder(공식, Chest ImaGenome-only) 실행 가능성 점검. 설치·환경 교체·재구현 없이 접근·의존성만 확인하고 기록한다.
python pg40_medgrounder_check.py --out results/iter_040/medgrounder/feasibility.json
"""
import argparse
import importlib
import json
import os
import sys
import urllib.request

MODS = {"albumentations": "albumentations", "ensemble-boxes": "ensemble_boxes", "omegaconf": "omegaconf", "opencv-python-headless": "cv2",
        "scipy": "scipy", "torchvision": "torchvision", "nltk": "nltk", "opt-einsum": "opt_einsum", "matplotlib": "matplotlib", "tqdm": "tqdm",
        "gdown": "gdown"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    if os.path.exists(a.out):
        sys.exit("output exists")
    out = {"repo": "https://github.com/aehrc/MedGrounder",
           "weights": "Google Drive folder listed in README (medgrounder_pretrain_imagenome.pth etc.)"}
    try:
        req = urllib.request.urlopen("https://raw.githubusercontent.com/aehrc/MedGrounder/main/requirements.txt", timeout=30).read().decode()
        out["requirements_txt"] = req.split()
    except Exception as e:
        out["requirements_txt"] = repr(e)[:150]
    st = {}
    for k, m in MODS.items():
        try:
            importlib.import_module(m)
            st[k] = "present"
        except Exception:
            st[k] = "MISSING"
    out["execution_env_modules"] = st
    try:
        r = urllib.request.urlopen("https://drive.google.com/drive/folders/1fwr-Bi2ICb26-MIJVKPxwhHVWGJaaBvz", timeout=20)
        out["drive_folder_http_status"] = r.status
    except Exception as e:
        out["drive_folder_http_status"] = repr(e)[:150]
    missing = [k for k, v in st.items() if v == "MISSING" and k != "gdown"]
    out["conclusion"] = ("NOT EXECUTED" if missing else "dependencies present; weights still need a Drive download path") + \
        ": required packages missing in the fixed medgemma env (pip install / env replacement / re-implementation not allowed by the plan): " + ",".join(missing)
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    json.dump(out, open(a.out, "w"), indent=1)
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
