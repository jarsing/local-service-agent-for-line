---
day: 4
planned_date: "2026-09-18"
plan_version: "2026-09-16.v1"
document_type: article_outline
status: skeleton
prerequisites: [2, 3]
---

# Day 4｜先讓 LINE 安全進門：Webhook 驗簽與最小回覆

> 文章骨架，Webhook 與實測尚未建立。今天不接模型、不做業務寫入。

## 本日任務

讓系統先判斷「這個事件可信嗎？」再解析內容。建立隔離測試頻道的最小回合，把簽章、原始請求、事件型別與回覆責任分開。

## 中文摘要

TODO：從伪造事件的風險切入，解釋驗簽先於解析／執行，以及本機 fixture 與真實 LINE 往返的證據差別。

## English Summary

TODO: Explain a signature-verified LINE webhook boundary, a minimal reply path, and the difference between synthetic request tests and a live channel check.

## 第一張圖計畫

原始 HTTP body → 簽章驗證 → 事件解析 → 支援型別判斷 → 最小回覆。未通過驗簽的支線在進入模型或工具前停止。

## 正文施工單

### 1. 建立隔離的 LINE 開發入口

確認使用測試頻道、HTTPS 入口與秘密來源；本機測試用的外部連線方式要記實際工具與設定。不得變更客戶正式 Webhook。這個臨時入口不是正式雲端部署。

### 2. 對原始內容驗簽，再做解析

依官方簽章文件與選用 SDK 核對實作，不先改寫 body。用合成 secret／fixture 測合法、竄改與缺簽事件；語法正確的 JSON 也未必可信。

### 3. 限定事件與回覆的支援範圍

只處理一種文字事件與最小回覆；明定空事件、未知事件和格式錯誤的行為。核對 reply token 的實際規則，不假設可以存起來無限重用。

### 4. 把觀測與失敗留在邊界

只記去識別事件資訊和錯誤類型；不要 log token、完整用戶內容或原始 ID。事件去重／長任務由 Day 15 深化，今天不承諾具備可靠非同步處理。

## 預定交付與驗收

預定：`src/line/`、`tests/line/`、`examples/line-events/`、`docs/day04/verification.md`；實際副檔名由 Day 3 選型決定。以上尚未建立。

| 案例 | 預期 | 實際结果 |
|---|---|---|
| 合法合成簽章＋文字事件 | 通過邊界並產生最小回覆 | 未執行 |
| body 被改一個字／缺少簽章 | 不進入業務處理或模型呼叫 | 未執行 |
| 空事件或未知型別 | 依明確契約安全處理，不崩潰 | 未執行 |

另外做一次經授權的開發頻道往返並保留去識別證據。單元測試與 live 結果分開；沒有頻道就寫未完成。

## 查證與銜接

入口：[SERIES.md](../SERIES.md) 的 L-SIGNATURE、L-WEBHOOK；回覆細則從 LINE 官方 API 參考逐條補查。前篇 [Day 3](day03.md) 建环境，下篇 [Day 5](day05.md) 才把 Gemini 接進已驗簽的事件路徑。
