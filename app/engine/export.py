"""フェーズのレビュー履歴を Markdown / JSON で書き出す（提出証跡の持ち寄り用）。

決定的: DB の保存値をそのまま整形するだけ。再採点・判定のやり直し・LLM 呼び出しはしない。
キーや機微情報は出力しない（raw_llm_output やキーは含めない）。
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.db import repository
from app.db.repository import get_connection
from app.engine.compare import compute_comparison
from app.engine.gate import compose_review, judge


def _result_label(status: str, passed: int | None) -> str:
    """保存済みの status / passed から表示ラベルを決める（判定はやり直さない）。"""
    if status == "manual_check":
        return "要手動確認"
    return "開門" if passed else "あと一歩"


def _build_round(conn, phase: dict, hist: dict) -> dict:
    """1ラウンド分の保存値を整形して dict にする。スコアの再計算はしない。"""
    review = repository.get_review(conn, hist["review_id"])
    artifact = repository.get_artifact(conn, review["artifact_id"])
    status = review["status"]

    coverage_breakdown = repository.get_coverage_metrics(conn, hist["review_id"])
    findings = json.loads(review["findings"] or "[]")
    recommendations = json.loads(review["recommendations"] or "[]")

    # 合成所見は保存済みの語り部品から組み直す（judge は閾値比較のみ＝再採点ではない）。
    if status == "ok" and review["total_score"] is not None:
        _, score_line = judge(review["total_score"], phase["pass_threshold"])
        composed = compose_review(
            review["acknowledgement"] or "",
            score_line,
            findings,
            review["closing"] or "",
            addressee=artifact["submitted_by"] if artifact else None,
        )
    else:
        composed = "要手動確認（manual_check）"

    return {
        "round_no": hist["round_no"],
        "submitted_by": artifact["submitted_by"] if artifact else None,
        "submitted_at": artifact["submitted_at"] if artifact else None,
        "status": status,
        "result": _result_label(status, review["passed"]),
        "passed": None if review["passed"] is None else bool(review["passed"]),
        "rubric_score": review["rubric_score"],
        "coverage_score": review["coverage_score"],
        "total_score": review["total_score"],
        "coverage_breakdown": coverage_breakdown,
        "rubric_breakdown": json.loads(review["rubric_breakdown"] or "[]"),
        "findings": findings,
        "recommendations": recommendations,
        "composed_review": composed,
    }


def _collect_phase(conn, phase_key: str) -> tuple[dict, list[dict]]:
    phase = repository.get_phase(conn, phase_key)
    if phase is None:
        raise ValueError(f"未知のフェーズです: {phase_key}")
    history = repository.get_round_history(conn, phase["id"])
    rounds = [_build_round(conn, phase, h) for h in history]

    # 各ラウンドに「前回との比較」を付ける（round_no>1 かつ両方 ok のときのみ・決定的）。
    for i in range(1, len(rounds)):
        if rounds[i]["status"] == "ok" and rounds[i - 1]["status"] == "ok":
            rounds[i]["comparison"] = compute_comparison(
                _round_to_compare_input(rounds[i - 1]),
                _round_to_compare_input(rounds[i]),
            )

    return phase, rounds


def _round_to_compare_input(r: dict) -> dict:
    """エクスポート用ラウンド dict を compute_comparison の入力形に変換する。"""
    items = {b["item_key"]: (b["score"], b["max_score"]) for b in r["rubric_breakdown"]}
    coverage = {m["technique"]: m["rate"] for m in r["coverage_breakdown"]}
    return {
        "items": items,
        "coverage": coverage,
        "rubric_score": r["rubric_score"],
        "coverage_score": r["coverage_score"],
        "total_score": r["total_score"],
    }


# --- 整形（Markdown / JSON） --------------------------------------------------

def _fmt_score(v: float | None) -> str:
    return f"{v:.2f}" if isinstance(v, (int, float)) else "—"


def _render_json(phase: dict, phase_key: str, rounds: list[dict]) -> str:
    payload = {
        "phase": {
            "key": phase_key,
            "name": phase["name"],
            "pass_threshold": phase["pass_threshold"],
            "rubric_weight": phase["rubric_weight"],
            "coverage_weight": phase["coverage_weight"],
        },
        "rounds": rounds,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _render_md(phase: dict, phase_key: str, rounds: list[dict]) -> str:
    lines: list[str] = [
        f"# 提出証跡: {phase['name']}（{phase_key}）",
        "",
        f"- 合格ライン: {phase['pass_threshold']}点",
        f"- 配点: ルーブリック {phase['rubric_weight']} / カバレッジ {phase['coverage_weight']}",
        f"- ラウンド数: {len(rounds)}",
        "",
    ]

    if not rounds:
        lines.append("まだ提出はありません。")
        return "\n".join(lines) + "\n"

    for r in rounds:
        lines += [
            f"## R{r['round_no']}（{r['result']}）",
            "",
            f"- 提出者: {r['submitted_by'] or '—'}",
            f"- 日時: {r['submitted_at'] or '—'}",
            f"- status: {r['status']}",
            (
                f"- スコア: 総合 {_fmt_score(r['total_score'])} / "
                f"ルーブリック {_fmt_score(r['rubric_score'])} / "
                f"カバレッジ {_fmt_score(r['coverage_score'])}"
            ),
            "",
            "### 所見",
            "",
            r["composed_review"] or "—",
            "",
        ]

        if r["recommendations"]:
            lines += ["### 技法レコメンド", "", "| 対象 | おすすめ技法 | 理由 |", "| --- | --- | --- |"]
            for rec in r["recommendations"]:
                reason = (rec.get("reason") or "").replace("\n", " ").replace("|", "\\|")
                lines.append(
                    f"| {rec.get('target')} | {rec.get('recommended_technique')} | {reason} |"
                )
            lines.append("")

        if r["coverage_breakdown"]:
            lines += ["### カバレッジ内訳", "", "| 技法 | covered | total | rate | weight |", "| --- | --- | --- | --- | --- |"]
            for m in r["coverage_breakdown"]:
                lines.append(
                    f"| {m['technique']} | {m['covered']} | {m['total']} | "
                    f"{m['rate']:.2f} | {m['weight']} |"
                )
            lines.append("")

        if r["rubric_breakdown"]:
            lines += ["### 項目別スコア", "", "| 項目 | score/max | 根拠 |", "| --- | --- | --- |"]
            for it in r["rubric_breakdown"]:
                # 表崩れを避けるため改行とパイプを退避する。
                rationale = (it.get("rationale") or "").replace("\n", " ").replace("|", "\\|")
                lines.append(
                    f"| {it.get('item_key')} | {it.get('score')}/{it.get('max_score')} | {rationale} |"
                )
            lines.append("")

        cmp = r.get("comparison")
        if cmp:
            lines += ["### 前回との比較", "", cmp["summary"], ""]
            if cmp["improved"]:
                lines.append(f"- 良くなった: {' / '.join(cmp['improved'])}")
            if cmp["degraded"]:
                lines.append(f"- 少し戻った（デグレ）: {' / '.join(cmp['degraded'])}")
            td = cmp["score_deltas"]["total_score"]
            if td["delta"] is not None:
                lines.append(
                    f"- 総合点: {td['prev']:.2f} → {td['cur']:.2f}（{td['delta']:+.2f}）"
                )
            lines.append("")

    return "\n".join(lines) + "\n"


# --- 公開 API -----------------------------------------------------------------

def export_phase(phase_key: str, fmt: str, out_dir: str) -> str:
    """フェーズ履歴を fmt（md/json）で out_dir に書き出し、ファイルパスを返す。"""
    if fmt not in ("md", "json"):
        raise ValueError(f"未知のフォーマットです: {fmt}（md か json）")

    conn = get_connection()
    try:
        phase, rounds = _collect_phase(conn, phase_key)
    finally:
        conn.close()

    if fmt == "json":
        content = _render_json(phase, phase_key, rounds)
    else:
        content = _render_md(phase, phase_key, rounds)

    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    # ファイル名から phase_key と format が分かる形にする。
    file_path = out_path / f"{phase_key}_{fmt}.{fmt}"
    file_path.write_text(content, encoding="utf-8")
    return str(file_path)


def export_all(fmt: str, out_dir: str) -> list[str]:
    """全フェーズを fmt で書き出し、ファイルパスの一覧を返す。"""
    conn = get_connection()
    try:
        phases = repository.get_all_phases(conn)
    finally:
        conn.close()
    return [export_phase(p["key"], fmt, out_dir) for p in phases]


def _main() -> None:
    parser = argparse.ArgumentParser(description="フェーズのレビュー履歴をエクスポート")
    parser.add_argument("--phase", required=True, help="フェーズ key、または all")
    parser.add_argument("--format", required=True, choices=["md", "json"], dest="fmt")
    parser.add_argument("--out", required=True, help="出力ディレクトリ")
    args = parser.parse_args()

    if args.phase == "all":
        paths = export_all(args.fmt, args.out)
    else:
        paths = [export_phase(args.phase, args.fmt, args.out)]

    for p in paths:
        print(f"書き出し: {p}")


if __name__ == "__main__":
    _main()
