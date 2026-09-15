# SERIES.md — LOCAL 30 天施工藍圖

版本：2026-09-16.v1。日期採 Asia/Taipei；Day 1＝2026-09-15，Day 30＝2026-10-14。

**這是依現有 Day 1 Repo 新擬的 Day 02–30 規劃，不是宣稱已找回舊對話完整目錄，也不是已完成的文章或功能。** 目前 `main` 基準 commit 為 `9185d18c1ce87d93574fe3fe45bb6f1e9a3617ea`；現況與發布證據見 `STATUS.md`。

## 1. 主線、讀者與完成形狀

正式名稱：**LOCAL：30 天打造 LINE × Google AI 地方服務 Agent**。

讀者定位（本版編輯建議）：懂基本程式與 HTTP／JSON，希望把 LINE Bot 從回答問題提升為可驗證服務的開發者。文章先交代問題，再展示工程選擇與證據，不用地方故事掩蓋技術內容。

共同示範是**合成地方服務目錄＋人工服務請求**：找服務→核對來源→釐清需求→確認操作→受控建立請求→核對後端→必要時交接真人。彰化是起始情境，不暗示真實政府單位或客戶已採用；只以合成或獲授權資料示範。

終點是一個有程式、測試、重現文件與清楚限制的 Google AI／LINE 示範作品；不是 30 個獨立工具、完整商用 SaaS、金流／預約大全或災害應變平台。

## 2. 保留 Day 1 的語言與契約

- **L — LINE-native Interface**：LINE 服務入口。
- **O — Orchestration & Tools**：編排與受控工具。
- **C — Context & Consented Memory**：上下文、任務狀態與經同意的記憶。
- **A — Assurance & Accountability**：品質驗證、授權與責任。
- **L — Launch & Learning Loop**：部署與持續改善。

這五項跨篇交織，不強迫各占六天，也不是執行順序。

核心句：「會查、會做、會記，也會說不知道。」是產品目標；「AI 說『完成』，不等於後端真的完成。」是待實作驗證的工程原則。既有 `docs/day01/handoff-timeout-001.json` 保持不變，Day 14 將它接成測試，Day 21、29、30 再核對。

## 3. 範圍與技術門檻

Repo 已提出 Gemini API／Google AI Studio、Google ADK、Google Antigravity 與 Google Cloud 的方向，但尚未鎖定語言、SDK、模型、資料庫或部署版本。

本版建議先走單一語言、單一 Agent、小型合成資料與明確工具契約。Python 是候選，不是已批准或已存在的實作；Cloud Run／Firestore 是後段候選。Day 3 與 Day 24 須各自完成選型與驗證，記入 `DECISIONS.md`。不混用 Gemini API 世代或不同 ADK 版本，不憑記憶填方法名稱。

優先完成只讀查詢、有效確認、一次受控請求、逾時核對與可重現測試。多 Agent、MCP、向量資料庫、語音、付款與多租戶後台只在真的解決必要問題時才提出變更，不為展示工具而加入。

前期本機／隔離開發頻道的測試，不等於 Day 24 的雲端部署；部署與真實外部呼叫須另有帳號、預算及授權。

## 4. 30 天地圖

Day 1 已由作者確認開賽，但本次未取得 iThome 首篇全文及精確 URL；其文章標題、末尾預告與計數待補存。不得重新生成一份 Day 1 冒充已發布稿。下表 Day 02–30 全部是本版規劃。

