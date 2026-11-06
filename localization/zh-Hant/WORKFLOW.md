# Dressmaker 繁體化更新工作流程

**適用版本**：Steam Windows 版《Dressmaker》  
**翻譯主檔**：`localization/zh-Hant/translations.csv`  
**最後更新**：2026-10-20

## 目的

遊戲每次更新後，只處理新增或變更的內容，不覆蓋既有的人工校對；同時維持 Addressables 目錄、備份與還原鏈一致。流程以「先抽取、再比對、人工校對、測試副本驗證、最後套用實機」為原則。

## 核心原則

1. `translations.csv` 是唯一翻譯主檔。`extract_convert.py` 產生的 OpenCC 結果只是草稿，不可直接覆蓋主檔。
2. 字串以 `(table, id)` 對應，不可用文字內容當識別鍵。
3. 每次更新都保留翻譯備份與原始簡中快照，兩者分開存放。
4. 圖片與文字分開檢查；Addressables CRC 由 `patcher.py` 計算，不可手動修改 `catalog.bin`。
5. 先在測試副本完成安裝與還原，再套用到實際遊戲。
6. 已套用補丁時，不要手動刪除 `.zh-hant-backup` 或 `.zh-hant-state.json`。Steam 更新後由工具的遷移邏輯處理新舊檔案。

## 檔案與路徑

以下路徑均相對於 本專案根目錄，實際遊戲資料夾為 `C:\Program Files (x86)\Steam\steamapps\common\Dressmaker`。

| 用途 | 路徑 |
| --- | --- |
| 翻譯主檔 | `localization/zh-Hant/translations.csv` |
| 繁體圖片素材 | `localization/zh-Hant/images/` |
| 抽取與轉換工具 | `localization/zh-Hant/tools/extract_convert.py` |
| 更新差異工具 | `localization/zh-Hant/tools/diff_update.py` |
| 安裝／還原邏輯 | `localization/zh-Hant/tools/patcher.py` |
| PyInstaller 設定 | `localization/zh-Hant/tools/DressmakerZHant.spec` |
| 發佈版工具 | `localization/zh-Hant/release/DressmakerZHant.exe` |
| 翻譯與原文備份 | `localization/zh-Hant/backups/` |
| 本次更新工作區 | `localization/zh-Hant/backups/update-YYYYMMDD/` |

遊戲端重要檔案：

- 文字包：`Dressmaker_Data/StreamingAssets/aa/StandaloneWindows64/localization-string-tables-chinese(simplified)(zh-hans)_assets_all.bundle`
- 圖片包：`Dressmaker_Data/StreamingAssets/aa/StandaloneWindows64/localization-assets-chinese(simplified)(zh-hans)_assets_all.bundle`
- 目錄：`Dressmaker_Data/StreamingAssets/aa/catalog.bin`
- 內建標題：`Dressmaker_Data/sharedassets1.assets` 與 `Dressmaker_Data/sharedassets1.assets.resS`
- 工具狀態：文字包旁的 `.zh-hant-state.json`
- 語言設定備份：`%LOCALAPPDATA%\DressmakerZHant\options.json.original`

目前基準版本為 2026-10-20、5,398 筆文字，原始簡中快照由維護者在本機保存，公開儲存庫不附原文快照。首次維護若沒有快照，請使用 `--old-source` 指定自行抽取的基準，或將差異標為待確認。下一次更新請以最新已發佈的 `source-YYYYMMDD.csv` 作為比對基準。

## 快速清單

- [ ] 關閉遊戲，確認 Steam 已完成更新
- [ ] 備份 `translations.csv`
- [ ] 確認文字包是目前原始簡中，不是已套用版本
- [ ] 抽取新原文到本次更新工作區
- [ ] 與上一版原文快照比對，產生 `report.md`、`review.csv`、`draft.csv`
- [ ] 人工校對新增與原文變更項目，合併回 `translations.csv`
- [ ] 檢查圖片與內建標題是否有變更
- [ ] 重建 `DressmakerZHant.exe`
- [ ] 在測試副本完成 install、restore、混合狀態遷移測試
- [ ] 套用實機，使用 Steam 啟動，確認主選單與 `Player.log`
- [ ] 保存新的 `source-YYYYMMDD.csv`，更新 README 與版本紀錄

## 流程

### 0. 更新準備與備份

先關閉遊戲。以下指令在 PowerShell 執行；日期與專案路徑可依實際情況調整。後續步驟沿用本節設定的 `$root`、`$locale`、`$work`；若中途重開視窗，請先重新執行本節設定。

