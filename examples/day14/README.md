# Day 14｜「今天想吃素」不等於以後都要！經同意的記憶與地方店家查詢

同一個 LOCAL 新增公開店家查詢、一項可查看／更正／忘記的飲食偏好，以及三個可操作的說明入口。模型只能提案，明確同意由後端接收並驗證。

本章沿用 Day 11 文件交易、Day 12 Webhook／身分／資料與 Day 13 確認卡；不覆蓋前篇。前置導覽：[Day 13](../day13/README.md)。正式文章：[Day 14｜「今天想吃素」不等於以後都要！經同意的記憶與地方店家查詢](https://ithelp.ithome.com.tw/articles/10418240)。

## 固定模型與 SDK 基準

本系列及 Day 14 固定使用 `gemini-3.8-flash`、思考等級 `LOW`、`google-genai==2.23.0`。不自行替換、升級或降版。相依 pin 沿用 Day 12 的 `requirements.txt`；固定設定不代表真正 SDK 與模型已在本輪驗證。

```bash
# 真實模型與雲端入口均讀取這個既定模型設定；API 金鑰由私人環境提供。
export GEMINI_MODEL=gemini-3.8-flash
```

## 1. 最小開始

從含有前篇的 **Repo 根目錄** 執行。先試不需要網路與模型金鑰的公開資料工具：

```bash
python3 -c "from examples.day14.places import search_local_places; import json; print(json.dumps(search_local_places(area='花壇鄉', dietary_type='vegetarian'), ensure_ascii=False, indent=2))"
```

標準函式庫路線可執行 102 項核心測試與獨立行程演練：

```bash
python3 -m examples.day14.verify --group core --origin author_local --out out/day14/core-01
python3 -m examples.day14.demo --origin author_local --out out/day14/processes-01
```

沿用 Day 12 已可用的相依環境，不因本篇自行升級 SDK：

```bash
PY=examples/day12/.venv/bin/python
$PY -m examples.day14.verify --group all --origin author_local --out out/day14/all-01
$PY -m examples.day14.verify --group previous --origin author_local --out out/day14/previous-01
```

`all` = 本篇核心 102＋簽章 ASGI 流程 27，共 129；`previous` = Day 12 核心 45＋Day 13 的 67，共 112。真正 ADK 或 Firestore 不在其中；缺少相依不能略過後宣稱全部通過。輸出目錄必須是**尚未存在的新目錄**，再跑時換尾碼。`--origin author_local` 是操作者標記，不是驗證來源的密碼。

`demo` 產生 `OBSERVATIONS.json`、`REPORT.html`、六組 PID／stdout／stderr 與每步 SQLite 備份。A 同意、B 新行程查詢、C 更正、D 查詢、E 忘記、F 查詢；下一行程只接資料庫與階段，不讀前一步報告。確認由合成測試程式代送；不是 Gemini 或真人操作。

未備妥 Python 環境者先依 Day 12 README 安裝。Windows 改用虛擬環境的 `Scripts/python.exe`。Python 暫存位置另受 `TMPDIR` 控制，不由 `--out` 決定。

## 2. 店家工具與來源

`places.search_local_places(area='', dietary_type='', keyword='')` 是唯讀工具。資料為 `data/places.json`，快照版本 `vegfest-selected-20260927-v1`，**只選錄 2 筆，不是官方 50 家全部匯入**。

| 店家 | 欄位來源 | 使用範圍 |
|---|---|---|
| John手作蔬食 | 官方名單、縣府店家頁、店家平台菜單 | 菜單列有全素／奶素／蛋奶素品項；不是全店認證 |
| 和米素食 | 官方名單第 22 筆 | 一般蔬食選項；細分素別未採錄，不從店名推定 |

每個素別與地址欄位都記來源 ID。`data/places.json` 包含來源 URL、查閱日期與欄位適用範圍；不帶另一活動的優惠。公開名單圖僅人工選錄事實欄位，不把整張海報重新授權或重新散布。

`vegetarian` 表示蔬食但未細分類；`vegan / lacto / ovo_lacto / allium / friendly` 按已採錄類型精確比對。這不是完整飲食相容性推論器，不以「素」字推定全素，也不保證交叉接觸條件。空字串在獨立工具中為不限；**經 `TurnTools` 包裝時**，空字串才表示讀取已同意偏好。明示 `any` 一律只對本次解除飲食篩選，不修改長期值。

店家清單、集章期間與即時營業分開。公告為 2026-08-01 至 2026-09-30 17:00（Asia/Taipei）；本實作在截止時刻起回 `ended`，不刪店家。嘉年華日期是 10/3，不能拿來延長集章。測試用 `now` 明示時間，不修改系統時鐘。

`open_now / hours / coordinates / walking_distance_m / accessibility` 未核對，保留 `null`。只有「附近」時追問鄉鎮；未提供步行路線，不能保證「最近、現在有開、長輩少走路」。無符合資料與服務例外使用不同提示。

## 3. 同意生命週期

保存的是本帳號**一項找店家的飲食條件**，不是家人檔案。`PreferenceMemory` 以 `tenant_id + user_id` 產生文件識別；Session 不在索引裡。同帳號換 Session 可以取用，他人／其他租戶不可。

| 操作 | 實作 |
|---|---|
| 當次需求 | 工具的明示條件，偏好庫不變 |
| 長期需求 | `propose_dietary_memory` 提案，等待人按同意 |
| 查看 | `我的偏好`／固定 Postback；不依賴模型 |
| 更正 | 新提案＋新同意；同意前仍保留舊值 |
| 先不要 | 取消這張提案並提高版本，保留既有已同意值 |
| 忘記 | `忘記我的飲食偏好`／固定忘記按鈕立即移除值，提高版本 |

模型工具**不包含** `approve()`、任意資料庫寫入、owner 或 authorization 參數。自然語言被模型判成忘記時，也先給確認卡；固定明確的忘記命令則直接處理。

待同意前不寫偏好值，也不保存原句到偏好庫。提案保存在有期限的簽章 Postback 資料中：飲食 enum、原版本、原事件時間起算 300 秒、操作及 nonce。nonce 同時綁定事件與內容；簽章綁定帳號。簽章不是加密，收到／轉貼 token 不代表有權；後端仍依驗簽來源及當前 grant 核對。

儲存 collection `consented_preferences` 的正常欄位：`schema / revision / dietary_type / consented_at / last_nonce`。忘記後只留不含偏好值的版本與不透明 nonce，用來阻止舊卡恢復。舊同意卡的同鍵同內容可回原結果，內容不同或版本改變便失效。

## 4. 撤回不能只刪一個欄位

Day 14 重用原 Store，但新增專用 `PrivateLedger` 與 `process()` 接點：傳輸記錄只存 HMAC 指紋及處理狀態，不保存帶偏好的回覆計畫；新回合也不寫 `line_traces`。這是為了避免刪偏好後，舊的個人化回覆還被讀回或重送。它不回改 Day 12／13，也不自動清除前篇留下的舊紀錄。

模型每回合使用新的 `InMemorySessionService` Session，完成後刪除；不載入前次對話／摘要。已同意的值由後端唯讀取用，不先塞進模型 prompt。Function Tool 設定 `skip_summarization`，工具結果由固定程式呈現，不再把個人化結果送回下一次模型呼叫。

工具前後及 Reply 前重查偏好版本／當前權限；已觀察到修改或忘記便抑制舊結果。**這不代表能收回已交給 LINE 的網路請求或舊聊天訊息**，也不宣稱清除 SQLite 歷史頁、備份、服務請求、提供者保留資料。忘記代表本應用之後不再主動取用該偏好值。

不保存回覆計畫的代價是：回覆前的重試要重新核對、可能再讀資料；進入 sending 後結果不明則停止自動重送。沒有加入記憶體背景佇列，不把回覆失敗硬改為成功。

## 5. 真正 ADK、Firestore 與 Gemini 各自驗證

工具一回合限制一次，模型最多一次呼叫，18 秒候選 timeout；此界線是成本／範例範圍，不是手機 Webhook 時限保證。原同步少量白名單限制仍在，不能把它稱為高流量正式服務完成。

已有相符 SDK 時，真正 Runner＋腳本模型九項測試：

```bash
$PY -m examples.day14.verify --group adk --origin author_local --out out/day14/adk-01
```

這九項包含兩個真正 ADK Session ID、工具事件 ID／參數對應、提出記憶不寫入、無工具時拒絕、忘記後的條件，以及 ADK 公開 Context 範本實際展開、已保存偏好不進模型請求、ToolContext 不由模型提供等檢查。**腳本模型不是 Gemini 理解能力的結果。**

依 Day 11 文件啟動本機 Firestore Emulator，在另一終端機設定 `FIRESTORE_EMULATOR_HOST` 後：

```bash
export FIRESTORE_EMULATOR_HOST=127.0.0.1:8080
$PY -m examples.day14.verify --group emulator --origin author_local --out out/day14/emulator-01
```

只用 `demo-local-day14` 與每次隨機的隔離 namespace，四項契約不連正式雲端、不退回 SQLite。沒有 host 或 SDK 就非零退出。測試紀錄留在模擬器內，不刪整個 emulator／正式 project。

最後才由操作者核准至多四個真實 Gemini 開發回合。沿用固定的 `gemini-3.8-flash`、`LOW` 與私人金鑰，**不要為本篇更換模型或 SDK**：

```bash
# 固定系列模型；GOOGLE_API_KEY 或 GEMINI_API_KEY 已在私人環境。
export GEMINI_MODEL=gemini-3.8-flash
$PY -m examples.day14.live_check --model "$GEMINI_MODEL" --suite lifecycle --approve-live --out out/day14/live-01
```

此檢查有「單次蔬食、長期提案、新 Session 取用、忘記後再查」四個合成開發案例；同意動作明確由**測試程式**代送。記錄 prompt 與雜湊、資料版本、模型原文（不含 thought）、用量、請求／工具執行／回傳與實際參數；遇不符就停，不無限調提示後挑成功的一次。不是盲測／四種所有真實說法的準確率，更不是手機真人同意證明。這份含合成偏好的紀錄留在自己的私人輸出目錄，不直接上傳 Git。

### 本輪加強：讓模型理解有可追查的依據

`model_contract.py` 的規則不是自然語言分類器。它交給真正 Gemini 理解原句，工具綁定仍由後端執行。已存在的 `ScriptedInterpreter` 只是一個明標的測試替身；不能拿它的映射結果填進模型實測表。

實際 ADK 指令範本使用 `{day14_catalog_context}`，內容由 `session_state()` 注入公開資料版本與可查區域。Session state 另含內部偏好版本 `day14_preference_revision`；工具從 ADK 提供的 `ToolContext` 核對同一 Session／使用者／版本。**保存的飲食值不進這份 Prompt**，而是在 `TurnTools` 執行時補入空白 `dietary_type`。這是資料最小化的工具端 Context，不是把全部 ADK Memory Bank 打開。

Google Gen AI SDK 的 `Content`、`FunctionCall`、`GenerateContentConfig` 等型別用來描述請求／結果；真正模型呼叫仍由 ADK 的 Gemini adapter 執行，不額外再發一次直接 SDK 請求。模型固定為 `gemini-3.8-flash`；現有設定為 temperature=0、max_output_tokens=512、ThinkingLevel.LOW。套件 pin 保留前篇 `google-adk==2.9.1`、`google-genai==2.23.0`、`google-cloud-firestore==2.31.0`。不要自行替換模型或修改套件版本；pin 本身不代表已完成真正 SDK 整合。

`before_model_callback` 保存的是 **呼叫前的 contents/config 快照**，不是網路封包攔截。模型請求／工具執行／工具回傳用同一 call ID 與名稱核對，並比對原參數與回傳值；`tool_events` 再顯示有效搜尋條件及偏好版本。預期工具與預期值只在檢查程式，沒有被送給模型。

`live_check` 四個生命週期回合須檢查：模型先提出什麼、資料庫是否在模型呼叫後維持原狀、測試程式何時明示同意，以及下一個 Session 怎麼查。每次保留 SQLite 備份、直接 SELECT 的偏好列與檔案雜湊；它不是只拿 JSON 的 `passed` 互相背書。`model_inputs` 含本次原句，只供明示的合成測試使用；正常服務不持久保存它，不使用真實使用者資料做公開示範。

另有否定與轉述的 **獨立、可選** 四回合開發組。必須再次核准才執行，不會接在預設 lifecycle 後偷偷多呼叫：

```bash
$PY -m examples.day14.live_check --model "$GEMINI_MODEL" --suite intent_boundaries \
  --approve-live --out out/day14/live-boundaries-01
```

每次最多四回合，無自動改提示後重跑。`lifecycle` 與 `intent_boundaries` 都是公開開發題，不是 Day 18 保留評測，也不宣稱四題通過代表意圖理解全面過關。若 `execution_state` 為 `dependency_or_startup_failure`，讀原錯誤環境後處理；結果不符合就保留 failed，不能填成 successful。

## 6. 三個入口與手機驗收

「我要預約／你好／功能」直接回三按鈕，**不需要 Gemini 才能提供已知功能**：

- 查活動：執行原花壇歷史活動查詢。
- 查蔬食：選資料已有的區域，再讀取偏好查店家。
- 留下服務詢問：引導「新需求：…」，接回原確認與建單，不表示預約成立或已通知真人。

其他自由文字由真正 Gemini 選工具；例外仍標暫不可用，並提供三入口，而不是改稱資料不存在。

手機順序：先「今天想吃素，花壇有什麼店？」→「我的偏好」仍空；再「以後優先找蔬食，幫我記住」→看用途與期限→人按同意→再查花壇；更正蛋奶素後再查；忘記後再查並按舊同意卡。每步核對相同帳號的偏好文件、有效搜尋條件及訊息。嚴格素別可能查無資料；不是故障，更不是允許降級成未知素別。

放大字級、VoiceOver／TalkBack、LINE Message Validation API 各自記錄，不以存在 altText 代替驗收。Day 13 的已建單取消行為仍應保持。

## 7. 沿用 Cloud Run，而不是另建一套服務

先保留原 project／region／service、舊修訂版與流量，從自己的授權設定準備 `PROJECT_ID / REGION / SERVICE / OLD_REVISION / IMAGE_TAG / IMAGE_DIGEST / BUILD_CONTEXT`。沿用 `LOCAL_ACTOR_KEY`、namespace、Runtime SA、原授權與 Secret Manager 參照；不要重建它們，也不要把金鑰貼進命令或此文件。任意換簽章鍵會讓舊卡失效，也可能破壞前篇帳號綁定。

先通過上述本機／SDK／模擬器檢查，再由操作者核准建置與部署：

```bash
# BUILD_CONTEXT 必須是 Repo 外、尚未存在的目錄。
$PY -m examples.day14.build_context --out "$BUILD_CONTEXT"
docker buildx build --platform linux/amd64 --load -t "$IMAGE_TAG" "$BUILD_CONTEXT"
docker push "$IMAGE_TAG"
# 從本次 Artifact Registry 取得完整 digest 後填入 IMAGE_DIGEST。
gcloud run deploy "$SERVICE" --project "$PROJECT_ID" --region "$REGION" \
  --image "$IMAGE_DIGEST" --no-traffic --tag d14
# NEW_REVISION 取自真正部署輸出。比較 YAML，確認入口與原設定後再切流量。
gcloud run services update-traffic "$SERVICE" --project "$PROJECT_ID" --region "$REGION" \
  --to-revisions "$NEW_REVISION=100"
```

入口 `examples.day14.main:app`；`LOCAL_MODEL_MODE=gemini`、`GEMINI_MODEL=gemini-3.8-flash`，雲端 `LOCAL_BACKEND=cloud` 並無 `FIRESTORE_EMULATOR_HOST`，且原設定核准 `LOCAL_APPROVE_EXTERNAL=yes`。資料庫現有 `roles/datastore.user` 與原具名秘密存取權需核對，不假設這份檔案已設定 IAM。

建置來源只含必要 runtime、兩筆公開快照與 LICENSE，不含私人 evidence、tests、.env。每次保存 `SOURCE_MANIFEST.json`、實際相依版本與映像 digest。Docker build 成功、部署就緒與手機收到回覆是不同結果。

流量變更不是瞬間原子操作；看真正處理事件的修訂版。需回復時將舊修訂版設為 100%，再核對服務；這不撤銷資料。Day 12／13 版本沒有本篇的偏好入口，回復也不表示已執行忘記。**本章不提供自動 CD 或遠端寫入授權。**

## 8. CI 範圍與檔案

候選 `.github/workflows/day14.yml` 包含 core 與 flow 兩工作：102 項核心＋六行程演練；27 項 ASGI＋112 項前篇回歸。Push 到 main 或手動觸發，不是合併前強制閘。SDK、Emulator、Gemini、LINE、Cloud Run 不在此工作流；沒有自動部署。環境準備可能連網，但測試不用業務金鑰。是否已執行／通過看自己的實際 run，不從檔案存在推定。

主要檔案：`places.py` 公開資料與時效；`memory.py` 同意生命週期；`engine.py` 當回合工具；`model_contract.py` 路由政策／公開 Context；`trace_contract.py` 工具三聯核對；`adk_router.py` 真正 Runner；`messages.py` 固定卡片；`main.py` 傳輸接點；`demo.py` 六行程紀錄。資料定義與來源見 `data/places.json`。本次資料是最小可核對切片，不是全臺地點推薦器。


## 9. v2 交付時的實際驗證狀態

助理環境執行：102 核心＋27 ASGI＋112 前篇指定回歸＝241 項，失敗／錯誤／略過皆零；六個獨立 Python 行程演練另外記錄。102 核心含新28項政策／Context／三聯軌跡檢查，不是28次模型呼叫。完整第一次失敗與修正後紀錄保存於私人工作包；公開程式只放測試入口。

本環境缺少 `google.adk`、`google.genai` 與 Firestore SDK，ADK 九項未執行；Emulator 四項在缺少 host 的 setUp 即受阻，沒有打到資料庫。不得把這些 probe 算入通過總數。SDK 整組仍須在作者原環境安裝核對與 `pip check`；Gemini、LINE、Docker、Cloud Run、遠端 Day14 CI 尚未執行。

原始 v1 的通過結果是歷史交付紀錄；本段數字只指 v2 明示的測試範圍。這份候選是可交整合的起點，不是已發布或上線簽核。
