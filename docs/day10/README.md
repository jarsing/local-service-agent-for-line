# Day 10｜逾時後到底有沒有送出？

正式文章：[Day 10｜逾時後到底有沒有送出？](https://ithelp.ithome.com.tw/articles/10416095)。前篇：[Day 9](https://ithelp.ithome.com.tw/articles/10415923)。

操作：[examples/day10/README.md](../../examples/day10/README.md)；契約：[CONTRACT.md](../../examples/day10/CONTRACT.md)。

## 本篇串起的能力

Day 1 原始政策與 Day 2 的未知／同鍵思考，接到 Day 8 確認核心及 Day 9 真正 SQLite 建單。先保留待查證，再以原識別唯讀查回；查詢成功但沒找到時，由可信控制器允許原鍵重送一次。

這是受控流程，不是模型自由重試。查回錯誤、權限或確認無效時，有明確停止位置。

## 驗證層次

| 層次 | 實際入口 | 能回答什麼 | 驗證結果 |
|---|---|---|---|
| 核心與 SQLite | `demo.py`、`verify.py` | 固定政策、真實資料列、權限、時效、查回與一次重送 | 本機與 CI 144/144 通過 |
| 真正 ADK Runner／固定腳本模型 | `verify.py --sdk`、`run.py` | 真正 Runner／工具介接；模型輸出由腳本產生 | 本機與 CI 19/19 通過（合計 163/163） |
| Gemini | `run.py --live --approve-live --model ...` | 個別 run 的模型原文、工具事件及用量；另需人工判讀 | 保留入口；本篇未新增 live Gemini 實測 |
| GitHub CI | `.github/workflows/ci.yml` | 指定 commit 在 runner 跑過列明測試；以真實 run 為準 | 首筆 Run [35895443513](https://github.com/jarsing/local-service-agent-for-line/actions/runs/35895443513)（commit `0e33e058…`）與次筆 Run [35898709828](https://github.com/jarsing/local-service-agent-for-line/actions/runs/35898709828)（commit `116e205a…`）全數通過 |

這些是離線 CI 結果；本篇未新增 live Gemini 實測，LINE 與 Cloud Run 也未由這筆 run 驗證。


## 接續

Day 10 留下待查證與原識別；下一篇深入 Firestore 持久化與重啟後接續。CD 沿既定日次逐步串接，本篇只加入離線 CI。
