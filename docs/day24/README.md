# Day 24｜改了一行，20 題還過嗎？Google AI 實測牆與 A/B 成本量測

以三大分母（9 題真實路由、6 列 A/B 成本、20 題地方契約回歸）建立實測牆，直接調用 Gemini 3.8 Flash SDK 核對工具要求與關鍵參數，關閉自動函式執行；62 項離線自測與專用 CI 工作流全數通過。

[iThome 文章](https://ithelp.ithome.com.tw/articles/10422261)｜[執行指南](../../examples/day24/README.md)｜[路由擷取器](../../examples/day24/capture.py)｜[核對器](../../examples/day24/audit.py)｜[離線回歸](../../examples/day24/offline.py)｜[測試](../../examples/day24/test_evidence.py)

已附 15 筆真實 Gemini 3.8 Flash 呼叫序列化紀錄與稽核報表，9/9 路由全過（100%），6 列成對 A/B 完整計算成本。

前篇：[Day 23](https://ithelp.ithome.com.tw/articles/10421985)。下一步是 Day 25 結構化輸出抽取地方資料；雙 LINE 視窗整合驗收仍在 Day 26。
