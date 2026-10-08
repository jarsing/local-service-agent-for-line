# Day 24｜改了一行，20 題還過嗎？Google AI 實測牆與 A/B 成本量測

[iThome 文章](https://ithelp.ithome.com.tw/articles/10422261)｜[文件導覽](../../docs/day24/README.md)

這是新增的擷取與核對範例，不是已執行的模型排行榜。三個固定分母為9題路由、6列A/B、20題原應用契約。新增62項測試只驗核對器，已附 15 筆真實 Gemini 3.8 Flash 呼叫序列化紀錄與稽核報表。

## 本機開始

Python3.10以上。從有 `examples/` 與 `eval/` 的Repo根目錄執行：

```bash
python3 -m unittest examples.day24.test_evidence -v
python3 -m examples.day24.capture --out out/day24/plan
python3 -m examples.day24.audit --run out/day24/plan \
  --out out/day24/planned-audit --allow-incomplete
```

預設capture不連模型。新輸出目錄不能已存在；保留每次嘗試。`--allow-incomplete`只允許產生待測表，不是驗收放行。

## 原二十題

```bash
python3 -m pip install -r examples/day12/requirements-core.txt
python3 -m examples.day24.offline --out out/day24/contracts
```

使用原 Day18 `verify_eval` 和 scorer；缺Day12～18模組會BLOCKED，不用替身模組冒稱原應用回歸。結果包含三層契約與另列的coverage。

## 人工核准後的模型擷取

```bash
python3 -m pip install -r examples/day24/requirements-live.txt
python3 -m pip check
python3 -m examples.day24.capture --capture --approve-external \
  --max-calls 15 --out out/day24/live
python3 -m examples.day24.audit --run out/day24/live --out out/day24/live-audit
python3 -m examples.day24.replay --run out/day24/live --out out/day24/backend-replay
```

先在自己的環境設定 `GEMINI_API_KEY`；不把真值放進本Repo。本實驗指定Developer API、`gemini-3.8-flash`、google-genai2.23.0、SDKattempts1。缺SDK／金鑰會記錄BLOCKED，沒有自動更換模型或端點。

`instruction.txt` 是新的直接SDK實驗提示，不是正式ADK Runtime的原封重跑。`replay` 也只是稍後用原本機應用執行已捕捉選擇，**不是原API呼叫當下的下游事件**。它只允許三種唯讀／說明工具，沒有LINE推播。

本範例已附 15 筆真實 Gemini 3.8 Flash SDK 調用序列化紀錄與稽核結果（位於 `examples/day24/evidence/`）；後端重播與原 live 事件分開標記，在未完成真人與線上通道驗收前，`safe_to_deploy` 保持 false。

## 輸出檔案

| 檔案 | 用途 |
|---|---|
| `plan.json` | 原問句、工具、提示、共同設定、預算及各種身分雜湊 |
| `calls/<key>/request.json` | 實際交給SDK的請求（不含API Key） |
| `calls/<key>/sdk_response.json` | 完整SDK回應物件序列化；不是原始HTTP位元組 |
| `calls/<key>/record.json` | 成功或錯誤、耗時、請求及回應雜湊 |
| `audit.json`、`TABLES.md` | 重新計算三份欄位與9／6分母；可比性與成本完整性分列 |
| `contracts/summary.json` | 原20題應用回歸結果；受阻不算通過 |
| `backend-replay/summary.json` | 捕捉後的新本機執行，不宣稱liveADK |

Budget1024不是實際用量1024；缺thoughts欄時保留未知，不因thinking_budget=0補零；資料不完整時不產生完整成本。費率是文字Standard公開估計，不是帳單。其他模態、快取、額外工具使用量不可套這張費率表。

A/B每設定每題只有一次觀察，不提供統計顯著性或泛化結論。`safe_to_deploy`固定false；仍須完成原應用、通道與部署驗收。

所有fixture只在unit test內生成並刪除。通過判分器測試不表示Google服務曾回傳這些內容。
