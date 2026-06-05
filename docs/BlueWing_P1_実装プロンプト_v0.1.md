# BlueWing P1 実装プロンプト（Claude Code 用） v0.1

> 対象: 実装フェーズ計画 v0.1 の P1（雛形・設定・DBスキーマ・セットアップ）
> 参照: 企画書 v0.3 / 詳細設計 v0.2 / ペルソナ定義書 v0.2
>
> 各タスクは独立。1タスクずつ Claude Code に渡す。原則1〜2ファイルに限定する。

## 共通の前提・ルール（全タスク共通）

- 環境は Windows / PowerShell。実装は VSCode拡張の Claude Code。
- 実行主体は人。Claude Code は破壊的・機微な操作（インストール、DB初期化、起動）は自分で実行せず、PowerShell コマンドとして提示し、人が手元で実行する。
- OpenAI APIキーは環境変数 `OPENAI_API_KEY` から読む。**コードや設定ファイル（.env含む）にキーを書かない。ログにも出さない。**
- Python 3.10以上を前提にしてよい。
- 設計（詳細設計 v0.2）に沿う。設計にない仕様追加・挙動変更はしない。
- 指定外ファイルは作成・変更しない。曖昧なときは範囲を保守的に絞る。
- 変更箇所には、意図が分かりにくいところだけ日本語の簡潔なコメントを付ける。冗長にしない。

---

#### Task 1: プロジェクト雛形と requirements.txt

目的：
ディレクトリ構成の土台と依存定義を用意する。

対象ファイル：
- ディレクトリ構成（空の `__init__.py` を含む）
- `requirements.txt`

変更内容：
- 詳細設計§1の構成で、次のディレクトリと空ファイルを作成する：
  `app/`, `app/db/`, `app/ingest/`, `app/engine/`, `app/persona/`, `app/rubrics/`, `app/settings/`, `app/ui/templates/`, `app/ui/static/`, `tests/`
  （`app` 配下の各パッケージに `__init__.py` を置く）
- `requirements.txt` を次の内容で作成する：
  ```
  fastapi
  uvicorn[standard]
  jinja2
  python-multipart
  openai
  pyyaml
  openpyxl
  pydantic
  pytest
  ```

禁止事項：
- 上記以外のファイル作成・依存追加禁止。
- 実装コードはまだ書かない（雛形のみ）。

追加ルール：
- 余計な説明は出力しない。

