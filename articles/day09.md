---
day: 9
planned_date: "2026-09-23"
plan_version: "2026-09-16.v1"
document_type: article_outline
status: skeleton
prerequisites: [8]
---

# Day 9｜回答要有出處：把地方資料接成可追溯的知識查詢

> 文章骨架；本篇規劃自建知識查詢，不把它宣稱為已啟用 Google Search Grounding 或其他託管服務。

## 本日任務

從 Day 8 的欄位查詢前進到「依據什麼回答」。建立來源、段落、版本與適用時間的追溯鏈；資料規模小時先採能解釋的檢索方法，必要時再用證據評估 embedding。

## 中文摘要

TODO：說明來源資料如何整理、取回並支持回答；指出「有連結」不代表連結內容真的支持該句話。

## English Summary

TODO: Design a traceable retrieval pipeline that links answer claims to permitted source excerpts and clearly distinguishes custom retrieval from managed grounding products.

## 第一張圖計畫

合成／授權文件 → 來源與版本標記 → 段落取回 → 模型回答 → 引用核對。將沒有證據的句子畫成不允許直接輸出的分支。

## 正文施工單

### 1. 為資料建立可追溯的入口

紀錄來源 ID、段落 ID、取得日期、適用日期與權利範圍。合成文件的日期與地名不能被當成真實地方資訊；更新資料時保留版本差異。

### 2. 用最小檢索基線找出證據

說明資料切分、查詢方式、候選數與找不到資料的行為。比較關鍵字／結構化過濾與語義檢索的需要，不預先宣稱某一方法必然較好。

### 3. 限制模型只能根據已取回的內容作答

傳入可引用片段與穩定識別，區分片段裡的資料與指令。禁止由模型任意生成來源 URL；可點連結須來自可信來源映射。

### 4. 檢查引用是否支持主張

自動檢查識別存在與來源範圍，人工或明確評測檢查語义支持。格式檢查不能證明句子含義正確；保存不支持、部分支持與找不到證據的反例。

## 預定交付與驗收

預定：`examples/knowledge/`、`src/retrieval/`、`tests/retrieval/`、`docs/day09/source-manifest.md`、`docs/day09/verification.md`；尚未建立。

| 案例 | 預期 | 實際結果 |
|---|---|---|
| 片段明確支持問題 | 回答連到正確片段／版本 | 未執行 |
| 模型引用不存在的來源 ID | 不通過引用驗證 | 未執行 |
| 只有部分證據或相關但不支持的段落 | 明說限制，不補造結論 | 未執行 |

使用固定的小型問答集，分開檢索命中與答案正確率，實測前不填百分比。

## 查證與銜接

入口：[SERIES.md](../SERIES.md) 的 G-FUNCTION、G-ADK、G-SAFETY；如實際新增 embedding 或 Google Grounding，先另查該官方功能並記 ADR。前篇 [Day 8](day08.md) 會查，下篇 [Day 10](day10.md) 處理資料不足、過期與衝突。
