---
day: 11
planned_date: "2026-09-25"
plan_version: "2026-09-16.v1"
document_type: article_outline
status: skeleton
prerequisites: [7, 8, 10]
---

# Day 11｜對話記得，不等於任務完成：拆開 Session、任務與後端狀態

> 文章骨架；業務狀態與儲存介面尚未實作。ADK 的 session 與業務資料庫不得混為一談。

## 本日任務

回答「使用者說繼續時，系統究竟要接哪件事？」建立對話、待確認操作、已建立請求的責任界線，為後續寫入與逾時核對準備可持久化的業務狀態。

## 中文摘要

TODO：用關閉對話再回來的案例，說明 session、任務狀態與後端事實各自保存什麼；明確指出模型記憶不具有業務完成權威。

## English Summary

TODO: Separate conversational context, pending task state, and authoritative backend records, including restart and identity-isolation requirements.

## 第一張圖計畫

同一使用者 → 對話 Session／任務狀態／後端請求三個容器；標示哪些可由摘要重建、哪些必須查持久化事實。

## 正文施工單

### 1. 定義三種狀態的擁有者與生命週期

session 保存對話相關資訊；任務追蹤正在釐清或等待確認的內容；後端紀錄保存真正執行結果。狀態名稱先映射 Day 2 契約，不重複發明互相衝突的枚舉。

### 2. 從可信入口建立範圍與識別

定義使用者、場域、對話與任務識別的關係。識別來自伺服器已驗證的事件，不接受模型提供另一個 user ID 就跨人查詢。

### 3. 為業務狀態建立可替換儲存介面

先以適合 Day 3 技術棧的本機持久化實作做測試，明確定義讀取、版本檢查與原子更新。ADK session adapter 另依官方支援選定，不假設 Firestore 能直接代入任何介面。

### 4. 重啟、重複與順序顛倒時怎麼辦

測試重新啟動後的狀態恢復、兩次更新衝突與舊訊息覆蓋。今天以合成業務紀錄驗證儲存，不宣稱 Day 13 的真實建單能力已完成。

## 預定交付與驗收

預定：`src/state/`、`tests/state/`、`docs/day11/state-model.md`、`docs/day11/verification.md`；尚未建立。

| 案例 | 預期 | 實際結果 |
|---|---|---|
| 同一使用者中斷後繼續 | 恢復正確任務，不靠模型猜測 | 未執行 |
| 其他使用者／場域查同一任務 ID | 被拒絕，無資料外洩 | 未執行 |
| 重啟或舊版本更新 | 事實保留；衝突有明確處理 | 未執行 |

至少做一次真正的本機程序重啟測試；記憶體替身通過不能證明持久化。並發測試邊界與未測規模要註明。

## 查證與銜接

入口：[SERIES.md](../SERIES.md) 的 G-SESSION、G-MEMORY；本機資料層另查實際採用的官方文件。前篇 [Day 10](day10.md) 決定何時釐清，下篇 [Day 12](day12.md) 把確認綁定到具體待執行任務。
