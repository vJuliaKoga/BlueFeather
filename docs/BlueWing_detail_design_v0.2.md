# BlueWing　詳細設計 v0.2

> 対象企画書: BlueWing 企画書 v0.3
> 前提: テストケース入力 = 構造化CSV/Excel、UI = Jinja2サーバレンダリング
>
> **v0.2の変更点**：名称をBlueWingに統一。決定的計算・判定を「関守エンジン」、所見の文面生成を「BlueWing語り層」として明確に分離。合否は「あと一歩／開門」で表現。
>
> 配点・重み・閾値の初期値は調整前提の「ドラフト」。

---

## 1. モジュール構成

```
bluewing/
├─ app/
│   ├─ main.py                 # FastAPIエントリ・ルーティング
│   ├─ config.py               # 環境変数・設定読込（APIキーは保持しない）
│   ├─ settings/
│   │   ├─ phases.yaml          # フェーズ定義・閾値・重み
│   │   └─ rubrics.yaml         # フェーズ別ルーブリック項目・配点
│   ├─ db/
│   │   ├─ schema.sql
│   │   └─ repository.py
│   ├─ ingest/
│   │   └─ testcase_loader.py   # CSV/Excel取込・検証
│   ├─ engine/                 # 関守エンジン（決定的）
│   │   ├─ coverage.py          # 定量カバレッジ計算
│   │   ├─ scoring.py           # 総合点の合算
│   │   └─ gate.py              # 合否判定（あと一歩／開門）・ループ制御
│   ├─ persona/                # BlueWing 語り層（LLM）
│   │   ├─ reviewer.py          # ルーブリック採点・技法レコメンド呼び出し
│   │   ├─ prompts.py           # ペルソナ定義書を反映したシステムプロンプト
│   │   └─ schema.py            # 出力JSONスキーマ（pydantic）
│   ├─ ui/
│   │   ├─ templates/
│   │   └─ static/
├─ tests/
└─ README.md
```

設計原則: カバレッジ・重み付き合算（rubric_score / total_score）・合否判定は **関守エンジン（engine/）** が決定的に行う。各ルーブリック項目の定性スコア（0〜max）と、所見・指摘・技法レコメンドの **文面** は **BlueWing語り層（persona/）** が担う。総合点・カバレッジ点・合否判定はLLMに出させない。

## 2. テストケース入力フォーマット（CSV/Excel）

ワークブック1冊（または2つのCSV）に、次の2つのシート/表を持つ。

### 2.1 targets シート（カバレッジ対象＝分母）

| 列名 | 必須 | 説明 |
|---|---|---|
| `target_id` | ○ | 対象の一意ID（例: BVA-age-01） |
| `technique` | ○ | 同値分割 / 境界値分析 / デシジョンテーブル / 状態遷移 |
| `category` | ○ | パラメータ名・条件名・状態名など |
| `target` | ○ | 具体的対象（例: age=min-1、ルールR03、S1→S2(submit)） |
| `must_cover` | - | 必須対象か（Y/N、未指定はY扱い） |
| `note` | - | 備考 |

### 2.2 cases シート（テストケース＝実績）

| 列名 | 必須 | 説明 |
|---|---|---|
| `test_id` | ○ | テストケースの一意ID |
| `technique` | ○ | 技法 |
| `precondition` | - | 前提条件 |
| `input` | ○ | 入力値・操作 |
| `expected` | ○ | 期待結果 |
| `target_ids` | ○ | カバーするtarget_id（カンマ区切り、targetsと相互参照） |
| `note` | - | 備考 |

`cases.target_ids` を正とし、ツールが `targets` と突き合わせてカバレッジを計算する。テスターは「対象を列挙 → ケースを書いて target_id を紐付ける」だけでよい。

### 2.3 取込時の検証（ingest/testcase_loader.py）

- 必須列の存在、`target_id` の重複・未定義参照（cases が存在しない target_id を指す）を検出。
- 検証エラーは提出を弾き、画面に明示する（誤集計を防ぐ）。
- 設計初期フェーズ（テスト計画〜基本設計）はテストケース未提出でも可。対象外フェーズではカバレッジ計算をスキップ。

## 3. 定量カバレッジ計算（engine/coverage.py）

LLMを通さず、取り込んだ表だけで計算する。

- 技法ごとに、`covered = target_ids で1件以上参照された target 数`、`total = must_cover=Y の target 数`。
- `coverage_rate(technique) = covered / total`（total=0 のときは対象外）。
- 技法重み（境界値・分岐を高く）で加重平均し、`coverage_score`（0〜100）を出す。

技法重みのドラフト:

| 技法 | 重み |
|---|---|
| 境界値分析 | 0.35 |
| デシジョンテーブル（分岐） | 0.35 |
| 状態遷移 | 0.20 |
| 同値分割 | 0.10 |

```
coverage_score = 100 × Σ(weight_t × coverage_rate_t) / Σ(weight_t)   ※ total>0 の技法のみ
```

