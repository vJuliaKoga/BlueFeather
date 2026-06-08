# BlueFeather P2 実装プロンプト（Claude Code 用） v0.1

> 対象: 実装フェーズ計画 v0.1 の P2（CSV/Excel取込 ＋ 定量カバレッジ計算・関守エンジン）
> 参照: 詳細設計 v0.2 §2（入力フォーマット）・§3（カバレッジ計算）
>
> 各タスクは独立。1タスクずつ Claude Code に渡す。原則1〜2ファイルに限定する。

## 共通の前提・ルール（全タスク共通）

- 環境は Windows / PowerShell。実装は VSCode拡張の Claude Code。実行は人が手元で行う。
- この層は **決定的（LLM非依存）**。同じ入力なら必ず同じ結果になること。
- 依存は P1 の requirements.txt の範囲（csv は標準ライブラリ、xlsx は openpyxl）。**pandas は使わない。**
- 設計（詳細設計 v0.2）に沿う。設計にない仕様追加・挙動変更はしない。
- 指定外ファイルは作成・変更しない。曖昧なときは範囲を保守的に絞る。
- 変更箇所には、意図が分かりにくいところだけ日本語の簡潔なコメントを付ける。冗長にしない。

---

#### Task 1: サンプルデータ（samples/targets.csv, samples/cases.csv）

目的：
取込・カバレッジの検証に使うサンプルを用意する。一部の対象をあえて未カバーにする。

対象ファイル：
- `samples/targets.csv`
- `samples/cases.csv`

変更内容：
- `samples/targets.csv` を次の内容で作成する：
  ```csv
  target_id,technique,category,target,must_cover,note
  BVA-age-01,境界値分析,age,age=min-1,Y,
  BVA-age-02,境界値分析,age,age=min,Y,
  BVA-age-03,境界値分析,age,age=max,Y,
  BVA-age-04,境界値分析,age,age=max+1,Y,
  DT-login-01,デシジョンテーブル,login,ルールR01,Y,
  DT-login-02,デシジョンテーブル,login,ルールR02,Y,
  ST-order-01,状態遷移,order,S1->S2(submit),Y,
  EP-plan-01,同値分割,plan,無料プラン,Y,
  ```
- `samples/cases.csv` を次の内容で作成する（BVA-age-04 と DT-login-02 はあえて未カバー）：
  ```csv
  test_id,technique,precondition,input,expected,target_ids,note
  T001,境界値分析,,age=17,エラー,BVA-age-01,
  T002,境界値分析,,age=18,OK,BVA-age-02,
  T003,境界値分析,,age=120,OK,BVA-age-03,
  T004,デシジョンテーブル,,正しいID/PW,ログイン成功,DT-login-01,
  T005,状態遷移,下書き,submit,申請中,ST-order-01,
  T006,同値分割,,無料プラン選択,無料機能のみ,EP-plan-01,
  ```

禁止事項：
- 上記2ファイル以外を作成・変更しない。

追加ルール：
- 文字コードは UTF-8。

---

#### Task 2: app/ingest/testcase_loader.py（取込・検証）

目的：
targets/cases を読み込み、構造化して返す。検証エラーはまとめて投げる。

対象ファイル：
- `app/ingest/testcase_loader.py`

変更内容：
- データ構造（dataclass）を定義する：
  ```python
  @dataclass
  class Target:
      target_id: str
      technique: str
      category: str
      target: str
      must_cover: bool = True
      note: str = ""

  @dataclass
  class Case:
      test_id: str
      technique: str
      precondition: str
      input: str
      expected: str
      target_ids: list[str]
      note: str = ""
  ```
- 読込関数を実装する：
  - `load_from_csv(targets_csv: str, cases_csv: str) -> tuple[list[Target], list[Case]]`（標準ライブラリ csv）
  - `load_from_xlsx(xlsx_path: str) -> tuple[list[Target], list[Case]]`（openpyxl。シート名 `targets` と `cases`）
  - どちらも内部で同じ検証を通す。
- パース仕様：
  - `must_cover`：`N` のときのみ False。空欄や `Y` は True。
  - `target_ids`：カンマ区切りを分割し、前後空白を除去、空要素は捨てる。
- 検証（エラーはすべて収集し、`TestcaseValidationError(messages: list[str])` でまとめて送出）：
  - 必須列の不足（targets: target_id, technique, category, target / cases: test_id, technique, input, expected, target_ids）。
  - `targets.target_id` の重複。
  - `cases.target_ids` が targets に存在しない ID を参照している（未定義参照。どの test_id がどの ID を指しているか明示）。
  - `technique` が許可集合（境界値分析 / デシジョンテーブル / 状態遷移 / 同値分割）以外（targets・cases 両方）。