| Day | 日期 | 文章／規劃標題 | 必要前置 |
|---|---|---|---|
| 01 | 2026-09-15 | 既有系列起點：以 iThome 原文與 Day 1 JSON 為準 | — |
| 02 | 2026-09-16 | [先定義什麼叫完成：LOCAL 的能力邊界與驗收契約](articles/day02.md) | 01 |
| 03 | 2026-09-17 | [讓每一次實驗可重跑：建立 Google AI 開發與驗證環境](articles/day03.md) | 02 |
| 04 | 2026-09-18 | [先讓 LINE 安全進門：Webhook 驗簽與最小回覆](articles/day04.md) | 02、03 |
| 05 | 2026-09-19 | [讓 LINE 接上 Gemini：第一個只讀對話回合](articles/day05.md) | 03、04 |
| 06 | 2026-09-20 | [別讓文字直接控制系統：結構化輸出與伺服器驗證](articles/day06.md) | 02、05 |
| 07 | 2026-09-21 | [用 Google ADK 組成第一個單一 Agent](articles/day07.md) | 03、05、06 |
| 08 | 2026-09-22 | [讓 Agent 真的會查：受控的地方服務查詢工具](articles/day08.md) | 02、06、07 |
| 09 | 2026-09-23 | [回答要有出處：把地方資料接成可追溯的知識查詢](articles/day09.md) | 08 |
| 10 | 2026-09-24 | [不知道不是失敗：過期、衝突與資料不足的回覆策略](articles/day10.md) | 06、09 |
| 11 | 2026-09-25 | [對話記得，不等於任務完成：拆開 Session、任務與後端狀態](articles/day11.md) | 07、08、10 |
| 12 | 2026-09-26 | [一句「好」不夠：把使用者確認綁定到具體操作](articles/day12.md) | 06、11 |
| 13 | 2026-09-27 | [讓 Agent 會做事：建立可核對的人工服務請求](articles/day13.md) | 08、11、12 |
| 14 | 2026-09-28 | [逾時不等於失敗：讓 Day 1 的驗收案例真正跑起來](articles/day14.md) | 01、11、12、13 |
| 15 | 2026-09-29 | [LINE 重送也不能重做：事件去重與非同步工作邊界](articles/day15.md) | 04、11、14 |
| 16 | 2026-09-30 | [工具有能力，不代表有權限：Prompt Injection 與最小權限](articles/day16.md) | 08、09、12、14、15 |
| 17 | 2026-10-01 | [記憶必須經過同意：可查看、可撤回的偏好資料](articles/day17.md) | 11、12、16 |
| 18 | 2026-10-02 | [對話變長怎麼辦：只帶必要上下文，不遺失任務狀態](articles/day18.md) | 11、14、17 |
| 19 | 2026-10-03 | [讓使用者看懂狀態：LINE Flex Message 與安全操作](articles/day19.md) | 06、12、14、15、18 |
| 20 | 2026-10-04 | [交給真人也要交代清楚：人工接手的資料與回執](articles/day20.md) | 14、16、17、19 |
| 21 | 2026-10-05 | [不只看回答順不順：建立 LOCAL 的回歸評測集](articles/day21.md) | 10、14、16、17、20 |
| 22 | 2026-10-06 | [錯在哪裡要查得到：可觀察性與最小稽核紀錄](articles/day22.md) | 14、15、16、21 |
| 23 | 2026-10-07 | [速度與成本一起看：為地方服務訂下效能預算](articles/day23.md) | 18、21、22 |
| 24 | 2026-10-08 | [部署不是搬上雲：Cloud Run 與持久化業務狀態](articles/day24.md) | 11、14、15、21、23 |
| 25 | 2026-10-09 | [上線前最後一道門：秘密、權限、配額與停止開關](articles/day25.md) | 16、17、22、24 |
| 26 | 2026-10-10 | [改 Prompt 也算改系統：版本、回歸與安全回滾](articles/day26.md) | 21、22、24、25 |
| 27 | 2026-10-11 | [換一個地方也能用嗎：用第二組合成場域驗證可移植性](articles/day27.md) | 09、16、17、21、26 |
| 28 | 2026-10-12 | [別人真的跑得起來嗎：乾淨環境重現與文件驗收](articles/day28.md) | 03、21、25、26、27 |
| 29 | 2026-10-13 | [LOCAL 比基礎聊天多了什麼：端到端證據與取捨總驗收](articles/day29.md) | 05、14、21、23、27、28 |
| 30 | 2026-10-14 | [從 30 篇文章到可交接的 LOCAL：成果、限制與下一步](articles/day30.md) | 01–29 |

## 5. 階段交付與備稿節奏

| 階段 | 要多長出的能力 | 不能跳過的證據 |
|---|---|---|
| Day 01–07 | 從驗收規格到 LINE × Gemini／ADK 的第一個回合 | 規格審查、版本紀錄、驗簽、正常與失敗回覆 |
| Day 08–14 | 從會查到能受控寫入、核對未知結果 | 引用、有效確認、後端紀錄、Day 1 逾時回歸 |
| Day 15–20 | 重送、權限、同意記憶、可理解介面與人工接手 | 故障注入、隔離、撤回、狀態與真人回執邊界 |
| Day 21–26 | 從零散測試到評測、觀察、雲端與變更流程 | 固定評測集、實測紀錄、部署驗證、停止與回滾演練 |
| Day 27–30 | 可移植、可重現、可交接 | 第二合成場域、乾淨環境、端到端比較與公開證據索引 |

