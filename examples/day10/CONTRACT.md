# Day 10｜逾時後到底有沒有送出？

## 固定契約

Day 1 `docs/day01/handoff-timeout-001.json` 維持445 bytes、SHA-256 `9a4768046189e6ba0d42637953b8d73e41566f7c573ea0a76b32079b1a762218`。

收到本篇合成傳輸逾時時，`policy.pending_verification()` 獨立產生四欄政策，再由測試與 Day 1 固定規格比較。程式沒有讀 expected 當回覆。`request_created=null` 表示尚不確定，工具回覆不含被丟棄的 request_id。

## 狀態機與寫入

`submit → lookup → retry → done`，查回找到回條、權限拒絕或查回受阻時可以提早到 `done`。一個控制器最多三次工具執行；首次送出後最多再寫一次。

`not_found` 是成功查詢當下沒找到，不是確認第一次永遠不會提交。安全來自重送使用原鍵、Day 9 再驗確認和權限、交易／唯一限制；包含查回後有另一個送出者先寫入的競爭測試。

| 案例 | 入口可見結果 | 資料列觀察 | 主要測試 |
|---|---|---|---|
| 正常 | request_created | 最終1 | test_baseline_one_insert_no_lookup |
| 提交後失去回覆 | pending_verification → already_created | 逾時時1、查回後1，原單號 | test_after_commit_lookup_returns_original_id_without_second_create |
| 寫入前中斷 | pending → pending/not_found → request_created | 0 → 0 → 1 | test_before_write_lookup_miss_then_same_key_retry_creates_once |
| 查回也受阻 | pending → pending/lookup_unavailable | 可能已有1，入口仍未知 | test_lookup_unavailable_keeps_unknown_despite_existing_row |
| 查無紀錄後競爭寫入 | retry 得到原回條 | 最終1 | test_retry_race_finds_original_row_instead_of_creating_another |
| 重送時確認到期 | expired | 0 | test_first_write_after_expiry_is_rejected |
| 已寫入後確認到期 | 唯讀回原單 | 1、不修改 | test_receipt_after_confirmation_expiry_is_still_read_only |
| 權限撤回 | not_authorized | 不洩露回條、不新增 | test_current_permission_is_rechecked_for_lookup / retry |
| 輸入改鍵／改內容 | operation_binding_mismatch | 不新增 | test_controller_refuses_model_generated_key |
| 直接讀取同鍵異內容 | idempotency_conflict | 原列保持 | test_same_key_changed_text_conflicts_at_read_only_lookup |
| 再次逾時 | 保留 pending，停止當次流程 | 依實際資料列 | test_repeated_timeout_stops_after_one_retry |

`lookup` 只 SELECT；連線用 `mode=ro` 和 `query_only`。程式／schema 錯誤不概括吞成「查無資料」。可辨識的忙碌或 I/O 受阻保留未知。

## Google 元件與決策者

ADK Runner 真正接起 model → FunctionTool → controller → 原 Day 9 服務／新唯讀查回 → model。模型負責提出呼叫與解釋回條；控制器綁定 actor、原四參數、當前 phase 與次數上限。沒有讓模型從文字自行推定同意或自由決定重試策略。

每回合最多一次實際工具呼叫，最多三次模型請求；一案最多三回合。測試入口每回合提供 `expected_tool` 和 `send_args`，因此測的是受控工具介接，不是自由規劃能力。

固定腳本替身、真實 Gemini、應用端文案、真實 LINE 顯示分開。查驗 `TOOL_REQUESTED/EXECUTED/RESPONSE` 的 call ID、名稱、args、response，成功回條須對到 SQLite 的同一 request_id。原文仍需人工判讀。

## CI 與反例

選測是 Day 1、Day 2、Day 8、Day 9、Day 10 的實際依賴，不宣稱全系列已納入。測試數動態統計，缺相依、零測試、略過、錯誤一律不等於整組通過。

隔離退步案例把 lookup 傳入的鍵改錯，用同一套 `check_case()` 對照真實軌跡；預期抓到錯誤的外層測試仍應通過。沒有為了截圖修改正式 main，也沒有把它稱為一筆 GitHub 失敗 run。

## 範圍

提交點由合成傳輸包裝定位，SQLite 真正提交。尚未驗證實際網路封包遺失、LINE 介面、跨服務 exactly-once、真人通知或雲端部署。確認仍在行程記憶體，重新開機後的完整接續由後續篇章處理。