```powershell
$root   = "C:\Program Files (x86)\Steam\steamapps\common\Dressmaker"
$locale = "C:\Projects\dressmaker-zh-hant\localization\zh-Hant"
$date   = Get-Date -Format "yyyyMMdd"
$work   = Join-Path $locale "backups\update-$date"
New-Item -ItemType Directory -Force $work | Out-Null

Copy-Item "$locale\translations.csv" "$locale\backups\translations-$date-before-update.csv"
```

確認文字包狀態。`patched_sha256` 相同代表目前仍是已套用版本：

```powershell
$textBundle = Join-Path $root "Dressmaker_Data\StreamingAssets\aa\StandaloneWindows64\localization-string-tables-chinese(simplified)(zh-hans)_assets_all.bundle"
$statePath = "$textBundle.zh-hant-state.json"
(Get-FileHash $textBundle -Algorithm SHA256).Hash.ToLower()
if (Test-Path $statePath) {
  $state = Get-Content $statePath -Raw | ConvertFrom-Json
  $state.original_sha256
  $state.patched_sha256
}
```

判讀方式（第一個雜湊依序比對後兩個）：

- 等於 `original_sha256`：文字包是目前原始簡中，可以繼續抽取。
- 等於 `patched_sha256`：文字包仍是繁體補丁。若確定這次更新有文字內容，請先用 Steam「驗證遊戲檔案完整性」讓文字包回到原始簡中，再繼續。不要直接從補丁版抽取，否則會把繁體當成新原文。
- 兩者都不同：通常是 Steam 更新後的新原檔，可以抽取；抽取後依步驟 1 確認內容是簡中。若檔案來源不明或內容混雜，再用 Steam 驗證。
- 沒有狀態檔：可能是首次安裝或狀態檔遺失，先以遊戲檔案的實際內容判斷；不確定時先用 Steam 驗證。

若這次更新確定沒有動到文字，可略過步驟 1–4，保留現有 `translations.csv`，直接檢查圖片並重建工具。

Steam 更新後即使文字、目錄已換新，舊圖片包或舊 `.zh-hant-*` 備份仍可能留著，這是正常的混合狀態；不要手動清理，新工具會在安裝時自動遷移。

### 1. 抽取新原文

```powershell
py "$locale\tools\extract_convert.py" `
  --game $root `
  --source-out "$work\source.csv" `
  --out "$work\opencc.csv"
```

- `source.csv`：原始簡中，供差異比對與日後保存。
- `opencc.csv`：整份 OpenCC 初稿，只供參考，不可直接取代主檔。

省略 `--out` 時，初稿會寫到 `localization/zh-Hant/opencc-draft.csv`；工具會拒絕直接覆寫 `translations.csv`。

抽取後快速確認第一筆是簡中：

```powershell
Get-Content "$work\source.csv" -TotalCount 3
```

應看到「维多利亚印花棉布」這類簡體字。若看到「維多利亞」等繁體，表示抽到了已套用版本，請先完成 Steam 驗證再重抽。

### 2. 產生差異報告

```powershell
py "$locale\tools\diff_update.py" `
  --new-source "$work\source.csv" `
  --old-source "$locale\backups\source-20261020.csv" `
  --out-dir $work
```

- `--old-source` 請改成上一個已發佈版本的原文快照。省略時，工具會自動選 `backups/source-*.csv` 中排序最後的檔案；為避免新舊快照混淆，建議明確指定。
- 千萬不要在比對前把本次 `source.csv` 複製成 `backups/source-*.csv`，否則可能拿新版本跟自己比對。

輸出位於 `$work`：

| 檔案 | 用途 |
| --- | --- |
| `report.md` | 各語言表統計與前 50 筆新增／變更／移除摘要 |
| `review.csv` | 完整校對清單，欄位包含 `kind`、新舊原文、現有譯文與初稿 |
| `draft.csv` | 符合本次原文的候選主檔；保留既有譯文、排除已移除字串，新增字串先套 OpenCC |
| `source.csv` | 本次原始簡中快照 |

`review.csv` 的 `kind`：

- `added`：遊戲新增字串，尚無譯文。
- `changed`：同一個 ID 的簡中原文變更，現有譯文需要重新確認。
- `removed`：主檔有、遊戲已移除。會列在 `review.csv` 供確認，但不會寫進 `draft.csv`；若懷疑是抽取錯誤，請先重新抽取，不要直接升為主檔。
- `unverified`：新原文與主檔都有，但舊快照缺少該 ID，無法判斷原文是否變更。通常是基準檔不完整，需人工確認。