先處理 Day 02–04，再完成 Day 05–07；後續以 3–5 篇為一批。維持至少 3 天、目標 7 天的**連續可發布庫存**，再往 20 篇目標推進。這是工作目標，不是目前已有的存稿數；不沿用沒有證據的完成期限。

文章骨架、完整初稿、已驗證、作者核准可發布、已在 iThome 公開、平台計數已核對，是不同狀態。到期日以外的其他個人行程不寫入公開 Repo；只提前保護忙碌日期。

若技術受阻，先修最短關鍵路徑與縮小非必要功能。設計篇可以提供真正完整且經審閱的規格，但必須標示尚未實作；不能發布空白骨架或把待測寫成通過。要換題／調序，先列出下游依賴再更新本表。

## 6. 逐篇交付規則

每篇骨架包含：本日新增能力、必要前置、問題、設計、預定交付檔案、正向／反向案例、驗證方法、限制、配圖計畫、來源與前後銜接。預定檔案路徑不是已存在資產。

程式集中維護共用 `src/`、`tests/`、`examples/`；需要時才建資料夾，不每天複製整份程式。當日證據規劃放 `docs/dayNN/verification.md`，圖放 `assets/dayNN/`。每次證據須帶執行版本／commit、環境、命令、輸入、預期、實際、判定及已知限制；官方格式與 LOCAL 內部格式分開標示。

每日驗證→作者審稿→發布 iThome→開公開頁檢查正文／圖／程式／系列→核對 Day 計數→回填 `STATUS.md`。GitHub commit 不是 iThome 發布，自動排程也不能未經查核當成成功。此 Repo 不含自動發布設定。

## 7. 官方查證入口

以下是 2026-09-16 建稿時的查證起點，不表示每篇技術主張都已核對或測試。已能讀取的文件只提供方向，實作時要重查使用的 API 世代、SDK／模型相容性及具體限制。Cloud Run 容器契約已取得，完整部署、權限與費用仍待實作日逐項核對。引用請補上實際章節、支持的主張與查證日期。

| ID | 官方入口 |
|---|---|
| G-START | [Gemini API：Getting started](https://ai.google.dev/gemini-api/docs/get-started) |
| G-STRUCTURED | [Gemini API：Structured outputs](https://ai.google.dev/gemini-api/docs/structured-output) |
| G-FUNCTION | [Gemini API：Function calling](https://ai.google.dev/gemini-api/docs/function-calling) |
| G-ADK | [Google ADK 官方文件](https://adk.dev/) |
| G-SESSION | [Google ADK：Sessions](https://adk.dev/sessions/session/) |
| G-MEMORY | [Google ADK：Memory](https://adk.dev/sessions/memory/) |
| G-EVAL | [Google ADK：Evaluation](https://adk.dev/evaluate/) |
| G-SAFETY | [Google ADK：Safety and Security](https://adk.dev/safety/) |
| L-SIGNATURE | [LINE：Verify webhook signature](https://developers.line.biz/en/docs/messaging-api/verify-webhook-signature/) |
| L-WEBHOOK | [LINE：Receive messages](https://developers.line.biz/en/docs/messaging-api/receiving-messages/) |
| L-FLEX | [LINE：Send Flex Messages](https://developers.line.biz/en/docs/messaging-api/using-flex-messages/) |
| C-RUN | [Cloud Run：Container runtime contract](https://docs.cloud.google.com/run/docs/container-contract) |
| C-TRANSACTIONS | [Firestore：Transactions and batched writes](https://docs.cloud.google.com/firestore/native/docs/manage-data/transactions) |
| O-AGENTS | [OpenAI：Custom instructions with AGENTS.md](https://developers.openai.com/codex/agent-configuration/agents-md) |

賽事細則查證入口：[2026 iThome 鐵人賽活動頁](https://ithelp.ithome.com.tw/2026ironman/event)。本次未取得完整細則，AI 使用、每日計數、時區邊界及定時發布規則不得自行補造；由作者可見的當屆規則／後台證據補存。文件中的備稿門檻是內部流程，不是假稱官方規定。

## 8. 本次來源界線

已讀：`README.zh-TW.md`、Repo 目錄與 `docs/day01/handoff-timeout-001.json`，基準 commit 如頁首。作者已明確確認開賽，這項事實保留；「首篇原文／URL 尚未存入本 Repo」不等於懷疑作者未開賽。未取得舊串完整 30 天目錄，所以新增規劃使用本版號，待與公開 Day 1 預告核對後再鎖定逐日標題。
