#!/usr/bin/env python3
"""
MyType Voice Input for Windows
Powered by Gemini API

快捷鍵按一下開始錄音，再按一下停止並辨識，辨識完成後自動貼入當前輸入框。
"""

import os
import sys
import json
import wave
import time
import threading
import tempfile
from pathlib import Path

import numpy as np
import sounddevice as sd
import keyboard
import pyperclip
import google.generativeai as genai
import tkinter as tk
from tkinter import simpledialog


# ─── 設定 ──────────────────────────────────────────────────────────────────────

CONFIG_PATH = Path(__file__).parent / "config.json"

DEFAULT_CONFIG = {
    "api_key": "",
    "hotkey": "ctrl+alt+space",
    "model": "gemini-2.0-flash",
    "sample_rate": 16000,
    "channels": 1,
    "auto_paste": True,
    "preview_seconds": 2.0,
    "window_opacity": 0.92,
}

PROMPT = (
    "請將這段音訊轉錄成繁體中文文字。\n"
    "規則：\n"
    "1. 去除語氣詞（嗯、啊、那個、就是、然後）\n"
    "2. 自動加入適當標點符號\n"
    "3. 英文專有名詞保留原文\n"
    "只輸出最終文字，不附任何說明或解釋。"
)


def load_config() -> dict:
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, encoding="utf-8") as f:
            cfg = json.load(f)
        for k, v in DEFAULT_CONFIG.items():
            cfg.setdefault(k, v)
        return cfg
    save_config(DEFAULT_CONFIG)
    return DEFAULT_CONFIG.copy()


def save_config(cfg: dict):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


# ─── 音訊錄製 ──────────────────────────────────────────────────────────────────

class AudioRecorder:
    def __init__(self, sample_rate: int = 16000, channels: int = 1):
        self.sample_rate = sample_rate
        self.channels = channels
        self._frames: list[np.ndarray] = []
        self._stream = None

    def start(self):
        self._frames = []
        self._stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=self.channels,
            dtype="int16",
            callback=self._callback,
        )
        self._stream.start()

    def _callback(self, indata, frames, time_info, status):
        self._frames.append(indata.copy())

    def stop(self) -> float:
        """停止錄音，回傳錄音秒數。"""
        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        return self.duration

    def save_wav(self, path: str) -> bool:
        if not self._frames:
            return False
        audio = np.concatenate(self._frames, axis=0)
        with wave.open(path, "wb") as wf:
            wf.setnchannels(self.channels)
            wf.setsampwidth(2)  # int16 = 2 bytes
            wf.setframerate(self.sample_rate)
            wf.writeframes(audio.tobytes())
        return True

    @property
    def duration(self) -> float:
        if not self._frames:
            return 0.0
        return sum(len(f) for f in self._frames) / self.sample_rate


# ─── Gemini ASR ────────────────────────────────────────────────────────────────

class GeminiASR:
    def __init__(self, api_key: str, model_name: str):
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel(model_name)

    def transcribe(self, wav_path: str) -> str:
        audio_file = genai.upload_file(wav_path, mime_type="audio/wav")
        try:
            resp = self.model.generate_content([PROMPT, audio_file])
            return resp.text.strip()
        finally:
            try:
                genai.delete_file(audio_file.name)
            except Exception:
                pass


# ─── 懸浮 UI ───────────────────────────────────────────────────────────────────

BG      = "#1e1e2e"
FG      = "#cdd6f4"
FG_SUB  = "#7f849c"
C_REC   = "#f38ba8"
C_PROC  = "#fab387"
C_OK    = "#a6e3a1"
C_BTN   = "#313244"
C_GREEN = "#40a02b"


