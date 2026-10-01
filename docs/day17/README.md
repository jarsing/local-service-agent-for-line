# Day 17｜查不到，是真的沒有，還是系統當下查不了？三種查不到與服務降級

同一個 LOCAL 服務新增有型別的結果分流。區分查無資料、暫時查不了與不支援，給予固定文案與按鈕引導。

[五分鐘重現與驗收](../../examples/day17/README.md)｜
[有型別的結果](../../examples/day17/outcomes.py)｜
[固定文案與按鈕](../../examples/day17/messages.py)｜
[例外配接器](../../examples/day17/adapters.py)｜
[離線示範](../../examples/day17/demo.py)

前篇：[Day 16](https://ithelp.ithome.com.tw/articles/10419112)；本篇：[Day 17](https://ithelp.ithome.com.tw/articles/10419526)。

離線測試、示範路徑、Cloud Run 部署與 LINE 實機對話分開驗證。
English overview: typed outcomes and service degradation for LOCAL, distinguishing empty lookups, temporary downtime, and unsupported requests.
