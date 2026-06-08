"""フェーズレビューの結線（取込→カバレッジ→LLM→合算→判定→合成→保存→gate更新）。

スコア式・判定は scoring/gate を呼ぶ（再実装しない）。LLM は reviewer 経由のみ。
例外で全体を落とさない。LLM 失敗は manual_check に集約する。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from app.db import repository
from app.db.repository import get_connection
from app.engine.coverage import CoverageResult, compute_coverage
from app.engine.gate import compose_review, judge
from app.engine.scoring import compute_rubric_score, compute_total_score
from app.ingest.testcase_loader import (
    TestcaseValidationError,
    extract_workbook_text,
    load_from_csv,
    load_from_xlsx,
)
from app.persona import reviewer


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _format_coverage_summary(result: CoverageResult) -> str:
    """LLM への参考用にカバレッジ内訳を短い文章にする（点数は語りに使う参考のみ）。"""
    lines = [
        f"{tc.technique}: {tc.covered}/{tc.total}（rate {tc.rate:.2f}）"
        for tc in result.by_technique
    ]
    return "技法別カバレッジ: " + " / ".join(lines) if lines else "カバレッジ対象なし"


def _safe_run_review(phase_key, artifact_body, coverage_summary, prev_context):
    """reviewer 呼び出しを保護する。例外時も落とさず manual_check 相当に集約。"""
    try:
        return reviewer.run_review(phase_key, artifact_body, coverage_summary, prev_context)
    except Exception as e:
        # キー値は含めない。種別のみ残す。
        raw = f"LLM呼び出しに失敗しました: {type(e).__name__}"
        return reviewer.ReviewResult("manual_check", None, raw)


def _render_artifact_text(targets, cases) -> str:
    """取込んだ targets / cases を、レビュー対象の成果物本文として読める形に整形する。

    本文未入力で Excel / CSV のみ提出されたとき、これを成果物本体としてレビューに回す。
    """
    lines: list[str] = ["# テスト対象（targets）"]
    for t in targets:
        mc = "" if t.must_cover else "（must_cover=N）"
        lines.append(f"- {t.target_id} [{t.technique}/{t.category}] {t.target}{mc}")
    lines.append("")
    lines.append("# テストケース（cases）")
    for c in cases:
        pre = c.precondition or "-"
        tids = ", ".join(c.target_ids) or "-"
        lines.append(
            f"- {c.test_id} [{c.technique}] 前提:{pre} / 入力:{c.input} / 期待:{c.expected} / 対象:{tids}"
        )
    return "\n".join(lines)


def run_phase_review(
    phase_key: str,
    artifact_body: str,
    submitted_by: str,
    targets_path: str | None = None,
    cases_path: str | None = None,
    workbook_path: str | None = None,
) -> dict:
    conn = get_connection()
    try:
        phase = repository.get_phase(conn, phase_key)
        if phase is None:
            raise ValueError(f"未知のフェーズです: {phase_key}")
        phase_id = phase["id"]

        # 取込元の決定: workbook（Excel1ファイル）優先 → CSV2ファイル → なし。
        # 実際に使ったファイルを artifacts.testcase_file_path に控えとして記録する。
        load_kind: str | None = None
        used_file_path: str | None = None
        if workbook_path:
            load_kind, used_file_path = "xlsx", workbook_path
        elif targets_path and cases_path:
            load_kind, used_file_path = "csv", cases_path

        # 1. 成果物ファイルがあれば取込。
        #    Excel は、まず targets/cases テンプレとして厳密に取込む（一致すればカバレッジ可）。
        #    工程ごとにテンプレが異なるため、一致しない一般の成果物Excelはカバレッジ対象外とする。
        targets = cases = None
        if load_kind == "xlsx":
            try:
                targets, cases = load_from_xlsx(workbook_path)
            except TestcaseValidationError:
                # テンプレ不一致 → カバレッジは行わず、後段で全文テキストをレビュー本体に使う。
                targets = cases = None
        elif load_kind == "csv":
            targets, cases = load_from_csv(targets_path, cases_path)

        # 2. レビュー対象本文: 本文 > targets/cases整形 > Excel全文テキスト。
        effective_body = (artifact_body or "").strip()
        if not effective_body:
            if cases is not None:
                effective_body = _render_artifact_text(targets, cases)
            elif load_kind == "xlsx":
                # テンプレ不一致の成果物Excelは、全シートをテキスト化してレビューに回す。
                effective_body = extract_workbook_text(workbook_path)
        if not effective_body:
            # 本文もファイルも無ければレビューできない。500で落とさず差し戻す。
            raise TestcaseValidationError(
                ["レビューできる成果物がありません。本文を入力するか、Excel（成果物ブック）"
                 "または CSV（targets と cases の両方）を添えてください。"]
            )

        # 3. round_no を決め、artifact を保存（reviewer は別接続で読むため先に commit）。
        round_no = repository.next_round_no(conn, phase_id)
        artifact_id = repository.insert_artifact(
            conn,
            phase_id,
            round_no,
            effective_body,
            used_file_path,
            submitted_by,
            _now_iso(),
        )
        conn.commit()

        # 4. カバレッジ（対象フェーズかつ取込データがある場合のみ）。
        coverage_score: float | None = None
        coverage_result: CoverageResult | None = None
        coverage_summary: str | None = None
        if phase["coverage_weight"] > 0 and cases is not None:
            coverage_result = compute_coverage(targets, cases)
            coverage_score = coverage_result.coverage_score
            coverage_summary = _format_coverage_summary(coverage_result)

        # 5. 前フェーズの成果物を参考コンテキストとして取得（あれば。今回の採点対象ではない）。
        prev_context = repository.get_previous_phase_artifact_body(conn, phase_id)

        # 6. LLM レビュー（reviewer 経由のみ）。
        review = _safe_run_review(phase_key, effective_body, coverage_summary, prev_context)

        # 3'. manual_check は合否判定せず記録して終了（落とさない）。
        if review.status == "manual_check":
            review_id = repository.insert_review(
                conn, artifact_id=artifact_id,
                rubric_score=None, coverage_score=coverage_score, total_score=None,
                passed=None, rubric_breakdown=None, findings=None, recommendations=None,
                acknowledgement=None, closing=None,
                raw_llm_output=review.raw_output, status="manual_check", created_at=_now_iso(),
            )
            repository.upsert_gate_status(conn, phase_id, round_no, closed=0, closed_at=None)
            conn.commit()
            return {
                "status": "manual_check",
                "passed": None,
                "total_score": None,
                "rubric_score": None,
                "coverage_score": coverage_score,
                "review_text": "要手動確認（manual_check）",
                "review_id": review_id,
                "round_no": round_no,
            }

        # 4. 合算→判定→合成。
        parsed = review.parsed
        rubric_items = repository.get_rubric_items(conn, phase_id)
        weights = {k: v["weight"] for k, v in rubric_items.items()}
        item_scores = {rs.item_key: (rs.score, rs.max_score) for rs in parsed.rubric_scores}

        rubric_score = compute_rubric_score(item_scores, weights)
        total_score = compute_total_score(
            rubric_score, coverage_score, phase["rubric_weight"], phase["coverage_weight"]
        )
        passed, score_line = judge(total_score, phase["pass_threshold"])
        review_text = compose_review(
            parsed.acknowledgement,
            score_line,
            parsed.overall_findings,
            parsed.closing,
            addressee=submitted_by,
        )

        # 5. reviews と coverage_metrics を保存。
        rubric_breakdown = json.dumps(
            [rs.model_dump() for rs in parsed.rubric_scores], ensure_ascii=False
        )
        findings_json = json.dumps(parsed.overall_findings, ensure_ascii=False)
        recommendations_json = json.dumps(
            [r.model_dump() for r in parsed.technique_recommendations], ensure_ascii=False
        )
        review_id = repository.insert_review(
            conn, artifact_id=artifact_id,
            rubric_score=rubric_score, coverage_score=coverage_score, total_score=total_score,
            passed=1 if passed else 0,
            rubric_breakdown=rubric_breakdown, findings=findings_json,
            recommendations=recommendations_json,
            acknowledgement=parsed.acknowledgement, closing=parsed.closing,
            raw_llm_output=review.raw_output, status="ok", created_at=_now_iso(),
        )
        if coverage_result is not None:
            for tc in coverage_result.by_technique:
                repository.insert_coverage_metric(
                    conn, review_id, tc.technique, tc.total, tc.covered, tc.rate, tc.weight
                )

        # 6. gate_status を upsert（開門なら closed=1・closed_at 記録）。
        repository.upsert_gate_status(
            conn, phase_id, round_no,
            closed=1 if passed else 0,
            closed_at=_now_iso() if passed else None,
        )
        conn.commit()

        # 7. 結果を返す。
        return {
            "status": "ok",
            "passed": passed,
            "total_score": total_score,
            "rubric_score": rubric_score,
            "coverage_score": coverage_score,
            "review_text": review_text,
            "review_id": review_id,
            "round_no": round_no,
        }
    finally:
        conn.close()
