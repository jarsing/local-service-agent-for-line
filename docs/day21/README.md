# Day 21｜一條 Trace 找到問題：從模型工具呼叫一路追到後端結果

建立結構化追蹤核對器（`trace_audit.py`）：以合成事件驗證工具要求、本地執行、資料庫稽核與呈現四段契約，並接上一筆直接 SDK 呼叫的 Gemini 決策回應（下游事件依契約重建），落實證據優先與多層缺陷診斷。

[五分鐘重現與驗收](../../examples/day21/README.md)｜
[追蹤核對與日誌映射器](../../examples/day21/trace_audit.py)｜
[追蹤契約自測套件](../../examples/day21/test_trace_audit.py)

前篇：[Day 20](https://ithelp.ithome.com.tw/articles/10420729)；本篇：[Day 21](https://ithelp.ithome.com.tw/articles/10421328)。

離線合成回放、結構化日誌映射與雲端 Trace 分開驗證。
English overview: Trace audit validator for LOCAL that checks tool request, local execution, database audit and presentation events against a contract using synthetic replays, plus one directly captured Gemini decision (downstream events reconstructed per contract), and a log-field mapping aligned with Cloud Logging.
