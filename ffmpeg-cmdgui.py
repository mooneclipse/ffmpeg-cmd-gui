#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""FFmpeg コマンドGUI v2.0

GUIで入力したオプションから ffmpeg コマンドを組み立てて実行する。
標準ライブラリのみ（tkinter/ttk 含む）。単一ファイル。

構成:
  - ロジック（GUI非依存）: build_command / command_to_display / 設定の読み書き /
    進捗行のパース / FFmpegWorker
  - GUI: FFmpegConverterGUI（Tk の生成は main() の中だけ）

将来拡張: ファイル欄へのドラッグ＆ドロップは標準ライブラリだけでは実現できないため未実装
（tkinterdnd2 等の外部依存が必要になる）。
"""
from __future__ import annotations

import json
import os
import queue
import re
import shlex
import shutil
import subprocess
import sys
import threading
import time

try:  # tkinter が無い環境でもロジック部分は import できるようにする
    import tkinter as tk
    from tkinter import filedialog, messagebox
    from tkinter import font as tkfont
    from tkinter import ttk
except ImportError:  # pragma: no cover
    tk = filedialog = messagebox = tkfont = ttk = None

VERSION = "2.0.0"
APP_NAME = "FFmpeg コマンドGUI"

# ---------------------------------------------------------------------------
# デザイントークン（DESIGN.md §3）
# ---------------------------------------------------------------------------
BG = "#EEF1F4"
SURFACE = "#FFFFFF"
SURFACE_ALT = "#F5F7F9"
BORDER = "#CBD3DB"
BORDER_STRONG = "#9AA6B2"
TEXT = "#1B2530"
TEXT_SUB = "#5A6775"
TEXT_DISABLED = "#8C98A4"

ACCENT = "#0B6E7F"
ACCENT_HOVER = "#095A68"
ACCENT_PRESSED = "#074753"
ACCENT_SOFT = "#D9EDF0"
ACCENT_DISABLED = "#9FC4CB"
SUCCESS = "#1E7F4F"
WARN = "#9A5B00"
ERROR = "#C2362B"
ERROR_HOVER = "#A52B22"
ERROR_PRESSED = "#8A231B"
ERROR_DISABLED = "#E2A7A2"
TROUGH = "#DCE3EA"
HOVER_NEUTRAL = "#E4EAF0"

CMD_BG = "#14202B"
CMD_BORDER = "#0E1720"
CMD_TEXT = "#D6E3EC"
CMD_EXE = "#7FD6E4"
CMD_FLAG = "#F2C46D"
CMD_PATH = "#A8E0B0"
CMD_DIM = "#6F8294"
CMD_SELECT = "#2E4A5E"
CMD_ERROR = "#F29A92"  # DESIGN に無い追加色: 暗い面の上で読めるエラー文字色

# ウィンドウ寸法（96dpi 基準 px。DESIGN §6.1）
WIN_INIT = (780, 680)
WIN_MIN = (640, 600)
LOG_EXTRA_HEIGHT = 150
LOG_MAX_LINES = 2000

EMPTY_COMMAND_HINT = "入力ファイルと出力ファイルを選ぶと、ここにコマンドが表示されます"


# ---------------------------------------------------------------------------
# コマンド組み立て（GUI非依存）
# ---------------------------------------------------------------------------
_NEGATIVE_NUMBER = re.compile(r"-\d")


def _assemble(ffmpeg_path, input_option, input_file, output_option, output_file):
    """(引数, 役割) のリストを返す。役割: exe / flag / text / path。

    オプション欄の分割に失敗した場合は shlex.split の ValueError をそのまま上げる。
    """
    parts = [(ffmpeg_path if (ffmpeg_path or "").strip() else "ffmpeg", "exe"), ("-y", "flag")]

    def add_options(option_text):
        for token in shlex.split(option_text or "", posix=True):
            is_flag = token.startswith("-") and len(token) > 1 and not _NEGATIVE_NUMBER.match(token)
            parts.append((token, "flag" if is_flag else "text"))

    add_options(input_option)
    if input_file:
        parts.append(("-i", "flag"))
        parts.append((input_file, "path"))
    add_options(output_option)
    if output_file:
        parts.append((output_file, "path"))
    return parts


def build_command(ffmpeg_path, input_option, input_file, output_option, output_file):
    """ffmpeg 実行用の引数リストを組み立てる（純関数）。

    並び: [ffmpeg, "-y", <入力オプション...>, "-i", 入力, <出力オプション...>, 出力]
    ffmpeg_path が空なら "ffmpeg"。オプション文字列は shlex.split(posix=True) で分割する。
    引用符の不整合は ValueError。パスはそのまま要素として渡す（引用符を付けない）。
    """
    return [arg for arg, _role in _assemble(ffmpeg_path, input_option, input_file, output_option, output_file)]


def command_to_display(cmd):
    """表示用の1行文字列にする。実行には使わない（実行は常にリストで行う）。"""
    if os.name == "nt":
        return subprocess.list2cmdline(cmd)
    return shlex.join(cmd)


def clean_path(text):
    """入力欄のパスを整える（前後の空白と、エクスプローラの「パスのコピー」が付ける二重引用符を除く）。"""
    text = (text or "").strip()
    if len(text) >= 2 and text[0] == '"' and text[-1] == '"':
        text = text[1:-1].strip()
    return text


# ---------------------------------------------------------------------------
# 進捗行のパース（GUI非依存）
# ---------------------------------------------------------------------------
_DURATION_RE = re.compile(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)")
_TIME_RE = re.compile(r"time=\s*(\d+):(\d+):(\d+(?:\.\d+)?)")
_PROGRESS_RE = re.compile(r"^\s*(?:frame|size)=")
_ERROR_RE = re.compile(
    r"error|invalid|no such file|unable to|failed|could not|not found|permission denied|"
    r"unrecognized|unknown encoder|unknown decoder|does not exist|conversion failed",
    re.IGNORECASE,
)


def _hms_to_seconds(h, m, s):
    return int(h) * 3600 + int(m) * 60 + float(s)


def parse_duration(line):
    """`Duration: 00:00:03.00` 行から総秒数。無ければ None（`N/A` も None）。"""
    m = _DURATION_RE.search(line)
    return _hms_to_seconds(*m.groups()) if m else None


def parse_progress_time(line):
    """進捗行 `frame= ... time=00:00:01.23 ...` から経過秒数。進捗行でなければ None。"""
    if not _PROGRESS_RE.match(line):
        return None
    m = _TIME_RE.search(line)
    return _hms_to_seconds(*m.groups()) if m else None


def is_progress_line(line):
    return bool(_PROGRESS_RE.match(line))


def format_hms(seconds):
    seconds = max(0, int(seconds))
    return "%02d:%02d:%02d" % (seconds // 3600, seconds % 3600 // 60, seconds % 60)


def format_elapsed(seconds):
    seconds = max(0, int(seconds))
    if seconds >= 3600:
        return "%d:%02d:%02d" % (seconds // 3600, seconds % 3600 // 60, seconds % 60)
    return "%d:%02d" % (seconds // 60, seconds % 60)


# ---------------------------------------------------------------------------
# 設定・プリセット（GUI非依存）
# ---------------------------------------------------------------------------
SETTING_KEYS = ("ffmpeg_path", "input_option", "input_file_path", "output_option", "output_file_path")


def normalize_settings(data):
    """辞書から既知キーだけを取り出す。未知キーは無視、欠けたキー・None は空文字。"""
    if not isinstance(data, dict):
        raise ValueError("設定ファイルの形式が正しくありません")
    result = {}
    for key in SETTING_KEYS:
        value = data.get(key)
        result[key] = "" if value is None else str(value)
    return result


def read_settings_file(path):
    with open(path, "r", encoding="utf-8-sig") as f:
        return normalize_settings(json.load(f))


def write_settings_file(path, settings):
    data = {key: settings.get(key, "") for key in SETTING_KEYS}
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def settings_dir():
    if os.name == "nt":
        base = os.environ.get("APPDATA") or os.path.join(os.path.expanduser("~"), "AppData", "Roaming")
    else:
        base = os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(base, "ffmpeg-cmd-gui")


def latest_settings_path():
    return os.path.join(settings_dir(), "latest_cnv.json")


# ---------------------------------------------------------------------------
# 実行ワーカー（GUI非依存。結果は queue 経由で渡す）
# ---------------------------------------------------------------------------
class FFmpegWorker(threading.Thread):
    """ffmpeg をリスト引数で直接起動し、出力を1行ずつ queue に流す。

    メッセージ: ("line", str) / ("done", returncode) / ("not_found", str) / ("error", str)
    """

    def __init__(self, cmd, out_queue):
        super().__init__(daemon=True)
        self.cmd = list(cmd)
        self.out = out_queue
        self._proc = None
        self._cancel = threading.Event()

    @property
    def cancelled(self):
        return self._cancel.is_set()

    def run(self):
        extra = {}
        if os.name == "nt":
            extra["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            proc = subprocess.Popen(
                self.cmd,
                stdin=subprocess.DEVNULL,  # ffmpeg に端末入力を読ませない
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                **extra,
            )
        except FileNotFoundError as e:
            self.out.put(("not_found", str(e)))
            return
        except OSError as e:
            self.out.put(("error", str(e)))
            return
        self._proc = proc
        if self._cancel.is_set():  # 起動直後に停止が押された場合
            self._signal("terminate")
        try:
            # text モードは \r も改行として扱うので、ffmpeg の進捗行（\r 区切り）も1行ずつ届く
            for line in proc.stdout:
                line = line.rstrip("\r\n")
                if line:
                    self.out.put(("line", line))
        except Exception as e:  # 読み取り中の予期せぬ失敗でもスレッドを正常終了させる
            self.out.put(("line", "[出力の読み取りに失敗しました: %s]" % e))
        returncode = proc.wait()
        self.out.put(("done", returncode))

    def _signal(self, how):
        proc = self._proc
        if proc is not None and proc.poll() is None:
            try:
                getattr(proc, how)()
            except OSError:
                pass

    def terminate(self):
        self._cancel.set()
        self._signal("terminate")

    def kill(self):
        self._cancel.set()
        self._signal("kill")

    def is_process_running(self):
        return self._proc is not None and self._proc.poll() is None


# ---------------------------------------------------------------------------
# 状態定義（DESIGN §8 の7状態）
# ---------------------------------------------------------------------------
IDLE_STATES = ("idle_empty", "idle_ready")
FINAL_STATES = ("success", "failed", "cancelled")
BUSY_STATES = ("running", "stopping")

STATE_SPECS = {
    "idle_empty": dict(button="convert", button_enabled=False, inputs=True, bar="reset", color=TEXT_SUB,
                       text="入力ファイルと出力ファイルを選んでください"),
    "idle_ready": dict(button="convert", button_enabled=True, inputs=True, bar="reset", color=TEXT,
                       text="準備できました"),
    "running": dict(button="stop", button_enabled=True, inputs=False, bar="run", color=TEXT,
                    text="変換中…", button_text="停止"),
    "stopping": dict(button="stop", button_enabled=False, inputs=False, bar="freeze", color=WARN,
                     text="停止しています…", button_text="停止中…"),
    "success": dict(button="convert", button_enabled=True, inputs=True, bar="ok", color=SUCCESS,
                    text="✓ 完了しました（所要 {elapsed}）"),
    "failed": dict(button="convert", button_enabled=True, inputs=True, bar="err", color=ERROR,
                   text="✕ 失敗しました（終了コード {code}）。ログを確認してください"),
    "cancelled": dict(button="convert", button_enabled=True, inputs=True, bar="warn", color=WARN,
                      text="停止しました。出力ファイルは途中までの可能性があります"),
}

BAR_STYLES = {
    "reset": "Conv.Horizontal.TProgressbar",
    "run": "Conv.Horizontal.TProgressbar",
    "ok": "Ok.Conv.Horizontal.TProgressbar",
    "err": "Err.Conv.Horizontal.TProgressbar",
    "warn": "Warn.Conv.Horizontal.TProgressbar",
}


# ---------------------------------------------------------------------------
# GUI 部品
# ---------------------------------------------------------------------------
def pick_font_family(root, candidates, fallback_named_font):
    """candidates のうち最初に存在するファミリー名を返す。無ければ名前付きフォントの実ファミリー。"""
    available = {name.lower(): name for name in tkfont.families(root)}
    for name in candidates:
        if name.lower() in available:
            return available[name.lower()]
    return tkfont.nametofont(fallback_named_font, root=root).actual("family")


def setup_fonts(root):
    ui = pick_font_family(root, ("Yu Gothic UI", "Segoe UI", "Noto Sans CJK JP"), "TkDefaultFont")
    mono = pick_font_family(root, ("Consolas", "DejaVu Sans Mono", "Noto Sans Mono"), "TkFixedFont")
    spec = (
        ("F_TITLE", ui, 14, "bold"),
        ("F_HEAD", ui, 10, "bold"),
        ("F_BODY", ui, 10, "normal"),
        ("F_SMALL", ui, 9, "normal"),
        ("F_STATUS", ui, 11, "bold"),
        ("F_ACTION", ui, 12, "bold"),
        ("F_MONO", mono, 10, "normal"),
        ("F_MONO_S", mono, 9, "normal"),
    )
    fonts = {}
    for name, family, size, weight in spec:
        fonts[name] = tkfont.Font(root=root, name=name, family=family, size=size, weight=weight)
    return fonts


def setup_style(root, px):
    """ttk スタイル（DESIGN §9）。px は DPI スケール済みの px 変換関数。"""
    st = ttk.Style(root)
    st.theme_use("clam")

    # Frame / Label
    st.configure("TFrame", background=BG)
    st.configure("Card.TFrame", background=SURFACE)
    st.configure("TLabel", background=BG, foreground=TEXT, font="F_BODY")
    st.configure("Card.TLabel", background=SURFACE, foreground=TEXT, font="F_BODY")
    st.configure("Title.TLabel", background=BG, foreground=TEXT, font="F_TITLE")
    st.configure("Head.TLabel", background=BG, foreground=TEXT, font="F_HEAD")
    st.configure("CardHead.TLabel", background=SURFACE, foreground=TEXT, font="F_HEAD")
    st.configure("Hint.TLabel", background=BG, foreground=TEXT_SUB, font="F_SMALL")
    st.configure("CardHint.TLabel", background=SURFACE, foreground=TEXT_SUB, font="F_SMALL")
    st.configure("CardHint.Warn.TLabel", foreground=WARN)
    st.configure("CardHint.Error.TLabel", foreground=ERROR)
    st.configure("Status.TLabel", background=BG, foreground=TEXT_SUB, font="F_STATUS")

    # Button: 副 / 小
    neutral = [("disabled", SURFACE_ALT), ("pressed", TROUGH), ("active", HOVER_NEUTRAL)]
    st.configure("TButton", background=SURFACE, foreground=TEXT, font="F_BODY",
                 padding=(px(12), px(4)), borderwidth=1, relief="flat",
                 bordercolor=BORDER_STRONG, lightcolor=SURFACE, darkcolor=SURFACE,
                 focuscolor=ACCENT_SOFT, anchor="center")
    st.map("TButton", background=neutral, foreground=[("disabled", TEXT_DISABLED)],
           bordercolor=[("disabled", BORDER), ("focus", ACCENT)],
           lightcolor=neutral, darkcolor=neutral)
    st.configure("Small.TButton", font="F_SMALL", padding=(px(10), px(3)))

    # Button: 主要 / 危険
    def solid(name, base, hover, pressed, disabled):
        st.configure(name, background=base, foreground="#FFFFFF", font="F_ACTION",
                     padding=(px(24), px(10)), borderwidth=0, relief="flat",
                     bordercolor=base, lightcolor=base, darkcolor=base, focuscolor=ACCENT_SOFT)
        states = [("disabled", disabled), ("pressed", pressed), ("active", hover)]
        st.map(name, background=states, foreground=[("disabled", "#FFFFFF")],
               bordercolor=states, lightcolor=states, darkcolor=states)

    solid("Accent.TButton", ACCENT, ACCENT_HOVER, ACCENT_PRESSED, ACCENT_DISABLED)
    solid("Danger.TButton", ERROR, ERROR_HOVER, ERROR_PRESSED, ERROR_DISABLED)

    # Button: リンク
    st.configure("Link.TButton", background=BG, foreground=ACCENT, font="F_BODY",
                 padding=(px(4), px(2)), borderwidth=0, relief="flat",
                 bordercolor=BG, lightcolor=BG, darkcolor=BG, focuscolor=ACCENT_SOFT)
    st.map("Link.TButton", foreground=[("disabled", TEXT_DISABLED), ("active", ACCENT_HOVER)],
           background=[("active", BG)])

    # Entry
    focus_ring = [("focus", ACCENT)]
    st.configure("TEntry", fieldbackground=SURFACE, foreground=TEXT, font="F_BODY",
                 padding=(px(8), px(6)), borderwidth=1,
                 bordercolor=BORDER, lightcolor=BORDER, darkcolor=BORDER,
                 insertcolor=TEXT, selectbackground=ACCENT_SOFT, selectforeground=TEXT)
    st.map("TEntry", fieldbackground=[("disabled", SURFACE_ALT), ("readonly", SURFACE_ALT)],
           foreground=[("disabled", TEXT_DISABLED)],
           bordercolor=focus_ring, lightcolor=focus_ring, darkcolor=focus_ring)
    st.configure("Mono.TEntry", font="F_MONO")

    # Progressbar
    st.configure("Conv.Horizontal.TProgressbar", troughcolor=TROUGH, background=ACCENT,
                 bordercolor=TROUGH, lightcolor=ACCENT, darkcolor=ACCENT, thickness=px(8))
    for prefix, color in (("Ok", SUCCESS), ("Err", ERROR), ("Warn", WARN)):
        st.configure("%s.Conv.Horizontal.TProgressbar" % prefix,
                     background=color, lightcolor=color, darkcolor=color)

    # Scrollbar（ログ欄）
    st.configure("Vertical.TScrollbar", background=BORDER_STRONG, troughcolor=SURFACE_ALT,
                 bordercolor=SURFACE_ALT, lightcolor=BORDER_STRONG, darkcolor=BORDER_STRONG,
                 arrowcolor=TEXT_SUB, gripcount=0, arrowsize=px(12), width=px(12))
    st.map("Vertical.TScrollbar", background=[("active", TEXT_SUB), ("pressed", TEXT_SUB)])
    return st


class FFmpegConverterGUI:
    def __init__(self, root, scale=1.0):
        self.root = root
        self.scale = scale
        self.state_name = None
        self._worker = None
        self._queue = None
        self._poll_id = None
        self._kill_id = None
        self._copy_reset_id = None
        self._duration = None   # 入力の総時間（秒）。Duration 行が取れたときのみ
        self._pct = 0.0
        self._t_start = 0.0
        self._bar_mode = "determinate"
        self._log_visible = False
        self._log_last_was_progress = False
        self._display_cmd = None  # 現在のプレビュー文字列（コピー用）。無効なら None

        root.title("%s v%s" % (APP_NAME, VERSION))
        root.configure(bg=BG)
        root.option_add("*Text.selectBackground", ACCENT_SOFT)
        root.option_add("*Text.selectForeground", TEXT)

        self.ffmpeg_path = tk.StringVar()
        self.input_option = tk.StringVar()
        self.input_file_path = tk.StringVar()
        self.output_option = tk.StringVar()
        self.output_file_path = tk.StringVar()
        self._vars = (self.ffmpeg_path, self.input_option, self.input_file_path,
                      self.output_option, self.output_file_path)
        self._lockable = []  # 実行中に無効化するウィジェット

        self.create_widgets()
        self._fit_window()

        for var in self._vars:
            var.trace_add("write", self._on_change)

        self.set_state("idle_empty")
        self.load_latest_settings()
        self._on_change()

        root.bind("<Control-Return>", lambda _e: self.convert())
        root.bind("<Escape>", lambda _e: self.stop())
        root.protocol("WM_DELETE_WINDOW", self.on_close)

    # ----- 寸法 -----
    def px(self, n):
        return round(n * self.scale)

    # ----- ウィジェット構築 -----
    def create_widgets(self):
        px = self.px
        root = self.root
        root.columnconfigure(0, weight=1)
        root.rowconfigure(5, weight=1)

        def place(widget, row, pady, sticky="nsew"):
            widget.grid(row=row, column=0, sticky=sticky, padx=px(16), pady=pady)

        # row0: ヘッダー
        header = ttk.Frame(root)
        place(header, 0, (px(16), px(12)), "ew")
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text=APP_NAME, style="Title.TLabel").grid(row=0, column=0, sticky="w")
        preset = ttk.Frame(header)
        preset.grid(row=0, column=1, sticky="e")
        ttk.Label(preset, text="プリセット", style="Hint.TLabel").pack(side="left", padx=(0, px(8)))
        self.load_btn = ttk.Button(preset, text="読み込み", command=self.load_preset)
        self.load_btn.pack(side="left", padx=(0, px(8)))
        self.save_btn = ttk.Button(preset, text="保存", command=self.save_preset)
        self.save_btn.pack(side="left")
        self._lockable += [self.load_btn, self.save_btn]

        # row1: ffmpeg 面
        card = self._make_card("ffmpeg")
        place(card, 1, (0, px(12)), "ew")
        card.columnconfigure(0, weight=1)
        self.ffmpeg_entry = ttk.Entry(card, textvariable=self.ffmpeg_path)
        self.ffmpeg_entry.grid(row=1, column=0, sticky="ew", padx=(px(12), 0))
        ffmpeg_btn = ttk.Button(card, text="選択", style="Small.TButton", command=self.browse_ffmpeg)
        ffmpeg_btn.grid(row=1, column=1, padx=(px(8), px(12)))
        self.ffmpeg_hint = ttk.Label(card, text=" ", style="CardHint.TLabel")
        self.ffmpeg_hint.grid(row=2, column=0, columnspan=2, sticky="w", padx=px(12), pady=(px(4), px(12)))
        self._lockable += [self.ffmpeg_entry, ffmpeg_btn]

        # row2/3: 変換前・変換後
        card, self.input_option_entry, self.input_file_entry, in_btn = self._make_io_card(
            "変換前", "例: -ss 00:00:10", self.input_option, self.input_file_path)
        place(card, 2, (0, px(12)), "ew")
        in_btn.configure(command=self.browse_input)
        card, self.output_option_entry, self.output_file_entry, out_btn = self._make_io_card(
            "変換後", "例: -c:v libx264 -crf 23", self.output_option, self.output_file_path)
        place(card, 3, (0, px(12)), "ew")
        out_btn.configure(command=self.browse_output)
        self._lockable += [self.input_option_entry, self.input_file_entry, in_btn,
                           self.output_option_entry, self.output_file_entry, out_btn]

        # row4: 「実行コマンド」見出し行
        head = ttk.Frame(root)
        place(head, 4, (0, px(8)), "ew")
        head.columnconfigure(1, weight=1)
        tk.Frame(head, width=3, bg=ACCENT).grid(row=0, column=0, sticky="ns")
        ttk.Label(head, text="実行コマンド", style="Head.TLabel").grid(row=0, column=1, sticky="w", padx=(px(8), 0))
        self.copy_btn = ttk.Button(head, text="コピー", style="Small.TButton", command=self.copy_command)
        self.copy_btn.grid(row=0, column=2, sticky="e")

        # row5: コマンドストリップ
        self.cmd_text = tk.Text(
            root, bg=CMD_BG, fg=CMD_TEXT, font="F_MONO", height=3, width=1, wrap="word",
            relief="flat", borderwidth=0, highlightthickness=1,
            highlightbackground=CMD_BORDER, highlightcolor=ACCENT,
            padx=px(12), pady=px(10), spacing2=3, insertbackground=CMD_TEXT,
            selectbackground=CMD_SELECT, selectforeground="#FFFFFF", cursor="arrow")
        place(self.cmd_text, 5, (0, px(12)))
        for tag, color in (("exe", CMD_EXE), ("flag", CMD_FLAG), ("path", CMD_PATH),
                           ("text", CMD_TEXT), ("empty", CMD_DIM), ("error", CMD_ERROR)):
            self.cmd_text.tag_configure(tag, foreground=color)
        self.cmd_text.bind("<Button-1>", lambda e: e.widget.focus_set())
        self.cmd_text.configure(state="disabled")

        # row6: 実行行
        run = ttk.Frame(root)
        place(run, 6, (0, px(12)), "ew")
        run.columnconfigure(0, weight=1)
        run.columnconfigure(1, minsize=px(150 + 16))
        info = ttk.Frame(run)
        info.grid(row=0, column=0, sticky="ew")
        info.columnconfigure(0, weight=1)
        self.status_label = ttk.Label(info, text="", style="Status.TLabel")
        self.status_label.grid(row=0, column=0, sticky="ew")
        self.progress = ttk.Progressbar(info, style=BAR_STYLES["reset"], mode="determinate", maximum=100)
        self.progress.grid(row=1, column=0, sticky="ew", pady=(px(8), 0))
        self.convert_btn = ttk.Button(run, text="変換", style="Accent.TButton", command=self.convert)
        self.stop_btn = ttk.Button(run, text="停止", style="Danger.TButton", command=self.stop)
        for btn in (self.convert_btn, self.stop_btn):
            btn.grid(row=0, column=1, sticky="nsew", padx=(px(16), 0))
        self.stop_btn.grid_remove()

        # row7: ログ開閉
        self.log_toggle = ttk.Button(root, text="▸ ログ", style="Link.TButton", command=self.toggle_log)
        self.log_toggle.grid(row=7, column=0, sticky="w", padx=px(16), pady=(0, px(16)))

        # row8: ログ欄（畳み時は grid_remove）
        self.log_frame = tk.Frame(root, bg=BG)
        self.log_frame.columnconfigure(0, weight=1)
        self.log_frame.rowconfigure(0, weight=1)
        self.log_text = tk.Text(
            self.log_frame, bg=SURFACE_ALT, fg=TEXT, font="F_MONO_S", height=8, width=1, wrap="char",
            relief="flat", highlightthickness=1, highlightbackground=BORDER, highlightcolor=BORDER,
            padx=px(8), pady=px(6), state="disabled")
        scroll = ttk.Scrollbar(self.log_frame, orient="vertical", command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scroll.set)
        self.log_text.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")
        self.log_text.tag_configure("err", foreground=ERROR)
        self.log_text.tag_configure("warn", foreground=WARN)
        self.log_text.tag_configure("dim", foreground=TEXT_SUB)
        self.log_text.bind("<Button-1>", lambda e: e.widget.focus_set())
        self.log_frame.grid(row=8, column=0, sticky="nsew", padx=px(16), pady=(0, px(16)))
        self.log_frame.grid_remove()

    def _make_heading(self, parent, text, example=None, bg=SURFACE):
        """左バー付き見出し。parent の row0 に置く。"""
        px = self.px
        frame = tk.Frame(parent, bg=bg)
        frame.columnconfigure(1, weight=1)
        tk.Frame(frame, width=3, bg=ACCENT).grid(row=0, column=0, sticky="ns")
        ttk.Label(frame, text=text, style="CardHead.TLabel").grid(row=0, column=1, sticky="w", padx=(px(8), 0))
        if example:
            ttk.Label(frame, text=example, style="CardHint.TLabel").grid(row=0, column=2, sticky="e")
        return frame

    def _make_card(self, title, example=None):
        """面（tk.Frame、1px枠）と見出しを作る。以降の行は row1 から。"""
        px = self.px
        card = tk.Frame(self.root, bg=SURFACE, highlightthickness=1,
                        highlightbackground=BORDER, highlightcolor=BORDER)
        self._make_heading(card, title, example).grid(
            row=0, column=0, columnspan=3, sticky="ew", padx=px(12), pady=(px(12), px(8)))
        return card

    def _make_io_card(self, title, example, option_var, file_var):
        px = self.px
        card = self._make_card(title, example)
        card.columnconfigure(1, weight=1)
        card.columnconfigure(0, minsize=px(72 + 12))
        ttk.Label(card, text="オプション", style="Card.TLabel").grid(
            row=1, column=0, sticky="w", padx=(px(12), 0), pady=(0, px(8)))
        option_entry = ttk.Entry(card, textvariable=option_var, style="Mono.TEntry", font="F_MONO")
        option_entry.grid(row=1, column=1, columnspan=2, sticky="ew", padx=(px(8), px(12)), pady=(0, px(8)))
        ttk.Label(card, text="ファイル", style="Card.TLabel").grid(
            row=2, column=0, sticky="w", padx=(px(12), 0), pady=(0, px(12)))
        file_entry = ttk.Entry(card, textvariable=file_var)
        file_entry.grid(row=2, column=1, sticky="ew", padx=(px(8), 0), pady=(0, px(12)))
        btn = ttk.Button(card, text="選択", style="Small.TButton")
        btn.grid(row=2, column=2, padx=(px(8), px(12)), pady=(0, px(12)))
        return card, option_entry, file_entry, btn

    def _fit_window(self):
        """初期サイズ・最小サイズを決めて画面中央に置く（DESIGN §6.1 / §11）。"""
        root = self.root
        px = self.px
        root.update_idletasks()
        min_w = max(px(WIN_MIN[0]), root.winfo_reqwidth())
        min_h = max(px(WIN_MIN[1]), root.winfo_reqheight())
        root.minsize(min_w, min_h)
        w = min(max(px(WIN_INIT[0]), min_w), root.winfo_screenwidth())
        h = min(max(px(WIN_INIT[1]), min_h), root.winfo_screenheight())
        x = max(0, (root.winfo_screenwidth() - w) // 2)
        y = max(0, (root.winfo_screenheight() - h) // 2)
        root.geometry("%dx%d+%d+%d" % (w, h, x, y))
        root.resizable(True, True)

    # ----- 値の取得 -----
    def _values(self):
        return {
            "ffmpeg_path": clean_path(self.ffmpeg_path.get()),
            "input_option": self.input_option.get(),
            "input_file": clean_path(self.input_file_path.get()),
            "output_option": self.output_option.get(),
            "output_file": clean_path(self.output_file_path.get()),
        }

    def _command_roles(self):
        v = self._values()
        return _assemble(v["ffmpeg_path"], v["input_option"], v["input_file"],
                         v["output_option"], v["output_file"])

    # ----- ファイル選択 -----
    def browse_ffmpeg(self):
        types = [("実行ファイル", "*.exe"), ("All Files", "*.*")] if os.name == "nt" else [("All Files", "*.*")]
        name = filedialog.askopenfilename(filetypes=types)
        if name:
            self.ffmpeg_path.set(name)

    def browse_input(self):
        name = filedialog.askopenfilename(filetypes=[("All Files", "*.*")])
        if name:
            self.input_file_path.set(name)

    def browse_output(self):
        # 上書き確認は変換実行時に自前で出すので、ダイアログ側の確認は切る
        name = filedialog.asksaveasfilename(filetypes=[("All Files", "*.*")], confirmoverwrite=False)
        if name:
            self.output_file_path.set(name)

    # ----- 入力変更時の更新 -----
    def _on_change(self, *_args):
        self._render_preview()
        self._update_ffmpeg_hint()
        if self.state_name in IDLE_STATES or self.state_name in FINAL_STATES:
            target = self._idle_state()
            if target != self.state_name:
                self.set_state(target)

    def _idle_state(self):
        v = self._values()
        return "idle_ready" if (v["input_file"] and v["output_file"]) else "idle_empty"

    def _update_ffmpeg_hint(self):
        value = self._values()["ffmpeg_path"]
        if not value:
            if shutil.which("ffmpeg"):
                text, style = "未設定です。PATH上の ffmpeg を使います", "CardHint.TLabel"
            else:
                text, style = ("PATH上に ffmpeg が見つかりません。ffmpeg.exe を選択してください",
                               "CardHint.Warn.TLabel")
        elif os.path.isfile(value):
            text, style = " ", "CardHint.TLabel"  # 高さを保つため空白1文字
        else:
            text, style = "ファイルが見つかりません", "CardHint.Error.TLabel"
        self.ffmpeg_hint.configure(text=text, style=style)

    def _render_preview(self):
        t = self.cmd_text
        t.configure(state="normal")
        t.delete("1.0", "end")
        self._display_cmd = None
        v = self._values()
        if not (v["input_file"] or v["output_file"] or v["input_option"].strip() or v["output_option"].strip()):
            t.insert("end", EMPTY_COMMAND_HINT, "empty")
        else:
            try:
                parts = self._command_roles()
            except ValueError:
                t.insert("end", "オプション欄を解釈できません（引用符が閉じていません）", "error")
            else:
                for i, (arg, role) in enumerate(parts):
                    if i:
                        t.insert("end", " ")
                    t.insert("end", command_to_display([arg]), role)
                self._display_cmd = command_to_display([a for a, _r in parts])
        t.configure(state="disabled")
        if self.state_name not in BUSY_STATES:
            self.copy_btn.state(["!disabled"] if self._display_cmd else ["disabled"])

    def copy_command(self):
        if not self._display_cmd:
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(self._display_cmd)
        self.copy_btn.configure(text="コピーしました")
        if self._copy_reset_id:
            self.root.after_cancel(self._copy_reset_id)
        self._copy_reset_id = self.root.after(1500, self._reset_copy_label)

    def _reset_copy_label(self):
        self._copy_reset_id = None
        self.copy_btn.configure(text="コピー")

    # ----- 状態管理（DESIGN §8。切替はここ1か所） -----
    def set_state(self, name, **fmt):
        spec = STATE_SPECS[name]
        previous = self.state_name
        self.state_name = name

        # 変換/停止ボタン（同じセルに重ねて切替）
        if spec["button"] == "stop":
            self.convert_btn.grid_remove()
            self.stop_btn.grid()
            self.stop_btn.configure(text=spec["button_text"])
            self.stop_btn.state(["!disabled"] if spec["button_enabled"] else ["disabled"])
        else:
            self.stop_btn.grid_remove()
            self.convert_btn.grid()
            self.convert_btn.state(["!disabled"] if spec["button_enabled"] else ["disabled"])

        # 入力系
        for w in self._lockable:
            w.state(["!disabled"] if spec["inputs"] else ["disabled"])
        if spec["inputs"] and self._display_cmd is None:
            self.copy_btn.state(["disabled"])
        elif spec["inputs"]:
            self.copy_btn.state(["!disabled"])
        # 実行中でもコピーは可（実行内容は固定。コピーは読み取りのみ）

        # 状態テキスト
        self.status_label.configure(text=spec["text"].format(**fmt), foreground=spec["color"])

        # 進捗バー
        bar = spec["bar"]
        if bar == "run":
            self._pct = 0.0
            self._duration = None
            self._bar_set(BAR_STYLES["run"], indeterminate=True)
        elif bar == "freeze":
            self._bar_set(None, value=self._pct)
        elif bar == "reset":
            self._pct = 0.0
            self._bar_set(BAR_STYLES["reset"], value=0)
        elif bar == "ok":
            self._pct = 100.0
            self._bar_set(BAR_STYLES["ok"], value=100)
        else:  # err / warn: 現在位置で止める
            self._bar_set(BAR_STYLES[bar], value=self._pct)
        return previous

    def _bar_set(self, style, indeterminate=False, value=0):
        pb = self.progress
        if style:
            pb.configure(style=style)
        pb.stop()
        if indeterminate:
            pb.configure(mode="indeterminate")
            pb.start(12)
            self._bar_mode = "indeterminate"
        else:
            pb.configure(mode="determinate", maximum=100)
            pb["value"] = value
            self._bar_mode = "determinate"

    # ----- ログ -----
    def toggle_log(self):
        self._set_log_visible(not self._log_visible)

    def _set_log_visible(self, visible):
        if visible == self._log_visible:
            return
        self._log_visible = visible
        root = self.root
        extra = self.px(LOG_EXTRA_HEIGHT)
        if visible:
            self.log_toggle.grid_configure(pady=(0, 0))
            self.log_frame.grid()
            root.rowconfigure(5, weight=1)
            root.rowconfigure(8, weight=2)
            self.log_toggle.configure(text="▾ ログ")
            root.update_idletasks()
            root.geometry("%dx%d" % (root.winfo_width(), root.winfo_height() + extra))
        else:
            self.log_frame.grid_remove()
            self.log_toggle.grid_configure(pady=(0, self.px(16)))
            root.rowconfigure(8, weight=0)
            self.log_toggle.configure(text="▸ ログ")
            root.update_idletasks()
            new_h = max(root.winfo_height() - extra, root.winfo_reqheight())
            root.geometry("%dx%d" % (root.winfo_width(), new_h))

    def _log_clear(self):
        t = self.log_text
        t.configure(state="normal")
        t.delete("1.0", "end")
        t.configure(state="disabled")
        self._log_last_was_progress = False

    def _log(self, text, tag=None, progress=False):
        t = self.log_text
        at_bottom = t.yview()[1] >= 0.999
        t.configure(state="normal")
        if self._log_last_was_progress:
            # 直前の進捗行を置換して流量を抑える
            t.delete("end-2l linestart", "end-1c")
        t.insert("end", text + "\n", (tag,) if tag else ())
        self._log_last_was_progress = progress
        real_lines = int(t.index("end-1c").split(".")[0]) - 1
        if real_lines > LOG_MAX_LINES:
            t.delete("1.0", "%d.0" % (real_lines - LOG_MAX_LINES + 1))
        t.configure(state="disabled")
        if at_bottom:
            t.see("end")

    @staticmethod
    def _classify(line):
        if _ERROR_RE.search(line):
            return "err"
        if "warning" in line.lower():
            return "warn"
        return None

    # ----- 変換の実行 -----
    def convert(self):
        if self.state_name in BUSY_STATES:
            return
        v = self._values()
        if not v["input_file"]:
            messagebox.showerror("エラー", "変換前のファイルが指定されていません。")
            return
        if not os.path.isfile(v["input_file"]):
            messagebox.showerror("エラー", "変換前のファイルが見つかりません。\n%s" % v["input_file"])
            return
        if not v["output_file"]:
            messagebox.showerror("エラー", "変換後のファイルが指定されていません。")
            return
        try:
            cmd = build_command(v["ffmpeg_path"], v["input_option"], v["input_file"],
                                v["output_option"], v["output_file"])
        except ValueError:
            messagebox.showerror("エラー", "オプション欄を解釈できません。引用符（\" または '）が閉じているか確認してください。")
            return
        if os.path.exists(v["output_file"]):
            name = os.path.basename(v["output_file"]) or v["output_file"]
            if not messagebox.askyesno("上書きの確認", "「%s」は既にあります。上書きしますか？" % name):
                return

        self.save_latest_settings()
        self._log_clear()
        self._log("$ " + command_to_display(cmd), "dim")
        self._queue = queue.Queue()
        self._worker = FFmpegWorker(cmd, self._queue)
        self._t_start = time.monotonic()
        self.set_state("running")
        self._worker.start()
        self._schedule_poll()

    def stop(self):
        """停止ボタン / Esc。実行中のみ有効。terminate し、効かなければ kill。"""
        if self.state_name != "running" or self._worker is None:
            return
        self.set_state("stopping")
        self._worker.terminate()
        self._kill_id = self.root.after(3000, self._force_kill)

    def _force_kill(self):
        self._kill_id = None
        if self._worker is not None and self._worker.is_process_running():
            self._log("[terminate が効かないため強制終了します]", "warn")
            self._worker.kill()

    def _schedule_poll(self):
        if self._poll_id is None:
            self._poll_id = self.root.after(50, self._poll)

    def _poll(self):
        self._poll_id = None
        try:
            for _ in range(300):
                self._handle(self._queue.get_nowait())
        except queue.Empty:
            pass
        if self._worker is not None or not self._queue.empty():
            self._schedule_poll()

    def _handle(self, msg):
        kind, payload = msg
        if kind == "line":
            self._on_line(payload)
        elif kind == "done":
            self._on_done(payload)
        elif kind in ("not_found", "error"):
            self._on_launch_failed(kind, payload)

    def _on_line(self, line):
        if self._duration is None and not is_progress_line(line):
            dur = parse_duration(line)
            if dur:
                self._duration = dur
        t = parse_progress_time(line)
        if t is not None:
            self._on_progress(t)
            self._log(line, "dim", progress=True)
        elif is_progress_line(line):
            self._log(line, "dim", progress=True)
        else:
            self._log(line, self._classify(line))

    def _on_progress(self, t):
        if self.state_name != "running":
            return
        if self._duration:
            self._pct = max(0.0, min(100.0, t / self._duration * 100))
            if self._bar_mode != "determinate":
                self._bar_set(None, value=self._pct)
            else:
                self.progress["value"] = self._pct
            text = "変換中… %d%%   %s / %s" % (int(self._pct), format_hms(t), format_hms(self._duration))
        else:
            text = "変換中… %s" % format_hms(t)
        self.status_label.configure(text=text)

    def _on_done(self, returncode):
        worker, self._worker = self._worker, None
        if self._kill_id:
            self.root.after_cancel(self._kill_id)
            self._kill_id = None
        self._log("[終了コード %s]" % returncode, "err" if returncode != 0 else None)
        if worker is not None and worker.cancelled:
            self.set_state("cancelled")
        elif returncode == 0:
            self.set_state("success", elapsed=format_elapsed(time.monotonic() - self._t_start))
        else:
            self.set_state("failed", code=returncode)
            self._set_log_visible(True)
            last = self.log_text.tag_prevrange("err", "end")
            if last:
                self.log_text.see(last[0])

    def _on_launch_failed(self, kind, detail):
        self._worker = None
        if kind == "not_found":
            message = ("ffmpeg が見つかりません。\n"
                       "「ffmpeg」欄で ffmpeg の実行ファイルを選択するか、PATH に ffmpeg を追加してください。")
        else:
            message = "ffmpeg を起動できませんでした。\n%s" % detail
        self._log("[起動に失敗しました] " + detail, "err")
        self.set_state(self._idle_state())
        messagebox.showerror("エラー", message)

    # ----- 設定・プリセット -----
    def _current_settings(self):
        return {
            "ffmpeg_path": self.ffmpeg_path.get(),
            "input_option": self.input_option.get(),
            "input_file_path": self.input_file_path.get(),
            "output_option": self.output_option.get(),
            "output_file_path": self.output_file_path.get(),
        }

    def _apply_settings(self, settings):
        self.ffmpeg_path.set(settings["ffmpeg_path"])
        self.input_option.set(settings["input_option"])
        self.input_file_path.set(settings["input_file_path"])
        self.output_option.set(settings["output_option"])
        self.output_file_path.set(settings["output_file_path"])

    def save_latest_settings(self):
        """前回設定の自動保存。失敗してもアプリは続行する。"""
        try:
            os.makedirs(settings_dir(), exist_ok=True)
            path = latest_settings_path()
            tmp = path + ".tmp"
            write_settings_file(tmp, self._current_settings())
            os.replace(tmp, path)
        except Exception:
            pass

    def load_latest_settings(self):
        try:
            self._apply_settings(read_settings_file(latest_settings_path()))
        except Exception:
            pass  # 無い・壊れている場合は空のまま起動

    def save_preset(self):
        name = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON files", "*.json")])
        if not name:
            return
        try:
            write_settings_file(name, self._current_settings())
        except OSError as e:
            messagebox.showerror("エラー", "プリセットを保存できませんでした。\n%s" % e)

    def load_preset(self):
        name = filedialog.askopenfilename(filetypes=[("JSON files", "*.json")])
        if not name:
            return
        try:
            settings = read_settings_file(name)
        except (OSError, ValueError) as e:  # JSONDecodeError / UnicodeDecodeError も ValueError
            messagebox.showerror("エラー", "プリセットを読み込めませんでした。\n%s" % e)
            return
        self._apply_settings(settings)

    # ----- 終了 -----
    def on_close(self):
        worker = self._worker
        if worker is not None:
            if not messagebox.askokcancel("終了の確認", "変換中です。停止して終了しますか？"):
                return
            worker.terminate()
            if worker.is_process_running():
                try:
                    worker._proc.wait(timeout=2)
                except Exception:
                    worker.kill()
        self.save_latest_settings()
        self.root.destroy()


def main():
    if os.name == "nt":
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
    if tk is None:
        sys.stderr.write("tkinter が見つかりません。Python に tkinter を含めてインストールしてください。\n")
        return 1
    root = tk.Tk()
    scale = root.winfo_fpixels("1i") / 96
    setup_fonts(root)
    setup_style(root, lambda n: round(n * scale))
    FFmpegConverterGUI(root, scale)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
