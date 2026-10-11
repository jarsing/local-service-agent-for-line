# Contributing to LOCAL

感謝你協助讓地方服務更容易理解與維護。優先處理可重現的小問題；不用先讀完全部連載才能提出改善。

## 回報一般問題

請使用 [https://github.com/jarsing/local-service-agent-for-line/issues](https://github.com/jarsing/local-service-agent-for-line/issues)，附上完整 Commit、作業系統、Python 版本、最小輸入、實際命令、預期及實際結果、去識別日誌。先查看是否已有相同問題。

正式 LINE 使用者識別、金鑰、權杖、電話與原始私人對話，不放進公開 Issue。疑似安全問題優先使用 Repo 已啟用的私人通報功能；若未啟用，先透過維護者另行提供且已核實的私人管道聯繫，不公開漏洞細節或秘密。

## 提出修改

一次聚焦一個行為。先提供能重現問題的測試，再提交修改與通過結果。保留來源、操作綁定、資料狀態及原始紀錄；schema 遷移要另附影響範圍、回復方式及舊資料案例。

本機最小入口由 Repo 根目錄執行：

```bash
python3 -m unittest test_day27_replay -v
```

新加入的 Day 28 候選在整合後使用獨立開發相依套件：

```bash
python3 -m venv .venv-day28
.venv-day28/bin/python -m pip install -r examples/day28/requirements-dev.txt
.venv-day28/bin/python -m unittest discover -s examples/day28 -p test_contracts.py -v
```

Windows 請改用 `.venv-day28/Scripts/python.exe`。尚未整合此候選時，上述 Day 28 路徑不會存在。

新測試與既有測試分開報數，範例資料須明確標示合成。模型 API、Firestore 寫入、LINE 推播與部署另需維護者核准，日常離線 CI 不使用私人金鑰。重新執行採新輸出目錄，不回寫歷史證據。

## 文件與授權

繁體中文文件使用臺灣用語；英文入口提供相同操作前提與失敗處理。文件的完成式敘述應能對回實際結果。

提交你有權提供的內容，標明第三方來源並保留適用授權。此指南不轉移你的著作權，也不替第三方素材取得新授權；專案程式依既有 MIT LICENSE 使用。品牌致謝可表達為友善請求，不加入未揭露的強制 logo 條件。

## English contributor summary

Report a minimal reproduction, commit, OS, Python version, command, expected/actual behavior and sanitized logs. Add a failing regression test before changing behavior. Keep identities and operation bindings intact. Document schema migrations and rollback. Separate local mock contracts, real API calls, container runs, device observations and deployment acceptance.

Do not put secrets or personal data in public issues. For security concerns use enabled private reporting or a verified private maintainer contact. Cloud calls and deployment changes require explicit approval. Preserve copyright notices and third-party licensing obligations; no copyright assignment is requested by this guide.
