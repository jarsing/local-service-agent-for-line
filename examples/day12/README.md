# Day 12｜換了雲端行程，剛才交代的事還在嗎？第一個 Cloud Run 版本

本文已於 iThome 鐵人賽正式發布：[Day 12 文章連結](https://ithelp.ithome.com.tw/articles/10417489)

目標：使用者在 LINE 查詢 → 提出詢問 → 點原確認卡 → Firestore 保存 → 換 Cloud Run revision／新行程後查回同一單。不是預約或真人已受理的系統。

## 先讀哪份？

[架構與資料流](ARCHITECTURE.md)

## 範圍與真實資料

Day 5 搜尋核心、Day 8 確認型別／指紋、Day 11 prepare/create/lookup/restore_session 直接重用；Day 12 的延後 postback 同意、LINE 事件狀態與雲端入口是新程式。

預設仍是 Day 9 花壇歷史教學快照（2026-09-19）。資料只有活動地點與時段，沒有集合點；不能替它補出集合承諾。要更新為目前可參加的活動，必須由作者先提供採用資料與來源。

資料隔離前綴 `day11-d12-...` 是沿用舊 validator，不是把此篇誤認 Day 11。服務資料在外部 store；沒有把 SQLite 與 Firestore 雙寫。

## 1. 先跑不呼叫外部 API 的核心

從含有前篇的 LOCAL Repo 根目錄操作。使用獨立環境，不升級 Day 11 的既有環境。

```bash
python3 -m venv examples/day12/.venv
PY=examples/day12/.venv/bin/python
$PY -m pip install -r examples/day12/requirements-core.txt
$PY -m pip check
$PY -m examples.day12.verify --group core --origin author_local --out /tmp/local-day12-core-01
$PY -m examples.day12.demo --out /tmp/local-day12-two-processes-01
```

輸出目錄須尚不存在，避免覆寫前次 evidence。45 項是本次候選的具名核心／ASGI 測試；數量依實際程式與結果記錄，不為湊數修改。

這些測試以 FastAPI TestClient 執行 ASGI，模擬 LINE 事件、StubQuery 與 ReplyRecorder，真的寫 SQLite；**不是網路 HTTP listener、LINE API、Gemini、Firestore 或 Cloud Run 實測**。

`demo.py` 另啟動兩個獨立子行程，B 只拿資料庫設定與新 status 事件；它不讀 A 的輸出。第二種演練在 A 已 commit、發送前 `os._exit(73)`，B 仍查原單。父行程以真正 SQLite SQL 查 a.sqlite3/b.sqlite3，比原 request/operation ID 與筆數。

## 2. SDK 候選與本機模擬器

```bash
$PY -m pip install -r examples/day12/requirements.txt
$PY -m pip check
$PY -m pip list --format=json > /tmp/local-day12-installed-packages.json
$PY -m examples.day12.verify --group adk --origin author_local --out /tmp/local-day12-adk-01
```

此群組必須有真正 ADK／GenAI 才會執行。3 項候選測試包含實際 Runner 工具往返、純文字假完成的拒絕、Gemini retry 參數介面；缺相依回非零，不能報綠燈。

Firestore 模擬器依 Day 11 指南啟動，保留真實 project／host 設定：

```bash
export FIRESTORE_EMULATOR_HOST=127.0.0.1:8080
$PY -m examples.day12.verify --group emulator --origin author_local --out /tmp/local-day12-emulator-01
```

兩項新測試只驗「延後同意後建單／查回」與「未同意不寫入」，不將 Day 11 的 59 項重跑算成本篇新增情境。缺 server 不回退 SQLite。

## 3. 服務與設定

`env.example` 是設定格式。以 Repo 外的私人檔載入，不要把 real user ID／secrets 放進 Repo。正式 cloud 路線須 `LOCAL_APPROVE_EXTERNAL=yes`；在 Cloud Run 有 K_SERVICE 時，程式會拒絕 sqlite-test 或 stub 模式。

主要命令：

```bash
# 已載入本次私人設定；此命令會建立尚不存在的 grant/catalog，需作者核准。
$PY -m examples.day12.admin seed --approve-seed
# 前景服務，不在回 200 後發動背景建單。
$PY -m uvicorn examples.day12.main:app --host 0.0.0.0 --port 8080 --workers 1 --no-access-log
```

本機手動服務使用 LineReply，會真的呼叫 LINE API；它不是上面的 TestClient。沒有真實頻道與核准就只跑核心／模擬器測試。

`GET /healthz` 不讀資料庫。`POST /webhook` 先驗原 bytes，再驗 destination／使用者／資料庫授權。不提供 /kill、/seed、任意 request 查詢等公開管理路由。

## 4. 真實 Google AI 的用途

一般查詢把原句交給 ADK／Gemini，模型產生 date/area/keyword，Day 5 search_catalog 執行，手機展示核對過的工具欄位。它不是用規則產生參數卻說由 Gemini 決定。

本篇有意不將模型的最後文字直接當成單號或服務承諾。完整模型原文仍保存到私人 line_traces，供語意判讀。查原單、確認與取消採確定性路由；不為每個按鈕多付一次模型呼叫。

日常 CI 沒有真實 API key，也不應以失敗重跑直到模型剛好說對。真實實驗先定回合上限與資料，保留不利結果。

## 5. 標準回覆／新意圖

「需要協助：原文」建立待確認內容。點確認卡才批准；裸字好只引導回原卡。「查詢原單」讀目前任務。「新需求：原文」才明確建立另一件事。此最小版綁定一個花壇教學案例，不是任意需求路由系統。

使用者自己的 request_text 可能包含私人資訊；僅白名單合成測試，事前告知保存目的。原始 query trace 與reply plan存在該隔離 namespace，清理方式與保留期間由作者確認。

## 6. 測試與相依版本

Day 12 提供可在本機執行的核心 ASGI 測試（45 項）與 ADK 離線測試（3 項）；各組項目與結果以實際執行報告為準。目前公開 GitHub Actions 仍執行 `ci.yml` 與 `day11.yml` 的前篇回歸，尚未自動納入本篇 45／3 項。
