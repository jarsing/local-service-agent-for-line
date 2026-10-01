# Day 18｜20 題地方契約評測：從問句、工具到回覆，連失敗一起留下

這是接回既有 LOCAL 服務的評測程式，不是新的聊天機器人，也不是另一份 production runtime。

## 範圍與驗證狀態

題集、判分器、節奏控制與原服務接線一起提供。判分器可獨立執行；完整二十題必須在保留 Day 12～17 原始檔案的 Repo 裡執行。真實 Gemini 抽樣需另外核准外部呼叫與費用。不得把判分器自測當成二十題通過，也不得把離線腳本輸出當成模型準確率。

原程式基準：`0b9d40e8b9059edfe583bd4ea57c596946e6bc07`，Day 17 核心 `b208e160ec13b8cf19d9b4531e3333d59d3cb25b`。本章沒有新的已發布 Commit、CI 或雲端修訂版。

## 從 Repo 根目錄執行

Python 3.11 以上；沿用系列的 Python 3.13.5 環境。判分器只用標準函式庫，原服務接線仍依賴既有 FastAPI／httpx 與各篇模組。

```bash
python3 -m examples.day18.verify_eval --validate-only
python3 -m examples.day18.verify_eval --self-test
python3 -m examples.day18.verify_eval --out out/day18/offline-001
```

每次使用新目錄。完整整合若需要安裝原服務測試相依套件，在原本隔離虛擬環境安裝 `examples/day12/requirements-core.txt`，不要改全域 Python。正式套件版本與環境管理沿用前篇。

`--validate-only` 只查二十題結構。`--self-test` 查判分器與限流器，不呼叫舊服務；其測試計數是 unittest 方法數。無此參數才執行情境。

結束狀態：0 表示所選題沒有 FAIL/BLOCKED，1 有 FAIL，2 有 BLOCKED。部分選題即使狀態為 0，報告的 `all_twenty_passed` 仍為 false；未選題不會消失。完整離線 CI 必須使用預設全部二十題，不傳 `--case`。

## 檔案分工

| 檔案 | 用途 |
|---|---|
| `eval/local20.json` | 固定的 A10+B10 開發契約題集；不是 ADK 原生 EvalSet |
| `dataset.py` | 題號、數量、Schema、資料效果預算與事前等價值驗證 |
| `scoring.py` | 工具、後端、訊息計畫三層斷言；另外標示需求完整度 |
| `local_adapter.py` | 呼叫原 `DocumentApplication.route`，使用隔離 SQLite、既有工具與 formatter |
| `restart_probe.py` | 子行程 A 寫入退出，子行程 B 重開同 DB 讀回；不是雲端重啟實測 |
| `gate.py` | 同時工作數、發送間隔、外部請求上限；不自動重試 |
| `live_adapter.py` | 既有 `BudgetAdkInterpreter` + 真實 Gemini，附請求節奏控制 |
| `test_eval.py` | 評分器反例自測，使用明示的合成觀察資料 |
| `verify_eval.py` | 離線／Live 入口、固定二十分母、報告與 manifest |

## 三層與觀察範圍

1. 工具層同時看提出和執行；Live 還核對 request／execution／response 的相同 ID 與名稱。腳本路由只驗契約，不宣稱意圖準確率。
2. 後端層以原 SQLite `docs` 表的觸發器及前後快照查 `requests`、`consented_preferences` 兩種文件集合。事件帳本、context 與 catalog 另外列示。
3. 介面層驗的是送出前的訊息計畫。這次接線直接呼叫 `route()`，沒有驗簽 HTTP、Reply API 或手機送達。不能拿此分數當 LINE 端對端成功率。

A02 的合法同意與忘記在準備階段。A03 第一次確認在準備階段：首次新增一筆；第二次才開始零新增觀察。A04 先建立兩筆不同請求，再確認舊卡不能改掉新任務。A06 的故障是實際本機提交後，由測試程式模擬未收到回條；沒有製造真實網路故障。A07 確實啟動不同子行程，但不證明 Cloud Run 或 Firestore。A08 撤權前先取得合法記憶提案卡，撤權後嘗試同意寫入，預期 PermissionError；不把驗簽失敗 401 混進這個斷言。

