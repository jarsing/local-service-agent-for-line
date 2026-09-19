# Day 5｜ADK＋受控查詢：第一個 Agent 與 Orchestration

程式與操作見 [examples/day05/README.md](../../examples/day05/README.md)。

本篇的可重現單位：四筆合成活動、四個開發案例、同一模型的有工具／無工具回合，以及沿用 Day 4 的 LINE 入口。工具名稱 `search_local_events` 對應 Day 1 預告的活動查詢介面。

文章與程式的共同主張：讀者能把 Python 函式交給 ADK 使用，看到工具請求、實際查詢、工具回傳與最後回答；理解未知欄位和查無活動的差別，並說明引入工具取得資料的好處與額外模型往返的代價。

四題是開發示例與探索性比較，保留各題原文、執行條件、結果與失敗。模型與框架的適用範圍由這些資料解釋，不預設哪一組每題都比較好。

公開版本以作者實際提交為準。發布文章時連到對應 commit；若作者選擇建立 `day05` tag，再核對 tag 指向同一提交。

來源：
- Google ADK Function tools：https://adk.dev/tools-custom/function-tools/
- Google ADK Events：https://adk.dev/events/
- Google ADK Runtime Config：https://adk.dev/runtime/runconfig/
- Google ADK Session：https://adk.dev/sessions/session/
- LINE Build a bot：https://developers.line.biz/en/docs/messaging-api/building-bot/
