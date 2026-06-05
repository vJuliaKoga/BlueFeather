# BlueWing P3 実装プロンプト（Claude Code 用） v0.1

> 対象: 実装フェーズ計画 v0.1 の P3（BlueWing語り層・LLM呼び出し・スキーマ検証・フォールバック）
> 参照: 詳細設計 v0.2 §6 / ペルソナ定義書 v0.2 / prompts.py（作成済み）
>
> 各タスクは独立。1タスクずつ Claude Code に渡す。原則1〜2ファイルに限定する。

## 共通の前提・ルール（全タスク共通）

- 環境は Windows / PowerShell。実装は VSCode拡張の Claude Code。実行は人が手元で行う。
- **`prompts.py` は作成済み。`app/persona/prompts.py` に配置しておくこと**（中身は変更しない）。
- この層が出すのは「各ルーブリック項目の定性スコア（0〜max）」と「語りの文面」まで。**総合点・カバレッジ点・合否判定・具体的な点数は出さない**（それらは P4 の関守エンジン）。
- OpenAI APIキーは環境変数 `OPENAI_API_KEY` から（config 経由）。**コード・テスト・ログにキーを書かない。**
- テストはモックのみ（ネットワーク・キー不要）。実呼び出しの確認だけ各自のキーで行う。
- OpenAI SDK は v1 系（`from openai import OpenAI`）。モデル名は `config` の `OPENAI_MODEL`。
- 設計どおりに作る。指定外ファイルは触らない。意図が分かりにくい箇所だけ簡潔な日本語コメント。

---

#### Task 1: app/persona/schema.py（出力JSONのpydanticモデル）

目的：
LLM出力JSONの型を定義し、検証できるようにする。

対象ファイル：
- `app/persona/schema.py`

変更内容：
- 詳細設計§6.3 に対応する pydantic モデルを定義する：
  ```python
  class RubricScore(BaseModel):
      item_key: str
      score: int
      max_score: int
      rationale: str
      findings: list[str] = []

  class TechniqueRecommendation(BaseModel):
      target: str
      recommended_technique: str
      reason: str

  class ReviewLLMOutput(BaseModel):
      rubric_scores: list[RubricScore]
      technique_recommendations: list[TechniqueRecommendation] = []
      acknowledgement: str
      closing: str
      overall_findings: list[str] = []
  ```
- `RubricScore` に検証を入れる：`score` は 0 以上 `max_score` 以下。範囲外は検証エラー。

禁止事項：
- スコア計算・合否判定をここに書かない。

追加ルール：
- 余計なフィールドは追加しない（設計どおり）。

完了確認（人が実行）：
```powershell
python -c "from app.persona.schema import ReviewLLMOutput; print('ok')"
```

---

#### Task 2: app/persona/reviewer.py（呼び出し・抽出・検証・フォールバック）＋ サンプル成果物

目的：
prompts.py のメッセージで LLM を呼び、JSONを抽出・検証する。失敗時は安全に逃がす。

対象ファイル：
- `app/persona/reviewer.py`
- `samples/artifact.md`

変更内容（テスト容易性のため、関数を分離して実装する）：
- `_call_llm(messages: list[dict]) -> str`：OpenAI を呼び、本文テキストを返す薄いラッパ。テストで差し替えられるよう、この関数1つに呼び出しを閉じ込める。モデルは config から。可能なら JSON を要求する `response_format` を使ってよいが、依存はしない。
- `parse_llm_json(text: str) -> ReviewLLMOutput`：先頭末尾のコードフェンス（```や```json）を除去 → `json.loads` → `ReviewLLMOutput` で検証。失敗時は例外。
- `ReviewResult`（dataclass）：`status`（'ok' | 'manual_check'）、`parsed`（ReviewLLMOutput | None）、`raw_output`（str）。
- `review_messages(messages: list[dict]) -> ReviewResult`：
  - `_call_llm` → `parse_llm_json` を試す。成功なら status='ok'。
  - 失敗したら、**1回だけ**「JSONのみで再出力してください。前後の説明やコードフェンスは付けないでください。」を追記して再試行。
  - それでも失敗なら status='manual_check'、parsed=None、raw_output に最後の生テキストを保存。**例外で落とさない。**
- `run_review(phase_key: str, artifact_body: str, coverage_summary: str | None = None) -> ReviewResult`：
  - DB（config の db_path）から phase 名と当該フェーズの rubric_items（item_key, description, max_score）を取得（最小クエリでよい）。
  - `prompts.build_messages(...)` でメッセージ生成 → `review_messages(...)` に委譲。
- CLI（`if __name__ == "__main__"`、argparse）：`--phase` `--artifact`（mdファイルパス）`--coverage`(任意)。artifact を読み、`run_review` を実行し、status と acknowledgement の冒頭を表示。
- `samples/artifact.md`：詳細設計フェーズ想定の短いサンプル成果物（日本語で数行。年齢入力の境界値やログインの分岐に軽く触れる程度でよい）。

禁止事項：
- 合否判定・total_score・coverage_score をここで出さない。
- キーをコードに書かない。pandas不要。

追加ルール：
- `_call_llm` 以外からは OpenAI に触れない（モック1点で差し替えられるように）。

完了確認（人が実行・実呼び出し。事前に P1 の `python -m app.db.init` 済みであること）：
```powershell
$env:OPENAI_API_KEY = "（各自のキー）"
python -m app.persona.reviewer --phase detailed_design --artifact samples/artifact.md
# 期待: status=ok と、BlueWing 口調の acknowledgement の冒頭が表示される
```

---

#### Task 3: 単体テスト（tests/test_schema.py, tests/test_fallback.py）

目的：
スキーマ検証とフォールバック制御を、モックで確実に検証する。

対象ファイル：
- `tests/test_schema.py`
- `tests/test_fallback.py`

変更内容：
- `tests/test_schema.py`：
  - 正常な dict が `ReviewLLMOutput` で通る。
  - `score > max_score` で検証エラー。
  - 必須フィールド欠落で検証エラー。
  - `technique_recommendations` 省略時に空配列になる。
- `tests/test_fallback.py`（`_call_llm` を monkeypatch して `review_messages` を検証。DB・ネットワーク不要）：
  - 正常JSONを返す → status='ok'。
  - ```json ...``` フェンス付きJSON → 抽出して status='ok'。
  - 壊れた応答を2回返す → status='manual_check'、raw_output に生テキストが残る、例外で落ちない。
  - 1回目壊れ・2回目正常 → 再試行で status='ok'。

禁止事項：
- 実際の OpenAI 呼び出し・キーを使わない。

追加ルール：
- メッセージはダミーで良い（`review_messages` は messages を受けるだけ）。

完了確認（人が実行）：
```powershell
pytest tests/test_schema.py tests/test_fallback.py -q
```

---

## P3完了の目安
- `ReviewLLMOutput` で出力JSONを検証でき、score範囲外を弾ける
- フェンス付きJSONも抽出できる
- 壊れた応答は1回再試行 → なお失敗で manual_check（落ちない）
- 実キーでの1回の実呼び出しで status=ok の所見が返る（語り口・点数や合否は文面に出ない）

## メモ
- この時点では所見の「合成」（スコア行の差し込み・テンプレート組み立て）はまだ。P4 で関守エンジンの合算・合否判定とつなぐ。
