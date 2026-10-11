# Day 27｜Demo 版本凍結與備援重放

本目錄提供 Day 27 所確立的展示版本凍結（Demo Freeze）、Google Cloud Shell 驗收入口，以及本機 SQLite 離線重放備援程式。

相關發布文件：[Day 27 三分鐘展示手冊](../../docs/day27/DEMO.md)

---

## 包含檔案

1. **`cleanroom.sh`**：Google Cloud Shell 一鍵乾淨容器驗收腳本。拉取指定 Commit 程式碼，於容器內以 `--network none` 斷網隔離重跑 155 項測試，產出完整退出碼與日誌。
2. **`replay_day27.py`**：本機 SQLite 離線重放示範程式。操作合成身分，驗證同號查回、PAUSED 停止閘門阻擋、SERVING 恢復後單次認領，以及重送防呆機制。
3. **`test_day27_replay.py`**：5 項獨立單元測試，涵蓋狀態移轉、輸出防覆寫、核心雜湊不符阻擋、故障注入報告記錄與型別判定。

---

## 如何執行驗證？

### 途徑 A：在 Google Cloud Shell 執行乾淨容器驗收（推薦）

開啟 Google Cloud Shell 瀏覽器終端機，執行：

```bash
bash examples/day27/cleanroom.sh
```

或從程式庫根目錄執行 `day27_cleanroom.sh`。

### 途徑 B：在本機離線執行 SQLite 備援重放（無需 Docker）

從程式庫根目錄執行：

```bash
# 1. 執行 5 項獨立本機測試
python3 -m unittest test_day27_replay -v

# 2. 執行一般模式重放
python3 replay_day27.py --out out/day27/replay-normal

# 3. 執行最佳化模式（-O）重放
python3 -O replay_day27.py --out out/day27/replay-optimized
```

執行後將在 `out/day27/replay-normal/` 與 `out/day27/replay-optimized/` 分別建立 `demo.sqlite3` 資料庫與 `report.json` 驗證報告。
