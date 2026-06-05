"""review_messages のフォールバック制御テスト（_call_llm を monkeypatch）。

DB・ネットワーク・キーは使わない。messages はダミーで良い。
"""

import json

from app.persona import reviewer

_DUMMY_MESSAGES = [{"role": "user", "content": "dummy"}]


def _valid_json_text():
    return json.dumps(
        {
            "rubric_scores": [
                {
                    "item_key": "k",
                    "score": 2,
                    "max_score": 4,
                    "rationale": "r",
                    "findings": [],
                }
            ],
            "acknowledgement": "ack",
            "closing": "close",
        }
    )


def test_ok_on_valid_json(monkeypatch):
    monkeypatch.setattr(reviewer, "_call_llm", lambda messages: _valid_json_text())
    result = reviewer.review_messages(_DUMMY_MESSAGES)
    assert result.status == "ok"
    assert result.parsed is not None


def test_ok_on_fenced_json(monkeypatch):
    fenced = "```json\n" + _valid_json_text() + "\n```"
    monkeypatch.setattr(reviewer, "_call_llm", lambda messages: fenced)
    result = reviewer.review_messages(_DUMMY_MESSAGES)
    assert result.status == "ok"
    assert result.parsed is not None


def test_manual_check_when_both_broken(monkeypatch):
    monkeypatch.setattr(reviewer, "_call_llm", lambda messages: "これは壊れた応答です")
    result = reviewer.review_messages(_DUMMY_MESSAGES)
    assert result.status == "manual_check"
    assert result.parsed is None
    assert result.raw_output == "これは壊れた応答です"


def test_retry_succeeds_second_time(monkeypatch):
    # 1回目は壊れ、2回目は正常を返す。
    calls = {"n": 0}

    def fake(messages):
        calls["n"] += 1
        return "壊れ" if calls["n"] == 1 else _valid_json_text()

    monkeypatch.setattr(reviewer, "_call_llm", fake)
    result = reviewer.review_messages(_DUMMY_MESSAGES)
    assert result.status == "ok"
    assert calls["n"] == 2
