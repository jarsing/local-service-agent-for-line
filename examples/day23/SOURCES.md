# Day 23｜來源與宣告範圍

核對日：2026-10-06。下列文件支持產品能力；本案是否實際部署需另有證據。`stack_options.json` 是設計集合，不是從雲端控制台擷取的實況。

| 主題 | 官方來源 | 支持範圍 |
|---|---|---|
| AI Studio | https://ai.google.dev/gemini-api/docs/ai-studio-quickstart | 試提示、System Instructions、執行設定、取得程式碼 |
| 模型端點 | https://ai.google.dev/gemini-api/docs/migrate-to-cloud | Developer API 與 Google Cloud 路徑、統一 Gen AI SDK；當前頁使用 Gemini Enterprise Agent Platform 名稱 |
| ADC | https://docs.cloud.google.com/vertex-ai/generative-ai/docs/start/gcp-auth | Cloud 模型路徑之身分驗證；不能推出只要改端點就等效 |
| 模型治理能力 | https://docs.cloud.google.com/vertex-ai/generative-ai/docs/security-controls | 按模型／功能核對服務周界等控制，不保證全部功能都適用 |
| Antigravity | https://www.antigravity.google/docs/home | 桌面、CLI、SDK、IDE 是不同介面；SDK 並非虛構產品 |
| Antigravity SDK | https://www.antigravity.google/docs/sdk/overview | Python runtime harness、工具與 hooks；本案未聲稱已改用它 |
| ADK | https://google.github.io/adk-docs/runtime/ | ADK 執行介面、runtime 設定與事件流程 |
| LOCAL 既有編排 | https://github.com/jarsing/local-service-agent-for-line/blob/61a2dca4a875bcbb1fcf595f6b9c2e98bac402f8/examples/day14/adk_router.py | 實際 import google.adk，使用 Runner／LlmAgent／ToolContext；本案既有服務脈絡 |
| 替代框架持久化 | https://docs.langchain.com/oss/python/langgraph/persistence | LangGraph 有 checkpoint 持久化，不能概稱其他框架只在記憶體保存 |
| Cloud Run 縮放 | https://docs.cloud.google.com/run/docs/about-instance-autoscaling | 預設無流量可縮到零；maximum instances 與等待亦影響服務 |
| 最小實例 | https://docs.cloud.google.com/run/docs/configuring/min-instances | 暖實例與閒置計費取捨，非任意回應時間保證 |
| 計費範圍 | https://cloud.google.com/run/pricing | Cloud Build／Artifact Registry 等費用另列；scale-to-zero 不等於整個專案零帳單 |
| Cloud SQL | https://docs.cloud.google.com/sql/docs/mysql/connect-run | 支援 Cloud Run 接入與連線池管理，不因 Webhook 就不適用 |
| Firestore 強一致讀取 | https://firebase.google.com/docs/firestore/understand-reads-writes-scale | 預設讀取強一致，也有其他明示讀取選項 |
| Firestore 交易隔離 | https://firebase.google.com/docs/firestore/transaction-data-contention | 交易可序列化隔離、衝突；不同版本／客戶端機制須分開 |
| Firestore 交易重跑 | https://firebase.google.com/docs/firestore/manage-data/transactions | 函式可能重跑，寫入共同提交；外部副作用不應塞進回呼 |
| LINE HTTP timeout | https://developers.line.biz/en/docs/messaging-api/check-webhook-error-statistics/ | request_timeout 是兩秒內未收到回應 |
| LINE 非同步建議 | https://developers.line.biz/en/docs/messaging-api/receiving-messages/ | 驗簽後處理，事件採非同步；不是模型必須兩秒回答 |

Cloud Firestore／Cloud SQL 的能力欄只用於這份候選設計。Firestore 方案的 `relational_joins=false` 表示本篇不以它提供關聯式查詢路徑，不是宣稱不能另外設計資料分析流程。Vertex 方案的 `model_perimeter=true` 是設計需求，仍待模型、區域、IAM 與周界驗收。

沒有從這些官方文件推導 LOCAL 已部署 WIF、私網、暖實例、可靠佇列或 Day 22 雲端控制面。
