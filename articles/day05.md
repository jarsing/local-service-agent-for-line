---
day: 5
planned_date: "2026-09-19"
plan_version: "2026-09-16.v1"
document_type: article_outline
status: skeleton
prerequisites: [3, 4]
---

# Day 5｜讓 LINE 接上 Gemini：第一個只讀對話回合

> 文章骨架；以下實作與結果未完成。只做無外部寫入能力的基線聊天。

## 本日任務

把安全入口與模型接起來，得到能作後續比較的最小基線。回答「會說話與會辦事差在哪裡？」本日不把模型生成的地方資訊當作已查證資料。

## 中文摘要

TODO：介紹 LINE → Gemini → LINE 的最小只讀回合，展示正常輸出與上游失敗，並說明這還不是能代辦服務的 Agent。

## English Summary

TODO: Introduce a read-only LINE–Gemini baseline with explicit failure handling and no claim that generated answers are verified local information.

## 第一張圖計畫

已驗簽事件 → 最小模型適配層 → 回覆整理 → LINE。標示本階段「沒有工具、沒有寫入、沒有長期記憶」。

## 正文施工單

### 1. 定義基線的工作與不工作範圍

先用合成問句與無需即時地方知識的測試。遇到要求建單或預約時，不聲稱已完成；說明目前能力不足。保存這個版本供 Day 29 對照，不為了比較而故意弱化它。

### 2. 讓模型與 LINE 之間有可測試的接面

依 Day 3 鎖定版本做單次呼叫，將輸入大小、輸出整理與錯誤映射集中處理。定義保守的時間預算，不在本篇假設所有模型回覆都趕得上 LINE 的限制。

### 3. 處理模型沒有正常回答的情況

測空輸出、拒答／安全阻擋、上游逾時、配額或網路錯誤。只對安全且有界的條件考慮重試，不把错误訊息與憑證直接丟給使用者。

### 4. 留下第一份可比较的回合紀錄

記模型版本、設定、請求時間、可取得的用量資訊與輸出；未提供的值標 unavailable，不估成零。終端或 LINE 截圖必須来自真實測試且去識別。

## 預定交付與驗收

預定：`src/model/`、`tests/model/`、`examples/baseline/`、`docs/day05/verification.md`。這些路径尚未建立。

| 案例 | 預期 | 實際結果 |
|---|---|---|
| 簡單合成問句 | 完成可觀測的只讀回合 | 未執行 |
| 「幫我建立服務請求」 | 不捏造已寫入或已受理 | 未執行 |
| 模型逾時／空輸出 | 有界等待與清楚降級回覆 | 未執行 |

適配層可用 stub 測錯誤，再於授權下做真實模型與 LINE 往返；兩種證據不能混算。

## 查證與銜接

入口：[SERIES.md](../SERIES.md) 的 G-START、L-WEBHOOK；核對當前回覆限制、模型錯誤與用量欄位。前篇 [Day 4](day04.md) 是入口，下篇 [Day 6](day06.md) 將不受控文字轉成需要驗證的結構化輸出。
