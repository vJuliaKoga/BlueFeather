"""gate（合否判定・所見合成）のテスト（純粋関数・ネットワーク/DB不要）。"""

import re

from app.engine.gate import compose_review, judge
from app.persona.schema import TechniqueRecommendation


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
    recos = [TechniqueRecommendation(target="年齢入力欄", recommended_technique="境界値分析", reason="範囲制約があるため")]
    closing = "まずはここから、いってみませんか。"

    text = compose_review(ack, score_line, findings, recos, closing)

    # 順序: 承認 → スコア行 → 指摘 → 結び
    assert text.index(ack) < text.index(score_line) < text.index(findings[0]) < text.index(closing)

    # スコア行以外に「N点」表記が無いこと（スコア行を除いた残りに数値+点が出ない）。
    rest = text.replace(score_line, "")
    assert re.search(r"\d+点", rest) is None
