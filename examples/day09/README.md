# Day 9｜按兩次送出，會不會多一筆？受控建單與冪等

正式文章：https://ithelp.ithome.com.tw/articles/10415923。前篇：[Day 8](https://ithelp.ithome.com.tw/articles/10415219)。

已確認詢問 → ADK 工具 → 真正 SQLite 保存 → 單號 → 同鍵同內容取原單 → 同鍵異內容衝突。

## 1. 先跑不需要 Google 套件的部分

以下全部從 Repo 根目錄執行（macOS／Linux）：

```bash
python3 examples/day09/verify.py
python3 examples/day09/demo.py
```

`verify.py` 預設是確認／建單核心與報告測試。`demo.py` 真正寫入新的 SQLite，印出 `report.json` 與 `REPORT.html` 的位置。每次結果都在 `examples/day09/output/` 新開資料夾，不覆蓋前次。

Day 8 相依核心需在 `examples/day08/confirmation.py`；請使用包含前篇的完整 LOCAL Repo。讀者可用 Python 3.10+；作者既有環境是 Python 3.13.5。原 Day 8 程式保持唯讀，版本不同時先核對相容性。

## 2. Google ADK 離線整合

沿用 Day 5 已安裝的虛擬環境：

```bash
PY=examples/day05/.venv/bin/python
$PY examples/day09/verify.py --sdk
$PY examples/day09/run.py
```

`run.py` 省略 `--live` 使用固定腳本的模型替身，真正走 ADK Runner 與 FunctionTool；這不是 Gemini 模型品質實測。完整驗證會清楚區分各組數量；SDK 缺套件時回報未完成，不計為通過。

全新讀者可另外建立 Day 9 虛擬環境並安裝 requirements；安裝會連網，請依自己的環境確認：

```bash
python3 -m venv examples/day09/.venv
examples/day09/.venv/bin/python -m pip install -r examples/day09/requirements.txt
PY=examples/day09/.venv/bin/python
$PY examples/day09/verify.py --sdk
```

相依版本沿用本系列 `google-adk==2.9.1`、`google-genai==2.23.0`、`httpx==0.28.1`，不是宣稱目前最新版本。

## 3. 真實 Gemini（另計 API 用量）

先在環境中設定 `GEMINI_API_KEY`，或指定自己已有的私人檔案：

```bash
$PY examples/day09/run.py --live --approve-live
# 指定檔案時加 --env-file /你自己的路徑/.env
```

不會自行搜尋其他資料夾或印出金鑰。預設沿用前篇 `gemini-3.8-flash`／LOW；若該帳號不支援，保留錯誤並先確認選擇，不自動換模型。

一次實驗兩回合：首次建單、同一組參數重送。全程最多 6 次模型請求，每回合最多 3 次；兩次工具執行，每回合最多 1 次。HTTP attempts=1，沒有隱藏自動重試；單回合整體有時間上限。

兩回合都從同一份新確認開始；測試程式使用 Day 8 原核心明確代送同意。成功必須同時核對工具參數、事件對應、兩個狀態、同一單號、資料庫一筆、回覆引用正確單號。語氣與是否暗示真人已處理仍需人工讀原文。

## 4. 作者工作區的證據路徑

要將結果存回每日資料夾，從 Repo 根目錄加：

```bash
--origin author_local --out ../../LOCAL-Day09/editorial/evidence
```

這兩個參數適用於 `verify.py`、`demo.py`、`run.py`；新讀者可維持預設 `reader_local`。`origin` 是執行者標記，原始紀錄的真假仍須靠實際檔案與執行過程核對。

報告保留 Python／SQLite／套件版本、實際 source_files 雜湊、可見工具事件與模型用量；thoughts token 缺值保留 null。`day08_dependency_commit` 只是前篇相依基準，Day 9 尚未 Commit 時不猜 SHA。

## 5. 契約、身分與副作用

完整規格：[CONTRACT.md](CONTRACT.md)。

- `request_created`：本次新建成功；`already_created`：原單存在並已核對內容。
- `idempotency_conflict`：同鍵參數不同，原單不改。
- `unconfirmed_operation`：原確認找不到、不同人、尚未確認或已取消，沒有首次建單。
- `expired`、`version_changed`、`content_changed` 等沿用前篇核對結果；`storage_busy` 則是資料庫忙碌。
- `HandoffRequest.status` 為 `pending_human_review`。`human_claimed: false`，本篇沒有對外通知或真人受理。
- 權限與 `Actor(tenant_id,user_id,session_id)` 由可信入口提供；Day 8 的原 `Identity(user_id,session_id)` 不變。這裡測試隔離，不等於完成真實登入。
- 首次寫入要有仍有效確認；重送已建立同鍵同內容是讀原回條，確認之後到期也不再寫入。
- SQLite 交易管理實際資料列；確認狀態仍在同一行程記憶體。這不是跨服務的 exactly-once 執行保證。

## 6. 檔案入口

| 檔案 | 用途 |
|---|---|
| `handoff.py` | 資料結構、SQLite 交易／唯一約束、建單與原單回條 |
| `day08_gateway.py`／`dependencies.py` | 唯讀重用 Day 8，集中身分與確認介接 |
| `fixtures.json` | 花壇教學快照；保留 Day 8 演練標籤，非 Day 7 原 version_id |
| `adk_bridge.py`／`runtime.py` | 工具簽名、可信身分與兩回合驗證 |
| `scripted_model.py` | 離線模型替身，非 Gemini |
| `demo.py`／`run.py` | 核心對照／ADK與Gemini入口 |
| `verify.py`、`test_handoff.py`、`test_reporting.py`、`test_adk_offline.py` | 分層測試與動態數量 |
| `reporting.py`／`provenance.py` | 靜態報告、來源與用量，不預填作者心得 |

Day 10 接續這份建單契約處理逾時與原識別核對；本篇沒有啟用 GitHub Actions。
