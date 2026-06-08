"""根拠の妥当性チェック（QA4AI・LLM二段検査）。

BlueFeather の指摘（findings）が成果物本文に基づくか（でっち上げが無いか）を、別の
LLM 呼び出しで点検する。採点・合否には一切影響しない（点検のみ）。
LLM 呼び出しは reviewer._call_llm を再利用（テストで差し替え可能）。
"""

from __future__ import annotations

import json

from app.persona import reviewer

_SYSTEM = """\
あなたはレビュー文の事実性を点検する校閲者です。
「成果物本文」と、レビューAIが出した「指摘」のリストを受け取り、各指摘が成果物本文に
根拠を持つか（でっち上げでないか）を判定します。
JSON のみを返します。前後の説明やコードフェンス（```）は一切付けません。
"""

_USER_TEMPLATE = """\
# 成果物本文
----------------------------------------
{artifact_body}
----------------------------------------

# レビューAIの指摘（各々について成果物に根拠があるか判定）
{findings_block}

# 出力（このスキーマの JSON のみ）
{{
  "results": [
    {{ "finding": "<指摘の原文>", "grounded": true, "reason": "<成果物のどこに基づく/基づかないか>" }}
  ]
}}
"""

_RETRY = "JSONのみで再出力してください。前後の説明やコードフェンスは付けないでください。"


def _build_messages(artifact_body: str, findings: list[str]) -> list[dict]:
    findings_block = "\n".join(f"- {f}" for f in findings)
    user = _USER_TEMPLATE.format(artifact_body=artifact_body, findings_block=findings_block)
    return [
        {"role": "system", "content": _SYSTEM},
        {"role": "user", "content": user},
    ]


def _parse(text: str) -> list[dict]:
    """応答 JSON を {finding, grounded, reason} の一覧に整える。失敗時は例外。"""
    s = text.strip()
    if s.startswith("```"):
        lines = s.splitlines()[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        s = "\n".join(lines).strip()
    data = json.loads(s)
    results = data["results"]
    out: list[dict] = []
    for r in results:
        out.append(
            {
                "finding": str(r["finding"]),
                "grounded": bool(r["grounded"]),
                "reason": str(r.get("reason", "")),
            }
        )
    return out


def check_grounding(artifact_body: str, findings: list[str]) -> list[dict]:
    """各 finding に {finding, grounded, reason} を返す。失敗時は判定保留で落とさない。"""
    if not findings:
        return []

    messages = _build_messages(artifact_body, findings)
    raw = reviewer._call_llm(messages)
    try:
        return _parse(raw)
    except Exception:
        pass

    # 1回だけ「JSONのみで再出力」を促して再試行。
    raw2 = reviewer._call_llm(messages + [{"role": "user", "content": _RETRY}])
    try:
        return _parse(raw2)
    except Exception:
        # なお失敗なら、各 finding を判定保留にして返す（落とさない）。
        return [
            {"finding": f, "grounded": None, "reason": "判定保留（応答を解釈できませんでした）"}
            for f in findings
        ]
