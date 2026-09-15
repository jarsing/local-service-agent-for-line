---
day: 26
planned_date: "2026-10-10"
plan_version: "2026-09-16.v1"
document_type: article_outline
status: skeleton
prerequisites: [21, 22, 24, 25]
---

# Day 26｜改 Prompt 也算改系統：版本、回歸與安全回滾

> 文章骨架；版本流程與回滾演練尚未完成。程式回到舊版不代表已發生的外部副作用或資料變更自動撤銷。

## 本日任務

回答「只改一句 Prompt，為什麼也可能弄壞服務？」把程式、Prompt、模型設定、資料版本與評測結果連成可追溯的變更單位。

## 中文摘要

TODO：描述小步變更、固定回歸、版本記錄與回滾邊界；用一個刻意造成回歸的測試變更展示檢查是否真的攔得住。

## English Summary

TODO: Treat prompts, model settings, code, and knowledge data as versioned system inputs, with regression gates and rollback plans that account for persistent side effects.

## 第一張圖計畫

變更分支 → 固定測試／評測 → 作者審閱 → 候選部署 → 核對 → 採用或回滾；資料與已執行操作另外標示不可直接倒轉。

## 正文施工單

### 1. 定義一個能重現行為的版本組合

記錄程式 commit、Prompt、模型識別／設定、依賴鎖定與知識版本。服務 alias 可能漂移時，保留實際回傳資訊與限制，不承諾永久完全相同。

### 2. 每次只改一個主要因素

保留變更理由與預期改善，先跑快速契約測試，再跑相關模型評測。實際 CI／工具需依現有 Repo 建立，不把 YAML 草稿當作已運作的自動檢查。

### 3. 使用既定門檻決定是否採用

Day 21 硬性門檻與 Day 23 效能預算都要檢查；不能只挑好的分數。對部署或合併需明確授權，AI 不替作者批准自己的變更。

### 4. 演練有界的回滾

區分應用 revision 回退、資料 schema 相容性、工作佇列與已執行業務。需要補償操作時另設明確流程，不靠重試或刪資料假裝從未發生。

## 預定交付與驗收

預定：`docs/day26/change-policy.md`、`docs/day26/rollback-runbook.md`、與技術棧相符的檢查流程、`docs/day26/verification.md`；尚未建立。

| 案例 | 預期 | 實際結果 |
|---|---|---|
| 小型正常變更 | 版本／理由／測試／核准可追溯 | 未執行 |
| 故意讓 Prompt 假報完成 | 回歸門檻攔下，不因語句流暢而通過 | 未執行 |
| 回退版本時仍有進行中工作 | 狀態與冪等識別保留，資料相容性有明確處理 | 未執行 |

CI 成功、評測通過與作者核准分開記錄；不自動發布 release／tag 或合併 main，除非該動作已获授權。

## 查證與銜接

入口：[SERIES.md](../SERIES.md) 的 G-EVAL、C-RUN、O-AGENTS；實際 CI、revision 與流量切換查各服務官方文件。前篇 [Day 25](day25.md) 建停止開關，下篇 [Day 27](day27.md) 用另一組合成場域檢查可移植性。
