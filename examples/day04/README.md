# LOCAL Day 4｜LINE Webhook × Gemini 文字回合

範圍：單一測試頻道、一位允許的測試者、兩個固定指令。沿用 `../day03/run.py` 的案例與回覆擷取函式，不修改 Day 3；沒有建立服務案件、ADK、持久化工作佇列或雲端部署。

## 環境

使用可用的 Python 3.10 以上。下列指令從 **程式 Repo 根目錄** 執行；可由 Antigravity 在作者核准後執行，不必更換系統 Python。

```bash
python3 -m venv examples/day04/.venv
examples/day04/.venv/bin/python -m pip install -r examples/day04/requirements.txt
examples/day04/.venv/bin/python examples/day04/verify.py --output ../../LOCAL-Day04/editorial/evidence
```

Windows 使用 `.venv/Scripts/python.exe`。若既有環境已經相容，可沿用；搬過位置的虛擬環境可能需要重建，但不要刪除其他日次的環境。

套件檔是本例的直接相依套件版本，不是完整的跨平台鎖定。`google-genai==2.23.0` 來自作者 Day 3 的實測紀錄，不是「官方最新版本」宣告。模型預設沿用 `gemini-3.8-flash`／`LOW`，不自動替換；帳號不支援時保留錯誤再處理。

## 私人設定與啟動

只用沒有正式客戶的測試 LINE 官方帳號。LINE 的 Channel secret、Channel access token 與 Your user ID 分別放在 Repo 外同一份 `line.env`；名稱如下：

```text
LINE_CHANNEL_SECRET=YOUR_TEST_CHANNEL_SECRET
LINE_CHANNEL_ACCESS_TOKEN=YOUR_TEST_CHANNEL_ACCESS_TOKEN
LINE_TEST_USER_ID=YOUR_USER_ID_UNDER_THIS_PROVIDER
```

金鑰檔案由作者自行填入，不貼到對話。沿用 Day 3 的 Gemini `.env`，不複製金鑰到公開 Repo。**本例明確讀指定檔案，不像 Day 3 優先讀同名環境變數。**

對本系列的新工作目錄，程式 Repo 位於 `2026ironman/GitHub/local-service-agent-for-line`；從這裡出發：

```bash
examples/day04/.venv/bin/python examples/day04/app.py --live \
  --line-env ../../LOCAL-Day04/editorial/private/line.env \
  --gemini-env ../../LOCAL-Day03/editorial/private/.env \
  --output ../../LOCAL-Day04/editorial/evidence
```

此步驟允許後續固定指令觸發真實 Google 與 LINE 回覆 API；可能消耗額度。啟動本身不發訊息、不建立通道、不調整 LINE 設定。

## LINE 端設定

1. Messaging API 頻道的 Basic settings：確認 Channel secret 與 Your user ID。User ID 不同於可搜尋的 LINE ID 或 @官方帳號，且與 Provider 有關。
2. 準備該測試頻道仍有效的 Channel access token。不要為了測試而重新發行正式頻道金鑰。
3. 用既有、獲准的 HTTPS 開發入口，將請求導向 `127.0.0.1:8000`；沒有既有入口時，可在作者核准後使用 Cloudflare Quick Tunnel：

   ```bash
   cloudflared tunnel --url http://127.0.0.1:8000
   ```

4. Webhook URL 填 `https://實際主機名稱/webhook`，按 Verify，再開啟 Use webhook。正確簽章的 `events: []` 會回 HTTP 200。
5. 只在測試帳號檢查自動回應設定，避免舊的預設文字混淆測試。不要改正式帳號。加入此測試官方帳號為好友。
6. 先傳 `LOCAL ping`，確認 LINE 固定回覆。再傳 **一次** `LOCAL 測試`，觸發 Day 3 合成案例的 Gemini 說明。

其他文字、圖片、群組、非允許帳號與非 active 事件會略過，這是有意限制，不是泛用客服。原始 LINE 文字與身分不送給 Gemini。

## 分開判讀

- `WEBHOOK_VERIFIED_EMPTY`：收到可通過驗簽的空事件，不等於模型或回覆已完成。
- `ACCEPTED_IN_MEMORY`：只進入當次行程的記憶體佇列，尚未取得模型結果。
- `MODEL_TEXT_RECEIVED`：有符合本例基本條件的模型文字，語意仍待審閱。
- `LINE_REPLY_ACCEPTED`：回覆 API 回應 200，不是手機已顯示、已讀或業務完成。
- `MODEL_ERROR`／`MODEL_NEEDS_REVIEW`：嘗試送出固定降級說明，**不是 Gemini 成功回答**。
- `LINE_REPLY_UNKNOWN`：未取得可確認的回覆結果，不盲目重試、不改用 push。

每次啟動建立新 `run-...`，保存 `verification.json`、`REPORT.html`、`CHATGPT_HANDOFF.md`。報告不放在 Webhook 服務路由，須本機開檔閱讀。手機是否顯示與作者判讀另外記錄。

## 自訂限制與誠實邊界

預設最多 3 次模型嘗試、8 次 LINE 回覆嘗試；模型逾時 15 秒、LINE HTTP 逾時 8 秒、不自動重試。這些是本例設定，不是官方限制或帳單保證。重新啟動會重置計數。

只有一個背景工作執行緒與一格待處理佇列。佇列滿回 503；同一行程用事件識別去重。程式中止／重啟會遺失待辦與去重紀錄，已回 200 的工作也可能尚未回覆。這不是 Cloud Tasks，也不保證跨重啟的精確一次。

不建議直接用於正式營運。本例只在使用者事件送達後的有限本機時間內嘗試 reply；LINE 的 token 可能受傳遞延遲與平台條件影響，不因本機設 35 秒就保證可用。HTTP 逾時也不能證明遠端沒有執行或沒有費用。

原始 request body、Channel secret、access token、reply token、user ID 不存入實驗報告。受信任的通道代理仍會處理傳輸資料；本例不提供其他個資的合規保證。結束後由作者關閉測試頻道的 Use webhook，停止本機服務及臨時通道，不刪測試紀錄。

## 官方參考

- [LINE：驗證簽章](https://developers.line.biz/en/docs/messaging-api/verify-webhook-signature/)
- [LINE：驗證 Webhook URL](https://developers.line.biz/en/docs/messaging-api/verify-webhook-url/)
- [LINE：接收事件](https://developers.line.biz/en/docs/messaging-api/receiving-messages/)
- [LINE：回覆訊息與 token](https://developers.line.biz/en/reference/messaging-api/nojs/#send-reply-message)
- [LINE：建立機器人](https://developers.line.biz/en/docs/messaging-api/building-bot/)
- [LINE：User ID](https://developers.line.biz/en/docs/messaging-api/getting-user-ids/)
- [Google：SDK](https://googleapis.github.io/python-genai/)
- [FastAPI：直接讀取 Request](https://fastapi.tiangolo.com/advanced/using-request-directly/)
- [Cloudflare：Quick Tunnel](https://developers.cloudflare.com/tunnel/get-started/)
