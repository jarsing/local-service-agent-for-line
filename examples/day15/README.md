# Day 15｜對話越來越長之後：Session、摘要與上下文預算

同一個 LOCAL 新增有限短期上下文。Gemini 解讀指代，ADK 在模型呼叫前組裝內容；
原 Day 14 的同意偏好、原單查回與權限控制不靠摘要回想。

## 先跑起來

從含有前篇的 **Repo 根目錄** 執行。使用 Python 3.13.5（沿用作者環境）：

```bash
python3 -m examples.day15.demo --out out/day15/first-run
```

這是五分鐘最小離線路徑，不需套件或金鑰。輸出目錄必須尚未存在。
命令會跑核心測試、五回合合成請求大小比較、刻意超量拒絕，並直接保存 SQLite
同意／忘記前後資料。它量 UTF-8 bytes，`tokens` 與模型延遲保留 `null`。
報告 `passed` 只是索引；逐項依據在 `contracts.log`、逐回合 JSON 與 SQLite 備份。

例題都是合成資料，同意由測試程式代送，不是假裝作者手機操作。
A/B 兩組使用相同的簡化工具 schema 與相同公開話題投影；B 只保留兩回合與摘要。
**不是把 Day 14 當成一個原本就無限存歷史的壞版本**。

## 五層怎麼分

| 層 | 資料 | 是否進模型 |
|---|---|---|
| 規則 | 原同意限制、工具定義、指代規則 | 是；納入輸入計量 |
| 當次事件 | 最新問句；簽章與 actor 在後端 | 問句是，身分憑證不是 |
| 最近視窗 | 最多兩個已完成話題投影 | 是；完整問答對 |
| 濃縮摘要 | `goal`、`area` | 是；僅供指代，不是同意／完成事實 |
| 後端事實 | 原服務單、目前權限、已同意偏好 | 由原工具取用；偏好值不放 Prompt |

`SafeTurn` 僅接受 places/events/help 與已知公開鄉鎮，不保存原句、模型原文、
飲食值、姓名、健康條件、單號、卡片、工具結果全文。轉成的 user/model 訊息
明標為投影，不能被引用成使用者原話。不是所有複雜追問都能靠這個最小 schema 處理。

`GoalSummary` 是確定性的欄位縮減，不另外呼叫 LLM，也不是 ADK 的自動
EventsCompactionConfig。官方自動壓縮可用於更一般的對話；本篇先選可檢查的
欄位與撤回邊界。手寫摘要不能被宣稱成模型摘要品質實驗。

`ContextJournal` 沿用 Day 11 的文件交易介面，寫入 `conversation_context`。
同 actor、不同 ADK Session 可讀同一份短期脈絡。預設有效期 900 秒是示範設定；
**到期不再取用，不等於 Firestore 自動實體刪檔**。只保留兩個投影與小摘要，
帳號／租戶分開。既有 collection、namespace、簽章鍵與偏好文件不搬移。

保存／更正／取消／忘記使偏好版本變動時，新 runtime 會清空短期脈絡；
即使清理失敗，下一次 read 也拒用版本不符的舊內容。工具前後與 Reply 前仍依
Day 14 檢查；不能撤回已經交給 LINE 的網路請求、訊息或外部保留紀錄。

同時提交的新對話採 generation 比對，舊結果不覆寫新脈絡。這是短期 context 的
一致性控制，不取代 Day 9 的建單冪等。原請求建立與查回繼續沿用舊路由。

## 預算：輪數上限不等於 Token 上限

`BudgetSessionManager.prepare` 先縮到最近兩回合，再用提供的計量器檢查整份請求。
超量依序丟最舊完整回合、最後丟摘要；當次問句與規則不裁掉。仍超量就拒絕。
`max_turns=0` 不會出現 Python `[-0:]` 意外保留全歷史。

離線 `ByteCounter` 只能搭配 `unit="utf8_bytes"`。線上 `GeminiTokenCounter`
透過 Gemini Developer API `models.countTokens` 的 `generateContentRequest`
計入系統指令、完整 ADK function declarations、contents 與 tool config。
不是 `len(text)/4`，也不是只計目前一句話。

候選預設輸入上限 8,192 tokens；生成設定仍為 512 max_output_tokens、LOW。
這是應用選的投入上限，不是模型上下文容量公告。輸出與思考實際用量仍看 API
usage metadata，不由輸入估值推算帳單。

每回合最多四次 countTokens、一個生成請求；原 18 秒回合逾時限制仍在，
計量也花時間。countTokens 出錯便停止生成，沒有 byte 假裝 token 的 fallback。
這是少量白名單同步示範；不是高流量或 LINE Webhook 延遲已過關的承諾。

## 原環境中的測試

先沿用前篇環境；不為本篇自動升級：

```bash
PY=examples/day12/.venv/bin/python
$PY -m examples.day15.verify --group all --origin author_local --out out/day15/all-01
$PY -m examples.day15.verify --group previous --origin author_local --out out/day15/previous-01
```

`all` 是 Day 15 標準函式庫與 HTTP/ASGI 替身；`previous` 是選定 Day 14、13、12
本機群組。前篇真正 ADK 不混進 previous，不以沒有安裝套件當作 skip 後成功。

