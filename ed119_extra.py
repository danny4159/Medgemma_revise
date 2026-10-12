"""iter_119 잠금 이후 추가 기술표(amendment). 새 정책·문턱·재채점 없음, 저장 per_patient의 상태만 교차 집계.
 (1) draft-free(B/G/E) 모두 정답이 아닌 K정답 사례(초안 고유 정보 진단), (2) K≠G 불일치 중재표, (3) E unresolved reason 분포.
analyze 이후에 추가했음을 결과에 명시한다. 결과는 새 파일에만 쓴다."""
import json
import time

import ed119_analyze as A

pp = json.load(open("results/iter_117/eval/per_patient.json"))
digest = A.hashlib.sha256(open("results/iter_117/eval/per_patient.json", "rb").read()).hexdigest()
m = [p for p in pp if p["group"] == "mismatch"]
c = [p for p in pp if p["group"] == "control"]
st = lambda p, q: A.state(p["answers"][q], p["gt"])  # noqa: E731

out = dict(amendment="잠금(analysis_spec.json) 이후 추가된 기술표. 사후 분석, 정책 최적화 아님.", per_patient_sha256=digest,
           created_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))

# (1) 초안 고유 정보 진단: K 정답이고 B/G/E 모두 정답이 아닌 사례
uniq = [p for p in m if st(p, "K") == "correct" and all(st(p, q) != "correct" for q in "BGE")]
out["draft_unique"] = dict(
    n=len(uniq), ids=[p["id"] for p in uniq],
    E_state={s: sum(st(p, "E") == s for p in uniq) for s in A.STATES},
    G_state={s: sum(st(p, "G") == s for p in uniq) for s in A.STATES},
    S_correct=sum(st(p, "S") == "correct" for p in uniq), M_correct=sum(st(p, "M") == "correct" for p in uniq),
    N_state={s: sum(st(p, "N") == s for p in uniq) for s in A.STATES}, R_state={s: sum(st(p, "R") == s for p in uniq) for s in A.STATES},
    by_category={k: sum(p["category"] == k for p in uniq) for k in ("opacity", "normal", "not_normal_no_opacity")},
    note="K/B 이진·불일치 선정 구조상 oracle 진단. 사용 가능한 selector 아님. 무엇이 이 사례를 정답으로 만들었는지(영상 인식 vs 우연)는 미판별.")

# (2) K≠G 불일치 중재 (mismatch에서 G는 항상 resolved)
kg = [p for p in m if p["answers"]["K"] != p["answers"]["G"]]
rows = {}
for side in ("K_right", "G_right"):
    sub = [p for p in kg if (p["answers"]["K"] == p["gt"]) == (side == "K_right")]
    rows[side] = dict(n=len(sub), E_state={s: sum(st(p, "E") == s for p in sub) for s in A.STATES},
                      S_correct=sum(st(p, "S") == "correct" for p in sub), M_correct=sum(st(p, "M") == "correct" for p in sub))
out["K_vs_G_disagreement"] = dict(n=len(kg), sides=rows,
    note="E가 resolved인 경우에만 draft-free 중재 가능. 이 표는 기술 통계이며 새 결합 규칙의 선택이 아니다.")
out["K_vs_G_control"] = dict(n=sum(p["answers"]["K"] != p["answers"]["G"] for p in c),
    G_gain=sum(st(p, "K") != "correct" and st(p, "G") == "correct" for p in c),
    G_loss=sum(st(p, "K") == "correct" and st(p, "G") != "correct" for p in c))

# (3) E unresolved reason (저장된 원 resolver 결과)
rs = {}
for g, sub in (("mismatch", m), ("control", c)):
    rs[g] = {}
    for cond in ("E", "N", "R"):
        for p in sub:
            if p["answers"][cond] is None:
                k = f"{cond}:{p['resolve'][cond]['reason']}"
                rs[g][k] = rs[g].get(k, 0) + 1
out["unresolved_reasons"] = rs

# (4) 반대 방향 오류 위험: draft-free 정답을 K가 틀리게 하는 경우 vs 반대
out["opposing"] = dict(
    K_correct_G_wrong=sum(st(p, "K") == "correct" and st(p, "G") == "wrong" for p in m),
    K_wrong_G_correct=sum(st(p, "K") == "wrong" and st(p, "G") == "correct" for p in m),
    S_vs_G_mismatch=dict(S_correct_G_wrong=sum(st(p, "S") == "correct" and st(p, "G") == "wrong" for p in m),
                         S_wrong_G_correct=sum(st(p, "S") != "correct" and st(p, "G") == "correct" for p in m)))
A.wx("results/iter_119/eval/extra_tables.json", out)
print(json.dumps(out, ensure_ascii=False, indent=1)[:3500])
