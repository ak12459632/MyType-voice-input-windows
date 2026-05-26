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
    "settings_hotkey": "ctrl+alt+s",
    "model": "whisper-large-v3-turbo",
    "sample_rate": 16000,
    "channels": 1,
    "device": None,
    "auto_paste": True,
    "preview_seconds": 2.0,
    "window_opacity": 0.95,
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

TK_KEY_MAP = {
    "Return": "enter", "space": "space", "Tab": "tab",
    "BackSpace": "backspace", "Delete": "delete",
    "Insert": "insert", "Home": "home", "End": "end",
    "Prior": "page up", "Next": "page down",
    "Up": "up", "Down": "down", "Left": "left", "Right": "right",
    **{f"F{i}": f"f{i}" for i in range(1, 13)},
}


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
                prompt="繁體中文及英文，台灣用語，英文保持原文，勿翻譯",
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

TRANSPARENT = "#010101"   # transparentcolor key — never use as UI color

BG        = "#0f0e17"
BG2       = "#1a182a"
SURFACE   = "#211e36"
FG        = "#eae8f5"
FG_SUB    = "#918db5"
FG_DIM    = "#5a5780"
C_PURPLE  = "#7b68ee"
C_PURP_L  = "#9c94f5"
C_REC     = "#fc7ea3"
C_PROC    = "#fcb86e"
C_OK      = "#6ee7b7"
C_BTN     = "#211e36"
C_GREEN   = "#00c897"
C_RED     = "#e05c7a"
C_ACCENT  = "#7b68ee"
C_BORDER  = "#2d2a45"

W_FLOAT = 440
R_FLOAT = 14


def _draw_rrect(canvas: tk.Canvas, w: int, h: int, r: int, color: str):
    canvas.delete("bg")
    o = color
    canvas.create_arc(0,     0,     2*r, 2*r, start=90,  extent=90, fill=o, outline=o, tags="bg")
    canvas.create_arc(w-2*r, 0,     w,   2*r, start=0,   extent=90, fill=o, outline=o, tags="bg")
    canvas.create_arc(0,     h-2*r, 2*r, h,   start=180, extent=90, fill=o, outline=o, tags="bg")
    canvas.create_arc(w-2*r, h-2*r, w,   h,   start=270, extent=90, fill=o, outline=o, tags="bg")
    canvas.create_rectangle(r,   0,   w-r, h,   fill=o, outline=o, tags="bg")
    canvas.create_rectangle(0,   r,   w,   h-r, fill=o, outline=o, tags="bg")
    canvas.tag_lower("bg")


def _apply_ttk_style():
    s = ttk.Style()
    s.theme_use("default")
    s.configure("TNotebook",     background=BG2,    borderwidth=0)
    s.configure("TNotebook.Tab", background=BG2,    foreground=FG_DIM,
                font=("Segoe UI", 10), padding=[16, 8])
    s.map("TNotebook.Tab",
          background=[("selected", BG)],
          foreground=[("selected", FG)])
    s.configure("TFrame",        background=BG)
    s.configure("Treeview",      background=SURFACE, foreground=FG,
                fieldbackground=SURFACE, font=("Segoe UI", 10), rowheight=28)
    s.configure("Treeview.Heading", background=BG2, foreground=FG_SUB,
                font=("Segoe UI", 9, "bold"))
    s.map("Treeview",            background=[("selected", C_PURPLE)])
    s.configure("Vertical.TScrollbar", background=C_BTN, troughcolor=BG2,
                borderwidth=0, arrowsize=14)
    s.configure("TCombobox",
                selectbackground=BG2, selectforeground=FG,
                fieldbackground=BG2,  background=SURFACE,
                foreground=FG,        arrowcolor=FG_SUB)
    s.map("TCombobox",
          fieldbackground=[("readonly", BG2)],
          selectbackground=[("readonly", BG2)])


