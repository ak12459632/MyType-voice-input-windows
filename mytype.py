#!/usr/bin/env python3
"""
MyType Voice Input for Windows
Powered by Groq Whisper
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
from groq import Groq
import tkinter as tk
from tkinter import ttk, simpledialog


# ─── 設定 ─────────────────────────────────────────────────────────────────────

CONFIG_PATH  = Path(__file__).parent / "config.json"
LEXICON_PATH = Path(__file__).parent / "lexicon.json"

DEFAULT_CONFIG = {
    "groq_api_key": "",
    "hotkey": "ctrl+alt+space",
    "model": "whisper-large-v3-turbo",
    "sample_rate": 16000,
    "channels": 1,
    "device": None,
    "auto_paste": True,
    "preview_seconds": 2.0,
    "window_opacity": 0.92,
    "post_process": False,
    "post_process_model": "llama-3.1-8b-instant",
}

POSTPROCESS_PROMPT = (
    "你是文字潤稿助手。將以下語音辨識結果做最小幅度的修正：\n"
    "1. 去除語氣詞（嗯、啊、那個、就是、然後）\n"
    "2. 修正數字與日期格式（例：三月十五號 → 3/15）\n"
    "3. 補全標點符號\n"
    "4. 保持繁體中文，英文專有名詞維持原文\n"
    "只輸出修正後的文字，不附任何說明。\n\n原文："
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


# ─── 音訊錄製 ─────────────────────────────────────────────────────────────────

class AudioRecorder:
    def __init__(self, sample_rate: int = 16000, channels: int = 1, device=None):
        self.sample_rate = sample_rate
        self.channels    = channels
        self.device      = device
        self._frames: list[np.ndarray] = []
        self._stream = None

    def start(self):
        self._frames = []
        self._stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=self.channels,
            dtype="int16",
            callback=self._callback,
            device=self.device,
        )
        self._stream.start()

    def _callback(self, indata, frames, time_info, status):
        self._frames.append(indata.copy())

    def stop(self) -> float:
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
            wf.setsampwidth(2)
            wf.setframerate(self.sample_rate)
            wf.writeframes(audio.tobytes())
        return True

    @property
    def duration(self) -> float:
        if not self._frames:
            return 0.0
        return sum(len(f) for f in self._frames) / self.sample_rate


# ─── ASR ──────────────────────────────────────────────────────────────────────

class GroqASR:
    def __init__(self, api_key: str, model_name: str):
        self.client     = Groq(api_key=api_key)
        self.model_name = model_name

    def transcribe(self, wav_path: str) -> str:
        with open(wav_path, "rb") as f:
            result = self.client.audio.transcriptions.create(
                model=self.model_name,
                file=f,
                response_format="text",
                language="zh",
                prompt="繁體中文，台灣用語",
            )
        return result.strip() if isinstance(result, str) else result.text.strip()


# ─── 個人詞庫 ─────────────────────────────────────────────────────────────────

class LexiconManager:
    def __init__(self):
        self._entries: dict[str, str] = {}
        self._load()

    def _load(self):
        if LEXICON_PATH.exists():
            with open(LEXICON_PATH, encoding="utf-8") as f:
                self._entries = json.load(f)

    def save(self):
        with open(LEXICON_PATH, "w", encoding="utf-8") as f:
            json.dump(self._entries, f, ensure_ascii=False, indent=2)

    def set_all(self, entries: dict[str, str]):
        self._entries = dict(entries)

    def apply(self, text: str) -> str:
        for src, tgt in self._entries.items():
            text = text.replace(src, tgt)
        return text

    def entries(self) -> dict[str, str]:
        return dict(self._entries)


# ─── 文字後處理 ───────────────────────────────────────────────────────────────

class TextProcessor:
    def __init__(self, client: Groq, model: str, enabled: bool = False):
        self.client  = client
        self.model   = model
        self.enabled = enabled

    def process(self, text: str) -> str:
        if not self.enabled or not text:
            return text
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": POSTPROCESS_PROMPT + text}],
            max_tokens=512,
        )
        return resp.choices[0].message.content.strip()


# ─── UI 顏色常數 ──────────────────────────────────────────────────────────────

BG      = "#1e1e2e"
FG      = "#cdd6f4"
FG_SUB  = "#7f849c"
C_REC   = "#f38ba8"
C_PROC  = "#fab387"
C_OK    = "#a6e3a1"
C_BTN   = "#313244"
C_GREEN = "#40a02b"
C_RED   = "#f38ba8"


def _apply_ttk_style():
    s = ttk.Style()
    s.theme_use("default")
    s.configure("TNotebook",        background=BG,       borderwidth=0)
    s.configure("TNotebook.Tab",    background=C_BTN,    foreground=FG_SUB,
                font=("Segoe UI", 10), padding=[14, 7])
    s.map("TNotebook.Tab",
          background=[("selected", "#585b70")],
          foreground=[("selected", FG)])
    s.configure("TFrame",           background=BG)
    s.configure("Treeview",         background=C_BTN,    foreground=FG,
                fieldbackground=C_BTN, font=("Segoe UI", 10), rowheight=28)
    s.configure("Treeview.Heading", background="#585b70", foreground=FG,
                font=("Segoe UI", 9, "bold"))
    s.map("Treeview",               background=[("selected", "#7f849c")])
    s.configure("Vertical.TScrollbar", background=C_BTN, troughcolor=BG,
                borderwidth=0, arrowsize=14)


# ─── 懸浮 UI ──────────────────────────────────────────────────────────────────

class FloatingUI:
    def __init__(self, root: tk.Tk, config: dict):
        self.root = root
        self.cfg  = config
        self.on_confirm: callable = None
        self.on_cancel:  callable = None
        self._text     = ""
        self._timer_id = None
        self._drag_x   = self._drag_y = 0
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

        bar = tk.Frame(self.root, bg=BG)
        bar.pack(fill=tk.X, padx=12, pady=(10, 4))

        self.dot = tk.Canvas(bar, width=10, height=10, bg=BG, highlightthickness=0)
        self.dot.pack(side=tk.LEFT, padx=(0, 6))

        self.status_var = tk.StringVar()
        tk.Label(bar, textvariable=self.status_var, bg=BG, fg=FG_SUB,
                 font=("Segoe UI", 9)).pack(side=tk.LEFT)

        self.preview_frame = tk.Frame(self.root, bg=BG)

        self.text_var = tk.StringVar()
        tk.Label(
            self.preview_frame, textvariable=self.text_var,
            bg=BG, fg=FG, font=("Segoe UI", 11),
            wraplength=380, justify=tk.LEFT, anchor="w",
        ).pack(fill=tk.X, padx=12, pady=(0, 6))

        btn_bar = tk.Frame(self.preview_frame, bg=BG)
        btn_bar.pack(fill=tk.X, padx=12, pady=(0, 10))

        tk.Button(btn_bar, text="貼上  ↵ Enter",
                  bg=C_GREEN, fg="white", relief="flat",
                  font=("Segoe UI", 9), padx=10, pady=4, cursor="hand2",
                  command=self._confirm).pack(side=tk.LEFT, padx=(0, 6))
        tk.Button(btn_bar, text="取消  Esc",
                  bg=C_BTN, fg=FG, relief="flat",
                  font=("Segoe UI", 9), padx=10, pady=4, cursor="hand2",
                  command=self._cancel).pack(side=tk.LEFT)

    def _drag_start(self, e):
        self._drag_x, self._drag_y = e.x, e.y

    def _drag_move(self, e):
        x = self.root.winfo_x() + (e.x - self._drag_x)
        y = self.root.winfo_y() + (e.y - self._drag_y)
        self.root.geometry(f"+{x}+{y}")

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
        self.status_var.set("辨識中…")
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
            self._countdown(float(self.cfg.get("preview_seconds", 2.0)))
        else:
            self.status_var.set("辨識完成  ·  按 Enter 貼上，Esc 取消")

    def _countdown(self, remaining: float):
        if remaining <= 0:
            self._confirm()
            return
        self.status_var.set(f"辨識完成  ·  {remaining:.1f}s 後自動貼上  ·  Esc 取消")
        self._timer_id = self.root.after(
            100, lambda: self._countdown(round(remaining - 0.1, 1)))

    def hide(self):
        self._cancel_timer()
        self.preview_frame.pack_forget()
        self.root.withdraw()

    def _confirm(self):
        self._cancel_timer()
        if self.on_confirm:
            self.on_confirm(self._text)

    def _cancel(self):
        self._cancel_timer()
        if self.on_cancel:
            self.on_cancel()


# ─── 設定視窗 ─────────────────────────────────────────────────────────────────

class SettingsWindow:
    def __init__(self, parent: tk.Tk, cfg: dict, lexicon: LexiconManager,
                 groq_client: Groq, on_save: callable):
        self.parent      = parent
        self.cfg         = cfg
        self.lexicon     = lexicon
        self.groq_client = groq_client
        self.on_save     = on_save
        self._win        = None

    def show(self):
        if self._win and self._win.winfo_exists():
            self._win.lift()
            self._win.focus_force()
            return
        self._build()

    def _build(self):
        _apply_ttk_style()

        self._win = tk.Toplevel(self.parent)
        self._win.title("MyType 設定")
        self._win.configure(bg=BG)
        self._win.attributes("-topmost", True)
        self._win.resizable(False, False)

        nb = ttk.Notebook(self._win)
        nb.pack(fill=tk.BOTH, expand=True, padx=16, pady=(12, 0))

        t_api  = ttk.Frame(nb)
        t_proc = ttk.Frame(nb)
        t_lex  = ttk.Frame(nb)
        nb.add(t_api,  text="  API 設定  ")
        nb.add(t_proc, text="  文字後處理  ")
        nb.add(t_lex,  text="  個人詞庫  ")

        self._build_api_tab(t_api)
        self._build_proc_tab(t_proc)
        self._build_lexicon_tab(t_lex)

        foot = tk.Frame(self._win, bg=BG)
        foot.pack(fill=tk.X, padx=16, pady=12)
        tk.Button(foot, text="儲存並關閉",
                  bg=C_GREEN, fg="white", relief="flat",
                  font=("Segoe UI", 10), padx=20, pady=8, cursor="hand2",
                  command=self._save).pack(side=tk.RIGHT)

        self._win.update_idletasks()
        sw = self._win.winfo_screenwidth()
        sh = self._win.winfo_screenheight()
        self._win.geometry(f"500x530+{(sw - 500) // 2}+{(sh - 530) // 2}")

    # ── API 設定 ──────────────────────────────────────────────────────────────

    def _build_api_tab(self, p):
        def lbl(text, row, pady=(14, 3)):
            tk.Label(p, text=text, bg=BG, fg=FG_SUB, font=("Segoe UI", 9)).grid(
                row=row, column=0, columnspan=2, sticky="w", padx=20, pady=pady)

        lbl("Groq API Key", 0)
        self._api_key_var = tk.StringVar(value=self.cfg.get("groq_api_key", ""))
        key_entry = tk.Entry(p, textvariable=self._api_key_var, show="•",
                             bg=C_BTN, fg=FG, insertbackground=FG, relief="flat",
                             font=("Segoe UI", 10), width=44)
        key_entry.grid(row=1, column=0, columnspan=2, padx=20, sticky="ew")

        self._show_key = tk.BooleanVar(value=False)
        def toggle_show():
            key_entry.config(show="" if self._show_key.get() else "•")
        tk.Checkbutton(p, text="顯示 Key", variable=self._show_key,
                       bg=BG, fg=FG_SUB, selectcolor=C_BTN, activebackground=BG,
                       font=("Segoe UI", 9), command=toggle_show).grid(
            row=2, column=0, sticky="w", padx=20, pady=(4, 0))

        self._test_var = tk.StringVar(value="")
        tk.Button(p, text="測試連線", bg=C_BTN, fg=FG, relief="flat",
                  font=("Segoe UI", 9), padx=12, pady=4, cursor="hand2",
                  command=self._test_connection).grid(
            row=3, column=0, sticky="w", padx=20, pady=(12, 4))
        tk.Label(p, textvariable=self._test_var, bg=BG, fg=C_OK,
                 font=("Segoe UI", 9)).grid(row=3, column=1, sticky="w", padx=8)

        lbl("辨識模型", 4)
        self._model_var = tk.StringVar(value=self.cfg.get("model", "whisper-large-v3-turbo"))
        for i, m in enumerate(["whisper-large-v3-turbo", "whisper-large-v3"]):
            tk.Radiobutton(p, text=m, variable=self._model_var, value=m,
                           bg=BG, fg=FG, selectcolor=C_BTN, activebackground=BG,
                           font=("Segoe UI", 10)).grid(
                row=5 + i, column=0, columnspan=2, sticky="w", padx=32)

        lbl("快捷鍵（設定視窗固定為 Ctrl+Alt+S）", 7)
        self._hotkey_var = tk.StringVar(value=self.cfg.get("hotkey", "ctrl+alt+space"))
        tk.Entry(p, textvariable=self._hotkey_var, bg=C_BTN, fg=FG,
                 insertbackground=FG, relief="flat", font=("Segoe UI", 10),
                 width=26).grid(row=8, column=0, columnspan=2,
                                sticky="w", padx=20, pady=(0, 16))

    def _test_connection(self):
        key = self._api_key_var.get().strip()
        if not key:
            self._test_var.set("請先輸入 API Key")
            return
        self._test_var.set("測試中…")
        self._win.update()

        def run():
            try:
                Groq(api_key=key).chat.completions.create(
                    model="llama-3.1-8b-instant",
                    messages=[{"role": "user", "content": "hi"}],
                    max_tokens=1,
                )
                self._win.after(0, lambda: self._test_var.set("連線成功"))
            except Exception as e:
                msg = str(e)[:50]
                self._win.after(0, lambda: self._test_var.set(f"失敗：{msg}"))

        threading.Thread(target=run, daemon=True).start()

    # ── 文字後處理 ────────────────────────────────────────────────────────────

    def _build_proc_tab(self, p):
        self._proc_var = tk.BooleanVar(value=self.cfg.get("post_process", False))
        tk.Checkbutton(p, text="啟用文字後處理（Groq LLaMA）",
                       variable=self._proc_var,
                       bg=BG, fg=FG, selectcolor=C_BTN, activebackground=BG,
                       font=("Segoe UI", 10, "bold")).pack(
            anchor="w", padx=20, pady=(18, 4))

        tk.Label(p, text="處理項目：去除語氣詞・修正數字/日期格式・補全標點符號",
                 bg=BG, fg=FG_SUB, font=("Segoe UI", 9),
                 wraplength=440, justify=tk.LEFT).pack(
            anchor="w", padx=32, pady=(0, 18))

        tk.Label(p, text="後處理模型", bg=BG, fg=FG_SUB,
                 font=("Segoe UI", 9)).pack(anchor="w", padx=20, pady=(0, 6))

        self._proc_model_var = tk.StringVar(
            value=self.cfg.get("post_process_model", "llama-3.1-8b-instant"))
        for m, desc in [
            ("llama-3.1-8b-instant",    "快速（建議，額外延遲約 0.3s）"),
            ("llama-3.3-70b-versatile", "高品質（額外延遲約 1s）"),
        ]:
            tk.Radiobutton(p, text=f"{m}  —  {desc}",
                           variable=self._proc_model_var, value=m,
                           bg=BG, fg=FG, selectcolor=C_BTN, activebackground=BG,
                           font=("Segoe UI", 10)).pack(anchor="w", padx=32, pady=3)

        tk.Frame(p, bg="#585b70", height=1).pack(fill=tk.X, padx=20, pady=16)
        tk.Label(p, text="啟用後每次辨識會多一次 LLaMA API 呼叫。\n"
                         "關閉時僅依 Whisper 原始輸出 + Prompt 引導輸出繁體字。",
                 bg=BG, fg=FG_SUB, font=("Segoe UI", 9),
                 wraplength=440, justify=tk.LEFT).pack(anchor="w", padx=20)

    # ── 個人詞庫 ──────────────────────────────────────────────────────────────

    def _build_lexicon_tab(self, p):
        tk.Label(p, text="辨識後自動替換詞條（貼上前套用）",
                 bg=BG, fg=FG_SUB, font=("Segoe UI", 9)).pack(
            anchor="w", padx=20, pady=(12, 4))

        tree_frame = tk.Frame(p, bg=C_BTN, highlightthickness=1,
                              highlightbackground="#585b70")
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=(0, 10))

        self._tree = ttk.Treeview(tree_frame, columns=("原詞", "替換為"),
                                  show="headings", height=7)
        for col, w in [("原詞", 195), ("替換為", 195)]:
            self._tree.heading(col, text=col)
            self._tree.column(col, width=w, anchor="w")

        sb = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self._tree.yview)
        self._tree.configure(yscrollcommand=sb.set)
        self._tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)

        for src, tgt in self.lexicon.entries().items():
            self._tree.insert("", tk.END, values=(src, tgt))

        input_row = tk.Frame(p, bg=BG)
        input_row.pack(fill=tk.X, padx=20, pady=(0, 6))

        self._lex_src = tk.StringVar()
        self._lex_tgt = tk.StringVar()

        tk.Label(input_row, text="原詞", bg=BG, fg=FG_SUB,
                 font=("Segoe UI", 9)).pack(side=tk.LEFT)
        tk.Entry(input_row, textvariable=self._lex_src, bg=C_BTN, fg=FG,
                 insertbackground=FG, relief="flat", font=("Segoe UI", 10),
                 width=13).pack(side=tk.LEFT, padx=(4, 8))
        tk.Label(input_row, text="→", bg=BG, fg=FG_SUB,
                 font=("Segoe UI", 10)).pack(side=tk.LEFT)
        tk.Entry(input_row, textvariable=self._lex_tgt, bg=C_BTN, fg=FG,
                 insertbackground=FG, relief="flat", font=("Segoe UI", 10),
                 width=13).pack(side=tk.LEFT, padx=(4, 10))
        tk.Button(input_row, text="新增", bg=C_GREEN, fg="white", relief="flat",
                  font=("Segoe UI", 9), padx=10, pady=3, cursor="hand2",
                  command=self._add_entry).pack(side=tk.LEFT)

        tk.Button(p, text="刪除選取", bg=C_RED, fg="white", relief="flat",
                  font=("Segoe UI", 9), padx=10, pady=4, cursor="hand2",
                  command=self._delete_entry).pack(anchor="w", padx=20, pady=(0, 8))

    def _add_entry(self):
        src = self._lex_src.get().strip()
        tgt = self._lex_tgt.get().strip()
        if not src or not tgt:
            return
        for item in self._tree.get_children():
            if self._tree.item(item)["values"][0] == src:
                self._tree.delete(item)
                break
        self._tree.insert("", tk.END, values=(src, tgt))
        self._lex_src.set("")
        self._lex_tgt.set("")

    def _delete_entry(self):
        for item in self._tree.selection():
            self._tree.delete(item)

    # ── 儲存 ──────────────────────────────────────────────────────────────────

    def _save(self):
        self.cfg["groq_api_key"]       = self._api_key_var.get().strip()
        self.cfg["model"]              = self._model_var.get()
        self.cfg["hotkey"]             = self._hotkey_var.get().strip()
        self.cfg["post_process"]       = self._proc_var.get()
        self.cfg["post_process_model"] = self._proc_model_var.get()
        save_config(self.cfg)

        new_entries = {
            self._tree.item(i)["values"][0]: self._tree.item(i)["values"][1]
            for i in self._tree.get_children()
        }
        self.lexicon.set_all(new_entries)
        self.lexicon.save()

        if self.on_save:
            self.on_save()
        self._win.destroy()


# ─── 主應用程式 ───────────────────────────────────────────────────────────────

class MyTypeApp:
    def __init__(self):
        self.cfg = load_config()
        self._ensure_api_key()

        self._recording   = False
        self._busy        = False
        self._target_hwnd = None

        self.root = tk.Tk()
        self.root.title("MyType")
        self.ui = FloatingUI(self.root, self.cfg)
        self.ui.on_confirm = self._paste
        self.ui.on_cancel  = self._cancel
        self.root.protocol("WM_DELETE_WINDOW", self._quit)

        self._select_device()

        self.asr       = GroqASR(self.cfg["groq_api_key"], self.cfg["model"])
        self.lexicon   = LexiconManager()
        self.processor = TextProcessor(
            client  = self.asr.client,
            model   = self.cfg.get("post_process_model", "llama-3.1-8b-instant"),
            enabled = self.cfg.get("post_process", False),
        )
        self.recorder = AudioRecorder(
            sample_rate = self.cfg["sample_rate"],
            channels    = self.cfg["channels"],
            device      = self.cfg.get("device"),
        )
        self.settings_win = SettingsWindow(
            parent      = self.root,
            cfg         = self.cfg,
            lexicon     = self.lexicon,
            groq_client = self.asr.client,
            on_save     = self._on_settings_save,
        )

    # ── 初始設定 ──────────────────────────────────────────────────────────────

    def _ensure_api_key(self):
        if self.cfg.get("groq_api_key"):
            return
        temp = tk.Tk()
        temp.withdraw()
        key = simpledialog.askstring(
            "MyType 初始設定",
            "請輸入您的 Groq API Key：\n（可在 https://console.groq.com/keys 取得，免費）",
            parent=temp,
        )
        temp.destroy()
        if not key or not key.strip():
            print("[MyType] 未設定 API Key，程式結束")
            sys.exit(1)
        self.cfg["groq_api_key"] = key.strip()
        save_config(self.cfg)
        print("[MyType] API Key 已儲存至 config.json")

    # ── 裝置選擇 ──────────────────────────────────────────────────────────────

    def _select_device(self):
        input_devs = [
            (i, d["name"])
            for i, d in enumerate(sd.query_devices())
            if d["max_input_channels"] > 0
        ]

        win = tk.Toplevel(self.root)
        win.title("選擇錄音裝置")
        win.configure(bg=BG)
        win.attributes("-topmost", True)
        win.resizable(False, False)

        tk.Label(win, text="選擇錄音裝置", bg=BG, fg=FG,
                 font=("Segoe UI", 11, "bold")).pack(padx=24, pady=(16, 8))
        tk.Label(win, text="Enter 確認　Esc 使用系統預設", bg=BG, fg=FG_SUB,
                 font=("Segoe UI", 9)).pack(padx=24, pady=(0, 8))

        listbox = tk.Listbox(win, bg=C_BTN, fg=FG, selectbackground="#585b70",
                             font=("Segoe UI", 10), width=52,
                             height=min(len(input_devs), 10),
                             borderwidth=0, highlightthickness=1,
                             highlightcolor="#585b70", activestyle="none")
        listbox.pack(padx=24, pady=(0, 12))

        saved = self.cfg.get("device")
        default_lb = 0
        for lb_i, (dev_i, dev_name) in enumerate(input_devs):
            listbox.insert(tk.END, f"  {dev_name}")
            if dev_i == saved:
                default_lb = lb_i
        listbox.selection_set(default_lb)
        listbox.see(default_lb)

        selected = [saved]

        def confirm(_event=None):
            sel = listbox.curselection()
            if sel:
                selected[0] = input_devs[sel[0]][0]
            win.destroy()

        def use_default(_event=None):
            selected[0] = None
            win.destroy()

        btn_frame = tk.Frame(win, bg=BG)
        btn_frame.pack(pady=(0, 16))
        tk.Button(btn_frame, text="確定  ↵", bg=C_GREEN, fg="white", relief="flat",
                  font=("Segoe UI", 9), padx=16, pady=6, cursor="hand2",
                  command=confirm).pack(side=tk.LEFT, padx=(0, 8))
        tk.Button(btn_frame, text="系統預設", bg=C_BTN, fg=FG, relief="flat",
                  font=("Segoe UI", 9), padx=16, pady=6, cursor="hand2",
                  command=use_default).pack(side=tk.LEFT)

        win.bind("<Return>", confirm)
        win.bind("<Escape>", use_default)
        win.update_idletasks()
        w, h = win.winfo_reqwidth(), win.winfo_reqheight()
        sw, sh = win.winfo_screenwidth(), win.winfo_screenheight()
        win.geometry(f"+{(sw - w) // 2}+{(sh - h) // 2}")
        win.grab_set()
        win.wait_window()

        self.cfg["device"] = selected[0]
        save_config(self.cfg)
        label = "系統預設" if selected[0] is None else next(
            name for idx, name in input_devs if idx == selected[0])
        print(f"[MyType] 錄音裝置：{label}")

    # ── 快捷鍵 ────────────────────────────────────────────────────────────────

    def _register_hotkey(self):
        hk = self.cfg["hotkey"]
        keyboard.add_hotkey(hk, self._toggle, suppress=True)
        keyboard.add_hotkey("ctrl+alt+s", self._open_settings, suppress=False)
        print(f"[MyType] 就緒  快捷鍵：{hk}　設定：Ctrl+Alt+S")
        print("[MyType] Ctrl+C 或關閉視窗結束程式")

    def _toggle(self):
        if self._busy:
            return
        if not self._recording:
            self._start_recording()
        else:
            self._stop_recording()

    def _open_settings(self):
        self.root.after(0, self.settings_win.show)

    def _on_settings_save(self):
        keyboard.unhook_all()
        self._register_hotkey()
        self.asr            = GroqASR(self.cfg["groq_api_key"], self.cfg["model"])
        self.processor.client  = self.asr.client
        self.processor.model   = self.cfg.get("post_process_model", "llama-3.1-8b-instant")
        self.processor.enabled = self.cfg.get("post_process", False)
        print("[MyType] 設定已更新")

    # ── 錄音流程 ──────────────────────────────────────────────────────────────

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
        self._busy      = True
        dur = self.recorder.stop()

        if dur < 0.3:
            print(f"[MyType] 錄音太短（{dur:.2f}s），已忽略")
            self._busy = False
            self.root.after(0, self.ui.hide)
            return

        self.root.after(0, self.ui.show_processing)
        threading.Thread(target=self._transcribe_worker, daemon=True).start()

    # ── 辨識 Worker ───────────────────────────────────────────────────────────

    def _transcribe_worker(self):
        tmp  = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        path = tmp.name
        tmp.close()
        try:
            if not self.recorder.save_wav(path):
                raise RuntimeError("錄音資料為空")
            text = self.asr.transcribe(path)
            text = self.processor.process(text)
            text = self.lexicon.apply(text)
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

    # ── 貼上 ──────────────────────────────────────────────────────────────────

    def _paste(self, text: str):
        self.ui.hide()
        if not text:
            return
        self.root.after(80, lambda: self._do_paste(text))

    def _do_paste(self, text: str):
        if self._target_hwnd:
            try:
                import ctypes
                ctypes.windll.user32.keybd_event(0x12, 0, 0, 0)
                ctypes.windll.user32.SetForegroundWindow(self._target_hwnd)
                ctypes.windll.user32.keybd_event(0x12, 0, 0x0002, 0)
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

    # ── 結束 ──────────────────────────────────────────────────────────────────

    def _quit(self):
        keyboard.unhook_all()
        self.root.destroy()

    def run(self):
        self._register_hotkey()
        try:
            self.root.mainloop()
        except KeyboardInterrupt:
            self._quit()


# ─── 入口 ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app = MyTypeApp()
    app.run()