完了確認：
```powershell
python -V
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

---

#### Task 2: app/config.py（設定・キー読込）

目的：
環境変数から設定を読み、キー未設定なら安全に停止する。

対象ファイル：
- `app/config.py`

変更内容：
- 環境変数を読む設定アクセサを実装する：
  - `OPENAI_API_KEY`（必須）。未設定なら分かりやすい例外を投げて停止する。
  - `OPENAI_MODEL`（任意。環境変数で指定、無ければ既定のモデル名定数。コードに固定の最終決定値を埋め込まず、定数は1か所で差し替え可能にする）。
  - `BLUEWING_DB_PATH`（任意。既定 `bluewing.db`）。
- キーの値を返すアクセサは用意してよいが、**ログ出力・print・例外メッセージにキー値を含めない**。
- 設定取得は1関数（例 `get_settings()`）に集約する。

禁止事項：
- キーをファイルに書く・既定値として埋める・ログに出すこと禁止。
- .env からのキー読込実装は禁止。

追加ルール：
- キー未設定時のメッセージは「OPENAI_API_KEY が未設定です」と、設定方法（PowerShell）への誘導程度に留める。

完了確認（人が実行）：
```powershell
# 未設定時にエラーで止まることを確認
Remove-Item Env:\OPENAI_API_KEY -ErrorAction SilentlyContinue
python -c "from app.config import get_settings; get_settings()"
# 設定すると通ることを確認
$env:OPENAI_API_KEY = "（各自のキー）"
python -c "from app.config import get_settings; s=get_settings(); print('model=', s.openai_model, 'db=', s.db_path)"
```

---

#### Task 3: app/db/schema.sql（DDL）

目的：
SQLiteのテーブル定義を用意する。

対象ファイル：
- `app/db/schema.sql`

変更内容：
- 次のDDLをそのまま記述する（詳細設計§7）：
  ```sql
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
  ```

禁止事項：
- テーブル・列の追加変更禁止（設計どおり）。

追加ルール：
- `IF NOT EXISTS` を付け、再実行で壊れないようにする。

---

#### Task 4: settings/phases.yaml と rubrics.yaml（ドラフト値）

目的：
フェーズ定義とルーブリック配点の初期値（ドラフト）を用意する。

対象ファイル：
- `app/settings/phases.yaml`
- `app/settings/rubrics.yaml`

変更内容：
- `phases.yaml` を次の内容で作成する：
  ```yaml
  phases:
    - { key: test_plan,       name: テスト計画,           order_no: 1, pass_threshold: 80, rubric_weight: 1.0, coverage_weight: 0.0 }
    - { key: requirements,    name: 要件抽出,             order_no: 2, pass_threshold: 80, rubric_weight: 1.0, coverage_weight: 0.0 }
    - { key: viewpoints,      name: 観点整理,             order_no: 3, pass_threshold: 80, rubric_weight: 1.0, coverage_weight: 0.0 }
    - { key: basic_design,    name: 基本設計,             order_no: 4, pass_threshold: 80, rubric_weight: 1.0, coverage_weight: 0.0 }
    - { key: detailed_design, name: 詳細設計,             order_no: 5, pass_threshold: 80, rubric_weight: 0.7, coverage_weight: 0.3 }
    - { key: testcase_impl,   name: テストケース実装,     order_no: 6, pass_threshold: 80, rubric_weight: 0.6, coverage_weight: 0.4 }
    - { key: api_automation,  name: APIテスト・自動化,    order_no: 7, pass_threshold: 80, rubric_weight: 0.4, coverage_weight: 0.6 }
  ```
- `rubrics.yaml` を次の内容で作成する（max_scoreは全項目4）：
  ```yaml
  rubrics:
    test_plan:
      - { item_key: scope_clarity,        description: スコープ・対象の明確さ,             max_score: 4, weight: 1.0 }
      - { item_key: strategy_validity,    description: テスト戦略・アプローチの妥当性,     max_score: 4, weight: 1.2 }
      - { item_key: risk_identification,  description: リスクの識別と対応方針,             max_score: 4, weight: 1.0 }
      - { item_key: schedule_feasibility, description: 体制・スケジュールの現実性,         max_score: 4, weight: 0.8 }
      - { item_key: completion_criteria,  description: 完了基準・合格基準の明確さ,         max_score: 4, weight: 1.0 }
    requirements:
      - { item_key: req_coverage,         description: 要件の網羅性,                       max_score: 4, weight: 1.2 }
      - { item_key: testability,          description: 各要件のテスト可能性,               max_score: 4, weight: 1.2 }
      - { item_key: ambiguity_removal,    description: 曖昧さ・多義性の排除,               max_score: 4, weight: 1.0 }
      - { item_key: prioritization,       description: 優先度・重要度の整理,               max_score: 4, weight: 0.8 }
      - { item_key: traceability,         description: トレーサビリティ,                   max_score: 4, weight: 0.8 }
    viewpoints:
      - { item_key: viewpoint_coverage,   description: 観点の網羅性,                       max_score: 4, weight: 1.3 }
      - { item_key: structuring,          description: 観点の構造化・分類の妥当性,         max_score: 4, weight: 1.0 }
      - { item_key: technique_assignment, description: 各観点への技法割当の妥当性,         max_score: 4, weight: 1.2 }
      - { item_key: no_omission_dup,      description: 抜け漏れ・重複のなさ,               max_score: 4, weight: 1.0 }
    basic_design:
      - { item_key: technique_selection,  description: 技法選択の妥当性,                   max_score: 4, weight: 1.2 }
      - { item_key: condition_derivation, description: テスト条件導出の網羅性,             max_score: 4, weight: 1.3 }
      - { item_key: viewpoint_mapping,    description: 観点との対応づけ,                   max_score: 4, weight: 1.0 }
      - { item_key: design_consistency,   description: 設計の一貫性,                       max_score: 4, weight: 0.8 }
    detailed_design:
      - { item_key: boundary_coverage,    description: 境界値の特定の網羅性,               max_score: 4, weight: 1.5 }
      - { item_key: branch_coverage,      description: 分岐・デシジョンの網羅性,           max_score: 4, weight: 1.5 }
      - { item_key: state_transition,     description: 状態遷移の網羅性,                   max_score: 4, weight: 1.0 }
      - { item_key: expected_clarity,     description: 期待結果の明確さ,                   max_score: 4, weight: 1.0 }
    testcase_impl:
      - { item_key: case_concreteness,    description: ケースの具体性・実行可能性,         max_score: 4, weight: 1.0 }
      - { item_key: boundary_cases,       description: 境界値ケースの網羅,                 max_score: 4, weight: 1.5 }
      - { item_key: branch_cases,         description: 分岐ケースの網羅,                   max_score: 4, weight: 1.5 }
      - { item_key: expected_verifiability, description: 期待結果の検証可能性,             max_score: 4, weight: 1.0 }
    api_automation:
      - { item_key: automation_selection, description: 自動化対象選定の妥当性,             max_score: 4, weight: 1.0 }
      - { item_key: assertion_sufficiency, description: アサーションの十分さ,              max_score: 4, weight: 1.2 }
      - { item_key: maintainability,      description: 保守性・再実行性,                   max_score: 4, weight: 0.8 }
  ```

禁止事項：
- 上記2ファイル以外を変更しない。値はドラフトのため、項目構成は設計どおりに保つ。

追加ルール：
- フェーズキーは `prompts.py` の技法レコメンド対象（viewpoints / basic_design / detailed_design）と一致させること（変更しない）。

---

#### Task 5: app/db/init.py（DB初期化・YAML投入）

目的：
schema.sql でテーブルを作り、YAML からフェーズ・ルーブリックを冪等に投入する。

対象ファイル：
- `app/db/init.py`
- （必要なら）`app/db/repository.py`（接続取得のみ。最小限）

変更内容：
- `app/db/schema.sql` を読んでDB（`BLUEWING_DB_PATH`）にテーブルを作成する。
- `settings/phases.yaml` を読み、`phases` を key で upsert（存在すれば更新、無ければ挿入）する。
- `settings/rubrics.yaml` を読み、各フェーズの `rubric_items` を (phase, item_key) で差分更新する（重複生成しない）。
- `python -m app.db.init` で実行できるようにする（`if __name__ == "__main__"`）。

禁止事項：
- 採点ロジック・APIは実装しない（P2以降）。
- キーやモデル呼び出しに触れない。

追加ルール：
- 再実行しても重複行が増えない冪等実装にする。
- 接続は `config.get_settings()` の db_path を使う。

完了確認（人が実行）：
```powershell
$env:OPENAI_API_KEY = "（各自のキー）"   # config読込のため
python -m app.db.init
python -c "import sqlite3,os; c=sqlite3.connect(os.environ.get('BLUEWING_DB_PATH','bluewing.db')); print('phases=', c.execute('select count(*) from phases').fetchone()[0]); print('items=', c.execute('select count(*) from rubric_items').fetchone()[0])"
# 期待: phases=7, items=29
```

---

#### Task 6: README.md（メンバー配布用・セットアップ）

目的：
各自が自分の端末で導入・初期化できる手順を1枚にまとめる。

対象ファイル：
- `README.md`

変更内容：
- 次を簡潔に記載する：
  - 必要環境：Python 3.10以上（Python以外の別ソフトは不要）。
  - セットアップ：venv作成 → 有効化 → `pip install -r requirements.txt`。
  - キー設定（PowerShell）：`$env:OPENAI_API_KEY = "（各自のキー）"`、必要なら永続化コマンド。
  - DB初期化：`python -m app.db.init`。
  - 注記：UI起動・レビュー機能は後続フェーズ（P5）で追加される旨。
  - 各自ローカル型である旨（履歴はローカルに保存、提出証跡は後でエクスポートして持ち寄る）。

禁止事項：
- キーの実値を記載しない。

追加ルール：
- コマンドはPowerShell前提で書く。

---

## P1完了の目安
- venv作成・依存導入が通る
- キー未設定で安全に停止し、設定すると設定値が読める
- `python -m app.db.init` で phases=7 / rubric_items=31 が入る
- メンバーがREADMEだけで導入〜DB初期化まで辿れる
