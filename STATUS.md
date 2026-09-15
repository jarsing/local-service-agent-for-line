# STATUS.md — 進度、證據與下次接手

更新基準：2026-09-16，Asia/Taipei。計畫版本：2026-09-16.v1。Day 2 預定日為 9/16；每次接手按實際當地日期重新計算，不永久沿用「今天 Day 2」。

## 現況快照

作者已確認 2026-09-15 成功開賽。現有 Repo 是 Day 1 設計版本：中英文 README、總覽圖、合成驗收 JSON；尚沒有可操作 Agent、部署或效能成果。此次新增五份管理文件與 29 篇骨架，**不是新增 29 篇成稿，也不是完成產品實作**。

基準 `main` commit：`9185d18c1ce87d93574fe3fe45bb6f1e9a3617ea`。本次採獨立分支／PR 交付，不自行合併、不改動既有 Day 1 檔案。PR 與新 commit 以實際 Git 記錄為準，不預填不存在的識別。

可核對的 Day 02–30：骨架 29；完整稿 0；`ready` 0；已實測篇數 0。此數字只涵蓋本次看到的 Repo，不宣稱作者其他裝置沒有稿件。Day 1 發布依作者確認；公開 URL／平台計數尚待補存。

## 狀態定義與發布門檻

文章狀態：`skeleton` → `draft` → `review` → `ready`。`external_published` 表示作者已發布但原文尚未歸檔。需要返工可退回，不靠日期自動升級。

驗證狀態：`not_run`、`blocked`、`failed`、`verified`、`reviewed_design`。`reviewed_design` 只代表規格／設計經審查，不等於程式、真實 API 或部署通過。Day 1 現有 JSON 僅是 `spec_available`。

圖：`planned`／`ready`／`not_required`（附理由）；來源：`entry_only`／`checked`；發布：`not_recorded`／`author_reported`／`public_verified`；計數：`unverified`／`verified`。未知不填零、不冒充未發布。

`ready` 必須同時滿足：全文已完成、聲稱的實作有對應證據（或全文清楚限定為已審查的設計）、API／來源已核對、圖與程式預覽無誤、沒有 TODO 或私人資料、作者完成審閱。作者審閱人／日期留在當日證據。AI 不可自行替作者簽核。

連續庫存從下一個尚待發布的 Day 起算，遇到第一篇非 `ready` 就停止；分散在後面的成稿不算連續安全天數。目標先 3 天，再 7 天，再向 20 篇推進；目前為 0。

## 稿件與證據總表

日期是預定發文日，不是已發布時間；`entry_only` 只有查證入口，還不能宣稱各項主張已查核。

| Day | 預定日期 | 文章 | 稿件 | 驗證 | 圖 | 來源 |
|---|---|---|---|---|---|---|
| 01 | 2026-09-15 | iThome 原文待歸檔 | external_published | spec_available | Repo 總覽圖存在；文章圖待核 | 待核 |
| 02 | 2026-09-16 | [骨架](articles/day02.md) | skeleton | not_run | planned | entry_only |
| 03 | 2026-09-17 | [骨架](articles/day03.md) | skeleton | not_run | planned | entry_only |
| 04 | 2026-09-18 | [骨架](articles/day04.md) | skeleton | not_run | planned | entry_only |
| 05 | 2026-09-19 | [骨架](articles/day05.md) | skeleton | not_run | planned | entry_only |
| 06 | 2026-09-20 | [骨架](articles/day06.md) | skeleton | not_run | planned | entry_only |
| 07 | 2026-09-21 | [骨架](articles/day07.md) | skeleton | not_run | planned | entry_only |
| 08 | 2026-09-22 | [骨架](articles/day08.md) | skeleton | not_run | planned | entry_only |
| 09 | 2026-09-23 | [骨架](articles/day09.md) | skeleton | not_run | planned | entry_only |
| 10 | 2026-09-24 | [骨架](articles/day10.md) | skeleton | not_run | planned | entry_only |
| 11 | 2026-09-25 | [骨架](articles/day11.md) | skeleton | not_run | planned | entry_only |
| 12 | 2026-09-26 | [骨架](articles/day12.md) | skeleton | not_run | planned | entry_only |
| 13 | 2026-09-27 | [骨架](articles/day13.md) | skeleton | not_run | planned | entry_only |
| 14 | 2026-09-28 | [骨架](articles/day14.md) | skeleton | not_run | planned | entry_only |
| 15 | 2026-09-29 | [骨架](articles/day15.md) | skeleton | not_run | planned | entry_only |
| 16 | 2026-09-30 | [骨架](articles/day16.md) | skeleton | not_run | planned | entry_only |
| 17 | 2026-10-01 | [骨架](articles/day17.md) | skeleton | not_run | planned | entry_only |
| 18 | 2026-10-02 | [骨架](articles/day18.md) | skeleton | not_run | planned | entry_only |
| 19 | 2026-10-03 | [骨架](articles/day19.md) | skeleton | not_run | planned | entry_only |
| 20 | 2026-10-04 | [骨架](articles/day20.md) | skeleton | not_run | planned | entry_only |
| 21 | 2026-10-05 | [骨架](articles/day21.md) | skeleton | not_run | planned | entry_only |
| 22 | 2026-10-06 | [骨架](articles/day22.md) | skeleton | not_run | planned | entry_only |
| 23 | 2026-10-07 | [骨架](articles/day23.md) | skeleton | not_run | planned | entry_only |
| 24 | 2026-10-08 | [骨架](articles/day24.md) | skeleton | not_run | planned | entry_only |
| 25 | 2026-10-09 | [骨架](articles/day25.md) | skeleton | not_run | planned | entry_only |
| 26 | 2026-10-10 | [骨架](articles/day26.md) | skeleton | not_run | planned | entry_only |
| 27 | 2026-10-11 | [骨架](articles/day27.md) | skeleton | not_run | planned | entry_only |
| 28 | 2026-10-12 | [骨架](articles/day28.md) | skeleton | not_run | planned | entry_only |
| 29 | 2026-10-13 | [骨架](articles/day29.md) | skeleton | not_run | planned | entry_only |
| 30 | 2026-10-14 | [骨架](articles/day30.md) | skeleton | not_run | planned | entry_only |

