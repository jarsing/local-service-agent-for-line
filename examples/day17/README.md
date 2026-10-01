# Day 17｜查不到，是真的沒有，還是系統當下查不了？三種查不到與服務降級

這個模組把查詢結果分成可核對的狀態，並由 Python 產生固定文案與按鈕。它提供單回合查詢接點、SQLite 離線示範及契約測試，使用 Python 3.11 以上版本的標準函式庫，不需要模型金鑰或外部資料庫。

## 執行離線示範與測試

在含有 `examples/` 的專案根目錄執行。輸出路徑必須指向新的空資料夾；請依開發環境規則設定適合的路徑。

```bash
python3 -m examples.day17.demo --out out/day17/demo-run
python3 -m examples.day17.verify --out out/day17/verify-run
```

`demo` 逐一執行固定預約詞、查無資料、上游 503、不支援、缺少區域及成功查詢。自然語言由 `ScriptedInterpreter` 按照測試程式指定工具，不代表 Gemini 的意圖判定成果。店家、活動、偏好、服務單及事件識別值全部是離線合成資料。

`verify` 自動探索 `examples/day17/tests/test_*.py`，將實際執行計數寫入 `verification.json`，並保留 `test.log`。失敗或零項測試會以非零狀態結束。測試計數採 `unittest` 方法數；同一方法內的 `subTest` 不另加為測試數。

測試的暫存資料也集中在該次輸出目錄的 `temporary/`，由驗證入口設定 `tempfile` 的位置。

| 示範輸出 | 用途 |
|---|---|
| `demo_results.json` | 每個案例的輸入、已執行工具、結果狀態、訊息及替身呼叫次數 |
| `write_audit.json` | 業務寫入稽核、前後快照雜湊與 ledger 紀錄數 |
| `business_before.json`、`business_after.json` | 偏好與服務詢問的可讀資料快照 |
| `before.sql`、`after.sql` | 相同範圍的 SQL 快照，便於逐字比對 |
| `fixture.sqlite3` | 當次完整合成 SQLite 資料，含查詢目錄、處理紀錄及稽核表 |

## 三種結果的證據與下一步

| 結果狀態 | 判斷依據 | 呈現與下一步 |
|---|---|---|
| `no_data` | 已執行支援的查詢，可信轉換器確認條件有效、查詢完成且結果集為空 | 說明公開快照沒有符合資料，提供查詢入口與重新輸入條件 |
| `query_unavailable` | 明確的暫時性故障、目錄版本異動、工具契約失敗或未分類例外 | 說明這次暫時查不了，提供重新輸入條件與既有 `status` 查單入口 |
| `unsupported` | 確實執行 `show_local_help(reason='unsupported')`，並通過結果契約 | 說明服務範圍，提供 `d14:events`、`d14:places`、`d14:enquiry` |

`needs_area` 保留區域選擇；`help` 保留一般功能說明；`preference_changed` 維持偏好異動後不採用舊結果的訊息。這些狀態不能因資料列表為空就被改成 `no_data`。

模型只產生一段文字、沒有工具結果，會得到 `tool_contract`，不能推定為不支援。工具結果的身分、呼叫次數、偏好版本及活動目錄版本，也必須先通過核對。

## 接入既有服務

`QueryService` 不建立 HTTP 伺服器，也不送出 LINE 訊息。它回傳以下形式的訊息計畫，由既有服務保留驗證、確認流程、冪等處理、送出前偏好版本檢查與訊息傳送。

```python
{
    "messages": [...],
    "result": {"status": "no_data", "reason": "empty_snapshot", ...},
    "memory_revision": 0,
}
```

| 接點 | 契約 |
|---|---|
| `tools_factory(actor)` | 建立該回合工具；初始化失敗也在結果分類的例外範圍內 |
| `interpreter.ask(text, actor, event_id, tools)` | 完成一次工具選擇與執行；服務不採用模型自行撰寫的結果散文 |
| `query_adapter(raw)` | 依已核對的真實資料格式建立 `TrustedQueryResult`；未提供轉換器時拒絕猜測原始查詢字典 |
| `catalog_is_current(actor)` | 活動查詢必備，只有明確回傳 `True` 才採用結果 |
| `assert_revision(actor, revision)` | 有偏好版本的結果必備，版本異動時拋出指定的偏好例外 |
| `legacy_route(actor, event)` | `route()` 收到既有 postback 時交回原路由，維持原本的授權與業務處理 |
| `preference_changed_exceptions` | 注入既有專案的具體偏好例外類別，不使用廣泛例外取代 |
| `emit(event, **fields)` | 接收事件名稱、有限失敗原因、耗時與例外類別，不接收原始對話或例外全文 |

同步接點透過 `asyncio.to_thread` 執行。若資料來源不能跨執行緒使用，應提供合適的非同步接點；離線 SQLite 示範因此使用非同步的工具工廠與偏好核對函式。

`route()` 會直接接住既有精確功能詞與 `d14:help`。使用者按「稍後重新查詢」時，訊息動作送出固定文字 `重新輸入查詢條件`，接著顯示條件提示。這一步不保存或重播上一段輸入，也不重新執行上一回合可能已有作用的工具。

`route_query()` 專責可交給這條查詢分流的訊息。正式服務若還有偏好提案、記憶管理及服務詢問流程，必須保留原本的工具白名單、同意與確認規則。離線 `ScriptedTools` 只提供兩個查詢與說明工具；它不代表正式工具集合全部唯讀。

## 逾時與例外分類

服務預設以 18 秒限制一次 `interpreter.ask` 的等待範圍。呼叫內部直接拋出的 `TimeoutError` 會先轉成 `upstream_timeout`；外層等待期限才使用 `model_timeout`。取消作業期間可能超出指定秒數，因此這個數值不保證 LINE 手機端的完整回覆耗時。

已辨識的 SDK HTTP 錯誤應在接入層轉為 `UpstreamHTTPError`，資料層暫時故障可轉為 `QueryUnavailable(FailureReason.STORE_UNAVAILABLE)`。此模組不依任意例外剛好具有的 `status_code` 屬性猜測 SDK 類別。`PermissionError` 與外部取消會繼續向上傳遞。

這個模組不替 SDK 設定重試，也不修改模型或金鑰。若原呼叫層採用 `HttpRetryOptions(attempts=1)`，其中 `attempts` 包含第一次嘗試，表示沒有額外重試。既有 SDK 設定與整體 Webhook 回應期限，仍應在宿主服務核對。

## 業務寫入稽核的範圍

SQLite 的 `preferences` 與 `service_requests` 在種子資料建立後加上 `INSERT`、`UPDATE`、`DELETE` 觸發器。示範同時比對前後內容與稽核表，避免「先寫入、再改回原值」被相同快照掩蓋。測試另外執行刻意更新及新增刪除的反例，確認稽核確實能捕捉寫入。

`ledger` 由離線示範器逐案寫入處理紀錄，和業務寫入分開列示。SQLite 結果只支持列明的合成資料與執行路徑，不能推論正式 Firestore 全部沒有寫入，也不證明 Gemini 意圖準確率、LINE 手機顯示或雲端服務狀態。
