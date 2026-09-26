# Day 12｜Cloud Run 手動部署與新修訂版查回

這是候選命令指南，助理沒有執行建置、計費、IAM、LINE 或雲端操作。以下皆由作者在已核准的隔離測試專案操作。先完成 README 的核心、ADK、模擬器檢查；Docker build／pip check／實際雲端 smoke 各是新的驗證。

## 1. 先備與五類設定

需要作者確認：測試 LINE 頻道與白名單、專用 Google project／Firestore location／Cloud Run region、可用模型與 API 費用授權、Secret Manager 的具名數字版本、可用的 Docker／gcloud 操作環境。

建議專用測試 project，Firestore `(default)` Native database；不要把本例 datastore.user 給存有正式客戶資料的共用專案。服務持久 namespace 可用 `day11-d12-author-a`，沿用 Day 11 validator 的前綴；跨 revision 不變更。

以下變數是作者實值，不由範例猜測：

```bash
: "${PROJECT_ID:?請設定核准的專案}"
: "${REGION:?請設定 Cloud Run 區域}"
: "${FIRESTORE_LOCATION:?請設定 Firestore 位置}"
: "${ARTIFACT_REPO:?請設定容器儲存庫名稱}"
: "${SERVICE:?請設定本次測試服務名稱}"
: "${RUNTIME_SA:?請設定專用執行身分 email}"
gcloud version
docker version
```

建立資源是新外部操作，需作者授權。未存在的資源才建立；下列不是可忽略錯誤的 idempotent script：

```bash
gcloud services enable run.googleapis.com firestore.googleapis.com artifactregistry.googleapis.com secretmanager.googleapis.com --project "$PROJECT_ID"
gcloud firestore databases create --project "$PROJECT_ID" --database='(default)' --location="$FIRESTORE_LOCATION" --type=firestore-native
gcloud artifacts repositories create "$ARTIFACT_REPO" --project "$PROJECT_ID" --location "$REGION" --repository-format=docker
```

## 2. 人的部署身分和容器身分分開

由具管理權限的操作者建立專用 SA，例如 local-day12-runtime；將實際 email 設為 RUNTIME_SA。不要使用 Owner／Editor 讓應用通過。

```bash
gcloud iam service-accounts create local-day12-runtime --project "$PROJECT_ID" --display-name='LOCAL Day 12 test runtime'
gcloud projects add-iam-policy-binding "$PROJECT_ID" --member="serviceAccount:$RUNTIME_SA" --role=roles/datastore.user
```

`roles/datastore.user` 是提供資料讀寫的預定義角色，權限不只一個集合；專用測試 project 限縮資料影響面，不把 namespace 當授權邊界。Python Firestore server SDK 採 IAM，客戶端 Firestore rules 不替它做授權。[3]

人的部署者需要相應 Cloud Run 部署權限、對此 runtime SA 的 actAs，以及映像儲存庫的存取；設定公開 invoker IAM 另需政策修改權。不要因某步不足直接加 Editor。此指南保留人工部署；WIF 是日後 GitHub OIDC 換取短效 Google 憑證的入口，不是這次 runtime ADC 的別名。[2][8]

## 3. 秘密與資料準備

在 Secret Manager 建立／選用五項私人 secret：LINE channel secret、LINE access token、穩定 actor HMAC key、測試白名單、Gemini Developer API key。每項各授 runtime SA 的 `roles/secretmanager.secretAccessor`，不要在整個 project 一次給所有 secret。

```bash
# 對每個已核准的 SECRET_NAME 個別執行，保存 policy 結果。
gcloud secrets add-iam-policy-binding "$SECRET_NAME" --project "$PROJECT_ID" \
  --member="serviceAccount:$RUNTIME_SA" --role=roles/secretmanager.secretAccessor
```

用數字版本，不用 latest，將對應字串存為 SECRETS_BINDINGS（內容是名稱與版本，不是 secret 值）：

```bash
# 請換成你實際存在的名稱／數字版本。
SECRETS_BINDINGS='LINE_CHANNEL_SECRET=local-line-channel-secret:1,LINE_CHANNEL_ACCESS_TOKEN=local-line-token:1,LOCAL_ACTOR_KEY=local-actor-key:1,LINE_ALLOWED_USER_IDS=local-allowed-users:1,GOOGLE_API_KEY=local-gemini-key:1'
```

