# Day 24｜來源與實作範圍

核對日2026-10-07。以下文件支持API語意；沒有證明本案已執行Live請求或雲端部署。

| 主題 | 來源 | 本篇用途 |
|---|---|---|
| 原題集 | https://github.com/jarsing/local-service-agent-for-line/blob/95fa11b968c4eb86b4c37c5ca62f1f94fd8d4d36/eval/local20.json | 固定20題、9個live IDs與原問句 |
| 原harness | https://github.com/jarsing/local-service-agent-for-line/tree/95fa11b968c4eb86b4c37c5ca62f1f94fd8d4d36/examples/day18 | 不以新增形式檢查替代原20題應用驗收 |
| 原路由政策 | https://github.com/jarsing/local-service-agent-for-line/blob/95fa11b968c4eb86b4c37c5ca62f1f94fd8d4d36/examples/day14/model_contract.py | 保留同意、未知與不支援的分層責任；本篇新提示另外版本化 |
| Function Calling | https://ai.google.dev/gemini-api/docs/function-calling | 模型要求不等於Python已執行 |
| ThinkingConfig／UsageMetadata | https://ai.google.dev/api/generate-content | budget與level分開，用量來源不缺欄補零 |
| SDK | https://googleapis.github.io/python-genai/ | Client、GenerateContentConfig與SDK物件序列化；本次Live未驗 |
| 價格 | https://ai.google.dev/gemini-api/docs/pricing#gemini-2.5-flash | 文字Standard輸入0.30／輸出含thinking2.50 USD每百萬 |
| 配額 | https://ai.google.dev/gemini-api/docs/rate-limits | 序列呼叫也不保證符合專案其他流量的限制 |
| 回滾 | https://docs.cloud.google.com/run/docs/rollouts-rollbacks-traffic-migration | Revision流量切換，不等於撤回資料副作用 |
| 歷史A/B | https://github.com/jarsing/local-service-agent-for-line/blob/95fa11b968c4eb86b4c37c5ca62f1f94fd8d4d36/examples/day21/fixtures/ab_benchmark_raw.json | 明示不可比較，不拿摘要冒充本篇原回應 |

本篇沒有取得新的Google模型原始成績；所有成功的合成回應只用於測試。後端重播與原live事件分開標記。公開檔案雜湊可辨識內容，不能證明造訪API的事實。
