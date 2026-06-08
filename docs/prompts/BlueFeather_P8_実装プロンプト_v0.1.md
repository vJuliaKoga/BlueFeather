# BlueFeather P8 実装プロンプト（前回比較・デグレ検出） v0.1

> 目的: 同じフェーズの「前回ラウンド」と「今回ラウンド」を突き合わせ、何が良くなったか・何が下がったか（デグレ）を見える化する。
> デグレの定義: 前回より下がった項目（ルーブリック項目スコア、または技法別カバレッジ率）。
> 参照: P4 pipeline / reviews・coverage_metrics・gate_status / P6 export
>
> 命名メモ: 表示名は BlueFeather。実行時識別子（`BLUEWING_DB_PATH`、`app/...`）は据え置き。

## 設計方針

- 比較の計算は **決定的（関守エンジン）**。前回・今回の保存値を突き合わせるだけ。新たなLLM呼び出しはしない。
- 変化の語りは、judge のスコア行と同じく **テンプレートで BlueFeather 口調** に組む（良くなった点を一緒に喜び、下がった点は責めずに示す）。
- round_no が1（前回が無い）や、いずれかが manual_check（スコア無し）のときは比較をスキップし、画面では「比較対象なし」を穏やかに表示。

## 共通ルール

- 環境は Windows / PowerShell。実装は Claude Code。実行は人。
- 既存の採点・判定・保存は変えない。比較は読み取り中心。
- 指定外ファイルは触らない。意図が分かりにくい箇所だけ簡潔な日本語コメント。

---

#### Task 1: app/engine/compare.py（比較の計算・決定的）

目的：
前回と今回のレビューを突き合わせ、増減とデグレを算出する。

対象ファイル：
- `app/engine/compare.py`
- `app/db/repository.py`（「フェーズの直近2レビュー取得」を追加）

変更内容：
- 純粋関数 `compute_comparison(prev, cur) -> dict`（DB非依存・テスト容易）：
  - 入力 `prev` / `cur` は、項目スコア（item_key→(score, max)）、技法別カバレッジ率（technique→rate）、rubric_score、coverage_score、total_score を含む辞書。
  - 出力：
    - `item_deltas`：item_key ごとに {prev, cur, delta, direction(up/down/same)}
    - `coverage_deltas`：technique ごとに {prev, cur, delta}
    - `score_deltas`：rubric_score / coverage_score / total_score の増減
    - `improved`：上がった項目の一覧
    - `degraded`：下がった項目の一覧（＝デグレ）
    - `summary`：テンプレートで組む BlueFeather 口調の短い総括
  - summary の例：
    - 改善のみ：「前回から、{改善項目}が一歩進みましたね。いい流れです。」
    - デグレあり：「{改善項目}は良くなりました。一方で {デグレ項目} が少し戻ったようです。ここだけ見直してみませんか。」
    - 変化なし：「前回から大きな変化はないようです。」
- `repository` に `get_last_two_reviews(phase_key)`（round_no 降順で2件。2件未満なら不足を示す）を追加。
- DBラッパ `compare_phase(phase_key)`：直近2件を取得し、`compute_comparison` に渡す。2件未満や manual_check 混在のときは「比較不可」を返す。

禁止事項：
- LLM呼び出しをしない。採点ロジックを再実装しない。

完了確認（人が実行）：
```powershell
python -c "from app.engine.compare import compute_comparison; print('ok')"
```

---

#### Task 2: 所見画面に「前回との比較」を表示

目的：
今回の所見の下に、前回からの変化を穏やかに見せる。

対象ファイル：
- `app/ui/templates/review.html`
- `app/main.py`

変更内容：
- `GET /reviews/{id}`：そのレビューのフェーズで `compare_phase` を呼び、比較データ（または「比較対象なし」）をテンプレートへ渡す。
- `review.html`：round_no>1 かつ比較可能なときだけ「前回との比較」セクションを表示：
  - 総括（summary）
  - 改善項目（緑/青系・status-open相当）
  - デグレ項目（煽らない琥珀系・status-near相当）と前回→今回の値
  - total_score / coverage_score の増減
  - 比較不可のときは「前回がまだ無いため比較はありません」等を穏やかに表示。

禁止事項：
- 画面で比較計算を再実装しない（compare 経由）。

完了確認：
- Task 4 まで入れて起動確認。

---

#### Task 3: エクスポートに比較を含める

目的：
持ち寄り証跡にも「前回からの変化」を残す。

対象ファイル：
- `app/engine/export.py`

変更内容：
- 各ラウンドの出力に、前回との比較（improved / degraded / score_deltas / summary）を追記する（round_no>1 かつ比較可能なとき）。
- Markdown・JSON 両方に反映。

禁止事項：
- 再採点・再計算でズレを生まない（保存値ベース）。

完了確認（人が実行）：
```powershell
python -m app.engine.export --phase detailed_design --format md --out exports/
# 2ラウンド以上ある場合、Markdownに「前回との比較」が含まれる
```

---

#### Task 4: 単体テスト（tests/test_compare.py）

目的：
比較とデグレ判定の正しさを決定的に検証する。

対象ファイル：
- `tests/test_compare.py`

変更内容：
- 構成した入力で `compute_comparison` を検証：
  - prev 項目スコア: boundary 3 / branch 3 / state 4 / expected 3
  - cur  項目スコア: boundary 4 / branch 2 / state 4 / expected 3
  - 期待：improved に boundary（3→4）、degraded に branch（3→2）、state/expected は same。
  - total_score の増減も期待どおり符号が出ること。
- カバレッジ率の増減（例: 境界値 0.75→1.00 は improved、0.50→0.25 は degraded）も検証。
- 2件未満・manual_check 混在で「比較不可」になることを検証。

禁止事項：
- ネットワーク・LLMを使わない。

完了確認（人が実行）：
```powershell
pytest tests/test_compare.py -q
```

---

## P8完了の目安
- 直近2ラウンドから、項目・カバレッジ・スコアの増減が決定的に出る
- デグレ（下がった項目）が一覧で見える
- 所見画面に「前回との比較」が穏やかに表示される（改善は喜び、デグレは責めない）
- エクスポートにも比較が含まれる
- round1 や manual_check では比較をスキップして落ちない
