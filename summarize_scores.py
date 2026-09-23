"""legacy/eval_results/scores.json을 과제별 한 표(Markdown)로 정리한다. 재채점·추론 없음."""
import argparse
import json
from pathlib import Path

DEFAULT_IN = Path(__file__).resolve().parent.parent / "legacy" / "eval_results" / "scores.json"

G2_NAMES = {"A_multilabel": "A multilabel", "B_binary": "B binary", "C_openended": "C open-ended"}
G3_NAMES = {"1_grid": "grid", "2_bbox": "bbox", "3_desc": "desc", "4_name": "name"}


def f(v):
    """비율은 0-1 척도 소수 4자리, 누락/null은 N/A (0으로 바꾸지 않음)."""
    if v is None:
        return "N/A"
    if isinstance(v, float):
        return f"{v:.4f}"
    return str(v)


def valid(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and v == v


def get(d, k):
    return d.get(k)


def aux(d, keys):
    return ", ".join(f"{k}={f(get(d, k))}" for k in keys)


def rows(scores):
    out = []
    for ds, m in scores["G1"].items():
        out.append(("G1", ds, "VQA", f"{f(get(m, 'n'))} QA", "token_f1", f(get(m, "token_f1")),
                    f"exact_match={f(get(m, 'exact_match'))}, closed_accuracy={f(get(m, 'closed_accuracy'))}"
                    f" (n_closed_yesno={f(get(m, 'n_closed_yesno'))})"))
    for ds, methods in scores["G2"].items():
        for key, m in methods.items():
            if key == "B_binary":
                out.append(("G2", ds, G2_NAMES[key], f"{f(get(m, 'n'))} image-label 질의 (n_scored={f(get(m, 'n_scored'))})",
                            "accuracy", f(get(m, "accuracy")),
                            aux(m, ["sensitivity_recall", "specificity", "precision", "n_unparsed", "n_skipped_uncertain"])))
            else:
                out.append(("G2", ds, G2_NAMES[key], f"{f(get(m, 'n'))} 영상", "micro_f1", f(get(m, "micro_f1")),
                            aux(m, ["micro_precision", "micro_recall"])))
    for ds, methods in scores["G3"].items():
        for key, m in methods.items():
            name = G3_NAMES[key]
            n = f"{f(get(m, 'n'))} 영상"
            if name == "grid":
                r = ("accuracy_main_lesion", aux(m, ["accuracy_any_lesion", "n_unparsed", "random_baseline",
                                                      "always_center_baseline", "majority_cell_baseline"]))
            elif name == "bbox":
                n += f" (n_parsed={f(get(m, 'n_parsed'))})"
                r = ("mean_iou", aux(m, ["iou@0.3", "iou@0.5", "whole_image_baseline_iou"]))
            elif name == "desc":
                r = ("side_accuracy_radiological", aux(m, ["side_accuracy_image_frame", "vertical_accuracy",
                                                            "name_accuracy_in_description"]))
            else:
                r = ("name_accuracy", "")
                if ds == "deeplesion_ct":
                    r = (r[0], "주석: docs에 부위명 정답과 진단명 질문 불일치 기록")
            out.append(("G3", ds, name, n, r[0], f(get(m, r[0])), r[1]))
    return out


def report(scores):
    rs = rows(scores)
    head = ["group", "dataset", "method", "n / 단위", "주요 metric", "값", "보조 metric·분모·기준선"]
    lines = ["# scores.json 과제별 성능 요약", "",
             "값은 원본 JSON 그대로(재채점 없음). 주요 metric이 서로 달라 행 간 전역 순위는 계산하지 않는다.",
             "n의 단위는 과제별로 다르며(QA, image-label 질의, 영상) 독립 영상 수가 아니므로 합산하지 않는다.", "",
             "| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    lines += ["| " + " | ".join(r) + " |" for r in rs]
    bb = {ds: m["2_bbox"] for ds, m in scores["G3"].items()
          if isinstance(m, dict) and isinstance(m.get("2_bbox"), dict) and valid(m["2_bbox"].get("mean_iou"))}
    if not bb:
        lines += ["", "## 최저 성능 과제: 선정 불가", "",
                  "- 유효한 숫자 bbox mean_iou가 있는 항목이 없어 최저 과제를 선정하지 않았다 (누락·null은 후보에서 제외)."]
        return "\n".join(lines) + "\n"
    low = min(bb, key=lambda d: bb[d]["mean_iou"])
    b = bb[low]
    others = ", ".join(f"{d} {f(bb[d]['mean_iou'])}" for d in bb if d != low)
    head_txt = f"## 최저 성능 과제: {low} bbox (직접 bbox 추정)" if len(bb) > 1 else f"## bbox 후보 1개: {low} (비교 대상 부족)"
    if len(bb) > 1:
        crit = (f"같은 metric(bbox mean_iou)을 쓰는 유효 후보 {len(bb)}개 데이터셋 중 최저값이다")
    else:
        crit = "유효한 bbox mean_iou 후보가 이 하나뿐이라 다른 과제보다 낮다고 판단할 수 없다"
    wb = b.get("whole_image_baseline_iou")
    if valid(wb):
        base = f"전체영상 기준선 {f(wb)} (mean_iou - 기준선 = {b['mean_iou'] - wb:+.4f})."
    else:
        base = f"전체영상 기준선 {f(wb)}."
    lines += ["", head_txt, "",
              f"- 선정 기준: {crit} "
              f"(mean_iou={f(b['mean_iou'])}, n_parsed={f(b.get('n_parsed'))}/{f(b.get('n'))}, "
              f"iou@0.3={f(b.get('iou@0.3'))}, iou@0.5={f(b.get('iou@0.5'))}"
              + (f"; 다른 데이터셋: {others}" if others else "") + "). "
              + base + " 다른 metric(accuracy, F1)과 섞은 전역 순위가 아니다."]
    if low == "deeplesion_ct":
        lines += [
              "- 이유(docs 근거의 해석): `legacy/docs/MEDGEMMA_평가_전체정리.txt` 맨 앞 '중대 정정'(14-43행)에 따르면 "
              "이 초기 평가는 공식 형식(y-first, 0-1000 스케일, JSON box_2d)이 아닌 임의의 xyxy 0-1 형식을 썼고, "
              "'좌표 출력 능력이 없다'는 결론은 철회됐다. "
              "`legacy/docs/MEDGEMMA_1.5_평가정리.txt` 8장(389-436행)·12장(715-746행)은 이 비공식 형식에서 "
              "축대칭 템플릿 박스(80%) 등 영상 무관 출력으로 퇴화했고, 공식 형식에서도 학습 범주(해부구조) 밖의 "
              "CT 병변은 IoU 약 0.007로 낮았다고 기록한다. 12장 한계 3은 8bit 윈도잉 PNG(DeepLesion)로는 "
              "CT 공식 전처리를 적용할 수 없다는 입력 조건 제약도 적는다.",
              f"- 한계: 위 0.007은 별도의 공식 형식 재평가(n=20, docs 인용)이며 이 표의 현재 JSON 값 "
              f"{f(b['mean_iou'])}(n={f(b.get('n'))}, 초기 비공식 형식)을 대체하지 않는다. "
              "원인별 기여도는 검증되지 않았고 소표본이다. "
              "모델이 CT 위치를 못 낸다는 능력 부재 주장이나 3D 입력이 해결한다는 주장으로 읽으면 안 된다."]
    else:
        lines += [f"- 이유: {low}의 낮은 bbox 성능 원인은 이 스크립트에서 docs 근거로 확인하지 않았다 "
                  "(DeepLesion CT 설명은 이 과제에 적용하지 않음). 원인별 기여도는 미검증이다."]
    lines.append("")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", type=Path, default=DEFAULT_IN)
    ap.add_argument("--output", type=Path, default=None)
    a = ap.parse_args()
    text = report(json.loads(a.input.read_text()))
    print(text)
    if a.output:
        a.output.parent.mkdir(parents=True, exist_ok=True)
        a.output.write_text(text)


if __name__ == "__main__":
    main()