class FloatingUI:
    """右下角懸浮視窗，顯示錄音狀態與辨識結果預覽。"""

    def __init__(self, root: tk.Tk, config: dict):
        self.root = root
        self.cfg = config
        self.on_confirm: callable = None
        self.on_cancel: callable = None
        self._text = ""
        self._timer_id = None
        self._drag_x = self._drag_y = 0

        self._build()

    def _build(self):
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", self.cfg.get("window_opacity", 0.92))
        self.root.configure(bg=BG)
        self.root.withdraw()

        self.root.bind("<ButtonPress-1>", self._drag_start)
        self.root.bind("<B1-Motion>",     self._drag_move)
        self.root.bind("<Return>",        lambda e: self._confirm())
        self.root.bind("<Escape>",        lambda e: self._cancel())

        # 狀態列
        bar = tk.Frame(self.root, bg=BG)
        bar.pack(fill=tk.X, padx=12, pady=(10, 4))

        self.dot = tk.Canvas(bar, width=10, height=10, bg=BG, highlightthickness=0)
        self.dot.pack(side=tk.LEFT, padx=(0, 6))

        self.status_var = tk.StringVar()
        tk.Label(bar, textvariable=self.status_var, bg=BG, fg=FG_SUB,
                 font=("Segoe UI", 9)).pack(side=tk.LEFT)

        # 文字預覽區（初始隱藏）
        self.preview_frame = tk.Frame(self.root, bg=BG)

        self.text_var = tk.StringVar()
        tk.Label(
            self.preview_frame, textvariable=self.text_var,
            bg=BG, fg=FG, font=("Segoe UI", 11),
            wraplength=380, justify=tk.LEFT, anchor="w",
        ).pack(fill=tk.X, padx=12, pady=(0, 6))

        btn_bar = tk.Frame(self.preview_frame, bg=BG)
        btn_bar.pack(fill=tk.X, padx=12, pady=(0, 10))

        tk.Button(
            btn_bar, text="貼上  ↵ Enter",
            bg=C_GREEN, fg="white", relief="flat",
            font=("Segoe UI", 9), padx=10, pady=4, cursor="hand2",
            command=self._confirm,
        ).pack(side=tk.LEFT, padx=(0, 6))

        tk.Button(
            btn_bar, text="取消  Esc",
            bg=C_BTN, fg=FG, relief="flat",
            font=("Segoe UI", 9), padx=10, pady=4, cursor="hand2",
            command=self._cancel,
        ).pack(side=tk.LEFT)

    # ── 拖曳 ────────────────────────────────────────────────────────────────────

    def _drag_start(self, e):
        self._drag_x, self._drag_y = e.x, e.y

    def _drag_move(self, e):
        x = self.root.winfo_x() + (e.x - self._drag_x)
        y = self.root.winfo_y() + (e.y - self._drag_y)
        self.root.geometry(f"+{x}+{y}")

    # ── 工具 ────────────────────────────────────────────────────────────────────

    def _set_dot(self, color: str):
        self.dot.delete("all")
        self.dot.create_oval(1, 1, 9, 9, fill=color, outline="")

    def _place(self, fixed_h: int | None = None):
        w  = 430
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        x  = sw - w - 20
        if fixed_h:
            self.root.geometry(f"{w}x{fixed_h}+{x}+{sh - fixed_h - 60}")
        else:
            self.root.update_idletasks()
            h = self.root.winfo_reqheight()
            self.root.geometry(f"{w}x{h}+{x}+{sh - h - 60}")

    def _cancel_timer(self):
        if self._timer_id:
            self.root.after_cancel(self._timer_id)
            self._timer_id = None

    # ── 狀態切換（公開 API）────────────────────────────────────────────────────

    def show_recording(self):
        self._cancel_timer()
        self.preview_frame.pack_forget()
        self._set_dot(C_REC)
        self._place(50)
        self.root.deiconify()
        self._rec_start = time.time()
        self._tick()

    def _tick(self):
        elapsed = time.time() - self._rec_start
        self.status_var.set(f"錄音中  {elapsed:.1f}s  ·  再按快捷鍵停止")
        self._timer_id = self.root.after(100, self._tick)

    def show_processing(self):
        self._cancel_timer()
        self._set_dot(C_PROC)
        self.status_var.set("傳送至 Gemini 辨識中…")
        self._place(50)

    def show_preview(self, text: str):
        self._cancel_timer()
        self._text = text
        self.text_var.set(text)
        self._set_dot(C_OK)
        self.preview_frame.pack(fill=tk.X)
        self._place()
        self.root.focus_force()

        if self.cfg.get("auto_paste", True):
            secs = float(self.cfg.get("preview_seconds", 2.0))
            self._countdown(secs)
        else:
            self.status_var.set("辨識完成  ·  按 Enter 貼上，Esc 取消")

    def _countdown(self, remaining: float):
        if remaining <= 0:
            self._confirm()
            return
        self.status_var.set(f"辨識完成  ·  {remaining:.1f}s 後自動貼上  ·  Esc 取消")
        self._timer_id = self.root.after(
            100, lambda: self._countdown(round(remaining - 0.1, 1))
        )

    def hide(self):
        self._cancel_timer()
        self.preview_frame.pack_forget()
        self.root.withdraw()

    # ── 動作 ────────────────────────────────────────────────────────────────────

    def _confirm(self):
        self._cancel_timer()
        if self.on_confirm:
            self.on_confirm(self._text)

    def _cancel(self):
        self._cancel_timer()
        if self.on_cancel:
            self.on_cancel()


# ─── 主應用程式 ────────────────────────────────────────────────────────────────

