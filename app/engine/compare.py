"""前回ラウンドとの比較・デグレ検出（関守エンジン・決定的）。

前回・今回の「保存値」を突き合わせて増減を出すだけ。新たな LLM 呼び出しや
採点ロジックの再実装はしない。変化の語りは judge と同様にテンプレートで組む。
"""

from __future__ import annotations

import json

from app.db.repository import (
    get_connection,
    get_coverage_metrics,
    get_last_two_reviews,
)


def _direction(delta: float) -> str:
    if delta > 0:
        return "up"
    if delta < 0:
        return "down"
    return "same"


def _compose_summary(improved: list[str], degraded: list[str]) -> str:
    """改善・デグレから BlueFeather 口調の短い総括をテンプレートで組む。"""
    imp = "・".join(improved)
    deg = "・".join(degraded)
    if not improved and not degraded:
        return "前回から大きな変化はないようです。"
    if improved and not degraded:
        return f"前回から、{imp}が一歩進みましたね。いい流れです。"
    if degraded and not improved:
        return f"{deg} が少し戻ったようです。責める話ではありません。ここだけ見直してみませんか。"
    return f"{imp}は良くなりました。一方で {deg} が少し戻ったようです。ここだけ見直してみませんか。"


def compute_comparison(prev: dict, cur: dict) -> dict:
    """前回 prev と今回 cur の保存値を突き合わせ、増減・デグレを算出する（純粋関数）。

    prev / cur は次を含む辞書:
      - items: item_key -> (score, max)
      - coverage: technique -> rate
      - rubric_score / coverage_score / total_score
    """
    item_deltas: dict[str, dict] = {}
    improved: list[str] = []
    degraded: list[str] = []

    # 項目スコアの増減（両方に存在する item_key のみ突き合わせる）。
    for key, (cur_score, _cur_max) in cur["items"].items():
        if key not in prev["items"]:
            continue
        prev_score = prev["items"][key][0]
        delta = cur_score - prev_score
        d = _direction(delta)
        item_deltas[key] = {"prev": prev_score, "cur": cur_score, "delta": delta, "direction": d}
        if d == "up":
            improved.append(key)
        elif d == "down":
            degraded.append(key)

    # 技法別カバレッジ率の増減。
    coverage_deltas: dict[str, dict] = {}
    for tech, cur_rate in cur["coverage"].items():
        if tech not in prev["coverage"]:
            continue
        prev_rate = prev["coverage"][tech]
        delta = cur_rate - prev_rate
        coverage_deltas[tech] = {"prev": prev_rate, "cur": cur_rate, "delta": delta}
        d = _direction(delta)
        if d == "up":
            improved.append(tech)
        elif d == "down":
            degraded.append(tech)

    # 集計スコアの増減（どちらかが None の項は delta=None）。
    score_deltas: dict[str, dict] = {}
    for name in ("rubric_score", "coverage_score", "total_score"):
        p = prev.get(name)
        c = cur.get(name)
        delta = (c - p) if (p is not None and c is not None) else None
        score_deltas[name] = {"prev": p, "cur": c, "delta": delta}

    return {
        "item_deltas": item_deltas,
        "coverage_deltas": coverage_deltas,
        "score_deltas": score_deltas,
        "improved": improved,
        "degraded": degraded,
        "summary": _compose_summary(improved, degraded),
    }


def _to_compare_input(conn, row: dict) -> dict:
    """直近レビュー行（rubric_breakdown は JSON 文字列）を比較用の辞書に整える。"""
    breakdown = json.loads(row["rubric_breakdown"] or "[]")
    items = {b["item_key"]: (b["score"], b["max_score"]) for b in breakdown}
    coverage = {m["technique"]: m["rate"] for m in get_coverage_metrics(conn, row["review_id"])}
    return {
        "items": items,
        "coverage": coverage,
        "rubric_score": row["rubric_score"],
        "coverage_score": row["coverage_score"],
        "total_score": row["total_score"],
    }


def compare_phase(phase_key: str) -> dict:
    """フェーズの直近2ラウンドを比較する（DBラッパ）。

    2件未満、または manual_check（スコア無し）が混ざるときは比較不可を返す。
    """
    conn = get_connection()
    try:
        rows = get_last_two_reviews(conn, phase_key)
        if len(rows) < 2:
            return {"comparable": False, "reason": "前回がまだ無いため、比較はありません。"}
        cur_row, prev_row = rows[0], rows[1]  # round_no 降順なので [0]=今回 / [1]=前回
        if cur_row["status"] != "ok" or prev_row["status"] != "ok":
            return {
                "comparable": False,
                "reason": "スコアの無いラウンド（要手動確認）があるため、比較はありません。",
            }
        prev = _to_compare_input(conn, prev_row)
        cur = _to_compare_input(conn, cur_row)
    finally:
        conn.close()

    result = compute_comparison(prev, cur)
    result["comparable"] = True
    result["prev_round_no"] = prev_row["round_no"]
    result["cur_round_no"] = cur_row["round_no"]
    return result
