# BlueFeather P9 実装プロンプト（LLM出力のQA4AI） v0.1

> 目的: BlueFeather（レビューAI）の出力自体を品質保証する。レビューAIをレビューする層。
> 優先度:
> - コア（必須）: (d) ルール遵守チェック / (b) 根拠の妥当性 / (c) LLM-as-judge
> - 任意（時間があれば）: (e) トレース・可観測性 / (a) 採点の安定性
> 参照: P3 reviewer（`_call_llm`）/ ペルソナ定義書 v0.2 / reviews
>
> 命名メモ: 表示名は BlueFeather。実行時識別子（`BLUEWING_DB_PATH`、`app/...`）は据え置き。

## 設計方針

- ルール遵守（d）は **決定的・軽量**（毎回でも回せる）。根拠妥当性（b）と judge（c）は **LLMを使う二段検査**（オンデマンドで実行）。
- QA4AI のLLM呼び出しは、既存の `app/persona/reviewer._call_llm` を再利用してよい（モデルは config の `OPENAI_MODEL`。別モデルにしたい場合は env で切替可能にしてよいが必須ではない）。
- QA4AIの結果は新テーブル `qa4ai_results`(review_id, check_type, result_json, created_at) に保存する（`CREATE TABLE IF NOT EXISTS` で追加）。

## 共通ルール

- 環境は Windows / PowerShell。実装は Claude Code。実行は人。
- キーをコード・ログ・出力に書かない。LLM検査もモックでテストできるよう、呼び出しは差し替え可能に。
- 指定外ファイルは触らない。意図が分かりにくい箇所だけ簡潔な日本語コメント。

---

#### Task 1（コア・d）: app/qa4ai/rule_check.py（ルール遵守・決定的）

目的：
所見が BlueFeather のルールを守れているか、機械的に点検する。

対象ファイル：
- `app/qa4ai/rule_check.py`

変更内容：
- `check_rules(review_text: str, score_line: str | None = None) -> list[str]`（違反メッセージの一覧。空ならOK）：
  - 本文（score_line を除いた所見テキスト）に **点数表記（`\d+\s*点`）が無い**こと。
  - 禁止語「不合格」「ダメ」が無いこと。
  - 文の出だしに否定（「いや」「でも」「だって」）が無いこと。
  - （任意で）承認の一文が冒頭にあるか等の軽いチェックを足してよい。
- 決定的・LLM非依存。

禁止事項：
- LLM呼び出しをしない。

完了確認（人が実行）：
```powershell
python -c "from app.qa4ai.rule_check import check_rules; print(check_rules('いま73点。あと一歩です。'))"
# 期待: 点数表記の違反が1件以上返る（本文に点数が出ている例）
```

---

#### Task 2（コア・b）: app/qa4ai/grounding.py（根拠の妥当性・LLM）

目的：
所見の指摘が、成果物の記述に基づいているか（でっち上げが無いか）を検査する。

対象ファイル：
- `app/qa4ai/grounding.py`

変更内容：
- プロンプト（このファイル内に定義）：成果物本文と、BlueFeather が出した指摘（findings）を渡し、各指摘について「成果物に根拠があるか（grounded: true/false）」と理由をJSONで返させる。JSONのみ・コードフェンス無し。
- `check_grounding(artifact_body: str, findings: list[str]) -> list[dict]`：`_call_llm` 経由で呼び、各 finding に {finding, grounded, reason} を返す。パース失敗時は P3 同様に1回再試行→なお失敗で「判定保留」を返し落とさない。
- LLM呼び出しは `app/persona/reviewer._call_llm` を再利用（または同等の薄いラッパ）。テストで差し替えられること。

禁止事項：
- 採点・合否に影響を与えない（これは点検であって再採点ではない）。

完了確認：
- Task 5 のモックテストで検証。実呼び出しは Task 6 のUIから。

---

#### Task 3（コア・c）: app/qa4ai/judge.py（LLM-as-judge）

目的：
別LLMが、BlueFeather の所見の質を採点する。

対象ファイル：
- `app/qa4ai/judge.py`

変更内容：
- 評価軸（各 0〜4 など）：具体性 / 実行可能性 / ペルソナ遵守（承認から入る・否定なし・代替案あり）/ 点数や合否が文面に漏れていないか。
- プロンプト（このファイル内）：所見テキストを渡し、軸ごとのスコアとコメントをJSONで返させる（JSONのみ）。pydantic で検証。
- `judge_review(review_text: str) -> dict`：`_call_llm` 経由。パース失敗時は1回再試行→なお失敗で「判定保留」。
- judge 用の小さな pydantic モデルを定義（軸スコア＋コメント＋総評）。

禁止事項：
- BlueFeather 本体の採点・合否を上書きしない（独立した点検結果として保存）。

完了確認：
- Task 5 のモックテストで検証。

---

#### Task 4（コア）: 保存とUI結線（qa4ai_results ＋ 点検アクション）

目的：
QA4AIをレビュー画面から実行し、結果を保存・表示する。

