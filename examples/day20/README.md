# Day 20｜模型設定、延遲與每項任務成本：品質先過關，再談快與省

本範例只計費與檢查比較身分，沒有Gemini／ADK client。`--demo` 的兩筆Token數是人為算術輸入，沒有延遲或模型通過率。

## 本機執行
```bash
python3 -m unittest examples.day20.test_cost_ledger -v
python3 -m examples.day20.cost_ledger --demo --fx 32 --out out/day20/formula-demo
python3 -m examples.day20.cost_ledger --init-cases eval/local20.json --out out/day20/cases-template
```
已有同次capture與grade時才使用：
```bash
python3 -m examples.day20.cost_ledger --input captured_rows.json --rates examples/day20/pricing.checked.json --fx 32 --out out/day20/imported-round-1
```
`captured_rows.json` 須為非空list，格式見主程式與測試。程式另提供 `summarize_ledger()`、`adapt_genai_usage()`、`evaluate_latency_budget()` 與 `format_cost_summary()` 供 LINE Webhook 與日後 Trace 整合調用。匯入不是認證；`billing_verified=false`。輸出目錄不能已存在。

## 費率與欄位
- 價格檔限定gemini-2.5-flash、標準文字、無cache、無grounding；輸入USD0.30/M，輸出含思考USD2.50/M，2026-10-03官方頁快照。
- 32為呼叫者明示的USD/TWD假設，不是即時匯率。
- prompt／candidates／thoughts／cache四欄均需非負整數，bool不算int；output_semantics須為candidates_excludes_thoughts。
- 未知模型、缺費率、欄位語意不明、cache／grounding範圍不符都拒絕；不要fallback至另一模型。
- usage=None保留未知費用，不補0；品質FAIL仍計入已知用量。品質通過只代表contract_status，coverage另外列，不能推論完整服務成功。
- 計算維持Decimal全精度；展示時再四捨五入。估計不等於帳單，Cloud Run、LINE、人工與稅等另計。

## 基準與比較
根目錄 `eval/local20.json` 為原交接完整副本；既有Repo已有時只比對，不覆蓋。選題固定local11/local12/local19，原local14仍是upstream_503。
`validate_comparable()` 要求模型、API、題目、輸入、Prompt、工具、資料、scorer、程式與其他生成設定一致，attempts=1，只允許預定思考變因不同。入口匯入不會自動執行A/B比較，接線者須顯式呼叫此函式。

## Live整合未包含
必須由既有ADK路徑保存真實usage、monotonic計時、有效模型設定、原始回應與grade檔案，再轉成本中介格式。每題call attribution要個別紀錄，不使用共享計數器的重疊差額。未取得就BLOCKED，勿自行製作六列成績。

價格來源：[Gemini API pricing](https://ai.google.dev/gemini-api/docs/pricing)。設定支援須按釘選SDK、endpoint與當日文件核對，不能由本計算器推導。
