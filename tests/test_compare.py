"""前回比較・デグレ検出のテスト（決定的・ネットワーク/LLM 非依存）。

compute_comparison は純粋関数として直接検証する。
compare_phase の「比較不可」分岐は repository 呼び出しを monkeypatch で差し替える。
"""

import json

from app.engine import compare
from app.engine.compare import compute_comparison


def _inputs():
    prev = {
        "items": {"boundary": (3, 4), "branch": (3, 4), "state": (4, 4), "expected": (3, 4)},
        "coverage": {"境界値": 0.75, "同値": 0.50},
        "rubric_score": 60.0,
        "coverage_score": 70.0,
        "total_score": 60.0,
    }
    cur = {
        "items": {"boundary": (4, 4), "branch": (2, 4), "state": (4, 4), "expected": (3, 4)},
        "coverage": {"境界値": 1.00, "同値": 0.25},
        "rubric_score": 65.0,
        "coverage_score": 75.0,
        "total_score": 65.0,
    }
    return prev, cur


def test_item_improved_and_degraded():
    prev, cur = _inputs()
    res = compute_comparison(prev, cur)
    # boundary は 3→4 で改善、branch は 3→2 でデグレ。
    assert "boundary" in res["improved"]
    assert "branch" in res["degraded"]
    # 変化なしは direction=same で improved/degraded に入らない。
    assert res["item_deltas"]["state"]["direction"] == "same"
    assert res["item_deltas"]["expected"]["direction"] == "same"
    assert "state" not in res["degraded"] and "state" not in res["improved"]


def test_total_score_delta_sign():
    prev, cur = _inputs()
    res = compute_comparison(prev, cur)
    td = res["score_deltas"]["total_score"]
    assert td["delta"] == 5.0
    assert td["delta"] > 0


def test_coverage_improved_and_degraded():
    prev, cur = _inputs()
    res = compute_comparison(prev, cur)
    # 境界値 0.75→1.00 は改善、同値 0.50→0.25 はデグレ。
    assert "境界値" in res["improved"]
    assert "同値" in res["degraded"]
    assert abs(res["coverage_deltas"]["境界値"]["delta"] - 0.25) < 1e-9
    assert res["coverage_deltas"]["同値"]["delta"] < 0


def test_summary_mentions_degraded():
    prev, cur = _inputs()
    res = compute_comparison(prev, cur)
    # デグレありの総括にはデグレ項目名が含まれる。
    assert "branch" in res["summary"] or "同値" in res["summary"]


def test_no_change_summary():
    base = {
        "items": {"a": (3, 4)},
        "coverage": {},
        "rubric_score": 50.0,
        "coverage_score": None,
        "total_score": 50.0,
    }
    res = compute_comparison(base, dict(base, items={"a": (3, 4)}))
    assert res["improved"] == [] and res["degraded"] == []
    assert res["summary"] == "前回から大きな変化はないようです。"


# --- compare_phase の比較不可分岐（repository を monkeypatch） -------------------

class _DummyConn:
    def close(self):
        pass


def _row(round_no, status, breakdown=None):
    return {
        "review_id": round_no, "round_no": round_no,
        "rubric_score": 60.0, "coverage_score": 70.0, "total_score": 60.0,
        "status": status, "rubric_breakdown": json.dumps(breakdown or []),
    }


def test_compare_phase_incomparable_when_less_than_two(monkeypatch):
    monkeypatch.setattr(compare, "get_connection", lambda: _DummyConn())
    monkeypatch.setattr(compare, "get_last_two_reviews", lambda conn, key: [_row(1, "ok")])
    res = compare.compare_phase("detailed_design")
    assert res["comparable"] is False


def test_compare_phase_incomparable_when_manual_check(monkeypatch):
    monkeypatch.setattr(compare, "get_connection", lambda: _DummyConn())
    rows = [_row(2, "manual_check"), _row(1, "ok")]
    monkeypatch.setattr(compare, "get_last_two_reviews", lambda conn, key: rows)
    res = compare.compare_phase("detailed_design")
    assert res["comparable"] is False


def test_compare_phase_comparable(monkeypatch):
    monkeypatch.setattr(compare, "get_connection", lambda: _DummyConn())
    cur = _row(2, "ok", [{"item_key": "boundary", "score": 4, "max_score": 4}])
    prev = _row(1, "ok", [{"item_key": "boundary", "score": 3, "max_score": 4}])
    monkeypatch.setattr(compare, "get_last_two_reviews", lambda conn, key: [cur, prev])
    monkeypatch.setattr(compare, "get_coverage_metrics", lambda conn, rid: [])
    res = compare.compare_phase("detailed_design")
    assert res["comparable"] is True
    assert res["prev_round_no"] == 1 and res["cur_round_no"] == 2
    assert "boundary" in res["improved"]
