# Dressmaker 繁體中文補丁

這個補丁把 Steam Windows 版《Dressmaker》的介面、內容、教學、對話、遊戲標題圖、宣傳單及報紙標題轉為繁體中文，並附上可還原的 Windows 安裝工具。安裝器會以繁體內容取代簡中語言表和圖片，同步更新 Addressables 目錄 CRC，並備份原檔以便還原。

## 使用

1. 關閉遊戲。
2. 執行 `release/DressmakerZHant.exe`。
3. 確認遊戲資料夾，按「一鍵繁體中文化」。
4. 重新啟動遊戲。工具會將遊戲語言設為簡體中文，以載入繁體文字表。

工具會備份文字包、圖片包、遊戲內建標題串流檔、Addressables 目錄和原本的遊戲語言偏好。按「還原原狀」可以移除補丁與內建標題修改。若 Steam 更新了遊戲檔案，工具會自動辨識更新後的原始檔並重建備份與 CRC；若語言表有新增或移除字串，請先依 [WORKFLOW.md](WORKFLOW.md) 更新翻譯主檔。若提示檔案不符，請先用 Steam 驗證遊戲檔案。

## 內容與限制

- 目前包含 5,398 筆文字，分布於內容、教學、對話及介面 4 個語言表；另處理 3 張本地化圖片，以及主選單使用的內建標題圖（`sharedassets1.assets.resS`）。
- 文字以 OpenCC 台灣用語轉換後，再統一遊戲介面常用詞；工具會保留遊戲字串 ID、富文字標籤及格式佔位符。
- 此版本支援 Steam Windows 版。遊戲更新後，若語言表仍包含原本所有字串 ID，工具會自動辨識新的原始檔並重建備份與 CRC；若更新新增了字串，這些字串在更新主檔前會維持簡中，需依 [WORKFLOW.md](WORKFLOW.md) 更新 `translations.csv` 與工具。若移除字串或新增語言表，安裝會因覆蓋率檢查停止，必須先更新主檔。新圖片同樣需要先更新素材。
- 補丁只包含翻譯文字與工具，不包含遊戲原始語言檔；安裝時會在玩家自己的遊戲目錄內修改語言表、圖片與標題串流，同步更新 Addressables 目錄 CRC，並備份原檔與目錄。

## 開發與重建

`translations.csv` 是翻譯表，欄位為 `table,id,text`。`tools/extract_convert.py` 可從本機已安裝遊戲重新抽取簡中原文，並另存 OpenCC 初稿；`tools/diff_update.py` 會與上一版原文快照比對，產生新增、變更與移除清單；`tools/patcher.py` 是安裝工具原始碼。

遊戲每次更新後的完整處理流程——抽取、比對、人工校對、重建與測試——見 [WORKFLOW.md](WORKFLOW.md)。

使用 Python 3.11 以上、UnityPy 1.25、OpenCC 及 PyInstaller 重建工具：

```powershell
py -m pip install UnityPy opencc-python-reimplemented pyinstaller
py -m PyInstaller --noconfirm --clean .\localization\zh-Hant\tools\DressmakerZHant.spec
copy .\dist\DressmakerZHant.exe .\localization\zh-Hant\release\DressmakerZHant.exe
```

建置產物位於 `dist` 資料夾。spec 會一併打包 UnityPy 所需的影像編碼、CPU 資料與 FMOD 函式庫。
