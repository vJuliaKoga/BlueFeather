"""採点の安定性測定（QA4AI・CLI）。

同一の成果物を N 回採点し、total_score と rubric_score のばらつき（平均・標準偏差・範囲）を
測る再現性チェック。DB には保存しない（本体の履歴を汚さない）。
コスト: N 回の LLM 呼び出しが発生する（実キーが必要）。
"""

from __future__ import annotations

import argparse
import statistics
from pathlib import Path

from app.db.repository import get_connection, get_phase, get_rubric_items
from app.engine.scoring import compute_rubric_score, compute_total_score
from app.persona import reviewer


def _score_once(phase_key: str, body: str, phase: dict, weights: dict) -> tuple[float, float] | None:
    """1回採点して (rubric_score, total_score) を返す。manual_check は None。"""
    result = reviewer.run_review(phase_key, body)
    if result.status != "ok" or result.parsed is None:
        return None
    item_scores = {rs.item_key: (rs.score, rs.max_score) for rs in result.parsed.rubric_scores}
    rubric_score = compute_rubric_score(item_scores, weights)
    # 安定性測定では rubric の揺れを見る（カバレッジは決定的なので None=0 扱い）。
    total = compute_total_score(
        rubric_score, None, phase["rubric_weight"], phase["coverage_weight"]
    )
    return rubric_score, total


def _stats(values: list[float]) -> dict | None:
    if not values:
        return None
    return {
        "mean": round(statistics.fmean(values), 2),
        "stdev": round(statistics.pstdev(values), 2) if len(values) > 1 else 0.0,
        "min": round(min(values), 2),
        "max": round(max(values), 2),
    }


def _main() -> None:
    parser = argparse.ArgumentParser(
        description="同一成果物をN回採点しスコアのばらつきを測る（N回のLLM呼び出しコストが発生）"
    )
    parser.add_argument("--phase", required=True, help="フェーズキー（例: detailed_design）")
    parser.add_argument("--artifact", required=True, help="成果物 md のパス")
    parser.add_argument("--runs", type=int, default=5, help="繰り返し回数（既定5・各回がLLMコスト）")
    args = parser.parse_args()

    body = Path(args.artifact).read_text(encoding="utf-8")
    conn = get_connection()
    try:
        phase = get_phase(conn, args.phase)
        if phase is None:
            raise SystemExit(f"未知のフェーズです: {args.phase}")
        items = get_rubric_items(conn, phase["id"])
    finally:
        conn.close()
    weights = {k: v["weight"] for k, v in items.items()}

    rubric_vals: list[float] = []
    total_vals: list[float] = []
    holds = 0
    for i in range(args.runs):
        out = _score_once(args.phase, body, phase, weights)
        if out is None:
            holds += 1
            print(f"run {i + 1}/{args.runs}: manual_check（採点保留）")
            continue
        rubric_score, total = out
        rubric_vals.append(rubric_score)
        total_vals.append(total)
        print(f"run {i + 1}/{args.runs}: total={total:.2f} rubric={rubric_score:.2f}")

    print(f"--- total_score  : {_stats(total_vals)}")
    print(f"--- rubric_score : {_stats(rubric_vals)}")
    if holds:
        print(f"（manual_check: {holds} 回）")


if __name__ == "__main__":
    _main()
