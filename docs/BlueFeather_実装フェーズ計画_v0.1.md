# BlueFeather 実装フェーズ計画（Phase task list） v0.1

> 対象: BlueFeather 企画書 v0.3 / 詳細設計 v0.2 / ペルソナ定義書 v0.2 / prompts.py
> 前提:
> - 動かし方は **各自ローカル型**（各自で導入＋各自のOPENAI_API_KEY、履歴はローカルSQLiteに分散）
> - 環境は **Windows / PowerShell**、実装は **VSCode拡張のClaude Code**
> - 実行主体は人（Claude Codeはコマンドを提示し、実行は各自が手元で行う）
> - APIキーはファイルに書かず **環境変数 `OPENAI_API_KEY`** から読む
> - ゲートは「チームを縛る仕組み」ではなく **各自の自己チェック**。提出証跡は各自の履歴を持ち寄る
>
> 各Pは小さく作って、完了条件をPowerShellで確認してから次へ進む。各P完了時に、そのPのClaude Code実装プロンプトを別途起こす想定。

---

## P1: 雛形・設定・DBスキーマ・セットアップ

### ゴール
誰でも自分の端末で「環境を作って起動準備が整う」ところまで。

### タスク
- ディレクトリ構成（詳細設計§1）の雛形作成。
- `requirements.txt` 作成。最小構成:
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
- `app/config.py`: 環境変数読込。`OPENAI_API_KEY` 未設定なら明示エラーで停止。`OPENAI_MODEL`・`BLUEFEATHER_DB_PATH` も環境変数/既定値から。**キーは保持・出力しない。**
- `app/db/schema.sql`（詳細設計§7のDDL）。
- `app/settings/phases.yaml` `rubrics.yaml`（§4・§5の配点・閾値ドラフトを投入）。
- 起動時にYAML→DBへ投入（既存なら差分更新）する初期化処理。
- メンバー配布用 `README.md`（導入手順・キー設定・起動方法）。

### 完了条件
- [ ] venv作成・依存インストールが成功する
- [ ] `OPENAI_API_KEY` 未設定時に分かりやすいエラーで止まる
- [ ] DB初期化で全テーブルが作られ、phases/rubric_itemsにドラフト値が入る

### PowerShellでの確認
```powershell
python -V                                  # 3.10以上を確認
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# キー設定（セッション or ユーザー永続化のどちらか）
$env:OPENAI_API_KEY = "（各自のキー）"

# DB初期化（実装したスクリプト/コマンドを実行）
python -m app.db.init

# テーブル確認
python -c "import sqlite3,os; c=sqlite3.connect(os.environ.get('BLUEFEATHER_DB_PATH','bluefeather.db')); print([r[0] for r in c.execute('select name from sqlite_master where type=\""table\""')])"
```