出力は `coverage_metrics`（技法別の total / covered / rate）として保存し、画面で内訳を見せる。

## 4. ルーブリック設計（settings/rubrics.yaml）

各項目は `max_score`（例: 0〜4）と `weight` を持つ。LLM（BlueWing語り層）が項目ごとに根拠つきで採点し、関守エンジンが加重して `rubric_score`（0〜100）を決定的に算出する。

```
rubric_score = 100 × Σ(weight_i × score_i / max_score_i) / Σ(weight_i)
```

### 配点ドラフト（フェーズ別・調整前提）

**テスト計画**: スコープ・対象の明確さ(1.0) / テスト戦略の妥当性(1.2) / リスクの識別と対応(1.0) / 体制・スケジュールの現実性(0.8) / 完了・合格基準の明確さ(1.0)

**要件抽出**: 要件の網羅性(1.2) / テスト可能性(1.2) / 曖昧さの排除(1.0) / 優先度の整理(0.8) / トレーサビリティ(0.8)

**観点整理**: 観点の網羅性(1.3) / 構造化・分類の妥当性(1.0) / 技法割当の妥当性〔技法レコメンド対象〕(1.2) / 抜け漏れ・重複のなさ(1.0)

**基本設計**: 技法選択の妥当性(1.2) / テスト条件導出の網羅性(1.3) / 観点との対応づけ(1.0) / 設計の一貫性(0.8)

**詳細設計**: 境界値特定の網羅性(1.5) / 分岐・デシジョンの網羅性(1.5) / 状態遷移の網羅性(1.0) / 期待結果の明確さ(1.0)

**テストケース実装**: 具体性・実行可能性(1.0) / 境界値ケースの網羅(1.5) / 分岐ケースの網羅(1.5) / 期待結果の検証可能性(1.0)

**APIテスト・自動化**: 自動化対象選定の妥当性(1.0) / アサーションの十分さ(1.2) / 保守性・再実行性(0.8)（機械的カバレッジは coverage_score 側）

## 5. 総合点とゲート制御（engine/scoring.py, engine/gate.py）

### 5.1 総合点

```
total_score = rubric_weight × rubric_score + coverage_weight × coverage_score
```

`rubric_weight + coverage_weight = 1.0`。フェーズ別ドラフト:

| フェーズ | rubric_weight | coverage_weight | 合格閾値ドラフト |
|---|---|---|---|
| テスト計画 | 1.0 | 0.0 | 80 |
| 要件抽出 | 1.0 | 0.0 | 80 |
| 観点整理 | 1.0 | 0.0 | 80 |
| 基本設計 | 1.0 | 0.0 | 80 |
| 詳細設計 | 0.7 | 0.3 | 80 |
| テストケース実装 | 0.6 | 0.4 | 80 |
| APIテスト・自動化 | 0.4 | 0.6 | 80 |

### 5.2 合否判定とループ

- `total_score >= 合格閾値` → `gate_status.closed=1` → 次フェーズ解放（**開門**）。
- `total_score < 合格閾値` → クローズせず、**「あと一歩」** として現在地と不足点を返す。人が修正し ラウンドN+1 を提出。
- 「あと一歩／開門」の判定は **関守エンジンが決定的に行い**、BlueWingはその結果を語り口で包む（数値判定をLLMに委ねない）。
- フェーズは `order_no` 順。前フェーズが未クローズだと次フェーズの提出はできない（任意で緩める設定も可）。

## 6. BlueWing 語り層（persona/）

### 6.1 役割

- ルーブリック項目ごとの採点（score＋根拠＋指摘の文面）。
- 観点整理など対象フェーズでの技法レコメンド。
- 所見テキスト（承認・視点・結び）の生成。
- 総合点・カバレッジ点・合否判定は出さない（関守エンジンの担当）。

### 6.2 システムプロンプト

`persona/prompts.py` に、**BlueWing ペルソナ定義書 v0.2** を反映したシステムプロンプトを置く。語り口・話法・禁止表現・所見テンプレートはペルソナ定義書に準拠する。

### 6.3 出力JSONスキーマ（pydanticで検証）

```json
{
  "phase": "detailed_design",
  "rubric_scores": [
    { "item_key": "boundary_coverage", "score": 3, "max_score": 4,
      "rationale": "BlueWingの語り口での根拠", "findings": ["指摘1", "指摘2"] }
  ],
  "technique_recommendations": [
    { "target": "年齢入力欄", "recommended_technique": "境界値分析", "reason": "範囲制約があるため" }
  ],
  "acknowledgement": "できている点への承認の一言（語り口）",
  "closing": "委ねる結びの一言（語り口）",
  "overall_findings": ["横断的な指摘"]
}
```

- `acknowledgement` と `closing` は、所見テンプレートの「承認」「委ねる結び」に充てる。
- スコア行（「あと一歩、ここ」／「開門」）は関守エンジンの判定から決定的に生成し、上記の語りと合成する。

