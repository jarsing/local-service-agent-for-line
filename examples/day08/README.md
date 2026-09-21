# Day 8｜一句「好」不夠：確認綁定具體操作

把對話中的一句「好」，綁定到具體的使用者、操作內容、資料版本與有效期限。

**使用者需求 → Gemini 整理草稿與工具呼叫 → 程式組成確認內容 → ADK 出示確認等待回覆 → 使用者確認 → 程式重新核對伺服器狀態 → 記錄內容確認收據。**

本篇實作結合 Google ADK 的 `ToolContext.request_confirmation` 與本機應用端的 `ConfirmationStore`，並對照「正常確認」與「等待中換版」兩種情境。

## 1. 先跑不用金鑰的離線驗證

以下指令均從 **Repo 根目錄** 執行（macOS / Linux）：

```bash
# 沿用 Day 5 既有虛擬環境
PY=examples/day05/.venv/bin/python

# 執行 34 項離線測試（25 項核心單元測試 + 9 項 ADK 工具確認整合與介接回歸測試）
$PY examples/day08/verify.py

# 執行合成資料離線示範（0 模型呼叫）
$PY examples/day08/demo.py

# 生成本機人機協同確認介面 HTML
$PY examples/day08/ui.py
```

若直接使用系統 Python 3.10+（不含 ADK 套件時），可單獨執行 25 項核心邏輯測試：

```bash
python3 examples/day08/test_confirmation.py
python3 examples/day08/demo.py
```

## 2. 核心架構與設計規則

- **確認不是布林值**：核心確認紀錄包含 `owner` (使用者與 Session)、`snapshot` (操作與活動資訊快照)、`fingerprint` (SHA-256 內容指紋)、`catalog_version` (目錄採用版本) 與 `expires_at` (到期時限)。
- **入口在按鈕，防線在後端**：畫面上的確認按鈕僅是輸入入口；真正接收確認時，後端必須重新核對伺服器端目前最新狀態。
- **等待中換版防禦**：使用者在畫面看到舊時段（07:30~11:00），若在決定期間系統已採用新版（08:00~11:00），按鈕送出的舊確認將被判定為 `version_changed`，系統出示新時段並要求重新確認，避免誤認舊資訊。
- **收據不等於執行授權**：所有核心判定回傳的 `execution_allowed` 均固定為 `false`。Day 8 僅完成「內容確認」；真正的人工服務請求建立與後端寫入保留至 Day 9。

## 3. 檔案結構

- `confirmation.py`：單行程記憶體確認核心（`ConfirmationStore`、`Identity`、`Operation`、`operation_fingerprint`）。
- `test_confirmation.py`：25 項核心單元測試（涵蓋正常接受、版本換版、內容異動、不同使用者、期限邊界、重複確認等）。
- `adapter.py`：提供兩份花壇場次內建教學快照（演練標籤 `v-0337e2296139` 與 `v-62ccd0ef3ca44e6ca8b7ef2d3302ab28`，不等同 Day 7 原始歸檔 `version_id`）與狀態切換器。
- `adk_bridge.py`：ADK 工具確認介接層，將 `ToolContext.request_confirmation` 與 `ConfirmationStore` 串接。
- `test_adk_offline.py`：9 項使用 `ScriptedMockLlm` 的離線 ADK 流程整合與介接邊界測試。
- `ui.py`：人機協同介面生成器，產出靜態實測報告 `CONFIRM.html`。
- `verify.py`：全域離線驗證入口（34 測試全數通過）。
- `run.py`：統一執行腳本，省略 `--live` 時使用離線替身（預設），加上 `--live` 時執行真實 Gemini 呼叫（需 `GEMINI_API_KEY`）。
- `CONTRACT.md`：核心小規格與驗收條件。

## 4. 真實 Gemini 模型實測（需 API Key）

當設定好環境變數後，可執行真實 Gemini 3.8 Flash 工具確認流程：

```bash
export GEMINI_API_KEY="你的_GEMINI_API_KEY"
$PY examples/day08/run.py --live --model gemini-3.8-flash
```

實測會依序執行：
1. **情境 1**：正常流程，Gemini 整理詢問並呼叫 `prepare_handoff_draft`，ADK 暫停發出確認，確認後寫入收據。
2. **情境 2**：等待中換版，出示 v1 後切換至 v2，確認時回傳 `version_changed`，由模型提示新時段。
