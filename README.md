# BlueFeather

テスト設計の各フェーズを採点・ゲート判定する、各自ローカル型のツールです。
このドキュメントは導入〜DB初期化までの手順をまとめたものです（コマンドは PowerShell 前提）。

## 必要環境

- Python 3.10 以上（Python 以外の別ソフトは不要）

## セットアップ

```powershell
# 1. 仮想環境の作成
python -m venv .venv

# 2. 有効化
.\.venv\Scripts\Activate.ps1

# 3. 依存のインストール
pip install -r requirements.txt
```

## OpenAI APIキーの設定

キーは環境変数からのみ読み込みます。**コードや設定ファイル（.env 含む）には書きません。**

```powershell
# 現在のセッションだけ有効
$env:OPENAI_API_KEY = "（各自のキー）"
```

```powershell
# 永続化したい場合（ユーザー環境変数に保存。新しい端末セッションから有効）
setx OPENAI_API_KEY "（各自のキー）"
```

必要に応じて使用モデルや DB パスも環境変数で指定できます（任意）。

```powershell
$env:OPENAI_MODEL    = "（使用モデル名）"   # 未指定なら既定値
$env:BLUEFEATHER_DB_PATH = "bluefeather.db"       # 未指定なら bluefeather.db
```

## DB初期化

```powershell
python -m app.db.init
```

フェーズ定義とルーブリック配点が `app/settings/*.yaml` から投入されます。再実行しても重複しません（冪等）。

## 通し確認（提出 → あと一歩 → 再提出 → エクスポート）

「提出 → あと一歩 → 改善して再提出 → エクスポート」を一気通貫で確認できます（コマンドは PowerShell 前提）。

```powershell
$env:OPENAI_API_KEY = "（各自のキー）"
uvicorn app.main:app --reload
```

1. `detailed_design` のフェーズ画面で、成果物本文に `samples/artifact.md` の内容、
   targets に `samples/targets.csv`、cases に `samples/cases.csv` を添えて提出します。
   `cases.csv` は一部の target しか網羅していないため、カバレッジが下がり「あと一歩」になります。
2. 同じフェーズに、cases を `samples/cases_full.csv` に差し替えて再提出します（全 target をカバー）。
   カバレッジは 100 に上がります。
3. フェーズ画面の「証跡をエクスポート（Markdown / JSON）」から履歴をダウンロードします。
   CLI でも書き出せます。

```powershell
python -m app.engine.export --phase detailed_design --format md   --out exports/
python -m app.engine.export --phase detailed_design --format json --out exports/
```

> 注記: 合否（開門）の最終判定はカバレッジに加え、LLM のルーブリック採点にも依ります。
> このため、再提出で必ず開門するとは限りません。一方で、カバレッジが 100 に上がることは
> 決定的に確認できます（下記）。

```powershell
# cases_full でカバレッジが 100 になることを決定的に確認
python -m app.engine.coverage --targets samples/targets.csv --cases samples/cases_full.csv
# 期待: 全技法 rate 1.00、coverage_score = 100.00
```

## 持ち寄り（証跡の集約）

各自ローカル型のため、提出証跡は各自が書き出して持ち寄り、まとめ役が集約します。

- 各自: フェーズごとに `python -m app.engine.export --phase <key> --format md|json --out exports/`
  （`--phase all` で全フェーズを一括書き出し）。
- まとめ役: 集めた JSON を機械的に集約する／Markdown を読みやすく束ねる。
- エクスポートは決定的です（DB の保存値を整形するだけ。再採点・LLM 呼び出しはしません）。
  キーや機微情報は出力ファイルに含めません。

## 注記

- 各自ローカル型です。履歴は各自の端末にローカル保存されます。提出証跡はエクスポートして持ち寄る運用とします。
