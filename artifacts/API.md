# Warikan デモ API 仕様書

`server.py`（Python 標準ライブラリのみ）が提供する API の仕様です。
**境界値・状態遷移・異常系のテスト設計**に使えるよう、全ステータスコードと
エラー内容、入力検証ルールを網羅しています。実装と一致するように記述しています。

- ベース URL: `http://localhost:8000`（`PORT` 環境変数で変更可）
- リクエスト本文: JSON（`Content-Type: application/json`）
- レスポンス本文: JSON（`charset=utf-8`）
- すべてのレスポンスに `Cache-Control: no-store` が付与されます

---

## 0. はじめに — API の呼び出し方（はじめての方向け）

この API は `http://localhost:8000` への **HTTP リクエスト**です。
「**どのパスに**・**どのメソッド(GET/POST)で**・**どんな本文(JSON)で**」送ると、結果が JSON で返ります。
まず `python server.py` でサーバを起動しておいてください。

### 呼び出し方は3通り

**(A) ブラウザ** … GET の API は URL を開くだけ。例: <http://localhost:8000/api/health> を開くと `{"ok": true}` が表示されます。

**(B) curl（コマンド）** … POST やヘッダ付きはこれが手軽です。

```bash
curl -s -X POST http://localhost:8000/api/login \
  -H "Content-Type: application/json" \
  -d '{"userId":"testuser","password":"password"}'
```

| フラグ | 意味 |
| --- | --- |
| `-X POST` | メソッドを指定（省略時は GET） |
| `-H "..."` | ヘッダ追加（`Content-Type` や `Authorization`） |
| `-d '...'` | リクエスト本文（JSON 文字列） |
| `-s` | 進捗表示を消す（静かに実行） |
| `-i` | レスポンスのヘッダも表示 |
| `-w "%{http_code}"` | ステータスコードを出力（後述） |

**(C) PowerShell（Windows）** … `Invoke-RestMethod` が便利。JSON は `ConvertTo-Json` で作ると安全です。

```powershell
$body = @{ userId = "testuser"; password = "password" } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://localhost:8000/api/login `
  -ContentType "application/json" -Body $body
```

> 💡 Windows の `curl` は `-d` 内の**日本語が文字化けする**ことがあります。日本語（備考など）を
> 送るときは PowerShell の `Invoke-RestMethod`（UTF-8 で正しく送れる）か、`--data-binary "@ファイル.json"`
> を使ってください。

### ステータスコードの読み方

レスポンスの「番号」で結果の種類が分かります。

| コード | 意味 | このアプリでの例 |
| --- | --- | --- |
| `200` | 成功 | 正常に処理された |
| `400` | リクエストが不正 | 入力が範囲外・形式違反 |
| `401` | 認証エラー | token が無効、または ID/パスワード誤り |
| `404` | 存在しない | 未定義のパス |
| `409` | 競合 | ユーザ ID が重複 |

curl でコードを見るには `-w` を使います（本文の後ろに改行＋コードを出力）:

```bash
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8000/api/health
# -> 200
```

### token（ログインの鍵）の使い方

認証が必要な API（`/api/qrcode`, `/api/results`）は、先に **ログインして token を取得**し、
`Authorization: Bearer <token>` を付けて呼びます。

```bash
# 1) ログインして token を変数に入れる
TOKEN=$(curl -s -X POST http://localhost:8000/api/login \
  -H "Content-Type: application/json" \
  -d '{"userId":"testuser","password":"password"}' \
  | python -c "import sys,json;print(json.load(sys.stdin)['token'])")

# 2) token を付けて呼ぶ
curl -s http://localhost:8000/api/results -H "Authorization: Bearer $TOKEN"
```

```powershell
# PowerShell の場合
$login = Invoke-RestMethod -Method Post -Uri http://localhost:8000/api/login `
  -ContentType "application/json" `
  -Body (@{ userId = "testuser"; password = "password" } | ConvertTo-Json)
$auth = @{ Authorization = "Bearer $($login.token)" }
Invoke-RestMethod -Uri http://localhost:8000/api/results -Headers $auth
```

