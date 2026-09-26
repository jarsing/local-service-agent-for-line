# LOCAL Day 3：第一個可重現的 Gemini 文字實驗

一次合成輸入、一次 GenerateContent 呼叫。沒有 LINE、ADK 工具、資料庫操作或雲端部署；API_TEXT_RECEIVED 不是回答品質或業務成功的判定。

## 1. 環境與離線檢查

沿用 Python 3.10 以上，建議使用獨立虛擬環境。下面從 Repo 根目錄執行；若已有合適虛擬環境，使用該 Python，不要重裝系統環境。

```bash
python3 -m venv examples/day03/.venv
examples/day03/.venv/bin/python -m pip install -r examples/day03/requirements.txt
examples/day03/.venv/bin/python -m unittest discover -s examples/day03 -p test_run.py -v
```

Windows 改用 `examples/day03/.venv/Scripts/python.exe`。離線測試本身不需要 SDK／金鑰，使用合成替身，不代表真實模型呼叫已通過。

## 2. 金鑰與單次真實呼叫

在 Google AI Studio 取得本人有權使用的 Gemini API 金鑰，核對所屬專案與帳務。將 `GEMINI_API_KEY=...` 保存在 Repo 外的私人 `.env`；不要提交、截圖或貼進聊天。

```bash
examples/day03/.venv/bin/python examples/day03/run.py --live \
  --env-file ../editorial/private/.env \
  --output ../editorial/evidence/day03
```

相對路徑只是範例，須符合你自己的資料夾位置。程式優先讀 `GEMINI_API_KEY` 環境變數；未設定才讀 `--env-file`。不要把金鑰本身放在命令參數。

預設模型 `gemini-3.8-flash`；不宣稱最新。使用其他支援相同設定的模型須明確傳入 `--model` 並保留新紀錄，程式不會自動切換。起始依賴是範圍，不是完整 lock；真正版本在 JSON 與 sdk-version.txt。若要重現相同 SDK，可使用紀錄中的精確版本重新建立環境。

本次最多一個應用層生成呼叫；SDK attempts=1、HTTP timeout=60000ms、輸出上限2048、LOW thinking。這些不是帳單封頂或模型完全不思考的承諾。

## 3. 判讀

- `API_TEXT_RECEIVED`：收到非空文字、結束原因STOP、沒有本例不接受的內容；**還要人工審閱內容**。
- `API_RESPONSE_NEEDS_REVIEW`：空白、截斷、被阻擋或出現非預期內容；不當成正常成功。
- `BLOCKED_NO_LIVE_CONSENT`／`BLOCKED_SETUP`：未開始真實生成。
- `API_ERROR`：已嘗試呼叫但有例外；不推論費用一定為零，不自動重試。

查看新建的 `run-.../REPORT.html`；保留 verification.json、response.txt、CHATGPT_HANDOFF.md。缺少用量欄位保持 null，不填零。程式不輸出 HTTP header、完整例外本文或模型 thought/signature。

## 4. 三個人工問題

1. 是否清楚表示後端狀態仍未知，而非宣布請求已建立？
2. 是否沒有假稱它已查詢、安排或通知真人？
3. 是否把下一步核對說成建議，而不是已執行的動作？

不符合就如實記錄；不要改模型輸出來美化結果。

## 官方來源

- https://ai.google.dev/gemini-api/docs/get-started
- https://ai.google.dev/gemini-api/docs/api-key
- https://ai.google.dev/gemini-api/docs/libraries
- https://googleapis.github.io/python-genai/
- https://ai.google.dev/gemini-api/docs/whats-new-gemini-3.5
- https://ai.google.dev/gemini-api/docs/billing

本範例為獨立執行腳本，無外部自動化部署副作用。
