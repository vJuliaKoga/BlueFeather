# BlueFeather P7 実装プロンプト（UIファイルアップロード対応） v0.1

> 位置づけ: P6 までで本体は完成。本フェーズ（実質 6.5 の追補）は、カバレッジ対象フェーズの提出フォームに「ブラウザからのファイルアップロード」を確実に表示し、配線する。
> 対応: Excel 1ファイル（targets/cases の2シート）と CSV 2ファイルの両方。両方あるときは Excel を優先。アップロードは uploads/ に保存して控えを残す。
> 参照: 詳細設計 v0.2 §2 / P2 の `load_from_xlsx`（実装済み）
>
> 命名メモ: 表示名は BlueFeather。実行時識別子（環境変数 `BLUEWING_DB_PATH`、モジュールパス `app/...`）は既存のまま据え置き。

## 背景（なぜ今これをやるか）

- 現状、提出フォームに「本文・提出者名」しか出ていないことがある。これは設計上、ファイル欄を **カバレッジ対象フェーズ（coverage_weight>0：詳細設計・テストケース実装・自動化）だけ** に出す作りのため。前半フェーズで出ないのは正しい挙動。
- ただし、対象フェーズでも欄が出ていない場合は「coverage対象フラグが画面に渡っていない／未配線」の可能性がある。本フェーズで、フラグの受け渡しとアップロードの配線を確実にする。

## 共通の前提・ルール（全タスク共通）

- 環境は Windows / PowerShell。実装は VSCode拡張の Claude Code。実行は人が手元で行う。
- 取込・検証は既存の `testcase_loader`（CSV/xlsx 共通の検証）を使う。`load_from_xlsx` は変更しない。
- 既存のフロー（本文＋提出者名の提出、CSV2ファイル経路）は壊さない。
- スコア計算・判定・LLM呼び出しを画面側に再実装しない（pipeline / engine 経由）。
- キーをコード・ログ・画面に出さない。
- 指定外ファイルは触らない。意図が分かりにくい箇所だけ簡潔な日本語コメント。

---

#### Task 1: pipeline に workbook 経路と使用ファイルの記録を足す

目的：
単一Excelワークブックからも取込でき、使ったファイルの控えを記録する。

対象ファイル：
- `app/engine/pipeline.py`

変更内容：
- `run_phase_review(...)` に引数 `workbook_path: str | None = None` を追加（既存の `targets_path` / `cases_path` は残す）。
- 取込データの優先順：
  1. `workbook_path` があれば `testcase_loader.load_from_xlsx(workbook_path)`
  2. なければ `targets_path` と `cases_path` の両方があるとき `load_from_csv(...)`
  3. どちらも無ければカバレッジはスキップ（coverage_score=None）
- 実際に使ったファイルのパスを `artifacts.testcase_file_path` に記録する（提出物と控えの対応づけ）。
- それ以降（compute_coverage → 採点 → 判定 → 合成 → 保存）は既存のまま。

禁止事項：
- 既存のCSV2ファイル経路の挙動を変えない。
- 採点・判定ロジックに手を入れない。

完了確認（人が実行）：
```powershell
python -c "from app.engine.pipeline import run_phase_review; import inspect; print('workbook_path' in inspect.signature(run_phase_review).parameters)"
# 期待: True
```

---

#### Task 2: フェーズ画面にアップロード欄を表示する

目的：
カバレッジ対象フェーズで、Excel欄とCSV欄を確実に出す。

対象ファイル：
- `app/ui/templates/phase.html`

変更内容：
- 提出フォームの `<form>` に `enctype="multipart/form-data"` が付いていることを確認（無ければ付ける）。
- ビューから渡るフラグ（例 `coverage_enabled`）が真のときだけ、アップロード欄を表示：
  - Excel（1ファイル・targets/casesの2シート）: `<input type="file" name="workbook" accept=".xlsx">`
  - CSV targets: `<input type="file" name="targets" accept=".csv">`
  - CSV cases: `<input type="file" name="cases" accept=".csv">`
  - 補足文: 「Excel1ファイルでも、CSV2ファイルでも提出できます。両方ある場合はExcelを優先します。」
- フラグが偽（前半フェーズ）のときは欄を出さない。

禁止事項：
- 画面側で取込・採点・判定を再実装しない（渡された値の表示と入力のみ）。

完了確認：
- Task 3・4 で起動して表示確認。

---

#### Task 3: 提出処理の受け取り・保存・配線

目的：
アップロードを受けて uploads/ に残し、pipeline に渡す。フラグも確実に渡す。

対象ファイル：
- `app/main.py`

変更内容：
- `GET /phases/{key}`：テンプレートに **`coverage_enabled = (phase.coverage_weight > 0)`** を必ず渡す（欄が出ない不具合の予防）。
- `POST /phases/{key}/submit`：
  - `workbook`（.xlsx）、`targets`（.csv）、`cases`（.csv）を任意の UploadFile として受ける。
  - 拡張子を検証（workbook は .xlsx、targets・cases は .csv）。不正なら phase 画面にメッセージを出して差し戻す（500で落とさない）。
  - アップロードされたファイルは `uploads/` に **保存して残す**。ファイル名は衝突しないよう一意化（例: 日時＋フェーズキー＋元ファイル名）。
  - 優先順（workbook → CSV2ファイル → なし）で、保存先パスを `run_phase_review(...)` に渡す。
  - 完了後、作成された review の詳細へリダイレクト。

禁止事項：
- アップロードを保存せず捨てる実装にしない（uploads/ に残す方針）。
- スコア計算・判定・LLM呼び出しを main.py に再実装しない。

追加ルール：
- `uploads/` が無ければ作成する。

完了確認（人が実行）：
```powershell
$env:OPENAI_API_KEY = "（各自のキー）"
uvicorn app.main:app --reload
# detailed_design のフェーズ画面に、Excel欄・CSV欄（targets/cases）が表示されることを確認
```

---

#### Task 4: サンプルワークブック（fixture）と通し確認

目的：
動作確認用に、既存CSVと同内容の .xlsx を用意する。

対象ファイル：
- `samples/make_workbook.py`
- （生成物）`samples/sample.xlsx`

変更内容：
- `make_workbook.py`：openpyxl で `samples/targets.csv` と `samples/cases.csv` を読み、シート名 `targets` / `cases` を持つ `samples/sample.xlsx` を生成する小スクリプト。
- 実行して `samples/sample.xlsx` を作る（targets/cases の内容は変えず、Excel化するだけ）。

完了確認（人が実行）：
```powershell
python samples/make_workbook.py
python -c "from app.ingest.testcase_loader import load_from_xlsx; t,c=load_from_xlsx('samples/sample.xlsx'); print(len(t), len(c))"
# 期待: 8 6

# ブラウザ通し確認
$env:OPENAI_API_KEY = "（各自のキー）"
uvicorn app.main:app --reload
# detailed_design に artifact を貼り、Excel欄に samples/sample.xlsx を指定して提出
# → CSV2ファイルのときと同じ coverage_score 73.75 由来の内訳になる
# → uploads/ にアップロードしたファイルが残っていることを確認
```

---

## P7完了の目安
- カバレッジ対象フェーズ（詳細設計・テストケース実装・自動化）に、Excel欄とCSV欄が表示される
- 前半フェーズ（テスト計画〜基本設計）には欄が出ない（正しい挙動）
- Excel1ファイル / CSV2ファイルのどちらでも提出でき、両方あればExcel優先
- 既存のCSV経路・本文提出は壊れない
- アップロードしたファイルが uploads/ に残り、DBの記録（artifacts.testcase_file_path）と対応づく
- sample.xlsx 提出時、CSVのときと同じ 73.75 由来の内訳になる