> 💡 PowerShell の `Invoke-RestMethod` は `400`/`401` などで**例外を投げます**。エラー時の本文も
> 見たいときは PowerShell 7+ の `-SkipHttpErrorCheck` を付けるか、`try { ... } catch { $_ }` で受けてください。

---

## 1. 共通仕様

### 1.1 認証

- ログイン成功で **token** を発行します。以降、認証が必要な API には
  `Authorization: Bearer <token>` ヘッダを付けます。
- token はサーバのメモリ上にのみ保持され、**サーバ再起動で失効**します。
- 認証が必要な API に有効な token が無い場合、`401 {"error": "unauthorized"}` を返します。

| API | 認証 |
| --- | ---- |
| `/api/login`, `/api/register`, `/api/account/change`, `/api/account/delete` | 不要 |
| `/api/validate`, `/api/calc`, `/api/health` | 不要 |
| `/api/qrcode`, `/api/results`(POST/GET) | **必要** |

> 補足: `account/change` と `account/delete` は token ではなく、本文の userId / password で本人確認します。

### 1.2 エラーレスポンス形式

エラーは原則 `{"error": "メッセージ"}` の形です。`/api/calc` のみ追加情報を含みます。

### 1.3 共通の異常系

| 条件 | ステータス | 本文 |
| --- | --- | --- |
| 未定義の API パス | `404` | `{"error": "not found"}` |
| 本文が不正な JSON / 非 UTF-8 | （空オブジェクト `{}` として処理）| 各 API の検証に従う |

> 本文が壊れていてもサーバは落ちず、空の本文として各 API の検証ロジックにかけられます。
> 例: `/api/login` に壊れた本文 → 認証失敗 `401`、`/api/register` に空本文 → 形式エラー `400`。

---

## 2. 入力検証ルール（境界値の基準）

数値項目の有効範囲です。`/api/validate` と `/api/calc` で共通に使われます。

| 項目 | 最小 | 最大 | 備考 |
| --- | --- | --- | --- |
| `myCount`（自分側の人数） | 1 | 99 | 整数 |
| `otherCount`（相手側の人数） | 1 | 99 | 整数 |
| `total`（合計金額） | 1 | 999999 | 整数 |
| `myRatio`（自分側の支払割合） | 0 | 100 | 整数。`/api/calc` のみ検証 |

### 2.1 「入力あり（filled）」と判定される値

数値は文字列・数値どちらでも受け付けます。次のルールで整数として解釈します。

| 入力例 | filled | 解釈 | 備考 |
| --- | --- | --- | --- |
| `"5"`, `5` | ✓ | 5 | |
| `"05"` | ✓ | 5 | 先頭ゼロ可 |
| `" 5 "` | ✓ | 5 | 前後の空白は除去 |
| `5.0` | ✓ | 5 | 整数値の小数は可 |
| `""` | ✗ | - | 未入力扱い |
| `"5.5"`, `5.5` | ✗ | - | 小数は不可 |
| `"-5"` | ✗ | - | 符号付きは不可 |
| `"abc"`, `null`, `true` | ✗ | - | 数値でない |

- **filled** = 上記ルールで整数として解釈できる
- **valid** = filled かつ有効範囲内（境界値テストの対象）

### 2.2 境界値テストの早見表

| 項目 | invalid | valid | valid | invalid |
| --- | --- | --- | --- | --- |
| 人数（myCount / otherCount） | `0` | `1` | `99` | `100` |
| 金額（total） | `0` | `1` | `999999` | `1000000` |
| 割合（myRatio, calc のみ） | `-1`(=不可) | `0` | `100` | `101` |

---

## 3. エンドポイント詳細

### 3.1 `POST /api/login` — 認証

**認証**: 不要