- `TestcaseValidationError` も同ファイルに定義してよい（`messages` 属性を持つ Exception）。

禁止事項：
- カバレッジ計算・スコアはここに書かない（Task 3）。
- pandas を使わない。

追加ルール：
- エラーメッセージは人が直せる粒度（列名・ID・test_id を含める）。

完了確認（人が実行）：
```powershell
python -c "from app.ingest.testcase_loader import load_from_csv; t,c=load_from_csv('samples/targets.csv','samples/cases.csv'); print('targets=',len(t),'cases=',len(c))"
# 期待: targets= 8 cases= 6
```

---

#### Task 3: app/engine/coverage.py（定量カバレッジ計算・関守エンジン）

目的：
技法別の網羅率と coverage_score を決定的に算出する。

対象ファイル：
- `app/engine/coverage.py`

変更内容：
- 技法重み（ドラフト・調整可能。将来 settings への外出しを検討）：
  ```python
  TECHNIQUE_WEIGHTS = {
      "境界値分析": 0.35,
      "デシジョンテーブル": 0.35,
      "状態遷移": 0.20,
      "同値分割": 0.10,
  }
  ```
- `compute_coverage(targets, cases)` を実装する：
  - 対象は `must_cover=True` の target のみ。
  - ある target は、いずれかの case の `target_ids` に含まれていれば「カバー済み」。
  - 技法ごとに `total`（must_cover の target 数）、`covered`（うちカバー済み数）、`rate = covered/total`。`total==0` の技法は計算から除外。
  - `coverage_score = 100 × Σ(weight_t × rate_t) / Σ(weight_t)`（total>0 の技法のみで加重）。
  - 技法別の内訳（technique, total, covered, rate, weight）と coverage_score を持つ結果オブジェクト（dataclass など）を返す。
- CLI（`if __name__ == "__main__"`、argparse）：`--targets` `--cases`（CSV）を受け、内訳と coverage_score を表示する。loader を内部で使う。

禁止事項：
- LLM・OpenAI に一切触れない。
- 合否判定・総合点（total_score）はここで出さない（P4）。

追加ルール：
- 浮動小数の表示は小数2桁程度に整える（内部計算は丸めない）。

完了確認（人が実行）：
```powershell
python -m app.engine.coverage --targets samples/targets.csv --cases samples/cases.csv
# 期待される内訳:
#   境界値分析: covered 3 / total 4  rate 0.75
#   デシジョンテーブル: covered 1 / total 2  rate 0.50
#   状態遷移: covered 1 / total 1  rate 1.00
#   同値分割: covered 1 / total 1  rate 1.00
# 期待 coverage_score = 73.75
```

---

#### Task 4: 単体テスト（tests/test_loader.py, tests/test_coverage.py）

目的：
取込・検証・カバレッジ計算の正しさと決定性を担保する。

対象ファイル：
- `tests/test_loader.py`
- `tests/test_coverage.py`

変更内容：
- `tests/test_loader.py`：
  - samples の正常読込（targets=8, cases=6）。
  - 未定義参照（存在しない target_id を指す case）で `TestcaseValidationError`。
  - target_id 重複で `TestcaseValidationError`。
  - 必須列不足で `TestcaseValidationError`。
  - 許可外 technique で `TestcaseValidationError`。
  - （異常系は一時ファイル/文字列で小さな入力を作って検証する）
- `tests/test_coverage.py`：
  - samples から計算し、技法別 rate と `coverage_score == 73.75`（許容誤差付き）を検証。
  - `total==0` の技法が計算から除外されることを検証。
  - 同じ入力で2回計算して結果が一致（決定性）を検証。

禁止事項：
- ネットワーク・OpenAI 呼び出しを含めない。

追加ルール：
- テストは samples かテスト内で作る小さな入力のみを使う。

完了確認（人が実行）：
```powershell
pytest tests/test_loader.py tests/test_coverage.py -q
```

---

## P2完了の目安
- samples が targets=8 / cases=6 で読める
- 未定義参照・重複・列不足・許可外technique が検証で弾ける
- samples の coverage_score が 73.75 になる
- 同じ入力なら必ず同じ結果（決定性）

## 計算の内訳（確認用）
- 境界値分析: 3/4 = 0.75 ／ デシジョンテーブル: 1/2 = 0.50 ／ 状態遷移: 1/1 = 1.00 ／ 同値分割: 1/1 = 1.00
- 分子 = 0.35×0.75 + 0.35×0.50 + 0.20×1.00 + 0.10×1.00 = 0.2625 + 0.175 + 0.20 + 0.10 = 0.7375
- 分母 = 0.35 + 0.35 + 0.20 + 0.10 = 1.00
- coverage_score = 100 × 0.7375 / 1.00 = 73.75
