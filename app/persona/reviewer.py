"""BlueWing 語り層の呼び出し・抽出・検証・フォールバック（詳細設計§6.4）。

LLM を呼び、JSON を抽出・検証する。失敗時は安全に逃がす（落とさない）。
合否判定・total_score・coverage_score はここでは出さない（P4）。
OpenAI への接続は _call_llm の1か所に閉じ込める（テストで差し替え可能にするため）。
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

from app.config import get_settings
from app.db.repository import get_connection
from app.persona import prompts
from app.persona.schema import ReviewLLMOutput

# 再試行時に追記する指示（JSONのみで再出力させる）。
_RETRY_INSTRUCTION = "JSONのみで再出力してください。前後の説明やコードフェンスは付けないでください。"


@dataclass
class ReviewResult:
    status: str  # 'ok' | 'manual_check'
    parsed: ReviewLLMOutput | None
    raw_output: str


def _call_llm(messages: list[dict]) -> str:
    """OpenAI を呼び、本文テキストを返す薄いラッパ。呼び出しはここだけに閉じる。"""
    from openai import OpenAI

    settings = get_settings()
    client = OpenAI(api_key=settings.openai_api_key)
    resp = client.chat.completions.create(
        model=settings.openai_model,
        messages=messages,
        # JSON を要求するが、抽出・検証側はこれに依存しない。
        response_format={"type": "json_object"},
    )
    return resp.choices[0].message.content or ""


def _strip_code_fences(text: str) -> str:
    """先頭末尾のコードフェンス（``` や ```json）を除去する。"""
    s = text.strip()
    if s.startswith("```"):
        lines = s.splitlines()
        lines = lines[1:]  # 開始フェンス行（```/```json）を捨てる
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]  # 終了フェンス行を捨てる
        s = "\n".join(lines).strip()
    return s


def parse_llm_json(text: str) -> ReviewLLMOutput:
    """コードフェンス除去 → json.loads → ReviewLLMOutput 検証。失敗時は例外。"""
    cleaned = _strip_code_fences(text)
    data = json.loads(cleaned)
    return ReviewLLMOutput.model_validate(data)


def review_messages(messages: list[dict]) -> ReviewResult:
    """LLM 呼び出し → 検証。失敗時は1回だけ再試行し、なお失敗なら manual_check。"""
    raw = _call_llm(messages)
    try:
        return ReviewResult("ok", parse_llm_json(raw), raw)
    except Exception:
        pass

    # 1回だけ「JSONのみで再出力」を追記して再試行。
    retry_messages = messages + [{"role": "user", "content": _RETRY_INSTRUCTION}]
    raw2 = _call_llm(retry_messages)
    try:
        return ReviewResult("ok", parse_llm_json(raw2), raw2)
    except Exception:
        # 例外で落とさず、生テキストを残して手動確認に回す。
        return ReviewResult("manual_check", None, raw2)


def run_review(
    phase_key: str,
    artifact_body: str,
    coverage_summary: str | None = None,
) -> ReviewResult:
    """DB から phase 名と rubric_items を引き、メッセージを組んでレビューする。"""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT id, name FROM phases WHERE key = ?", (phase_key,)
        ).fetchone()
        if row is None:
            raise ValueError(f"未知のフェーズです: {phase_key}")
        phase_id, phase_name = row
        items = conn.execute(
            "SELECT item_key, description, max_score FROM rubric_items "
            "WHERE phase_id = ? ORDER BY id",
            (phase_id,),
        ).fetchall()
    finally:
        conn.close()

    rubric_items = [
        {"item_key": r[0], "description": r[1], "max_score": r[2]} for r in items
    ]
    messages = prompts.build_messages(
        phase_key=phase_key,
        phase_name=phase_name,
        rubric_items=rubric_items,
        artifact_body=artifact_body,
        coverage_summary=coverage_summary,
    )
    return review_messages(messages)


def _main() -> None:
    parser = argparse.ArgumentParser(description="BlueWing 語り層レビュー（実呼び出し）")
    parser.add_argument("--phase", required=True, help="フェーズキー（例: detailed_design）")
    parser.add_argument("--artifact", required=True, help="成果物 md のパス")
    parser.add_argument("--coverage", default=None, help="参考カバレッジ要約（任意）")
    args = parser.parse_args()

    body = Path(args.artifact).read_text(encoding="utf-8")
    result = run_review(args.phase, body, args.coverage)

    print(f"status={result.status}")
    if result.parsed is not None:
        # 冒頭だけ表示（点数や合否は文面に出ない想定）。
        print(result.parsed.acknowledgement[:80])
    else:
        print("要手動確認（manual_check）")


if __name__ == "__main__":
    _main()
