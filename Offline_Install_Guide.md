# 離線環境安裝 Python 套件指南

由於您的伺服器沒有網際網路連線，我已經幫您將所有需要的套件 (包含 `requirements.txt` 中的項目及其相依套件) 下載到了專案目錄下的 `packages` 資料夾中。

## 步驟 1: 複製檔案

請將整個 `packages` 資料夾以及 `requirements.txt` 複製到您的伺服器上的專案目錄中 (例如 `D:\W52_DigitalSOP`)。

## 步驟 2: 離線安裝

在伺服器的終端機 (PowerShell 或 CMD) 中，切換到專案目錄，並執行以下指令進行離線安裝：

```bash
pip install --no-index --find-links=packages -r requirements.txt
```

### 指令說明：
*   `--no-index`: 告訴 pip 不要去 PyPI (網際網路) 尋找套件。
*   `--find-links=packages`: 告訴 pip 在本地的 `packages` 資料夾中尋找安裝檔。

執行完畢後，您可以使用 `pip list` 確認套件是否已成功安裝。
