-- BlueFeather SQLite スキーマ（詳細設計§7）。再実行で壊れないよう IF NOT EXISTS を付ける。

CREATE TABLE IF NOT EXISTS phases (
  id INTEGER PRIMARY KEY, key TEXT UNIQUE, name TEXT, order_no INTEGER,
  pass_threshold REAL, rubric_weight REAL, coverage_weight REAL
);
CREATE TABLE IF NOT EXISTS rubric_items (
  id INTEGER PRIMARY KEY, phase_id INTEGER REFERENCES phases(id),
  item_key TEXT, description TEXT, max_score INTEGER, weight REAL
);
CREATE TABLE IF NOT EXISTS artifacts (
  id INTEGER PRIMARY KEY, phase_id INTEGER REFERENCES phases(id),
  round_no INTEGER, body TEXT, testcase_file_path TEXT,
  submitted_by TEXT, submitted_at TEXT
);
CREATE TABLE IF NOT EXISTS reviews (
  id INTEGER PRIMARY KEY, artifact_id INTEGER REFERENCES artifacts(id),
  rubric_score REAL, coverage_score REAL, total_score REAL, passed INTEGER,
  rubric_breakdown TEXT, findings TEXT, recommendations TEXT,
  acknowledgement TEXT, closing TEXT,
  raw_llm_output TEXT, status TEXT, created_at TEXT
);
CREATE TABLE IF NOT EXISTS coverage_metrics (
  id INTEGER PRIMARY KEY, review_id INTEGER REFERENCES reviews(id),
  technique TEXT, total_targets INTEGER, covered_targets INTEGER,
  coverage_rate REAL, weight REAL
);
CREATE TABLE IF NOT EXISTS gate_status (
  phase_id INTEGER PRIMARY KEY REFERENCES phases(id),
  current_round INTEGER, closed INTEGER, closed_at TEXT
);
