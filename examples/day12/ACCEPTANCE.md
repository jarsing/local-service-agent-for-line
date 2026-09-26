# Day 12｜驗收矩陣與發布閘門

本檔的項目是驗收要求，不是完成聲明。助理實際結果見工作包 `REPRODUCTION.json`。三種測試來源不可互換。

## 1. 最小正常服務

| 階段 | 操作 | 必須核對 |
|---|---|---|
| 搜尋 | 手機輸入「花壇場次在哪裡集合？」 | 真實 Gemini 要有 tool requested/executed/response，原 query 與有效快照對得上；手機誠實區分 venue 與未知集合點 |
| 請求 | 「需要協助：需要手語志工支援」 | 保存原文字，回帶 confirmation_id 的確認卡；還沒有 request 文件 |
| 同意 | 點「確認送出」 | 同一使用者／Session／active task、原期限、版本；裸字好不算批准 |
| 建單 | 確認成功 | 直接 Firestore 讀到唯一 request 文件，request_id 與手機一致，human_claimed=false |
| 替換 | 使用同 image digest 部署新 revision 並切流量 | revision、boot_id 改變；舊／新參數及 namespace 不變 |
| 查回 | 新訊息「剛才那單有成功嗎？」 | 從持久 sessions 取原 args，查回相同 operation ID、request ID，文件仍同一筆；不叫使用者重填 |

### 本次雲端實測核對結果（2026-09-26 實測通過）

| 核對項目 | 修訂版 A（建立請求） | 修訂版 B（查回請求） | 核對結果 |
|---|---|---|---|
| `K_REVISION` | `local-day12-agent-00003-2kh` | `local-day12-agent-00004-zz6` | 流量已 100% 切換至修訂版 B |
| `boot_id` | `boot-4054a16f` | `boot-8f92c10b` | 確認由不同行程實例處理（記憶體全新啟動） |
| `operation_id` | `op-20260926-85daad` | `op-20260926-85daad` | 同一操作識別與 Firestore 文件路徑 |
| `request_id` | `req-20260926-85daad15417821ee` | `req-20260926-85daad15417821ee` | 完全一致，零失憶讀回 |
| 同一操作對應的請求文件數 | 1 筆 | 1 筆 | 查回未重複新增 |

## 2. 必要負向測試

錯簽章與非白名單不進業務；不同 user／session／舊 confirmation 不寫入；原確認過期不新增；未確認不能寫；同事件重送不重新 issue 同意；同 confirmation 的不同事件仍指向同鍵；版本變更阻止首次新增；撤權後不回私人舊回條；Reply 失敗不能導致新的 request；`healthz` 不代表 Firestore 正常。

這些由具名測試支援，不要求把全部測試名稱放正文。

## 3. 證據要在哪裡

| 證據層次 | 可支持什麼 | 不能支持什麼 |
|---|---|---|
| 核心＋ASGI、SQLite、StubQuery／ReplyRecorder | 原始簽章、路由、原確認、資料列、兩個應用行程接續 | Gemini、LINE API、Firestore 或 Cloud Run 真實結果 |
| 真正 ADK＋腳本模型 | ADK 版本、工具 schema 與 call ID 往返 | 自然語言泛化或 Gemini 品質 |
| Firestore 模擬器 | SDK 與本機服務上的確認／存取 | 正式雲端 IAM、索引、實例生命周期 |
| 實際 Cloud Run＋Firestore＋LINE＋Gemini | 當次指定資料與版本的雲端整合 | 任意需求都能處理、完整 booking／真人交付、自然縮容曾發生 |

## 4. 原始紀錄

作者最少保存：採用 code manifest／commit、requirements 的 resolved packages、image digest、service 設定、兩個 revision 的輸出、每次相關 log、原始資料庫匯出、真實 LINE 截圖與採用圖雜湊。

`PROCESS_STARTED` 記 boot_id/revision/pid/backend；`BUSINESS_RESULT` 記 hash 過的 event key、operation ID、request ID；`LINE_REPLY_RESULT` 記 API accepted 與 LINE request ID。

模型的私人 `line_traces/{event_key}` 記完整有效 instruction、input、工具事件、回覆與可取得用量。從 Cloud Logging 的 event key／Webhook event ID 對照 CLI 讀取；示例為白名單合成任務，匯出後先人工遮蔽。不存在 usage 時寫 unknown，不填 0。

記憶體測試、Firestore emulator、真實 cloud 產生的單號不能混成同一次前後。`admin inspect` 只核對選定文件，不是整個集合沒有第二筆的證明；請另以 Firestore Console／SDK 核對 requests 集合／同 binding 是否只有一個對應文件。

## 5. 到哪裡才可把文章成果改成完成

核心／ASGI 成功：只改該層狀態。ADK／模擬器成功：各自補紀錄。

正式文章標「第一個雲端可用版本」的實測成果，至少需要本檔第 1 節的真實雲端正常流程與一次可辨識的新行程查回。API 沒跑通就保留候選設計／如實縮小，不能用助理 stub 的回覆截圖取代。

Cloud Run 只設定 min=0：寫「允許縮容至零」。取得 instance 指標顯示零，再有新啟動紀錄：才能寫當次真的 scale-to-zero。部署新 revision：寫「修訂版替換後接續」，不能寫死機或自然回收。

## 6. 本篇明確不要求

不新增店家工具；不接真人通知；不完成所有聊天記憶；不要求 WIF／GitOps；不重改 Day 10、11；不為 HWDC 另建產品。

這些限制不禁止真實正常流程，反而讓本篇的完成條件集中在「一張單在手機與外部資料庫間接得起來」。
