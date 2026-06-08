"""ルール遵守チェック（QA4AI・決定的・LLM非依存）。

BlueFeather の所見が、ペルソナのルール（点数表記を出さない・突き放さない・否定で
始めない）を守れているかを機械的に点検する。毎回でも回せる軽量チェック。
"""

from __future__ import annotations

import re

# 本文に出てはいけない点数表記（例: 「73点」「73 点」）。スコア行は除外して判定する。
_SCORE_PATTERN = re.compile(r"\d+\s*点")

# 突き放す断定の禁止語。
_FORBIDDEN_WORDS = ["不合格", "ダメ"]

# 否定の出だし（行頭・文頭で始めない）。
_NEGATIVE_OPENERS = ["いや", "でも", "だって"]


def check_rules(review_text: str, score_line: str | None = None) -> list[str]:
    """所見テキストのルール違反メッセージ一覧を返す（空ならOK）。決定的。

    score_line（エンジンが差し込む点数行）は本文から除外して点検する。
    """
    violations: list[str] = []

    # スコア行は正当に点数を含むため、本文から取り除いてから点検する。
    body = review_text or ""
    if score_line:
        body = body.replace(score_line, "")

    # 1. 本文に点数表記が無いこと。
    if _SCORE_PATTERN.search(body):
        violations.append("本文に点数表記（〜点）が含まれています。点数はエンジンが差し込む役割です。")

    # 2. 禁止語が無いこと。
    for w in _FORBIDDEN_WORDS:
        if w in body:
            violations.append(f"突き放す断定の語が含まれています: 「{w}」")

    # 3. 各文の出だしが否定で始まらないこと（改行・句点で文を区切る）。
    for sentence in re.split(r"[。\n]", body):
        s = sentence.strip()
        for opener in _NEGATIVE_OPENERS:
            if s.startswith(opener):
                violations.append(f"否定の出だしで始まる文があります: 「{opener}…」")
                break

    return violations
