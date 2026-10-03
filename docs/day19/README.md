# Day 19｜志工真的接到單了嗎？最小真人通知與收件匣閉環

建立志工收件匣與狀態推進契約（`request_created` → `notification_accepted` → `human_claimed` → `resolved`），落實通知去重與 CAS 樂觀鎖防搶單機制。

[五分鐘重現與驗收](../../examples/day19/README.md)｜
[收件匣合約與狀態機](../../examples/day19/inbox_contract.py)｜
[合約自測套件](../../examples/day19/test_inbox_contract.py)

前篇：[Day 18](https://ithelp.ithome.com.tw/articles/10419979)；本篇待作者發布後補上正式連結。

離線測試、示範路徑、Cloud Run 部署與 LINE 實機對話分開驗證。
English overview: Volunteer inbox closed-loop contract for LOCAL, implementing ticket projection, deduplicated notifications, and CAS optimistic locking for human handoff.
