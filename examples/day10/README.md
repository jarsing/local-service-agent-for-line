# Day 10｜逾時後到底有沒有送出？

正式文章：[Day 10｜逾時後到底有沒有送出？](https://ithelp.ithome.com.tw/articles/10416095)。前篇：[Day 9](https://ithelp.ithome.com.tw/articles/10415923)。

本例用合成傳輸故障包裝既有 Day 9 建單服務，使用真正 SQLite 比較「提交後回條遺失」和「寫入前中斷」。模型提出工具呼叫，可信應用端掌握查回與一次重送的順序。

## 1. 先跑核心：不需要第三方套件

需要**包含 Day 2、Day 8、Day 9 的完整 LOCAL Repo**。將本章整合到 `examples/day10/`、workflow 放到 `.github/workflows/ci.yml` 後，在 Repo 根目錄執行。以下命令使用 macOS／Linux shell；核心 Python 以 3.13.5 驗證。

```bash
python3 examples/day10/demo.py
python3 examples/day10/verify.py
```

`demo.py` 會列出新 run 的 `REPORT.html`，每次另開資料夾。核心 verification 明列 Day 2 的原型測試、Day 8 確認核心、Day 9 建單與報告、Day 10 查回與交付檢查，**不是聲稱已跑 Day 2～10 所有日次**。

`dependency-lock.json` 核對 Day 1 原規格與真正重用的 Day 8／9 核心。發現差異時先保留作者較新檔案，確認相容性；不要覆蓋前篇或自行重算鎖值來消除失敗。Day 1 規格保持原位與位元組。

### 看哪幾份資料？

| 檔案 | 用途 |
|---|---|
| `report.json`／`REPORT.html` | 方法、案例、步驟與狀態摘要；HTML 是靜態報告 |
| `<case>/step-00.sqlite3`、`step-01.sqlite3`… | 起點與每步後的真正資料庫快照 |
| `<case>/handoff.sqlite3` | 最終資料庫 |
| `<case>/events.jsonl` | 傳輸、後端、政策、應用文案，以及 ADK 路線的工具事件 |
| `verification.json`、各組 `.json/.txt` | 固定測試、真實數量、退出碼、執行來源 |

資料筆數是測試端讀資料庫的觀察，沒有塞進模型提示。`CLIENT_STATUS` 是應用端固定文案事件，不是 Gemini 原文或 LINE 送達回條。

## 2. 真正 ADK、固定腳本模型

沿用 Day 9 或 Day 5 已有的相符虛擬環境，或建立本章環境。環境觀念見 Day 9，這裡只列命令：

```bash
python3 -m venv examples/day10/.venv
examples/day10/.venv/bin/python -m pip install -r examples/day10/requirements.txt
PY=examples/day10/.venv/bin/python
$PY -m pip check
$PY examples/day10/verify.py --sdk
$PY examples/day10/run.py --case after_commit
$PY examples/day10/run.py --case before_write
$PY examples/day10/run.py --case lookup_unavailable
```

安裝會連網。驗證及省略 `--live` 的 run 在行程內封鎖 Python socket／DNS，ADK 真正執行工具，模型則為 `ScriptedRecoveryModel`。它檢查介接、工具參數與回條，不評分 Gemini 的語意能力。

缺少 ADK 時，`verify.py --sdk` 回非零結束代碼，SDK 測試列為未執行／相依不可用；核心通過不會把整份結果改成通過。Windows 請改用 `examples/day10/.venv/Scripts/python.exe` 的完整路徑，不照抄 shell 的 `PY=`。

## 3. 真實 Gemini：另核准，明確指定模型

每個命令只跑**一個**案例；最大三回合，每回合最多三次模型請求、一次工具呼叫。每個案例上限九次模型請求、三次工具呼叫，每回合45秒，HTTP attempts=1。兩個案例分開執行的總上限十八次模型請求。

先確認帳號可用的精確模型識別、金鑰、用量與預算。程式沒有自動換模型或背景輪詢。

```bash
# REPLACE_WITH_APPROVED_MODEL_ID 必須換成作者已確認可用的模型。
$PY examples/day10/run.py --live --approve-live \
  --model REPLACE_WITH_APPROVED_MODEL_ID --case after_commit
$PY examples/day10/run.py --live --approve-live \
  --model REPLACE_WITH_APPROVED_MODEL_ID --case before_write
```

金鑰由環境中的 `GEMINI_API_KEY` 或明示 `--env-file /你自己的路徑/.env` 提供；程式不搜尋其他資料夾。請勿把私人路徑或金鑰貼進公開命令紀錄。直接相依版本延續前篇；本工作包沒有驗證帳號是否可用任何特定 Gemini 模型。

每回合查核 `TOOL_REQUESTED` → `TOOL_EXECUTED` → `TOOL_RESPONSE` 的 call ID、名稱、四參數與回條，再核對 SQLite。自然語言需人工判讀：待查證是否說準、有沒有額外承諾真人會回覆。`technical_checks_passed` 不等於模型品質已過關。

## 4. 查回與重送是兩個動作

- `reconcile_handoff_request` 只使用 SQLite read-only 連線，查無紀錄不會新增。
- 當次成功查詢但沒有找到，狀態仍為 `pending_verification`，`observation=not_found`；控制器才允許再呼叫原建單工具一次。
- 重送必須沿用原四參數；原 Day 9 服務重新查權限、確認與版本，並以交易和唯一限制處理同時送出的情況。
- 查回本身受阻為 `lookup_unavailable`，保留未知並停止這次自動流程。
- 既有回條重查當前權限、本人、Session、同鍵同內容；第一次新增才要求確認仍有效。

`already_created` 代表核對到既有請求，`request_created` 代表本次新增；`human_claimed=false`，交付範圍為 `local_sqlite_only`。兩者都不是「真人已接手」。

## 5. CI：兩個獨立工作，結果各自記錄

`.github/workflows/ci.yml` 用 `push` 到 `main` 與 `workflow_dispatch`。作者採用並 Push 才會觸發，檔案存在不表示已執行。

1. `core`：Day 1 原規格位元組、Day 2／8／9／10 的具名核心回歸、SQLite 故障示範。Python 標準函式庫即可。
2. `sdk`：安裝明列的 ADK 相依，執行 Day 9 與 Day 10 真正 ADK＋替身整合。

日常工作不呼叫 Gemini／LINE 業務 API、不部署，不需自備業務金鑰。Actions 本身仍有平台自動提供的憑證來取得程式與保存 artifact；下載、安裝、上傳都可能連網。流程只給 `contents: read`，checkout 不保存 Git 憑證。

第三方 Action 固定至 `action-lock.json` 核對的完整 SHA。選測清單與原始指令記錄在外層報告，來源在 GitHub 執行時為 `github_actions`，並保存 GITHUB_SHA、run ID、attempt、job；不修改 Day 9 的舊 `--origin` 列舉。

每次 Push 都檢查，避免改到前篇相依而漏跑。Push 後檢查不會撤銷已經進 main 的 commit；這篇沒有部署閘門。徽章和 Actions 圖片等真正遠端 run 取得後再公開。

## 6. 成果層與檔案用途

| 檔案 | 責任 |
|---|---|
| `upstream.py`／`dependency-lock.json` | 真正載入並核對 Day 8／9，沒有替代建單核心 |
| `records.py` | SendArgs 與純讀回條，從實際資料列核對身分和內容 |
| `fault.py` | 可辨識的 BEFORE_WRITE／AFTER_COMMIT 合成傳輸中斷 |
| `reconcile.py`／`policy.py` | 狀態、同鍵限制、查回和一次重送，獨立實作 Day 1 回覆政策 |
| `adk_bridge.py`／`runtime.py`／`scripted_model.py` | 真正 ADK 兩工具、可信順序、固定替身、模型原文與工具事件 |
| `demo.py`／`run.py` | 核心對照；ADK 或核准後 Gemini 入口 |
| `proof.py` | 用固定預期、事件、回條、SQLite 獨立核對，不信摘要 success |
| `test_recovery.py`／`test_packaging.py`／`test_adk_offline.py` | 正常、故障、隔離退步、schema 與實際 Runner 測試 |
| `verify.py`／`test_driver.py` | 各日獨立行程、防模組撞名、真實數量與失敗退出碼 |
| `evidence.py`／`reporting.py` | 來源、raw JSONL、靜態報告；模型思考與秘密不輸出 |

本例是單行程確認記憶體＋SQLite 的受控教學流程，模擬服務邊界的失去回覆。實際 LINE 傳送、網路中斷、跨服務持久狀態、通知與部署各自留待後續驗證。

作者要把結果另存每日 evidence 時，在命令後加：

```text
--origin author_local --out ../../LOCAL-Day10/editorial/evidence
```

這是從 Repo 根目錄執行的相對路徑，僅用於作者核准的工作區。所有新 run 使用新資料夾；歷史來源與結果保持原樣。
