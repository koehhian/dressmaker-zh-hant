# 發布驗證紀錄

日期：2026-11-06（臺灣時間）。本次沿用 2026-10-20 的 EXE，未修改安裝器或翻譯主檔。

| 項目 | 實際結果 |
| --- | --- |
| 本機 Steam 遊戲基準 | App 4019220 / build 26043449 |
| 翻譯表 | 5,398 筆，4 個語言表，無重複 `(table,id)` |
| 原始碼：安裝 → 重複安裝 → 還原 | 通過 |
| EXE：安裝 → 重複安裝 → 還原 | 通過 |
| 內建主選單標題串流 | 安裝後雜湊改變，還原後完全一致 |
| 還原完整性 | 5 個受測遊戲檔案與語言偏好逐位元恢復 |
| 備份清理 | 還原後測試副本無 `.zh-hant-*` 殘留 |
| 畫面 | README 使用 2026-10-20 保存的實際主選單與安裝器截圖；本次未重新遊玩全流程 |

測試使用暫存遊戲副本及隔離的使用者設定，不修改正式遊戲。輸入資產取自本機遊戲原始備份；安裝器保留原有覆蓋率、CRC 與檔案驗證。

```powershell
py tests/roundtrip.py --game "C:\Program Files (x86)\Steam\steamapps\common\Dressmaker"
py tests/roundtrip.py --game "C:\Program Files (x86)\Steam\steamapps\common\Dressmaker" --exe "localization/zh-Hant/release/DressmakerZHant.exe"
```

兩次均結束碼 0，輸出 `PASS: install, repeat install, title stream, exact file/profile restoration; isolated temporary fixture`。

安裝器 SHA-256：`98f68396bfb45f121cd1d18e740907cb126850d4932fdda5c268ded21d94a6cc`

以上驗證不代表所有關卡、所有譯文、未測試的遊戲更新版本或其他作業系統皆已通過。
