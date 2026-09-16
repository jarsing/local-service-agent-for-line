# LOCAL Day 2 — 可重現的逾時與核對實驗

Python 3.10+，需可用的標準函式庫 `sqlite3`（SQLite 3.24+）。沒有 pip 依賴、金鑰、網路呼叫、Git 操作或雲端部署。

## 在 repository 根目錄執行

```sh
python3 -m unittest discover -s examples/day02 -p test_demo.py -v
python3 examples/day02/demo.py
```

Windows 使用實際安裝的 Python 3.10+ 直譯器執行相同腳本，例如 `py -3`；先確認版本，不默默安装或修改全域環境。

要產生本次實際測試的 HTML 與 JSON 報告：

```sh
python3 examples/day02/verify.py --output ../editorial/evidence/day02
```

最後一個路徑是範例：改成自己的**私人證據資料夾**。每次執行新建 run-* 子資料夾，不覆寫舊結果。先審閱紀錄再分享；失敗 stack trace 可能含本機路徑。報告不是公開網站，也不需要啟動伺服器，直接用瀏覽器開 REPORT.html。

## 必須保留的 Day 1 檔案

`docs/day01/handoff-timeout-001.json` 位於 Repo 根目錄，測試核對原始 Git blob SHA `2279609fba99c4bdc4171c4ee6ff4bcda191a797`。不要修改規格或 hash 常數來通過測試。

若跨平台換行轉換導致原檔檢查失敗，先比較 Git blob 與工作樹位元組並回報；不能關閉測試或忽略差異。

## 檔案

- `demo.py`：合成請求、SQLite 保存、冪等、注入故障與核對。
- `test_demo.py`：20 個驗收與邊界測試。
- `verify.py`：執行測試與 Demo，產生原始紀錄、HTML 報告與交接摘要。非零退出碼代表失敗／阻擋，不會發布任何內容。

SQLite 保存合成服務 ID 與請求文字，不只是內容雜湊。對外回執只回傳最小狀態與請求識別，避免把完整請求直接回傳。程式使用臨時資料庫，結束自動清理，不移轉舊版資料庫 schema。

## 故障與預期

寫入前逾時：0 筆；提交後回應遺失：1 筆。兩者都回 `pending_verification`，而不是讓送出端根據故障代碼猜後端事實。核對到請求時是 `request_created`＋`awaiting_acceptance`，不是真人已完成。

相同作用域／識別／內容回同一筆；相同識別、不同內容拒絕。核對暫時不可用或查不到時仍待核對，不換新鍵盲目重試。

## 限制

身分與確認是可信合成夾具，不是正式授權；不存在 LINE 驗簽、Gemini、ADK、Firestore 或人工客服整合。重新開啟連線不等於程式崩潰／斷電測試。小規模同鍵並發不是正式壓力測試；不宣稱分散式 exactly-once。

結果必須在實際採用版本重新執行。生成報告不能替作者簽核，也不證明 iThome 已投稿。
