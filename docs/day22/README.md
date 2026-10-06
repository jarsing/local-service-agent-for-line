# Day 22｜權限、秘密與停止開關：最小特權與緊急制動

建立獨立 SQLite 人工停止契約示例（`circuit_breaker.py`）：以受控停止閘門與 epoch 版本控制，阻斷維護期間的新單副作用，保留已確認的原單與授權查單，搭配三權分立目標架構規劃與專用 GitHub Actions 離線 CI。

[五分鐘重現與驗收](../../examples/day22/README.md)｜
[停止閘門與狀態機](../../examples/day22/circuit_breaker.py)｜
[安全契約自測套件](../../examples/day22/test_security.py)

前篇：[Day 21](https://ithelp.ithome.com.tw/articles/10421328)；本篇：[Day 22](https://ithelp.ithome.com.tw/articles/10421645)。

離線停止狀態機、原子建單與 CAS 認領已由本機自測與 CI 驗證；雲端 IAM 政策、Secret Manager 實際掛載與雙 LINE 視窗實機交互待進一步驗收。
English overview: Standalone stop gate and security contract for LOCAL featuring control epoch invalidation, atomic request and outbox commit, CAS claim protection, and three-tier identity separation design.
