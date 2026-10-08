# Day 24｜來源與實作範圍

核對日 2026-10-08。以下文件支持 API 語意與定價依據。

| 主題 | 來源 | 本篇用途 |
|---|---|---|
| 原題集 | https://github.com/jarsing/local-service-agent-for-line/blob/95fa11b968c4eb86b4c37c5ca62f1f94fd8d4d36/eval/local20.json | 固定 20 題、9 個 live IDs 與原問句 |
| 原 harness | https://github.com/jarsing/local-service-agent-for-line/tree/95fa11b968c4eb86b4c37c5ca62f1f94fd8d4d36/examples/day18 | 不以新增形式檢查替代原 20 題應用驗收 |
| 原路由政策 | https://github.com/jarsing/local-service-agent-for-line/blob/95fa11b968c4eb86b4c37c5ca62f1f94fd8d4d36/examples/day14/model_contract.py | 保留同意、未知與不支援的分層責任；本篇新提示另外版本化 |
| Function Calling | https://ai.google.dev/gemini-api/docs/function-calling | 模型要求不等於 Python 已執行 |
| ThinkingConfig／UsageMetadata | https://ai.google.dev/api/generate-content | budget 與 level 分開，用量來源不缺欄補零 |
| SDK | https://googleapis.github.io/python-genai/ | Client、GenerateContentConfig 與 SDK 物件序列化；已完成 15 筆真實調用序列化 |
| 價格 | https://ai.google.dev/gemini-api/docs/pricing#gemini-3.8-flash | 文字 Standard 輸入 0.75／輸出含 thinking 3.75 USD 每百萬（依 rate_card.json） |
| 配額 | https://ai.google.dev/gemini-api/docs/rate-limits | 序列呼叫也不保證符合專案其他流量的限制 |
| 回滾 | https://docs.cloud.google.com/run/docs/rollouts-rollbacks-traffic-migration | Revision 流量切換，不等於撤回資料副作用 |
| 歷史 A/B | https://github.com/jarsing/local-service-agent-for-line/blob/95fa11b968c4eb86b4c37c5ca62f1f94fd8d4d36/examples/day21/fixtures/ab_benchmark_raw.json | 明示不可比較，不拿摘要冒充本篇原回應 |

本篇已取得 15 筆真實 Gemini 3.8 Flash 模型調用原始紀錄（9 題路由全數通過、6 列成對 A/B 成本量測），保存於 `examples/day24/evidence/`；合成回應僅用於單元測試替身。後端重播與原 live 事件分開標記，未經真人與通道驗收前 `safe_to_deploy` 保持 false。