リクエスト:
```json
{ "userId": "testuser", "password": "password" }
```

| 条件 | ステータス | 本文 |
| --- | --- | --- |
| ID/パスワードが正しい | `200` | `{"token": "<16進32文字>"}` |
| ID/パスワードが誤り（未登録含む） | `401` | `{"error": "認証に失敗しました"}` |

デモ用アカウント: `testuser` / `password`、`warikan` / `warikan123`
（新規登録したアカウントでもログイン可）

```bash
curl -s -X POST http://localhost:8000/api/login \
  -H "Content-Type: application/json" \
  -d '{"userId":"testuser","password":"password"}'
```

---

### 3.2 `POST /api/register` — 新規登録

**認証**: 不要

リクエスト:
```json
{ "userId": "alice", "password": "abc123" }
```

検証順とレスポンス:

| 条件（上から順に評価） | ステータス | 本文 |
| --- | --- | --- |
| `userId` が半角英数 1〜15 文字でない、または `password` が半角英数 1〜20 文字でない | `400` | `{"error": "ユーザIDは15文字以内、パスワードは20文字以内の半角英数字で入力してください"}` |
| すでに存在する `userId`（シード/登録済み問わず） | `409` | `{"error": "このユーザIDは既に使われています"}` |
| 成功 | `200` | `{"ok": true}` |

- 形式ルール: `userId` = `^[0-9A-Za-z]{1,15}$`、`password` = `^[0-9A-Za-z]{1,20}$`
- パスワードは PBKDF2(SHA-256) でハッシュ化して `data/accounts.json` に保存（平文保存なし）

**境界値テスト例**: userId 0文字(空)→400 / 1文字→OK / 15文字→OK / 16文字→400。記号・全角→400。

---

### 3.3 `POST /api/account/change` — パスワード変更

**認証**: 不要（本文で本人確認）

リクエスト:
```json
{ "userId": "alice", "password": "abc123", "newPassword": "new999" }
```

| 条件（上から順に評価） | ステータス | 本文 |
| --- | --- | --- |
| `userId` がデモ用アカウント（testuser/warikan） | `400` | `{"error": "デモ用アカウントは変更できません"}` |
| `userId`/`password` が一致しない | `401` | `{"error": "ユーザIDまたはパスワードが違います"}` |
| `newPassword` が半角英数 1〜20 文字でない | `400` | `{"error": "新しいパスワードは20文字以内の半角英数字で入力してください"}` |
| 成功 | `200` | `{"ok": true}` |

---

### 3.4 `POST /api/account/delete` — 退会（削除）

**認証**: 不要（本文で本人確認）

リクエスト:
```json
{ "userId": "alice", "password": "new999" }
```

| 条件（上から順に評価） | ステータス | 本文 |
| --- | --- | --- |
| `userId` がデモ用アカウント | `400` | `{"error": "デモ用アカウントは削除できません"}` |
| `userId`/`password` が一致しない | `401` | `{"error": "ユーザIDまたはパスワードが違います"}` |
| 成功 | `200` | `{"ok": true}` |

- 退会すると、そのアカウントの割り勘結果（`data/results.json` 内）も削除されます。

---

### 3.5 `POST /api/validate` — 入力検証

**認証**: 不要

数値入力の状態と計算可否を返します。UI のボタン有効/無効判定にも使用。
`myRatio` はこの API では**検証しません**（人数・金額のみ）。

リクエスト:
```json
{ "myCount": "5", "otherCount": "", "total": "50000" }
```

レスポンス（常に `200`）:
```json
{
  "fields": {
    "myCount":    { "filled": true,  "valid": true },
    "otherCount": { "filled": false, "valid": false },
    "total":      { "filled": true,  "valid": true }
  },
  "allFilled": false,
  "canCalculate": false
}
```

