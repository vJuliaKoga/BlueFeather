# BlueWing P5 実装プロンプト（Claude Code 用） v0.1

> 対象: 実装フェーズ計画 v0.1 の P5（FastAPI ＋ Jinja2 UI）
> 参照: 詳細設計 v0.2 §8（API設計） / ペルソナ定義書 v0.2（語り口・所見の見せ方）
>
> 各タスクは独立。1タスクずつ Claude Code に渡す。原則1〜2ファイルに限定する。

## 共通の前提・ルール（全タスク共通）

- 環境は Windows / PowerShell。実装は VSCode拡張の Claude Code。実行は人が手元で行う。
- UIは **Jinja2 サーバレンダリング**。Node・ビルド・外部CDN依存は使わない（CSSは同梱の1ファイル）。サーバ側のHTML `<form>` は通常どおり使ってよい。
- 提出処理は P4 の `engine.pipeline.run_phase_review` を呼ぶだけ。スコア計算・判定・LLM呼び出しを画面側に再実装しない。
- 見た目の方針: BlueWingらしく穏やかで読みやすい。「あと一歩」は警告色で煽らず前向きに、「開門」は控えめに祝う。装飾過多にしない。
- キーをコード・ログ・画面に出さない。
- 設計どおりに作る。指定外ファイルは触らない。意図が分かりにくい箇所だけ簡潔な日本語コメント。

---

#### Task 1: 共通レイアウトとスタイル（base.html, style.css）

目的：
全画面共通の枠とトーンを用意する。

対象ファイル：
- `app/ui/templates/base.html`
- `app/ui/static/style.css`

変更内容：
- `base.html`：
  - ヘッダーに「BlueWing — 9人目のメンバー」。グローバルナビ（ダッシュボードへ戻るリンク）。
  - `{% block content %}{% endblock %}` を本文に。
  - `style.css` を読み込む（`/static/style.css`）。
  - フッターに、内部レビュー支援ツールである旨の控えめな一文。
- `style.css`：
  - 落ち着いた配色（やわらかい背景、読みやすい本文色、アクセントは穏やかな青系を1色）。
  - 本文はシステムフォントスタック。行間ゆったり、横幅は読みやすい上限（例 760〜900px）。
  - 状態表示用のクラスを用意：`status-open`（開門・穏やかな緑/青）、`status-near`（あと一歩・煽らない琥珀系）、`status-todo`（未着手・グレー）。
  - 所見ブロック用に、引用のように少し内側に寄せた読みやすいスタイル。

禁止事項：
- 外部CDN・JSフレームワーク・Webフォント読み込み禁止。

完了確認：
- ブラウザで base を継承した画面が崩れず表示できること（確認はTask 4で）。

---

#### Task 2: ダッシュボードとフェーズ画面（dashboard.html, phase.html）

目的：
全フェーズの進捗一覧と、各フェーズの提出・履歴画面を作る。

対象ファイル：
- `app/ui/templates/dashboard.html`
- `app/ui/templates/phase.html`

変更内容：
- `dashboard.html`（base継承）：
  - 7フェーズを `order_no` 順に一覧。各行に：フェーズ名、状態（未着手 / あと一歩 / 開門済み を status クラスで色分け）、最新の総合点（あれば表示、なければ「—」）、フェーズ画面へのリンク。
  - 状態判定の前提値はビューから渡される（テンプレートは表示に専念）。
- `phase.html`（base継承）：
  - フェーズ名と合格閾値。
  - ルーブリック項目の一覧（item_keyの説明・最大点・重み）。
  - 提出フォーム（`POST /phases/{key}/submit`、`enctype=multipart/form-data`）：
    - 成果物本文（textarea）
    - 提出者名（text）
    - targets / cases ファイル（file 入力。coverage対象フェーズのときだけ表示。フラグはビューから受ける）
  - ラウンド履歴（各ラウンド: round_no、総合点、開門/あと一歩、レビュー詳細へのリンク）。

