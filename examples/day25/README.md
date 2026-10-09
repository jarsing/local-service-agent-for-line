# Day 25｜Gemini 結構化輸出抽取地方資料：從公開文字到服務資料庫

本目錄提供地方非結構化文本抽取至本機服務資料庫之參考實作。三種來源範例與模型輸出提供 Mock 模擬資料；五題真實 Gemini 3.8 Flash 實測與人工審閱成果公開於 `evidence/live/`；SQLite 操作為真實本機讀寫。尚未整合原 Day 14 的線上 LINE 服務。

## 安裝與本機測試

在含 `examples/` 的專案根目錄，使用獨立 Python 3.10+ 環境執行：

```bash
python3 -m pip install -r examples/day25/requirements-core.txt
python3 -m unittest examples.day25.test_ingestion -v
python3 -m examples.day25.demo --out out/day25/demo-01
```

測試含 47 項案例（全數通過，涵蓋型別出處核對、決策雜湊防偽與重跑覆寫防護）。輸出目錄不可已存在。測試暫存檔案只建立在 `out/day25/tests/`，結束後自動移除。

## 單次模型擷取與五題實測

在本機先準備一份經確認可使用的單店原文，設定 `SOURCE_URL`；來源網址只作紀錄，不會被程式開啟。

```bash
python3 -m examples.day25.capture --source-file source.txt \
  --source-id public-place-01 --source-ref "$SOURCE_URL" \
  --out out/day25/plan-01
```

預設只有計畫，`external_model_calls=0`。確認來源可以送交外部模型、帳號額度與費用限制後，準備 `google-genai==2.23.0`、在環境中設定 `GEMINI_API_KEY`，再選新目錄執行：

```bash
python3 -m pip install -r examples/day25/requirements-live.txt
python3 -m pip check
python3 -m examples.day25.capture --source-file source.txt \
  --source-id public-place-01 --source-ref "$SOURCE_URL" \
  --out out/day25/live-01 --capture --approve-external
```

每次明確核准最多呼叫一次，SDK attempts=1、timeout=18000 ms，不自動改用其他模型。輸入超過 16000 字元會拒收；輸出上限 4096 Token。設定採用 `response_json_schema=PlaceExtraction.model_json_schema()`、`response_mime_type="application/json"`、`thinking_level="low"`，不傳舊採樣參數。

五題實測執行入口為 `examples.day25.run_live`，實測請求、回應與計量數據完整保存在 `examples/day25/evidence/live/`。

## 人工審閱與入庫

模型文字通過 `validate_candidate` 僅標記為 `PENDING_REVIEW`，不直接寫入資料庫。操作者審閱候選後記錄於 `review_decisions.json`，再透過 `--review` 產生綁定雜湊之 `ReviewReceipt` 授權入庫：

```bash
python3 -m examples.day25.run_live --out examples/day25/evidence/live --review
```

`ReviewReceipt` 綁定來源雜湊、候選雜湊與已審閱欄位。相同內容雜湊重送只保留一筆；跨來源店家重複過濾、撤回與時段複查效期留待後續擴充。

`search_reviewed_places` 是本機候選讀取器。指定素別時明確回傳 `unsupported_filter`，不清空使用者條件來找出葷食資料。原 Day 14 的素別規則、活動資訊及固定模板需另做整合驗收。
