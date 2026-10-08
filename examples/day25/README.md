# 公開文字抽取與本機採用

這是候選範例，尚未整合原 Day 14 的 LINE 服務。三種來源範例與模型輸出都是 Mock 模擬資料；SQLite 操作是真實本機讀寫。Gemini 真實呼叫尚未驗證。

## 安裝與本機測試

在含 `examples/` 的專案根目錄，使用獨立 Python 3.10+ 環境執行：

```bash
python3 -m pip install -r examples/day25/requirements-core.txt
python3 -m unittest examples.day25.test_ingestion -v
python3 -m examples.day25.demo --out out/day25/demo-01
```

測試含 38 項案例。輸出目錄不可已存在。測試暫存檔案只建立在 `out/day25/tests/`，結束後移除。本次參考環境的測試成功不代表其他 Python 版本均已實際測過。

## 單次模型擷取

在本機先準備一份經確認可使用的單店原文，設定 `SOURCE_URL`；來源網址只作紀錄，不會被程式開啟。

```bash
python3 -m examples.day25.capture --source-file source.txt \
  --source-id public-place-01 --source-ref "$SOURCE_URL" \
  --out out/day25/plan-01
```

預設只有計畫，`external_model_calls=0`。確認來源可以送交外部模型、帳號額度與費用限制後，準備 `google-genai==2.23.0`、在私人環境設定 `GEMINI_API_KEY`，再選新目錄執行：

```bash
python3 -m pip install -r examples/day25/requirements-live.txt
python3 -m pip check
python3 -m examples.day25.capture --source-file source.txt \
  --source-id public-place-01 --source-ref "$SOURCE_URL" \
  --out out/day25/live-01 --capture --approve-external
```

每次明確核准最多呼叫一次，SDK attempts=1、timeout=18000 ms，不自動改用其他模型。實網分支尚未在本次環境驗證。輸入超過 16000 字元會拒收；輸出上限 4096 Token，不代表固定費用。`response_schema` 使用 Pydantic 類別，`thinking_level=low`，不傳舊採樣參數。若 2.23.0 SDK 對 Schema 屬性有相容問題，保留錯誤後修正新的實驗版本，不回寫原始紀錄。

成功取得回應後，保存 SDK 物件序列化與來源雜湊；型別及原文核對通過只標 `PENDING_REVIEW`，不寫資料庫。`request.json` 是 SDK 請求的可序列化描述，不是 HTTP 原始封包。模型文字、候選資料與原始來源可能仍包含不可信內容，應以純文字方式查看，不當成 HTML 或命令執行。

## 驗證與採用

`PlaceExtraction` 驗型別與欄位關係，`validate_candidate` 比對原文，引句存在不證明語意正確。人工審閱另確認否定句、實體歸屬、飲食標籤、時段與資料時效。收據必須綁定來源、候選內容及已確認欄位。

`ReviewReceipt` 不是公開授權 API；本例的呼叫端必須是可信本機執行者。Demo 的收據是測試資料，不是有人已審閱的證據。相同內容雜湊重送只保留一筆；跨來源店家去重、撤回、最新版本選擇與時段複查效期尚未實作，不能直接用在正式店家目錄。

`search_reviewed_places` 是本機候選讀取器，沒有冒充已接線的 `search_local_places`。指定素別時明確回傳 `unsupported_filter`，不清空使用者條件來找出葷食資料。原 Day 14 的素別規則、活動資訊及固定模板需另做整合驗收。這份候選程式也沒有 Firebase、Firestore、LINE 或部署操作。
