"""iter_107 순수 기하 함수: axis-aligned xyxy box 집합의 정확한 합집합 면적, coverage, union IoU, 표준 matching recall.

좌표는 원본 영상 기준 정규화 xyxy. 모델·GPU를 쓰지 않는다. 합집합은 좌표 압축으로 정확히 계산한다(외접 사각형 근사 아님).
"""
import itertools


def valid_box(b):
    return len(b) == 4 and all(isinstance(v, (int, float)) for v in b) and b[2] > b[0] and b[3] > b[1]


def union_area(boxes):
    boxes = [b for b in boxes if b[2] > b[0] and b[3] > b[1]]
    if not boxes:
        return 0.0
    xs = sorted({v for b in boxes for v in (b[0], b[2])})
    total = 0.0
    for x0, x1 in zip(xs, xs[1:]):
        spans = sorted((b[1], b[3]) for b in boxes if b[0] <= x0 and b[2] >= x1)
        cur_end, h = None, 0.0
        for lo, hi in spans:
            if cur_end is None or lo > cur_end:
                h += hi - lo
                cur_end = hi
            elif hi > cur_end:
                h += hi - cur_end
                cur_end = hi
        total += (x1 - x0) * h
    return total


def clip_to(b, g):
    return [max(b[0], g[0]), max(b[1], g[1]), min(b[2], g[2]), min(b[3], g[3])]


def inter_union_with_box(pred, g):
    """P∩g 면적 (P는 box 집합의 합집합)."""
    cl = [clip_to(b, g) for b in pred]
    return union_area([c for c in cl if c[2] > c[0] and c[3] > c[1]])


def area(b):
    return max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])


def coverage(pred, g):
    """area(P∩g)/area(g). 예측이 없으면 0."""
    if not pred:
        return 0.0
    return inter_union_with_box(pred, g) / area(g)


def union_iou(pred, gts):
    ua, ub = union_area(pred), union_area(gts)
    if ua == 0 or ub == 0:
        return 0.0
    inter = union_area_inter(pred, gts)
    return inter / (ua + ub - inter)


def union_area_inter(A, B):
    """두 box 집합 합집합의 교집합 면적 = ua + ub - union(A∪B)."""
    return union_area(A) + union_area(B) - union_area(list(A) + list(B))


def outside_fraction(pred, gts):
    """예측 합집합 면적 중 gts 합집합 밖 비율. 예측 면적 0이면 None. 임상 FP가 아니다."""
    ua = union_area(pred)
    if ua == 0:
        return None
    return 1.0 - union_area_inter(pred, gts) / ua


def iou(a, b):
    iw = min(a[2], b[2]) - max(a[0], b[0])
    ih = min(a[3], b[3]) - max(a[1], b[1])
    inter = max(0.0, iw) * max(0.0, ih)
    ua = area(a) + area(b) - inter
    return inter / ua if ua > 0 else 0.0


def match_recall(pred, gts, thr=0.3):
    """표준 일대일 matching: 최대 cardinality(IoU>=thr). 소규모(<=6 GT)이므로 전수. returns (n_matched, n_gt, n_pred)."""
    n = len(gts)
    best = 0
    P = len(pred)
    if P == 0 or n == 0:
        return 0, n, P
    ok = [[iou(p, g) >= thr for g in gts] for p in pred]

    def rec(i, used):
        if i == P:
            return 0
        r = rec(i + 1, used)
        for j in range(n):
            if ok[i][j] and not (used >> j) & 1:
                r = max(r, 1 + rec(i + 1, used | (1 << j)))
        return r
    best = rec(0, 0)
    return best, n, P


def pairwise_disjoint(boxes):
    return all(iou(a, b) == 0 and not (min(a[2], b[2]) > max(a[0], b[0]) and min(a[3], b[3]) > max(a[1], b[1]))
               for a, b in itertools.combinations(boxes, 2))
