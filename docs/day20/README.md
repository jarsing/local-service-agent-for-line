# Day 20｜模型設定、延遲與每項任務成本：品質先過關，再談快與省

建立來源明確的模型成本帳本（`cost_ledger.py`），以 Decimal 精度如實計算 Gemini 思考與輸入輸出費用，落實品質契約先於快省之比較原則。

[五分鐘重現與驗收](../../examples/day20/README.md)｜
[成本帳本計算器](../../examples/day20/cost_ledger.py)｜
[帳本契約自測套件](../../examples/day20/test_cost_ledger.py)

前篇：[Day 19](https://ithelp.ithome.com.tw/articles/10420229)；本篇待作者發布後補上正式連結。

離線測試、牌價算術示範與 Live 模型調用分開驗證。
English overview: Cost ledger contract for LOCAL, calculating token billing and latency across distinct task types with strict provenance and comparable identity verification.
