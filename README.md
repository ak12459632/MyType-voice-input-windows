# MyType Voice Input for Windows

Windows 語音輸入工具——按快捷鍵開始錄音，放開後由 **Groq Whisper** 自動辨識成**繁體中文與英文**，並貼入任何輸入框。

---

## 功能特色

- 全域快捷鍵（預設 `Ctrl+Alt+Space`），在任何視窗皆可觸發
- 錄音完畢後傳送至 Groq Whisper API，**自動偵測語言**：支援繁體中文（台灣用語）、英文，及中英混合輸入
- **圓角深紫色懸浮視窗**：即時預覽辨識結果，倒數後自動貼入
- **設定視窗**（`Ctrl+Alt+S`）：GUI 介面管理所有設定，4 個分頁，儲存後即時生效
  - **API & 模型**：管理 Groq API Key、測試連線、選擇 Whisper 辨識模型
  - **音訊 & 快捷鍵**：選擇錄音裝置、自訂錄音快捷鍵與設定視窗快捷鍵
  - **文字後處理**：可選啟用 Groq LLaMA，自動去除語氣詞、修正數字格式、補全標點
  - **個人詞庫**：自訂辨識後替換詞條（例：`skrf` → `scikit-rf`），儲存於 `lexicon.json`
- **兩組快捷鍵均可自訂**：錄音快捷鍵與設定視窗快捷鍵皆可在 GUI 內錄製設定
- 所有錄音裝置在設定視窗內管理，無需重啟程式

---

## 系統需求

| 項目 | 需求 |
|---|---|
| 作業系統 | Windows 10 / 11 |
| Python | 3.10 以上 |
| 麥克風 | 任何 Windows 可辨識的錄音裝置 |
| 網路 | 需要（Groq API 為雲端服務） |
| Groq API Key | 需要（免費帳號即可） |

---

## 安裝步驟

### 第一步：安裝 Python

