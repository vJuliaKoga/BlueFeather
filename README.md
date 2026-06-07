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

## 注記

- UI 起動・レビュー機能は後続フェーズ（P5）で追加されます。現時点では雛形・設定・DB初期化までです。
- 各自ローカル型です。履歴は各自の端末にローカル保存されます。提出証跡は後でエクスポートして持ち寄る運用とします。
