# 參與校對與維護

歡迎回報錯字、臺灣用語、圖片文字與排版問題。請先搜尋既有 Issues，提供出現場景、原句、建議與實際畫面。

翻譯位於 `localization/zh-Hant/translations.csv`，欄位為 `table,id,text`。修改時保留 `(table,id)`、富文字標籤、換行與格式佔位符，勿只依 OpenCC 結果批次覆蓋已校對內容。遊戲更新請依 [WORKFLOW.md](localization/zh-Hant/WORKFLOW.md) 抽取與比對，在本機保存原文快照，不要上傳原始資產包。

提交 Pull Request 時說明改動目的、影響文字／畫面與實際執行的檢查。若修改安裝或還原程式，使用本機遊戲副本執行 `py tests/roundtrip.py --game "遊戲資料夾"`，確認重複安裝及還原雜湊一致。此測試建立暫存副本，隔離使用者語言設定，不直接修改正式遊戲。

新增圖片請標明來源及可使用範圍。工具程式碼採 MIT；請勿把第三方遊戲內容視為 MIT 資產。
