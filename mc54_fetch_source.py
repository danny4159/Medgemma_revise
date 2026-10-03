"""iter_054: MediConfusion 공식 metadata/소스를 고정 revision으로 results/iter_054/source에 저장한다 (덮어쓰기 금지)."""
import hashlib
import json
import os
import subprocess
import sys
import urllib.request

REPO = "MShahabSepehri/MediConfusion"
OUT = "results/iter_054/source"
FILES = ["data/dataset.json", "data/image_dict.json", "configs/prompts/answering.json", "utils/answering.py",
         "Models/llava.py", "scripts/download.py", "README.md", "LICENSE"]


def main():
    rev = subprocess.run(["git", "ls-remote", "--", f"https://github.com/{REPO}", "HEAD"], capture_output=True, text=True,
                         check=True).stdout.split()[0]
    os.makedirs(OUT, exist_ok=True)
    man = {"repo": REPO, "revision": rev, "files": {}}
    for f in FILES:
        url = f"https://raw.githubusercontent.com/{REPO}/{rev}/{f}"
        dst = os.path.join(OUT, f.replace("/", "__"))
        if os.path.exists(dst):
            sys.exit(f"exists: {dst}")
        with urllib.request.urlopen(url, timeout=120) as r:
            data = r.read()
            final = r.geturl()
        with open(dst, "xb") as fh:
            fh.write(data)
        man["files"][f] = {"url": url, "final_url": final, "saved": dst, "sha256": hashlib.sha256(data).hexdigest(),
                           "bytes": len(data)}
        print(f, len(data))
    with open(os.path.join(OUT, "source_manifest.json"), "x") as fh:
        json.dump(man, fh, indent=1)


if __name__ == "__main__":
    main()
