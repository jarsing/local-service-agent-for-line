# Day 9｜按兩次送出，會不會多一筆？受控建單與冪等

正式文章：https://ithelp.ithome.com.tw/articles/10415923

操作入口：[examples/day09/README.md](../../examples/day09/README.md)。
規格入口：[CONTRACT.md](../../examples/day09/CONTRACT.md)。
前篇：[Day 8｜一句「好」不夠：確認綁定具體操作](https://ithelp.ithome.com.tw/articles/10415219)。

## 本篇要驗證的能力

把已確認的詢問接成 ADK 工具 `create_handoff_request`，在本機 SQLite 建立請求，取得可查回的 `request_id`。同鍵同內容取回同單，同鍵異內容回報衝突。

確認核心仍用 Day 8；Day 9 在適配層檢查原確認已存在、已明確同意且符合本人、內容、版本與期限，另檢查操作權限。讀取已建立的原單與執行首次寫入分開。

## 可重現的三層

- 核心：Python 標準函式庫與真實 SQLite，含六個不同連線的同鍵同時送出。
- ADK：真正 Runner／工具事件與固定腳本模型，驗證介接而非語言品質。
- Gemini：使用者另外核准後執行兩回合，記錄真正參數、回條與原文，無預填成功結果。

測試總數與通過數以 `verification.json` 的各組結果為準；程式已提供不等於每個環境已實測。

## 接續關係

Day 8 是內容確認；本篇是請求建立；Day 10 是逾時之後依原識別查回並加入離線 CI。請求狀態 `pending_human_review` 代表等待真人受理，沒有真實對外通知。

`fixtures.json` 沿用前篇兩個教學版本標籤。Day 8 原 `Identity` 只有 user/session，Day 9 的 Actor 額外放服務範圍，不修改前篇。