保留 `LOCAL_ACTOR_KEY` 與 namespace 不變，否則無法以同一 logical Session 找回舊任務。不要把 service-account JSON 複製到映像；Cloud Run 用指定 runtime SA 的 ADC 讀 Firestore。[2][4]

`cloud-runtime.example.yaml` 複製到 Repo 外，設定 project、namespace、bot destination、作者驗過的 Gemini model ID、來源版本。不要把 `FIRESTORE_EMULATOR_HOST` 或 `GOOGLE_APPLICATION_CREDENTIALS` 帶到 Cloud Run。

上線前用作者自己的本機 ADC 核准登入與相同私人設定執行 seed。`admin` 不會呼叫模型／LINE，但仍會建立 grant/catalog 文件；沒有 HTTP seed 端點。

```bash
# 認證由作者自行完成；不要把本機 ADC 檔交給他人。
gcloud auth application-default login
# 在同一終端機載入作者自己的 Repo 外私人設定，backend=cloud、核准=yes。
python -m examples.day12.admin seed --approve-seed
```

來源資料只含歷史活動地點，沒有集合點，手機必須保留未知。若作者要示範查到真正集合點，需先提供有來源的新採用資料並重新核對資料契約，不要把 venue 欄偷偷改名。

## 4. 小型可追溯建置

整合 Day 12 後先在本機提交作者確認的版本（不是要求助理 Push）。產生建置 context；只會列出程式與相依，沒有私人 evidence／金鑰。

```bash
python -m examples.day12.build_context --out "$BUILD_CONTEXT"
docker buildx build --platform linux/amd64 --load -t "$IMAGE_TAG" "$BUILD_CONTEXT"
docker run --rm --entrypoint python "$IMAGE_TAG" -m pip check
```

`BUILD_CONTEXT` 須為 Repo 外尚不存在的目錄；`IMAGE_TAG` 格式為 `REGION-docker.pkg.dev/PROJECT/REPOSITORY/local-day12:作者版本`。保存 context 的 SOURCE_MANIFEST.json、base image digest、resolved pip list。工作目錄有未提交改動時，不只用 git HEAD 宣稱那些 bytes 已受測。

作者核准上傳後：

```bash
gcloud auth configure-docker "${REGION}-docker.pkg.dev"
docker push "$IMAGE_TAG"
gcloud artifacts docker images describe "$IMAGE_TAG" --project "$PROJECT_ID" --format='value(image_summary.digest)'
```

取得 digest 後設定 `IMAGE_DIGEST=REGION-docker.pkg.dev/PROJECT/REPOSITORY/local-day12@sha256:...`。部署用 digest，不用會被覆寫的 tag。

## 5. 第一個雲端修訂版

```bash
: "${IMAGE_DIGEST:?需要實際推送的 image digest}"
: "${ENV_FILE:?Repo 外 cloud-runtime.yaml 路徑}"
: "${REV_A_SUFFIX:?例如 d12a加上唯一短時間字串}"
gcloud run deploy "$SERVICE" --project "$PROJECT_ID" --region "$REGION" \
  --image "$IMAGE_DIGEST" --service-account "$RUNTIME_SA" \
  --revision-suffix "$REV_A_SUFFIX" \
  --allow-unauthenticated --ingress all \
  --min-instances 0 --max-instances 2 --min 0 --max 2 \
  --memory 512Mi --cpu 1 --concurrency 4 --timeout 60s \
  --port 8080 --execution-environment gen2 \
  --env-vars-file "$ENV_FILE" --set-secrets "$SECRETS_BINDINGS" \
  --startup-probe='httpGet.path=/healthz,httpGet.port=8080,timeoutSeconds=2,periodSeconds=5,failureThreshold=24' \
  --liveness-probe='httpGet.path=/healthz,httpGet.port=8080,timeoutSeconds=2,periodSeconds=30,failureThreshold=3'
```

`min/max-instances` 是 revision 層級，`min/max` 是 service 層級。這裡兩層都明示；上限仍不是帳單硬上限，別忽略模型／Firestore／artifact／logs 費用。[5]

LINE 無法替 Webhook 附 Cloud Run IAM token，因此測試 endpoint 允許外部存取；**業務入口仍強制 LINE 原始簽章、destination、direct-user 白名單與存放中的 grant**。組織政策不允許公開時，先停下來確認入口方案，不擅自放寬政策。

```bash
SERVICE_URL="$(gcloud run services describe "$SERVICE" --project "$PROJECT_ID" --region "$REGION" --format='value(status.url)')"
curl --fail --max-time 10 "$SERVICE_URL/healthz"
gcloud run services describe "$SERVICE" --project "$PROJECT_ID" --region "$REGION" --format=json > "$EVIDENCE/service-a.json"
```

