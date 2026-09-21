# LOCAL Day 7｜看懂不等於可信：來源、版本與不知道

把同一張海報的更新，變成可追溯的活動資料更新。

**原圖與已核對資料 → 補公告年份 → 教學修訂圖 → Gemini 擷取 → 場次配對 → 欄位差異 → 人工核對 → 查詢採用新版。**

本例沿用 Day 6 的 Gemini 圖片擷取及欄位型別，重用 Day 5 的 Python 搜尋工具。正式內容由自己的真實執行產生；`demo.py` 是標示清楚的離線分支示範。

## 1. 先跑不用金鑰的示範

以下從 **Repo 根目錄** 執行，macOS／Linux 使用 Bash；Windows 請將直譯器路徑換成相應的 `Scripts/python.exe`。

```bash
# 已完成 Day 5／6 時沿用既有環境。
PY=examples/day05/.venv/bin/python
$PY examples/day07/verify.py --sdk
$PY examples/day07/demo.py
```

沒有前篇環境時：

```bash
python3 -m venv examples/day07/.venv
PY=examples/day07/.venv/bin/python
$PY -m pip install -r examples/day07/requirements.txt
$PY -m pip check
$PY examples/day07/verify.py --sdk
$PY examples/day07/demo.py
```

`verify.py` 真的執行單元測試，`--sdk` 額外匯入 Google SDK 型別及 Day 6 組態，兩者分開記錄；這些步驟沒有模型呼叫。`demo.py` 的圖片、資料、核對者都是離線夾具，不是實際活動，也不是 Gemini 回覆。

## 2. 匯入 Day 6 已核對的資料

需要四份相符的資料：擷取目錄裡的 `verification.json` 和原圖；人工核對目錄的 `review.audit.json` 與 `catalog.reviewed.json`。不必重新呼叫舊圖。

先將變數換成自己的實際位置：

```bash
CATALOG=/實際路徑/catalog.reviewed.json
AUDIT=/實際路徑/review.audit.json
DAY06_RUN=/實際路徑/原圖擷取資料夾
$PY examples/day07/run.py prepare \
  --catalog "$CATALOG" --audit "$AUDIT" --day06-run "$DAY06_RUN" \
  --output output/day07 --origin author_local
```

程式會印出工作紀錄位置。後面使用同一個位置，例如：

```bash
SESSION=output/day07/實際印出的run資料夾
```

程式依位元組核對 Day 6 圖片、原始紀錄與核對目錄的雜湊，首次匯入時指派穩定的活動 ID。ID 之後保存在資料裡，更新以這個 ID 配對，不用新圖雜湊重新計算。

## 3. 海報缺年份時，以對應公告補依據

```bash
$PY examples/day07/run.py notice-template --session "$SESSION"
```

編輯另存的 `notice.template.json`：保存對應公告的網址、短段原文、取得時間，以及每場活動的 `event_id`、完整日期、支持年份與月日的原文。確認同一屆、同一場後，填核對者、`same_event_confirmed: true` 與 `approved: true`，另存為 `notice.json`。

```bash
$PY examples/day07/run.py enrich --session "$SESSION" --notice /實際路徑/notice.json
```

程式檢查引句在保存的公告原文裡、年月日相符。這是人工提供來源後的機械檢查；「公告屬於同一個活動」仍須人確認。原圖片三元組保留，例如日期仍是 `null/09.19/unclear`；查詢用的完整日期放在 `enrichments.date`，附自己的來源。

需要日期比較的場次至少補一場；有來源支持八場時才補八場。公告未寫發布時間就保留 `published_at: null`，另記 `retrieved_at`。已有完整日期時略過這一步。

## 4. 建立教學修訂圖

在瀏覽器開啟 `examples/day07/revision_editor.html`，選取本次 `source_before.*` 原圖。框住一個**原本已經存在的活動時段**，例如將 `07:30~11:00` 改成 `08:00~11:00`。頁面會加上「教學用修訂版／非主辦公告」，下載 `revision.png` 和 `edit.json`。

原圖、修改區域、修改文字與新圖雜湊都有紀錄。請檢查框選沒有遮住其他日期或場次。圖片若沒有集合時間，就修改活動時間，不為了配合案例補一個集合時間。新圖需符合 Day 6 的 6 MiB 大小條件。若瀏覽器限制連續下載，允許本頁下載這兩份檔案。

本頁只讀你選取的本機圖片，不傳送圖片。少數瀏覽器限制本機 Web Crypto 時，可用自己的本機靜態網頁服務開啟同一檔案；不需對外建立通道。

## 5. 只對新圖做一次 Gemini 擷取

