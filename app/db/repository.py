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


# --- 画面表示用の取得（P5） ----------------------------------------------------

def get_all_phases(conn: sqlite3.Connection) -> list[dict]:
    """全フェーズを order_no 順に返す。"""
    rows = conn.execute(
        "SELECT id, key, name, order_no, pass_threshold, rubric_weight, coverage_weight "
        "FROM phases ORDER BY order_no"
    ).fetchall()
    return [
        {
            "id": r[0], "key": r[1], "name": r[2], "order_no": r[3],
            "pass_threshold": r[4], "rubric_weight": r[5], "coverage_weight": r[6],
        }
        for r in rows
    ]


def get_phase_by_id(conn: sqlite3.Connection, phase_id: int) -> dict | None:
    row = conn.execute(
        "SELECT id, key, name, order_no, pass_threshold, rubric_weight, coverage_weight "
        "FROM phases WHERE id = ?",
        (phase_id,),
    ).fetchone()
    if row is None:
        return None
    return {
        "id": row[0], "key": row[1], "name": row[2], "order_no": row[3],
        "pass_threshold": row[4], "rubric_weight": row[5], "coverage_weight": row[6],
    }


def get_rubric_items_full(conn: sqlite3.Connection, phase_id: int) -> list[dict]:
    """phase の rubric_items を表示用に一覧で返す（説明・最大点・重み）。"""
    rows = conn.execute(
        "SELECT item_key, description, max_score, weight "
        "FROM rubric_items WHERE phase_id = ? ORDER BY id",
        (phase_id,),
    ).fetchall()
    return [
        {"item_key": r[0], "description": r[1], "max_score": r[2], "weight": r[3]}
        for r in rows
    ]


def get_gate_status(conn: sqlite3.Connection, phase_id: int) -> dict | None:
    row = conn.execute(
        "SELECT current_round, closed, closed_at FROM gate_status WHERE phase_id = ?",
        (phase_id,),
    ).fetchone()
    if row is None:
        return None
    return {"current_round": row[0], "closed": row[1], "closed_at": row[2]}


def get_latest_review_for_phase(conn: sqlite3.Connection, phase_id: int) -> dict | None:
    """フェーズ最新のレビュー（artifacts 経由で結合）。"""
    row = conn.execute(
        "SELECT r.id, r.total_score, r.passed, r.status, a.round_no "
        "FROM reviews r JOIN artifacts a ON r.artifact_id = a.id "
        "WHERE a.phase_id = ? ORDER BY r.id DESC LIMIT 1",
        (phase_id,),
    ).fetchone()
    if row is None:
        return None
    return {"id": row[0], "total_score": row[1], "passed": row[2], "status": row[3], "round_no": row[4]}


def get_round_history(conn: sqlite3.Connection, phase_id: int) -> list[dict]:
    """ラウンド履歴（round_no 昇順）。"""
    rows = conn.execute(
        "SELECT a.round_no, r.id, r.total_score, r.passed, r.status "
        "FROM reviews r JOIN artifacts a ON r.artifact_id = a.id "
        "WHERE a.phase_id = ? ORDER BY a.round_no ASC, r.id ASC",
        (phase_id,),
    ).fetchall()
    return [
        {"round_no": r[0], "review_id": r[1], "total_score": r[2], "passed": r[3], "status": r[4]}
        for r in rows
    ]


def get_review(conn: sqlite3.Connection, review_id: int) -> dict | None:
    # artifacts と結合し、表示に必要な round_no / phase_id も併せて返す。
    row = conn.execute(
        "SELECT r.id, r.artifact_id, r.rubric_score, r.coverage_score, r.total_score, r.passed, "
        "       r.rubric_breakdown, r.findings, r.recommendations, r.acknowledgement, r.closing, "
        "       r.raw_llm_output, r.status, r.created_at, a.round_no, a.phase_id "
        "FROM reviews r JOIN artifacts a ON r.artifact_id = a.id "
        "WHERE r.id = ?",
        (review_id,),
    ).fetchone()
    if row is None:
        return None
    return {
        "id": row[0], "artifact_id": row[1], "rubric_score": row[2], "coverage_score": row[3],
        "total_score": row[4], "passed": row[5], "rubric_breakdown": row[6], "findings": row[7],
        "recommendations": row[8], "acknowledgement": row[9], "closing": row[10],
        "raw_llm_output": row[11], "status": row[12], "created_at": row[13],
        "round_no": row[14], "phase_id": row[15],
    }


