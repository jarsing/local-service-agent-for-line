# Day 21｜一條 Trace 找到問題：從模型工具呼叫一路追到後端結果

建立結構化追蹤核對器（`trace_audit.py`），驗證單一請求跨 LINE Webhook、Gemini 模型工具呼叫、本地執行、資料庫稽核與前端呈現的完整因果事件鏈，落實證據優先與多層缺陷診斷。

[五分鐘重現與驗收](../../examples/day21/README.md)｜
[追蹤核對與日誌映射器](../../examples/day21/trace_audit.py)｜
[追蹤契約自測套件](../../examples/day21/test_trace_audit.py)

前篇：[Day 20](https://ithelp.ithome.com.tw/articles/10420729)；本篇待作者發布後補上正式連結。

離線合成回放、結構化日誌映射與雲端 Trace 分開驗證。
English overview: Trace audit contract for LOCAL, linking Gemini tool requests, execution dispatch, database probes, and presentation rendering into an inspectable causality chain aligned with Google Cloud Logging and Cloud Trace.
