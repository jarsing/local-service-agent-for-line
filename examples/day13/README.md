# Day 13｜LINE Flex 的狀態與安全操作

將 Day 12 的待確認、已保存回條與狀態提示，換成固定 Flex 模板。模型不產生卡片結構；後端仍決定哪些操作可以執行。

本目錄沿用 `examples/day12/` 與更早的確認／儲存服務。基準版本為 `297f1a99b2486c25e6628f8f6745daccd4e743e0`；整合時保留所有前篇，不以本目錄覆蓋 Day 12。本篇對應鐵人賽文章：[Day 13｜LINE Flex 的狀態與安全操作](https://ithelp.ithome.com.tw/articles/10417809)。

## 1. 最小開始

從 Repo 根目錄執行。僅模板測試使用 Python 標準函式庫：

```bash
python3 -m unittest examples.day13.test_flex -v
```

完整本機檢查沿用 Day 12 已可用的環境，不另外升級 SDK：

```bash
PY=examples/day12/.venv/bin/python
$PY -m examples.day13.verify --group all --out /tmp/local-day13-check-01
$PY -m examples.day13.demo --out /tmp/local-day13-scenarios-01
```

若還沒有 Day 12 環境，先依 [Day 12 操作說明](../day12/README.md) 安裝。本篇沒有新的第三方相依套件。檔名以你的實際 Python 路徑為準，Windows 使用該環境的 `Scripts/python.exe`。

`verify` 的 renderer 群組是本篇固定模板單元測試；integration 是簽章 ASGI＋原服務＋SQLite 與建置清單檢查；previous 重跑 Day 12 核心。全數通過只支持上述範圍，不是 LINE API 或 Firestore 雲端結果。

原有真正 ADK 三項另外執行；缺相依即非零退出，不能略過後說前篇 48 項全部通過：

```bash
$PY -m examples.day12.verify --group adk --origin author_local --out /tmp/local-day13-previous-adk-01
```

## 2. 卡片與原狀態

| 來源狀態 | 呈現 | 操作 |
|---|---|---|
| awaiting_confirmation | 待確認／尚未建單；原 expires_at 的臺灣時間 | confirm:cid、cancel:cid、text:cid |
| request_created／already_created + pending_human_review | 詢問已保存／找到原詢問，待人工覆核、尚未通知窗口 | status:cid、text:cid |
| pending_verification | 結果待查證，不顯示未核實單號 | 有原 cid 就查原任務，無 cid 則明標查目前任務 |
| expired／cancelled／superseded | 具名失效原因 | 不提供確認或取消寫入按鈕 |
| 欄位缺漏／不支援狀態 | 顯示結果待核對 | 中性提示，不從模型文字補成功 |

`messages.py` 的來源必須是已通過應用端授權的後端結果。型別檢查本身不是授權。資料只進入固定文字欄位，extra layout／action／URL 不合併到模板。詢問原文完整保留並標記為使用者提供；本篇不宣稱擋住所有語意或社交工程攻擊。

一份有效確認只有原來的期限。重畫卡片、切換文字版，不會更新 `expires_at`，也沒有客戶端即時倒數。

確認前取消不寫 request。已建立後按舊取消，只讀回原單並提示「這個按鈕不會撤銷已建立的請求」。目前任務被新需求取代後，舊卡的確認／取消／綁定查詢均回 superseded，不把新任務冒充舊單。這是目前任務策略，不是歷史單據搜尋。

## 3. 模板預覽與 LINE 物件驗證

匯出明標為合成的 JSON：

```bash
$PY -m examples.day13.export_samples --out /tmp/local-day13-samples-01
```

`confirmation.json`、`receipt.json`、`pending.json` 等可供 LINE Flex Simulator 檢視；Simulator 中填入的是 message 的 `contents` 或按該介面的輸入格式貼入。`*.text.json` 是相同狀態的純文字回覆。`req-SYNTHETIC-001` 等代號明確是範例，沒有對應真正資料庫操作。不要拿這份範例按鈕測正式確認流程。

本機 validator 只涵蓋本篇輸出的元件子集，內部預算為 altText 350 UTF-16 units、postback data 200 個 ASCII 字元以內、bubble 24,000 bytes。這些是本篇保守預算，不是完整 LINE JSON Schema。

作者核准後可送一個真正 LINE 驗證請求（不是發聊天訊息）：

```bash
# LINE_CHANNEL_ACCESS_TOKEN 由私人環境提供，不放在命令文字或 Repo。
$PY -m examples.day13.validate_line \
  --file /tmp/local-day13-samples-01/confirmation.json \
  --out /tmp/local-day13-confirmation-validated.json \
  --approve-line-validation
```

再核對 receipt、pending 與 expired 的代表模板。API 接受訊息物件，不代表按鈕有業務權限，也不代表手機、放大字體或螢幕報讀已驗過。

`altText` 包含狀態、適用單號與下一步；可輸入「文字版」繞過 Flex。文字版的確認也保留原 cid。`wrap/scaling` 與顏色對比檢查不等於完整無障礙認證，VoiceOver／TalkBack 依實際裝置另記結果。

## 4. 如何接回 Day 12

新入口為 `examples.day13.main:app`。

`bridge.FlexApplication` 繼承 Day 12 Application：原 `process()`、驗簽、白名單、EventLedger 與 LineReply 都保留。原 `route()` 先取得已核對的結果，再換呈現；一般 Gemini 活動查詢仍是原文字結果，不為每個按鈕呼叫模型。

新增唯讀 postback：`status:<cid>` 與 `text:<cid>`。`read_bound_status()` 先比對目前任務，再讀該 cid 的原參數，讀後再次核對 active task。它不發同意、不建單，也不發明新送出鍵。此結果只是當下觀察；真正寫入時由原 decide/create 重新檢查。

舊 Day 12 `status` 仍指向目前任務。新卡的 status:cid 是綁定這筆；兩者標籤有區分。不能只改 messages.py，卻讓新的唯讀路由在雲端成為 unsupported_postback。

原傳輸仍是少量白名單同步示範，工作與 Reply 在 HTTP200 前完成。沒有新增記憶體背景佇列、Push API 或真人通知。

## 5. 沿用現有 Cloud Run，一次更新

這些命令會建置、推送並更新雲端，必須由操作者確認帳戶、費用與目前服務。不要為 Day 13 重建 project、Firestore、Service Account 或秘密。

先記錄既有 service、region、project、Day 12 修訂版與流量。使用同一套 Day 12 的私人設定，保持 namespace、LOCAL_ACTOR_KEY、授權與秘密引用不變。下列 shell 變數都由操作者填入自己已核對的值，不直接複製示意名稱到別的專案。

```bash
# PROJECT_ID、REGION、SERVICE 與 OLD_REVISION 取自目前服務，先核對。
gcloud run services describe "$SERVICE" --project "$PROJECT_ID" --region "$REGION" --format=json

# BUILD_CONTEXT 是 Repo 外尚不存在的目錄；IMAGE_TAG 是已核准 Artifact Registry 的新標籤。
$PY -m examples.day13.build_context --out "$BUILD_CONTEXT"
docker buildx build --platform linux/amd64 --load -t "$IMAGE_TAG" "$BUILD_CONTEXT"
docker push "$IMAGE_TAG"
```

本篇 build_context 先沿用 Day 12 檔案白名單，再加入 Day 13 runtime，並把容器入口改成 `examples.day13.main:app`。不加入測試、私人 evidence、.env 或編輯規則。上面的離線檢查只驗匯出清單，Docker build 是否成功要另看真正建置結果。

取得本次 Artifact Registry 的完整 image digest，存入 `IMAGE_DIGEST`；不要用文章裡的截短值。先部署到既有服務的新修訂版，暫不轉流量，核對執行身分與環境後才切換：

```bash
gcloud run deploy "$SERVICE" --project "$PROJECT_ID" --region "$REGION" \
  --image "$IMAGE_DIGEST" --no-traffic --tag d13

# NEW_REVISION 取自此次真實部署輸出；確認是 Day 13 入口且沿用正確環境。
gcloud run services update-traffic "$SERVICE" --project "$PROJECT_ID" --region "$REGION" \
  --to-revisions "$NEW_REVISION=100"
```

沿用既有服務時上述部署保留原有設定；仍須比較修訂版 YAML 確認環境、身分、資源與原秘密引用。Cloud Run 流量切換不是即時原子交棒，實際接受訊息的修訂版看 log。需要回復時，用相同 update-traffic 命令把 `OLD_REVISION` 設為100%，不刪資料或重算確認。

Day 12 的離線資料、手機圖與舊修訂版是歷史成果，保存不動；本次只增加新的 Day 13 驗證。LINE Webhook URL 可維持原值。

## 6. 手機最小驗收

先用現有白名單帳號建立一份新教學需求，再用下面順序做；每組使用不同測試任務，原文不要含真人個資。

1. 正常確認：看完原文與期限，確認後收到待人工覆核卡；從 Firestore 或既有管理工具核對同一 request。
2. 再按一次：回到同一張確認卡再按；新事件仍是同一 request，確認紀錄與筆數不增加。
3. 取消後再確認：另一份任務先取消，再按原確認；仍取消、無 request。
4. 過期：另一份任務等待原五分鐘，穿插做其他非新需求操作；再點舊卡不得新增。不要只看卡片文案，自資料確認 expires_at 原值。
5. 新需求後舊卡：先A，再用「新需求：」建立B；A的確認／取消／查這筆不得改動B。
6. 文字版：確認前、回條後各看一次，同 cid／單號／原期限，沒有重新同意。
7. 觀察字級、單號折行與按鈕可點性；使用哪台裝置、是否真的試了 VoiceOver／TalkBack，按實際結果記錄。

`pending_verification` 已有離線故障注入與模板；沒有取得真實雲端 pending 畫面，就不要把合成圖稱為線上故障。也不必為本篇破壞雲端資料庫或延遲模型來製造事故。

## 7. 來源

- [LINE Flex](https://developers.line.biz/ja/docs/messaging-api/using-flex-messages/)
- [LINE 訊息 API 與 Postback](https://developers.line.biz/ja/reference/messaging-api/)
- [LINE 2023 字級 scaling 更新](https://developers.line.biz/en/news/2023/#flex-message-update-4-released)
- [W3C：不要只靠顏色](https://www.w3.org/WAI/WCAG22/Understanding/use-of-color.html)
- [Cloud Run 流量切換](https://docs.cloud.google.com/run/docs/rollouts-rollbacks-traffic-migration)

公開 GitHub Actions 是否包含本篇，需看實際 workflow 與 run；本目錄不自行新增自動部署，也不以本機測試結果宣稱 CI 已執行。
