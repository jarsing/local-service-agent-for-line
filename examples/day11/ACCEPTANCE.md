# Day 11｜驗收說明

正式章名：Day 11｜服務重啟了，剛才交代的事還在嗎？重送、背景工作與重啟恢復。

## 先判斷這次到底驗了哪一層

| 層次 | 入口 | 可支持的結論 | 不能代替 |
|---|---|---|---|
| 記憶體教學控制組 | `demo.py --compare-memory` 內的 memory-control | 新行程失去該控制組的任務參照 | Day 10 SQLite 檔案會消失 |
| 核心／SQLite 文件 adapter | `verify.py --group core` | 本篇規則、真實本機 SQLite、跨行程與負向案例 | Firestore 交易或 SDK 相容性 |
| 真正 ADK＋固定腳本模型 | `verify.py --sdk` | 前篇 19 項與本章工具介接的實際執行 | 真實 Gemini 語意、完整聊天恢復 |
| 真正 Firestore 模擬器 | `verify.py --group emulator` | 該模擬器與 SDK 下的資料讀寫、競爭、跨行程結果 | 正式 Firestore IAM、索引、配額與部署 |
| ADK＋Firestore 組合 | `demo.py --backend emulator --adk --case after_commit` | 同一個案例的 Runner、工具事件與 Firestore 文件 | 任意自然語言及 LINE 手機端到端 |
| 正式 Firestore | 明確核准後 `--backend cloud ...` | 實際專案／資料庫下取得的紀錄 | 自動等同模擬器、全部正式服務保證 |
| GitHub CI | 作者 push 後 ci.yml＋day11.yml 的 run | 同一提交中列明的測試與 artifacts | 尚未執行的 emulator、Gemini、LINE、Cloud Run |

## 對照交接指南的八個最小案例

| 要驗的事 | 代表測試／案例 | 檢查點 |
|---|---|---|
| 1. 正常建立，新行程讀回 | `normal`、`test_reopened_database_new_service_reads_original`、`MemoryComparisonTests` | 不同 PID；同一組 A／B 原單號與內容相同；B 不重發確認 |
| 2. 提交後回條遺失 | `after_commit`、`test_postcommit_crash_returns_original_row` | A exit 73；請求 1→1；B 查回原單；writes=1 |
| 3. 未寫入且確認到期 | `expired_before_write` | 請求0→0；B expired；原 expires_at 不變 |
| 4. 已寫入但確認到期 | `expired_after_commit` | 請求1→1；原確認不續期；回條歷史可讀，權限仍重核 |
| 5. 同鍵異內容／同確認換鍵 | ContractChecks 的 changed payload／wrong key／used confirmation 案例 | 拒絕結果，沒有第二份請求；原文包含空白亦不偷改 |
| 6. 同鍵同時提交 | `test_parallel_same_key_has_one_business_receipt` | 多個提交使用同一文件；只有一個 created，成功回條同一 ID；暫時受阻可保持未知，不能改稱成功 |
| 7. 查回受阻 | `lookup_unavailable`、`test_lookup_outage_does_not_trigger_write` | 已有一筆但 B 無單號；pending_verification；不新增、不把未查到當不存在 |
| 8. 前篇回歸 | 原 Day10 verifier 的 core／sdk | 144 核心與19 ADK 分開跑；未安裝 SDK 就非零、不可報163通過 |

新增正常記憶體對照：A 可以收件，A 結束後 B 沒有任何 binding/confirmation/request；只有合成授權資料重建，沒有讀取 A 的觀察匯出當接續輸入。每組各自產生單號，跨組不要求相同。

## 在作者本機跑

從包含本篇與前篇程式的 Repo 根目錄執行。`PY` 指向本篇獨立環境；尚未安裝 SDK 時，核心可直接用 python3。

```bash
python3 examples/day11/verify.py --group core --origin author_local
python3 examples/day11/demo.py --compare-memory --backend sqlite-test --origin author_local

PY=examples/day11/.venv/bin/python
$PY examples/day11/verify.py --sdk --origin author_local
# 以下先依 README 啟動真正模擬器。
export FIRESTORE_EMULATOR_HOST=127.0.0.1:8080
$PY examples/day11/verify.py --group emulator --origin author_local
$PY examples/day11/demo.py --compare-memory --backend emulator --origin author_local
$PY examples/day11/demo.py --backend emulator --origin author_local
$PY examples/day11/demo.py --backend emulator --adk --case after_commit --origin author_local
```

`--sdk` = core＋SDK，不含 emulator；`--group all` 需所有相依與模擬器均就緒。正常環境失敗不修改測試預期，也不略過後報全綠。

## 資料、事件與摘要如何互相核對

1. 以 `process-a.execution.json`／`process-b.execution.json` 的真實退出碼，確認 A 的預期中斷與 B 正常結束。
2. events.jsonl 的 PID 必須分屬真正兩個子行程；同一 pid 重建物件不算跨行程。
3. `config.json` 不能帶 A 的 request_id、四個 send_args 給 B。B 應從可信 actor 對應的 sessions.active_operation 取得 bindings。
4. 比較 A／B 的原 confirmation、期限、snapshot、execution_allowed；B 事件不得含 CONFIRMATION_STORED。
5. SQLite 路線由 proof.py **直接用 SQL 讀 after-a.sqlite3／after-b.sqlite3**，再核對 JSON 匯出。若刪資料列，檢查必須失敗。
6. Firestore 路線由父行程在子行程停止後，另用真正 SDK 讀回各集合，產生 after-a.json／after-b.json。這是逐集合觀察，**不是整個資料庫的同時間原子快照**。保留 project、database、namespace 與讀取環境；可到模擬器／正式專案另查同文件。離線匯出與其 hash 不能自己證明雲端一定存在。
7. 有 ADK 時再查 TOOL_REQUESTED／TOOL_EXECUTED／TOOL_RESPONSE 的 call ID、原四參數、回條 request_id；模型文字不當資料存在證明。
8. totals 依具名測試結果加總，套件版本、subTest 分支、同一題的多次重跑不增加獨立案例數。

## 失敗與停止

`session_not_found` 不是自動重新同意的理由。`lookup_unavailable` 不是允許另發新鍵的理由。租約到期只允許協調工作，不延長原確認，也不重設嘗試次數。

SDK 缺失、模擬器設定錯誤、服務不可用及程式錯誤，各保留非零退出紀錄。只有預期的暫時儲存錯誤轉為未知；Schema／程式錯誤須暴露，不一律吃掉。

`--group all` 的 totals 是各群組實際測試執行項目數；同一 ContractChecks 在 SQLite 與 Firestore 上重驗，要分後端列出，不當成新增使用者情境。同一套核心在乾淨環境重跑，也不重複增加本章的獨立測試數。

## 發布前驗收門檻

本機核心、真正 SDK/模擬器、遠端 CI、作者採用稿與實圖逐項登錄。尚未驗過 Firestore 時，文章只能稱設計與待驗證，不把 SQLite 對照換標為 Firestore。

本章沒有替使用者登入、LINE 接收與送達、完整聊天歷史、真人受理、Cloud Run 部署或完整 CD 取得新結果；這些也不是靠核心全綠就能自動勾選的項目。
