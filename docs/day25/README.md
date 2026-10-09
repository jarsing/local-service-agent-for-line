# Day 25｜Gemini 結構化輸出抽取地方資料：從公開文字到服務資料庫

以 Pydantic 定義防偽契約、以程式進行四道確定性原文核對、以人工審閱收據（ReviewReceipt）把關語意與時效，並透過本機 SQLite 驗證冪等採用與候選查詢；38 項離線測試與專用 CI 工作流全數通過。

[iThome 文章](https://ithelp.ithome.com.tw/users/20120682/ironman/9872)｜[執行指南](../../examples/day25/README.md)｜[抽取模型入口](../../examples/day25/capture.py)｜[契約規格](../../examples/day25/schema.py)｜[採用儲存庫](../../examples/day25/store.py)｜[測試](../../examples/day25/test_ingestion.py)

實測涵蓋 5 題情境（明確時段、非標準時段、提示詞注入防禦、否定句語意陷阱、城市級介紹文本）。

前篇：[Day 24](https://ithelp.ithome.com.tw/articles/10422261)。下一步是 Day 26 雙 LINE 視窗整合驗收。