前往 [python.org](https://www.python.org/downloads/) 下載並安裝 Python 3.10 以上版本。

> 安裝時請勾選 **「Add Python to PATH」**。

安裝完成後，開啟 **PowerShell** 確認：

```powershell
python --version
```

### 第二步：下載本專案

**方法 A：直接下載 ZIP**

點擊頁面右上角的綠色 **Code** 按鈕 → **Download ZIP** → 解壓縮到任意資料夾。

**方法 B：使用 Git Clone**

```powershell
git clone https://github.com/ak12459632/MyType-voice-input-windows.git
cd MyType-voice-input-windows
```

### 第三步：安裝依賴套件

```powershell
pip install -r requirements.txt
```

| 套件 | 用途 |
|---|---|
| `groq` | 呼叫 Groq Whisper API 進行語音辨識，以及 LLaMA 文字後處理 |
| `sounddevice` | 從麥克風錄製音訊 |
| `numpy` | 處理錄音資料 |
| `keyboard` | 監聽全域快捷鍵 |
| `pyperclip` | 將文字寫入剪貼簿 |

### 第四步：取得 Groq API Key

1. 前往 [console.groq.com/keys](https://console.groq.com/keys)
2. 註冊或登入免費帳號
3. 點擊 **Create API key**
4. 複製金鑰備用（格式為 `gsk_...`）

> Groq 免費帳號每天可使用 **7,200 次**語音辨識請求，對個人使用綽綽有餘。

### 第五步：啟動程式

```powershell
python mytype.py
```

首次啟動時會自動彈出輸入框，貼入 API Key 後按確定，金鑰會自動儲存至 `config.json`。

啟動成功後終端機顯示：

```
[MyType] 就緒  快捷鍵：ctrl+alt+space　設定：ctrl+alt+s
[MyType] Ctrl+C 或關閉視窗結束程式
```

---

## 使用方法

```
1. 將游標點入任何輸入框（記事本、瀏覽器、聊天視窗...）

2. 按下 Ctrl + Alt + Space  →  右下角出現懸浮視窗，開始錄音

3. 說出想輸入的內容（中文、英文或中英混合皆可）

4. 再按一次 Ctrl + Alt + Space  →  停止錄音，傳送至 Groq 辨識

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

## 設定視窗（Ctrl+Alt+S）

按下 `Ctrl+Alt+S` 開啟設定視窗，包含四個分頁：

### 分頁一：API & 模型

| 項目 | 說明 |
|---|---|
| Groq API Key | 顯示/隱藏、修改 API Key |
| 測試連線 | 即時驗證 Key 是否可用 |
| 辨識模型 | `whisper-large-v3-turbo`（預設）或 `whisper-large-v3` |
| 語言 | 自動偵測，支援繁體中文及英文混合輸入 |

### 分頁二：音訊 & 快捷鍵

| 項目 | 說明 |
|---|---|
| 錄音裝置 | 從所有可用輸入裝置中選擇，儲存後立即生效 |
| 錄音快捷鍵 | 自訂觸發錄音的全域快捷鍵（預設 `ctrl+alt+space`） |
| 設定視窗快捷鍵 | 自訂開啟設定視窗的快捷鍵（預設 `ctrl+alt+s`） |

> 快捷鍵可手動輸入，或點「錄製」後直接按下想要的組合鍵。

### 分頁三：文字後處理

啟用後，每次辨識結果會額外送至 Groq LLaMA 進行潤稿：

- 去除語氣詞（嗯、啊、那個、就是、然後）
- 修正數字與日期格式（例：三月十五號 → 3/15）
- 補全標點符號

| 模型 | 速度 | 說明 |
|---|---|---|
| `llama-3.1-8b-instant` | 快（+0.3s） | 預設，建議使用 |
| `llama-3.3-70b-versatile` | 較慢（+1s） | 品質更高 |

> 不啟用時仍會透過 Whisper Prompt 引導輸出繁體字，效果已相當不錯。

### 分頁四：個人詞庫

自訂辨識後的替換規則，每次貼上前自動套用：

- 新增詞條：填入「原詞」→「替換為」→ 點「新增」
- 刪除詞條：點選列表中的詞條 → 點「刪除選取」

詞庫儲存於 `lexicon.json`（不上傳 GitHub）。

**使用範例：**

| 原詞 | 替換為 | 用途 |
|---|---|---|
| `skrf` | `scikit-rf` | 技術縮寫展開 |
| `WH一千` | `WH-1000XM4` | 型號正確拼寫 |

---

## 設定說明（config.json）

```json
{
  "groq_api_key": "gsk_...",
  "hotkey": "ctrl+alt+space",
  "settings_hotkey": "ctrl+alt+s",
  "model": "whisper-large-v3-turbo",
  "sample_rate": 16000,
  "channels": 1,
  "device": 2,
  "auto_paste": true,
  "preview_seconds": 2.0,
  "window_opacity": 0.95,
  "post_process": false,
  "post_process_model": "llama-3.1-8b-instant"
}
```

| 欄位 | 說明 |
|---|---|
| `groq_api_key` | Groq API Key |
| `hotkey` | 錄音快捷鍵 |
| `settings_hotkey` | 設定視窗快捷鍵 |
| `model` | Whisper 辨識模型 |
| `device` | 錄音裝置索引（`null` = 系統預設） |
| `auto_paste` | `true` = 倒數後自動貼上；`false` = 等待手動確認 |
| `preview_seconds` | 自動貼上前的預覽秒數 |
| `window_opacity` | 懸浮視窗透明度（0.0 ~ 1.0） |
| `post_process` | 是否啟用 LLaMA 文字後處理 |
| `post_process_model` | 後處理使用的 LLaMA 模型 |

---

## 常見問題

### Q：按快捷鍵沒有反應？

部分防毒軟體會封鎖鍵盤 hook，嘗試以**系統管理員身分**執行：

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

### Q：辨識結果輸出簡體字？

確認 `config.json` 中的模型為 `whisper-large-v3-turbo`。若仍有問題，可啟用文字後處理讓 LLaMA 進行繁化。

### Q：辨識到背景音而非我說的話？

錄音時麥克風會收取所有環境聲音。建議：

- 使用耳麥（麥克風離嘴近）
- 錄音時將背景影片/音樂靜音
- 在設定 → 音訊 & 快捷鍵 中切換至指向性更強的麥克風

### Q：如何讓程式開機自動啟動？

1. 按下 `Win + R`，輸入 `shell:startup`，開啟「啟動」資料夾
2. 建立 `.bat` 檔，內容如下：

```bat
@echo off
pythonw "D:\MyType-voice-input-windows\mytype.py"
```

3. 存檔後重新開機即自動啟動（`pythonw` 不會顯示終端機視窗）

---

## 授權

MIT License — 自由使用、修改與散佈。