def get_coverage_metrics(conn: sqlite3.Connection, review_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT technique, total_targets, covered_targets, coverage_rate, weight "
        "FROM coverage_metrics WHERE review_id = ? ORDER BY id",
        (review_id,),
    ).fetchall()
    return [
        {"technique": r[0], "total": r[1], "covered": r[2], "rate": r[3], "weight": r[4]}
        for r in rows
    ]


# --- QA4AI（レビューAIの出力点検）---------------------------------------------

def ensure_qa4ai_table(conn: sqlite3.Connection) -> None:
    """既存DBにも qa4ai_results を用意する（CREATE TABLE IF NOT EXISTS）。"""
    conn.execute(
        "CREATE TABLE IF NOT EXISTS qa4ai_results ("
        " id INTEGER PRIMARY KEY, review_id INTEGER REFERENCES reviews(id),"
        " check_type TEXT, result_json TEXT, created_at TEXT)"
    )


def insert_qa4ai_result(
    conn: sqlite3.Connection,
    review_id: int,
    check_type: str,
    result_json: str,
    created_at: str,
) -> None:
    conn.execute(
        "INSERT INTO qa4ai_results (review_id, check_type, result_json, created_at) "
        "VALUES (?, ?, ?, ?)",
        (review_id, check_type, result_json, created_at),
    )


def get_qa4ai_results(conn: sqlite3.Connection, review_id: int) -> dict[str, dict]:
    """check_type ごとに最新の結果（result_json を展開）を返す。無ければ空 dict。"""
    rows = conn.execute(
        "SELECT check_type, result_json, created_at FROM qa4ai_results "
        "WHERE review_id = ? ORDER BY id ASC",
        (review_id,),
    ).fetchall()
    # 同じ check_type は後勝ち（最新の実行結果を採用）。
    latest: dict[str, dict] = {}
    import json as _json
    for r in rows:
        latest[r[0]] = {"result": _json.loads(r[1]), "created_at": r[2]}
    return latest


def get_last_two_reviews(conn: sqlite3.Connection, phase_key: str) -> list[dict]:
    """フェーズの直近2レビューを round_no 降順で返す（最大2件・前回比較用）。

    rubric_breakdown は JSON 文字列のまま返す（呼び出し側で必要時に展開）。
    2件未満なら、ある分だけ返す（呼び出し側で「比較不可」を判断）。
    """
    rows = conn.execute(
        "SELECT r.id, a.round_no, r.rubric_score, r.coverage_score, r.total_score, "
        "       r.status, r.rubric_breakdown "
        "FROM reviews r JOIN artifacts a ON r.artifact_id = a.id "
        "JOIN phases p ON a.phase_id = p.id "
        "WHERE p.key = ? ORDER BY a.round_no DESC, r.id DESC LIMIT 2",
        (phase_key,),
    ).fetchall()
    return [
        {
            "review_id": r[0], "round_no": r[1], "rubric_score": r[2],
            "coverage_score": r[3], "total_score": r[4], "status": r[5],
            "rubric_breakdown": r[6],
        }
        for r in rows
    ]


def get_previous_phase_artifact_body(conn: sqlite3.Connection, phase_id: int) -> str | None:
    """order_no が手前のフェーズで最後に提出された成果物本文を返す（無ければ None）。

    レビュー時の参考コンテキスト用。直前フェーズが未提出なら、さらに手前で提出済みの
    最も近いフェーズの最新ラウンドを採用する。
    """
    row = conn.execute(
        "SELECT a.body FROM artifacts a "
        "JOIN phases p ON a.phase_id = p.id "
        "WHERE p.order_no < (SELECT order_no FROM phases WHERE id = ?) "
        "ORDER BY p.order_no DESC, a.round_no DESC LIMIT 1",
        (phase_id,),
    ).fetchone()
    return row[0] if row else None


def get_artifact(conn: sqlite3.Connection, artifact_id: int) -> dict | None:
    """artifact を id で取得（提出者・日時の取得に使う）。"""
    row = conn.execute(
        "SELECT id, phase_id, round_no, body, testcase_file_path, submitted_by, submitted_at "
        "FROM artifacts WHERE id = ?",
        (artifact_id,),
    ).fetchone()
    if row is None:
        return None
    return {
        "id": row[0], "phase_id": row[1], "round_no": row[2], "body": row[3],
        "testcase_file_path": row[4], "submitted_by": row[5], "submitted_at": row[6],
    }
