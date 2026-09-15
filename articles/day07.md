---
day: 7
planned_date: "2026-09-21"
plan_version: "2026-09-16.v1"
document_type: article_outline
status: skeleton
prerequisites: [3, 5, 6]
---

# Day 7｜用 Google ADK 組成第一個單一 Agent

> 文章骨架；Agent 尚未實作。框架的實際 API 以 Day 3 選定版本及本日核對為準。

## 本日任務

在 Day 5 的模型適配與 Day 6 的驗證邊界上，引入單一 ADK Agent。回答「加入框架後，哪些責任可以交給它，哪些仍然是我們的？」先讓最小回合保持可測試，不急著加入多 Agent。

## 中文摘要

TODO：說明單一 Agent、執行流程與事件／session 的分工；比較加入 ADK 前後的責任，而不是重寫一篇框架功能列表。

## English Summary

TODO: Introduce a minimal single-agent ADK integration while keeping application validation, identity, and business state outside model authority.

## 第一張圖計畫

LINE 適配 → ADK 執行邊界 → Gemini → 回覆驗證 → LINE。把框架事件、使用者訊息與業務狀態畫成不同資料，不暗示三者等價。

## 正文施工單

### 1. 只引入目前需要的 ADK 能力

列出指令、模型、執行生命週期與本階段 session 的最小用途。核對所選 ADK 世代的官方快速入門與事件介面；不要從舊版記憶拼出類別或方法。

### 2. 接回現有邊界，不讓範例成為另一套產品

重用 Day 4 的驗簽與 Day 6 的輸出驗證。由伺服器建立使用者與對話識別；不接受模型自己指定他人的 session。LINE 傳輸細節不要散落在 Agent 指令內。

### 3. 保留可替換的測試接面

以固定輸入與替身模型測試事件映射、異常與停止條件，再做經授權的真實模型回合。明定呼叫次數／時間上限，避免無界迴圈。

### 4. 解釋為何目前只用一個 Agent

比較直接模型呼叫與單一 Agent 的新增成本和收益；多 Agent 暫不需要的理由記在 ADR-006。可使用 Antigravity 或 Codex 協助重構，但只記實際使用的工具。

## 預定交付與驗收

預定：`src/agent/`、`tests/agent/`、`docs/day07/architecture.md`、`docs/day07/verification.md`。以上尚未建立。

| 案例 | 預期 | 實際結果 |
|---|---|---|
| 原有正常問句 | 經 ADK 完成回合且通過原驗證 | 未執行 |
| 偽造其他使用者／session 資訊 | 不取得其他對話內容 | 未執行 |
| 模型異常或執行超限 | 有界停止，回到明確失敗處理 | 未執行 |

保留與 Day 5 基線相同的測試輸入。框架啟動成功不等於 Agent 已能查資料或寫入。

## 查證與銜接

入口：[SERIES.md](../SERIES.md) 的 G-ADK、G-SESSION、G-STRUCTURED。前篇 [Day 6](day06.md) 定義可接受輸出，下篇 [Day 8](day08.md) 加入第一個真正的唯讀工具。
