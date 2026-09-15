---
day: 14
planned_date: "2026-09-28"
plan_version: "2026-09-16.v1"
document_type: article_outline
status: skeleton
prerequisites: [1, 11, 12, 13]
---

# Day 14｜逾時不等於失敗：讓 Day 1 的驗收案例真正跑起來

> 文章骨架；既有 Day 1 JSON 是規格，不是本日已通過的測試。以下故障注入與核對流程仍待實作。

## 本日任務

兌現首篇承諾：工具逾時、後端是否寫入仍未知時，LOCAL 不宣告完成，也不換新識別重建。回答「回應遺失了，怎麼知道事情到底有沒有做？」

## 中文摘要

TODO：以寫入前逾時、寫入後回應遺失兩種情況，解釋未知狀態、相同冪等識別核對與有界重試；只有真實執行後才寫測試結論。

## English Summary

TODO: Turn the Day 1 synthetic acceptance specification into an executable regression case covering uncertain write outcomes and reconciliation with the original idempotency key.

## 第一張圖計畫

寫入要求 → 後端可能已保存 → 回應逾時 → pending_verification → 以原識別核對 → 已存在／仍處理中／可安全重試。不要把第一次查不到直接畫成「確定未寫入」。

## 正文施工單

### 1. 先逐項保留 Day 1 的驗收預期

直接讀取 `docs/day01/handoff-timeout-001.json`，讓測試引用它而非複製一份可能漂移的預期。說明 `claim_completed: false`、`reconcile_by_idempotency_key` 與 `reuse_same_idempotency_key` 對應的程式行為。

### 2. 在可控制的位置注入故障

分別模擬寫入前中止、寫入完成但回應遺失、核對查詢失敗與仍在執行。保留後端真實紀錄，讓測試能區分「不知道」與「實際沒有寫入」。

### 3. 用持久化操作識別恢復未知結果

沿用 Day 13 的原識別、已確認內容與使用者範圍。核對本身不能跨人查詢；第一次未查到紀錄不必然代表原操作不會稍後完成，需依後端一致性與交易契約判斷。

### 4. 讓重試有界且不重複副作用

所有重試沿用同一冪等識別；期限、退避與轉人工條件明確記錄。若權限已失效或確認需重做，按契約處理，不因重試而放寬安全門檻。不能保證任意外部服務都具備同樣語意。

## 預定交付與驗收

預定：`src/reconciliation/`、`tests/reconciliation/`、`docs/day14/fault-matrix.md`、`docs/day14/verification.md`。既有 Day 1 JSON 保留不變；上述新檔尚未建立。

| 案例 | 預期 | 實際結果 |
|---|---|---|
| 已保存但回應遺失 | 先回未知；核對後回既有請求，不重建 | 未執行 |
| 未保存或仍在執行 | 依明確後端契約等待／以原識別安全重試 | 未執行 |
| 核對不可用、重試超限或程序重啟 | 保留未知與原識別，不誤报完成 | 未執行 |

每個案例同時驗證使用者回覆、請求筆數與操作識別。確定性故障測試與真實模型回覆測試分開；附實際命令與去識別紀錄，不生成假的成功截圖。

## 查證與銜接

入口：[SERIES.md](../SERIES.md) 的 G-FUNCTION、G-SAFETY；查所選資料庫的交易、一致性與唯一性文件。前篇 [Day 13](day13.md) 建立請求，下篇 [Day 15](day15.md) 處理 LINE 事件重送與工作程序生命週期。
