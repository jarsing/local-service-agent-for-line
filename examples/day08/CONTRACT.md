# Day 8｜一句「好」不夠：確認綁定具體操作

## 這份小規格要回答什麼？

同一個人確認的，是同一份詢問、同一版活動資料，而且仍在有效期間。核心只記錄內容確認；實際建立人工服務請求在 Day 9。

## 本篇候選的接受規則

1. 確認識別由伺服器產生；綁定 `user_id`、`session_id`、草稿 ID 與修訂版、活動 ID、目錄採用版本、操作類型、接收對象、完整詢問與畫面活動資訊。
2. `current_operation`、`current_catalog_version`、`data_status`、`permitted`、`actor` 由應用程式取得，不能照收模型或前端提供的同名欄位。
3. 接受時刻必須為 `created_at <= now < expires_at`；正好到期就拒絕。本例預設 300 秒是可調教學設定，不是平台規定。
4. 當前資料仍須為已採用狀態，目錄版本與操作指紋須符合當時展示內容。
5. 正常接受回傳 `confirmation_recorded`，保存確認收據；重複確認回傳 `already_confirmed` 與同一收據，不新增確認紀錄。
6. 舊草稿的待確認紀錄在重新出示時標成 `superseded`。改問題、改接收對象、改活動或改呈現資訊，都需要重新核對。
7. 另一人的回覆不能確認或取消這份內容；此種失敗也不替原使用者取消待辦。
8. 所有核心回覆 `execution_allowed` 均為 `false`。這份 JSON 不是可攜式執行授權；Day 9 要讀服務端紀錄並再次核對後，才能建立請求。

## 固定預期與測試接點

| 行為 | 固定預期 | 對應核心測試 |
|---|---|---|
| 內容版本相符、本人期限內接受 | confirmation_recorded | test_confirmation_records_content_not_execution |
| 目錄換版 | version_changed | test_changed_catalog_invalidates_old_confirmation |
| 問題／畫面內容改變 | content_changed | test_changed_text_requires_new_confirmation／test_changed_displayed_time_is_content_change |
| 使用者或 Session 不同 | wrong_actor | test_other_user_cannot_confirm_or_cancel／test_other_session_is_rejected |
| 恰好到期 | expired | test_expiry_at_exact_boundary |
| 目錄尚待複核 | data_pending | test_pending_source_cannot_be_confirmed |
| 明確取消後再接受 | cancelled | test_cancelled_offer_stays_cancelled |
| 同一份重複接受 | already_confirmed，收據相同 | test_repeat_returns_same_receipt |
| 授權已撤回 | not_authorized | test_revoked_permission_is_rechecked |
| 新的確認取代舊待辦 | superseded | test_reissued_offer_supersedes_previous |

## 這份核心與 ADK 整合分開驗證

核心使用 Python 標準函式庫；在 Repo 根目錄執行：

```bash
python3 examples/day08/test_confirmation.py
python3 examples/day08/demo.py
```

`demo.py` 是明確標示的合成離線資料，不呼叫模型。ADK 真實的確認事件、介面回覆、工具接續與模型文字，要由 Day 8 整合案例另外驗證；不能用這些單元測試代替。

目前實作是記憶體 store 與本行程的 Lock；重啟後資料不保留，也沒有跨行程交易。這是 Day 11 後續持久化的接點，不在這篇另建資料平台。