安裝工具會比對語言表 ID 數；主檔若保留遊戲已移除的 ID，安裝會失敗。因此 `draft.csv` 只包含本次原文的 ID，移除項目僅留在 `review.csv`。

### 3. 校對與合併

打開 `review.csv`（UTF-8 BOM，可直接用 Excel 或 VS Code）：

1. `added`：以 `draft` 欄的 OpenCC 初稿為起點，逐筆改成台灣用語；必要時比對遊戲情境。
2. `changed`：先看 `old_source` 與 `new_source` 差異，再修改 `existing_translation`。不要因為 OpenCC 結果不同就整批重轉，否則會破壞既有校對。
3. `removed`：先確認不是抽取錯誤。這些字串已不在遊戲中，`draft.csv` 不會包含它們；若需要舊譯文，可對照 `review.csv` 或更新前的備份。
4. 只修改 `draft.csv`，不要直接改 `review.csv`。

校對完成後，才把草稿升為主檔：

```powershell
Copy-Item "$work\draft.csv" "$locale\translations.csv"
```

基本檢查：

```powershell
Import-Csv "$locale\translations.csv" | Group-Object table | Sort-Object Name | Format-Table Name, Count
Import-Csv "$locale\translations.csv" | Where-Object { -not $_.text.Trim() } | Select-Object table, id
Import-Csv "$locale\translations.csv" | Group-Object table, id | Where-Object Count -gt 1 | Select-Object Name, Count
```

第二個指令應沒有輸出；第三個指令應沒有重複 ID。`translations.csv` 的欄位固定為 `table,id,text`，請保留 UTF-8 BOM。

### 4. 文字品質檢查

只針對本次 `added` 與 `changed` 的項目做重點校對，不必每次重審全部 5,000 多筆。

- 格式標籤必須與原文一致：`<color=#xxxxxx>`、`</color>`、`<style=c1>`、`</style>`、`<b>`、`<size=...>` 等。
- 格式佔位符必須保留：`{0}`、`{1}`、`%s`、`%d`、`\n`。
- 確認台灣用語與前後文一致，例如「裡／裏」、「迴路」、「著／着」、「麵粉」、「頭髮」。OpenCC 的 s2twp 只是初稿，不能當最終結果。
- 介面字串若明顯變長，注意按鈕或欄位是否溢出；可在遊戲內切換該畫面確認。
- 不要把簡體原文直接留在譯文中；若看到可疑字，回到 `review.csv` 對照來源。

### 5. 圖片與內建標題檢查

先判斷圖片包是否被 Steam 換新：

```powershell
$imageBundle = Join-Path $root "Dressmaker_Data\StreamingAssets\aa\StandaloneWindows64\localization-assets-chinese(simplified)(zh-hans)_assets_all.bundle"
(Get-FileHash $imageBundle -Algorithm SHA256).Hash.ToLower()
$state.image_patched_sha256
$state.image_original_sha256
```

- 等於 `image_patched_sha256`：還是舊補丁圖片包，通常是這次更新沒動到圖片。若遊戲版面沒變，可略過圖片重製。
- 等於 `image_original_sha256` 或兩者都不同：Steam 換了新圖片包，必須重新檢查。
- 舊狀態檔可能沒有 `image_original_sha256`，此時以目錄 CRC 和實際畫面判斷。

需要檢查的文字圖片精靈名稱：

- `flyerFull_scn`：宣傳單。
- `gamelogo_scn`：遊戲標誌。
- `newspaperTitle_scn`：報紙標題。
- `sharedassets1.assets` 內的 `gamelogo_scn`：主選單內建標題，使用 2048×512 DXT5、單一 mip，資料在 `sharedassets1.assets.resS`。

可用 UnityPy 或 AssetStudio 抽出圖片包中的 Texture2D／Sprite，與 `images/` 現有素材比對。抽出所有 Texture2D 的範例：

```powershell
@'
import UnityPy
from pathlib import Path

bundle = Path(r"C:\Program Files (x86)\Steam\steamapps\common\Dressmaker\Dressmaker_Data\StreamingAssets\aa\StandaloneWindows64\localization-assets-chinese(simplified)(zh-hans)_assets_all.bundle")
out = Path(r"C:\Projects\dressmaker-zh-hant\work_test\image-audit")
out.mkdir(parents=True, exist_ok=True)
env = UnityPy.load(str(bundle))
for obj in env.objects:
    if obj.type.name == "Texture2D":
        tex = obj.read()
        tex.image.save(out / f"{tex.m_Name}.png")
        print(tex.m_Name, tex.m_Width, tex.m_Height)
'@ | py -
```

