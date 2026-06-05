"""総合点の合算（関守エンジン・詳細設計§5.1）。

純粋関数のみ。DB・LLM・IO には触れない。合否判定（閾値比較）は gate.py。
"""

from __future__ import annotations


def compute_rubric_score(
    item_scores: dict[str, tuple[int, int]],
    rubric_items: dict[str, float],
) -> float:
    """項目スコアと重みから rubric_score（0〜100）を算出する。

    item_scores: item_key -> (score, max_score)
    rubric_items: item_key -> weight
    rubric_score = 100 × Σ(weight_i × score_i/max_score_i) / Σ(weight_i)
    対応する weight が無い item_key は計算対象外（突き合わせの取れない項目は無視する）。
    """
    weighted_sum = 0.0
    weight_total = 0.0
    for item_key, (score, max_score) in item_scores.items():
        weight = rubric_items.get(item_key)
        if weight is None or max_score == 0:
            # weight 未定義、または max_score=0（0除算回避）の項目は対象外。
            continue
        weighted_sum += weight * (score / max_score)
        weight_total += weight

    if weight_total == 0:
        return 0.0
    return 100 * weighted_sum / weight_total


def compute_total_score(
    rubric_score: float,
    coverage_score: float | None,
    rubric_weight: float,
    coverage_weight: float,
) -> float:
    """total_score = rubric_weight × rubric_score + coverage_weight × coverage_score。

    coverage_weight==0 のとき coverage_score は None でもよく、その項は 0 とする。
    """
    coverage_term = 0.0
    if coverage_weight != 0:
        # 重みが効くときだけ coverage_score を使う（None なら 0 扱い）。
        coverage_term = coverage_weight * (coverage_score or 0.0)
    return rubric_weight * rubric_score + coverage_term
