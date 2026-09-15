---
day: 24
planned_date: "2026-10-08"
plan_version: "2026-09-16.v1"
document_type: article_outline
status: skeleton
prerequisites: [11, 14, 15, 21, 23]
---

# Day 24｜部署不是搬上雲：Cloud Run 與持久化業務狀態

> 文章骨架；Cloud Run／Firestore 是候選部署方案，尚未選定版本或實際部署。需要帳號、地區、預算與明確授權。

## 本日任務

回答「本機記得的狀態，換一個容器還在嗎？」把已測試的業務與工作狀態接到合適的持久化後端，驗證重啟、並發與外部 Webhook 的實際行為。

## 中文摘要

TODO：說明無狀態運算、持久化任務與受控工具的分工；強調部署成功與端到端通過不同，並交代尚未實測的限制。

## English Summary

TODO: Evaluate an isolated Cloud Run deployment with durable business state, explicitly separating application storage from ADK session persistence and external delivery guarantees.

## 第一張圖計畫

LINE → 經驗簽的入口 → Cloud Run 服務 → 業務儲存／可靠工作後端 → Gemini；秘密由受控配置提供。圖中標示公開入口與內部權限邊界。

## 正文施工單

### 1. 用實際條件決定最小雲端方案

確認地區、執行身分、資源限制、費用與停止方式。核對容器啟動、連接埠、請求與背景工作生命週期；不要假設 HTTP 結束後的本機背景程序必然可靠。

### 2. 實作業務儲存 adapter，不混淆 session

若採 Firestore，依官方交易與一致性語意實作 Day 11、13 的業務契約；不在可能重跑的交易函式內呼叫外部副作用。ADK session 支援另行查證，不假造通用 Firestore adapter。

### 3. 在測試專案串接入口與工作處理

只變更開發頻道，保留原設定與撤回方式。公開 Webhook 仍須驗簽；內部工具與工作端點採獨立權限。佇列、工作身分與重試設定以 Day 15 的契約驗證。

### 4. 重跑核心故障與隔離測試

部署後測正常查詢、寫入、回應遺失、容器重啟、並發重送與權限拒絕。保留 revision／程式版本與真實雲端紀錄；未成功就如實記錄阻擋，不用架構圖代替成果。

## 預定交付與驗收

預定：適合技術棧的容器／部署設定、`src/storage/`、`docs/day24/deployment.md`、`docs/day24/verification.md`；以上尚未建立。設定檔不得包含秘密。

| 案例 | 預期 | 實際結果 |
|---|---|---|
| 正常雲端回合及受控建單 | 結果與本機契約一致，可核對版本 | 未執行 |
| 重啟／多執行個體並發重送 | 原操作狀態保留，不重複副作用 | 未執行 |
| 未授權內部呼叫或公開偽造事件 | 在正確邊界拒絕 | 未執行 |

容器 build、雲端部署、健康檢查與 LINE 端到端分開記錄。沒有雲端實測只能標示設計／待部署，不宣稱已上線。

## 查證與銜接

入口：[SERIES.md](../SERIES.md) 的 C-RUN、C-TRANSACTIONS、G-SESSION、L-SIGNATURE；另查官方 IAM、秘密管理與所選 queue 文件。前篇 [Day 23](day23.md) 訂預算，下篇 [Day 25](day25.md) 驗證停止、權限與配置的最後一道門。
