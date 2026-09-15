---
day: 22
planned_date: "2026-10-06"
plan_version: "2026-09-16.v1"
document_type: article_outline
status: skeleton
prerequisites: [14, 15, 16, 21]
---

# Day 22｜錯在哪裡要查得到：可觀察性與最小稽核紀錄

> 文章骨架；可觀察性設計與實際紀錄尚未完成。本篇不要求收集完整用戶對話，也不把 log 當成業務真值。

## 本日任務

回答「使用者看到失敗時，我們能找到哪個步驟出了問題嗎？」讓一次 LINE 事件、模型回合、業務操作與後端狀態可以關聯，但不讓可觀察性變成新的個資與秘密外洩管道。

## 中文摘要

TODO：介紹最少必要的關聯識別、階段耗時、錯誤類型與狀態轉移；說明 trace 顯示成功仍須與後端紀錄核對。

## English Summary

TODO: Correlate transport events, model calls, business operations, and backend states using minimal, redacted telemetry rather than unrestricted conversation logging.

## 第一張圖計畫

LINE 事件識別 → 回合關聯識別 → 業務操作識別 → 工具／後端狀態；旁邊標出每層允許保存的最少欄位與遮蔽規則。

## 正文施工單

### 1. 明確區分各種識別的用途

事件 ID 用於收件去重，操作識別用於業務冪等，trace ID 用於排查；彼此可關聯但不混用。公開範例使用合成值，原始用戶識別不直接進入報表。

### 2. 記錄能回答問題的最少訊號

記錄階段、時間、結果類型、重試次數與可取得的模型用量。不預設所有觀測欄位在每個 SDK 都存在；缺值要標明，不猜測成零。

### 3. 加上遮蔽、存取與保存期限

遮蔽 token、秘密、完整對話與多餘個資；定義誰能查、保存多久、如何刪除。即使識別經過雜湊，也不自動宣稱資料已匿名。

### 4. 以一次故障重建時間線

重跑 Day 14 的回應遺失或 Day 15 的通知失敗，從紀錄定位斷點，再查後端確認真實狀態。觀測服務不可用時，系統應安全降級，而非因 log 失敗重做業務。

## 預定交付與驗收

預定：`src/observability/`、`tests/observability/`、`docs/day22/telemetry-contract.md`、`docs/day22/verification.md`；尚未建立。

| 案例 | 預期 | 實際結果 |
|---|---|---|
| 正常回合與逾時核對 | 能關聯階段與後端事實，不靠完整對話 | 未執行 |
| 輸入包含合成秘密標記 | 公開／一般操作紀錄不出現敏感值 | 未執行 |
| 紀錄輸出失敗或缺少欄位 | 不重做副作用，不把缺值當成功 | 未執行 |

使用合成 canary 值檢查紀錄洩漏；報告測過的輸出管道與仍未覆盖的範圍。沒有真實追蹤平台就展示本機結構化紀錄，不冒充雲端畫面。

## 查證與銜接

入口：[SERIES.md](../SERIES.md) 的 G-ADK、G-SAFETY、C-RUN；若採 Cloud Logging 或 OpenTelemetry，另查所用官方 SDK 與資料處理設定。前篇 [Day 21](day21.md) 定評測，下篇 [Day 23](day23.md) 用實測訊號分析延遲與成本。
