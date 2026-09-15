---
day: 19
planned_date: "2026-10-03"
plan_version: "2026-09-16.v1"
document_type: article_outline
status: skeleton
prerequisites: [6, 12, 14, 15, 18]
---

# Day 19｜讓使用者看懂狀態：LINE Flex Message 與安全操作

> 文章骨架；Flex Message 與畫面尚未建立。設計圖必須標示為設計稿，不能當作真實 LINE 實測截圖。

## 本日任務

回答「後端還在核對，為什麼畫面卻顯示成功？」把狀態、文字與操作按鈕綁到同一份伺服器資料，避免漂亮介面掩蓋未知或未完成。

## 中文摘要

TODO：展示查詢、待確認、待核對與請求已建立的視覺差異；說明按鈕只是操作入口，每次仍需重新核對伺服器狀態。

## English Summary

TODO: Render truthful task states through deterministic LINE Flex templates, with safe actions, current-state checks, and text fallbacks.

## 第一張圖計畫

權威狀態 → 固定模板 → 狀態卡片／文字替代 → 使用者動作 → 伺服器重新核對。將「待核對」與「已建立」並列，避免都使用成功語意。

## 正文施工單

### 1. 定義狀態與介面的一對一對應

使用 Day 6 契約和 Day 14 狀態，不讓模型直接生成任意 Flex JSON、URL 或已完成標章。狀態文案明確區分建立請求、通知送出與真人接手。

### 2. 建立可驗證的固定模板

只把經驗證的欄位插入模板，限制字數、連結目的地與必要資訊。提供可理解的替代文字，重要結果不能只靠顏色或圖片傳達。

### 3. 按鈕不能跳過安全邊界

確認、取消與重新查詢使用伺服器操作參照；點擊舊卡片時重查權限、版本與有效期限。即使客戶端能改 postback 內容，也不能因此執行未授權操作。

### 4. 在真實客戶端檢查，不只驗 JSON

核對不同文字長度、缺欄位與錯誤回覆。使用官方驗證／預覽工具和開發頻道測試，標明實際測過的裝置／版本；不能宣稱所有客戶端均一致。

## 預定交付與驗收

預定：`src/presentation/`、`tests/presentation/`、`examples/flex/`、`docs/day19/verification.md`；尚未建立。

| 案例 | 預期 | 實際結果 |
|---|---|---|
| 正常查詢與已建立請求 | 顯示與後端一致的狀態及可核對識別 | 未執行 |
| 待核對或通知失敗 | 不渲染為業務成功／真人受理 | 未執行 |
| 過期卡片、竄改參照與長文字 | 重新驗證／安全拒絕；版面有退路 | 未執行 |

模板驗證、伺服器動作測試與真實 LINE 顯示分開留證；只做預覽時不能標成端到端已通過。

## 查證與銜接

入口：[SERIES.md](../SERIES.md) 的 L-FLEX、L-WEBHOOK、G-STRUCTURED；查官方 postback、訊息限制與驗證端點。前篇 [Day 18](day18.md) 組装上下文，下篇 [Day 20](day20.md) 完成人工接手的資料與狀態交接。
