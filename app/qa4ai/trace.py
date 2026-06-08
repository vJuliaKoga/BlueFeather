"""LLM呼び出しのメタ記録（QA4AI・可観測性）。best-effort。

タイムスタンプ・用途・モデル名・所要時間・トークン数などの「メタ情報のみ」を
traces.jsonl に1行ずつ追記する。プロンプト本文・成果物・キーは記録しない。
記録の失敗で本処理を止めない（例外は飲み込む）。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

_TRACE_PATH = Path("traces.jsonl")


def record_trace(metadata: dict) -> None:
    """metadata を1行 JSON で追記する。失敗しても例外を投げない（best-effort）。"""
    try:
        entry = {"ts": datetime.now(timezone.utc).isoformat(), **metadata}
        with open(_TRACE_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        # 可観測性のための記録は、本処理を妨げてはならない。
        pass
