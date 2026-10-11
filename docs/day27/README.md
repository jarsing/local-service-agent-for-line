# 成果展示要鎖住什麼？Demo 版本凍結、三分鐘劇本與離線備援

建立固定版本凍結規約（Demo Freeze，D79）、0～180 秒雙手機三分鐘端到端展示劇本（`DEMO.md`），以及本機 SQLite 離線重放備援與墨菲定律四道防線。

[iThome 文章](https://ithelp.ithome.com.tw/articles/10423364)｜[三分鐘展示手冊](DEMO.md)｜[本機離線重放實作](../../examples/day27/replay_day27.py)｜[單元測試](../../examples/day27/test_day27_replay.py)

本篇包含：
- 四份對照版本凍結規約（Commit、執行設定、資料快照、展示素材）
- 0～180 秒三分鐘雙手機端到端展示劇本（提問保留未知、確認建單、暫停熔斷、原子認領、原單查回）
- 墨菲定律四道防線（雲端即時、本機模擬、離線 SQLite 狀態機、預錄備援規格）
- 本機 SQLite 雙模式驗證（一般模式與 `-O` 最佳化模式防禦）
- 實體 iPhone LINE Bot 真機建單（`req-20261011-dcd85c8b18175111`）與同號查回對照

前篇：[Day 26](https://ithelp.ithome.com.tw/articles/10423179)。下一步：Day 28 把 LOCAL 交給開發者。
