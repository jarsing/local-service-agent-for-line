# LOCAL Agent Kit for LINE

> 以 LINE 為入口、Google AI 為智慧核心的地方服務 Agent 計畫。

[English](README.md)

**系列：LOCAL：30 天打造 LINE × Google AI 地方服務 Agent**  
**作者：陳佳新（佳新哥）｜GitHub：jarsing**

## 目前狀態：Day 1 設計版本

目前提供專案文件與合成驗收規格，尚未有可操作 Agent、雲端部署或效能評測成果。

預定寫作期間為 2026/09/15–2026/10/14；GitHub 提交不等於已完成 iThome 發文與當日計數。

## 品牌與五個設計面向

品牌統一使用 **LOCAL**，全部大寫、不加句點。五個字母保留以下意義：

- **L — LINE-native Interface：**LINE 服務入口。
- **O — Orchestration & Tools：**編排與受控工具。
- **C — Context & Consented Memory：**上下文、任務狀態與經同意的記憶。
- **A — Assurance & Accountability：**品質驗證、授權與責任。
- **L — Launch & Learning Loop：**部署與持續改善。

這不是五個獨立產品，也不是固定執行順序，而是 LOCAL 的設計地圖。

## 核心主張

LINE 是入口 → Google AI 是智慧能力 → 地方政府、中小企業與社群是落地現場。

**會查、會做、會記，也會說不知道。**

這是產品目標，不是已完成的功能清單。

**AI 說「完成」，不等於後端真的完成。**

以彰化為第一個示範情境，後續檢查能否替換資料與工具。只使用合成或獲授權的資料，不直接公開客戶原始碼、個資、金鑰或正式營運資料。

## Day 1 交付

合成驗收案例：`docs/day01/handoff-timeout-001.json`

使用者同意建立人工服務請求，但工具逾時，後端狀態仍未知。系統不得直接宣告完成，也不應改用新識別值盲目重建請求。

這是驗收規格，不是官方 API payload，也不是已完成的端到端測試。

## 預定技術方向

Gemini API／Google AI Studio：模型與工具行為實驗。  
Google ADK：Agent 編排與對話狀態。  
Google Antigravity：規格、程式與測試協作。  
Google Cloud：後續實作及驗證部署方案。

實際模型、SDK、框架、資料儲存與部署版本，以後續驗證紀錄為準。

## 授權狀態

本設計版本尚未選定開源授權。公開可見不等於已授予完整開源使用權；程式、文章、圖片與資料的授權範圍，會在提供重用前說清楚。