以下會呼叫 Gemini，先確認金鑰與當次帳號用量。`GEMINI_API_KEY` 或 `--env-file` 沿用既有設定。

```bash
$PY examples/day07/run.py extract --session "$SESSION" --live \
  --image /實際路徑/revision.png --edit-manifest /實際路徑/edit.json \
  --source-kind teaching_revision \
  --source-ref "教學修訂副本：原來源網址；非主辦公告" \
  --env-file /實際私人路徑/gemini.env --origin author_local
```

這一步直接呼叫 `examples/day06/run.py --condition guided`，沿用本機已採用的模型、LOW、生成上限與 schema；本包不複製一份舊 Day 6 程式。預設一個新圖模型請求、HTTP 60 秒、SDK attempts=1。舊圖引用既有真實結果，費用與耗時分開計算。失敗結果保留，再試須明確決定，不自動重跑。

成功後打開印出的 `MATCH.html`。同名場次只有一筆時先提供建議，仍由你核對。名稱重複、改名、新增或消失時逐筆配對；未出現的舊場次在下一步確認移除。

儲存下載的 `matching.json` 後：

```bash
$PY examples/day07/run.py plan --session "$SESSION" --matching /實際下載位置/matching.json
```

要接用另一份已完成的新圖擷取結果，可使用 `extract --from-run /新圖擷取目錄`；教學圖仍需 `--edit-manifest` 證明它由原圖製成，且這次來源類型仍標為 `teaching_revision`。只接受實際 `LIVE_GEMINI`，離線例子用 `demo.py`。

## 6. 看差異、查待核狀態，再採用

`REVIEW.html` 顯示兩張圖、每個變動三元組、連動欄位與未變資訊。`value`、`quote`、`status` 任一變更都會進入差異；只有字串首尾空白與 Unicode 組成形式作正規化，日期或時間不自動猜換。

用同一個關鍵字查三次，讓差異可比較：

```bash
KEYWORD=你修改的那場活動名稱
$PY examples/day07/run.py query --session "$SESSION" --phase before --keyword "$KEYWORD"
$PY examples/day07/run.py query --session "$SESSION" --phase pending --keyword "$KEYWORD"
```

待核時，變動或連動的重要欄位以 `pending_review` 表示，不把舊時間顯示成最新答案；其餘活動仍可查詢。篩選會同時考慮舊、新候選值，避免日期改了就把待核活動藏起來。圖片的疑點文字改變時，這版會擴大到相關場次的重要欄位，請由人看回原圖。

在 `REVIEW.html` 勾選已核對項目，必要時修改三元組並說明原因，填心得，最後下載 `decision.json`。

```bash
$PY examples/day07/run.py apply --session "$SESSION" --decision /實際下載位置/decision.json
$PY examples/day07/run.py query --session "$SESSION" --phase after --keyword "$KEYWORD"
```

採用會生成新版本與 `adoption.json`，保留上一版及複核紀錄；`active.json` 只負責指出本機目前採用哪份。這是單人單機的教材流程，不是跨多台主機的交易系統。

沒有差異也需確認新圖關係和重要公告，因為模型可能漏讀新增小字。未變欄位可以引用先前的核對紀錄，新圖片仍留下本次檢查者。

## 7. 看報告與公開哪些東西

`REPORT.html` 彙整變動和查詢前後，`MATCH.html`、`REVIEW.html` 為同一次執行的實際介面，可用作文章配圖。

| 檔案 | 責任 |
|---|---|
| `base.json`／`base.enriched.json` | 上一版核對值、穩定 ID 與公告依據 |
| `candidate_verification.json`／`candidate.json` | 新圖的原始 Gemini 紀錄與可比較資料 |
| `matching.json`／`plan.json` | 經確認的場次配對、三元組差異與複核範圍 |
| `decision.json`／`catalog.after.json`／`adoption.json` | 這次人工採用、新目錄與採用依據 |
| `queries/*.json` | 相同問題在更新前、待核、採用後的真正工具輸出 |

圖片的使用範圍依來源處理。教學副本公開時保留醒目標示與原始來源，不能當成主辦的新公告。金鑰與完整私人資料留在 Repo 外。

## 深入閱讀

- [前篇資料型別](../day06/schema.py)
- [前篇搜尋工具](../day05/catalog.py)
- [Gemini 圖片理解](https://ai.google.dev/gemini-api/docs/generate-content/image-understanding)
- [Gemini 結構化輸出](https://ai.google.dev/gemini-api/docs/generate-content/structured-output)
- [Grounding with Google Search](https://ai.google.dev/gemini-api/docs/google-search)：是另一項需明確啟用的能力，本例並未使用。
