# BlueFeather P6 実装プロンプト（Claude Code 用） v0.1

> 対象: 実装フェーズ計画 v0.1 の P6（履歴エクスポート ＋ 通し動作確認）
> 参照: 詳細設計 v0.2 / これまでの P1〜P5 実装
>
> 命名メモ: 表示名は **BlueFeather**。ただし **実行時識別子は既存のまま据え置き**（環境変数 `BLUEWING_DB_PATH`、モジュールパス `app/engine/...` 等）。中途半端なリネームでDBやimportがズレる事故を避けるため、コード側の識別子は変えない。
>
> 各タスクは独立。1タスクずつ Claude Code に渡す。原則1〜2ファイルに限定する。

## 共通の前提・ルール（全タスク共通）

- 環境は Windows / PowerShell。実装は VSCode拡張の Claude Code。実行は人が手元で行う。
- 各自ローカル型のため、エクスポートは **提出証跡の「持ち寄り」用**。各自が書き出し、まとめ役が集約する想定。
- エクスポートは決定的（DBの保存値をそのまま整形するだけ。再採点・LLM呼び出しはしない）。
- 設計どおりに作る。指定外ファイルは触らない。意図が分かりにくい箇所だけ簡潔な日本語コメント。
- キーをコード・ログ・出力ファイルに含めない。

---

#### Task 1: app/engine/export.py（履歴エクスポート＋CLI）

目的：
フェーズのレビュー履歴を Markdown と JSON で書き出す。

対象ファイル：
- `app/engine/export.py`

変更内容：
- `export_phase(phase_key: str, fmt: str, out_dir: str) -> str`（戻り値は書き出したファイルパス）：
  - DB（repository 経由）から、当該フェーズの全ラウンドのレビューを取得（round_no 昇順）。
  - 各ラウンドに含める情報：提出者・日時、rubric_score / coverage_score / total_score、合否（開門／あと一歩）、合成所見（保存済みの語り部品から）、カバレッジ内訳（技法別 covered/total/rate）、項目別スコア（item・score/max・根拠）、status（ok / manual_check）。
  - `fmt='md'`：人が読める提出証跡として整形（フェーズ名・閾値・各ラウンドを見出しで区切る）。
  - `fmt='json'`：機械集約用に構造化（phase, rounds[] のJSON）。
  - `out_dir` が無ければ作成。ファイル名は `{phase_key}_{fmt}` が分かる形に。
- `export_all(fmt, out_dir)`（任意）：全フェーズをまとめて書き出す。
- CLI（`if __name__ == "__main__"`、argparse）：`--phase`（key または `all`）`--format md|json` `--out`。

禁止事項：
- 再採点・判定のやり直し・LLM呼び出しをしない（保存値の整形のみ）。
- キーや本文中の機微情報を出力しない。

完了確認（人が実行・事前に detailed_design に1回以上提出済みであること）：
```powershell
python -m app.engine.export --phase detailed_design --format md   --out exports/
python -m app.engine.export --phase detailed_design --format json --out exports/
# exports/ にMarkdownとJSONが生成され、ラウンドごとのスコア・所見・カバレッジ内訳が入っている
```

---

#### Task 2: ブラウザからのエクスポート（main.py エンドポイント＋画面リンク）

目的：
メンバーがCLIを使わずブラウザから証跡をダウンロードできるようにする。

対象ファイル：
- `app/main.py`（エクスポート用エンドポイント追加）
- `app/ui/templates/phase.html`（ダウンロードリンク追加）

変更内容：
- `GET /phases/{key}/export?format=md|json`：`export_phase` を呼んでファイルを生成し、`FileResponse` でダウンロードさせる（適切な Content-Disposition）。
- `phase.html` に「証跡をエクスポート（Markdown / JSON）」のリンクを追加（そのフェーズに履歴があるときに表示）。

禁止事項：
- 画面側で集計・再採点をしない（export.py 経由）。

追加ルール：
- 生成ファイルは既存の `exports/`（無ければ作成）に置いてから返す。

完了確認（人が実行）：
```powershell
$env:OPENAI_API_KEY = "（各自のキー）"
uvicorn app.main:app --reload
# detailed_design のフェーズ画面で「エクスポート（Markdown）」を押し、ファイルがダウンロードされること
```

---

#### Task 3: 通し確認用データ ＋ README更新

目的：
「提出 → あと一歩 → 改善して再提出 → エクスポート」を確認できるようにし、持ち寄り手順を残す。

対象ファイル：
- `samples/cases_full.csv`
- `README.md`（更新）

変更内容：
- `samples/cases_full.csv`：全 target をカバーするケース（カバレッジ100想定）。
  ```csv
  test_id,technique,precondition,input,expected,target_ids,note
  T001,境界値分析,,age=17,エラー,BVA-age-01,
  T002,境界値分析,,age=18,OK,BVA-age-02,
  T003,境界値分析,,age=120,OK,BVA-age-03,
  T004,境界値分析,,age=121,エラー,BVA-age-04,
  T005,デシジョンテーブル,,正しいID/PW,ログイン成功,DT-login-01,
  T006,デシジョンテーブル,,誤ったPW,ログイン失敗,DT-login-02,
  T007,状態遷移,下書き,submit,申請中,ST-order-01,
  T008,同値分割,,無料プラン選択,無料機能のみ,EP-plan-01,
  ```
- `README.md` に追記：
  - 通し確認手順（detailed_design に samples/artifact.md ＋ cases.csv を提出＝あと一歩 → cases_full.csv に差し替えて再提出 → エクスポート）。
  - 持ち寄り手順（各自がフェーズごとに `export` → まとめ役がJSONを集約 / Markdownを束ねる）。
  - 注記: 合否（開門）の最終判定はカバレッジに加えLLMのルーブリック採点にも依るため、再提出で必ず開門するとは限らない。カバレッジが100に上がることは決定的に確認できる。

禁止事項：
- 上記2ファイル以外を変更しない。

完了確認（人が実行）：
```powershell
# cases_full でカバレッジが100になることを決定的に確認
python -m app.engine.coverage --targets samples/targets.csv --cases samples/cases_full.csv
# 期待: 全技法 rate 1.00、coverage_score = 100.00
```

---

## P6完了の目安
- フェーズの履歴を Markdown / JSON で書き出せる
- ブラウザからも証跡をダウンロードできる
- cases_full でカバレッジが決定的に 100 になる
- 「提出 → あと一歩 → 再提出 → エクスポート」が一気通貫で確認できる

## この後の調整候補（任意・急ぎではない）
- ルーブリック各項目の採点ガイド（何点でどんな状態か）の言語化 → LLMの採点ぶれ低減。
- 配点・閾値・技法重みの実データを見ながらの調整。技法重みを settings の yaml へ外出し。
- `@app.on_event` を lifespan 方式へ置き換え（警告解消）。
- 表示名・READMEなどの BlueFeather 統一（必要になったら既存ドキュメントもまとめて）。
