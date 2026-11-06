# 發布流程

一般玩家從 Releases 下載；維護者可用 GitHub Desktop 提交及推送。

1. 依更新流程校對並重建安裝器，在遊戲副本上完成安裝、重複安裝與還原驗證。
2. 將已驗證 EXE 放到 `distribution/DressmakerZHant.exe`。此檔案是玩家補丁安裝器，不是遊戲本體。
3. 更新 `release.json` 的 tag、title、測試用 Steam build 與安裝器 SHA-256；每個發行版本使用新的 tag。
4. 更新 README、使用指南、驗證紀錄及 RELEASE_NOTES，均須寫明相容的 Steam build。
5. 執行 `py scripts/package_release.py`。程式會驗證雜湊與翻譯筆數，生成 Windows ZIP、純原始碼 ZIP、單獨 EXE 與 SHA256SUMS。
6. 使用 GitHub Desktop 提交及 Push origin。`main` 的發行設定、安裝器或打包流程變更會啟動 GitHub Actions；也可手動執行工作流程。
7. 等待 Actions 成功，再檢查 Releases 的四個附件與下載雜湊。發布不會覆寫既有同名版本。

工作流程只使用 GitHub 自動提供、限此儲存庫的短期 token，不需個人存取權杖。發行工作有內容寫入權限，用於建立 tag 與 Release。

原始碼 ZIP 不包含 `distribution/` 的 EXE。從原始碼重建後，須自行放入已驗證安裝器並更新 manifest，才能打包與發布；請勿略過雜湊檢查。