def _make_card(parent: tk.Widget, title: str = None,
               pady: tuple = (0, 10)) -> tk.Frame:
    outer = tk.Frame(parent, bg=BG)
    outer.pack(fill=tk.X, padx=20, pady=pady)
    if title:
        tk.Label(outer, text=title, bg=BG, fg=FG_DIM,
                 font=("Segoe UI", 8, "bold")).pack(anchor="w", pady=(0, 5))
    card = tk.Frame(outer, bg=SURFACE, padx=16, pady=14,
                    highlightthickness=1, highlightbackground=C_BORDER)
    card.pack(fill=tk.X)
    return card


# ─── 懸浮 UI（圓角） ──────────────────────────────────────────────────────────

class FloatingUI:
    def __init__(self, root: tk.Tk, config: dict):
        self.root = root
        self.cfg  = config
        self.on_confirm: callable = None
        self.on_cancel:  callable = None
        self._text     = ""
        self._timer_id = None
        self._drag_ox  = self._drag_oy = 0
        self._build()

    def _build(self):
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", self.cfg.get("window_opacity", 0.95))
        self.root.wm_attributes("-transparentcolor", TRANSPARENT)
        self.root.configure(bg=TRANSPARENT)
        self.root.withdraw()

        # Canvas 作為圓角背景渲染層
        self._cv = tk.Canvas(self.root, bg=TRANSPARENT,
                              highlightthickness=0, bd=0,
                              width=W_FLOAT, height=50)
        self._cv.pack()

        # 內容 Frame 嵌在 Canvas 內，x 起始 = R 避免覆蓋圓角區
        self._frame = tk.Frame(self._cv, bg=BG)
        self._cv.create_window(R_FLOAT, 0, anchor="nw",
                               window=self._frame,
                               width=W_FLOAT - 2 * R_FLOAT)

        self._frame.bind("<Configure>",
                         lambda _: self.root.after_idle(self._sync_size))

        # 拖曳綁定（canvas 區域）
        self._cv.bind("<ButtonPress-1>", self._drag_start)
        self._cv.bind("<B1-Motion>",     self._drag_move)
        self.root.bind("<Return>",       lambda _: self._confirm())
        self.root.bind("<Escape>",       lambda _: self._cancel())

        # ── 狀態列 ────────────────────────────────────────────────────────────
        bar = tk.Frame(self._frame, bg=BG)
        bar.pack(fill=tk.X, padx=12, pady=(14, 6))

        self.dot = tk.Canvas(bar, width=10, height=10,
                              bg=BG, highlightthickness=0)
        self.dot.pack(side=tk.LEFT, padx=(0, 8))

        self.status_var = tk.StringVar()
        slbl = tk.Label(bar, textvariable=self.status_var,
                        bg=BG, fg=FG_SUB, font=("Segoe UI", 9))
        slbl.pack(side=tk.LEFT)

        for w in (bar, self.dot, slbl):
            w.bind("<ButtonPress-1>", self._drag_start)
            w.bind("<B1-Motion>",     self._drag_move)

        # ── 預覽區 ────────────────────────────────────────────────────────────
        self.preview_frame = tk.Frame(self._frame, bg=BG)

        self.text_var = tk.StringVar()
        tk.Label(
            self.preview_frame, textvariable=self.text_var,
            bg=BG, fg=FG, font=("Segoe UI", 11),
            wraplength=W_FLOAT - 2 * R_FLOAT - 24,
            justify=tk.LEFT, anchor="w",
        ).pack(fill=tk.X, padx=12, pady=(0, 10))

        btn_bar = tk.Frame(self.preview_frame, bg=BG)
        btn_bar.pack(fill=tk.X, padx=12, pady=(0, 16))

        tk.Button(btn_bar, text="貼上  Enter",
                  bg=C_PURPLE, fg=FG, relief="flat",
                  font=("Segoe UI", 9), padx=14, pady=6, cursor="hand2", bd=0,
                  activebackground=C_PURP_L, activeforeground=FG,
                  command=self._confirm).pack(side=tk.LEFT, padx=(0, 8))
        tk.Button(btn_bar, text="取消  Esc",
                  bg=SURFACE, fg=FG_SUB, relief="flat",
                  font=("Segoe UI", 9), padx=14, pady=6, cursor="hand2", bd=0,
                  activebackground=BG2, activeforeground=FG,
                  command=self._cancel).pack(side=tk.LEFT)

    # ── 幾何同步 ──────────────────────────────────────────────────────────────

    def _sync_size(self):
        self._frame.update_idletasks()
        fh = max(self._frame.winfo_reqheight(), 1)
        total_h = fh + R_FLOAT
        _draw_rrect(self._cv, W_FLOAT, total_h, R_FLOAT, BG)
        self._cv.config(width=W_FLOAT, height=total_h)
        if self.root.winfo_viewable():
            x = self.root.winfo_x()
            y = self.root.winfo_y()
            self.root.geometry(f"{W_FLOAT}x{total_h}+{x}+{y}")

    def _place(self):
        self._frame.update_idletasks()
        fh = max(self._frame.winfo_reqheight(), 1)
        total_h = fh + R_FLOAT
        _draw_rrect(self._cv, W_FLOAT, total_h, R_FLOAT, BG)
        self._cv.config(width=W_FLOAT, height=total_h)
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        x  = sw - W_FLOAT - 20
        y  = sh - total_h - 60
        self.root.geometry(f"{W_FLOAT}x{total_h}+{x}+{y}")

    # ── 拖曳 ──────────────────────────────────────────────────────────────────

    def _drag_start(self, e):
        self._drag_ox = e.x_root - self.root.winfo_x()
        self._drag_oy = e.y_root - self.root.winfo_y()

    def _drag_move(self, e):
        self.root.geometry(f"+{e.x_root - self._drag_ox}+{e.y_root - self._drag_oy}")

    # ── 狀態切換 ──────────────────────────────────────────────────────────────

    def _set_dot(self, color: str):
        self.dot.delete("all")
        self.dot.create_oval(1, 1, 9, 9, fill=color, outline="")

    def _cancel_timer(self):
        if self._timer_id:
            self.root.after_cancel(self._timer_id)
            self._timer_id = None

    def show_recording(self):
        self._cancel_timer()
        self.preview_frame.pack_forget()
        self._set_dot(C_REC)
        self._place()
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
        self._place()

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

        # ── 標題列 ────────────────────────────────────────────────────────────
        title_bar = tk.Frame(self._win, bg=BG2, height=52)
        title_bar.pack(fill=tk.X)
        title_bar.pack_propagate(False)

        tk.Label(title_bar, text="MyType", bg=BG2, fg=C_PURPLE,
                 font=("Segoe UI", 14, "bold")).pack(side=tk.LEFT, padx=(20, 4), pady=12)
        tk.Label(title_bar, text="設定", bg=BG2, fg=FG,
                 font=("Segoe UI", 14)).pack(side=tk.LEFT, pady=12)

        # ── Notebook ──────────────────────────────────────────────────────────
        nb = ttk.Notebook(self._win)
        nb.pack(fill=tk.BOTH, expand=True)

        tab_names = ["   API & 模型   ", "   音訊 & 快捷鍵   ",
                     "   文字後處理   ", "   個人詞庫   "]
        contents = []
        for name in tab_names:
            tf = ttk.Frame(nb)
            nb.add(tf, text=name)
            inner = tk.Frame(tf, bg=BG)
            inner.pack(fill=tk.BOTH, expand=True)
            contents.append(inner)

        self._build_api_tab(contents[0])
        self._build_audio_tab(contents[1])
        self._build_proc_tab(contents[2])
        self._build_lexicon_tab(contents[3])

        # ── 底部列 ────────────────────────────────────────────────────────────
        foot = tk.Frame(self._win, bg=BG2, height=56)
        foot.pack(fill=tk.X, side=tk.BOTTOM)
        foot.pack_propagate(False)

        tk.Button(foot, text="取消", bg=BG2, fg=FG_SUB, relief="flat",
                  font=("Segoe UI", 10), padx=16, pady=6, cursor="hand2", bd=0,
                  activebackground=SURFACE, activeforeground=FG,
                  command=self._win.destroy).pack(side=tk.RIGHT, padx=(8, 20), pady=10)
        tk.Button(foot, text="儲存並套用", bg=C_PURPLE, fg=FG, relief="flat",
                  font=("Segoe UI", 10, "bold"), padx=20, pady=6, cursor="hand2", bd=0,
                  activebackground=C_PURP_L, activeforeground=FG,
                  command=self._save).pack(side=tk.RIGHT, pady=10)

        self._win.update_idletasks()
        sw = self._win.winfo_screenwidth()
        sh = self._win.winfo_screenheight()
        self._win.geometry(f"560x610+{(sw - 560) // 2}+{(sh - 610) // 2}")

    # ── Tab 1: API & 模型 ─────────────────────────────────────────────────────

    def _build_api_tab(self, p):
        tk.Frame(p, bg=BG, height=10).pack()

        card1 = _make_card(p, "GROQ API KEY")

        self._api_key_var = tk.StringVar(value=self.cfg.get("groq_api_key", ""))
        key_entry = tk.Entry(card1, textvariable=self._api_key_var, show="•",
                             bg=BG2, fg=FG, insertbackground=FG, relief="flat",
                             font=("Consolas", 10), width=44)
        key_entry.pack(fill=tk.X, pady=(0, 10), ipady=5)

        row = tk.Frame(card1, bg=SURFACE)
        row.pack(fill=tk.X)

        self._show_key = tk.BooleanVar(value=False)
        def toggle_show():
            key_entry.config(show="" if self._show_key.get() else "•")
        tk.Checkbutton(row, text="顯示 Key", variable=self._show_key,
                       bg=SURFACE, fg=FG_SUB, selectcolor=BG2,
                       activebackground=SURFACE, font=("Segoe UI", 9),
                       command=toggle_show).pack(side=tk.LEFT)

        self._test_var = tk.StringVar(value="")
        tk.Label(row, textvariable=self._test_var, bg=SURFACE, fg=C_OK,
                 font=("Segoe UI", 9)).pack(side=tk.RIGHT, padx=(0, 8))
        tk.Button(row, text="測試連線", bg=BG2, fg=FG, relief="flat",
                  font=("Segoe UI", 9), padx=12, pady=3, cursor="hand2", bd=0,
                  activebackground=C_BTN, command=self._test_connection).pack(side=tk.RIGHT)

        card2 = _make_card(p, "WHISPER 辨識模型")

        self._model_var = tk.StringVar(value=self.cfg.get("model", "whisper-large-v3-turbo"))
        for val, desc in [
            ("whisper-large-v3-turbo", "預設，速度快"),
            ("whisper-large-v3",       "精度更高，速度較慢"),
        ]:
            row2 = tk.Frame(card2, bg=SURFACE)
            row2.pack(fill=tk.X, pady=2)
            tk.Radiobutton(row2, variable=self._model_var, value=val,
                           bg=SURFACE, fg=FG, selectcolor=BG2,
                           activebackground=SURFACE).pack(side=tk.LEFT)
            tk.Label(row2, text=val, bg=SURFACE, fg=FG,
                     font=("Consolas", 10)).pack(side=tk.LEFT)
            tk.Label(row2, text=f"  ({desc})", bg=SURFACE, fg=FG_DIM,
                     font=("Segoe UI", 9)).pack(side=tk.LEFT)

        tk.Frame(p, bg=BG, height=6).pack()
        tk.Label(p, text="語言：自動偵測，支援繁體中文及英文混合輸入",
                 bg=BG, fg=FG_DIM, font=("Segoe UI", 8)).pack(anchor="w", padx=22)

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
                msg = str(e)[:48]
                self._win.after(0, lambda: self._test_var.set(f"失敗：{msg}"))

        threading.Thread(target=run, daemon=True).start()

    # ── Tab 2: 音訊 & 快捷鍵 ─────────────────────────────────────────────────

    def _build_audio_tab(self, p):
        tk.Frame(p, bg=BG, height=10).pack()

        card1 = _make_card(p, "錄音裝置")

        try:
            all_devs = sd.query_devices()
        except Exception:
            all_devs = []

        self._input_devices = [(None, "系統預設")]
        for i, d in enumerate(all_devs):
            if d["max_input_channels"] > 0:
                self._input_devices.append((i, d["name"]))

        dev_names = [name for _, name in self._input_devices]
        current   = self.cfg.get("device")
        default_i = next(
            (i for i, (dev_id, _) in enumerate(self._input_devices) if dev_id == current),
            0,
        )

        self._dev_combo = ttk.Combobox(card1, values=dev_names,
                                        state="readonly", font=("Segoe UI", 10), width=46)
        self._dev_combo.current(default_i)
        self._dev_combo.pack(fill=tk.X, pady=(0, 8))

        tk.Label(card1, text="儲存後立即生效，下次錄音即使用新裝置",
                 bg=SURFACE, fg=FG_DIM, font=("Segoe UI", 8)).pack(anchor="w")

        card2 = _make_card(p, "快捷鍵")

        self._hotkey_var      = tk.StringVar(value=self.cfg.get("hotkey", "ctrl+alt+space"))
        self._settings_hk_var = tk.StringVar(
            value=self.cfg.get("settings_hotkey", "ctrl+alt+s"))

        self._hotkey_row(card2, "錄音快捷鍵", self._hotkey_var)
        tk.Frame(card2, bg=C_BORDER, height=1).pack(fill=tk.X, pady=(6, 12))
        self._hotkey_row(card2, "設定視窗快捷鍵", self._settings_hk_var)

        tk.Frame(p, bg=BG, height=6).pack()
        tk.Label(p, text="格式範例：ctrl+alt+space  /  ctrl+shift+f1  /  alt+z",
                 bg=BG, fg=FG_DIM, font=("Segoe UI", 8)).pack(anchor="w", padx=22)

    def _hotkey_row(self, parent: tk.Frame, label: str, var: tk.StringVar):
        container = tk.Frame(parent, bg=SURFACE)
        container.pack(fill=tk.X, pady=(0, 4))

        tk.Label(container, text=label, bg=SURFACE, fg=FG_SUB,
                 font=("Segoe UI", 9)).pack(anchor="w", pady=(0, 5))

        ctrl = tk.Frame(container, bg=SURFACE)
        ctrl.pack(fill=tk.X)

        entry = tk.Entry(ctrl, textvariable=var, bg=BG2, fg=C_PURPLE,
                         insertbackground=C_PURPLE, relief="flat",
                         font=("Consolas", 10), width=26)
        entry.pack(side=tk.LEFT, ipady=5)

        btn = tk.Button(ctrl, text="錄製", bg=C_BTN, fg=FG, relief="flat",
                        font=("Segoe UI", 9), padx=10, pady=4, cursor="hand2", bd=0,
                        activebackground=BG2)
        btn.config(command=lambda v=var: self._capture_hotkey(v))
        btn.pack(side=tk.LEFT, padx=(8, 0))

    def _capture_hotkey(self, var: tk.StringVar):
        cap = tk.Toplevel(self._win)
        cap.title("")
        cap.configure(bg=BG)
        cap.attributes("-topmost", True)
        cap.overrideredirect(True)
        cap.resizable(False, False)

        border = tk.Frame(cap, bg=C_PURPLE, padx=1, pady=1)
        border.pack(fill=tk.BOTH, expand=True)
        inner = tk.Frame(border, bg=BG, padx=24, pady=20)
        inner.pack(fill=tk.BOTH, expand=True)

        tk.Label(inner, text="請按下快捷鍵組合", bg=BG, fg=FG,
                 font=("Segoe UI", 12, "bold")).pack(pady=(0, 8))

        hint_var = tk.StringVar(value="等待按鍵…")
        tk.Label(inner, textvariable=hint_var, bg=BG, fg=C_PURPLE,
                 font=("Consolas", 11)).pack(pady=(0, 10))

        tk.Label(inner, text="按 Esc 取消", bg=BG, fg=FG_DIM,
                 font=("Segoe UI", 8)).pack()

        w, h = 300, 130
        sw, sh = cap.winfo_screenwidth(), cap.winfo_screenheight()
        cap.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 2}")

        MOD_MAP = {
            "Control_L": "ctrl",  "Control_R": "ctrl",
            "Alt_L":     "alt",   "Alt_R":     "alt",
            "Shift_L":   "shift", "Shift_R":   "shift",
        }
        MODS = {"ctrl", "alt", "shift"}
        held = set()

        def on_press(event):
            sym = event.keysym
            if sym == "Escape":
                cap.destroy()
                return
            if sym in MOD_MAP:
                held.add(MOD_MAP[sym])
                mods_str = "+".join(sorted(m for m in held if m in MODS))
                hint_var.set(mods_str + "+" if mods_str else "等待按鍵…")
                return
            key  = TK_KEY_MAP.get(sym, sym.lower())
            mods = sorted(m for m in held if m in MODS)
            if mods:
                var.set("+".join(mods + [key]))
                cap.destroy()

        def on_release(event):
            sym = event.keysym
            if sym in MOD_MAP:
                held.discard(MOD_MAP[sym])

        cap.bind("<KeyPress>",   on_press)
        cap.bind("<KeyRelease>", on_release)
        cap.grab_set()
        cap.focus_force()

    # ── Tab 3: 文字後處理 ─────────────────────────────────────────────────────

    def _build_proc_tab(self, p):
        tk.Frame(p, bg=BG, height=10).pack()

        card1 = _make_card(p, "啟用設定")
        self._proc_var = tk.BooleanVar(value=self.cfg.get("post_process", False))
        tk.Checkbutton(card1, text="啟用文字後處理（Groq LLaMA）",
                       variable=self._proc_var,
                       bg=SURFACE, fg=FG, selectcolor=BG2, activebackground=SURFACE,
                       font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(0, 6))
        tk.Label(card1,
                 text="去除語氣詞  ·  修正數字/日期格式  ·  補全標點符號",
                 bg=SURFACE, fg=FG_SUB, font=("Segoe UI", 9)).pack(anchor="w")

        card2 = _make_card(p, "後處理模型")
        self._proc_model_var = tk.StringVar(
            value=self.cfg.get("post_process_model", "llama-3.1-8b-instant"))
        for val, desc in [
            ("llama-3.1-8b-instant",    "快速  +0.3s（建議）"),
            ("llama-3.3-70b-versatile", "高品質  +1s"),
        ]:
            row = tk.Frame(card2, bg=SURFACE)
            row.pack(fill=tk.X, pady=2)
            tk.Radiobutton(row, variable=self._proc_model_var, value=val,
                           bg=SURFACE, fg=FG, selectcolor=BG2,
                           activebackground=SURFACE).pack(side=tk.LEFT)
            tk.Label(row, text=val, bg=SURFACE, fg=FG,
                     font=("Consolas", 10)).pack(side=tk.LEFT)
            tk.Label(row, text=f"  —  {desc}", bg=SURFACE, fg=FG_DIM,
                     font=("Segoe UI", 9)).pack(side=tk.LEFT)

        tk.Frame(p, bg=BG, height=6).pack()
        tk.Label(p,
                 text="未啟用時仍透過 Whisper Prompt 引導輸出繁體字，效果已相當不錯",
                 bg=BG, fg=FG_DIM, font=("Segoe UI", 9),
                 wraplength=500, justify=tk.LEFT).pack(anchor="w", padx=22)

    # ── Tab 4: 個人詞庫 ───────────────────────────────────────────────────────

    def _build_lexicon_tab(self, p):
        tk.Frame(p, bg=BG, height=10).pack()

        tk.Label(p, text="替換詞條", bg=BG, fg=FG_DIM,
                 font=("Segoe UI", 8, "bold")).pack(anchor="w", padx=20, pady=(0, 5))

        outer = tk.Frame(p, bg=BG)
        outer.pack(fill=tk.BOTH, expand=True, padx=20, pady=(0, 10))

        card = tk.Frame(outer, bg=SURFACE, padx=16, pady=14,
                        highlightthickness=1, highlightbackground=C_BORDER)
        card.pack(fill=tk.BOTH, expand=True)

        tree_wrapper = tk.Frame(card, bg=SURFACE)
        tree_wrapper.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        self._tree = ttk.Treeview(tree_wrapper, columns=("原詞", "替換為"),
                                   show="headings", height=7)
        for col, w in [("原詞", 205), ("替換為", 205)]:
            self._tree.heading(col, text=col)
            self._tree.column(col, width=w, anchor="w")

        sb = ttk.Scrollbar(tree_wrapper, orient=tk.VERTICAL, command=self._tree.yview)
        self._tree.configure(yscrollcommand=sb.set)
        self._tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)

        for src, tgt in self.lexicon.entries().items():
            self._tree.insert("", tk.END, values=(src, tgt))

        tk.Frame(card, bg=C_BORDER, height=1).pack(fill=tk.X, pady=(0, 10))

        input_row = tk.Frame(card, bg=SURFACE)
        input_row.pack(fill=tk.X)

        self._lex_src = tk.StringVar()
        self._lex_tgt = tk.StringVar()

        tk.Label(input_row, text="原詞", bg=SURFACE, fg=FG_SUB,
                 font=("Segoe UI", 9)).pack(side=tk.LEFT)
        tk.Entry(input_row, textvariable=self._lex_src, bg=BG2, fg=FG,
                 insertbackground=FG, relief="flat", font=("Segoe UI", 10),
                 width=13).pack(side=tk.LEFT, padx=(6, 0), ipady=4)
        tk.Label(input_row, text="→", bg=SURFACE, fg=FG_DIM,
                 font=("Segoe UI", 12)).pack(side=tk.LEFT, padx=8)
        tk.Entry(input_row, textvariable=self._lex_tgt, bg=BG2, fg=FG,
                 insertbackground=FG, relief="flat", font=("Segoe UI", 10),
                 width=13).pack(side=tk.LEFT, ipady=4)

        btn_row = tk.Frame(card, bg=SURFACE)
        btn_row.pack(fill=tk.X, pady=(8, 0))
        tk.Button(btn_row, text="新增", bg=C_GREEN, fg=BG, relief="flat",
                  font=("Segoe UI", 9), padx=12, pady=4, cursor="hand2", bd=0,
                  command=self._add_entry).pack(side=tk.LEFT, padx=(0, 8))
        tk.Button(btn_row, text="刪除選取", bg=BG2, fg=C_RED, relief="flat",
                  font=("Segoe UI", 9), padx=12, pady=4, cursor="hand2", bd=0,
                  command=self._delete_entry).pack(side=tk.LEFT)

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
        self.cfg["settings_hotkey"]    = self._settings_hk_var.get().strip()
        self.cfg["post_process"]       = self._proc_var.get()
        self.cfg["post_process_model"] = self._proc_model_var.get()

        dev_idx            = self._dev_combo.current()
        self.cfg["device"] = self._input_devices[dev_idx][0]

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

    def _ensure_api_key(self):
        if self.cfg.get("groq_api_key"):
            return
        temp = tk.Tk()
        temp.withdraw()
        key = simpledialog.askstring(
            "MyType 初始設定",
            "請輸入您的 Groq API Key：\n（可在 console.groq.com/keys 取得，免費）",
            parent=temp,
        )
        temp.destroy()
        if not key or not key.strip():
            print("[MyType] 未設定 API Key，程式結束")
            sys.exit(1)
        self.cfg["groq_api_key"] = key.strip()
        save_config(self.cfg)
        print("[MyType] API Key 已儲存至 config.json")

    def _register_hotkey(self):
        hk  = self.cfg["hotkey"]
        shk = self.cfg.get("settings_hotkey", "ctrl+alt+s")
        keyboard.add_hotkey(hk,  self._toggle,        suppress=True)
        keyboard.add_hotkey(shk, self._open_settings, suppress=False)
        print(f"[MyType] 就緒  快捷鍵：{hk}　設定：{shk}")
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
        self.asr               = GroqASR(self.cfg["groq_api_key"], self.cfg["model"])
        self.processor.client  = self.asr.client
        self.processor.model   = self.cfg.get("post_process_model", "llama-3.1-8b-instant")
        self.processor.enabled = self.cfg.get("post_process", False)
        self.recorder.device   = self.cfg.get("device")
        print("[MyType] 設定已更新")

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
