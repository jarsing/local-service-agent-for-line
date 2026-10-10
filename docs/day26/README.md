# 走出自己房間之前：乾淨環境與雙 LINE 視窗的驗收規格

建立乾淨環境無干預重現規格（Clean-room Reproducibility，D48）與雙 LINE 視窗生命週期驗收規格（D68）；實作 SQLite CAS（Compare-and-Swap）原子認領教學片段，並提煉在地服務操作痛點與工程防呆矩陣。

[iThome 文章](https://ithelp.ithome.com.tw/articles/10423179)｜[停止開關與原子認領實作](../../examples/day22/circuit_breaker.py)｜[停止開關單元測試](../../examples/day22/test_security.py)

本篇包含：
- 乾淨容器規格腳本與依賴隔離（基於 `python:3.13-slim`、空建置上下文與 `--network none` 斷網測試）
- 雙 LINE 視窗跨端因果時序規格（確認送單、推播送達、暫停阻擋、恢復認領與查回狀態對帳）
- SQLite CAS 原子認領機制與控制世代（epoch）准入保護
- 在地服務營運痛點防呆矩陣（連按送出、翻看舊卡片與查無店家）

前篇：[Day 25](https://ithelp.ithome.com.tw/articles/10422718)。下一步：Day 27 Demo 版本與備援錄影。
