---
day: 15
planned_date: "2026-09-29"
plan_version: "2026-09-16.v1"
document_type: article_outline
status: skeleton
prerequisites: [4, 11, 14]
---

# Day 15｜LINE 重送也不能重做：事件去重與非同步工作邊界

> 文章骨架；可靠收件、佇列與工作程序尚未實作，不能把一般背景執行緒當成已具備可靠投遞。

## 本日任務

回答「同一個 Webhook 來兩次，或收件後程序掛掉怎麼辦？」分開傳輸事件、業務操作與使用者通知的識別，建立不靠單一請求生命週期完成長任務的處理契約。

## 中文摘要

TODO：介紹事件去重、持久化收件與工作恢復；說明 LINE 事件重送識別與 Day 14 的業務冪等識別不能互相代替。

## English Summary

TODO: Separate webhook delivery deduplication from business-operation idempotency and define a durable processing boundary for work that outlives the HTTP request.

## 第一張圖計畫

Webhook 驗簽 → 持久化收件／去重 → 回應 HTTP → 工作程序 → 原業務操作 → 狀態查詢／合法通知路徑。明示收件成功不等於業務成功。

## 正文施工單

### 1. 先核對 LINE 重送與回覆的實際規則

查官方事件識別、重送、順序與回覆限制。不要假設事件永不重複、永遠依序抵達，或 reply token 能在任意久之後重用。

### 2. 定義收件確認與持久化邊界

只有達到明確的可靠收件條件才回覆平台已接收；用本機持久化工作表或適合環境的佇列做最小驗證。具體後端需記 ADR，不在沒有驗證下宣稱 exactly-once。

### 3. 讓工作程序可以重試與恢復

定義待處理、執行中、完成與待核對狀態，處理程序中止與工作逾期。收件去重防止重複工作，Day 13–14 的業務冪等再防重複副作用，兩道防線各測一次。

### 4. 將結果通知視為另一個可失敗步驟

任務完成但通知失敗不能重做原業務；保留可查詢狀態。若使用 push 或其他通知方式，先核對條件、權限與費用，不任意向真實使用者發訊息。

## 預定交付與驗收

預定：`src/jobs/`、`tests/jobs/`、`docs/day15/delivery-contract.md`、`docs/day15/verification.md`；尚未建立。

| 案例 | 預期 | 實際結果 |
|---|---|---|
| 同一事件重送或並發抵達 | 不建立重複業務副作用 | 未執行 |
| 收件後／執行中程序中止 | 重啟後可恢復原工作與識別 | 未執行 |
| 業務已完成、結果通知失敗 | 只處理通知／查詢，不重建請求 | 未執行 |

真正中止再啟動工作程序，核對持久化紀錄；記憶體 mock 不能證明故障恢復。列清本機實驗與雲端服務的差異。

## 查證與銜接

入口：[SERIES.md](../SERIES.md) 的 L-WEBHOOK、L-SIGNATURE、C-RUN；佇列與通知 API 查實際選用的官方文件。前篇 [Day 14](day14.md) 修復未知結果，下篇 [Day 16](day16.md) 系統化驗證工具與資料邊界。
