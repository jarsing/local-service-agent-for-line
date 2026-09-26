# Day 12｜從 LINE 到同一張請求的最小架構

狀態：可執行候選實作，非雲端上線證明。正式題名依作者決定為「Day 12｜第一個雲端可用版本」。

## 1. 來源、提案與驗證分開

來源為交接 ZIP、所指向的 `1f548cc133c9a170bfc97b5ad031e7a7d955e721` 特定檔案，以及官方 LINE／Google 文件。摘要的函式名稱與實際原始碼有落差，完整差異在工作包 `SOURCE_ALIGNMENT.md`。

下列是 Day 12 新設計，不是來源已實作：FastAPI 統一入口、持久化的待確認 postback 接點、事件去重／回覆狀態、ADK 自然語言搜尋、雲端部署與跨 revision 驗收。

## 2. 資料流

LINE 原始 request bytes → 簽章驗證 → destination／direct-user／白名單 → 持久授權紀錄 → 路由。

一般查詢：原句 → ADK／Gemini 選搜尋參數 → Day 5 `search_catalog` → 有來源的欄位回覆。

需要協助：保留原句 → 原 Day 11 `prepare(approved=False)` → LINE quick reply 確認卡 → 帶原 confirmation_id 的 postback → Day 12 持久化同意 → 原 Day 11 `create()` → Firestore request → LINE Reply。

查詢原單：可信 LINE 身分 → 穩定邏輯 Session → 原 Day 11 `restore_session()` → 原 args → `lookup()` → 原單號。這段不用再呼叫模型。

不把 Gemini 指令中的「允許」當成權限，也不把裸字「好」當作哪一張確認卡的批准。

## 3. 元件

| 檔案 | 責任 |
|---|---|
| `main.py` | HTTP、路由、在回 200 前完成必要工作、最小事件 log |
| `settings.py`／`identity.py` | 明示後端與模型、白名單、raw-body HMAC、跨 revision 穩定 Actor |
| `catalog_view.py` | Day 9 歷史快照投影、Day 5 搜尋核心、已知／未知欄位呈現 |
| `adk_query.py` | 真正 ADK 自然語言工具呼叫候選；3 次模型呼叫、2 次搜尋工具上限 |
| `tasks.py` | 延後同意接點，重用 Day 8／11；不重建已存在的原操作 |
| `delivery.py` | webhook 事件去重、私人 query 額度、Reply 結果不明的處理 |
| `messages.py` | 程式產生確認與單號回覆，不讓模型編造狀態 |
| `inherit.py` | 讀取前篇原碼；撞名／版本不符明確失敗 |
| `admin.py` | 操作者一次性 seed 與指定任務匯出，不暴露 HTTP 管理介面 |
| `build_context.py`／`Dockerfile` | 列明檔案建置，不上傳私人工作區 |
| `verify.py`／`demo.py` | 分層測試與兩個獨立應用行程示範 |

## 4. Firestore 與 Session

保留 Day 11 真實路徑，不暗改成摘要中的另一套集合：

`local_day11_demo/{day11-d12-作者選定命名空間}/{collection}/{id}`

沿用 `bindings/confirmations/requests/jobs/sessions/grants/catalogs/drafts`；新增 `line_events`、`line_budget`、`line_traces`。

`jobs` 沿用 prepare 所建立的工作紀錄。本篇正常路徑透過明確確認直接呼叫原 create，查詢原單則只 lookup；沒有把 Day 11 worker 改成常駐雲端排程服務，也沒有宣稱所有 Day 11 故障演練已在 Cloud Run 重驗。

`line_events` 是平台事件狀態；`bindings` 的原送出鍵辨認一次業務操作。新 status 訊息是新事件，但要讀回同一業務操作。相同句子本身不是唯一識別；明確「新需求：」才啟動另一件事。

成功與已取得事件的失敗模型回合都保存，不只留有利輸出。