| フィールド | 意味 |
| --- | --- |
| `fields.<項目>.filled` | 入力ありか（2.1 参照） |
| `fields.<項目>.valid` | 有効範囲内か（2 参照） |
| `allFilled` | 3 項目すべて filled |
| `canCalculate` | 3 項目すべて valid（計算可能な状態か） |

```bash
curl -s -X POST http://localhost:8000/api/validate \
  -H "Content-Type: application/json" \
  -d '{"myCount":"100","otherCount":"5","total":"50000"}'
# -> myCount.valid:false, canCalculate:false
```

---

### 3.6 `POST /api/calc` — 割り勘計算

**認証**: 不要

リクエスト:
```json
{ "myCount": "5", "otherCount": "5", "total": "50000", "myRatio": "50" }
```

| 条件 | ステータス | 本文 |
| --- | --- | --- |
| 人数・金額が範囲内（`canCalculate`）かつ `myRatio` が 0〜100 | `200` | 計算結果（下記） |
| いずれかが範囲外・未入力 | `400` | `{"error": "入力された数字が不正です", "fields": {...}, "ratioValid": <bool>}` |

成功時レスポンス:
```json
{ "myPerPerson": 5000, "otherPerPerson": 5000, "change": 0, "showJasPay": true }
```

| フィールド | 意味 |
| --- | --- |
| `myPerPerson` | 自分側 1 人あたりの支払金額 |
| `otherPerPerson` | 相手側 1 人あたりの支払金額 |
| `change` | お釣り |
| `showJasPay` | ジャスPay ボタン表示要否（`otherPerPerson > 0`） |

#### 計算アルゴリズム（仕様書 1.3）

```
ceil100(x) = ceil(x / 100 - 1e-9) * 100          # 100円単位で切り上げ

myPerPerson    = ceil100(total * (myRatio / 100) / myCount)
otherPerPerson = ceil100((total - myPerPerson * myCount) / otherCount)
change         = myPerPerson*myCount + otherPerPerson*otherCount - total
showJasPay     = otherPerPerson > 0
```

#### 計算テストベクタ（期待値）

| myCount | otherCount | total | myRatio | myPerPerson | otherPerPerson | change | showJasPay |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 5 | 5 | 50000 | 50 | 5000 | 5000 | 0 | true |
| 3 | 2 | 10000 | 70 | 2400 | 1400 | 0 | true |
| 3 | 3 | 1000 | 50 | 200 | 200 | 200 | true |
| 2 | 2 | 10000 | 100 | 5000 | 0 | 0 | false |

```bash
curl -s -X POST http://localhost:8000/api/calc \
  -H "Content-Type: application/json" \
  -d '{"myCount":"0","otherCount":"5","total":"50000","myRatio":"50"}'
# -> 400, fields.myCount.valid:false
```

---

### 3.7 `POST /api/qrcode` — ジャスPay QR データ取得

**認証**: 必要（`Authorization: Bearer <token>`）

リクエスト:
```json
{ "amount": 5000, "total": 50000 }
```

| 条件 | ステータス | 本文 |
| --- | --- | --- |
| 認証なし/無効 | `401` | `{"error": "unauthorized"}` |
| 成功 | `200` | `{"content": "jaspay://transfer?to=<userId>&amount=<amount>&ref=<乱数>"}` |

> 返却される `content` は QR 化する文字列です。QR 画像の生成はフロント側、送金は
> ジャスPay 側の責務（システムテスト対象外。補足書 3.）。

---

### 3.8 `POST /api/results` — 割り勘結果の登録

**認証**: 必要

リクエスト（登録する結果データ。サーバは内容を検証せず保存します）:
```json
{
  "date": "2026-05-25", "time": "18:00",
  "myCount": 5, "otherCount": 5, "total": 50000, "myRatio": 50,
  "myPerPerson": 5000, "otherPerPerson": 5000, "change": 0, "note": "備考"
}
```

| 条件 | ステータス | 本文 |
| --- | --- | --- |
| 認証なし/無効 | `401` | `{"error": "unauthorized"}` |
| 成功 | `200` | `{"ok": true}` |