### 成果物
雛形一式、requirements.txt、schema.sql、settings/*.yaml、README.md

---

## P2: CSV/Excel取込 ＋ 定量カバレッジ計算（関守エンジン・決定的）

### ゴール
targets/cases を読み込み、技法別カバレッジを決定的に算出できる。

### タスク
- `app/ingest/testcase_loader.py`: targets/cases の読込（CSV/Excel）と検証（必須列・重複ID・未定義参照）。
- `app/engine/coverage.py`: 技法別 covered/total/rate、`coverage_score`（§3の式・技法重み）。
- 単体テスト（pytest）: 正常系、未定義参照エラー、total=0の扱い、重み付き加重平均。

### 完了条件
- [ ] サンプルのtargets/casesから、技法別カバレッジと`coverage_score`が出る
- [ ] 不正な入力（未定義target_id等）が検証で弾かれる
- [ ] 同じ入力なら必ず同じ結果（LLM非依存）

### PowerShellでの確認
```powershell
pytest tests/test_coverage.py -q
# サンプルを通して内訳を表示する確認用スクリプト
python -m app.engine.coverage --targets samples\targets.csv --cases samples\cases.csv
```

### 成果物
testcase_loader.py、coverage.py、テスト、samples/

---

## P3: BlueFeather語り層（LLM呼び出し・スキーマ検証・フォールバック）

### ゴール
prompts.py を使って、ルーブリック項目の定性スコア＋語りの文面をJSONで安全に得られる。

### タスク
- `app/persona/prompts.py`（作成済みを配置）。
- `app/persona/schema.py`: 出力JSONのpydanticモデル（§6.3）。
- `app/persona/reviewer.py`: `build_messages()` → OpenAI呼び出し → JSON抽出・検証。
- フォールバック: 失敗時1回再試行 → なお失敗で `status='manual_check'`、生テキスト保存、落とさない。

### 完了条件
- [ ] 1フェーズ分のルーブリックと成果物を渡すと、スキーマ準拠JSONが返る
- [ ] 文面に点数・合否が含まれない（語りのみ）
- [ ] 壊れた応答をモックしても落ちず manual_check になる

### PowerShellでの確認
```powershell
pytest tests/test_schema.py tests/test_fallback.py -q   # 検証・フォールバックはモックで
$env:OPENAI_API_KEY = "（各自のキー）"
python -m app.persona.reviewer --phase detailed_design --artifact samples\artifact.md  # 実呼び出し確認
```

### 成果物
prompts.py、schema.py、reviewer.py、テスト

---

## P4: 合算・合否判定・所見合成・ループ（関守エンジン）

### ゴール
定性スコア＋カバレッジから総合点・合否を決定的に出し、BlueFeatherの所見として合成できる。

### タスク
- `app/engine/scoring.py`: `rubric_score`（項目スコア×重み）、`total_score`（§5.1）。
- `app/engine/gate.py`: 閾値比較で `passed` 判定。「あと一歩／開門」のスコア行を決定的に生成。
- 所見合成: スコア行（エンジン）＋承認・指摘・結び（LLM文面）を §5テンプレート順に組む。
- `reviews`・`coverage_metrics`・`gate_status` への保存とラウンド管理（自己チェック前提）。
- 単体テスト: 合算の正しさ、閾値前後でのメッセージ切替。

### 完了条件
- [ ] 項目スコアとカバレッジから total_score が正しく出る
- [ ] 閾値以上で「開門」、未満で「あと一歩、ここ」の所見になる
- [ ] ラウンドと履歴がDBに残る

### PowerShellでの確認
```powershell
pytest tests/test_scoring.py tests/test_gate.py -q
```

### 成果物
scoring.py、gate.py、所見合成、テスト

---

## P5: FastAPI ＋ Jinja2 UI

### ゴール
ブラウザから成果物を提出し、BlueFeatherの所見を読める。

### タスク
- `app/main.py`: §8のエンドポイント（`/`、`/phases/{key}`、`/phases/{key}/submit`、`/reviews/{id}`、`/rubrics/{key}`）。
- `app/ui/templates`: ダッシュボード（7フェーズの進捗・ゲート状況）、フェーズ画面（提出フォーム＋ファイルアップロード＋ラウンド履歴）、所見表示（承認・スコア行・指摘・技法レコメンド・カバレッジ内訳）。
- 提出フロー結線: 取込・検証 → カバレッジ → LLM → 合算・判定 → 合成 → 保存。

### 完了条件
- [ ] ローカルで起動し、ブラウザで提出→所見表示まで通る
- [ ] CSV/Excelのアップロードと検証エラー表示が動く

### PowerShellでの確認
```powershell
uvicorn app.main:app --reload
# ブラウザで http://127.0.0.1:8000 を開いてサンプル提出
```

### 成果物
main.py、templates一式、static

---

## P6: 履歴エクスポート ＋ 通し動作確認

### ゴール
各自の履歴を持ち寄れる形に書き出し、提出〜開門までを一気通貫で確認する。

### タスク
- `app/engine/export.py`（または専用エンドポイント）: フェーズ/ラウンドのレビュー履歴を **Markdown と JSON** で書き出し。提出証跡として使える体裁に。
- 通し確認: 1フェーズ分のサンプルで、提出 → あと一歩 → 修正再提出 → 開門 → エクスポートまで。
- README更新: 持ち寄り手順（各自エクスポート → まとめ役が集約）。

### 完了条件
- [ ] レビュー履歴がMarkdown/JSONで書き出せる
- [ ] サンプル1フェーズで「あと一歩→開門→エクスポート」が通る

### PowerShellでの確認
```powershell
python -m app.engine.export --phase detailed_design --format md   --out exports\
python -m app.engine.export --phase detailed_design --format json --out exports\
```

### 成果物
export.py、exports/サンプル、更新版README

---

## 進め方メモ
- 各Pは「完了条件をPowerShellで確認 → 次のP」へ。順送りで小さく検証する。
- 各P着手時に、そのPだけのClaude Code実装プロンプトを起こす（詳細設計とこの計画を引用元にする）。
- 配点・閾値・技法重みはドラフト。P4以降で実データを見ながら調整する。

## 今後の調整候補
- ルーブリック各項目の採点ガイド（何点でどんな状態か）の言語化（LLMの採点ぶれ低減）。
- 状態遷移カバレッジの母集団（0スイッチ/1スイッチ）。
- 自動化フェーズの実測カバレッジ取り込み（外部レポート連携）。
