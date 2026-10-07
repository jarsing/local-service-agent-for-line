# Day 23｜選型判斷表：Google AI 工具箱在地方服務該怎麼選？

這是新增的離線架構決策練習，並非四套服務的實測排名。`stack_options.json` 是四份**待驗證設計**，並不是雲端部署盤點。程式只依需求篩選宣告，不會驗證實際 IAM、冷啟動、成本或資料庫設定。

## 一、開始執行

Python 3.10 以上、僅標準函式庫。從包含 `examples/` 的專案根目錄執行；本交付中對應 `public-files/`。

```bash
python3 -m unittest examples.day23.test_stack_matrix -v
python3 -m examples.day23.stack_matrix --eval --out out/day23/community
python3 -m examples.day23.stack_matrix --eval --profile governed --out out/day23/governed
python3 -m examples.day23.stack_matrix --eval --profile reporting --out out/day23/reporting
python3 -m examples.day23.stack_matrix --eval --require-scale-zero --out out/day23/scale-zero
```

指定 `--out` 時輸出目錄不可已存在；省略該參數則只輸出 JSON 到 stdout。

## 二、讀取結果

- `community`：四個明示設計皆保留，沒有性能贏家。
- `governed`：本組候選中，僅 `vertex-run` 宣告模型服務周界設計能力。這不是已完成周界部署。
- `reporting`：本組候選中，僅 `sql-run` 宣告關聯式查詢能力。Firestore 的 NoSQL 選型不代表弱一致性。
- `--require-scale-zero`：只檢查 Cloud Run 最小實例為 0，不代表整個專案沒有固定費用。Cloud SQL 費用另列。
- `CANDIDATE`：尚可考慮的設計，不是已驗證可發布。
- `EXCLUDED`：在此需求組合下排除，`reasons` 提供原因。
- `deployment_status=NOT_VERIFIED`、性能欄位 `null`：本篇沒有外部部署與量測。

四個設計是教學用的有限集合，不是 Google 全部組合。`governed + --require-scale-zero` 沒有候選，僅表示當前集合沒有匹配配置，不表示 Vertex AI 與縮到零在技術上不相容。可以另編新方案重新審閱。

## 三、量測本機程式，不冒充雲端測試

```bash
python3 -m examples.day23.stack_matrix --probe --runs 5 --out out/day23/local-probe
```

每次透過同一 Python 執行器建立新行程並匯入 `stack_matrix.py`，保留建立行程、匯入與退出總耗時。作業系統磁碟快取不會被清空。RSS 以 Linux／macOS 的 `resource` 單位換算，其他系統留 `null`。它是本機 Python 行程的峰值，**不是容器初始 RAM**。

`source_size_bytes` 只量 `stack_matrix.py` 本身，**不是相依套件體積或容器映像大小**。無 Google／LINE client，沒有 API Key，沒有真實模型呼叫。`cloud_run_cold_start_p95_ms` 和 `model_latency_ms` 固定留 `null`。

## 四、修改邊界

Antigravity 是這個專案的開發協作工具；既有服務編排使用 ADK。本篇若更改 `orchestrator`，核對器要求重新驗證既有契約。這不是說 Antigravity SDK 或其他框架不能做執行編排，而是本案沒有做替換實測。

`latency_check()` 僅做數值門檻計算，`PASS` 不認證數字來源。模型總耗時不得傳入後冒稱 LINE Webhook 回應時間。測試中的邊界數字是數值案例，不是平台實測。

## 五、來源

平台主張與本案決策的對照見同目錄 `SOURCES.md`。每個報告記錄執行程式與方案設定的 SHA256；這可辨識內容版本，但不證明使用者填入的宣告已在雲端實現。

Day 23 工程基線為 `e59bc77`；專用 Actions Run `37537427197` 已完成 26 項離線契約測試與三種 profile／本機探針執行。探針原始量測存於 `evidence/probe_linux.json` 與 `evidence/probe_macos.json`。
