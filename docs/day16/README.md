# Day 16｜不可信文件與最小權限

同一個 LOCAL 服務新增唯讀文件分流。外來文字不會取得建單、同意或忘記的工具權限。

[五分鐘重現與驗收](../../examples/day16/README.md)｜
[核心權限檢查](../../examples/day16/policy.py)｜
[ADK 接點](../../examples/day16/adk_guard.py)｜
[唯讀執行](../../examples/day16/read_tools.py)｜
[合成攻擊文件](../../examples/day16/data/untrusted_flyer.txt)

前篇：[Day 15](https://ithelp.ithome.com.tw/articles/10418768)；本篇：[Day 16](https://ithelp.ithome.com.tw/articles/10419112)。

離線測試、真 ADK＋腳本模型、Firestore 模擬器、真 Gemini、LINE 與 Cloud Run 分開驗證。
English overview: a minimal document reader with read-only tool declarations and independent backend authorization; model suggestions do not grant execution rights.
