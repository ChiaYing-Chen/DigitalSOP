# IIS 部署 Flask 應用程式標準作業程序 (SOP)

這份文件詳細記錄了如何在 Windows IIS 上部署 Flask 應用程式。您可以依照此流程將任何 Flask 專案 (包含 `app.py`) 部署到 IIS 上，並支援透過子路徑 (如 `http://IP/MyApp/`) 存取。

## 1. 環境準備 (只需做一次)

在伺服器上確保已安裝以下元件：

1.  **啟用 IIS 和 CGI 功能**：
    *   控制台 > 開啟或關閉 Windows 功能。
    *   Internet Information Services > World Wide Web 服務 > 應用程式開發功能 > 勾選 **CGI**。
2.  **安裝 Python**：確保已安裝 Python (建議 3.8 以上)。
3.  **安裝 wfastcgi**：
    *   開啟終端機 (以管理員身分)，執行：`pip install wfastcgi`
    *   啟用 wfastcgi：`wfastcgi-enable`
    *   **記下輸出的路徑**，例如：`c:\python\python.exe|c:\python\lib\site-packages\wfastcgi.py` (稍後 `web.config` 會用到)。

---

## 2. 專案準備

假設您的 Flask 專案位於 `D:\Projects\MyApp`，主程式為 `app.py`。

### 步驟 2.1：安裝依賴
在專案目錄下建立 `requirements.txt` 並安裝：
```text
Flask
wfastcgi
# 其他您的專案需要的套件
```
執行：`pip install -r requirements.txt`

### 步驟 2.2：建立 `web.config`
在專案根目錄 (`D:\Projects\MyApp`) 建立 `web.config` 檔案，內容如下：

```xml
<?xml version="1.0" encoding="utf-8"?>
<configuration>
  <system.webServer>
    <handlers>
      <add name="Python FastCGI"
           path="*"
           verb="*"
           modules="FastCgiModule"
           scriptProcessor="[您的Python路徑]|[您的wfastcgi.py路徑]"
           resourceType="Unspecified"
           requireAccess="Script" />
    </handlers>
  </system.webServer>
  <appSettings>
    <add key="WSGI_HANDLER" value="app.app" /> <!-- app.py 中的 app 變數 -->
    <add key="PYTHONPATH" value="D:\Projects\MyApp" /> <!-- 專案根目錄 -->
    <add key="WSGI_LOG" value="D:\Projects\MyApp\wfastcgi.log" /> <!-- 錯誤日誌路徑 -->
  </appSettings>
</configuration>
```
*   **注意**：`scriptProcessor` 的值請填入步驟 1 `wfastcgi-enable` 輸出的內容。

### 步驟 2.3：修改 `app.py` (關鍵！)
為了讓 Flask 在 IIS 的子應用程式 (如 `/MyApp`) 下正常運作，**必須**加入 `IISMiddleware` 並使用絕對路徑。

請在 `app.py` 中加入以下程式碼：

```python
import sys
import os
from flask import Flask

app = Flask(__name__)

# 1. 使用絕對路徑 (避免 IIS 找不到檔案)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# 範例：讀取同目錄下的資料夾
DATA_FOLDER = os.path.join(BASE_DIR, 'data')

# ... 您的路由程式碼 ...

# 2. 加入 IIS Middleware (處理子路徑問題)
class IISMiddleware:
    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        # 取得目前的請求路徑
        path = environ.get('PATH_INFO', '')
        
        # 設定您的 IIS 應用程式別名 (Alias)，例如 '/MyApp'
        # 如果是直接架在根目錄 (Port 80)，則不需要這段
        script_name = '/MyApp' 
        
        if path.startswith(script_name):
            environ['SCRIPT_NAME'] = script_name
            # 移除前綴，讓 Flask 路由能正確匹配
            new_path = path[len(script_name):]
            if not new_path.startswith('/'):
                new_path = '/' + new_path
            environ['PATH_INFO'] = new_path
            
        return self.app(environ, start_response)

# 套用 Middleware
app.wsgi_app = IISMiddleware(app.wsgi_app)

if __name__ == '__main__':
    app.run()
```

---

## 3. IIS 設定

1.  開啟 **IIS 管理員**。
2.  在 **Default Web Site** (或您自訂的站台) 上按右鍵 > **新增應用程式** (Add Application)。
3.  **別名 (Alias)**：輸入您想要的網址路徑，例如 `MyApp` (這要跟 `app.py` 裡的 `script_name` 一致)。
4.  **實體路徑**：選擇您的專案資料夾 `D:\Projects\MyApp`。
5.  點擊確定。

---

## 4. 權限設定 (最常被忽略的一步)

如果出現 `500 Internal Server Error` 且 log 顯示 `PermissionError`，請執行此步驟。

1.  開啟檔案總管，對專案資料夾 (`D:\Projects\MyApp`) 按右鍵 > **內容** > **安全性**。
2.  點擊 **編輯** > **新增**。
3.  輸入 **`IIS_IUSRS`** > 檢查名稱 > 確定。
4.  勾選 **讀取及執行** (Read & execute) 和 **列出資料夾內容** (List folder contents)。
5.  點擊確定套用。

---

## 5. 疑難排解

如果網頁顯示 **500 Internal Server Error**：

1.  **檢查 Log**：查看 `web.config` 中設定的 `wfastcgi.log` 檔案。
2.  **常見錯誤**：
    *   `PermissionError`: 請重新檢查步驟 4 的權限設定。
    *   `ModuleNotFoundError`: 確認 `requirements.txt` 的套件都有安裝在 `web.config` 指定的 Python 環境中。
    *   `ImportError`: 確認 `WSGI_HANDLER` 設定正確 (例如 `app.app`)。
3.  **進階偵錯**：
    如果 log 看不出原因，可以暫時在 `app.py` 加入以下設定，讓錯誤訊息直接顯示在瀏覽器上 ( **注意：排錯完後請務必移除，以免洩漏資訊** )：
    ```python
    app.config['PROPAGATE_EXCEPTIONS'] = True
    ```
