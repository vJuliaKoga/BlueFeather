"""coverage 計算のテスト（決定的・ネットワーク非依存）。"""

from app.engine.coverage import compute_coverage
from app.ingest.testcase_loader import Case, Target


def _load_samples():
    from app.ingest.testcase_loader import load_from_csv

    return load_from_csv("samples/targets.csv", "samples/cases.csv")


def test_coverage_score_and_rates():
    targets, cases = _load_samples()
    result = compute_coverage(targets, cases)
    rates = {tc.technique: tc.rate for tc in result.by_technique}
    assert rates["境界値分析"] == 0.75
    assert rates["デシジョンテーブル"] == 0.50
    assert rates["状態遷移"] == 1.00
    assert rates["同値分割"] == 1.00
    assert abs(result.coverage_score - 73.75) < 1e-9


def test_zero_total_technique_excluded():
    # デシジョンテーブルの target を持たない入力。該当技法は内訳から除外される。
    targets = [
        Target("B1", "境界値分析", "age", "a", True, ""),
        Target("B2", "境界値分析", "age", "b", True, ""),
    ]
    cases = [Case("T1", "境界値分析", "", "in", "exp", ["B1"], "")]
    result = compute_coverage(targets, cases)
    techniques = {tc.technique for tc in result.by_technique}
    assert "デシジョンテーブル" not in techniques
    assert "境界値分析" in techniques


def test_deterministic():
    targets, cases = _load_samples()
    r1 = compute_coverage(targets, cases)
    r2 = compute_coverage(targets, cases)
    assert r1.coverage_score == r2.coverage_score
    assert [(t.technique, t.covered, t.total, t.rate) for t in r1.by_technique] == [
        (t.technique, t.covered, t.total, t.rate) for t in r2.by_technique
    ]
