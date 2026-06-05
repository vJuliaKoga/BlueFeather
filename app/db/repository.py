"""DB接続の取得（最小限）。接続先は config の db_path を使う。"""

import sqlite3

from app.config import get_settings


def get_connection() -> sqlite3.Connection:
    """設定の db_path に接続する。外部キー制約を有効化する。"""
    conn = sqlite3.connect(get_settings().db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn
