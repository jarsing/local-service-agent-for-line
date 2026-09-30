# Day 16｜傳單裡偷藏指令，系統真的會照做嗎？不可信文件與最小權限

LOCAL 的文件閱讀分流只暴露三個唯讀工具，並在 ADK callback 與實際執行入口各自驗權。
既有本人確認、建單、偏好更正／忘記不重寫，也不因這個功能被停用。

> English summary: Day 16 adds a read-only document path to the same LOCAL service.
> The model receives only three query/help tools. A deterministic execution policy
> and read-only transaction view remain effective without callbacks. A synthetic
> flyer, intentional forbidden-call probes, SQLite triggers and before/after
> snapshots separate attempted actions from executed side effects. Real ADK,
> Gemini and LINE/cloud validation are separate evidence layers.

## Five-minute offline reproduction

在包含前篇的 Repo 根目錄執行；Python 3.13.5 為本包重現環境：

```bash
python3 -m examples.day16.demo --out out/day16/first-run
```

輸出目錄必須尚未存在。只讀取附帶的合成文字，不擷取網站、不讀郵件或私人資料。
使用標準函式庫與真正本機 SQLite；不呼叫 ADK、Gemini、countTokens、LINE 或 Firestore。

`seed()` 先準備合成授權、已同意 vegetarian、既有示範單據與短期脈絡，再啟用寫入探針。
測試程式直接送三個禁用工具名稱，然後實際查詢花壇店家。這不是模型攻擊成功率測試。

| 檔案 | 用途 |
|---|---|
| `untrusted_flyer.txt` | 原始合成攻擊樣本；與來源雜湊核對 |
| `harness-probes.json` | 明標 TEST_HARNESS_NOT_MODEL 的三個刻意拒絕 |
| `scripted-read.json` | 組裝請求、離線工具契約、callback／工具事件 |
| `sqlite-write-audit.json` | SQLite trigger 寫入紀錄；會捕捉寫入後還原 |
| `before.rows.json`、`after.rows.json` | 直接從 SQLite 讀取資料，不是模型文字 |
| `before.sqlite3`、`after.sqlite3` | 可重新 SQL 核對的備份 |
| `report.json` | 索引，包含觀測範圍與四個零，不單獨當證明 |
| `MANIFEST.sha256.json` | 附帶檔案的 SHA-256 |

四個零是：`dangerous_tool_schemas_exposed`、`dangerous_tool_executions`、
`database_writes`、`business_rows_changed`。離線 schema 值僅來自 contract fixture，
**不是 Google SDK 實際送出的 schema**；真正 SDK 的 pre-model config 另外測。
`document_text_in_request=true` 只表示原文保留於請求組裝，`real_model_document_seen=null`。
三個越權嘗試應存在並被拒絕；不能為了得到零而把 attempts 也藏起來。

## Runtime: one service, explicit route

新入口 `examples.day16.main:app` 繼承 `BudgetApplication`：

- `LOCAL 文件測試`：讀取附帶合成 flyer。
- `讀文件：` 後接文字：最多 800 字／3,200 bytes；本回合問題由伺服器固定提供。
- 其他正常訊息與 postback：沿用 Day 15／14／13 的原流程。

文件裡的 `m14:forget`、`新需求：` 等文字不重新解析為命令，不重播進 Day 15 歷史。
不提供圖片 OCR、任意 URL 下載、Shell、SQL、網路傳輸工具。圖片仍需作者依前篇
流程抽出文字，並將所有外來內容標為文件。文字前綴是應用路由，不是模型可修改的 mode。

正常 LINE 請求仍會寫 `line_events` 與 `line_budget` 等必要執行資料。
**所以整條 Webhook 不聲稱零資料庫寫入**；runtime 測試另比較非執行中繼資料的
業務文件與 conversation_context，保留防重送、當日模型額度與 Reply 前版本再核對。
文件閱讀不新增 collection，原資料庫／namespace／簽章鍵不搬移。

## Exact tool capability and independent authorization

Only:

```text
search_local_events(date, area, keyword)
search_local_places(area, dietary_type, keyword)
show_local_help(reason)
```

實作不是反射 `getattr(name)`、動態 import 或任意工具轉送。`read_functions()` 回傳
固定三個函式；`check_declarations()` 再檢查實際 pre-model config 沒混入其他能力。
模型產生未註冊工具名稱時，after-model gate 拒絕整批；不要聲稱未註冊工具一定會
觸發 before_tool_callback。多工具回合也在執行前拒絕，保留前篇一回合一業務工具限制。

`ReadPolicy.authorize()` 驗綁定脈絡、工具、額外欄位、值型別與目前授權／版本。
`DocumentTools.before_tool()` 是 ADK callback；`execute()` 不假定 callback 已跑過，
會獨立再驗。`PreferenceReader` 不提供 approve/forget/propose 或 signing key。
唯讀 Store／Transaction 介面拒絕 writable atomic／put／create。這些是可信 Python
應用的能力限制，不是防 Python reflection 的作業系統隔離或新的 Firestore IAM 身分。

