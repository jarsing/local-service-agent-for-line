# LOCAL Day 5｜ADK 活動搜尋

一個 `search_local_events(date, area, keyword)` 工具，四筆範例活動，四題有工具／無工具比較。`runtime.py` 由真正的 ADK Runner 推進工具迴圈；`line_bridge.py` 重用 Day 4 Webhook。所有中文說明採繁體中文與臺灣用語。

## 從 Repo 根目錄開始

Python 3.10 以上。已建立 Day 5 環境且版本相符時直接沿用。

```bash
python3 -m venv examples/day05/.venv
examples/day05/.venv/bin/python -m pip install -r examples/day05/requirements.txt
examples/day05/.venv/bin/python -m pip check
examples/day05/.venv/bin/python examples/day05/verify.py --sdk
```

`verify.py` 執行離線資料／LINE 路由測試；`--sdk` 另用真正 ADK 與腳本化模型做工具往返檢查，網路連線被封鎖。兩層都完成後再跑真實 Gemini。套件安裝固定為 `google-adk==2.9.1`、`google-genai==2.23.0`、`httpx==0.28.1`，其餘相依條件由該 ADK 版本解析；實際相依版本記在報告。這不是跨作業系統完整鎖檔。

## 四題比較

金鑰透過 `GEMINI_API_KEY` 環境變數提供，或用 `--env-file /實際私人路徑/gemini.env`。有 `--env-file` 時只使用該檔的金鑰，私人檔案留在 Repo 外。

```bash
examples/day05/.venv/bin/python examples/day05/run.py --live
```

預設四題 × 兩組，共八個 Agent 回合：

| 條件 | 可取得的資料 | 每題模型請求上限 |
|---|---|---:|
| `without_tool` | 問題，無目錄與工具 | 1 |
| `with_tool` | 問題，透過工具取得目錄 | 3 |

兩組使用同一模型、instruction、LOW 與 2,048 token 輸出上限。每題使用新 Session，逐題交錯執行順序；沒有 temperature=0 的確定性主張。比較整批最多 16 次模型請求；每回合工具最多兩次。這是資料取得方式的比較，資料與工具同時改變，未隔離「框架」本身的因果效果。

當發生 API／執行錯誤時停止整批，已完成的回合仍保留。模型有文字但缺工具軌跡，會留下 `TRACE_MISMATCH`，繼續完成其餘題目以供作者判讀。單獨補測可指定：

```bash
examples/day05/.venv/bin/python examples/day05/run.py --live --case meeting --condition with_tool
```

每次補測是另一份新紀錄，合併比較時要列出每題採用哪次；不要只挑最漂亮的答案。`--origin author_local` 可標示作者本機執行，這是操作者提供的標記，不是身分認證。

## 報告

預設輸出在 `output/day05/run-.../`，可用 `--output` 換位置。

- `verification.json`：版本、問題、設定、原文、工具與模型事件、耗時及用量。
- `REPORT.html`：同一份紀錄的閱讀版，先比較回答，再展開查詢軌跡。
- `COMPARISON.md`：原文對照表，可整合進文章。

`RECORDED` 表示回合文字與所需軌跡已取得；回答中的時間、地點、來源與未知欄位，仍需對照目錄逐項判讀。失敗紀錄也保留。用量未提供時使用 `null`。

## 接回 LINE

需要同一 Repo 已公開的 Day 4 檔案：`core.py`、`app.py`、`adapters.py`。介接層核對的是 Day 4 commit `7a6a640aca2c3a2d7fc8ed491fd62c1a1ac1dc80` 的檔案，不修改它們。

私人 `line.env` 使用 Day 4 已有的 `LINE_CHANNEL_SECRET`、`LINE_CHANNEL_ACCESS_TOKEN`、`LINE_TEST_USER_ID`；Gemini 使用已有金鑰檔。

```bash
examples/day05/.venv/bin/python examples/day05/line_bridge.py --live \
  --line-env /實際私人路徑/line.env \
  --gemini-env /實際私人路徑/gemini.env
```

監聽 `127.0.0.1:8000`，Webhook 路徑為 `/webhook`。沿用已核准的 HTTPS 測試入口；若上次測試後已關閉 Webhook，先重新開啟。手機先傳 `LOCAL ping`，再傳一次 `LOCAL 測試`。第二個指令送出固定的 `accessibility` 題；一般聊天維持原 Day 4 路由範圍。

這一段另加一個 Agent 回合，最多三次模型請求。搭配四題比較，預定上限為 19 次模型請求；LINE 原入口每次啟動最多八次 Reply API 嘗試，正常展示只需 ping 與模型回覆各一次。通道、API 與重試按作者已核准範圍操作。

## 快速排除問題

| 狀況 | 先看這裡 |
|---|---|
| 套件無法安裝 | 網路、PyPI、Python 版本與完整安裝錯誤。保留舊環境，勿用 `--no-deps` 跳過依賴。 |
| `--sdk` 受阻 | `sdk_check`、`sdk_error`、`sdk_result`；先解決 ADK 載入或介面差異。 |
| 401／403／429／503 | 報告的錯誤類型與 HTTP 狀態，再核對金鑰、權限、配額或服務狀況。 |
| `TRACE_MISMATCH` | 工具是否真的執行、參數、回傳結果與案例相符嗎？ |
| ping 沒回來 | Webhook 開關、通道、測試者 ID、簽章與連接埠。 |
| 出現兩則回覆 | 官方帳號的內建自動回應是否仍啟用？ |

## 延伸到 Day 6

`catalog.json` 是今天的手寫資料。下一篇將從活動海報整理相同欄位；工具介面可以沿用。日期、地區、來源、更新時間與未知欄位，是兩篇的資料接點。
