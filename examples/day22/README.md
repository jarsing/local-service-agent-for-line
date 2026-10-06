# Day 22｜權限、秘密與停止開關：最小特權與緊急制動

這是本次新增的**獨立 SQLite 人工停止契約示例**。不是原有 LINE handler 的改版，不是 Cloud Run 部署成果，也不是 Google IAM 或真人接手驗收。

## 本機執行

需求：Python 3.10 以上，僅標準函式庫。從包含 `examples/` 的目錄執行；完整資料包中這個目錄是 `public-files/`。

```bash
python3 -m unittest examples.day22.test_security -v
python3 -m examples.day22.circuit_breaker --demo --out out/day22/stop-demo
```

輸出目錄必須尚未存在。示例建立 `security.sqlite` 與 `REPORT.json`，不讀取 API Key，不呼叫 Google、LINE 或其他外部端點。新的示例 request_id 是合成 UUID，不能當作正式單據。

## 已實作範圍

- 初始狀態 `PAUSED`，控制狀態與 epoch 存在 SQLite。
- `admit()` 在模型呼叫前取得控制版本；`confirm()` 在寫入交易內再核對版本。
- 同一 owner／operation_key 已有紀錄時，先比對內容再讀回，暫停也不重建原單。
- 新單與 outbox 意圖在同一交易建立；注入 outbox 寫入失敗時，兩者一起回復。
- 暫停阻擋新確認、新認領、新結案與新派送許可；有權限的查單仍可用。
- 通知接受與業務狀態分開。晚到回條只改 outbox，不改 requests／claim_version。
- 已取得派送許可的工作可能在暫停後完成，不能宣稱開關撤回了已發出的請求。
- 恢復只切換控制狀態，不自動重送；原 retry key、內容與首次嘗試時間保留。
- 24 小時重試窗口屬本機替身協定測試，未驗 LINE 平台。
- 雙連線競爭、同鍵防重與志工 CAS 認領皆有自測。

## 信任邊界與整合前提

`SecurityStore.policy` 是可信設定。`subject` 必須由驗證過的 LINE 事件或受控管理入口取得，不能相信 request body 自填的身分或角色。

`confirm()` 的前提是既有確認流程已驗證本次使用者、操作內容與確認回條的綁定。`epoch` 不具備保密性，也不是授權或同意憑證。本篇指紋僅涵蓋示例的固定 `category`；擴充表單時須納入所有會影響操作的欄位，不能沿用此簡化指紋宣稱完整內容一致。

`request_snapshot()` 與 `outbox_snapshot()` 僅供內部測試。不可原樣暴露成公開查詢 API。

本地 role 表不等於雲端 IAM。程式可直接存取本地資料庫；本例不防範 Runtime 本身已遭入侵後的直接 SQL。需要更強控制權隔離時，須另設身分／服務／資料邊界。

## 與 Day 19 的關係

沿用單據、通知意圖、認領版本的責任分工，但不是把 Day 19 的 `Inbox` 包一層就完成接線。兩份 SQLite 檔案不能共同提供本篇同一交易的原子性。正式整合需明定權威原單庫、outbox、控制狀態及交易所在位置。

Cloud Run 多實例不能以實例私有 SQLite 檔案當成全體控制狀態；本例只驗本機共同資料庫，雲端需接共享儲存並重新驗收。

## 實機仍待完成

沒有 LINE sender、Webhook router、管理端點、Gemini Client、Firestore adapter、WIF 設定或雲端 IAM 政策匯出。真人雙視窗與停止／恢復整合驗收移至 Day 26；本篇保留固定驗收契約，不把 Mockup 當實機證據。

本次測試與格式結果集中保存在資料包 `evidence/verification.json`；不要以歷史 Day 19／21 的 Commit 或 CI 代替本篇結果。