- **1 アカウント 50 件まで**保存。51 件目以降は登録順で**古いものから削除**されます。

---

### 3.9 `GET /api/results` — 割り勘結果の取得

**認証**: 必要

| 条件 | ステータス | 本文 |
| --- | --- | --- |
| 認証なし/無効 | `401` | `{"error": "unauthorized"}` |
| 成功 | `200` | 結果の配列（**登録順＝古い→新しい**） |

> 画面では新しい登録を上に表示しますが、API は登録順（古い→新しい）で返します。

```bash
TOKEN=$(curl -s -X POST http://localhost:8000/api/login \
  -H "Content-Type: application/json" \
  -d '{"userId":"testuser","password":"password"}' \
  | python -c "import sys,json;print(json.load(sys.stdin)['token'])")
curl -s http://localhost:8000/api/results -H "Authorization: Bearer $TOKEN"
```

---

### 3.10 `GET /api/health` — 死活確認

**認証**: 不要

| 条件 | ステータス | 本文 |
| --- | --- | --- |
| 常に | `200` | `{"ok": true}` |

フロントは起動時にこの API でバックエンド接続を確認します。

---

## 4. テスト観点のヒント

- **境界値**: 2.2 の早見表を基準に、各数値項目で min-1 / min / max / max+1 を確認。
- **入力形式**: 空文字・小数・符号付き・先頭ゼロ・前後空白・全角数字・非数値（2.1）。
- **状態遷移**: `validate` の `allFilled` / `canCalculate` が入力に応じて変化するか。
  未ログイン→ログイン→（計算）→登録→取得 の各遷移。
- **認証**: 認証必須 API を token 無し/無効 token/失効 token（サーバ再起動後）で叩く。
- **エラー優先順位**: `account/change` の「デモ用→認証→新パスワード形式」の順序。
- **異常系**: 未定義パス(404)、壊れた JSON 本文、巨大な値、超過登録（50 件超で古いものが消えるか）。
- **計算**: 3.6 のテストベクタ、切り上げでお釣りが出るケース、割合 0/100 の端、
  極端な割合での `otherPerPerson` のマイナス（仕様どおりの挙動）。

---

## 5. コピペで試せる実例集（成功・失敗）

各 API の **成功例**と**失敗例**を、実際のレスポンスつきで載せます（`curl` はそのまま貼って実行できます）。
token が必要なものは、先に「0. token の使い方」で `TOKEN` を用意してください。

### 5.1 死活確認 `GET /api/health`

```bash
curl -s http://localhost:8000/api/health
```
```json
{"ok": true}
```

### 5.2 ログイン `POST /api/login`

成功（200）:
```bash
curl -s -X POST http://localhost:8000/api/login -H "Content-Type: application/json" \
  -d '{"userId":"testuser","password":"password"}'
```
```json
{"token": "b109b5ac59d16b18505e2b23f546b4e3"}
```
> token は毎回ランダムに変わります。

失敗（401・パスワード誤り）:
```bash
curl -s -X POST http://localhost:8000/api/login -H "Content-Type: application/json" \
  -d '{"userId":"testuser","password":"wrong"}'
```
```json
{"error": "認証に失敗しました"}
```

### 5.3 新規登録 `POST /api/register`

成功（200）:
```bash
curl -s -X POST http://localhost:8000/api/register -H "Content-Type: application/json" \
  -d '{"userId":"alice","password":"abc123"}'
```
```json
{"ok": true}
```

失敗（409・ID 重複）:
```json
{"error": "このユーザIDは既に使われています"}
```

失敗（400・形式違反。例: `"al!ce"` のように記号を含む）:
```json
{"error": "ユーザIDは15文字以内、パスワードは20文字以内の半角英数字で入力してください"}
```

### 5.4 パスワード変更 `POST /api/account/change`

