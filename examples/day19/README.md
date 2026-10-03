# Day 19｜志工真的接到單了嗎？最小真人通知與收件匣閉環

本目錄是新加入的隔離教學範例，尚未接入既有 LINE handler。使用 Python 標準函式庫；沒有實際 LINE HTTP sender、Firestore adapter、背景排程或管理 UI。

## 本機執行
```bash
python3 -m unittest examples.day19.test_inbox_contract -v
python3 -m examples.day19.inbox_contract --out out/day19/first-run
```
請從Repo根目錄執行，輸出路徑必須尚不存在。`REPORT.json` 的 origin 為 `SQLITE_OFFLINE_FAKE_SENDER`，`network_calls=0`。

## 主要介面與責任
- `Inbox.register_confirmed(request_id, owner_ref, category, recipient_ref)`：匯入已確認單的交接投影。呼叫者必須先核對來源原單、同意與擁有者；它本身不查現行服務DB。
- `set_volunteer()`：測試授權名單，不是公開註冊端點；正式權限管理需獨立保護。
- `claim()`：授權與條件UPDATE同一SQLite交易，確認version與未認領；成功為True，競爭失敗為False。
- `resolve()`：再次核對授權及claimant；只表示內部結案登錄，不自動通知LINE或驗證線下處理。
- `user_status()`：以owner_ref限制查詢，不回傳volunteer私人識別。
- `dispatch()`：使用持久化retry_key與固定payload。交易外呼叫注入sender；接受回條後補帳，不將已認領案件降回等待通知。

`notification_accepted` 是本範例對原 `notification_delivered` 的較窄命名提案。API接受、手機看到、人工claim是不同證據。

## 該測與尚未測
測試包含同號異內容、授權、舊版本、兩個執行緒和兩個SQLite連線競爭、晚到通知回條、重啟查回、送出後回條遺失與24小時後停止盲送。FakeSender保存的是替身接受紀錄；不宣稱網路只發送一次，也不保證正式跨實例／通道 exactly-once。

## 接回真實服務的必要條件
1. 保留原request_id，先讀原單確認狀態，再做冪等匯入；不要在原單確認交易中發LINE。
2. 真實sender須核對HTTP與通道回條；同鍵同內容重試、409去重回應與逾時不確定性分開處理。超時效先對帳。
3. 正式Firestore交易另驗。SQLite內交易不代表跨資料庫原子提交。
4. 從已驗簽事件／管理者session取得真實caller，不能信任Postback傳來的身分。
5. 非本人案件與撤權者一律拒絕；通知不帶未必要原句和電話；原單詳細資訊需另授權。

官方參考：[LINE retry](https://developers.line.biz/en/docs/messaging-api/retrying-api-request/)、[Firestore transactions](https://docs.cloud.google.com/firestore/native/docs/manage-data/transactions)、[SQLite transaction](https://www.sqlite.org/lang_transaction.html)。
