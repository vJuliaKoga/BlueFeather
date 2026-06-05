# BlueWing P4 実装プロンプト（Claude Code 用） v0.1

> 対象: 実装フェーズ計画 v0.1 の P4（合算・合否判定・所見合成・ループ／結線）
> 参照: 詳細設計 v0.2 §5・§6 / ペルソナ定義書 v0.2 §5・§6
>
> 各タスクは独立。1タスクずつ Claude Code に渡す。原則1〜2ファイルに限定する。

## 共通の前提・ルール（全タスク共通）

- 環境は Windows / PowerShell。実装は VSCode拡張の Claude Code。実行は人が手元で行う。
- スコア計算・合否判定は **決定的（LLM非依存）**。同じ入力なら必ず同じ結果。
- 役割: LLM（P3）が出した「項目スコア＋語りの文面」と、カバレッジ（P2）の数値を受け取り、**関守エンジンが合算・合否判定**し、所見を合成する。
- 合否は「あと一歩 / 開門」で表現。各自ローカル型なので、ゲートは **その端末内の自己チェック**。
- 設計どおりに作る。指定外ファイルは触らない。意図が分かりにくい箇所だけ簡潔な日本語コメント。

---

#### Task 1: app/engine/scoring.py（合算・純粋関数）

目的：
項目スコアから rubric_score を、rubric_score とカバレッジから total_score を決定的に算出する。

対象ファイル：
- `app/engine/scoring.py`

変更内容：
- `compute_rubric_score(item_scores, rubric_items) -> float`：
  - `item_scores`：item_key → (score, max_score)。`rubric_items`：item_key → weight。
  - `rubric_score = 100 × Σ(weight_i × score_i/max_score_i) / Σ(weight_i)`。
  - item_key の対応が取れないものはエラーにせず無視せず、対応する weight が無い項目は計算対象外（ログ等は不要、コメントで意図を明記）。
- `compute_total_score(rubric_score, coverage_score, rubric_weight, coverage_weight) -> float`：
  - `total_score = rubric_weight × rubric_score + coverage_weight × coverage_score`。
  - `coverage_weight == 0` のとき coverage_score は None でもよく、その項は 0 として扱う。
- いずれも純粋関数（DB・LLM・IOに触れない）。

禁止事項：
- DBアクセス・LLM呼び出しをここに書かない。
- 合否判定（閾値比較）はここに入れない（Task 2）。

完了確認（人が実行）：
```powershell
python -c "from app.engine.scoring import compute_rubric_score, compute_total_score; print('ok')"
```

---

#### Task 2: app/engine/gate.py（合否判定・所見合成）

目的：
閾値比較で合否を決め、BlueWingの語りとスコア行を1本の所見に組む。

対象ファイル：
- `app/engine/gate.py`

変更内容：
- スコア行テンプレート（調整可能な定数として）：
  - 開門: `"{score}点。ここで関門は開きますよ。よくやりましたね。"`
  - あと一歩: `"いま{score}点。合格ラインの{threshold}点まで、あと一歩というところです。"`
- `judge(total_score: float, threshold: float) -> tuple[bool, str]`：
  - `passed = total_score >= threshold`。
  - スコア行の `{score}` は **表示用に整数へ四捨五入**（合否判定そのものは丸めない total_score で行う）。
  - passed に応じて開門／あと一歩のスコア行を返す。
- `compose_review(acknowledgement, score_line, overall_findings, technique_recommendations, closing) -> str`：
  - ペルソナ定義書§5の順で1本の文章に組む：
    1. acknowledgement（承認）
    2. score_line（スコア行）
    3. overall_findings（`・` の箇条書き。2〜3点に絞る。多ければ先頭から絞る）
    4. technique_recommendations（あれば「この観点なら〜」の形で簡潔に）
    5. closing（委ねる結び）
  - 文面に余計な点数を足さない（スコア行以外に点数を書かない）。

禁止事項：
- DB・LLM に触れない（純粋関数）。

完了確認（人が実行）：
```powershell
python -c "from app.engine.gate import judge, compose_review; p,l=judge(72.875,80); print(p, l)"
# 期待: False と「いま73点。合格ラインの80点まで、あと一歩というところです。」
```

---

#### Task 3: app/engine/pipeline.py（結線・永続化・ラウンド管理）＋ repository

目的：
取込→カバレッジ→LLM→合算→判定→合成→保存の一連を結線する。

対象ファイル：
- `app/engine/pipeline.py`
- `app/db/repository.py`（不足する取得・保存関数を追加）