class MyTypeApp:
    def __init__(self):
        self.cfg = load_config()
        self._ensure_api_key()

        self.recorder = AudioRecorder(
            sample_rate=self.cfg["sample_rate"],
            channels=self.cfg["channels"],
        )
        self.asr = GeminiASR(self.cfg["api_key"], self.cfg["model"])

        self._recording = False
        self._busy = False          # 辨識進行中，封鎖快捷鍵
        self._target_hwnd = None    # 錄音時的前景視窗

        self.root = tk.Tk()
        self.root.title("MyType")
        self.ui = FloatingUI(self.root, self.cfg)
        self.ui.on_confirm = self._paste
        self.ui.on_cancel  = self._cancel

        self.root.protocol("WM_DELETE_WINDOW", self._quit)

    # ── 初始設定 ────────────────────────────────────────────────────────────────

    def _ensure_api_key(self):
        if self.cfg.get("api_key"):
            return
        # 首次執行：彈出輸入框要求填入 API Key
        temp = tk.Tk()
        temp.withdraw()
        key = simpledialog.askstring(
            "MyType 初始設定",
            "請輸入您的 Gemini API Key：\n（可在 https://aistudio.google.com/app/apikey 取得）",
            parent=temp,
        )
        temp.destroy()
        if not key or not key.strip():
            print("[MyType] 未設定 API Key，程式結束")
            sys.exit(1)
        self.cfg["api_key"] = key.strip()
        save_config(self.cfg)
        print("[MyType] API Key 已儲存至 config.json")

    # ── 快捷鍵 ──────────────────────────────────────────────────────────────────

    def _register_hotkey(self):
        hk = self.cfg["hotkey"]
        keyboard.add_hotkey(hk, self._toggle, suppress=True)
        print(f"[MyType] 就緒  快捷鍵：{hk}")
        print("[MyType] Ctrl+C 或關閉視窗結束程式")

    def _toggle(self):
        if self._busy:
            return
        if not self._recording:
            self._start_recording()
        else:
            self._stop_recording()

    # ── 錄音流程 ────────────────────────────────────────────────────────────────

    def _start_recording(self):
        try:
            import ctypes
            self._target_hwnd = ctypes.windll.user32.GetForegroundWindow()
        except Exception:
            self._target_hwnd = None

        self._recording = True
        self.recorder.start()
        self.root.after(0, self.ui.show_recording)

    def _stop_recording(self):
        self._recording = False
        self._busy = True
        dur = self.recorder.stop()

        if dur < 0.3:
            print(f"[MyType] 錄音太短（{dur:.2f}s），已忽略")
            self._busy = False
            self.root.after(0, self.ui.hide)
            return

        self.root.after(0, self.ui.show_processing)
        threading.Thread(target=self._transcribe_worker, daemon=True).start()

    # ── 辨識 Worker（背景執行緒）────────────────────────────────────────────────

    def _transcribe_worker(self):
        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        path = tmp.name
        tmp.close()
        try:
            if not self.recorder.save_wav(path):
                raise RuntimeError("錄音資料為空")
            text = self.asr.transcribe(path)
            print(f"[MyType] 辨識：{text}")
            self.root.after(0, lambda: self.ui.show_preview(text))
        except Exception as e:
            print(f"[MyType] 辨識失敗：{e}")
            self.root.after(0, self.ui.hide)
        finally:
            self._busy = False
            try:
                os.unlink(path)
            except Exception:
                pass

    # ── 貼上 ────────────────────────────────────────────────────────────────────

    def _paste(self, text: str):
        self.ui.hide()
        if not text:
            return
        self.root.after(80, lambda: self._do_paste(text))

    def _do_paste(self, text: str):
        if self._target_hwnd:
            try:
                import ctypes
                # Alt 鍵觸發技巧，允許跨程序切換前景視窗
                ctypes.windll.user32.keybd_event(0x12, 0, 0, 0)       # VK_MENU down
                ctypes.windll.user32.SetForegroundWindow(self._target_hwnd)
                ctypes.windll.user32.keybd_event(0x12, 0, 0x0002, 0)  # VK_MENU up
                time.sleep(0.12)
            except Exception as e:
                print(f"[MyType] 焦點切換失敗：{e}")

        pyperclip.copy(text)
        keyboard.press_and_release("ctrl+v")
        preview = text[:50] + ("…" if len(text) > 50 else "")
        print(f"[MyType] 已貼上：{preview}")

    def _cancel(self):
        self.ui.hide()
        print("[MyType] 已取消")

    # ── 結束 ────────────────────────────────────────────────────────────────────

    def _quit(self):
        keyboard.unhook_all()
        self.root.destroy()

    def run(self):
        self._register_hotkey()
        try:
            self.root.mainloop()
        except KeyboardInterrupt:
            self._quit()


# ─── 入口 ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app = MyTypeApp()
    app.run()
