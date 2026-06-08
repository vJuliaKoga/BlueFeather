"""gate（合否判定・所見合成）のテスト（純粋関数・ネットワーク/DB不要）。"""

import re

from app.engine.gate import compose_review, judge


def test_judge_almost():
    passed, line = judge(72.875, 80)
    assert passed is False
    assert "あと一歩" in line
    assert "73点" in line  # 表示は整数へ四捨五入


def test_judge_open_gate():
    passed, line = judge(92.125, 80)
    assert passed is True
    assert "開きます" in line
    assert "92点" in line


def test_compose_order_and_no_extra_score():
    ack = "丁寧に押さえられていますね。"
    _, score_line = judge(72.875, 80)
    findings = ["上限側の確認も添えてみませんか", "異常系の期待結果を明確に"]
    closing = "まずはここから、いってみませんか。"

    text = compose_review(ack, score_line, findings, closing)

    # 順序: 承認 → スコア行 → 指摘 → 結び
    assert text.index(ack) < text.index(score_line) < text.index(findings[0]) < text.index(closing)

    # スコア行以外に「N点」表記が無いこと（スコア行を除いた残りに数値+点が出ない）。
    rest = text.replace(score_line, "")
    assert re.search(r"\d+点", rest) is None

    # 技法レコメンド文（「〜が合うのではないかな」）は本文に重ねない（専用セクションへ一本化）。
    assert "が合うのではないか" not in text


def test_compose_addresses_by_name():
    text = compose_review("整理できていますね。", "", [], "", addressee="田中")
    assert text.startswith("田中さん、")


def test_compose_avoids_double_san():
    # 入力に「さん」が含まれていても二重「さんさん」にしない。
    text = compose_review("ありがとうございます。", "", [], "", addressee="佐藤さん")
    assert text.startswith("佐藤さん、")
    assert "さんさん" not in text
