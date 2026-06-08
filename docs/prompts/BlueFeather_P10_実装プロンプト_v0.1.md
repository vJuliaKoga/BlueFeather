# BlueFeather P10 実装プロンプト（自動化フェーズ・DeepEval結果取込） v0.1

> 目的: 自動化フェーズ（api_automation）の入力を「実装済みテストの実行結果（DeepEval JSON）」に対応させる。実測（pass_rate / メトリクス）を決定的スコアとして coverage 枠に流し込む。
> 重要な切り分け: 自動化フェーズの入力は **実装済みテストケースとその実行結果** であって、観点カバレッジ（P2の targets/cases）ではない。よって自動化フェーズでは観点カバレッジを使わず、DeepEval実測でスコアを作る。
> 参照: 詳細設計 v0.2 §5.1（api_automation: rubric_weight 0.4 / coverage_weight 0.6）/ P4 pipeline
>
> 命名メモ: 表示名は BlueFeather。実行時識別子（`BLUEWING_DB_PATH`、`app/...`）は据え置き。

## 投稿用JSONスキーマ（これに合わせて DeepEval を吐かせる）

```json
{
  "phase": "api_automation",
  "summary": { "total": 20, "passed": 18, "pass_rate": 0.9 },
  "metrics": [
    { "name": "answer_relevancy", "passed": 17, "total": 20, "avg_score": 0.86 },
    { "name": "faithfulness",     "passed": 19, "total": 20, "avg_score": 0.94 }
  ],
  "cases": [
    { "test_id": "T001", "metric": "answer_relevancy", "score": 0.91, "passed": true }
  ]
}
```

- `summary` 必須（total / passed / pass_rate）。
- `metrics` 必須（DeepEvalのメトリクスごとの passed/total/avg_score）。表示と将来の重み付け用。
- `cases` 任意（テスト別の詳細表示用。観点との紐付けはしない）。
- `code_coverage` は今回は使わない（省略）。将来 coverage.py を足すときに任意フィールドとして追加余地を残す。

## 決定的スコアの当て方（自動化フェーズ）

- `automation_score = pass_rate × 100`（まずはこれを基準。メトリクスは内訳表示）。
- pipeline では、自動化フェーズの `coverage_score` 枠にこの automation_score を入れる。
- `total_score = rubric_weight × rubric_score + coverage_weight × automation_score`（0.4 / 0.6）。

## 共通ルール

- 環境は Windows / PowerShell。実装は Claude Code。実行は人。
- DeepEval取込は **決定的**（JSONを読んで集計するだけ。LLM不使用）。
- 既存フェーズ（detailed_design / testcase_impl の観点カバレッジ経路）は壊さない。
- 指定外ファイルは触らない。意図が分かりにくい箇所だけ簡潔な日本語コメント。

---

#### Task 1: app/ingest/deepeval_loader.py（DeepEval結果の取込・検証）

目的：
投稿用スキーマのJSONを読み、構造化・検証する。

対象ファイル：
- `app/ingest/deepeval_loader.py`

変更内容：
- pydantic か dataclass で、summary / metrics / cases(任意) / code_coverage(任意) を表すモデルを定義。
- `load_deepeval(json_path: str)` を実装：必須欠落・型不正・pass_rate が 0〜1 外、などを検証して `DeepEvalValidationError`（messages一覧）でまとめて送出。
- `cases` に target_ids 等は要求しない（観点カバレッジとは無関係）。

禁止事項：
- 観点カバレッジ（targets/cases）の仕組みと混ぜない。
- LLMを使わない。

完了確認（人が実行・Task 5のサンプル作成後）：
```powershell
python -c "from app.ingest.deepeval_loader import load_deepeval; r=load_deepeval('samples/deepeval_sample.json'); print(r.summary.pass_rate)"
# 期待: 0.9
```

---

#### Task 2: app/engine/automation_score.py（実測スコア・決定的）

目的：
DeepEval結果から自動化フェーズの決定的スコアを出す。

対象ファイル：
- `app/engine/automation_score.py`

変更内容：
- `compute_automation_score(result) -> dict`：
  - `automation_score = round(result.summary.pass_rate × 100, 2)`。
  - 内訳として metrics（name, passed/total, avg_score）をそのまま保持して返す。
- 決定的・LLM非依存。

禁止事項：
- pass_rate 以外の重み付けを今は入れない（出力を見てから検討。コメントでその旨を明記）。

完了確認（人が実行）：
```powershell
python -c "from app.ingest.deepeval_loader import load_deepeval; from app.engine.automation_score import compute_automation_score; print(compute_automation_score(load_deepeval('samples/deepeval_sample.json'))['automation_score'])"
# 期待: 90.0
```

---

#### Task 3: pipeline に自動化フェーズの分岐を足す

目的：
自動化フェーズでは観点カバレッジではなくDeepEval実測を coverage_score に使う。

対象ファイル：
- `app/engine/pipeline.py`

変更内容：
- フェーズごとの入力種別を定数で持つ（例）：
  ```python
  COVERAGE_INPUT_KIND = {
      "detailed_design": "viewpoint",
      "testcase_impl": "viewpoint",
      "api_automation": "deepeval",
  }
  ```
  （将来 phases.yaml へ外出し可。今は定数でよい）
- `run_phase_review(...)` に `deepeval_path: str | None = None` を追加。
- 分岐：
  - kind が `deepeval`（api_automation）：`load_deepeval` → `compute_automation_score` → その値を `coverage_score` として採点に流す。観点カバレッジ（targets/cases）は使わない。metrics は内訳として保存。使用ファイルパスを記録。
  - kind が `viewpoint`：従来どおり targets/cases から coverage を計算。
  - kind 指定なし：coverage_score=None。
- rubric（LLM）採点は従来どおり成果物本文を対象に行う。

禁止事項：
- 観点カバレッジ経路と自動化経路を取り違えない。
- 採点式そのもの（total_score の計算）は変えない（coverage_score の出どころを差し替えるだけ）。

完了確認（人が実行）：
```powershell
python -c "from app.engine.pipeline import run_phase_review; import inspect; print('deepeval_path' in inspect.signature(run_phase_review).parameters)"
# 期待: True
```

---

#### Task 4: UI（自動化フェーズはDeepEval JSONを受ける）

目的：
自動化フェーズの画面でDeepEval結果JSONをアップロードでき、結果を表示する。

対象ファイル：
- `app/ui/templates/phase.html`
- `app/ui/templates/review.html`
- `app/main.py`

変更内容：
- `phase.html`：入力種別が `deepeval` のフェーズ（api_automation）では、targets/cases や Excel 欄ではなく **「DeepEval結果JSON」アップロード欄**（accept=".json"）を表示。`viewpoint` のフェーズは従来どおり。成果物本文（コード抜粋や方針の説明）の textarea は共通で残す。
- `main.py`：`POST /phases/{key}/submit` で、自動化フェーズのとき .json を受けて uploads/ に保存し、`deepeval_path` として `run_phase_review` に渡す。拡張子検証（.json）。フェーズ種別は `COVERAGE_INPUT_KIND` で判定し、テンプレートにも種別を渡す。
- `review.html`：自動化フェーズの所見では、coverage 内訳の代わりに **DeepEval内訳**（pass_rate、メトリクス別 passed/total・avg_score）を表示。

禁止事項：
- 画面で集計・採点を再実装しない（loader / automation_score / pipeline 経由）。
- 既存フェーズのCSV/Excel UIを壊さない。

完了確認（人が実行・実呼び出し）：
```powershell
$env:OPENAI_API_KEY = "（各自のキー）"
uvicorn app.main:app --reload
# api_automation のフェーズ画面に「DeepEval結果JSON」欄が出ること
# samples/deepeval_sample.json を投稿 → 所見＋DeepEval内訳（pass_rate 0.9 由来＝automation_score 90.0）が表示される
```

---

#### Task 5: サンプルとテスト

目的：
取込・スコアの正しさを決定的に検証する。

対象ファイル：
- `samples/deepeval_sample.json`
- `tests/test_deepeval.py`

変更内容：
- `samples/deepeval_sample.json`：上記スキーマ例（total 20 / passed 18 / pass_rate 0.9、metrics 2件、cases 数件）。
- `tests/test_deepeval.py`：
  - `load_deepeval` 正常読込（pass_rate 0.9、metrics 2件）。
  - 必須欠落・pass_rate 範囲外で `DeepEvalValidationError`。
  - `compute_automation_score` が `automation_score == 90.0` を返す。
  - `code_coverage` を含まないJSONでも正常に読める（任意フィールド）。

禁止事項：
- ネットワーク・LLMを使わない。

完了確認（人が実行）：
```powershell
pytest tests/test_deepeval.py -q
```

---

## P10完了の目安
- 自動化フェーズで DeepEval結果JSON を投稿でき、所見に DeepEval内訳が出る
- `automation_score = pass_rate × 100`（サンプルで 90.0）が決定的に出る
- 自動化フェーズの total_score が 0.4×rubric + 0.6×automation_score で出る
- 観点カバレッジ経路（detailed_design など）と取り違えない／壊さない
- code_coverage は省略でも動く（将来の任意拡張余地のみ確保）

## 補足
- DeepEvalスクリプト側は、この投稿用スキーマに合わせて結果を整形して出力する（生出力をそのまま投げない）。
- pass_rate 以外（メトリクス avg_score の重み付け等）をスコアに混ぜたくなったら、automation_score.py だけ直せばよい。出力を見てから調整する想定。
