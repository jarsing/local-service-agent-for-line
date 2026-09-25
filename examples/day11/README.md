# Day 11｜服務重啟了，剛才交代的事還在嗎？重送、背景工作與重啟恢復

正式文章：[Day 11｜服務重啟了，剛才交代的事還在嗎？重送、背景工作與重啟恢復](https://ithelp.ithome.com.tw/articles/10416397)。本章保存業務任務、原確認、回條與有限處理進度，示範跨行程接續。各層驗證範圍見下方結果表。

讀者問題：**服務重啟，剛才的詢問還找得到嗎？**

## 1. 這次保存什麼

保存的是原操作、當時的確認、請求回條、有限工作進度，以及同一邏輯 Session 的「目前任務參照」。
**不是完整 ADK 聊天歷史，也沒有恢復全部自然語言上下文。**

採用 Day 9 的花壇教學快照（date=2026-09-19），不改成新的可參加活動。`service_id` 是原 `Operation.destination` 的持久化欄位（`local_demo_service_desk`），不是活動 ID。

`event_id` 延續 Day 9／10，代表地方活動識別，不是 LINE 的 webhook 事件識別。LINE 事件去重與業務冪等是不同責任；本章沒有新增 LINE 接收端。

資料責任見 [CONTRACT.md](CONTRACT.md)，完整驗收矩陣見 [ACCEPTANCE.md](ACCEPTANCE.md)。前篇 [Day 10](../day10/README.md) 不改，SQLite 正常檔案可跨應用行程存留；新後端的動機是共用外部儲存與保存原先僅在記憶體的任務資料，不是「SQLite 一重啟就消失」。

## 2. 三條後端路線與一個記憶體控制組

| 選項 | 真正執行的是什麼 | 需要什麼 |
|---|---|---|
| `sqlite-test` | `SQLiteTestStore` 文件介面測試 adapter，真的寫 SQLite | Python 標準函式庫 |
| `emulator` | 真正 Firestore Python SDK → 本機 Google Firestore 模擬器 | Firestore SDK、Firebase CLI、相容 Node.js、Java 21、loopback RPC |
| `cloud` | 真正 Firestore Python SDK → 明示的 Google Cloud 專案 | 另外核准的專案、IAM／ADC、費用與清理計畫 |

同一個示範只選一種後端；Firestore 路線不先寫 SQLite 再同步。測試 adapter 不是 Firestore 模擬器。模擬器也不是正式雲端：交易、限制及索引仍可能不同。[官方限制](https://firebase.google.com/docs/emulator-suite/connect_firestore#how_the_cloud_firestore_emulator_differs_from_production)

| 層次 | 可公開核對的紀錄 |
|---|---|
| Day 11 記憶體／SQLite 核心 | GitHub Actions Run 36083862231，core 97／97 全數通過 |
| 真正 ADK＋固定腳本模型 | 同一 Actions Run，sdk 13／13 全數通過 |
| 本機 Firestore 模擬器實測 | 作者本機啟動模擬器，verify emulator 59／59 通過，六場景及 after_commit (PID 48888→48890) 查回原單 |
| 正式雲端 Firestore / Cloud Run | 留待 Day 12 接續驗證，不從本次本機模擬器推定 |

## 3. 先在沒有金鑰的環境看一次跨行程結果

需要完整 LOCAL Repo，包含 `docs/day01/` 與 `examples/day02/`、`day08/`、`day09/`、`day10/`。
以下 shell 命令適用 macOS／Linux，從 Repo 根目錄執行：

```bash
python3 examples/day11/demo.py --compare-memory --backend sqlite-test
python3 examples/day11/demo.py --backend sqlite-test
python3 examples/day11/verify.py --group core
```

第一個命令產生記憶體／SQLite 對照，第二個命令跑六種情境。兩者各有自己的 `REPORT.html`。先看 `normal`：不同 PID 取得同一筆；再看 `after_commit`：A 強制退出，B 查回原單。`verify.py --group core` 沿用 Day 10 驗證入口，再跑 Day 11 新增群組；實際數量動態統計。

只跑一種情境：

```bash
python3 examples/day11/demo.py --backend sqlite-test --case after_commit
```

### 兩個行程如何啟動？

`demo.py` 以 `subprocess.run()` 依序啟動 `process_worker.py --action first` 及 `--action resume`。A 在保存後可用 `os._exit(73)` 結束，跳過正常清理。B 收到後端設定與可信測試身分，從資料庫的 Session 參照讀出原四參數；沒有把 A 的回條當成 B 的輸入，也沒有在 B 再次呼叫 `prepare(..., approved=True)`。

租約為 30 秒，案例用測試邏輯時鐘前移 31 秒，不改系統時間，也不是實際等待 31 秒。本章驗的是應用行程結束與重啟，沒有重開宿主機或資料庫服務。

### 檔案怎麼讀？

| 檔案 | 意義 |
|---|---|
| `report.json`／`REPORT.html` | 摘要與靜態報告，不作唯一證據 |
| `<case>/config.json` | 測試後端、可信合成身分、故障位置與邏輯時間設定 |
| `<case>/process-a/events.jsonl`、`process-b/events.jsonl` | 真正 PID、操作、lease／claim、回條與退出事件 |
| `<case>/process-*.execution.json` | 父行程取得的真實退出碼；73 僅在指定 crash 案例為預期 |
| `<case>/after-a.sqlite3`、`after-b.sqlite3` | SQLite 測試路線的實際資料庫快照 |
| `<case>/after-a.json`、`after-b.json` | 各後端的實際文件匯出；Firestore 在子行程停止時逐集合讀取，非全庫原子快照 |
| `<case>/process-b/result.json` | 接續行程取得的結果，不把觀察器看到的資料偷偷送給模型 |
| `<case>/process-b/adk-report.json` | 只有 `--adk` 真的跑到時才有；模型是固定腳本 |

`proof.py` 在 SQLite 路線直接以唯讀 SQL 讀上述快照，再與文件匯出比對。Firestore 路線使用實際 SDK 讀到的文件匯出；沒有聲稱離線檔案就是第三方雲端認證。

## 4. 真正 Firestore 模擬器路線

使用獨立環境，不自動升級 Day 5 或 Day 9 的環境：

```bash
python3 -m venv examples/day11/.venv
examples/day11/.venv/bin/python -m pip install -r examples/day11/requirements.txt
examples/day11/.venv/bin/python -m pip check
```

`requirements.txt` 固定 Firestore 2.31.0（2026/09/24 核對官方發行頁）；交付環境未能安裝，**須在作者環境驗證相容性**。不是所有遞移套件都已鎖定，請保留實際 `pip list --format=json` 與 CLI 版本。

需要 Java 21、Firebase CLI 支援的 Node.js。已有相符 CLI 可直接用；沒有時可在專案私有工具目錄安裝，安裝會連網：

```bash
node --version
java -version
npm install --prefix examples/day11/.firebase-tools firebase-tools
examples/day11/.firebase-tools/node_modules/.bin/firebase --version
```

保留 `.firebase-tools/package-lock.json` 與實際版本在私人 evidence；它不是本交付已測過的 CLI 鎖。不要將 `.firebase-tools/` 或 `.venv/` 提交。

**終端機 A**，從 Repo 根目錄啟動：

```bash
examples/day11/.firebase-tools/node_modules/.bin/firebase emulators:start \
  --only firestore --project demo-local-day11 --config examples/day11/firebase.json
```

**終端機 B**，從同一 Repo 根目錄：

```bash
export FIRESTORE_EMULATOR_HOST=127.0.0.1:8080
PY=examples/day11/.venv/bin/python
$PY examples/day11/verify.py --group emulator
$PY examples/day11/demo.py --backend emulator
```

先做與第一個命令相同的 Firestore 對照：

```bash
$PY examples/day11/demo.py --compare-memory --backend emulator
```

`memory-control` 是另外設計的記憶體教學控制組；它的 A 退出前會留下測試端觀察檔，但 B 完全不讀該檔來恢復任務。它不代表 Day 10 的 SQLite 檔案會因行程結束而消失。正式模擬器組須真的執行，不能只改報告 label。

此入口只接受 `demo-` project 與 loopback host:port；沒有模擬器不會偷偷改連雲端，也不會退回 SQLite。缺套件、沒有啟動服務或測試錯誤都以非零退出，不列成通過。

測完在終端機 A 按 Ctrl+C。示範不設定 import/export；模擬器停止可能清除資料，先保存本機報告。每次使用新的 `day11-` 隔離命名空間，避免覆寫舊 run。

模擬器的開啟與套件安裝會用到網路；Firestore 測試時則使用本機 RPC，與「封鎖全部 socket 的標準函式庫測試」不同。

## 5. 真正 ADK＋固定腳本模型

安裝同一環境的可選 SDK 相依後，先 `pip check`：

```bash
PY=examples/day11/.venv/bin/python
$PY -m pip install -r examples/day11/requirements-sdk.txt
$PY -m pip check
$PY examples/day11/verify.py --sdk
$PY examples/day11/demo.py --backend sqlite-test --adk --case after_commit
```

前篇 19 項與本篇 ADK 測試分開記錄。`--sdk` 不自動啟動 Firestore 模擬器。

模擬器已啟動且兩組套件相容時，再驗真正組合：

```bash
export FIRESTORE_EMULATOR_HOST=127.0.0.1:8080
$PY examples/day11/demo.py --backend emulator --adk --case after_commit
```

`run_recovery()` 建立新的 `InMemorySessionService`，從已核對的業務任務參照提供原參數；ADK 舊 events 並未恢復。這不是原生 FirestoreSessionService 的實作，也沒有呼叫 Gemini API。若日後要接 Gemini，需另核准並保留語意、用量與真實工具軌跡，不能拿腳本輸出冒充。

每回合至多 1 次工具執行、3 次模型執行；每次流程最多 3 回合。工具核對 Session、原參數與次序，不讓模型指定權限。`TOOL_REQUESTED → TOOL_EXECUTED → TOOL_RESPONSE` 以 call ID、名稱、參數與結果核對。

## 6. 有限工作與資料責任

這不是一直跑的背景服務。每次明確啟動 worker，最多走初次送出、查回、一次原鍵重送。工作文件先保存嘗試計數與下一步，再呼叫實際服務。

- 租約未過期：另一 worker 得到 `worker_busy`。
- A 寫入後崩潰：資料已存在；B 等租約可接續時先查回。
- A 寫入前崩潰：B 成功查無後，才可用原確認與原鍵重送。
- 查回受阻或預算用完：停在待查證；不自動刷新預算或取得同意。
- 租約被新 worker 取得：舊 token 不能覆寫新工作進度。資料本身的防重複仍靠文件交易及同一 operation ID，不靠租約單獨保證。

租約使用可信應用端 UTC 時鐘。本例用邏輯時鐘驗證到期，不宣稱已驗證跨主機時鐘偏差。新 worker 還沒接走租約前，原 worker 可完成自己的紀錄；新 token 出現後舊 token 失效。

`prepare()` 是合成可信入口，使用原 Day 8 型別、指紋與 `ConfirmationStore.issue/decide` 產生一次原確認。Day 11 新增 `confirmation_gate.py` 檢核持久化快照。因 Day 8 沒有公開匯入 API，沒有灌入 `_records`，也不宣稱舊記憶體儲存整個不改就跨行程。

本例只保存每個邏輯 Session 的目前任務參照；新建另一任務會更新該參照。完整多任務歷史、待確認內容後續補同意的 UI 與聊天記憶留待後續。

## 7. CI 整合：保留原工作流，增加 Day 11 擴充

原 `.github/workflows/ci.yml` 不變。新增 `.github/workflows/day11.yml` 只跑 Day 11 新增 core 和 ADK 兩組。

作者採用並 Push 後，同一 commit 必須核對兩個工作流，才描述「前篇＋Day 11 全部列明檢查通過」。不要把本機 `verify.py --sdk` 跑過一次、舊 CI 又跑一次的同名測試加總成新的獨立案例。

新工作流沒有 Firestore 雲端／Gemini／LINE 秘密與呼叫，也沒有自動啟動模擬器。Firestore SDK與真正模擬器的本機整合結果須另外保存；未來加入 emulator CI 時再核准 CLI／JVM 與依賴鎖。Action SHA 延用 Day 10 的釘版，不因新增本檔改動原工作流。

## 8. 正式雲端不是預設操作

程式保留 `--backend cloud --approve-cloud` 路線，且要明示非 demo project 與 `day11-` namespace，清掉 `FIRESTORE_EMULATOR_HOST`；入口仍只執行合成演練，不是正式使用者服務。

執行前另確認專案、資料庫 `(default)`、IAM／ADC、費用及刪除範圍。使用 namespace 只是隔離命名，**不是權限邊界**。本地範例的合成授權表不是 production 登入系統。

`firestore.rules` 限制客戶端直接讀寫；Python 伺服器 SDK 使用 IAM，不能以這份 rules 代替伺服器授權測試。清理時只刪該次已核准的 demo namespace 與其子集合；Firestore 刪掉父文件不會自動清除所有子集合，不操作整個專案。

本交付未執行正式雲端，沒有新增雲端資源。

## 9. 參考資料

- [Firestore 交易與回呼重跑](https://firebase.google.com/docs/firestore/manage-data/transactions)
- [Firestore 模擬器與正式服務差異](https://firebase.google.com/docs/emulator-suite/connect_firestore)
- [Firebase CLI](https://firebase.google.com/docs/cli)
- [Cloud Run 容器執行契約](https://docs.cloud.google.com/run/docs/container-contract)
- [ADK Session](https://adk.dev/sessions/session/)
- [Firestore Python SDK 2.31.0](https://pypi.org/project/google-cloud-firestore/2.31.0/)

以上是本輪核對的外部文件，不是作者實測證明。文章以已執行層次定稿。
