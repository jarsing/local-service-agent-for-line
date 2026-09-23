# Day 10｜逾時後到底有沒有送出？

正式文章：[Day 10｜逾時後到底有沒有送出？](https://ithelp.ithome.com.tw/articles/10416095)。前篇：[Day 9](https://ithelp.ithome.com.tw/articles/10415923)。

操作：[examples/day10/README.md](../../examples/day10/README.md)；契約：[CONTRACT.md](../../examples/day10/CONTRACT.md)。

## 本篇串起的能力

Day 1 原始政策與 Day 2 的未知／同鍵思考，接到 Day 8 確認核心及 Day 9 真正 SQLite 建單。先保留待查證，再以原識別唯讀查回；查詢成功但沒找到時，由可信控制器允許原鍵重送一次。

這是受控流程，不是模型自由重試。查回錯誤、權限或確認無效時，有明確停止位置。

## 驗證層次

| 層次 | 實際入口 | 能回答什麼 |
|---|---|---|
| 核心與 SQLite | `demo.py`、`verify.py` | 固定政策、真實資料列、權限、時效、查回與一次重送 |
| ADK 替身 | `verify.py --sdk`、`run.py` | 真正 Runner／工具介接；模型輸出由腳本產生 |
| Gemini | `run.py --live --approve-live --model ...` | 個別 run 的模型原文、工具事件及用量；另需人工判讀 |
| GitHub CI | `.github/workflows/ci.yml` | 指定 commit 在 runner 跑過列明測試；以真實 run 為準 |

提供程式及 workflow 不等於作者已完成這四層驗證。首次遠端結果、公開文章與作者觀察，依真正取得的紀錄補充。

## 接續

Day 10 留下待查證與原識別；下一篇深入 Firestore 持久化與重啟後接續。CD 沿既定日次逐步串接，本篇只加入離線 CI。
