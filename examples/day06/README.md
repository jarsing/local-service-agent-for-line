# LOCAL Day 6｜從活動海報到服務資料

一張本機海報 → Gemini 圖片理解與結構化欄位 → 人工核對 → Day 5 搜尋工具。

本篇把 `time`／`venue`（活動資訊）與 `meeting_time`／`meeting_point`（集合資訊）分開保存，並用 `value`、`quote`、`status` 記錄模型整理的欄位。`source` 與來源更新時間由程式取得操作者提供的資料，與擷取時間分開。

## 1. 從 Repo 根目錄開始

已有 Day 5 環境時可沿用，先檢查：

```bash
examples/day05/.venv/bin/python examples/day06/verify.py --sdk
```

新讀者可另建本篇環境，以下後續指令的直譯器路徑相應改為 `examples/day06/.venv/bin/python`：

```bash
python3 -m venv examples/day06/.venv
examples/day06/.venv/bin/python -m pip install -r examples/day06/requirements.txt
examples/day06/.venv/bin/python -m pip check
examples/day06/.venv/bin/python examples/day06/verify.py --sdk
```

Python 3.10 以上，範例的 SDK 為 `google-genai==2.23.0`。本篇多模態擷取不另載入 ADK，資料查詢會使用同一個 Repo 的 `examples/day05/catalog.py`。

`verify.py` 的單元測試使用離線資料；`--sdk` 再載入真正的 SDK 型別，檢查圖片 Part、response schema 組態與回覆轉換，沒有網路呼叫。`counterexample.json` 是刻意換錯集合時間的合成反例，與真實 Gemini 輸出分開。

## 2. 選擇圖片與來源

準備可使用且無須公開個資的 PNG、JPEG 或 WEBP 海報，本例檔案上限 6 MiB。第一輪以一張清楚的單一活動海報為主，最好能分辨活動日期、時段與集合資訊。圖片沒有無障礙說明也很好，正好觀察未知欄位。

圖片本身未附在 Repo；可使用自己的活動海報，或取得適當使用權的素材。用 `--source-ref` 記錄原始網址或來源名稱。原公告有更新時間才填 `--source-updated-at`，沒有就省略；不要以本次擷取時間代填。

## 3. 執行同圖雙提示比較

以 `GEMINI_API_KEY` 環境變數或 Repo 外的 `--env-file` 提供既有金鑰：

```bash
examples/day05/.venv/bin/python examples/day06/run.py --live \
  --image /實際路徑/poster.jpg \
  --source-ref "海報原始網址或來源識別" \
  --env-file /實際私人路徑/gemini.env \
  --origin author_local
```

預設兩次呼叫：`baseline`（一般提示）、`guided`（欄位提示）。兩組使用同一張圖片、同一模型與 schema，只有提示文字不同。每次上限 8,192 output tokens、HTTP 60 秒、SDK attempts=1；API 錯誤停止批次，原始結果保留。單組重跑用 `--condition baseline` 或 `--condition guided`，會另建 run；文章比較要列清楚真正採用的兩次紀錄。

SDK 參數採 v2.23.0 README 的 `response_mime_type`＋`response_json_schema`，API 維持 GenerateContent。`--model` 可指定其他已確認相容模型，變更要記錄新的條件；預設沿用系列的 `gemini-3.8-flash` 與 `LOW`。

輸出預設為 `output/day06/run-.../`，可用 `--output` 改位置：

| 檔案 | 用途 |
|---|---|
| `verification.json` | 圖片、程式雜湊、提示、模型版本、兩組原文、欄位及用量 |
| `response_baseline.txt`、`response_guided.txt` | 兩組實際文字 |
| `source.jpg`／`source.png`／`source.webp` | 本次送出的原圖位元組 |
| `REPORT.html` | 本機看圖、比較與人工核對介面 |

`EXTRACTED` 是本例的模型回覆及結構檢查狀態，人工核對在下一步。

## 4. 在瀏覽器核對

打開 `REPORT.html`，看左側原圖與右側結果。下方核對介面從 `guided` 組開始：修改欄位時，同時修正 `value`、`quote`、`status`，留下修改原因。填寫核對者及心得，勾選確認，再按「選擇核對起點並儲存 review.json」。它是本機頁面，不需開網站伺服器。

核對檔在瀏覽器的下載資料夾。使用下載檔的實際位置：

```bash
examples/day05/.venv/bin/python examples/day06/review.py \
  --run output/day06/實際擷取資料夾 \
  --review-file /實際下載路徑/review.json
```

程式核對圖片和執行紀錄雜湊，另存 `catalog.reviewed.json`、`review.json`、`review.audit.json`。模型原文維持原樣。若原圖年份、場地或集合資訊仍不清楚，保留 null，再於來源確認時補充；只有活動名稱是建立搜尋目錄所需的欄位。

## 5. 沿用 Day 5 的工具查詢

```bash
examples/day05/.venv/bin/python examples/day06/query.py \
  --catalog output/day06/實際核對資料夾/catalog.reviewed.json \
  --keyword "海報上的活動名稱"
```

省略條件時，用第一筆活動名稱作為搜尋關鍵字；也可指定 `--date YYYY-MM-DD` 或 `--area 彰化市`。結果與程式／資料版本保存於新資料夾的 `query.json`。這一步是本機 Python 查詢，API 呼叫為零。

Day 5 的 `load_catalog` 限定合成教學資料，所以本篇採 `reviewed_poster_data` 的新載入入口，重用原本 `make_search_tool` 與比對邏輯。Day 6 介接補齊其他未知欄位清單，`updated_at` 沒有來源時維持 null；Day 5 程式與資料都保持原樣。

本篇尚未將新目錄接進正在服務的 LINE Bot。今天展示的是資料管線與既有工具的接點，後續可沿用同一資料格式接回 Agent；不必重建已完成的入口。

## 問題定位

| 狀況 | 先檢查 |
|---|---|
| `SDK BLOCKED` | 目前直譯器能否匯入 google.genai、Pydantic 版本及 SDK 組態錯誤 |
| `SCHEMA_ERROR` | 報告的欄位位置、原始文字；不把解析錯誤修掉後冒稱模型原文 |
| `RESPONSE_INCOMPLETE` | 結束原因、圖片清晰度、場次數與輸出上限 |
| 來源或紀錄雜湊不符 | 核對頁與 review.json 是否來自同一份 run |
| 查不到活動 | 查詢條件與已核對的日期／地區；未知日期先按活動名稱查 |
| 顯示 `null` | 檢查 status 和原圖，分清圖片沒寫與看不清楚 |

## 參考

- [圖片理解（GenerateContent）](https://ai.google.dev/gemini-api/docs/generate-content/image-understanding)
- [結構化輸出（GenerateContent）](https://ai.google.dev/gemini-api/docs/generate-content/structured-output)
- [GenAI Python SDK v2.23.0](https://github.com/googleapis/python-genai/tree/v2.23.0#json-response-schema)
- [前篇搜尋工具](../day05/catalog.py)

## 和 Day 5 發布稿接續

搜尋函式沿用 Day 5 程式版本 `59265ab`。本日資料另加 `meeting_time`（集合／報到時間）與 `venue`（活動場地），`time` 保留活動時段，來源更新日可為 null。`query.py` 重用的是 Python 搜尋邏輯；Day 5 的合成目錄與 Agent／LINE 回覆保持原樣。

兩組提示都可在報告裡選為人工核對起點，`review.audit.json` 保存 `selected_condition` 與欄位差異。一般提示組若比較合適，直接選它即可；兩組相同則保留這個觀察。模型摘錄的 quote 是核對線索，最後仍對照原圖。
