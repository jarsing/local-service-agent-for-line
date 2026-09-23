# Day 9｜按兩次送出，會不會多一筆？受控建單與冪等

## 這份契約要回答什麼

已確認的同一件事重送，取回同一張請求；同鍵異內容不改寫原單。Google ADK 負責提出與執行工具的往返，後端決定是否真的保存。

## 入口

`create_handoff_request(idempotency_key, confirmation_id, request_text, event_id, tool_context=None)`

模型只提供四個業務欄位；Actor 與權限由應用端提供。冪等鍵在準備確認時由應用端配置並保存綁定。本例四參數均精確比對，不移除空白、改字或語意合併。

## 接受與拒絕

| 前置條件／案例 | 固定預期 | 測試接點 |
|---|---|---|
| 已明確確認、本人、內容版本相同、期限內、目前有權限 | `request_created`，資料庫一筆 | `test_first_creation_persists_pending_human_request` |
| 同鍵同內容重送 | `already_created`，同單號同回條，仍一筆 | `test_replay_returns_same_request_without_insert` |
| 同鍵異內容 | `idempotency_conflict`，原單原樣 | `test_same_key_changed_text_conflicts_and_preserves_row` |
| 尚未確認 | `unconfirmed_operation`，不替使用者改成已確認 | `test_unconfirmed_is_not_implicitly_approved` |
| 首次寫入恰好到期 | `expired`，無新資料 | `test_exact_expiry_blocks_first_insert` |
| 寫入之前資料換版／待核 | `version_changed`／`data_pending` | 對應 `test_catalog_change_before_creation_requires_confirmation`／`test_pending_catalog_blocks_new_creation` |
| 當前草稿已變 | `content_changed` 或輸入不符的 `content_mismatch` | `test_current_server_draft_change_is_detected` |
| 同鍵已建立，確認後來到期 | 有當前權限時只讀原回條 | `test_committed_replay_after_expiry_is_read_only` |
| 權限已撤回 | `not_authorized`，不給回條 | `test_permission_rechecked_for_receipt_lookup` |
| 不同使用者／Session | 不給另一人的資料；Session 不符回 `wrong_actor` | `test_wrong_user_cannot_create_or_read_receipt`／`test_wrong_session_cannot_read_existing_receipt` |
| 六個獨立 DB 連線同時送同鍵 | 一個新建、五個原單、共一筆 | `test_concurrent_same_key_commits_one_request` |
| 另一個新確認，即使文字一樣 | 可以建立另一張新的請求 | `test_new_confirmed_intent_with_same_words_can_create_a_new_request` |

狀態文字只是可核對的結果；模型的說法不能代替 DB 回條。沒有 `human_claimed` 的真人受理流程，本篇結果中它保持 false。

## 寫入規則

- `BEGIN IMMEDIATE` 把查重與新增放進同一筆 SQLite 寫入交易。
- UNIQUE(tenant_id,user_id,idempotency_key) 與 UNIQUE(tenant_id,user_id,confirmation_id) 共同限制重複。
- `payload_hash` 比較工具送來的參數；`operation_fingerprint` 保存 Day 8 完整操作指紋。
- 查回既有單時仍檢查當前身分／權限／Session；它回的是歷史回條，不把新目錄改寫進舊單。
- Day 8 確認規則仍走原 `decide`；Day 9 必須先確認狀態已為 confirmation_recorded，避免由建單工具代人同意。
- gateway 所有變更共用單行程鎖，首次核對至寫入提交在鎖內；不是跨行程／跨系統交易。

## 模型驗證

`test_adk_offline.py` 檢查真實 ADK 的工具可見 schema、Session 身分、首次／重送事件、輸入篡改與未呼叫工具的假成功。`run.py` 另保存同次工具參數／回傳ID／回條／資料列與模型原文；語意判讀由作者留下。

## 明確後續

本篇沒有注入網路逾時、啟用 CI、通知真人或部署。Day 1 `handoff-timeout-001` 原檔保持不變；Day 10 在這個建單接點上驗證逾時與查回。
