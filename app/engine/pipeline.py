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
from app.ingest.testcase_loader import load_from_csv
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


def _safe_run_review(phase_key, artifact_body, coverage_summary):
    """reviewer 呼び出しを保護する。例外時も落とさず manual_check 相当に集約。"""
    try:
        return reviewer.run_review(phase_key, artifact_body, coverage_summary)
    except Exception as e:
        # キー値は含めない。種別のみ残す。
        raw = f"LLM呼び出しに失敗しました: {type(e).__name__}"
        return reviewer.ReviewResult("manual_check", None, raw)


def run_phase_review(
    phase_key: str,
    artifact_body: str,
    submitted_by: str,
    targets_path: str | None = None,
    cases_path: str | None = None,
) -> dict:
    conn = get_connection()
    try:
        phase = repository.get_phase(conn, phase_key)
        if phase is None:
            raise ValueError(f"未知のフェーズです: {phase_key}")
        phase_id = phase["id"]

        # 1. round_no を決め、artifact を保存（reviewer は別接続で読むため先に commit）。
        round_no = repository.next_round_no(conn, phase_id)
        artifact_id = repository.insert_artifact(
            conn,
            phase_id,
            round_no,
            artifact_body,
            cases_path,
            submitted_by,
            _now_iso(),
        )
        conn.commit()

        # 2. カバレッジ（対象フェーズかつファイルがある場合のみ）。
        coverage_score: float | None = None
        coverage_result: CoverageResult | None = None
        coverage_summary: str | None = None
        if phase["coverage_weight"] > 0 and targets_path and cases_path:
            targets, cases = load_from_csv(targets_path, cases_path)
            coverage_result = compute_coverage(targets, cases)
            coverage_score = coverage_result.coverage_score
            coverage_summary = _format_coverage_summary(coverage_result)

        # 3. LLM レビュー（reviewer 経由のみ）。
        review = _safe_run_review(phase_key, artifact_body, coverage_summary)

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
            parsed.technique_recommendations,
            parsed.closing,
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
