"""LLM-as-judge（QA4AI）。

別の LLM が BlueFeather の所見の質を軸ごとに採点する。本体の採点・合否は上書きしない
（独立した点検結果）。LLM 呼び出しは reviewer._call_llm を再利用（差し替え可能）。
"""

from __future__ import annotations

import json

from pydantic import BaseModel, field_validator

from app.persona import reviewer


class JudgeScores(BaseModel):
    """judge の軸別スコア（各 0〜4）とコメント・総評。"""

    specificity: int          # 具体性
    actionability: int        # 実行可能性
    persona_adherence: int    # ペルソナ遵守（承認から入る・否定なし・代替案あり）
    no_score_leak: int        # 点数や合否が文面に漏れていないか
    comment: str = ""
    overall: str = ""

    @field_validator("specificity", "actionability", "persona_adherence", "no_score_leak")
    @classmethod
    def _range(cls, v: int) -> int:
        if not (0 <= v <= 4):
            raise ValueError("各軸スコアは 0〜4 の範囲である必要があります")
        return v


_SYSTEM = """\
あなたはレビュー文の品質を評価する審査員です。
レビューAI（BlueFeather）が書いた「所見」を読み、次の4軸を各 0〜4 で採点します。
- specificity（具体性）: 指摘が具体的で曖昧でないか。
- actionability（実行可能性）: 次の一歩として実行できる助言になっているか。
- persona_adherence（ペルソナ遵守）: 承認から入り、否定で始めず、必ず代替案を添えているか。
- no_score_leak（点数・合否の非漏洩）: 具体的な点数や合否が文面に書かれていないほど高い。
JSON のみを返します。前後の説明やコードフェンス（```）は一切付けません。
"""

_USER_TEMPLATE = """\
# 評価対象の所見
----------------------------------------
{review_text}
----------------------------------------

# 出力（このスキーマの JSON のみ）
{{
  "specificity": 0,
  "actionability": 0,
  "persona_adherence": 0,
  "no_score_leak": 0,
  "comment": "<軸ごとの簡潔な所感>",
  "overall": "<総評>"
}}
"""

_RETRY = "JSONのみで再出力してください。前後の説明やコードフェンスは付けないでください。"


def _build_messages(review_text: str) -> list[dict]:
    return [
        {"role": "system", "content": _SYSTEM},
        {"role": "user", "content": _USER_TEMPLATE.format(review_text=review_text)},
    ]


def _parse(text: str) -> JudgeScores:
    s = text.strip()
    if s.startswith("```"):
        lines = s.splitlines()[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        s = "\n".join(lines).strip()
    return JudgeScores.model_validate(json.loads(s))


def judge_review(review_text: str) -> dict:
    """所見を軸別に採点した dict を返す。失敗時は判定保留で落とさない。

    成功: {"status": "ok", "specificity":…, …, "comment":…, "overall":…}
    失敗: {"status": "hold", "reason": …}
    """
    messages = _build_messages(review_text)
    raw = reviewer._call_llm(messages)
    try:
        return {"status": "ok", **_parse(raw).model_dump()}
    except Exception:
        pass

    raw2 = reviewer._call_llm(messages + [{"role": "user", "content": _RETRY}])
    try:
        return {"status": "ok", **_parse(raw2).model_dump()}
    except Exception:
        return {"status": "hold", "reason": "判定保留（応答を解釈できませんでした）"}