成功（200）:
```bash
curl -s -X POST http://localhost:8000/api/account/change -H "Content-Type: application/json" \
  -d '{"userId":"alice","password":"abc123","newPassword":"new999"}'
```
```json
{"ok": true}
```

失敗（401・現在のパスワード誤り）:
```json
{"error": "ユーザIDまたはパスワードが違います"}
```

失敗（400・デモ用アカウントを変更しようとした）:
```json
{"error": "デモ用アカウントは変更できません"}
```

### 5.5 退会 `POST /api/account/delete`

成功（200）:
```bash
curl -s -X POST http://localhost:8000/api/account/delete -H "Content-Type: application/json" \
  -d '{"userId":"alice","password":"new999"}'
```
```json
{"ok": true}
```

失敗（401・パスワード誤り）:
```json
{"error": "ユーザIDまたはパスワードが違います"}
```

### 5.6 入力検証 `POST /api/validate`

一部だけ入力（`otherCount` が空）→ `allFilled`/`canCalculate` が false:
```bash
curl -s -X POST http://localhost:8000/api/validate -H "Content-Type: application/json" \
  -d '{"myCount":"5","otherCount":"","total":"50000"}'
```
```json
{"fields": {"myCount": {"filled": true, "valid": true}, "otherCount": {"filled": false, "valid": false}, "total": {"filled": true, "valid": true}}, "allFilled": false, "canCalculate": false}
```

全項目が範囲内 → `canCalculate` が true:
```bash
curl -s -X POST http://localhost:8000/api/validate -H "Content-Type: application/json" \
  -d '{"myCount":"5","otherCount":"5","total":"50000"}'
```
```json
{"fields": {"myCount": {"filled": true, "valid": true}, "otherCount": {"filled": true, "valid": true}, "total": {"filled": true, "valid": true}}, "allFilled": true, "canCalculate": true}
```

### 5.7 割り勘計算 `POST /api/calc`

成功（200）:
```bash
curl -s -X POST http://localhost:8000/api/calc -H "Content-Type: application/json" \
  -d '{"myCount":"5","otherCount":"5","total":"50000","myRatio":"50"}'
```
```json
{"myPerPerson": 5000, "otherPerPerson": 5000, "change": 0, "showJasPay": true}
```

失敗（400・人数 0 は範囲外。どの項目が不正かが `fields` で分かる）:
```bash
curl -s -X POST http://localhost:8000/api/calc -H "Content-Type: application/json" \
  -d '{"myCount":"0","otherCount":"5","total":"50000","myRatio":"50"}'
```
```json
{"error": "入力された数字が不正です", "fields": {"myCount": {"filled": true, "valid": false}, "otherCount": {"filled": true, "valid": true}, "total": {"filled": true, "valid": true}}, "ratioValid": true}
```

### 5.8 QR データ取得 `POST /api/qrcode`（要 token）

成功（200）:
```bash
curl -s -X POST http://localhost:8000/api/qrcode -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" -d '{"amount":5000,"total":50000}'
```
```json
{"content": "jaspay://transfer?to=testuser&amount=5000&ref=0172393b"}
```

失敗（401・token を付けずに呼んだ）:
```bash
curl -s -X POST http://localhost:8000/api/qrcode -H "Content-Type: application/json" -d '{"amount":5000}'
```
```json
{"error": "unauthorized"}
```

### 5.9 結果の登録・取得 `POST` / `GET /api/results`（要 token）

登録（200）:
```bash
curl -s -X POST http://localhost:8000/api/results -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"date":"2026-05-25","time":"18:00","myCount":5,"otherCount":5,"total":50000,"myRatio":50,"myPerPerson":5000,"otherPerPerson":5000,"change":0,"note":"nijikai"}'
```
```json
{"ok": true}
```

