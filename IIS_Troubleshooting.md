# IIS 500 錯誤排除指南

雖然您的 `app.py` 在終端機可以正常執行，但 IIS 回傳 500 錯誤通常代表 **設定檔 (web.config)** 或 **權限** 有問題。

請依照以下步驟進行檢查：

## 1. 檢查錯誤日誌 (最重要)

請查看您的專案目錄下是否產生了 `wfastcgi.log` 檔案 (路徑應為 `D:\Python\W52_FlaskApp\W52_DigitalSOP\wfastcgi.log`)。
*   **如果有檔案**：請開啟查看最後幾行的錯誤訊息。這會直接告訴我們原因 (例如 `ImportError`, `PermissionError` 等)。
*   **如果沒有檔案**：代表 IIS 連寫入 Log 的權限都沒有，這通常是**權限問題**。

## 2. 檢查資料夾權限

IIS 的執行帳號 (`IIS_IUSRS`) 必須要有讀取和執行的權限。
1.  對 `D:\Python\W52_FlaskApp\W52_DigitalSOP` 資料夾按右鍵 > **內容** > **安全性**。
2.  確認 `IIS_IUSRS` 使用者是否存在，且擁有 **讀取及執行** 的權限。
3.  **重要**：如果您的 Python 虛擬環境 (`.venv`) 在這個資料夾內，權限通常會繼承。但如果您有複製或移動過檔案，請確保 `.venv` 資料夾也有相同的權限。

## 3. 確認 wfastcgi.py 的真實路徑

我在您的截圖中發現一個奇怪的地方：
*   之前的截圖顯示路徑有 `.venv`：`...W52_DigitalSOP\.venv\Lib\site-packages`
*   剛剛執行 `app.py` 的錯誤訊息卻顯示沒有 `.venv`：`...W52_DigitalSOP\Lib\site-packages`

這代表您的檔案結構可能與 `web.config` 設定不符。請在終端機執行以下指令，確認 `wfastcgi` 到底安裝在哪裡：

```bash
pip show wfastcgi
```

請查看 `Location:` 欄位。
*   如果顯示 `...W52_DigitalSOP\.venv\Lib\site-packages`，則目前的 `web.config` 路徑是正確的。
*   如果顯示 `...W52_DigitalSOP\Lib\site-packages` (沒有 .venv)，則您需要修改 `web.config` 中的路徑，將 `.venv\` 移除。

## 4. 測試 web.config 修改 (如果上述都沒問題)

如果路徑確認無誤，您可以嘗試在 `web.config` 中加入環境變數設定，確保 Python 能找到正確的模組：

```xml
<appSettings>
    <!-- 原有的設定 -->
    <add key="WSGI_HANDLER" value="app.app" />
    <add key="PYTHONPATH" value="D:\Python\W52_FlaskApp\W52_DigitalSOP" />
    <add key="WSGI_LOG" value="D:\Python\W52_FlaskApp\W52_DigitalSOP\wfastcgi.log" />
    
    <!-- 新增：強制設定 PATH -->
    <!-- 請將此處的 .venv 路徑改為您 pip show wfastcgi 顯示的真實路徑 -->
    <add key="PATH" value="D:\Python\W52_FlaskApp\W52_DigitalSOP\.venv\Scripts;%PATH%" />
</appSettings>
```