A05/B20 走既有 `讀文件：` 路由，腳本主動要求未授權工具，檢查原 DocumentTools callback 與資料層。這不是證明模型一定識破攻擊，也不是把整段惡意文字當成本人授權。

B15 預設注入實際的 0.01 秒 `asyncio.wait_for`，報告保留秒數；前篇 runtime 的 18 秒設定不被改動。需求可指定 `--injection-seconds 18` 做慢速等待測試。這不證明 Webhook 在兩秒內 ACK。

成功店家與區域追問沿用原 renderer，所以實際狀態仍是 `places_ok`／`places_needs_area`；正常活動為 `events_result`。本章不為了統一報表改動線上狀態。精確「我要預約」是 `help`，非固定口語預約才走 `unsupported`。

## 複合需求怎麼評

第十九題用 `show_local_help(reason=unsupported)` 符合既有單工具與能力範圍時，安全契約可通過。`coverage_requirements` 另檢查營業資訊限制、預約限制、下一步三項文字訊號，漏項列 `NEEDS_REVIEW`，不自動判成模型意圖錯誤。

這個完整度檢查是事前指定片語的出現與否，不是自然語言理解的完整語意評審。改文案時可人工核對後修訂片語集，保留題集版本；不要偷偷放寬預期來取得高分。

## 真實 Gemini 抽樣：另行核准後才執行

先沿用既有 `examples/day12/requirements.txt` 的固定模型環境，確認 `google-adk==2.9.1`、`google-genai==2.23.0`。金鑰由執行環境的 `GOOGLE_API_KEY` 或 `GEMINI_API_KEY` 取得，不寫進程式、報告或命令。

以下是**會產生外部呼叫及可能費用**的命令，不是日常離線驗證：

```bash
python3 -m examples.day18.verify_eval --mode live \
  --approve-external --case local13 --case local17 --case local19 \
  --max-model-calls 3 --max-count-calls 12 \
  --concurrency 1 --interval 2 \
  --out out/day18/live-001
```

以上上限是人工設定，不是實測數據，也不是每分鐘配額保證。必須先由操作者核准題號與上限。其他十七題在這份 Live 報告中是 NOT_RUN，不能寫成「Live 20 題」。適用 Live 題號由 JSON 明列；故障注入、固定入口與多步純後端題不灌進模型命中率。

`LimitedGemini` 沿用真實 `Gemini.generate_content_async`，不新增分類 prompt；countTokens 與生成請求共用節奏閘門及各自呼叫預算。模型設定與原回呼保持不變：Developer API、原 MODEL_ID、temperature=0、max_output_tokens=512、thinking LOW、attempts=1。遇到錯誤不自動重試，冷卻後用新輸出目錄跑另一輪。沒有背景排程。

原 BudgetAdkInterpreter 只要看到 `model_override` 就標為 ADK_SCRIPTED。本接線覆寫的是會真的呼叫 API 的受控 Gemini 子類，因此保留 `base_mode`，另外標記 `LIVE_GEMINI_WITH_REQUEST_GATE` 及 transport 來源；仍需以實際請求數、用量與 trace 核對，不只相信 mode 字串。

`reports.local.json` 僅作本機受限觀察。雖然本題集使用合成測試者與輸入，仍不要把整個 `out/`、SQLite、確認卡 token 或 trace 直接提交 Repo。公開證據先作欄位白名單與遮蔽。

## 報告不是一張滿分證書

`REPORT.md` 與 `results.json` 同時保留二十題、三層結果、完整度與缺漏。`run_manifest.json` 記錄實際來源檔雜湊、可取得的 Git SHA、套件版本與設定。離線 model_accuracy 為 null；未回傳 usage 也為 null，不以 0 美化成本。

題集是公開開發基準，不是保留測試集。二十題通過不代表所有地方輸入都通過，也不代表真人已受理。後續五十題、一百題是規劃目標。
