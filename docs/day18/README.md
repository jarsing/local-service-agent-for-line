# Day 18｜20 題地方契約評測：從問句、工具到回覆，連失敗一起留下

建立 20 題地方真實情境基準（`eval/local20.json`），以 Python 判分器落實「模型意圖、後端事實、呈現出口」三層確定性契約驗收。

[五分鐘重現與驗收](../../examples/day18/README.md)｜
[20 題基準資料庫](../../eval/local20.json)｜
[確定性判分器](../../examples/day18/scoring.py)｜
[離線評測執行器](../../examples/day18/verify_eval.py)

前篇：[Day 17](https://ithelp.ithome.com.tw/articles/10419526)；本篇：[Day 18](https://ithelp.ithome.com.tw/articles/10419979)。

離線測試、示範路徑、Cloud Run 部署與 LINE 實機對話分開驗證。
English overview: 20-case local contract evaluation suite for LOCAL, verifying model intent, backend ground-truth invariants, and LINE Flex presentations with deterministic Python scoring.
