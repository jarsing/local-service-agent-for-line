---
day: 6
planned_date: "2026-09-20"
plan_version: "2026-09-16.v1"
document_type: article_outline
status: skeleton
prerequisites: [2, 5]
---

# Day 6｜別讓文字直接控制系統：結構化輸出與伺服器驗證

> 文章骨架；schema 是待設計的 LOCAL 契約，不是官方 payload，亦尚未測試。

## 本日任務

回答「得到合法 JSON，就能讓模型控制系統嗎？」建立回覆資料契約與伺服器驗證，將格式正確、業務正確、已授權和後端完成分成不同層次。

## 中文摘要

TODO：說明結構化輸出解决的是資料形狀的一部分，而非真實性與授權；用格式合法但宣稱未完成業務成功的反例展示差異。

## English Summary

TODO: Distinguish schema-conforming model output from semantic correctness, authorization, and verified backend state.

## 第一張圖計畫

模型輸出 → 結構檢查 → 業務／來源檢查 → 狀態核對 → 可顯示回覆；在「合法但不實」支線展示拒絕或安全降級。

## 正文施工單

### 1. 先定義下游需要哪些資訊

依 Day 2 契約設計最小欄位，例如回答內容、待釐清事項、來源參照與候選動作。區別模型可提議的值與必須由伺服器填寫的權威狀態；正式欄位命名寫入文件後才鎖定。

### 2. 讓 Gemini 產生指定結構

使用 Day 3 確認的 API 世代和支援方式，核對 JSON Schema 支援範圍。不要拼接不同 SDK 的參數，也不把「模型輸出 schema」與「工具參數 schema」混為一談。

### 3. 加上獨立的業務驗證

檢查未知欄位、長度、枚舉、來源識別、候選動作範圍。模型自帶的權限、確認或完成狀態不可信；沒有後端證據就不得渲染成成功。

### 4. 明確定義無效輸出的處理

最多做有界的修正／重問，無法通過就回到安全訊息，不能無限要求模型重新輸出。保留拒答、截斷、缺欄位與語義矛盾的差別。

## 預定交付與驗收

預定：`docs/day06/response-contract.md`、`src/contracts/`、`tests/contracts/`、`docs/day06/verification.md`；尚未建立。

| 案例 | 預期 | 實際結果 |
|---|---|---|
| 結構與業務條件都合法 | 可以進入安全回覆層 | 未執行 |
| 合法 JSON 宣稱不存在的請求已完成 | 被狀態／業務驗證拒絕 | 未執行 |
| 缺欄位、超長或拒答 | 有界降級，不觸發工具 | 未執行 |

先用 deterministic fixture 驗證契約，再做少量真實模型樣本；樣本通過不能推論所有輸出皆安全。

## 查證與銜接

入口：[SERIES.md](../SERIES.md) 的 G-STRUCTURED、G-FUNCTION。前篇 [Day 5](day05.md) 接上模型，下篇 [Day 7](day07.md) 把這個驗證邊界帶進 Google ADK。
