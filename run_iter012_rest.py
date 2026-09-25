"""iter_012 pipeline 6-8단계 재개 실행기 (잠긴 rsna_diag.pipeline 함수를 같은 순서로 호출). 실행: python run_iter012_rest.py

변경 이유: pipeline 6단계의 부모 record 재사용 경로(generate.run_worker의 --parent-dir 분기)에 iter_010부터 있던 NameError
(lock_protocol 미import)가 있어 base_val이 시작 직후 실패했다. generate.py를 고치면 잠긴 protocol digest가 바뀌어
이미 완료·검증된 학습/선택 기록과의 연결이 끊기므로 코드는 바꾸지 않고, base validation 800요청 전체를 부모 재사용 없이
새 경로(base_val_full)에서 생성한다. 그 외 단계·규칙·gate는 pipeline.run()과 동일하다 (선택 파일은 write_or_verify로 재검증).
"""
import json
import os
import sys

from rsna_diag import final_eval, pipeline as PL, queue_lock, select as SEL

R = PL.R


def main():
    lk, own, _ = queue_lock.try_lock(os.path.join(os.path.realpath(R), "pipeline.lock"), queue_lock.my_info(role="pipeline_rest"))
    if lk is None:
        sys.exit(f"another pipeline owns {R}: {own}")
    try:
        d17 = [PL.run_dir(lr, 17) for lr in ("1e-4", "2e-4")]
        ext_p = f"{R}/select/extend.json"
        ext = PL.select_file("extend", d17, 5, ext_p)["extend"]
        E = 8 if ext else 5
        sel17 = PL.select_file("pick", d17, E, f"{R}/select/pick_seed17.json")
        lr = sel17["runs"][sel17["selected_run"]]["lr"]
        lr_s = {1e-4: "1e-4", 2e-4: "2e-4"}[lr]
        sel = {17: f"{R}/select/pick_seed17.json"}
        for s in (29, 43):
            p = f"{R}/select/pick_seed{s}.json"
            PL.select_file("pick", [PL.run_dir(lr_s, s)], E, p)
            sel[s] = p
        workers = PL.gen_check(sel17["runs"][sel17["selected_run"]]["adapter_dir"])
        PL.log(f"[rest] E={E} lr={lr_s} workers={workers}; base validation without parent reuse -> {R}/base_val_full")
        PL.gen(f"{R}/base_val_full", PL.IDS.format("validation"), "validation", "official_long,concise", workers)
        comp_p = f"{R}/final/comparator.json"
        pl = final_eval.comparator_payload(f"{R}/base_val_full", PL.PROT)
        PL.log(f"comparator {SEL.write_or_verify(comp_p, pl)}: {pl['comparator']} {json.dumps({k: round(v, 4) for k, v in pl['val_f1@0.3'].items()})}")
        PL.status("confirm_generation")
        PL.gen(f"{R}/confirm_base", PL.IDS.format("confirm"), "confirm", "official_long,concise", workers)
        sft_args = []
        for s in (17, 29, 43):
            j = json.load(open(sel[s]))
            PL.gen(f"{R}/confirm_sft_seed{s}", PL.IDS.format("confirm"), "confirm", "concise", workers, adapter=j["runs"][j["selected_run"]]["adapter_dir"])
            sft_args.append(f"{s}:{sel[s]}:{R}/confirm_sft_seed{s}")
        out = f"{R}/final/confirm_result.json"
        if os.path.exists(out):
            PL.log(f"{out} exists (not overwritten)")
        else:
            PL.sh([sys.executable, "-m", "rsna_diag.final_eval", "confirm", "--comparator", comp_p, "--extend", ext_p, "--conf-base",
                   f"{R}/confirm_base", "--protocol", PL.PROT, "--sft", *sft_args, "--out", out])
        PL.status("complete")
        PL.log("PIPELINE COMPLETE (rest runner)")
    finally:
        lk.release()


if __name__ == "__main__":
    main()
