"""iter_010 -> iter_011 학습 checkpoint 이관 (제한된 부모 checkpoint 가져오기 경로).

protocol이 바뀌면 protocol digest -> train digest가 바뀌므로 단순 digest 교체는 하지 않는다. 대신 아래를 명시적으로 검증한 migration manifest를
만들고, train.py는 이 manifest와 부모 checkpoint 파일을 다시 검증한 뒤에만 새 run으로 가져온다.
  - 부모 checkpoint 파일 sha256, 부모 train_digest/protocol digest, 부모 train_config 재계산 digest 일치
  - 부모 config와 새 config가 protocol_digest·새 입력 digest 외에 동일 (학습 의미 불변)
  - 부모 protocol이 잠근 manifest/GT sha == 현재 파일 sha (입력 대응), 현재 train ID 파일 == manifest의 train split 전체
  - checkpoint 위치가 step == epoch*steps_per_epoch + pos 와 일치
  - old -> new protocol 코드 파일 hash 변경 목록 (변경된 파일만; 학습 의미 불변은 변경 목록과 함께 서술)
사용: python -m rsna_diag.migrate make --parent-run D --old-protocol P0 --new-protocol P1 --out FILE --semantics-note TXT
"""
import argparse
import hashlib
import json
import math
import os
import sys

from . import lock_protocol


def cfg_digest(cfg):
    return hashlib.sha256(json.dumps(cfg, sort_keys=True).encode()).hexdigest()


def file_sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for ch in iter(lambda: f.read(1 << 20), b""):
            h.update(ch)
    return h.hexdigest()


class MigrationError(RuntimeError):
    pass


NEW_ONLY_KEYS = ("protocol_digest", "train_inputs_digest", "val_inputs_digest")


def make(parent_run, old_protocol, new_protocol, out, note, manifest_paths):
    import torch
    ck = os.path.join(parent_run, "ckpt_latest.pt")
    blob = torch.load(ck, map_location="cpu", weights_only=False)
    tc = json.load(open(os.path.join(parent_run, "train_config.json")))
    old_dig = lock_protocol.digest_of(old_protocol)
    new_dig = lock_protocol.verify(new_protocol)
    if cfg_digest(tc["config"]) != tc["train_digest"] or blob["train_digest"] != tc["train_digest"]:
        raise MigrationError("parent train digest inconsistent")
    if blob["protocol_digest"] != old_dig or tc["config"]["protocol_digest"] != old_dig:
        raise MigrationError("parent protocol digest != old protocol file")
    old_files = json.load(open(old_protocol))["locked"]["files"]
    new_files = json.load(open(new_protocol))["locked"]["files"]
    data_match = {}
    for f in manifest_paths:
        cur = file_sha(f)
        if old_files.get(f) != cur or new_files.get(f) != cur:
            raise MigrationError(f"{f}: sha differs between old protocol / new protocol / current")
        data_match[f] = cur
    spe = math.ceil(tc["config"]["n_train"] / tc["config"]["eff_batch"])
    if blob["step"] != blob["epoch"] * spe + blob["pos_in_epoch"]:
        raise MigrationError(f"checkpoint position inconsistent: step {blob['step']} epoch {blob['epoch']} pos {blob['pos_in_epoch']}")
    changed = {f: {"old": old_files.get(f), "new": new_files.get(f)} for f in sorted(set(old_files) | set(new_files))
               if old_files.get(f) != new_files.get(f)}
    man = {"parent_run": parent_run, "parent_ckpt": ck, "parent_ckpt_sha256": file_sha(ck), "parent_ckpt_bytes": os.path.getsize(ck),
           "parent_step": blob["step"], "parent_epoch": blob["epoch"], "parent_pos_in_epoch": blob["pos_in_epoch"],
           "parent_train_digest": tc["train_digest"], "parent_protocol_digest": old_dig, "parent_protocol_file": old_protocol,
           "parent_config": tc["config"], "parent_train_log": os.path.join(parent_run, "train_log.jsonl"),
           "parent_train_log_sha256_at_migration": file_sha(os.path.join(parent_run, "train_log.jsonl")),
           "new_protocol_file": new_protocol, "new_protocol_digest": new_dig, "invariant_config_excludes": list(NEW_ONLY_KEYS),
           "manifest_sha_old_new_current_equal": data_match, "protocol_file_changes_old_to_new": changed,
           "semantics_note": note}
    if os.path.exists(out):
        sys.exit(f"{out} exists (not overwritten)")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    json.dump(man, open(out, "w"), indent=1)
    return man


def verify_parent(migration_path, new_cfg, new_protocol_digest):
    """train.py가 호출. 부모 checkpoint를 다시 읽어 manifest와 대조하고 blob을 반환한다."""
    import torch
    m = json.load(open(migration_path))
    if m["new_protocol_digest"] != new_protocol_digest:
        raise MigrationError("migration manifest was made for a different new protocol")
    ck = m["parent_ckpt"]
    if file_sha(ck) != m["parent_ckpt_sha256"]:
        raise MigrationError("parent checkpoint file changed since migration manifest")
    blob = torch.load(ck, map_location="cpu", weights_only=False)
    if (blob["train_digest"] != m["parent_train_digest"] or blob["protocol_digest"] != m["parent_protocol_digest"]
            or blob["step"] != m["parent_step"] or blob["epoch"] != m["parent_epoch"] or blob["pos_in_epoch"] != m["parent_pos_in_epoch"]):
        raise MigrationError("parent checkpoint content differs from manifest")
    old, new = dict(m["parent_config"]), dict(new_cfg)
    for k in NEW_ONLY_KEYS:
        old.pop(k, None)
        new.pop(k, None)
    if old != new:
        diff = {k: (old.get(k), new.get(k)) for k in set(old) | set(new) if old.get(k) != new.get(k)}
        raise MigrationError(f"training semantics differ between parent and new config: {diff}")
    return blob, m


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    c = sp.add_parser("make")
    c.add_argument("--parent-run", required=True)
    c.add_argument("--old-protocol", required=True)
    c.add_argument("--new-protocol", required=True)
    c.add_argument("--out", required=True)
    c.add_argument("--semantics-note", required=True)
    a = ap.parse_args()
    make(a.parent_run, a.old_protocol, a.new_protocol, a.out, a.semantics_note,
         ["results/iter_010/manifests/infer_manifest.jsonl", "results/iter_010/manifests/gt_manifest.json"])
    print("migration manifest", a.out)


if __name__ == "__main__":
    main()
