---
day: 3
planned_date: "2026-09-17"
plan_version: "2026-09-16.v1"
document_type: article_outline
status: skeleton
prerequisites: [2]
---

# Day 3｜讓每一次實驗可重跑：建立 Google AI 開發與驗證環境

> 文章骨架；沒有預先選定或測過任何套件版本。狀態見 [STATUS.md](../STATUS.md)。

## 本日任務

回答「我的電腦跑得動，別人為什麼重現不了？」建立唯一技術基準、秘密設定與最小 smoke test，讓接下來每篇有可核對的起點。單一語言優先，Python 是候選而非既定事實。

## 中文摘要

TODO：說明版本紀錄、模型識別、環境變數與 smoke test 如何降低重現成本；清楚區分離線檢查與真正的 Gemini API 呼叫。

## English Summary

TODO: Describe a reproducible development baseline and separate local configuration checks from an authorized live Gemini API smoke test.

## 第一張圖計畫

乾淨環境 → 安裝鎖定依賴 → 載入本機秘密 → 離線檢查 → 經授權的最小 API 呼叫。圖中不出現真實金鑰。

## 正文施工單

### 1. 先做最小選型，不展開工具大戰

核對作業系統、語言版本、Gemini API 世代、SDK／Google ADK 相容性。比較必要選項後更新 ADR-005；不要混貼不同世代文件的範例。記錄執行時指定與服務回傳的模型識別，若只有 alias 就說明重現限制。

### 2. 建立可重建的環境與秘密入口

新增與所選語言一致的依賴清單和 lockfile；提供只含假值／空值的 `.env.example`。先讀現有 `.gitignore` 再最小調整，不輸出或提交秘密。

### 3. 拆開離線檢查與線上 smoke test

离線檢查版本、缺少設定時的錯誤與依賴載入；live test 只驗證最小模型回覆，不提前做工具呼叫。API 費用與憑證須有授權，失敗或未執行都留原始原因。

### 4. 讓協作工具遵守同一份規格

以 `AGENTS.md`／明確任務使用 Codex 或 Antigravity 協助產出和檢查；不要求讀者一定安裝某個 Coding Agent，也不把聊天記憶當環境設定。留下真正可執行的命令，再更新 AGENTS 的測試區段。

## 預定交付與驗收

預定新增：語言相符的 manifest／lockfile、`.env.example`、`examples/smoke/`、`docs/day03/environment.md`、`docs/day03/verification.md`。本次骨架未建立以上檔案。

| 案例 | 預期 | 實際結果 |
|---|---|---|
| 乾淨環境依文件安裝 | 依賴可載入，版本可列印與記錄 | 未執行 |
| 缺少金鑰／無效設定 | 清楚中止，不洩漏秘密或假裝通過 | 未執行 |
| 經授權的最小模型呼叫 | 保存去識別的輸入、輸出與模型資訊 | 未執行 |

證據須分開 offline／live。沒有帳號或網路時可完成部分環境工作，但 live 結果標 `blocked`；不得拿 mock 當真 API。

## 查證與銜接

入口：[SERIES.md](../SERIES.md) 的 G-START、G-ADK、O-AGENTS；實作當日核對 SDK 安裝與模型可用性。前篇 [Day 2](day02.md) 定契約，下篇 [Day 4](day04.md) 接 LINE 的安全入口。
