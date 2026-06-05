"""DB初期化・YAML投入（冪等）。

- schema.sql でテーブル作成。
- phases.yaml を key で upsert。
- rubrics.yaml を (phase, item_key) で差分更新（重複生成しない）。

再実行しても行が増えない実装にする。採点ロジック・APIはここでは扱わない（P2以降）。
"""

from pathlib import Path

import yaml

from app.db.repository import get_connection

# パッケージ相対でファイルを解決する（実行ディレクトリに依存しない）。
_DB_DIR = Path(__file__).resolve().parent
_APP_DIR = _DB_DIR.parent
_SCHEMA_PATH = _DB_DIR / "schema.sql"
_PHASES_PATH = _APP_DIR / "settings" / "phases.yaml"
_RUBRICS_PATH = _APP_DIR / "settings" / "rubrics.yaml"


def _create_tables(conn) -> None:
    conn.executescript(_SCHEMA_PATH.read_text(encoding="utf-8"))


def _upsert_phases(conn, phases) -> None:
    # key は UNIQUE。衝突時は更新する（差分更新）。
    for p in phases:
        conn.execute(
            """
            INSERT INTO phases (key, name, order_no, pass_threshold, rubric_weight, coverage_weight)
            VALUES (:key, :name, :order_no, :pass_threshold, :rubric_weight, :coverage_weight)
            ON CONFLICT(key) DO UPDATE SET
                name = excluded.name,
                order_no = excluded.order_no,
                pass_threshold = excluded.pass_threshold,
                rubric_weight = excluded.rubric_weight,
                coverage_weight = excluded.coverage_weight
            """,
            p,
        )


def _upsert_rubric_items(conn, rubrics) -> None:
    # (phase_id, item_key) で存在判定し、無ければ挿入・あれば更新（重複行を作らない）。
    for phase_key, items in rubrics.items():
        row = conn.execute("SELECT id FROM phases WHERE key = ?", (phase_key,)).fetchone()
        if row is None:
            # phases.yaml に無いフェーズキーはスキップ（不整合は投入しない）。
            continue
        phase_id = row[0]
        for it in items:
            existing = conn.execute(
                "SELECT id FROM rubric_items WHERE phase_id = ? AND item_key = ?",
                (phase_id, it["item_key"]),
            ).fetchone()
            if existing is None:
                conn.execute(
                    """
                    INSERT INTO rubric_items (phase_id, item_key, description, max_score, weight)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (phase_id, it["item_key"], it["description"], it["max_score"], it["weight"]),
                )
            else:
                conn.execute(
                    """
                    UPDATE rubric_items
                    SET description = ?, max_score = ?, weight = ?
                    WHERE id = ?
                    """,
                    (it["description"], it["max_score"], it["weight"], existing[0]),
                )


def init_db() -> None:
    phases = yaml.safe_load(_PHASES_PATH.read_text(encoding="utf-8"))["phases"]
    rubrics = yaml.safe_load(_RUBRICS_PATH.read_text(encoding="utf-8"))["rubrics"]

    conn = get_connection()
    try:
        _create_tables(conn)
        _upsert_phases(conn, phases)
        _upsert_rubric_items(conn, rubrics)
        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    init_db()
    print("DB初期化が完了しました。")