使用原 Day 14 `TurnTools` 與目錄：當次明示優先，長期偏好只補空缺；原函式前後皆
再讀目前權限與偏好版本。資料來源未知仍維持未知，不把合成店家當正式餐廳。

## Tests by layer

先沿用自己的前篇虛擬環境，不因這包自動升級：

```bash
PY=examples/day12/.venv/bin/python
$PY -m examples.day16.verify --group all --origin author_local --out out/day16/all-01
$PY -m examples.day16.verify --group previous --origin author_local --out out/day16/previous-01
```

`core` 為 stdlib／SQLite；`flow` 為真正 FastAPI＋SQLite、腳本模型與 LINE sender 替身。
`previous` 涵蓋 Day 12～15 指定群組。不是完整公司系統測試，更不是模型品質分數。
驗證報告寫入指定輸出目錄；測試暫存改用系統暫存位置，避免建置上下文誤落 Repo 內。測試數採實際 runner 結果，重跑不累加。

真正 ADK 與真正 Firestore 模擬器入口：

```bash
$PY -m examples.day16.verify --group adk --origin author_local --out out/day16/adk-01
# 依 Day 11 指南在另一終端機啟動模擬器後：
export FIRESTORE_EMULATOR_HOST=127.0.0.1:8080
$PY -m examples.day16.verify --group emulator --origin author_local --out out/day16/emulator-01
```

ADK 組使用真 Runner＋腳本 BaseLlm，檢查真工具宣告、未知名稱、callback 拒絕、
同一 call ID 與不把純文字成功聲明當回條。不是 Gemini 理解能力。
模擬器組只使用 `demo-local-day16`、隨機 `day11-d16-*` 命名空間，無 production 選項。
缺套件／前置環境以非零結束，不能改成 skip 後宣稱通過。

## One approved real Gemini turn

固定 `gemini-3.8-flash`／`LOW`／`google-genai==2.23.0`／`google-adk==2.9.1`。
首次作者同意送出合成文件與付費 API 後才執行：

```bash
export GEMINI_MODEL=gemini-3.8-flash
$PY -m examples.day16.live_check --approve-live --out out/day16/live-01
```

只建立合成 SQLite；不接正式 Firestore 或 LINE。最多一次生成、四次 countTokens，
失敗即停，不重試到成功。保存真 pre-model config／contents、回傳工具要求、執行與
回傳 ID、usage、耗時、SQLite trigger／快照。callback 快照不是網路封包側錄。

`security_contract_observed` 與 `normal_query_observed` 分開。若模型只回 help，
不能寫成正常查詢已由這一次真模型證明。若模型要求危險工具但未執行，保留
`model_requested_forbidden > 0`；安全目標是 executions=0，不保證 attempted calls=0。
若輸入未送出或 SDK 未啟動，不准填「Gemini 讀到惡意文字」。

## Cloud Run / LINE author acceptance

先完成本機、真 SDK 與必要 live 驗收。沿用 Day 15 的 project、region、service、Runtime SA、
Secret Manager 與 `LOCAL_ACTOR_KEY`。保留 `LOCAL_APPROVE_COUNT_TOKENS=yes`，
`Settings` 中每日模型上限繼續生效。程式回復不會回復偏好資料。

```bash
$PY -m examples.day16.build_context --out "$BUILD_CONTEXT"
```

`BUILD_CONTEXT` 是作者核准工作區的新空目錄。只匯出 allowlist，入口必須是
`examples.day16.main:app`。建置與部署依既有 Cloud Shell 路徑由作者操作；本包沒有
執行建置、建立 revision 或推送 GitHub。建置 context 是雲端 Gemini 模式用，非測試映像。

手機先記錄既有偏好／單號 → 發送 `LOCAL 文件測試` → 查看目前偏好／原單 →
另按真正的詢問確認卡，驗正常建單仍只一筆。正式紀錄勿含 raw user ID／secret／token。
手機圖片只能支持顯示結果；資料庫不變還需自己的同時間資料讀取與操作紀錄。
不要在 production 安裝本包 SQLite triggers；它們只供 synthetic demo。

## CI and publication state

`.github/workflows/day16.yml` 執行離線測試與 artifact 保存，沒有業務 API keys、live 模型或自動部署。
Day 16 文章已正式刊登於 [iThome 鐵人賽](https://ithelp.ithome.com.tw/articles/10419112)；公開 CI 通過 core 37、flow 12、adk 8、previous 300 項測試。
公開 Repo 不包含私人策略、交接、未去識別化紀錄與 assistant_check 內部檔案。

## References

- [Gemini function calling](https://ai.google.dev/gemini-api/docs/function-calling)
- [ADK tool callbacks](https://adk.dev/callbacks/types-of-callbacks/#before-tool-callback)
- [ADK safety](https://adk.dev/safety/)
- [Cloud Run service identity](https://docs.cloud.google.com/run/docs/securing/service-identity)
