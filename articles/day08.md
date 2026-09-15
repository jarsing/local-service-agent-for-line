---
day: 8
planned_date: "2026-09-22"
plan_version: "2026-09-16.v1"
document_type: article_outline
status: skeleton
prerequisites: [2, 6, 7]
---

# Day 8｜讓 Agent 真的會查：受控的地方服務查詢工具

> 文章骨架；工具名稱與資料格式都是待建立的 LOCAL 內部契約，尚未實作。

## 本日任務

讓 Agent 從自由生成改為查詢一份合成服務目錄。回答「模型挑選工具之後，誰負責參數、權限與回傳結果？」今天只做結構化欄位查詢，Day 9 再處理知識內容與引用。

## 中文摘要

TODO：從查詢服務項目開始，說明工具宣告、應用程式驗證、執行與结果回傳的分工；強調沒有結果時不能自己補出服務。

## English Summary

TODO: Add a read-only service lookup tool with validated arguments, bounded results, and explicit handling of empty or failed lookups.

## 第一張圖計畫

需求 → 模型提議查詢 → 伺服器檢查 → 合成目錄 → 受控結果 → 附限制的回答。把未知工具與不合法參數導向拒絕分支。

## 正文施工單

### 1. 建立小而可核對的合成服務目錄

定義服務識別、類別、場域與可公開描述；用明確的假資料，不模仿真實機關受理承諾。先保留確定性的查詢基線，不為小資料加入向量資料庫。

### 2. 設計工具的最小輸入與輸出

依官方文件核對 ADK 工具與 Gemini 呼叫方式。參數做型別、長度、允許值及數量限制；場域／使用者範圍來自可信伺服器，不由模型任意擴張。

### 3. 區分查無資料、工具失敗與合法結果

三者使用不同狀態；沒有項目不是錯誤，也不是允許模型編造答案。工具輸出帶穩定來源識別，為 Day 9 的引用準備。

### 4. 看執行軌跡，不只看最後一句

驗證實際呼叫的工具、參數與回傳內容；不要只看模型說「我查過了」。多次呼叫要有上限，禁止通用任意 SQL、URL 或 shell 工具。

## 預定交付與驗收

預定：`examples/service-catalog/`、`src/tools/`、`tests/tools/`、`docs/day08/tool-contract.md`、`docs/day08/verification.md`；目前尚不存在。

| 案例 | 預期 | 實際結果 |
|---|---|---|
| 存在且符合條件的服务 | 回傳可核對識別與限定欄位 | 未執行 |
| 查無資料／工具逾時 | 分別回覆無結果／暫不可用，不捏造 | 未執行 |
| 未知工具或超出允許範圍參數 | 在執行前拒絕 | 未執行 |

分開測試工具本身、Agent 選工具與端到端回答；三層都需證據，不能互相代替。

## 查證與銜接

入口：[SERIES.md](../SERIES.md) 的 G-FUNCTION、G-ADK、G-SAFETY。前篇 [Day 7](day07.md) 有執行骨架，下篇 [Day 9](day09.md) 讓回答能追溯到具體資料。
