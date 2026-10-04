"""GT-bounded DP matching for detector predictions (many candidates, GT<=4).

Same semantics as metrics.match: max-cardinality one-to-one matching at IoU>=thr,
tie-break by max total IoU, then lexicographically-smallest (gt-order) pred index tuple.
Complexity O(P * 2^G) instead of metrics.match's O((P+1)^G) recursion, for use when P is large
(detector: up to 100 candidates) and G (GT count) is small (<=4 in this dataset).
"""
import numpy as np

from . import metrics as M


def bounded_match(pred, gt, thr, max_gt=4):
    """returns list[(gi, pi)] identical (as a set of pairs achieving the same optimal key) to metrics.match,
    for len(gt) <= max_gt. Raises ValueError if len(gt) > max_gt (no silent truncation)."""
    g = len(gt)
    if g > max_gt:
        raise ValueError(f"len(gt)={g} exceeds max_gt={max_gt}; no truncation permitted")
    if g == 0 or not pred:
        return []
    p = len(pred)
    iou_mat = [[M.iou(pred[pi], gt[gi]) for pi in range(p)] for gi in range(g)]
    ok = [[iou_mat[gi][pi] >= thr for pi in range(p)] for gi in range(g)]

    n_masks = 1 << g
    # dp[pi][mask] = (best_card, best_iou, choice_pi_or_None) achievable using pred[0..pi-1] with gt subset `mask` matched
    # We do forward DP over pred index, mask = set of gt already matched.
    NEG = (-1, -1.0)
    dp = [dict() for _ in range(p + 1)]
    dp[0][0] = (0, 0.0)
    parent = [dict() for _ in range(p + 1)]
    for pi in range(p):
        cur = dp[pi]
        nxt = dp[pi + 1]
        for mask, (card, tot) in cur.items():
            # option: skip pred[pi]
            key = mask
            if key not in nxt or (card, tot) > nxt[key]:
                nxt[key] = (card, tot)
                parent[pi + 1][key] = (mask, None)
            # option: use pred[pi] to match some unmatched gi with ok
            for gi in range(g):
                bit = 1 << gi
                if mask & bit:
                    continue
                if not ok[gi][pi]:
                    continue
                nmask = mask | bit
                ncard, ntot = card + 1, tot + iou_mat[gi][pi]
                cand = (ncard, ntot)
                if nmask not in nxt or cand > nxt[nmask]:
                    nxt[nmask] = cand
                    parent[pi + 1][nmask] = (mask, gi)
    # pick best mask at pi=p
    best_mask, best_val = None, None
    for mask, val in dp[p].items():
        if best_val is None or val > best_val:
            best_val, best_mask = val, mask
    if best_mask is None:
        return []
    # backtrack to get one optimal assignment; among ties in (card,tot) our forward DP already
    # prefers larger tot at equal card via strict '>' comparisons, but pred-index tie-break
    # (lexicographically smallest gt-order pred tuple) requires care: metrics.match tie-breaks by
    # exploring pred indices in ascending order and only replacing on strict improvement, matching
    # gt in order 0..g-1. Our DP explores pred left-to-right and only takes a match if it strictly
    # improves (card, tot); since ties are strict '>' we keep the *first found* (leftmost / smallest
    # pred-index) assignment for a given (card,tot), consistent with metrics.match's preference for
    # smaller pred indices first in its search order restricted to fixed gt order.
    pairs = []
    pi, mask = p, best_mask
    while pi > 0:
        pmask, gi = parent[pi][mask]
        if gi is not None:
            pairs.append((gi, pi - 1))
        mask = pmask
        pi -= 1
    pairs.sort()
    return pairs
