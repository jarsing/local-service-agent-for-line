---
day: 2
planned_date: "2026-09-16"
plan_version: "2026-09-16.v1"
document_type: article_outline
status: skeleton
prerequisites: [1]
---

# Day 2｜先定義什麼叫完成：LOCAL 的能力邊界與驗收契約

> 文章骨架，不可直接發布。這篇預定是規格篇；以下交付與審查尚未完成。全系列進度以 [STATUS.md](../STATUS.md) 為準。

## 本日任務

延續 Day 1 的「AI 說完成，不等於後端真的完成」，回答：LOCAL 到底承諾完成什麼，又有哪些事不能做？把產品語言轉為可檢查的輸入、狀態、證據與禁止行為。今天不介紹一排工具，也不假裝已經有 Agent。

## 中文摘要

TODO：用 100–180 字說明「會查、會做、會記」各自需要什麼證據，並以人工服務請求逾時為例，帶出未知結果不得宣告完成。全文限定為設計與合成驗收規格。

## English Summary

TODO: Explain the proposed service contract, distinguish replies from verified backend outcomes, and identify timeout reconciliation as a design requirement rather than a completed feature.

## 第一張圖計畫

合成使用者需求 → LINE 入口 → Google AI 建議 → 伺服器驗證 → 後端證據 → 狀態回覆。用不同責任區塊表示「建議不等於執行」；圖說標示設計圖，不是現成部署。

## 正文施工單

### 1. 先限定一個地方服務案例

使用合成服務目錄與人工服務請求，定義查詢、釐清、確認、建立、核對、交接六個動作。排除付款、真實政府流程、完整預約與災害應變；不要讓案例擴成另一個大型產品。

### 2. 對每項能力寫下驗收契約

列出輸入、必要資料、身分與權限、可用工具、完成證據、失敗回覆。不把自然語言「好」視為所有後續動作的概括授權；把本次新設計欄位標成 LOCAL 自訂格式。

### 3. 把成功、失敗與未知分開

引用既有 `docs/day01/handoff-timeout-001.json`，逐項解釋 `pending_verification`、`claim_completed: false` 與相同冪等識別的作用。不要更改原案例或聲稱其已測試通過。

### 4. 定義三十天的最小完成形狀

用能力／證據矩陣連到後續篇章：Day 8 查詢、Day 12 確認、Day 13 寫入、Day 14 核對、Day 17 同意記憶。技術品牌與框架只是手段，不是完成條件。

## 預定交付與驗收

預定新增：`docs/day02/service-contract.md`、`docs/day02/acceptance-cases.json`、`docs/day02/verification.md`。這些檔案目前尚不存在。

| 審查案例 | 預期契約要求 | 實際結果 |
|---|---|---|
| 資料齊全、權限與確認有效 | 每個動作對應可觀察的後端證據 | 未審查 |
| 工具逾時、寫入結果未知 | 不宣告成功或失敗；使用原識別核對 | 未審查 |
| 要求超出範圍或缺少授權 | 不執行；說明限制或要求釐清 | 未審查 |

先檢查每個預期是否可被反例推翻，再由作者審阅。JSON 可解析只代表語法正確；規格一致性審查才可記 `reviewed_design`，仍不是程式測試。

## 查證與限制

查證入口見 [SERIES.md](../SERIES.md)：G-FUNCTION、G-SAFETY。核對模型提議工具與應用程式執行的責任；本文狀態機與欄位屬於自己的設計，不冒充官方標準。

阻擋定稿：先取得 Day 1 原文的結尾預告並核對銜接；無法取得時保留未知，不重寫首篇。下篇 [Day 3](day03.md) 將契約帶進可重跑的開發環境。