対象ファイル：
- `app/main.py`
- `app/ui/templates/review.html`
- （スキーマ追加）`app/db/repository.py` または初期化に `qa4ai_results` テーブルを `CREATE TABLE IF NOT EXISTS`

変更内容：
- `qa4ai_results`(id, review_id, check_type['rule'|'grounding'|'judge'], result_json, created_at) を追加。
- `POST /reviews/{id}/qa4ai`：対象レビューに対し rule_check（決定的）＋ grounding ＋ judge を実行し、結果を保存。完了後レビュー画面へ戻る。
- `review.html`：
  - 「QA4AIで点検する」ボタン（このレビューに対して実行）。
  - 実行済みなら結果セクションを表示：ルール違反一覧（無ければ「違反なし」）、根拠妥当性（grounded/ungrounded と理由）、judge の軸別スコアと総評。
  - grounding/judge が「判定保留」のときは穏やかにその旨を表示。

禁止事項：
- QA4AI結果で本体スコア・合否を書き換えない（あくまで点検）。
- キーを画面・ログに出さない。

完了確認（人が実行・実呼び出し）：
```powershell
$env:OPENAI_API_KEY = "（各自のキー）"
uvicorn app.main:app --reload
# 既存レビューの画面で「QA4AIで点検する」を押す
# → ルール違反（無ければ違反なし）、根拠妥当性、judgeスコアが表示される
```

---

#### Task 5（コア）: テスト（tests/test_rule_check.py, tests/test_qa4ai_llm.py）

目的：
ルール遵守（決定的）と、grounding/judge（モック）を検証する。

対象ファイル：
- `tests/test_rule_check.py`
- `tests/test_qa4ai_llm.py`

変更内容：
- `test_rule_check.py`：
  - 本文に点数がある → 違反検出。
  - 「不合格」を含む → 違反検出。
  - 「でも、〜」で始まる → 違反検出。
  - 健全な所見 → 違反なし（空リスト）。
- `test_qa4ai_llm.py`（`_call_llm` を monkeypatch）：
  - grounding：正常JSON → 各findingに grounded が付く。壊れた応答2回 → 判定保留で落ちない。
  - judge：正常JSON → 軸スコアが検証を通る。壊れた応答 → 判定保留。

禁止事項：
- 実際のOpenAI呼び出し・キーを使わない。

完了確認（人が実行）：
```powershell
pytest tests/test_rule_check.py tests/test_qa4ai_llm.py -q
```

---

#### Task 6（任意・e トレース／可観測性）: app/qa4ai/trace.py

目的：
LLM呼び出しの記録を残し、後から検証できるようにする。

対象ファイル：
- `app/qa4ai/trace.py`
- `app/persona/reviewer.py`（`_call_llm` に記録フックを足す。挙動は変えない）

変更内容：
- 各LLM呼び出しの metadata（タイムスタンプ、用途/フェーズ、モデル名、所要時間、取得できればトークン数）を `traces.jsonl` に追記。
- `_call_llm` の戻り値・例外挙動は変えない（記録だけ足す。失敗しても本処理を止めない）。
- **プロンプト本文や成果物の機微情報・キーは記録しない**（メタ情報のみ）。

禁止事項：
- 記録処理で本処理を遅延・失敗させない（記録は best-effort）。

完了確認（人が実行）：
```powershell
$env:OPENAI_API_KEY = "（各自のキー）"
python -m app.persona.reviewer --phase detailed_design --artifact samples/artifact.md
# traces.jsonl に1行追記され、モデル名・所要時間等が記録される（プロンプト本文は含まれない）
```

---

#### Task 7（任意・a 採点の安定性）: app/qa4ai/stability.py（CLI）

目的：
同じ成果物を複数回採点し、スコアのばらつきを測る（再現性のQA）。

対象ファイル：
- `app/qa4ai/stability.py`

変更内容：
- CLI：`--phase` `--artifact` `--runs N`（既定5）。同一入力で N 回 `run_review`→採点を実行し、total_score（と主要項目スコア）の平均・標準偏差・最小最大を表示。
- 保存（DBへ）はしなくてよい。コスト（N回のLLM呼び出し）が発生する旨をヘルプに明記。

禁止事項：
- 本体のレビュー履歴を汚さない（保存しないか、専用扱いにする）。

完了確認（人が実行）：
```powershell
$env:OPENAI_API_KEY = "（各自のキー）"
python -m app.qa4ai.stability --phase detailed_design --artifact samples/artifact.md --runs 3
# total_score の平均・標準偏差・範囲が表示される
```

---

## P9完了の目安
- コア: ルール違反の機械検出／指摘の根拠妥当性（LLM）／LLM-as-judge が、レビュー画面から実行・表示・保存できる
- QA4AI結果は本体のスコア・合否を書き換えず、独立した点検として残る
- grounding/judge は失敗時に判定保留で落ちない
- 任意: trace.jsonl にメタ記録（本文・キーは残さない）／stability でスコアのばらつきを測れる
