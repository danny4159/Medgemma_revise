"""iter_114 모델별 추가 비용 집계(실측 로그 기반, 새 모델 호출 없음). 사전 규칙: MSPC 추가 비용이 CURE 추가 비용 이하라고 말하려면
warm(적재 제외 생성 구간)과 cold(적재 포함) device-seconds 가 모두 이하여야 한다. 하나라도 어긋나면 False, 측정 불완전하면 None.
측정 범위: worker 프로세스별 모델 적재 후 요청 처리 구간(영상 전처리·forward·후처리·fsync 포함) = executions 'end'.wall_s, 적재 = 'start'.load_s(CURE는 loading_s).
worker 1개 = GPU 1장이므로 합이 device-seconds. 중단·재개된 실행은 'end' 이벤트가 없는 시작을 unmeasured 로 표시한다.
MG 대상(A)의 비용은 두 조합에 공통이다. 서비스 전체 비용(영상 입력부터 순위까지)의 일부이며 임상 처리량이 아니다.
사용: python nr114_cost.py <init|final>  → analysis/cost_<stage>.json (새 파일)
"""
import json
import sys
from pathlib import Path

R = Path("results/iter_114")
AN = R / "analysis_r1"


def read_events(path):
    return [json.loads(l) for l in open(path) if l.strip()]


def agg(files, load_key):
    starts = ends = 0
    warm = load = 0.0
    n_saved = 0
    for f in files:
        for e in read_events(f):
            if e["event"] == "start":
                starts += 1
                load += e[load_key]
            elif e["event"] == "end":
                ends += 1
                warm += e["wall_s"]
                n_saved += e["saved"]
    return {"warm_s": warm, "load_s": load, "n_start": starts, "n_end": ends, "n_saved_in_ends": n_saved, "complete_measurement": starts == ends}


def main(stage):
    names = ["init"] if stage == "init" else ["init", "expand"]
    tot = {k: {"warm_s": 0.0, "load_s": 0.0, "n_start": 0, "n_end": 0, "n_saved_in_ends": 0, "complete_measurement": True} for k in ("A", "MSPC", "CURE")}
    attempts = 0
    for nm in names:
        runs = json.load(open(AN / f"runs_{nm}.json"))
        parts = {"A": agg(sorted((Path(runs["A"])).glob("executions*.jsonl")), "load_s"),
                 "MSPC": agg(sorted((Path(runs["MSPC"])).glob("executions*.jsonl")), "load_s"),
                 "CURE": agg(sorted((Path(runs["CURE"]) / "cure").glob("shard*/executions.jsonl")), "loading_s")}
        for k, v in parts.items():
            for f in ("warm_s", "load_s", "n_start", "n_end", "n_saved_in_ends"):
                tot[k][f] += v[f]
            tot[k]["complete_measurement"] &= v["complete_measurement"]
        for rec in (Path(runs["CURE"]) / "cure").glob("shard*/outputs.jsonl"):
            for l in open(rec):
                if l.strip():
                    attempts += len(json.loads(l)["attempts"])
    complete = all(v["complete_measurement"] for v in tot.values())
    res = {"stage": stage, "per_model": tot, "cure_total_generate_calls_incl_cap_retries": attempts,
           "added_cost": {"mspc_warm_s": tot["MSPC"]["warm_s"], "mspc_cold_s": tot["MSPC"]["warm_s"] + tot["MSPC"]["load_s"],
                          "cure_warm_s": tot["CURE"]["warm_s"], "cure_cold_s": tot["CURE"]["warm_s"] + tot["CURE"]["load_s"]},
           "shared_target_A_cold_s": tot["A"]["warm_s"] + tot["A"]["load_s"], "complete_measurement": complete}
    ac = res["added_cost"]
    res["mspc_cost_le_cure"] = (ac["mspc_warm_s"] <= ac["cure_warm_s"] and ac["mspc_cold_s"] <= ac["cure_cold_s"]) if complete else None
    res["scope"] = __doc__
    out = AN / f"cost_{stage}.json"
    with out.open("x") as f:
        json.dump(res, f, indent=1)
    print(json.dumps({k: v for k, v in res.items() if k != "scope"}, indent=1))


if __name__ == "__main__":
    main(sys.argv[1])