真正 SDK 與模擬器分開：

```bash
$PY -m examples.day15.verify --group adk --origin author_local --out out/day15/adk-01

# 在另一終端機依 Day 11 指南啟動 Firestore Emulator 後：
export FIRESTORE_EMULATOR_HOST=127.0.0.1:8080
$PY -m examples.day15.verify --group emulator --origin author_local --out out/day15/emulator-01
```

`adk` 使用真 Runner＋腳本模型（5 個方法），不是 Gemini 理解能力；
`emulator` 是 4 個真 Firestore 模擬器方法，不退回 SQLite，不碰正式專案。
沒有套件／host 時以非零結束，保留原始錯誤。模擬器使用 demo-local-day15 與
隨機 day11-d15 namespace，不清空其他工作。

## 真正 Gemini 對照：先核准，再執行

固定模型／SDK：

- `gemini-3.8-flash`、`ThinkingLevel.LOW`
- `google-genai==2.23.0`、`google-adk==2.9.1`
- Firestore SDK 沿用 Day 12 requirements 的 `2.31.0`

`live_compare` 明示最多兩個生成回合、最多八次 countTokens。兩組使用相同
合成五回合的前四個話題投影、相同同意偏好、問句、schema、模型與設定，
比較的是最後一問，不是假稱五輪真人連續聊天全部已測：

```bash
export GEMINI_MODEL=gemini-3.8-flash
# 金鑰已在私人環境，勿把值放命令或報告。
$PY -m examples.day15.live_compare --approve-live --out out/day15/live-01
```

輸出保存模型請求、同一 call ID 的請求／工具執行／回傳、有效參數、Token 計量、
usage metadata、整輪耗時、countTokens 耗時與 SQLite 狀態。
先跑 full_comparison，再跑 budget；一組失敗即停，不自動改 Prompt 重試。
固定順序與單次樣本可能受服務暖機、網路等因素影響；不得據此宣稱穩定較快。

核對重點是：省略鄉鎮仍叫對 places、`area=花壇鄉`，模型的 `dietary_type`
留空而後端補 vegetarian。四種否定／轉述、更多領域與 Day 18 保留題集另處理。

正常服務不持久保存 `model_inputs`。這個 CLI 只處理自己建立的合成 SQLite，
不得改指真實使用者或正式資料庫。`before_model_callback` 的快照不是封包側錄。

## LINE 接點與人工交付

`examples.day15.main:app` 繼承原 Day 14 runtime，不重寫驗簽、同意、
忘記、三入口、原單確認／取消。自由文字與查店家／活動按鈕可留下公開話題，
記憶提案與服務需求原文不進對話摘要。

候選整合步驟：
1. 核對本機測試、真 SDK、模擬器與必要 live 對照。
2. 沿用現有 project/service/region、Runtime SA、Secret Manager、namespace 與
   `LOCAL_ACTOR_KEY`。不要重建環境或換鍵。
3. 核准模型輸入可傳給 countTokens 服務後，新增
   `LOCAL_APPROVE_COUNT_TOKENS=yes`；這只允許本篇計量，不授權自動部署。
4. 從唯一 Repo 匯出 Repo 外的新建置目錄：

```bash
$PY -m examples.day15.build_context --out "$BUILD_CONTEXT"
```

`BUILD_CONTEXT` 必須先設定到核准的工作區；作者的值見私人接手指南。
沿用 Day 14 已成功的 Cloud Shell 建置路徑，核對 Dockerfile 入口確為 Day 15。
沒有本機 Docker 不必為這篇新裝。保存真實 SOURCE_MANIFEST、映像 digest 與 revision。

以無流量候選 revision 核對後，再由作者決定切換；流量調整不是瞬間，
回復程式也不會回復偏好資料。此包沒有執行遠端操作或提供新的雲端成績。

手機建議順序：查花壇→問其他已知功能→「剛才那個鄉鎮，再找吃的」→更正偏好→
忘記→再查明示花壇→按舊同意卡。核對最新有效條件，不靠店名是否相同判斷記憶。

## CI 與目前交付狀態

`.github/workflows/day15.yml` 是候選工作流：Push 到 main／手動觸發，
只有離線測試、合成演練與 artifact，沒有模型金鑰、真正 countTokens 或自動部署。
安裝測試相依仍可能連網。日常來源讀取為 `contents: read`；
Action SHA 沿用前篇已使用版本，合併前仍核對作者實際工作流。

這份交付提供程式與本機重現入口，不代表 Day 15 文章已刊出或遠端 CI 已跑。
本輪助理結果與未跑層次記在私人工作包的 REPRODUCTION.json；作者執行後新增紀錄，
不要改寫舊報告或在沒有結果時填上一個綠燈。

## 官方參考

- [ADK callbacks](https://adk.dev/callbacks/types-of-callbacks/)
- [ADK context compression](https://adk.dev/context/compaction/)
- [Gemini countTokens](https://ai.google.dev/api/tokens)
- [Day 14 文章](https://ithelp.ithome.com.tw/articles/10418240)
