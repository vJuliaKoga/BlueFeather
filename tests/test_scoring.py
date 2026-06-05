"""scoring（合算）のテスト（純粋関数・ネットワーク/DB不要）。"""

from app.engine.scoring import compute_rubric_score, compute_total_score


def test_rubric_score_example():
    weights = {
        "boundary_coverage": 1.5,
        "branch_coverage": 1.5,
        "state_transition": 1.0,
        "expected_clarity": 1.0,
    }
    item_scores = {
        "boundary_coverage": (3, 4),
        "branch_coverage": (2, 4),
        "state_transition": (4, 4),
        "expected_clarity": (3, 4),
    }
    assert abs(compute_rubric_score(item_scores, weights) - 72.5) < 1e-9


def test_total_score_example():
    assert abs(compute_total_score(72.5, 73.75, 0.7, 0.3) - 72.875) < 1e-9


def test_total_score_coverage_weight_zero_with_none():
    # coverage_weight=0 のとき coverage_score=None でも total == rubric_score。
    assert compute_total_score(80.0, None, 1.0, 0.0) == 80.0
