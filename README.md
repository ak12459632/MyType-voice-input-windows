# MyType Voice Input for Windows

Windows 語音輸入工具——按快捷鍵開始錄音，放開後由 **Gemini API** 自動辨識成文字，並貼入任何輸入框。

---

## 功能特色

- 全域快捷鍵（預設 `Ctrl+Alt+Space`），在任何視窗皆可觸發
- 錄音完畢後傳送至 Gemini API，自動辨識繁體中文
- 辨識同時完成語氣詞過濾與標點符號補全
- 右下角懸浮視窗即時預覽辨識結果
- 倒數計時後自動貼入原輸入框，或手動按 Enter 確認 / Esc 取消
- 所有設定集中於 `config.json`，不需改動程式碼

---

## 系統需求

| 項目 | 需求 |
|---|---|
| 作業系統 | Windows 10 / 11 |
| Python | 3.10 以上 |
| 麥克風 | 任何 Windows 可辨識的錄音裝置 |
| 網路 | 需要（Gemini API 為雲端服務） |
| Gemini API Key | 需要（免費或付費皆可） |

---

## 安裝步驟

### 第一步：安裝 Python

前往 [python.org](https://www.python.org/downloads/) 下載並安裝 Python 3.10 以上版本。

> 安裝時請勾選 **「Add Python to PATH」**。

安裝完成後，開啟 **命令提示字元（cmd）** 或 **PowerShell**，確認安裝成功：

```powershell
python --version
```

應顯示 `Python 3.10.x` 或更新版本。

---

### 第二步：下載本專案

**方法 A：直接下載 ZIP**

1. 點擊頁面右上角的綠色 **Code** 按鈕
2. 選擇 **Download ZIP**
3. 解壓縮到任意資料夾，例如 `D:\MyType Voice Input`

**方法 B：使用 Git Clone**

```powershell
git clone https://github.com/ak12459632/MyType-voice-input-windows.git
cd MyType-voice-input-windows
```

---

### 第三步：安裝依賴套件

在專案資料夾中開啟終端機，執行：

```powershell
pip install -r requirements.txt
```

安裝的套件清單：

| 套件 | 用途 |
|---|---|
| `google-generativeai` | 呼叫 Gemini API 進行語音辨識 |
| `sounddevice` | 從麥克風錄製音訊 |
| `numpy` | 處理錄音資料 |
| `keyboard` | 監聽全域快捷鍵 |
| `pyperclip` | 將文字寫入剪貼簿 |

> 若 `sounddevice` 安裝失敗，改用：
> ```powershell
> pip install sounddevice --only-binary :all:
> ```

---

### 第四步：取得 Gemini API Key

1. 前往 [Google AI Studio](https://aistudio.google.com/app/apikey)
2. 登入 Google 帳號
3. 點擊 **建立 API 金鑰**
4. 複製金鑰備用（格式類似 `AIzaSy...`）

---

### 第五步：設定 API Key

**方法 A：首次執行自動引導（推薦）**

直接執行程式，第一次啟動時會自動彈出輸入框，貼入 API Key 後按確定，金鑰會自動儲存至 `config.json`。

**方法 B：手動編輯設定檔**

複製範本並填入金鑰：

```powershell
copy config.example.json config.json
```

用任意文字編輯器開啟 `config.json`，將 `api_key` 欄位改為你的金鑰：

```json
{
  "api_key": "AIzaSyXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX",
  ...
}
```

---

## 啟動程式

```powershell
python mytype.py
```

啟動成功後，終端機會顯示：

```
[MyType] 就緒  快捷鍵：ctrl+alt+space
[MyType] Ctrl+C 或關閉視窗結束程式
```

**程式在背景持續執行**，不需要保持終端機視窗在前景。

---

## 使用方法

```
1. 將游標點入任何輸入框（記事本、瀏覽器、聊天視窗...）

2. 按下 Ctrl + Alt + Space  →  右下角出現懸浮視窗，開始錄音

3. 說出想輸入的內容

4. 再按一次 Ctrl + Alt + Space  →  停止錄音，傳送至 Gemini 辨識

5. 辨識完成後懸浮視窗顯示結果，倒數 2 秒後自動貼入輸入框
```

### 懸浮視窗操作

| 動作 | 效果 |
|---|---|
| 等待倒數 | 自動貼上並關閉視窗 |
| 按 `Enter` | 立即貼上 |
| 按 `Esc` | 取消，不貼上 |
| 拖曳視窗 | 移動到螢幕任意位置 |

---

## 設定說明（config.json）

```json
{
  "api_key": "",           // Gemini API Key
  "hotkey": "ctrl+alt+space",  // 快捷鍵，可改為 "f9"、"ctrl+shift+r" 等
  "model": "gemini-2.0-flash", // Gemini 模型
  "sample_rate": 16000,    // 錄音取樣率（Hz），建議保持 16000
  "channels": 1,           // 聲道數（1=單聲道）
  "auto_paste": true,      // true=倒數後自動貼上 / false=等待手動確認
  "preview_seconds": 2.0,  // 自動貼上前的預覽秒數
  "window_opacity": 0.92   // 懸浮視窗透明度（0.0~1.0）
}
```

### 快捷鍵格式範例

| 設定值 | 說明 |
|---|---|
| `"ctrl+alt+space"` | 預設值 |
| `"f9"` | 單鍵 F9 |
| `"ctrl+shift+r"` | 組合鍵 |
| `"right ctrl"` | 右 Ctrl 鍵 |

### 模型選擇

| 模型名稱 | 速度 | 準確率 | 備註 |
|---|---|---|---|
| `gemini-2.0-flash` | 快 | 高 | 預設，推薦 |
| `gemini-2.5-flash-preview-05-20` | 中 | 更高 | 付費帳號可用 |
| `gemini-1.5-flash` | 快 | 高 | 備用選項 |

---

## 常見問題

### Q：按快捷鍵沒有反應？

- 確認終端機顯示「就緒」訊息
- 部分防毒軟體會封鎖鍵盤 hook，嘗試以**系統管理員身分**執行：
  ```powershell
  # 在 PowerShell（管理員）中執行
  python mytype.py
  ```

### Q：`sounddevice` 找不到麥克風？

確認 Windows 設定中麥克風已啟用：**設定 → 系統 → 聲音 → 輸入**

列出所有可用錄音裝置：
```python
import sounddevice as sd
print(sd.query_devices())
```

### Q：辨識結果為空或出現錯誤？

- 確認 `config.json` 中的 `api_key` 正確
- 確認有網路連線
- 錄音時間需超過 0.3 秒

### Q：文字貼到錯誤的視窗？

程式在**錄音停止那一刻**記住目標視窗。若你在辨識期間（1~2 秒）點擊了其他視窗，可能貼錯地方。建議：
- 按下第二次快捷鍵停止錄音後，不要移動滑鼠點擊其他地方

### Q：如何讓程式開機自動啟動？

1. 按下 `Win + R`，輸入 `shell:startup`，開啟「啟動」資料夾
2. 在該資料夾中建立一個 `.bat` 檔，內容如下：
   ```bat
   @echo off
   pythonw "D:\MyType Voice Input\mytype.py"
   ```
3. 存檔後重新開機即自動啟動

---

## 授權

MIT License — 自由使用、修改與散佈。
