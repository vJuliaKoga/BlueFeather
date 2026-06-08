"""grounding / judge のテスト（_call_llm を monkeypatch・実呼び出し無し）。"""

import json

from app.persona import reviewer
from app.qa4ai import grounding
from app.qa4ai.judge import judge_review

_FINDINGS = ["境界値の上限が抜けています", "状態遷移の戻りが未検証です"]


# --- grounding ----------------------------------------------------------------

def test_grounding_ok(monkeypatch):
    def fake(messages):
        return json.dumps(
            {
                "results": [
                    {"finding": _FINDINGS[0], "grounded": True, "reason": "本文に上限の記述あり"},
                    {"finding": _FINDINGS[1], "grounded": False, "reason": "本文に記述なし"},
                ]
            }
        )

    monkeypatch.setattr(reviewer, "_call_llm", fake)
    out = grounding.check_grounding("成果物本文", _FINDINGS)
    assert len(out) == 2
    assert all("grounded" in r for r in out)
    assert out[0]["grounded"] is True and out[1]["grounded"] is False


def test_grounding_hold_when_broken_twice(monkeypatch):
    monkeypatch.setattr(reviewer, "_call_llm", lambda messages: "これは壊れた応答です")
    out = grounding.check_grounding("成果物本文", _FINDINGS)
    # 落ちずに、各 finding が判定保留（grounded=None）で返る。
    assert len(out) == 2
    assert all(r["grounded"] is None for r in out)


def test_grounding_empty_findings_returns_empty(monkeypatch):
    # findings が空なら LLM を呼ばず空を返す。
    monkeypatch.setattr(reviewer, "_call_llm", lambda messages: (_ for _ in ()).throw(AssertionError("呼ぶべきでない")))
    assert grounding.check_grounding("本文", []) == []


# --- judge --------------------------------------------------------------------

def test_judge_ok(monkeypatch):
    def fake(messages):
        return json.dumps(
            {
                "specificity": 3,
                "actionability": 4,
                "persona_adherence": 4,
                "no_score_leak": 4,
                "comment": "具体的で実行可能",
                "overall": "良い所見です",
            }
        )

    monkeypatch.setattr(reviewer, "_call_llm", fake)
    res = judge_review("所見テキスト")
    assert res["status"] == "ok"
    assert res["specificity"] == 3 and res["actionability"] == 4


def test_judge_hold_when_broken(monkeypatch):
    monkeypatch.setattr(reviewer, "_call_llm", lambda messages: "壊れた応答")
    res = judge_review("所見テキスト")
    assert res["status"] == "hold"


def test_judge_hold_when_out_of_range(monkeypatch):
    # 軸スコアが範囲外（pydantic 検証に失敗）→ 再試行も同じ → 判定保留。
    bad = json.dumps(
        {"specificity": 9, "actionability": 2, "persona_adherence": 2, "no_score_leak": 2}
    )
    monkeypatch.setattr(reviewer, "_call_llm", lambda messages: bad)
    res = judge_review("所見テキスト")
    assert res["status"] == "hold"
