"""iter_112: MedRegA 공식 코드(고정 SHA)와 HF 모델 metadata/소형 파일 확보. 대용량 가중치는 mr112_weights.py가 받는다."""
import hashlib, json, os, sys, urllib.request

GH_SHA = "f003c701b0b146e5ca7233ccfd627ee5f9eb3993"
HF_REPO = "Luxuriant16/medrega"
HF_REV = "ec1d98335322b2200f93b35562b681e05fc3a194"
OUT = "results/iter_112/external"
GH_FILES = ["LICENSE", "README.md", "demo_data/data_file.jsonl", "src/demo.py",
            "src/internvl/conversation.py", "src/internvl/model/__init__.py",
            "src/internvl/model/internvl_chat/__init__.py",
            "src/internvl/model/internvl_chat/configuration_intern_vit.py",
            "src/internvl/model/internvl_chat/configuration_internvl_chat.py",
            "src/internvl/model/internvl_chat/modeling_intern_vit.py",
            "src/internvl/model/internvl_chat/modeling_internvl_chat.py",
            "src/internvl/model/internlm2/configuration_internlm2.py",
            "src/internvl/model/internlm2/modeling_internlm2.py",
            "src/internvl/model/internlm2/tokenization_internlm2.py",
            "src/internvl/model/internlm2/tokenization_internlm2_fast.py",
            "src/internvl/train/constants.py", "src/internvl/train/dataset.py",
            "src/tools/convert_to_int8.py"] + [f"demo_data/images/demo_0{i}.jpg" for i in range(1, 10)]
HF_SMALL = ["README.md", "added_tokens.json", "config.json", "configuration_intern_vit.py",
            "configuration_internlm2.py", "configuration_internvl_chat.py", "generation_config.json",
            "model.safetensors.index.json", "modeling_intern_vit.py", "modeling_internvl_chat.py",
            "special_tokens_map.json", "tokenizer.model", "tokenizer_config.json"]


def get(url, dst):
    if os.path.exists(dst):
        raise FileExistsError(dst)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    d = urllib.request.urlopen(url, timeout=120).read()
    with open(dst + ".tmp", "wb") as f:
        f.write(d)
    os.replace(dst + ".tmp", dst)
    return hashlib.sha256(d).hexdigest(), len(d)


def main():
    man = {"github": {"repo": "xmed-lab/MedRegA", "sha": GH_SHA, "files": {}},
           "hf": {"repo": HF_REPO, "revision": HF_REV, "files": {}}}
    for p in GH_FILES:
        url = f"https://raw.githubusercontent.com/xmed-lab/MedRegA/{GH_SHA}/{p}"
        man["github"]["files"][p] = dict(zip(("sha256", "bytes"), get(url, f"{OUT}/MedRegA/{p}")), url=url)
    for p in HF_SMALL:
        url = f"https://huggingface.co/{HF_REPO}/resolve/{HF_REV}/{p}"
        man["hf"]["files"][p] = dict(zip(("sha256", "bytes"), get(url, f"{OUT}/hf_small/{p}")), url=url)
    tree = json.load(urllib.request.urlopen(f"https://huggingface.co/api/models/{HF_REPO}/tree/{HF_REV}", timeout=60))
    man["hf"]["tree"] = tree
    with open(f"{OUT}/fetch_manifest.json", "w") as f:
        json.dump(man, f, indent=1)
    print("ok", len(man["github"]["files"]), len(man["hf"]["files"]))


if __name__ == "__main__":
    main()
