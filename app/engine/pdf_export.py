"""レビュー所見・QA4AI 結果を PDF に出力する（提出証跡）。

決定的: DB の保存値を整形するだけ（再採点・LLM 呼び出しはしない）。
日本語は reportlab 内蔵の CID フォント（HeiseiKakuGo-W5）で描画する（フォントファイル不要）。
キーや機微情報（raw_llm_output 等）は出力しない。
"""

from __future__ import annotations

import json
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.db import repository
from app.db.repository import get_connection
from app.engine.compare import compare_phase
from app.engine.gate import compose_review, judge
from app.persona.schema import TechniqueRecommendation

# 日本語フォント。どのビューア／プリンタでも字形が出るよう、Windows同梱の TTF/TTC を
# 「埋め込み」登録する（CID フォントは非埋め込みのため環境依存になる）。見つからなければ
# 内蔵 CID フォントへフォールバックする（テキスト層は正しいが字形はビューア依存）。
_FONT = "HeiseiKakuGo-W5"
_font_ready = False

_JP_FONT_CANDIDATES = [
    (r"C:\Windows\Fonts\YuGothR.ttc", 0),   # 游ゴシック
    (r"C:\Windows\Fonts\meiryo.ttc", 0),    # メイリオ
    (r"C:\Windows\Fonts\msgothic.ttc", 0),  # ＭＳ ゴシック
    (r"C:\Windows\Fonts\BIZ-UDGothicR.ttc", 0),
]


def _ensure_font() -> None:
    # 登録は1回でよい（多重登録を避ける）。
    global _font_ready, _FONT
    if _font_ready:
        return
    for path, idx in _JP_FONT_CANDIDATES:
        if Path(path).exists():
            try:
                pdfmetrics.registerFont(TTFont("BlueFeatherJP", path, subfontIndex=idx))
                _FONT = "BlueFeatherJP"
                _font_ready = True
                return
            except Exception:
                continue
    # 日本語TTFが見つからない環境（非Windows等）は内蔵CIDフォントで描画する。
    pdfmetrics.registerFont(UnicodeCIDFont("HeiseiKakuGo-W5"))
    _FONT = "HeiseiKakuGo-W5"
    _font_ready = True


def _styles() -> dict:
    return {
        "title": ParagraphStyle("title", fontName=_FONT, fontSize=16, leading=22, spaceAfter=4),
        "h2": ParagraphStyle(
            "h2", fontName=_FONT, fontSize=12, leading=18, spaceBefore=10, spaceAfter=4,
            textColor=colors.HexColor("#2b4a6f"),
        ),
        "body": ParagraphStyle("body", fontName=_FONT, fontSize=10.5, leading=16, spaceAfter=3),
        "muted": ParagraphStyle("muted", fontName=_FONT, fontSize=9, leading=14, textColor=colors.grey),
        "cell": ParagraphStyle("cell", fontName=_FONT, fontSize=9, leading=13),
    }


def _para(text, style) -> Paragraph:
    # reportlab の Paragraph は簡易マークアップを解釈するため、本文はエスケープする。
    safe = escape("" if text is None else str(text)).replace("\n", "<br/>")
    return Paragraph(safe, style)


def _table(headers: list, rows: list[list], styles: dict, col_widths=None) -> Table:
    data = [[_para(h, styles["cell"]) for h in headers]]
    for r in rows:
        data.append([_para(c, styles["cell"]) for c in r])
    t = Table(data, colWidths=col_widths, hAlign="LEFT")
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef2f7")),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#c9d3df")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    return t


def _grounded_label(it: dict) -> str:
    if it.get("grounded") is None:
        return "判定保留"
    return "あり" if it.get("grounded") else "なし"