更新圖片時：

1. 修改 `images/` 內對應的 PNG，維持正確尺寸與透明度。
2. 若精靈名稱、位置或版面改變，更新 `patcher.py` 的 `IMAGE_REPLACEMENTS`、`SHARED_TEXTURE_NAME` 與相關驗證，不要直接移除驗證。
3. 內建標題若格式、mip 或串流位置改變，`make_patched_shared_res` 會拒絕修改；請先確認新格式再調整程式。
4. 套用後重新抽出圖片包，逐一目視確認所有含文字的圖片；主選單標題另外用遊戲畫面確認。
5. 對照圖可保存在 `image-review/`，不要放進 `release/`。

### 6. 重建安裝工具

在 本專案根目錄執行：

```powershell
py -m pip install UnityPy opencc-python-reimplemented pyinstaller
py -m PyInstaller --noconfirm --clean ".\localization\zh-Hant\tools\DressmakerZHant.spec"
Copy-Item ".\dist\DressmakerZHant.exe" ".\localization\zh-Hant\release\DressmakerZHant.exe" -Force
```

- spec 會打包 `translations.csv`、`images/`、UnityPy 所需的 archspec 資料與 fmod 函式庫；不要改回舊的單行 PyInstaller 指令。
- 建置完成後先開啟 `release/DressmakerZHant.exe`，確認視窗正常出現，再進行測試副本。
- `extract_convert.py` 與 `diff_update.py` 是維護工具，不會打包進 exe。

### 7. 測試副本驗證

用目前實機「更新後、尚未套用」的狀態建立最小測試副本。這個副本足以測試安裝、CRC、還原與混合狀態遷移，但不能啟動遊戲。

```powershell
$dst = "C:\Projects\dressmaker-zh-hant\test_game"
Remove-Item -Recurse -Force $dst -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force "$dst\Dressmaker_Data\StreamingAssets\aa\StandaloneWindows64" | Out-Null
Copy-Item "$root\Dressmaker.exe" $dst
Copy-Item "$root\Dressmaker_Data\sharedassets1.assets" "$dst\Dressmaker_Data"
Copy-Item "$root\Dressmaker_Data\sharedassets1.assets.resS" "$dst\Dressmaker_Data"
Copy-Item "$root\Dressmaker_Data\StreamingAssets\aa\catalog.bin" "$dst\Dressmaker_Data\StreamingAssets\aa"
Get-ChildItem "$root\Dressmaker_Data\StreamingAssets\aa\StandaloneWindows64\localization-*chinese*.bundle" | Copy-Item -Destination "$dst\Dressmaker_Data\StreamingAssets\aa\StandaloneWindows64"
```

以上建立的是乾淨原始檔測試。若要重現 Steam 更新後的混合狀態，再複製實機既有的 `.zh-hant-*` 檔：

```powershell
Copy-Item "$root\Dressmaker_Data\StreamingAssets\aa\StandaloneWindows64\*.zh-hant-*" "$dst\Dressmaker_Data\StreamingAssets\aa\StandaloneWindows64"
Copy-Item "$root\Dressmaker_Data\StreamingAssets\aa\catalog.bin.zh-hant-backup" "$dst\Dressmaker_Data\StreamingAssets\aa" -ErrorAction SilentlyContinue
Copy-Item "$root\Dressmaker_Data\sharedassets1.assets.resS.zh-hant-backup" "$dst\Dressmaker_Data" -ErrorAction SilentlyContinue
```

執行安裝與還原：

```powershell
& ".\localization\zh-Hant\release\DressmakerZHant.exe" --install $dst
Get-Content "$env:TEMP\DressmakerZHant-cli.log"
& ".\localization\zh-Hant\release\DressmakerZHant.exe" --restore $dst
Get-Content "$env:TEMP\DressmakerZHant-cli.log"
```

`--install` 與 `--restore` 是測試用命令列入口；一般使用者仍使用圖形介面。日誌第一行應為 `OK`，失敗則為 `ERROR` 加原因。