取得（200・登録順の配列）:
```bash
curl -s http://localhost:8000/api/results -H "Authorization: Bearer $TOKEN"
```
```json
[{"date": "2026-05-25", "time": "18:00", "myCount": 5, "otherCount": 5, "total": 50000, "myRatio": 50, "myPerPerson": 5000, "otherPerPerson": 5000, "change": 0, "note": "nijikai"}]
```

失敗（401・token なし）:
```json
{"error": "unauthorized"}
```

> 備考に日本語を入れる場合は「0. はじめに」の💡（PowerShell か `--data-binary @file`）を参照。

### 5.10 未定義のパス（404）

```bash
curl -s -X POST http://localhost:8000/api/nope -H "Content-Type: application/json" -d '{}'
```
```json
{"error": "not found"}
```

---

## 6. 通しシナリオ（コピペ用）

ログイン〜計算〜登録〜取得までを一気に流す例です。

### 6.1 bash / Git Bash

```bash
B=http://localhost:8000

# 1. 死活確認
curl -s $B/api/health

# 2. ログインして token を取得
TOKEN=$(curl -s -X POST $B/api/login -H "Content-Type: application/json" \
  -d '{"userId":"testuser","password":"password"}' \
  | python -c "import sys,json;print(json.load(sys.stdin)['token'])")
echo "token = $TOKEN"

# 3. 入力検証
curl -s -X POST $B/api/validate -H "Content-Type: application/json" \
  -d '{"myCount":"5","otherCount":"5","total":"50000"}'

# 4. 計算
curl -s -X POST $B/api/calc -H "Content-Type: application/json" \
  -d '{"myCount":"5","otherCount":"5","total":"50000","myRatio":"50"}'

# 5. QR データ取得（要 token）
curl -s -X POST $B/api/qrcode -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" -d '{"amount":5000}'

# 6. 結果を登録（要 token）
curl -s -X POST $B/api/results -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"date":"2026-05-25","time":"18:00","myCount":5,"otherCount":5,"total":50000,"myRatio":50,"myPerPerson":5000,"otherPerPerson":5000,"change":0,"note":"nijikai"}'

# 7. 結果を取得（要 token）
curl -s $B/api/results -H "Authorization: Bearer $TOKEN"
```

### 6.2 PowerShell（Windows）

`Invoke-RestMethod` は JSON を自動でオブジェクト化し、日本語の備考も UTF-8 で正しく送れます。

```powershell
$B = "http://localhost:8000"

# 1. 死活確認
Invoke-RestMethod "$B/api/health"

# 2. ログインして token を取得
$login = Invoke-RestMethod -Method Post -Uri "$B/api/login" -ContentType "application/json" `
  -Body (@{ userId = "testuser"; password = "password" } | ConvertTo-Json)
$auth = @{ Authorization = "Bearer $($login.token)" }
"token = $($login.token)"

# 3. 入力検証
Invoke-RestMethod -Method Post -Uri "$B/api/validate" -ContentType "application/json" `
  -Body (@{ myCount = "5"; otherCount = "5"; total = "50000" } | ConvertTo-Json)

# 4. 計算
Invoke-RestMethod -Method Post -Uri "$B/api/calc" -ContentType "application/json" `
  -Body (@{ myCount = "5"; otherCount = "5"; total = "50000"; myRatio = "50" } | ConvertTo-Json)

# 5. QR データ取得（要 token）
Invoke-RestMethod -Method Post -Uri "$B/api/qrcode" -Headers $auth -ContentType "application/json" `
  -Body (@{ amount = 5000 } | ConvertTo-Json)

# 6. 結果を登録（要 token・日本語の備考も OK）
$rec = @{ date="2026-05-25"; time="18:00"; myCount=5; otherCount=5; total=50000; myRatio=50;
          myPerPerson=5000; otherPerPerson=5000; change=0; note="二次会" } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri "$B/api/results" -Headers $auth -ContentType "application/json" -Body $rec

# 7. 結果を取得（要 token）
Invoke-RestMethod -Uri "$B/api/results" -Headers $auth
```
