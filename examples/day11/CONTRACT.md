# Day 11｜服務重啟了，剛才交代的事還在嗎？重送、背景工作與重啟恢復

## 這篇的服務契約

同一個可信服務單位／使用者／邏輯 Session，在應用行程改變之後，仍可由保存的任務參照找到原操作；已有請求回傳原單號與內容，尚未寫入則重新核對原確認與現在權限。

這個契約針對有限、明確啟動的教學 worker。不是任意聊天無縫接續、跨服務 exactly-once 或真人已接手的承諾。

## 資料模型

`local_day11_demo/{namespace}/{kind}/{sha256_id}`，namespace 僅作合成演練隔離。

| kind | 責任 | 文件識別 |
|---|---|---|
| bindings | 原 actor、四參數、payload_hash、draft_key | SHA-256(JSON[tenant,user,idempotency_key]) |
| confirmations | 原 snapshot/fingerprint、recorded_at、expires_at、execution_allowed=false | SHA-256(JSON[tenant,user,confirmation_id]) |
| requests | request_id、內容、原參數、pending_human_review | 與 bindings 相同的 operation ID |
| jobs | phase、寫入/查回次數、lease token／期限、最後結果 | operation ID |
| sessions | actor、目前 active_operation | SHA-256(JSON[tenant,user,logical_session]) |
| grants／catalogs／drafts | 測試用現在權限、採用版本、原草稿 | 各自結構化識別 |

SHA-256 用於穩定識別與相等比較，不是數位簽章。Firestore 的可信存取、登入與更新權限要由應用服務／IAM管理；本章只用合成可信入口演練。

## 首次寫入與既有回條

- 每次 create／lookup／restore／worker claim 都重新讀當前 grant 與原 binding。
- 同鍵同內容取同一列；同鍵異內容 `idempotency_conflict`。
- 同確認換新鍵 `confirmation_already_used`，不能建立另一張。
- 新的明確意圖用新確認與新鍵，文字相同也可以另建立。
- 首次寫入：原確認須 recorded、execution_allowed仍false、內容／版本／期限有效；新 gate 比對原 Day 8 指紋。
- 已建立回條：核對當前權限、actor、Session、鍵與內容，不以後來到期的確認抹掉歷史。
- 單號由交易外產生一次候選值；交易 create 固定文件路徑；同時寫入或重試不能換一個路徑另建。
- 所有交易 callback 只讀寫文件；全部 read 在 write 之前。Gemini／LINE／事件 fsync／子行程退出不在 callback 裡。

Firestore 單獨實作以上契約。沒有沿用 Day 9 SQLite 寫入當主要後端，再宣稱 Firestore 自動一致。

## 接續流程

`submit → lookup → retry → done/paused`。提前退出、查回受阻或拒絕可在各步停止。

claim 先持久化本次計數、lease 和 crash 後應做的步驟，再執行服務。每操作最多兩次 write attempt 與一次自動 lookup；每次啟動最多三步。未執行的預留可能也消耗一次預算，這是防止無限重試的保守取捨。

lease 過期後其他 worker 可以接走；finish 以目前 token 核對，舊 token 不能回寫新版進度。lease 本身不替代冪等。查回中再次 crash 可能保守停住，後續由可信入口人工查回，不自動刷新預算。

## 最小案例與對應測試

| 案例 | 預期 | 主測試 |
|---|---|---|
| 正常新行程讀回 | 相同 request_id／內容，1筆 | ProcessTests.test_all_six_cases_have_actual_different_processes |
| 提交後 crash | A有1筆；B唯讀原單，write attempts=1 | test_after_commit_lookup_does_not_write_again |
| 寫入前 crash | A=0，B查無後同鍵寫入，最終1筆 | test_before_write_lookup_then_same_key_once |
| 首次寫入時確認到期 | expired，0筆 | test_expired_first_write_is_rejected |
| 已寫入後確認到期 | 原回條可讀，1筆 | test_expired_existing_receipt_can_be_read |
| 同鍵異內容 | 拒絕、原資料不改 | test_same_key_changed_text_is_conflict |
| 同確認換鍵 | 拒絕另一操作 | test_same_confirmation_new_key_not_a_new_intent |
| 當前權限撤回 | 拒絕，不洩漏單號 | test_current_permission_rechecked_for_receipt |
| 同時提交 | 同一operation只一筆 | test_parallel_same_key_has_one_business_receipt |
| 查回受阻 | pending，沒有額外寫入 | test_lookup_outage_does_not_trigger_write |
| 舊worker完成較晚 | token不符拒絕覆蓋 | test_stale_worker_cannot_finish_newer_claim |
| 查回後另一worker先寫入 | 原鍵重送取得原回條 | test_lookup_race_with_other_writer_keeps_one_receipt |
| JSON說成功但SQLite被刪 | proof捕捉不一致 | test_proof_reads_sqlite_not_only_json_claims |
| 固定腳本模型未呼叫工具 | 整合核對失敗 | AdkTests.test_text_only_model_is_not_completion |

`contract_checks.py` 同一組業務檢查分別由 SQLiteTestStore 和真正 emulator 測；後者未執行時不借用前者的結果。callback replay 的測試是隔離模擬交易回呼重跑，沒有把它當成 Firestore 實際衝突次數。

## 證據分層

- 助理標準函式庫結果：assistant_check + SQLITE_TEST_ADAPTER。
- 作者本機：有對應原始紀錄才列 author_local。
- 真正ADK：Runner、FunctionTool及call ID，模型明標scripted。
- emulator：實際SDK連線，記CLI/JVM/SDK、project、namespace、PID和文件。
- cloud：另核准，記指定專案與實際資料；不是 emulator 的別名。
- GitHub：同一commit上原ci.yml與day11.yml各自run，不能預填remote綠燈。

不以測試總數代替模型語意、不用原Day10的163替新Day11背書、不要求為保持總數而刪測試。


## v2 交接與欄位對照

本輪以最新 DAY11_CHATGPT_PROMPT／SUMMARY 為需求，但兩份摘要所列函式名仍有差異，詳見工作包 SOURCE_ALIGNMENT.md。原碼介面不修改。

- scope：程式使用 actor.tenant_id＋actor.user_id，Session 另核對。
- timestamp／valid_until：分別保留原 created_at／receipt.recorded_at 與 expires_at，不另發或續期。
- service_id：映射原 Operation.destination；event_id 是獨立活動識別。
- sessions：只存 active_operation 與 task_reference_only；不是 ADK 原生持久化 Session 服務。
- 記憶體對照：MemoryControlStore 僅供 normal 對照，B 新建儲存即沒有原任務；不自動落回該控制組。
- Firestore 的 server SDK 使用 IAM；firestore.rules 不替代服務端的 trusted actor、grants 與交易檢核。

新增的 wrapper／錯誤分類單元測試有使用 MagicMock／本地 Exception 類別；這些列入核心，不稱為真正 Firestore 整合測試。
