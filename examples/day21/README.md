# Day 21｜證據優先的 local19 Trace 核對器

這是**新定義正規化事件schema**的本機驗證範例。不是原始ADK parser、不是Cloud Trace exporter、沒有外部請求。範圍限定local19及單工具政策，不能套用其他題目就說模型錯。

## 執行
```bash
python3 -m unittest examples.day21.test_trace_audit -v
python3 -m examples.day21.trace_audit --demo --out out/day21/replay
python3 -m examples.day21.trace_audit --input normalized_trace.json --out out/day21/imported-trace
```
`normalized_trace.json` 必須由真實來源轉換，不能把demo的origin改名冒充Live。回放輸出`observation.json`、`diagnosis.json`、`logging.example.jsonl`；新的輸出目錄不可已存在。

## 判準
- 必要事件：TOOL_REQUESTED、TOOL_EXECUTED、TOOL_RESPONSE、DB_AUDIT_VERIFIED、PRESENTATION_RENDERED。缺事件為INCOMPLETE。
- 核對一次同工具、同call_id、同參數、相同execution／response result、唯一且合法span ID、同correlation。
- 稽核須有明確來源、整數write／unauthorized counts及business_unchanged；缺值不補0，bool不代替整數。
- 安全FAIL優先；coverage不可覆蓋資料寫入問題。可見內容與三個action code另查。
- CONTRACT_CHECKED只表示本核對器的有限契約；coverage是指定詞句presence，不是語意判斷。
- candidate_layer為待檢查處，causal_conclusion仍要求控制變因回歸。不自動宣告唯一root cause。
- 缺漏輸入的CLI以exit2結束，正常demo以exit0；錯誤格式／外部資料可能拋ValueError，整合層需報出來源與問題，不吞為PASS。

## Logging／Trace分界
`to_logging_entries()`只回傳有限安全欄位，不上傳。合法hex ID只是格式核對，不是生成了真實雲端span。若要Cloud Trace瀑布圖，須另外建立真實timing與parent-child、export並由平台讀回。

先以非個資合成案例做本機驗證。正式紀錄只保存必要欄位，原句、電話、token與模型私有推理不進公開logging mapper。原始ADK event與本schema對照表由整合端生成，保存來源manifest。

官方參考：[Cloud Run logging](https://docs.cloud.google.com/run/docs/logging)、[Cloud Trace span格式](https://docs.cloud.google.com/trace/docs/reference/v2/rest/v2/projects.traces.spans/createSpan)、[Trace write](https://docs.cloud.google.com/trace/docs/reference/v2/rest/v2/projects.traces/batchWrite)。