禁止事項：
- テンプレート内で計算・DBアクセスをしない（渡された値の表示のみ）。

完了確認：
- Task 4 で起動して表示確認。

---

#### Task 3: 所見表示（review.html）

目的：
BlueWingの所見と内訳を、穏やかに読める形で見せる。

対象ファイル：
- `app/ui/templates/review.html`

変更内容（base継承）：
- 上部に合成所見（`review_text`）を、所見ブロックのスタイルで読みやすく。
- スコア行は status クラスで色分け（開門/あと一歩）。`status='manual_check'` のときはスコアを出さず、「この回は自動採点を保留しました（要手動確認）」という穏やかな案内を出す。
- 技法レコメンド（あれば）一覧。
- カバレッジ内訳テーブル（技法 / covered / total / rate）。coverage対象外フェーズでは非表示。
- ルーブリック項目別の内訳（item説明・score/max・根拠）を折りたたみ等で（任意、無ければ一覧で可）。
- フェーズ画面へ戻るリンク。

禁止事項：
- スコア行以外の場所に点数を散らさない（本文の語りはそのまま尊重）。

完了確認：
- Task 4 で起動して表示確認。

---

#### Task 4: app/main.py（FastAPI・ルーティング・結線）

目的：
画面と処理をつなぎ、ブラウザから提出〜所見表示まで通す。

対象ファイル：
- `app/main.py`
- （必要なら）`app/db/repository.py` に「フェーズ別の最新レビュー取得」「レビュー1件取得」「ラウンド履歴取得」を追加

変更内容：
- FastAPI アプリ、`Jinja2Templates(directory="app/ui/templates")`、`StaticFiles` で `/static` を `app/ui/static` にマウント。
- ルート（詳細設計§8）：
  - `GET /`：全フェーズ＋状態＋最新総合点を集めて dashboard を描画。
  - `GET /phases/{key}`：フェーズ情報・ルーブリック項目・ラウンド履歴・coverage対象フラグ（coverage_weight>0）を渡して phase を描画。
  - `POST /phases/{key}/submit`：multipart を受ける（成果物本文・提出者・任意の targets/cases ファイル）。アップロードは `uploads/` 配下に保存し、そのパスを `run_phase_review` に渡す。完了後、作成された review の詳細へリダイレクト。
  - `GET /reviews/{id}`：review を取得して review を描画。
  - `GET /rubrics/{key}`：ルーブリック配点の確認（phase 画面の一部流用でも、簡易一覧でも可）。
- 取込検証エラー（`TestcaseValidationError`）は、phase 画面にメッセージ一覧を表示して提出を差し戻す（500で落とさない）。
- LLM が manual_check のときも、review 画面へ正常遷移する。

禁止事項：
- スコア計算・判定・LLM呼び出しを main.py に再実装しない（pipeline / repository 経由）。
- キーを画面・ログに出さない。

追加ルール：
- `uploads/` が無ければ作成する。

完了確認（人が実行・実呼び出し。P1のdb.init済み前提）：
```powershell
$env:OPENAI_API_KEY = "（各自のキー）"
uvicorn app.main:app --reload
# ブラウザで http://127.0.0.1:8000 を開く
# detailed_design を開き、samples/artifact.md の中身を貼り、targets/cases に samples のCSVを指定して提出
# → 「あと一歩」の所見と、カバレッジ内訳（coverage_score 73.75 由来）が表示される
```

---

## P5完了の目安
- `uvicorn` で起動し、ダッシュボードに7フェーズと状態が並ぶ
- フェーズ画面から成果物＋CSVを提出できる
- 提出後、BlueWingの所見・スコア行・カバレッジ内訳が穏やかに表示される
- 検証エラーは画面に出て差し戻し、manual_check も画面に正常表示（落ちない）

## メモ
- 履歴のエクスポート（持ち寄り用）は P6 で追加する。