`line_traces` 保存白名單測試者的原問句、模型原文、工具事件、用量及版本。屬私人測試資料，需事前告知測試者；不放到公開 log 或 Repo。原始 reply token、channel secret、access token 不寫入文件。作者另定保留期間與清理；本例沒有自動刪除排程。

一個 logical Session 只指向目前任務。新需求會替換目前參照；舊卡片因 active_operation 不符而拒絕。這不是跨任意聊天、群組或多任務搜尋的產品。

## 5. Google AI 的具體工作

`AdkQuery` 接收到的是使用者原句，不是 Day 11 固定 harness 的 `expected_tool/send_args`。

模型選擇日期、地區與活動名稱關鍵字；工具真正查資料。模型最終說明留在私人 trace，手機的時間、地點、來源、確認與單號則由已核對的工具／資料庫欄位組成。這是本次有意選擇的呈現方式，不是聲稱自然語言生成已全部通過語意評測。

一般查詢每回合至多 3 次模型呼叫、2 次工具呼叫，整段 ADK 消費有 18 秒 timeout；每個模型 HTTP 請求候選設定 `attempts=1`。SDK 支援該參數已對照上游 `google_llm.py`，仍須在作者選定依賴組合 smoke test。Firestore RPC 的自己的 timeout／交易重試是不同預算，不能把 18 秒描述成整個 Webhook 的硬性完成保證。

每位測試者每 UTC 日預設最多 10 次查詢嘗試，儲存在 Firestore，換行程不歸零。失敗嘗試也計算；查原單／確認不耗模型額度。這是應用端模型回合門檻，不是 Google 帳單總額上限。

## 6. 重要交易邊界

`prepare()` 保留原 issue、原 ID、快照與期限。Day 12 新增的 `decide()` 只在已驗簽 postback、owner/session/active task、版本／內容／時間均通過後，保存確認收據；這是新的持久化判斷，不宣稱原 Day 8 的記憶體 decide 可以直接還原。

確認與建單是兩筆交易。確認已保存、建單未完成時，查詢可能得到待查證；使用原確認卡重送仍使用原鍵，交給 Day 11 的資料庫限制。`execution_allowed` 永遠維持 false，不改成 true。

模型呼叫與 LINE Reply 都在 Firestore 交易外；取得 request 結果不等於 Reply 被 LINE 接受，更不等於手機已看見或真人已接手。

## 7. Webhook 的速度與可用範圍

LINE 官方建議非同步處理；正式慢任務應使用可持久交付的佇列。本篇是明示的少量白名單同步示範：關鍵工作與 Reply 在回 HTTP 200 前完成，不使用 Day 4 記憶體 queue 或 FastAPI BackgroundTasks 執行重要寫入。

同事件正在處理時回 503；有發送意圖後，即使 Reply 結果未知，也不盲目重複送 Reply。資料庫已建立請求時，使用者的新「查詢原單」事件可讀回。這取捨避免重複副作用，但沒有保證每一則回覆必送達；冷啟動、LINE reply-token 期限、批次事件與服務延遲仍須真實測試。部署需量延遲，不靠 healthz 代證。

`/healthz` 只回本行程 HTTP 健康，不查外部資料庫／模型，不會因外部中斷而反覆殺掉容器。它不是完整 readiness 或端到端健康保證。

## 8. 版本替換實驗

主要可重現路徑：同一 image digest 部署新 revision → 將流量切至新 revision → 從 LINE 發一則新的查原單訊息。

要核對 `K_REVISION`、每次啟動亂數產生的 `boot_id`、image digest、Firestore request 路徑、operation ID 與 request ID。

revision 是修訂版，不是單一實例 ID；boot_id 是本程式產生的啟動識別，不是 GCP 簽發的 instance ID。容器 PID 可能都是 1，不能只比 PID。新 revision 查回不能宣稱觀察到「縮至零」；自然 scale-to-zero 另看 instance 指標與時間區間。

Day 12 在核准的雲端 namespace 新建本次請求，不自動搬移 Day 11 的本機教學單據；沿用的是程式與資料責任，非宣稱舊資料已遷移。
