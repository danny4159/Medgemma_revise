"""평가 공통 gate (iter_011): 점수 계산 전에 생성 결과가 예상 요청 집합과 정확히 일치하는지, protocol/config/입력/adapter와 연결되는지 검사한다.

- verify_gen: 예상 ID x prompt x adapter 집합 == 원시 record 집합 (누락·중복·잉여 0), 각 record의 request_id/config/protocol/prompt/
  현재 pixel hash 일치, 완료 근거(completion.json)의 존재와 기대 개수 일치를 강제한다. 하나라도 어긋나면 GateError (점수를 만들지 않는다).
- adapter_digest: adapter.pt를 다시 읽어 tensor digest를 재계산하고 파일에 기록된 digest와 대조한다.
- check_seeds: 정확히 {17, 29, 43}, 중복 거부.
"""
import glob
import json
import os

from . import generate, lock_protocol, prompts as P

SEEDS = (17, 29, 43)


class GateError(RuntimeError):
    pass


def adapter_digest(adapter_dir):
    import torch
    from . import lora
    blob = torch.load(os.path.join(adapter_dir, "adapter.pt"), map_location="cpu", weights_only=True)
    dg = lora.state_digest(blob["state"])
    if blob.get("digest") != dg:
        raise GateError(f"adapter digest in file != recomputed for {adapter_dir}")
    return dg


def check_seeds(seed_args):
    """['17=dir', '29=dir', ...] 또는 [17, 29, 43] -> 정렬된 seed tuple. 중복·누락·잉여는 dictionary를 만들기 전에 거부한다."""
    seeds = [int(str(x).replace("=", ":").split(":")[0]) for x in seed_args]
    if len(set(seeds)) != len(seeds):
        raise GateError(f"duplicate seeds: {seeds}")
    if tuple(sorted(seeds)) != SEEDS:
        raise GateError(f"seed set must be exactly {list(SEEDS)}, got {sorted(seeds)}")
    return tuple(sorted(seeds))


def verify_gen(gen_dir, items, pnames, adapter_dir, protocol_path, parent_dir=None, parent_protocol=None, require_completion=True):
    """returns {(id, prompt): record}. items: 예상 item 목록(manifest 항목). adapter_dir=None이면 base."""
    pdig = lock_protocol.verify(protocol_path)
    prompts_used = {p: P.all_prompts()[p] for p in pnames}
    cdig, _ = generate.config_digest(generate.static_env(), prompts_used)
    adg = adapter_digest(adapter_dir) if adapter_dir else None
    files = sorted(glob.glob(os.path.join(gen_dir, "gen_worker*.jsonl")))
    accept = ()
    if parent_dir:
        if lock_protocol.locked_config_digest(parent_protocol) != lock_protocol.locked_config_digest(protocol_path):
            raise GateError("parent protocol generation config differs")
        accept = (lock_protocol.digest_of(parent_protocol),)
        files = sorted(glob.glob(os.path.join(parent_dir, "gen_worker*.jsonl"))) + files
    if not files:
        raise GateError(f"no gen_worker*.jsonl in {gen_dir}")
    cache = {}
    px = lambda p: cache.setdefault(p, generate.load_image(p)[2])
    try:
        done = generate.validate_existing({f: generate.read_records(f) for f in files}, items, pnames, prompts_used, cdig, adg, pdig, px, accept)
    except generate.RunError as e:
        raise GateError(str(e)) from e
    expected = {(i["id"], p) for i in items for p in pnames}
    missing = sorted(expected - set(done))
    if missing:
        raise GateError(f"{len(missing)} expected requests missing in {gen_dir}, e.g. {missing[:3]}")
    if set(done) - expected:
        raise GateError("extra requests present")
    if require_completion:
        cp = os.path.join(gen_dir, "completion.json")
        if not os.path.exists(cp):
            raise GateError(f"completion.json missing in {gen_dir}")
        c = json.load(open(cp))
        if c.get("n_expected") != len(expected) or c.get("n_actual_unique") != len(expected) or c.get("n_missing") != 0 or c.get("n_duplicate") != 0:
            raise GateError(f"completion.json counts inconsistent in {gen_dir}: {c}")
        if c.get("adapter_digest") != adg:
            raise GateError("completion.json adapter digest differs from adapter")
        if c.get("protocol_digest") != pdig:
            raise GateError("completion.json protocol digest differs from current protocol")
    return done