將測試 LINE 頻道 Webhook URL 設為 `SERVICE_URL/webhook`、啟用 Use webhook；關閉會重複回答的內建自動回覆，保留適當歡迎訊息。確認 Destination 是 bot 的 userId，不是頻道ID。設定與測試皆在作者自己的頻道完成。

## 6. 手機驗收

依序輸入：「花壇場次在哪裡集合？」→ 看工具資料欄位與未知 →「需要協助：需要手語志工支援」→ 點原確認卡的「確認送出」→ 看實際 request ID。

從 Firestore 直接讀 `requests/{operation_id}`，核對原句、確認、單號。記下相關 Cloud Logging `BUSINESS_RESULT` 的 event key、revision、boot ID；模型 query 原文與 tool trace 存在私有 `line_traces`，需要另外匯出。

LINE API 200 代表平台接受，不代替手機截圖；request 的 pending_human_review 代表待處理標記，不代表已有真人收到。

## 7. 同映像替換修訂版：只變更執行行程，不重新 seed

先保存 A 的實際 revision 名稱。再用相同 image digest／secret versions／namespace／Actor key 部署 B，重複第 5 節命令但 suffix 換成新的 REV_B_SUFFIX，加入 `--no-traffic`。

```bash
# 完成上段同規格的新 revision 部署後，讀真正名稱，不自行猜 PID。
REV_B="$(gcloud run services describe "$SERVICE" --project "$PROJECT_ID" --region "$REGION" --format='value(status.latestReadyRevisionName)')"
gcloud run services update-traffic "$SERVICE" --project "$PROJECT_ID" --region "$REGION" --to-revisions="$REV_B=100"
gcloud run services describe "$SERVICE" --project "$PROJECT_ID" --region "$REGION" --format=json > "$EVIDENCE/service-b.json"
```

在手機送一則新的「剛才那單有成功嗎？」。核對它真正到 B，而不是只看到 B 部署成功；新 BUSINESS_RESULT 應有不同 boot_id/revision、相同 request_id／operation_id。A 不必消失才能證明 B 沒靠 A 的記憶體。

這是「修訂版替換後讀回」，不是實例故障，也不是自然縮容至零。若要另做自然 scale-to-zero，需保存 instance count 時間序列曾為零、下一次請求的新 process log；不要用等待固定幾分鐘替代觀察。[1]

## 8. 排錯與停止

| 情況 | 先查 |
|---|---|
| /healthz 失敗 | 容器 $PORT/0.0.0.0、dependency-lock、缺設定、secret 讀取權 |
| LINE 401 | 原始 bytes、channel secret、signature header，不先 parse/重新 JSON 編碼 |
| LINE 403 | bot destination、白名單、grants；不要在 webhook 重新 grant |
| 已建單但手機沒看到 | LINE_REPLY_RESULT／reply-token 有效期；用新 status 事件讀原單，不另建 |
| query 暫不可用 | 原型選的模型是否可用、API key、ADK smoke、私人 trace／型別錯誤，不換成假結果 |
| 預期讀到原單卻找不到 | Actor key／namespace／project 是否和 A 相同；有沒有真的切到新 revision |
| Firestore 403 | runtime SA 的 IAM；不是去改公開 firestore.rules |

停止測試前先保存採用畫面、logs、原始文件與環境設定，撤除測試 Webhook 或取消白名單。刪服務、image、secret、Firestore namespace 都是另外的破壞性操作，只刪本次具名範圍；父文件刪除不會代刪所有子集合。保持 min=0 也不等於清除全部費用。

沒有提供一鍵刪除整個 project 的腳本。

## 官方依據（2026-09-25 核對）

1. https://docs.cloud.google.com/run/docs/container-contract
2. https://docs.cloud.google.com/run/docs/securing/service-identity
3. https://docs.cloud.google.com/firestore/native/docs/security/iam
4. https://docs.cloud.google.com/run/docs/configuring/services/secrets
5. https://docs.cloud.google.com/sdk/gcloud/reference/run/deploy
6. https://developers.line.biz/en/docs/messaging-api/verify-webhook-signature/
7. https://developers.line.biz/en/docs/messaging-api/receiving-messages/
8. https://docs.cloud.google.com/iam/docs/workload-identity-federation-with-deployment-pipelines
