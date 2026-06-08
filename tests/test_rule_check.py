"""ルール遵守チェックのテスト（決定的・LLM非依存）。"""

from app.qa4ai.rule_check import check_rules


def test_score_text_is_violation():
    # 本文に点数表記があれば違反。
    assert check_rules("いま73点。あと一歩です。")


def test_forbidden_word_is_violation():
    assert any("不合格" in m for m in check_rules("これは不合格の出来です。"))


def test_negative_opener_is_violation():
    assert any("でも" in m for m in check_rules("でも、ここは直したほうがよいです。"))


def test_healthy_review_has_no_violation():
    text = (
        "ていねいに整理できていますね。よくここまで進めました。\n"
        "この観点なら、境界の前後を一緒に見てみませんか。\n"
        "まずはここから、いってみませんか。"
    )
    assert check_rules(text) == []


def test_score_line_is_excluded():
    # スコア行に含まれる点数は違反にしない（本文から除外して点検）。
    score_line = "いま73点。合格ラインまであと一歩です。"
    text = "よくやりましたね。\n" + score_line + "\nまずはここから。"
    assert check_rules(text, score_line) == []