## 發布與計數帳本

全體 Day 02–30 初始為 `not_recorded`／`unverified`；沒有 URL 與計數證據，不得因 commit 或日期變更而改成成功。每次真正發布都在下表新增一列，不用一個總勾選取代逐篇紀錄。

| Day | 發布狀態 | 公開 URL | 公開時間／時區 | 平台 Day 計數 | 證據／核對時間 | 稿件對應 commit |
|---|---|---|---|---|---|---|
| 01 | author_reported | 待補存 | 作者確認 2026-09-15；精確時間待核 | unverified | 作者已確認開賽；本次未取得公開頁完整證據 | 待對應；不能以 Repo commit 代替發文 |

發布後檢查：公開網址可讀、正確年度／系列、正文完整、圖可顯示、程式不被截斷、當日 Day 計數正確。不要先發空白稿再隔日補成正文。平台排程與 AI 規則以當屆官方規則為準，本次沒有設定排程或提醒。

## 目前阻擋項

| ID | 缺口 | 影響與處理 |
|---|---|---|
| U01 | Day 1 原文、精確 URL、系列 URL、末尾 Day 2 預告尚未歸檔 | 不阻擋建立骨架；Day 2 定稿前核對銜接，不重寫已發布 Day 1 |
| U02 | 語言、SDK／模型／API 世代與測試命令未鎖定 | Day 3 以最小實驗選定；未選前不填不存在的版本 |
| U03 | API／LINE 測試憑證、外部呼叫與雲端預算未在此確認 | 離線合成材料先做；不可把未知帳號狀態當成已具備或完全不存在 |
| U04 | 作者偏好 MIT，但 Repo 尚無授權檔與素材範圍說明 | 本次不改授權；有正式決定後另作受控變更 |
| U05 | 當屆完整發文／AI 使用／平台計數／排程細則未存證 | 發布前以官方與作者後台確認，不沿用未查核舊規則 |

## 本次交接與下一個任務

已做：核對既有 Repo，提出版本化 30 天地圖，建立管理規則與各篇施工骨架。沒有新增產品程式、跑真實 API、部署、發 iThome 或替作者審稿。

下一步只做 **Day 02**：讀 `articles/day02.md` 與既有 Day 1 JSON，核對首篇預告，完成能力契約、案例表與文章初稿；清楚說明是規格篇。然後再接 Day 03 的環境／技術選型與 Day 04 的 LINE 驗簽，不一次攤開全部工程。

下一次協作者交付時，用以下項目覆寫本節，而不是把整串聊天追加進來：本次範圍、修改檔案、命令與真實結果、未完成原因、需要作者決策的最少事項、下一篇的第一個動作。每次變更同步上方狀態表；來源、測試證據與狀態互相矛盾時先回查，不猜。

## 可直接交給新對話／Coding Agent 的指令

```text
請在 jarsing/local-service-agent-for-line 的工作分支，先讀 AGENTS.md、STATUS.md、SERIES.md、DECISIONS.md、STYLE.md。
這次只處理 STATUS.md 指定的下一個任務。讀對應骨架、前篇定稿與證據，先回報範圍和阻擋項，再完成最小交付。
不要重選 LOCAL 主題，不要把骨架或 mock 當成成稿／真實實測。只執行已授權的命令與外部動作。
完成後更新 STATUS.md；重大取捨記入 DECISIONS.md，列出真實測試、未完成項與下一步。不要自行發文或合併 main。
```
