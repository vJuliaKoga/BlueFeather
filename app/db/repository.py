"""DB接続と最小限の取得・保存関数（sqlite3、config の db_path）。

採点式・判定ロジックはここに置かない（engine 側）。
取得・保存の関数は呼び出し側が開いた接続（conn）を受け取り、
トランザクション境界（commit）は呼び出し側が管理する。
"""

import sqlite3

from app.config import get_settings


def get_connection() -> sqlite3.Connection:
    """設定の db_path に接続する。外部キー制約を有効化する。"""
    conn = sqlite3.connect(get_settings().db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def get_phase(conn: sqlite3.Connection, key: str) -> dict | None:
    """phase を key で取得。無ければ None。"""
    row = conn.execute(
        "SELECT id, name, pass_threshold, rubric_weight, coverage_weight "
        "FROM phases WHERE key = ?",
        (key,),
    ).fetchone()
    if row is None:
        return None
    return {
        "id": row[0],
        "name": row[1],
        "pass_threshold": row[2],
        "rubric_weight": row[3],
        "coverage_weight": row[4],
    }


def get_rubric_items(conn: sqlite3.Connection, phase_id: int) -> dict[str, dict]:
    """phase の rubric_items を item_key -> {weight, max_score} で返す。"""
    rows = conn.execute(
        "SELECT item_key, weight, max_score FROM rubric_items WHERE phase_id = ? ORDER BY id",
        (phase_id,),
    ).fetchall()
    return {r[0]: {"weight": r[1], "max_score": r[2]} for r in rows}


def next_round_no(conn: sqlite3.Connection, phase_id: int) -> int:
    """phase の次の round_no（最大+1、無ければ1）。"""
    row = conn.execute(
        "SELECT MAX(round_no) FROM artifacts WHERE phase_id = ?", (phase_id,)
    ).fetchone()
    return (row[0] or 0) + 1


def insert_artifact(
    conn: sqlite3.Connection,
    phase_id: int,
    round_no: int,
    body: str,
    testcase_file_path: str | None,
    submitted_by: str,
    submitted_at: str,
) -> int:
    cur = conn.execute(
        "INSERT INTO artifacts "
        "(phase_id, round_no, body, testcase_file_path, submitted_by, submitted_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (phase_id, round_no, body, testcase_file_path, submitted_by, submitted_at),
    )
    return cur.lastrowid


def insert_review(
    conn: sqlite3.Connection,
    artifact_id: int,
    rubric_score: float | None,
    coverage_score: float | None,
    total_score: float | None,
    passed: int | None,
    rubric_breakdown: str | None,
    findings: str | None,
    recommendations: str | None,
    acknowledgement: str | None,
    closing: str | None,
    raw_llm_output: str | None,
    status: str,
    created_at: str,
) -> int:
    cur = conn.execute(
        "INSERT INTO reviews "
        "(artifact_id, rubric_score, coverage_score, total_score, passed, "
        " rubric_breakdown, findings, recommendations, acknowledgement, closing, "
        " raw_llm_output, status, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            artifact_id, rubric_score, coverage_score, total_score, passed,
            rubric_breakdown, findings, recommendations, acknowledgement, closing,
            raw_llm_output, status, created_at,
        ),
    )
    return cur.lastrowid


def insert_coverage_metric(
    conn: sqlite3.Connection,
    review_id: int,
    technique: str,
    total_targets: int,
    covered_targets: int,
    coverage_rate: float,
    weight: float,
) -> None:
    conn.execute(
        "INSERT INTO coverage_metrics "
        "(review_id, technique, total_targets, covered_targets, coverage_rate, weight) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (review_id, technique, total_targets, covered_targets, coverage_rate, weight),
    )


def upsert_gate_status(
    conn: sqlite3.Connection,
    phase_id: int,
    current_round: int,
    closed: int,
    closed_at: str | None,
) -> None:
    """gate_status を phase_id で upsert（current_round 更新、開門時は closed=1）。"""
    conn.execute(
        "INSERT INTO gate_status (phase_id, current_round, closed, closed_at) "
        "VALUES (?, ?, ?, ?) "
        "ON CONFLICT(phase_id) DO UPDATE SET "
        "  current_round = excluded.current_round, "
        "  closed = excluded.closed, "
        "  closed_at = excluded.closed_at",
        (phase_id, current_round, closed, closed_at),
    )
