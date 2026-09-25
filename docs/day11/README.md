# Day 11｜服務重啟了，剛才交代的事還在嗎？重送、背景工作與重啟恢復

正式文章：[Day 11｜服務重啟了，剛才交代的事還在嗎？重送、背景工作與重啟恢復](https://ithelp.ithome.com.tw/articles/10416397)。前篇：[Day 10](https://ithelp.ithome.com.tw/articles/10416095)。

**服務重啟，剛才的詢問還找得到嗎？** 本章實作保存業務任務參照、原操作、確認、回條與有限工作進度。

- [最小操作與排錯](../../examples/day11/README.md)
- [資料與責任契約](../../examples/day11/CONTRACT.md)
- [驗收矩陣與證據讀法](../../examples/day11/ACCEPTANCE.md)

程式包含 memory-control、SQLite 測試 adapter 與真正 Firestore SDK 路線。記憶體／SQLite 可用標準函式庫執行；ADK 及本機 Firestore 模擬器已由作者於本機完成全套實測（verify 59/59 通過，SDK 273/273 通過）。

本章 sessions 保存的是 **目前業務任務** ，不是完整 ADK 聊天事件；請求已建立，也不代表真人已受理。Firestore 路線不先寫 SQLite 再同步。

下一篇依已驗證範圍接入 Cloud Run 與正常 LINE 服務；本章沒有替該整合預先宣告完成。