### 6.4 パース失敗時のフォールバック

1. JSON抽出（コードフェンス除去）→ pydantic検証。
2. 失敗時: 1回だけ「JSONのみで再出力せよ」と再試行。
3. それでも失敗: `raw_llm_output` に生テキストを保存し、`reviews.status='manual_check'` として記録。スコアは付けず画面に「要手動確認」を表示。クラッシュさせない。

## 7. SQLite スキーマ（db/schema.sql）

```sql
CREATE TABLE phases (
  id INTEGER PRIMARY KEY, key TEXT UNIQUE, name TEXT, order_no INTEGER,
  pass_threshold REAL, rubric_weight REAL, coverage_weight REAL
);
CREATE TABLE rubric_items (
  id INTEGER PRIMARY KEY, phase_id INTEGER REFERENCES phases(id),
  item_key TEXT, description TEXT, max_score INTEGER, weight REAL
);
CREATE TABLE artifacts (
  id INTEGER PRIMARY KEY, phase_id INTEGER REFERENCES phases(id),
  round_no INTEGER, body TEXT, testcase_file_path TEXT,
  submitted_by TEXT, submitted_at TEXT
);
CREATE TABLE reviews (
  id INTEGER PRIMARY KEY, artifact_id INTEGER REFERENCES artifacts(id),
  rubric_score REAL, coverage_score REAL, total_score REAL, passed INTEGER,
  rubric_breakdown TEXT, findings TEXT, recommendations TEXT,
  acknowledgement TEXT, closing TEXT,
  raw_llm_output TEXT, status TEXT, created_at TEXT
);
CREATE TABLE coverage_metrics (
  id INTEGER PRIMARY KEY, review_id INTEGER REFERENCES reviews(id),
  technique TEXT, total_targets INTEGER, covered_targets INTEGER,
  coverage_rate REAL, weight REAL
);
CREATE TABLE gate_status (
  phase_id INTEGER PRIMARY KEY REFERENCES phases(id),
  current_round INTEGER, closed INTEGER, closed_at TEXT
);
```

`phases` と `rubric_items` は起動時に `settings/*.yaml` から投入（既存なら差分更新）。

## 8. API設計（FastAPI）

| メソッド | パス | 役割 |
|---|---|---|
| GET | `/` | ダッシュボード（7フェーズの進捗・ゲート状況・最新スコア） |
| GET | `/phases/{key}` | フェーズ詳細・ラウンド履歴・最新所見 |
| POST | `/phases/{key}/submit` | 成果物提出（本文＋CSV/Excel）→ 採点・所見生成 |
| GET | `/reviews/{id}` | 所見詳細（承認・スコア・指摘・技法レコメンド・カバレッジ） |
| GET | `/rubrics/{key}` | ルーブリック配点の確認 |
| POST | `/rubrics/{key}` | 配点・閾値の調整（任意） |

`submit` の流れ: 取込・検証 → カバレッジ計算（対象フェーズ） → LLM採点・語り生成 → 総合点・合否判定（関守エンジン） → 所見合成 → 保存。

## 9. 設定・環境変数（config.py）

- `OPENAI_API_KEY`: 環境変数から読み込む。未設定なら起動時に明示エラーで停止。ファイルには書かない。
- `OPENAI_MODEL`: 環境変数で指定（設定で切替可能）。コードに固定しない。
- `BLUEWING_DB_PATH`: SQLiteの保存先（既定値あり）。
- 閾値・重み・ルーブリックは `settings/*.yaml`（キー類は一切含めない）。

PowerShell例:

```powershell
$env:OPENAI_API_KEY = "（各自のキー）"
$env:OPENAI_MODEL   = "（使用モデル名）"
```

## 10. エラーハンドリング・ロギング方針

- 取込検証エラー: 提出を弾き、不足列・未定義参照を画面に列挙。
- LLM呼び出し失敗: リトライ後、`manual_check` で記録。
- ログは標準ロギングでファイル出力。APIキーや本文の機微情報はログに残さない。

## 11. 実装フェーズ分割（次工程: Phase task list の素案）

- P1: 雛形・config・SQLiteスキーマ投入（YAML→DB）
- P2: CSV/Excel取込＋定量カバレッジ計算（関守エンジン、単体テスト付き）
- P3: BlueWing語り層＋LLM出力スキーマ検証＋フォールバック
- P4: 総合点合算＋合否判定＋所見合成＋ループ制御
- P5: FastAPIエンドポイント＋Jinja2 UI
- P6: 通し動作確認（1フェーズ分のサンプルで提出〜開門まで）

各Pの完了時に、PowerShellで実行できる確認手順を用意する。

## 12. 今後詰める論点（残課題）

- ルーブリック各項目の「採点ガイド（何点ならどういう状態か）」の言語化。
- 状態遷移カバレッジの定義粒度（0スイッチ/1スイッチ）。
- 自動化フェーズの実測カバレッジを外部ツール出力から取り込むかどうか。