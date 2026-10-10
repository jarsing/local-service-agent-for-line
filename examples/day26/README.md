# Day 26｜乾淨容器重現與雙 LINE 視窗驗收規格

本目錄提供 Day 26 所確立的乾淨環境獨立重現（Clean-room Reproducibility，D48）執行腳本、標準 Dockerfile，以及本機 SQLite CAS 原子認領範例程式。

相關發布文件：[Day 26 驗收規格說明](../../docs/day26/README.md)｜[iThome 文章](https://ithelp.ithome.com.tw/articles/10423179)

---

## 包含檔案

1. **`cleanroom.sh`**：標準乾淨容器重現腳本。拉取 `python:3.13-slim` 基礎映像檔，透過全新建置環境與 `--network none` 斷網隔離，重跑全量 155 項測試並匯出 7 項驗證日誌。
2. **`Dockerfile`**：提供開發者或在 Google Cloud Shell 中建置獨立映像檔的標準設定。
3. **`stop_gate_example.py`**：SQLite CAS（Compare-and-Swap）原子認領與停止閘門（PAUSED 攔截）單元範例。

---

## 如何執行驗證？

### 途徑 A：在 Google Cloud Shell 或 Docker 環境執行（推薦）

Google Cloud Shell 內建完整 Docker 與 Python 環境，適合用於無干預重現驗證：

```bash
# 執行乾淨容器重現腳本（自動斷網跑 155 項測試）
bash examples/day26/cleanroom.sh
```

或使用本目錄 Dockerfile 建置映像檔並斷網執行：

```bash
docker build -t local-day26 -f examples/day26/Dockerfile .
docker run --rm --network none local-day26
```

### 途徑 B：在本機離線 Python 環境執行（無需 Docker）

若本機未安裝 Docker，可直接以 Python 執行相同的 155 項單元測試套件：

```bash
python3 -m unittest \
  examples.day25.test_ingestion \
  examples.day24.test_evidence \
  examples.day19.test_inbox_contract \
  examples.day22.test_security -v
```

### 途徑 C：驗證 SQLite CAS 原子認領範例

```bash
python3 -m examples.day26.stop_gate_example
```

執行後將在 `out/day26/claim-01/` 目錄建立 `claims.sqlite3` 資料庫與 `report.json` 驗證報告。