> **注意**：遊戲語言設定 `options.json` 位於 `%USERPROFILE%\AppData\LocalLow\Cozy Lives\Dressmaker\`，不在測試副本內；測試副本的安裝與還原仍會讀寫實機的語言設定及 `%LOCALAPPDATA%\DressmakerZHant\` 備份。測試前先關閉遊戲，且每次測試務必以 `--restore` 收尾，讓實機語言設定回到原狀。

至少完成以下三項：

1. 乾淨原始檔：install → 檢查 → restore。
2. 混合狀態：install 應自動辨識新文字／目錄與舊圖片／備份，不需手動刪檔 → restore。
3. 再次 install → restore，確認沒有殘留 `.zh-hant-*` 檔。

檢查重點：

- 安裝成功訊息中的字串數、語言表數與圖片數符合本次版本。
- `.zh-hant-state.json` 為 schema 2，`patched_sha256`、`image_patched_sha256`、`catalog_patched_sha256`、`shared_patched_sha256` 與實際檔案一致。
- 文字包抽樣為繁體；目錄 CRC 與文字包、圖片包一致。
- 圖片包三張圖與內建標題圖皆為繁體。
- 還原後文字、圖片、目錄、`sharedassets1.assets.resS` 的雜湊回到原始值，備份與狀態檔清除，遊戲語言設定還原。

### 8. 套用實機與遊戲內驗證

1. 關閉遊戲與所有工具視窗。
2. 執行 `localization/zh-Hant/release/DressmakerZHant.exe`。
3. 確認遊戲資料夾，按「一鍵繁體中文化」。
4. 看到完成訊息後，確認文字包旁有新的 schema 2 狀態檔與備份。
5. 用 Steam 啟動遊戲（直接執行 `Dressmaker.exe` 可能因 SteamAPI 初始化失敗而退出）：

```powershell
Start-Process "steam://rungameid/4019220"
```

6. 檢查主選單標題、按鈕與選項畫面；若時間允許，進入遊戲檢查新增內容。
7. 檢查 `Player.log`：

```powershell
$log = "$env:USERPROFILE\AppData\LocalLow\Cozy Lives\Dressmaker\Player.log"
Select-String -Path $log -Pattern "Exception|CRC|Addressables|Failed to load|mismatch" -CaseSensitive:$false
```

正常不應出現 CRC 不符、Addressables 載入失敗或例外。若出現錯誤，先關閉遊戲，再依下方還原流程處理。

8. 驗證完成後關閉遊戲。

### 9. 保存紀錄與發佈

只有在實機驗證通過後，才把本次原文快照存入備份：

```powershell
Copy-Item "$work\source.csv" "$locale\backups\source-$date.csv"
```

- 保留 `translations-$date-before-update.csv`、`report.md`、`review.csv`、`draft.csv`，方便日後追查。
- 更新 `README.md` 的字串數、圖片數與日期。
- 若遊戲版本有變，建議在備份中保留對應的發佈版 exe 或版本註記。
- 清理 `test_game`、暫存圖片與舊建置產物；`release/` 只保留最新的 `DressmakerZHant.exe`。

## 還原與異常處理

### 正常還原

關閉遊戲後，執行 `release/DressmakerZHant.exe`，按「還原原狀」；或使用命令列：

```powershell
& ".\localization\zh-Hant\release\DressmakerZHant.exe" --restore "C:\Program Files (x86)\Steam\steamapps\common\Dressmaker"
Get-Content "$env:TEMP\DressmakerZHant-cli.log"
```

工具會先驗證目前檔案與備份雜湊，再以交易方式還原文字、圖片、目錄與內建標題，最後還原遊戲語言設定。

### Steam 在補丁後又更新

此時目前檔案可能已不是工具記錄的 `patched_sha256`，還原會基於安全理由拒絕。處理方式：

1. 關閉遊戲。
2. 在 Steam 對遊戲執行「驗證遊戲檔案完整性」，讓官方檔案回到最新版。
3. 若更新只涉及非文字檔案或僅新增字串，可直接重新套用繁中補丁；工具的安裝流程會把新原檔當作基準，重建備份與 CRC。若需要完整翻譯新增內容，或安裝因語言表 ID 數不符而停止，請先依上方更新流程處理主檔。
4. 若只是要恢復官方原狀，驗證完成後不要重新套用即可。

不要手動刪除狀態檔來繞過檢查；這樣會失去原本的備份對應關係。

### 常見錯誤

| 訊息 | 可能原因 | 處理 |
| --- | --- | --- |
| 找不到這個工具建立的備份 | 尚未安裝，或備份被刪除 | 直接安裝；若先前已安裝，先用 Steam 驗證再重新安裝 |
| 遊戲語言檔已被更新或修改 | Steam 更新或手動改動 | 先 Steam 驗證，再重新安裝或還原 |
| 語言表……的 ID 數不符 | 遊戲移除字串或新增語言表，主檔未更新 | 依流程重新抽取比對，更新 `translations.csv` 後重建工具 |
| 覆蓋率檢查失敗 | 語言表筆數、名稱與主檔不一致 | 同上；不要略過這項檢查 |
| 原始語言檔備份校驗失敗 | 備份損壞 | 不要強制還原；用 Steam 驗證後重建 |
| 圖片資產不完整 | 精靈名稱或版面改變 | 檢查圖片包，更新 `IMAGE_REPLACEMENTS` 與相關程式 |
| 找不到遊戲內建標題圖片 | `sharedassets1.assets` 結構改變 | 檢查 `gamelogo_scn` 的 Texture2D／Sprite、格式與串流 |
| Addressables CRC 不符 | 目錄未同步或檔案被改動 | 重新安裝；必要時 Steam 驗證後重建，不要手改 `catalog.bin` |

### 手動救援原則

- `.zh-hant-backup` 是工具建立的原始檔備份，`.zh-hant-state.json` 記錄對應雜湊；兩者必須一起使用。
- 若備份與狀態仍完整，優先使用工具的還原功能，不要手動覆蓋。
- 若狀態已損壞，最安全的方式是 Steam 驗證回官方檔，再重新安裝補丁。
- 遊戲語言偏好備份位於 `%LOCALAPPDATA%\DressmakerZHant\`；正常還原會一併處理，通常不需要手動編輯。

## 工具狀態與自動遷移

`install()` 會依下列順序判斷每個檔案是原始、已補丁或未知：

1. 文字與圖片：若目前雜湊等於上次 `patched_sha256`，使用已驗證的 `.zh-hant-backup` 當原始檔；若等於 `original_sha256` 或與目錄 CRC 相符，使用目前檔案；否則停止，避免覆蓋未知版本。
2. 目錄：若目前等於上次補丁版，使用目錄備份；若目錄中的 CRC 已對應目前的文字與圖片原始檔，使用目前目錄；否則停止。
3. 內建標題：若目前 `.resS` 等於上次補丁版，使用備份；若等於原始版或 `sharedassets1.assets` 已更新，使用目前版本；否則停止。
4. 所有輸出先寫入暫存檔，成功後才替換，失敗時回滾。目錄 CRC 由解壓後的 UnityFS 區塊資料計算，包含區塊對齊填充；不可用一般檔案 CRC 取代。

這段邏輯是為了處理「Steam 只更新部分檔案」的混合狀態。若遊戲更新後工具仍能辨識原始檔，通常不需要任何手動清理。

## 附錄：本次基準與常用指令

- 基準日期：2026-10-20
- 文字：5,398 筆，4 個語言表
- 圖片：3 張本地化圖片 + 1 張內建主選單標題
- 原始簡中快照：`backups/source-20261020.csv`（本機維護檔，未隨公開版提供）
- 翻譯備份：`backups/translations-20261020-before-update.csv`
- 工具狀態 schema：2

常用指令：

```powershell
# 抽取新原文與 OpenCC 初稿
py ".\localization\zh-Hant\tools\extract_convert.py" `
  --game "C:\Program Files (x86)\Steam\steamapps\common\Dressmaker" `
  --source-out ".\localization\zh-Hant\backups\update-YYYYMMDD\source.csv" `
  --out ".\localization\zh-Hant\backups\update-YYYYMMDD\opencc.csv"

# 與上一版原文比對
py ".\localization\zh-Hant\tools\diff_update.py" `
  --new-source ".\localization\zh-Hant\backups\update-YYYYMMDD\source.csv" `
  --old-source ".\localization\zh-Hant\backups\source-20261020.csv" `
  --out-dir ".\localization\zh-Hant\backups\update-YYYYMMDD"

# 重建工具
py -m PyInstaller --noconfirm --clean ".\localization\zh-Hant\tools\DressmakerZHant.spec"
Copy-Item ".\dist\DressmakerZHant.exe" ".\localization\zh-Hant\release\DressmakerZHant.exe" -Force

# 測試副本安裝與還原
& ".\localization\zh-Hant\release\DressmakerZHant.exe" --install "C:\Projects\dressmaker-zh-hant\test_game"
& ".\localization\zh-Hant\release\DressmakerZHant.exe" --restore "C:\Projects\dressmaker-zh-hant\test_game"
```