変更内容：
- `repository.py` に最小限の関数を用意（sqlite3、config の db_path）：
  - phase 取得（key → id, name, pass_threshold, rubric_weight, coverage_weight）
  - rubric_items 取得（phase → item_key→weight, max_score）
  - 次の round_no 取得（phase の最大round+1、無ければ1）
  - artifacts / reviews / coverage_metrics の挿入、gate_status の upsert
- `run_phase_review(phase_key, artifact_body, submitted_by, targets_path=None, cases_path=None) -> dict`：
  1. round_no を決め、artifact を保存。
  2. coverage_weight>0 かつ targets/cases があれば `engine.coverage.compute_coverage` を実行（coverage_score と技法別metrics）。無ければ coverage_score=None。
  3. `persona.reviewer.run_review(phase_key, artifact_body, coverage_summary)` を実行。
     - 結果が `manual_check` なら、review を status='manual_check'・スコアなし・raw保存で記録し、合否判定はせず終了（落とさない）。
  4. 成功時: `compute_rubric_score`（LLMのitem_scores × rubric_itemsのweight）→ `compute_total_score` → `judge` → `compose_review`。
  5. reviews（rubric_score, coverage_score, total_score, passed, rubric_breakdown=JSON, findings=JSON, recommendations=JSON, acknowledgement, closing, status='ok'）と coverage_metrics を保存。
  6. gate_status を upsert（current_round 更新、passed なら closed=1・closed_at 記録）。
  7. 合成所見・スコア・合否を返す。

禁止事項：
- スコア計算式・判定ロジックをここに再実装しない（scoring/gate を呼ぶ）。
- キーをコードに書かない。

追加ルール：
- LLM呼び出しは reviewer 経由のみ（pipeline から直接 OpenAI に触れない）。
- 例外で全体を落とさない。LLM失敗は manual_check に集約。

完了確認（人が実行・実呼び出し。P1のdb.init済み前提）：
```powershell
$env:OPENAI_API_KEY = "（各自のキー）"
python -c "from app.engine.pipeline import run_phase_review; r=run_phase_review('detailed_design', open('samples/artifact.md',encoding='utf-8').read(), 'koga', 'samples/targets.csv','samples/cases.csv'); print(r['passed']); print(r['review_text'][:120])"
```

---

#### Task 4: 単体テスト（tests/test_scoring.py, tests/test_gate.py）

目的：
合算・合否・合成の正しさを決定的に検証する（ネットワーク・DB不要）。

対象ファイル：
- `tests/test_scoring.py`
- `tests/test_gate.py`

変更内容：
- `tests/test_scoring.py`：
  - 例の入力で `rubric_score` を検証。
    - rubric_items 重み: boundary_coverage 1.5 / branch_coverage 1.5 / state_transition 1.0 / expected_clarity 1.0（max_score 各4）
    - item_scores: boundary 3 / branch 2 / state 4 / expected 3
    - 期待 `rubric_score == 72.5`（許容誤差付き）
  - `compute_total_score(72.5, 73.75, 0.7, 0.3)` の期待 `== 72.875`。
  - `coverage_weight=0` のとき coverage_score=None でも total_score == rubric_score。
- `tests/test_gate.py`：
  - `judge(72.875, 80)` → passed False、スコア行に「あと一歩」を含む。
  - `judge(92.125, 80)` → passed True、スコア行に「開門」を含む。
  - `compose_review(...)` が、承認→スコア行→指摘→結び の順を保ち、スコア行以外に点数表記を含まない。

禁止事項：
- OpenAI呼び出し・キーを使わない。

完了確認（人が実行）：
```powershell
pytest tests/test_scoring.py tests/test_gate.py -q
```

---

## P4完了の目安
- 項目スコア＋重みから rubric_score（例で72.5）が出る
- rubric_score とカバレッジから total_score（例で72.875）が出る
- 閾値比較で「あと一歩／開門」が切り替わる
- pipeline で 取込→カバレッジ→LLM→合算→判定→合成→保存→gate更新 が一気通貫で動く
- LLM失敗は manual_check に集約され、全体は落ちない

## 計算の内訳（確認用）
- rubric_score 分子 = 1.5×(3/4) + 1.5×(2/4) + 1.0×(4/4) + 1.0×(3/4) = 1.125 + 0.75 + 1.0 + 0.75 = 3.625
- 分母 = 1.5 + 1.5 + 1.0 + 1.0 = 5.0 → rubric_score = 100 × 3.625/5.0 = 72.5
- total_score = 0.7×72.5 + 0.3×73.75 = 50.75 + 22.125 = 72.875（< 80 なので「あと一歩」）
- 合格例: rubric 全4点 → rubric_score 100、total = 0.7×100 + 0.3×73.75 = 92.125（≥ 80 で「開門」）
