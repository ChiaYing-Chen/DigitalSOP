# IIS Flask 部署完成報告

我已經依照 `IIS_Flask_Deployment_SOP.md` 為您準備好所有部署需要的檔案。

## 已完成項目

1.  **安裝 wfastcgi**: 已確認安裝。
2.  **修改 `app.py`**:
    *   已加入 `IISMiddleware` 以支援子目錄部署 (預設 Alias 為 `/DigitalSOP`)。
    *   已將資料庫路徑改為絕對路徑，避免讀取錯誤。
3.  **建立 `web.config`**:
    *   已設定 Python 路徑: `D:\Python\Python312\python.exe`
    *   已設定 wfastcgi 路徑: `d:\python\python312\lib\site-packages\wfastcgi.py`
    *   已設定專案路徑: `D:\W52_DigitalSOP`
4.  **建立 `requirements.txt`**: 列出專案依賴套件。

## 您需要執行的後續步驟 (請依照 SOP 繼續執行)

由於權限限制，我無法直接設定 IIS，請您手動執行以下步驟：

### 1. 註冊 wfastcgi (若尚未執行)
請以**系統管理員身分**開啟 PowerShell 或 CMD，執行以下指令：
```powershell
wfastcgi-enable
```
*   請確認輸出的路徑與 `web.config` 中的 `scriptProcessor` 設定一致。如果不一致，請手動更新 `web.config`。

### 2. 設定 IIS 應用程式
1.  開啟 **IIS 管理員**。
2.  在站台 (例如 Default Web Site) 按右鍵 -> **新增應用程式**。
3.  **別名 (Alias)**: 輸入 `DigitalSOP` (需與 `app.py` 中的 `script_name` 一致)。
4.  **實體路徑**: 選擇 `D:\W52_DigitalSOP`。
5.  點擊確定。

### 3. 設定資料夾權限 (關鍵！)
1.  在檔案總管對 `D:\W52_DigitalSOP` 按右鍵 -> **內容** -> **安全性**。
2.  點擊 **編輯** -> **新增**。
3.  輸入 `IIS_IUSRS` -> 確定。
4.  勾選 **讀取及執行** (Read & execute) 和 **列出資料夾內容**。
5.  點擊確定。

完成後，您應該可以透過 `http://localhost/DigitalSOP` 存取您的應用程式。
