"""ffmpeg-cmd-gui: task-oriented Tkinter wrapper for ffmpeg.

Targets YouTube uploaders and MMD creators on Windows. Pick a task,
fill in only the relevant fields, run with in-app progress and log.
"""

import json
import os
import queue
import re
import shlex
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText

APP_NAME = "ffmpeg-cmd-gui"

VIDEO_FILETYPES = [
    ("動画ファイル", "*.mp4 *.mov *.mkv *.avi *.webm *.wmv *.flv *.m4v *.ts"),
    ("すべて", "*.*"),
]
AUDIO_FILETYPES = [
    ("音声ファイル", "*.mp3 *.wav *.m4a *.flac *.aac *.ogg"),
    ("すべて", "*.*"),
]
IMAGE_FILETYPES = [
    ("画像ファイル", "*.png *.jpg *.jpeg *.bmp *.tga *.tif *.tiff"),
    ("すべて", "*.*"),
]


def config_dir():
    base = os.environ.get("APPDATA") or os.path.expanduser("~/.config")
    p = Path(base) / APP_NAME
    p.mkdir(parents=True, exist_ok=True)
    return p


SETTINGS_FILE = config_dir() / "settings.json"


def load_settings():
    try:
        with open(SETTINGS_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_settings(data):
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except OSError:
        pass


# ---------------------------------------------------------------- runner ---


class CommandRunner:
    """Run an ffmpeg command in a background thread, streaming output."""

    TIME_RE = re.compile(r"time=(\d+):(\d+):(\d+(?:\.\d+)?)")

    def __init__(self, root, log, progress, status_var, on_done):
        self.root = root
        self.log = log
        self.progress = progress
        self.status_var = status_var
        self.on_done = on_done
        self.proc = None
        self.q = queue.Queue()
        self._polling = False

    def is_running(self):
        return self.proc is not None and self.proc.poll() is None

    def run(self, args):
        if self.is_running():
            messagebox.showwarning("実行中", "既に処理が実行中です。")
            return
        self._append_log("$ " + shlex.join(args) + "\n\n", clear=True)
        self.progress.config(mode="indeterminate")
        self.progress.start(10)
        self.status_var.set("実行中...")
        threading.Thread(target=self._worker, args=(args,), daemon=True).start()
        if not self._polling:
            self._polling = True
            self._poll()

    def stop(self):
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.terminate()
            except OSError:
                pass

    def _worker(self, args):
        creationflags = 0
        if sys.platform == "win32":
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            self.proc = subprocess.Popen(
                args,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                bufsize=1,
                encoding="utf-8",
                errors="replace",
                creationflags=creationflags,
            )
            assert self.proc.stdout is not None
            for line in self.proc.stdout:
                self.q.put(("log", line))
                m = self.TIME_RE.search(line)
                if m:
                    h, mi, s = m.groups()
                    secs = int(h) * 3600 + int(mi) * 60 + float(s)
                    self.q.put(("time", secs))
            self.proc.wait()
            self.q.put(("done", self.proc.returncode))
        except FileNotFoundError:
            self.q.put(("error", "ffmpeg実行ファイルが見つかりません。パスを確認してください。"))
            self.q.put(("done", -1))
        except Exception as e:
            self.q.put(("error", str(e)))
            self.q.put(("done", -1))

    def _append_log(self, text, clear=False):
        self.log.config(state="normal")
        if clear:
            self.log.delete("1.0", tk.END)
        self.log.insert(tk.END, text)
        self.log.see(tk.END)
        self.log.config(state="disabled")

    def _poll(self):
        try:
            while True:
                kind, payload = self.q.get_nowait()
                if kind == "log":
                    self._append_log(payload)
                elif kind == "time":
                    h = int(payload // 3600)
                    m = int((payload % 3600) // 60)
                    s = int(payload % 60)
                    self.status_var.set(f"実行中... 処理位置 {h:02d}:{m:02d}:{s:02d}")
                elif kind == "error":
                    messagebox.showerror("エラー", payload)
                elif kind == "done":
                    self.progress.stop()
                    rc = payload
                    if rc == 0:
                        self.status_var.set("完了")
                    elif rc == -1:
                        self.status_var.set("起動失敗")
                    else:
                        self.status_var.set(f"終了コード {rc}")
                    self.on_done(rc)
                    self._polling = False
                    return
        except queue.Empty:
            pass
        self.root.after(100, self._poll)


# ----------------------------------------------------------------- base ----


class TaskPanel(ttk.Frame):
    title = ""
    key = ""

    def __init__(self, master, on_change):
        super().__init__(master)
        self._on_change_cb = on_change
        self._building = True
        self.build()
        self._building = False

    def build(self):
        raise NotImplementedError

    def build_command(self, ffmpeg):
        raise NotImplementedError

    def get_state(self):
        return {}

    def set_state(self, state):
        pass

    def notify(self, *_args):
        if not self._building:
            self._on_change_cb()

    def _var(self, default=""):
        v = tk.StringVar(value=default)
        v.trace_add("write", self.notify)
        return v

    def _bool_var(self, default=False):
        v = tk.BooleanVar(value=default)
        v.trace_add("write", self.notify)
        return v

    def _file_row(self, parent, row, label, var, save=False,
                  filetypes=None, default_ext=None):
        ttk.Label(parent, text=label).grid(
            row=row, column=0, sticky="w", padx=4, pady=3)
        ttk.Entry(parent, textvariable=var).grid(
            row=row, column=1, sticky="we", padx=4, pady=3)

        def browse():
            kw = {"filetypes": filetypes or [("すべて", "*.*")]}
            if save:
                if default_ext:
                    kw["defaultextension"] = default_ext
                fn = filedialog.asksaveasfilename(**kw)
            else:
                fn = filedialog.askopenfilename(**kw)
            if fn:
                var.set(fn)

        ttk.Button(parent, text="選択", command=browse, width=6).grid(
            row=row, column=2, padx=4, pady=3)


# ---------------------------------------------------------------- panels ---


class YouTubeEncodePanel(TaskPanel):
    title = "YouTube用にエンコード (MP4)"
    key = "youtube_encode"

    def build(self):
        self.columnconfigure(1, weight=1)
        self.input_file = self._var()
        self.output_file = self._var()
        self._file_row(self, 0, "入力", self.input_file, filetypes=VIDEO_FILETYPES)
        self._file_row(self, 1, "出力", self.output_file, save=True,
                       filetypes=[("MP4", "*.mp4"), ("すべて", "*.*")],
                       default_ext=".mp4")

        opts = ttk.Frame(self)
        opts.grid(row=2, column=0, columnspan=3, sticky="we", padx=4, pady=6)
        self.resolution = self._var("元のまま")
        self.fps = self._var("元のまま")
        self.crf = self._var("標準 (CRF 23)")
        self.audio_br = self._var("192k")

        ttk.Label(opts, text="解像度").grid(row=0, column=0, sticky="w", padx=4, pady=2)
        ttk.Combobox(opts, textvariable=self.resolution, state="readonly", width=12,
                     values=["元のまま", "720p", "1080p", "1440p", "2160p"]).grid(
            row=0, column=1, padx=4, pady=2, sticky="w")
        ttk.Label(opts, text="FPS").grid(row=0, column=2, sticky="w", padx=4, pady=2)
        ttk.Combobox(opts, textvariable=self.fps, state="readonly", width=10,
                     values=["元のまま", "24", "30", "60"]).grid(
            row=0, column=3, padx=4, pady=2, sticky="w")
        ttk.Label(opts, text="画質").grid(row=1, column=0, sticky="w", padx=4, pady=2)
        ttk.Combobox(opts, textvariable=self.crf, state="readonly", width=18,
                     values=["高画質 (CRF 18)", "標準 (CRF 23)", "軽量 (CRF 28)"]).grid(
            row=1, column=1, padx=4, pady=2, sticky="w")
        ttk.Label(opts, text="音声").grid(row=1, column=2, sticky="w", padx=4, pady=2)
        ttk.Combobox(opts, textvariable=self.audio_br, state="readonly", width=10,
                     values=["128k", "192k", "256k", "320k"]).grid(
            row=1, column=3, padx=4, pady=2, sticky="w")

        self.input_file.trace_add("write", self._auto_output)

    def _auto_output(self, *_):
        if self.input_file.get() and not self.output_file.get():
            p = Path(self.input_file.get())
            self.output_file.set(str(p.with_name(p.stem + "_yt.mp4")))

    def build_command(self, ffmpeg):
        if not self.input_file.get() or not self.output_file.get():
            return None
        args = [ffmpeg, "-y", "-i", self.input_file.get()]
        if self.resolution.get() != "元のまま":
            h = {"720p": 720, "1080p": 1080,
                 "1440p": 1440, "2160p": 2160}[self.resolution.get()]
            args += ["-vf", f"scale=-2:{h}"]
        if self.fps.get() != "元のまま":
            args += ["-r", self.fps.get()]
        crf = {"高画質 (CRF 18)": "18",
               "標準 (CRF 23)": "23",
               "軽量 (CRF 28)": "28"}[self.crf.get()]
        args += ["-c:v", "libx264", "-preset", "slow",
                 "-crf", crf, "-pix_fmt", "yuv420p"]
        args += ["-c:a", "aac", "-b:a", self.audio_br.get()]
        args += ["-movflags", "+faststart"]
        args.append(self.output_file.get())
        return args

    def get_state(self):
        return {
            "resolution": self.resolution.get(),
            "fps": self.fps.get(),
            "crf": self.crf.get(),
            "audio_br": self.audio_br.get(),
        }

    def set_state(self, state):
        self.resolution.set(state.get("resolution", "元のまま"))
        self.fps.set(state.get("fps", "元のまま"))
        self.crf.set(state.get("crf", "標準 (CRF 23)"))
        self.audio_br.set(state.get("audio_br", "192k"))


class TrimPanel(TaskPanel):
    title = "トリミング（範囲カット）"
    key = "trim"

    def build(self):
        self.columnconfigure(1, weight=1)
        self.input_file = self._var()
        self.output_file = self._var()
        self._file_row(self, 0, "入力", self.input_file, filetypes=VIDEO_FILETYPES)
        self._file_row(self, 1, "出力", self.output_file, save=True,
                       filetypes=VIDEO_FILETYPES, default_ext=".mp4")

        opts = ttk.Frame(self)
        opts.grid(row=2, column=0, columnspan=3, sticky="we", padx=4, pady=6)
        self.start = self._var("00:00:00")
        self.end = self._var("")
        self.reencode = self._bool_var(False)

        ttk.Label(opts, text="開始 (HH:MM:SS)").grid(
            row=0, column=0, sticky="w", padx=4, pady=2)
        ttk.Entry(opts, textvariable=self.start, width=14).grid(
            row=0, column=1, padx=4, pady=2, sticky="w")
        ttk.Label(opts, text="終了 (HH:MM:SS)").grid(
            row=0, column=2, sticky="w", padx=4, pady=2)
        ttk.Entry(opts, textvariable=self.end, width=14).grid(
            row=0, column=3, padx=4, pady=2, sticky="w")
        ttk.Checkbutton(
            opts, text="正確に切る（再エンコード・低速）", variable=self.reencode
        ).grid(row=1, column=0, columnspan=4, sticky="w", padx=4, pady=4)

        self.input_file.trace_add("write", self._auto_output)

    def _auto_output(self, *_):
        if self.input_file.get() and not self.output_file.get():
            p = Path(self.input_file.get())
            self.output_file.set(str(p.with_name(p.stem + "_trim" + p.suffix)))

    def build_command(self, ffmpeg):
        if not (self.input_file.get() and self.output_file.get() and self.start.get()):
            return None
        args = [ffmpeg, "-y", "-ss", self.start.get()]
        if self.end.get():
            args += ["-to", self.end.get()]
        args += ["-i", self.input_file.get()]
        if self.reencode.get():
            args += ["-c:v", "libx264", "-crf", "23", "-preset", "medium",
                     "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k"]
        else:
            args += ["-c", "copy"]
        args.append(self.output_file.get())
        return args

    def get_state(self):
        return {
            "start": self.start.get(),
            "end": self.end.get(),
            "reencode": self.reencode.get(),
        }

    def set_state(self, state):
        self.start.set(state.get("start", "00:00:00"))
        self.end.set(state.get("end", ""))
        self.reencode.set(state.get("reencode", False))


class AudioExtractPanel(TaskPanel):
    title = "音声抽出"
    key = "audio_extract"

    EXT_BY_FORMAT = {"mp3": ".mp3", "m4a": ".m4a", "wav": ".wav", "flac": ".flac"}

    def build(self):
        self.columnconfigure(1, weight=1)
        self.input_file = self._var()
        self.output_file = self._var()
        self._file_row(self, 0, "入力", self.input_file, filetypes=VIDEO_FILETYPES)
        self._file_row(self, 1, "出力", self.output_file, save=True,
                       filetypes=AUDIO_FILETYPES, default_ext=".mp3")

        opts = ttk.Frame(self)
        opts.grid(row=2, column=0, columnspan=3, sticky="we", padx=4, pady=6)
        self.format = self._var("mp3")
        self.bitrate = self._var("192k")

        ttk.Label(opts, text="形式").grid(row=0, column=0, sticky="w", padx=4, pady=2)
        ttk.Combobox(opts, textvariable=self.format, state="readonly", width=8,
                     values=["mp3", "m4a", "wav", "flac"]).grid(
            row=0, column=1, padx=4, pady=2, sticky="w")
        ttk.Label(opts, text="ビットレート").grid(row=0, column=2, sticky="w", padx=4, pady=2)
        ttk.Combobox(opts, textvariable=self.bitrate, state="readonly", width=8,
                     values=["128k", "192k", "256k", "320k"]).grid(
            row=0, column=3, padx=4, pady=2, sticky="w")

        self.input_file.trace_add("write", self._auto_output)
        self.format.trace_add("write", self._sync_ext)

    def _auto_output(self, *_):
        if self.input_file.get() and not self.output_file.get():
            p = Path(self.input_file.get())
            ext = self.EXT_BY_FORMAT.get(self.format.get(), ".mp3")
            self.output_file.set(str(p.with_suffix(ext)))

    def _sync_ext(self, *_):
        if self.output_file.get():
            ext = self.EXT_BY_FORMAT.get(self.format.get(), ".mp3")
            p = Path(self.output_file.get())
            if p.suffix.lower() != ext:
                self.output_file.set(str(p.with_suffix(ext)))

    def build_command(self, ffmpeg):
        if not (self.input_file.get() and self.output_file.get()):
            return None
        args = [ffmpeg, "-y", "-i", self.input_file.get(), "-vn"]
        fmt = self.format.get()
        if fmt == "mp3":
            args += ["-c:a", "libmp3lame", "-b:a", self.bitrate.get()]
        elif fmt == "m4a":
            args += ["-c:a", "aac", "-b:a", self.bitrate.get()]
        elif fmt == "wav":
            args += ["-c:a", "pcm_s16le"]
        elif fmt == "flac":
            args += ["-c:a", "flac"]
        args.append(self.output_file.get())
        return args

    def get_state(self):
        return {"format": self.format.get(), "bitrate": self.bitrate.get()}

    def set_state(self, state):
        self.format.set(state.get("format", "mp3"))
        self.bitrate.set(state.get("bitrate", "192k"))


class ImageSequencePanel(TaskPanel):
    title = "連番画像 → 動画 (MMD向け)"
    key = "image_sequence"

    NUM_RE = re.compile(r"(\d+)(?=\.[^.]+$)")

    def build(self):
        self.columnconfigure(1, weight=1)
        self.pattern = self._var()
        self.output_file = self._var()

        ttk.Label(self, text="先頭画像").grid(row=0, column=0, sticky="w", padx=4, pady=3)
        ttk.Entry(self, textvariable=self.pattern).grid(
            row=0, column=1, sticky="we", padx=4, pady=3)
        ttk.Button(self, text="選択", command=self._pick_first, width=6).grid(
            row=0, column=2, padx=4, pady=3)

        self._file_row(self, 1, "出力", self.output_file, save=True,
                       filetypes=[("MP4", "*.mp4"), ("MOV", "*.mov"), ("すべて", "*.*")],
                       default_ext=".mp4")

        opts = ttk.Frame(self)
        opts.grid(row=2, column=0, columnspan=3, sticky="we", padx=4, pady=6)
        self.fps = self._var("30")
        self.start_num = self._var("0")
        self.quality = self._var("高画質")

        ttk.Label(opts, text="FPS").grid(row=0, column=0, sticky="w", padx=4, pady=2)
        ttk.Combobox(opts, textvariable=self.fps, state="readonly", width=6,
                     values=["24", "30", "60"]).grid(
            row=0, column=1, padx=4, pady=2, sticky="w")
        ttk.Label(opts, text="開始番号").grid(row=0, column=2, sticky="w", padx=4, pady=2)
        ttk.Entry(opts, textvariable=self.start_num, width=8).grid(
            row=0, column=3, padx=4, pady=2, sticky="w")
        ttk.Label(opts, text="画質").grid(row=1, column=0, sticky="w", padx=4, pady=2)
        ttk.Combobox(opts, textvariable=self.quality, state="readonly", width=10,
                     values=["ロスレス", "高画質", "標準"]).grid(
            row=1, column=1, padx=4, pady=2, sticky="w")

        ttk.Label(self, text="例: frame_%04d.png （%04dは4桁ゼロ埋め）",
                  foreground="#666").grid(
            row=3, column=0, columnspan=3, sticky="w", padx=4, pady=(2, 0))

    def _pick_first(self):
        fn = filedialog.askopenfilename(filetypes=IMAGE_FILETYPES)
        if not fn:
            return
        m = self.NUM_RE.search(fn)
        if m:
            n = len(m.group(1))
            pattern = fn[:m.start()] + f"%0{n}d" + fn[m.end():]
            self.pattern.set(pattern)
            self.start_num.set(str(int(m.group(1))))
            if not self.output_file.get():
                self.output_file.set(str(Path(fn).parent / "output.mp4"))
        else:
            messagebox.showinfo(
                "情報",
                "ファイル名から連番を検出できませんでした。"
                "パターン欄を手動で編集してください（例: frame_%04d.png）。")
            self.pattern.set(fn)

    def build_command(self, ffmpeg):
        if not (self.pattern.get() and self.output_file.get()):
            return None
        args = [ffmpeg, "-y", "-framerate", self.fps.get()]
        if self.start_num.get():
            args += ["-start_number", self.start_num.get()]
        args += ["-i", self.pattern.get()]
        q = self.quality.get()
        if q == "ロスレス":
            args += ["-c:v", "libx264", "-preset", "veryslow",
                     "-qp", "0", "-pix_fmt", "yuv444p"]
        elif q == "高画質":
            args += ["-c:v", "libx264", "-preset", "slow",
                     "-crf", "18", "-pix_fmt", "yuv420p"]
        else:
            args += ["-c:v", "libx264", "-preset", "medium",
                     "-crf", "23", "-pix_fmt", "yuv420p"]
        args.append(self.output_file.get())
        return args

    def get_state(self):
        return {"fps": self.fps.get(),
                "start_num": self.start_num.get(),
                "quality": self.quality.get()}

    def set_state(self, state):
        self.fps.set(state.get("fps", "30"))
        self.start_num.set(state.get("start_num", "0"))
        self.quality.set(state.get("quality", "高画質"))


class TimecodeRemovePanel(TaskPanel):
    title = "タイムコード削除"
    key = "remove_tmcd"

    def build(self):
        self.columnconfigure(1, weight=1)
        self.input_file = self._var()
        self.output_file = self._var()
        self._file_row(self, 0, "入力", self.input_file, filetypes=VIDEO_FILETYPES)
        self._file_row(self, 1, "出力", self.output_file, save=True,
                       filetypes=VIDEO_FILETYPES, default_ext=".mp4")
        ttk.Label(
            self,
            text="ストリームコピー（再エンコードなし）でtmcdトラックを除去します。",
            foreground="#555",
        ).grid(row=2, column=0, columnspan=3, sticky="w", padx=4, pady=4)
        self.input_file.trace_add("write", self._auto_output)

    def _auto_output(self, *_):
        if self.input_file.get() and not self.output_file.get():
            p = Path(self.input_file.get())
            self.output_file.set(str(p.with_name(p.stem + "_notmcd" + p.suffix)))

    def build_command(self, ffmpeg):
        if not (self.input_file.get() and self.output_file.get()):
            return None
        return [ffmpeg, "-y", "-i", self.input_file.get(),
                "-c:a", "copy", "-c:v", "copy", "-write_tmcd", "0",
                self.output_file.get()]


class CustomPanel(TaskPanel):
    title = "カスタム（手動オプション）"
    key = "custom"

    def build(self):
        self.columnconfigure(1, weight=1)
        self.input_option = self._var()
        self.input_file = self._var()
        self.output_option = self._var()
        self.output_file = self._var()

        ttk.Label(self, text="入力オプション").grid(
            row=0, column=0, sticky="w", padx=4, pady=3)
        ttk.Entry(self, textvariable=self.input_option).grid(
            row=0, column=1, columnspan=2, sticky="we", padx=4, pady=3)
        self._file_row(self, 1, "入力", self.input_file)
        ttk.Label(self, text="出力オプション").grid(
            row=2, column=0, sticky="w", padx=4, pady=3)
        ttk.Entry(self, textvariable=self.output_option).grid(
            row=2, column=1, columnspan=2, sticky="we", padx=4, pady=3)
        self._file_row(self, 3, "出力", self.output_file, save=True)

    def build_command(self, ffmpeg):
        if not (self.input_file.get() or self.output_file.get()):
            return None
        args = [ffmpeg, "-y"]
        try:
            if self.input_option.get():
                args += shlex.split(self.input_option.get())
            if self.input_file.get():
                args += ["-i", self.input_file.get()]
            if self.output_option.get():
                args += shlex.split(self.output_option.get())
        except ValueError:
            return None
        if self.output_file.get():
            args.append(self.output_file.get())
        return args

    def get_state(self):
        return {
            "input_option": self.input_option.get(),
            "input_file_path": self.input_file.get(),
            "output_option": self.output_option.get(),
        }

    def set_state(self, state):
        self.input_option.set(state.get("input_option", ""))
        self.input_file.set(state.get("input_file_path", ""))
        self.output_option.set(state.get("output_option", ""))


TASK_CLASSES = [
    YouTubeEncodePanel,
    TrimPanel,
    AudioExtractPanel,
    ImageSequencePanel,
    TimecodeRemovePanel,
    CustomPanel,
]


# -------------------------------------------------------------- main GUI ---


class FFmpegGUI:
    def __init__(self, root):
        self.root = root
        root.title("FFmpeg コマンド GUI")
        root.geometry("760x720")
        root.minsize(640, 560)

        settings = load_settings()
        self.ffmpeg_path = tk.StringVar(value=settings.get("ffmpeg_path", ""))
        self.ffmpeg_path.trace_add("write", lambda *_: self._on_change())

        self._build_widgets()

        last_task = settings.get("last_task")
        if last_task in self.panel_by_key:
            self.task_var.set(self.panel_by_key[last_task].title)

        self._on_change()

    def _build_widgets(self):
        root = self.root
        root.columnconfigure(0, weight=1)
        root.rowconfigure(4, weight=1)

        top = ttk.Frame(root)
        top.grid(row=0, column=0, sticky="we", padx=10, pady=(10, 4))
        top.columnconfigure(1, weight=1)
        ttk.Label(top, text="ffmpeg.exe").grid(row=0, column=0, padx=(0, 6))
        ttk.Entry(top, textvariable=self.ffmpeg_path).grid(
            row=0, column=1, sticky="we")
        ttk.Button(top, text="選択", width=6,
                   command=self._browse_ffmpeg).grid(row=0, column=2, padx=6)

        sel = ttk.Frame(root)
        sel.grid(row=1, column=0, sticky="we", padx=10, pady=4)
        sel.columnconfigure(1, weight=1)
        ttk.Label(sel, text="タスク").grid(row=0, column=0, padx=(0, 6))

        self.panel_by_title = {}
        self.panel_by_key = {}
        titles = []

        container = ttk.LabelFrame(root, text="設定")
        container.grid(row=2, column=0, sticky="we", padx=10, pady=4)
        container.columnconfigure(0, weight=1)
        self._container = container

        for cls in TASK_CLASSES:
            panel = cls(container, on_change=self._on_change)
            self.panel_by_title[cls.title] = panel
            self.panel_by_key[cls.key] = panel
            titles.append(cls.title)

        self.task_var = tk.StringVar(value=titles[0])
        ttk.Combobox(sel, textvariable=self.task_var, state="readonly",
                     values=titles).grid(row=0, column=1, sticky="we")
        ttk.Button(sel, text="プリセット LOAD",
                   command=self._load_preset).grid(row=0, column=2, padx=(6, 2))
        ttk.Button(sel, text="プリセット SAVE",
                   command=self._save_preset).grid(row=0, column=3, padx=2)

        self.task_var.trace_add("write", lambda *_: self._switch_task())

        self.current_panel = self.panel_by_title[titles[0]]
        self.current_panel.grid(row=0, column=0, sticky="we", padx=4, pady=4)

        cmd_frame = ttk.LabelFrame(root, text="生成コマンド")
        cmd_frame.grid(row=3, column=0, sticky="we", padx=10, pady=4)
        cmd_frame.columnconfigure(0, weight=1)
        self.cmd_text = ScrolledText(cmd_frame, height=3, wrap=tk.WORD)
        self.cmd_text.grid(row=0, column=0, sticky="we", padx=4, pady=4)
        self.cmd_text.config(state="disabled")
        ttk.Button(cmd_frame, text="コピー",
                   command=self._copy_command).grid(row=0, column=1, padx=4)

        log_frame = ttk.LabelFrame(root, text="ログ")
        log_frame.grid(row=4, column=0, sticky="nsew", padx=10, pady=4)
        log_frame.rowconfigure(0, weight=1)
        log_frame.columnconfigure(0, weight=1)
        self.log_text = ScrolledText(log_frame, height=10, wrap=tk.WORD)
        self.log_text.grid(row=0, column=0, sticky="nsew", padx=4, pady=4)
        self.log_text.config(state="disabled")

        bottom = ttk.Frame(root)
        bottom.grid(row=5, column=0, sticky="we", padx=10, pady=(4, 10))
        bottom.columnconfigure(1, weight=1)
        self.run_btn = ttk.Button(bottom, text="▶ 実行",
                                  command=self._run, width=12)
        self.run_btn.grid(row=0, column=0, padx=(0, 6))
        self.progress = ttk.Progressbar(bottom, mode="indeterminate", length=200)
        self.progress.grid(row=0, column=1, sticky="we", padx=6)
        self.stop_btn = ttk.Button(bottom, text="■ 停止",
                                   command=self._stop, width=12, state="disabled")
        self.stop_btn.grid(row=0, column=2, padx=6)
        self.status_var = tk.StringVar(value="待機")
        ttk.Label(bottom, textvariable=self.status_var).grid(
            row=0, column=3, padx=10)

        self.runner = CommandRunner(root, self.log_text, self.progress,
                                    self.status_var, self._on_run_done)

    def _browse_ffmpeg(self):
        fn = filedialog.askopenfilename(filetypes=[
            ("ffmpeg", "ffmpeg.exe"),
            ("実行ファイル", "*.exe"),
            ("すべて", "*.*"),
        ])
        if fn:
            self.ffmpeg_path.set(fn)

    def _switch_task(self):
        title = self.task_var.get()
        if title not in self.panel_by_title:
            return
        self.current_panel.grid_forget()
        self.current_panel = self.panel_by_title[title]
        self.current_panel.grid(row=0, column=0, sticky="we", padx=4, pady=4)
        self._on_change()
        self._save_app_settings()

    def _on_change(self):
        args = self._current_command()
        self.cmd_text.config(state="normal")
        self.cmd_text.delete("1.0", tk.END)
        if args:
            self.cmd_text.insert(tk.END, shlex.join(args))
        self.cmd_text.config(state="disabled")

    def _current_command(self):
        ffmpeg = self.ffmpeg_path.get() or "ffmpeg.exe"
        return self.current_panel.build_command(ffmpeg)

    def _copy_command(self):
        text = self.cmd_text.get("1.0", tk.END).strip()
        if not text:
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.status_var.set("コマンドをコピーしました")

    def _run(self):
        args = self._current_command()
        if not args:
            messagebox.showerror(
                "エラー", "コマンドが組み立てられていません。必要な項目を入力してください。")
            return
        self.run_btn.config(state="disabled")
        self.stop_btn.config(state="normal")
        self.runner.run(args)
        self._save_app_settings()

    def _stop(self):
        self.runner.stop()

    def _on_run_done(self, rc):
        self.run_btn.config(state="normal")
        self.stop_btn.config(state="disabled")
        if rc == 0:
            messagebox.showinfo("完了", "処理が完了しました。")

    def _save_app_settings(self):
        save_settings({
            "ffmpeg_path": self.ffmpeg_path.get(),
            "last_task": self.current_panel.key,
        })

    def _save_preset(self):
        fn = filedialog.asksaveasfilename(
            defaultextension=".json", filetypes=[("JSON", "*.json")])
        if not fn:
            return
        data = {
            "task": self.current_panel.key,
            "state": self.current_panel.get_state(),
        }
        try:
            with open(fn, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except OSError as e:
            messagebox.showerror("エラー", f"保存に失敗しました: {e}")

    def _load_preset(self):
        fn = filedialog.askopenfilename(filetypes=[("JSON", "*.json")])
        if not fn:
            return
        try:
            with open(fn, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            messagebox.showerror("エラー", f"読み込みに失敗しました: {e}")
            return

        if isinstance(data, dict) and "task" in data and "state" in data:
            key = data["task"]
            if key not in self.panel_by_key:
                messagebox.showerror("エラー", f"未対応のタスク: {key}")
                return
            panel = self.panel_by_key[key]
            self.task_var.set(panel.title)
            panel.set_state(data["state"])
            self._on_change()
            return

        if isinstance(data, dict) and (
                "input_option" in data or "output_option" in data):
            custom = self.panel_by_key["custom"]
            self.task_var.set(custom.title)
            custom.set_state(data)
            self._on_change()
            return

        messagebox.showerror("エラー", "プリセット形式を認識できませんでした。")


if __name__ == "__main__":
    root = tk.Tk()
    try:
        style = ttk.Style()
        if sys.platform == "win32" and "vista" in style.theme_names():
            style.theme_use("vista")
    except tk.TclError:
        pass
    FFmpegGUI(root)
    root.mainloop()