def build_review_pdf(review_id: int, out_dir: str) -> str:
    """レビュー所見＋QA4AI結果を PDF に書き出し、ファイルパスを返す。"""
    _ensure_font()

    conn = get_connection()
    try:
        review = repository.get_review(conn, review_id)
        if review is None:
            raise ValueError(f"レビューが見つかりません: {review_id}")
        phase = repository.get_phase_by_id(conn, review["phase_id"])
        coverage_metrics = repository.get_coverage_metrics(conn, review_id)
        artifact = repository.get_artifact(conn, review["artifact_id"])
        submitted_by = artifact["submitted_by"] if artifact else None
        repository.ensure_qa4ai_table(conn)
        qa = repository.get_qa4ai_results(conn, review_id)
    finally:
        conn.close()

    st = _styles()
    story: list = [
        _para(f"BlueFeather 所見 — {phase['name']}（R{review['round_no']}）", st["title"]),
        _para(f"合格ライン {phase['pass_threshold']}点 ／ status: {review['status']}", st["muted"]),
        Spacer(1, 6),
    ]

    if review["status"] == "ok":
        findings = json.loads(review["findings"] or "[]")
        recos = [TechniqueRecommendation(**r) for r in json.loads(review["recommendations"] or "[]")]
        _passed, score_line = judge(review["total_score"], phase["pass_threshold"])
        review_text = compose_review(
            review["acknowledgement"] or "", score_line, findings, review["closing"] or "",
            addressee=submitted_by,
        )
        story.append(_para(score_line, st["h2"]))
        story.append(_para(review_text, st["body"]))

        if recos:
            story.append(_para("技法レコメンド", st["h2"]))
            story.append(
                _table(
                    ["対象", "おすすめ技法", "理由"],
                    [[r.target, r.recommended_technique, r.reason] for r in recos],
                    st, col_widths=[40 * mm, 35 * mm, 95 * mm],
                )
            )

        if coverage_metrics:
            story.append(_para("カバレッジ内訳", st["h2"]))
            story.append(
                _table(
                    ["技法", "covered", "total", "rate"],
                    [[m["technique"], m["covered"], m["total"], f"{m['rate']:.2f}"] for m in coverage_metrics],
                    st, col_widths=[70 * mm, 30 * mm, 30 * mm, 30 * mm],
                )
            )

        rubric = json.loads(review["rubric_breakdown"] or "[]")
        if rubric:
            story.append(_para("ルーブリック項目別", st["h2"]))
            story.append(
                _table(
                    ["項目", "score/max", "根拠"],
                    [[it.get("item_key"), f"{it.get('score')}/{it.get('max_score')}", it.get("rationale") or ""] for it in rubric],
                    st, col_widths=[40 * mm, 25 * mm, 105 * mm],
                )
            )

        # 前回との比較（画面と同じく直近2ラウンド・round_no>1 のときのみ）。
        if review["round_no"] > 1:
            cmp = compare_phase(phase["key"])
            if cmp.get("comparable"):
                story.append(_para("前回との比較", st["h2"]))
                story.append(_para(cmp["summary"], st["body"]))
                if cmp["improved"]:
                    story.append(_para("良くなった: " + " / ".join(cmp["improved"]), st["body"]))
                if cmp["degraded"]:
                    story.append(_para("少し戻った: " + " / ".join(cmp["degraded"]), st["body"]))
                td = cmp["score_deltas"]["total_score"]
                if td["delta"] is not None:
                    story.append(
                        _para(f"総合点 {td['prev']:.1f} → {td['cur']:.1f}（{td['delta']:+.1f}）", st["muted"])
                    )
    else:
        story.append(_para("この回は自動採点を保留しました（要手動確認）。", st["body"]))

    # QA4AI（点検結果。あれば）。
    if qa:
        story.append(Spacer(1, 8))
        story.append(_para("QA4AI（レビューの点検）", st["h2"]))

        if "rule" in qa:
            violations = qa["rule"]["result"].get("violations", [])
            if violations:
                story.append(_para("ルール遵守: 違反あり", st["body"]))
                for m in violations:
                    story.append(_para("・" + m, st["body"]))
            else:
                story.append(_para("ルール遵守: 違反なし", st["body"]))

        if "grounding" in qa:
            items = qa["grounding"]["result"].get("items", [])
            if items:
                story.append(_para("根拠の妥当性", st["body"]))
                story.append(
                    _table(
                        ["指摘", "根拠", "理由"],
                        [[it.get("finding", ""), _grounded_label(it), it.get("reason", "")] for it in items],
                        st, col_widths=[55 * mm, 20 * mm, 95 * mm],
                    )
                )

        if "judge" in qa:
            j = qa["judge"]["result"]
            if j.get("status") == "ok":
                story.append(_para("LLM-as-judge（各0〜4）", st["body"]))
                story.append(
                    _table(
                        ["具体性", "実行可能性", "ペルソナ遵守", "点数非漏洩"],
                        [[j.get("specificity"), j.get("actionability"), j.get("persona_adherence"), j.get("no_score_leak")]],
                        st, col_widths=[35 * mm, 40 * mm, 45 * mm, 35 * mm],
                    )
                )
                if j.get("overall"):
                    story.append(_para("総評: " + j["overall"], st["body"]))
            else:
                story.append(_para("LLM-as-judge: " + j.get("reason", ""), st["muted"]))

    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    file_path = out_path / f"review_{review_id}.pdf"
    doc = SimpleDocTemplate(
        str(file_path), pagesize=A4,
        leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm, bottomMargin=16 * mm,
        title=f"BlueFeather 所見 R{review['round_no']}",
    )
    doc.build(story)
    return str(file_path)
