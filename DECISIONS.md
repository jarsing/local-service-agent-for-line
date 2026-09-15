# DECISIONS.md — 決策與未定事項

初版：2026-09-16。這是決策紀錄，不是把建議自動升級成作者定案的機制。

狀態：`confirmed`＝有作者指示或既有 Repo 根據；`proposed`＝本次新擬、尚待實作／選定；`deferred`＝保留但不在目前範圍；`superseded`＝被後續有編號的決策取代；`working_rule`＝本次建置採用的協作規則，不表示作者已逐條簽核。`confirmed` 也不表示功能已實作。

## ADR-001｜品牌與主線（confirmed）

根據：既有 `README.zh-TW.md` 與作者本次要求。

使用 **LOCAL：30 天打造 LINE × Google AI 地方服務 Agent**；LOCAL 全大寫、不加句點。五面向原文保留，LINE 是入口、Google AI 是智慧核心。不改為虛擬同事企劃或三十篇工具介紹。

影響：`SERIES.md` 與文章需每日長出同一服務的新能力。五面向不是五個產品或固定執行順序。

## ADR-002｜以檔案接手，不依賴聊天記憶（confirmed）

根據：作者要求建立 AGENTS、SERIES、STATUS、DECISIONS、STYLE 與 Day 02–30 骨架。

規則放 AGENTS，計畫放 SERIES，現況放 STATUS，取捨放本檔，寫法放 STYLE；文章與證據各自獨立。只讀本次相關內容，不要求每次塞入全書。

影響：新對話／新 Agent 可透過檔案接續；檔案若未更新也會過時，不能宣稱這套方法保證永不遺漏。

## ADR-003｜Day 1 驗收規格不可被美化成成果（confirmed）

根據：`docs/day01/handoff-timeout-001.json` 與 README。基準 commit：`9185d18c1ce87d93574fe3fe45bb6f1e9a3617ea`。

既有案例是 synthetic_acceptance_spec：工具逾時、stored_request unknown、reply_state pending_verification、claim_completed false、以相同 idempotency key 核對／重試。不得聲稱已完成端到端測試，也不修改預期以迎合程式。

影響：Day 2 定契約、Day 14 實作故障注入、Day 21／29 回歸、Day 30 核對交付。

## ADR-004｜共同案例與 29 篇新目錄（proposed）

本次新增一條「合成服務目錄→受控人工服務請求→真人接手」主線。只讀查詢與一種寫入能力先做完整，再補記憶、介面、評測與部署。`SERIES.md` 的 2026-09-16.v1 是本次提出，並非已找回舊串定稿。

理由：使 Day 1 的案例有因果連續性，也限制 30 天範圍。替代方案「每天一個工具」不採納；多套互不相干的業務流程暫不引入。

待核對：首篇實際預告與既有未歸檔目錄。如找到作者已批准版本，列出差異後修正本案，不偷偷覆寫。

## ADR-005｜單一語言與版本基準（proposed）

先選一條語言路線；本版偏向 Python，仍須 Day 3 以使用者環境、SDK／ADK 相容性與最小可重現測試決定。套件管理器、Python 版本、Gemini API 世代、模型 ID、SDK／ADK 版本均未鎖定。

理由：避免教學中途切換語言與混用 API。文章預定路徑不指定尚未定案的副檔名。固定版本與實際模型識別要寫入環境紀錄；不得以 `latest` 當作完整重現依據。

重新評估條件：必要功能在所選版本不可用、環境確實不相容、或最小實驗失敗。先記證據，不因新工具發布就全面重構。

## ADR-006｜單一 ADK Agent＋伺服器受控工具（proposed）

Google ADK 是 README 已提出方向；具體整合方式尚未實作。先做一個 Agent，權限、確認、狀態與寫入驗證在可測試的伺服器邊界。業務後端是服務狀態的事實來源，不能由模型、摘要或 session 自行宣告完成。

替代與界線：保留基礎聊天作比較；多 Agent、MCP、向量庫與 Agent 間通信不作必備。Coding Agent／Antigravity 只協助建置，不成為使用者 runtime 的必需元件。

## ADR-007｜先本機驗證，後隔離雲端（proposed）

Day 11 定義業務儲存介面與本機持久化邊界，Day 15 定義可靠收件，Day 24 再驗證 Cloud Run＋Firestore 候選。不能把 ADK session 與業務資料庫視為同一機制；不得假造框架內建的持久化 adapter。

理由：先把正確性做成可重現測試，再驗證重啟、並發與雲端設定。憑證、地區、預算、queue 選型與權限未確認前，不自動部署或產生費用。

## ADR-008｜證據分級與發布門檻（working_rule）

作者要求可持續接手的稿件系統。本次管理規則區分骨架、初稿、實測、作者可發布核准、公開頁與平台計數。具體 enum 與定義見 `STATUS.md`。

一篇完整規格可以作為清楚標示的設計篇，但 `reviewed_design` 不能代表程式已測試。沒有作者審閱不能標 `ready`，沒有平台證據不能核對計數。這些是內部品質規則，不是假稱官方賽規。

## ADR-009｜資料、文章與品牌素材的權利（deferred）

已知作者偏好 MIT，並重視 LOCAL／作者／奇步應用名稱、來源及 Logo 的正確露出；但本次讀到的 Repo 尚無 LICENSE，README 仍標示授權未選定。

處理：保留作者偏好，不擅自建立或變更法律條款。程式／範例／工程文件與文章全文、圖片、照片、Logo、第三方資料的適用範圍，須由作者另行確認。不得把品牌露出期望默默加成標準授權的新條件。

本次五文件與骨架不構成替整個 Repo 選定授權，也不宣稱已完成權利清查。

## ADR-010｜最小改動與對外操作（working_rule）

此次只新增五份管理文件與 29 篇骨架，保留既有 README、圖片、.gitignore 及 Day 1 JSON。不新增產品程式、金鑰、部署設定、自動發文、LICENSE 或競賽成效宣稱。用獨立分支／PR 交付，不自行合併 main。

後續授權範圍以作者當次指示為準。新增需求若影響主線、時程、費用、權利或外部系統，先記入決策再執行。

## 新決策格式

```text
ADR-編號｜短名稱
日期：
狀態：proposed / confirmed / deferred / superseded
問題與證據：
採取的作法與理由：
未採用方案與代價：
影響文章／程式／測試：
驗證方法與重新評估條件：
決策者／確認依據：
取代哪個 ADR（若有）：
```

不得回寫歷史成「早就決定」；被取代的紀錄留原文與 superseded 指向。僅修字句不需新增 ADR，但行為契約變更必須可追溯。
