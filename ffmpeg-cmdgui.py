import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext
import json
import os
import subprocess

class FFmpegConverterGUI:
    def __init__(self, master):
        # GUIのウィンドウ設定
        self.master = master
        master.title("FFmpeg command gui")
        master.geometry("480x440")  # ウィンドウサイズを設定
        
        # ScrolledText ウィジェットを格納する変数
        self.convert_command = None  
        # ウィジェットの作成
        self.create_widgets()
        # 最新の設定をロード
        self.load_latest_settings()

    def create_widgets(self):
        # プリセット行
        preset_frame = tk.Frame(self.master)
        preset_frame.grid(row=0, column=0, columnspan=4, sticky="we", padx=15, pady=(15, 5))
        
        tk.Label(preset_frame, text="プリセット").pack(side=tk.LEFT)
        tk.Button(preset_frame, text="LOAD", command=self.load_preset, width=8).pack(side=tk.LEFT, padx=(10, 5))
        tk.Button(preset_frame, text="SAVE", command=self.save_preset, width=8).pack(side=tk.LEFT)

        # FFmpegパスの行
        ffmpeg_frame = tk.Frame(self.master)
        ffmpeg_frame.grid(row=1, column=0, columnspan=4, sticky="we", padx=15, pady=5)
        
        tk.Label(ffmpeg_frame, text="ffmpeg.exe").pack(side=tk.LEFT)
        self.ffmpeg_path = tk.StringVar()
        tk.Entry(ffmpeg_frame, textvariable=self.ffmpeg_path, width=50).pack(side=tk.LEFT, padx=(10, 5))
        tk.Button(ffmpeg_frame, text="選択", command=lambda: self.browse_file(self.ffmpeg_path), width=8).pack(side=tk.LEFT)

        # 入力ファイルのフレーム
        input_frame = tk.LabelFrame(self.master, text="変換前")
        input_frame.grid(row=2, column=0, columnspan=4, sticky="we", padx=15, pady=5)

        tk.Label(input_frame, text="オプション").grid(row=0, column=0, sticky="w", padx=(5, 10), pady=5)
        self.input_option = tk.StringVar()
        tk.Entry(input_frame, textvariable=self.input_option, width=50).grid(row=0, column=1, columnspan=2, sticky="we", pady=5)

        tk.Label(input_frame, text="ファイル").grid(row=1, column=0, sticky="w", padx=(5, 10), pady=5)
        self.input_file_path = tk.StringVar()
        tk.Entry(input_frame, textvariable=self.input_file_path, width=50).grid(row=1, column=1, sticky="we", pady=5)
        tk.Button(input_frame, text="選択", command=lambda: self.browse_file(self.input_file_path), width=8).grid(row=1, column=2, padx=5, pady=5)

        # 出力ファイルのフレーム
        output_frame = tk.LabelFrame(self.master, text="変換後")
        output_frame.grid(row=3, column=0, columnspan=4, sticky="we", padx=15, pady=5)

        tk.Label(output_frame, text="オプション").grid(row=0, column=0, sticky="w", padx=(5, 10), pady=5)
        self.output_option = tk.StringVar()
        tk.Entry(output_frame, textvariable=self.output_option, width=50).grid(row=0, column=1, columnspan=2, sticky="we", pady=5)

        tk.Label(output_frame, text="ファイル").grid(row=1, column=0, sticky="w", padx=(5, 10), pady=5)
        self.output_file_path = tk.StringVar()
        tk.Entry(output_frame, textvariable=self.output_file_path, width=50).grid(row=1, column=1, sticky="we", pady=5)
        tk.Button(output_frame, text="選択", command=lambda: self.browse_file(self.output_file_path, save=True), width=8).grid(row=1, column=2, padx=5, pady=5)

        # 実行コマンド表示
        tk.Label(self.master, text="実行コマンド").grid(row=4, column=0, padx=15, sticky="w", pady=(10, 0))
        self.convert_command = scrolledtext.ScrolledText(self.master, width=60, height=3, wrap=tk.WORD)
        self.convert_command.grid(row=5, column=0, padx=15, columnspan=4, sticky="we")
        self.convert_command.config(state='disabled')

        # 変換ボタン
        tk.Button(self.master, text="変換", command=self.convert, width=20, height=2).grid(row=6, column=0, columnspan=4, pady=15)

        # イベントのバインド
        for var in [self.input_file_path, self.input_option, self.output_option, self.output_file_path, self.ffmpeg_path]:
            var.trace_add("write", self.update_convert_command)

    def browse_file(self, string_var, save=False):
        # ファイルを選択するダイアログの表示
        if save:
            filename = filedialog.asksaveasfilename(filetypes=[("All Files", "*.*")])
        else:
            filename = filedialog.askopenfilename(filetypes=[("All Files", "*.*")])
        if filename:
            string_var.set(filename)

    def update_convert_command(self, *args):
        # 変換コマンドを更新する
        ffmpeg = self.ffmpeg_path.get() or "ffmpeg.exe"
        input_option = self.input_option.get()
        input_file = self.input_file_path.get()
        output_option = self.output_option.get()
        output_file = self.output_file_path.get()

        # コマンドの構築
        cmd_parts = [ffmpeg, "-y"]
        
        if input_option:
            cmd_parts.append(input_option)
        
        if input_file:
            cmd_parts.extend(['-i', f'"{input_file}"'])
        
        if output_option:
            cmd_parts.append(output_option)
        
        if output_file:
            cmd_parts.append(f'"{output_file}"')

        # コマンドを結合
        cmd = ' '.join(cmd_parts)
        
        # テキストウィジェットを更新
        self.convert_command.config(state='normal')  # 一時的に編集可能にする
        self.convert_command.delete('1.0', tk.END)  # 既存の内容をクリア
        if cmd.strip():
            self.convert_command.insert(tk.END, cmd)
        self.convert_command.config(state='disabled')  # 再び読み取り専用にする

    def convert(self):
        # 変換処理を実行
        cmd = self.convert_command.get('1.0', tk.END).strip()
        if not cmd:
            messagebox.showerror("エラー", "変換コマンドが生成されていません。")
            return

       # 一時的なバッチファイルにコマンドを書き込む
        with open("temp_ffmpeg_cmd.bat", "w", encoding="shift_jis") as f:
            f.write("@echo off\n")
            f.write(f"{cmd}\n")
            f.write("echo.\n")  # 空行を追加
            f.write("echo 処理が完了しました。何かキーを押すと終了します。\n")
            f.write("pause >nul\n")  # キー入力を待つ（メッセージを表示せず）
            f.write("exit\n")  # コマンドプロンプトを終了

        try:
            # 新しいコマンドプロンプトウィンドウでバッチファイルを実行
            subprocess.Popen(["start", "cmd", "/k", "temp_ffmpeg_cmd.bat"], shell=True)
        except Exception as e:
            messagebox.showerror("エラー", f"変換処理の開始中にエラーが発生しました: {str(e)}")

        # 最新の設定を保存
        self.save_latest_settings()

    def save_latest_settings(self):
        # 最新の設定をJSON形式で保存
        settings = {
            "ffmpeg_path": self.ffmpeg_path.get(),
            "input_option": self.input_option.get(),
            "input_file_path": self.input_file_path.get(),
            "output_option": self.output_option.get(),
            "convert_command": self.convert_command.get('1.0', tk.END).strip()
        }
        with open("latest_cnv.json", "w") as f:
            json.dump(settings, f)

    def load_latest_settings(self):
       # 保存された設定をロード
        try:
            with open("latest_cnv.json", "r") as f:
                settings = json.load(f)
            self.ffmpeg_path.set(settings.get("ffmpeg_path", ""))
            self.input_option.set(settings.get("input_option", ""))
            self.input_file_path.set(settings.get("input_file_path", ""))
            self.output_option.set(settings.get("output_option", ""))
            
            # convert_command の設定
            self.convert_command.config(state='normal')
            self.convert_command.delete('1.0', tk.END)
            self.convert_command.insert(tk.END, settings.get("convert_command", ""))
            self.convert_command.config(state='disabled')
            
            # GUIの更新を強制
            self.master.update_idletasks()
        except FileNotFoundError:
            pass

    def save_preset(self):
        # プリセットを保存
        filename = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON files", "*.json")])
        if filename:
            settings = {
                "ffmpeg_path": self.ffmpeg_path.get(),
                "input_option": self.input_option.get(),
                "input_file_path": self.input_file_path.get(),
                "output_option": self.output_option.get(),
            }
            with open(filename, "w") as f:
                json.dump(settings, f)

    def load_preset(self):
        # プリセットをロード
        filename = filedialog.askopenfilename(filetypes=[("JSON files", "*.json")])
        if filename:
            with open(filename, "r") as f:
                settings = json.load(f)
            self.ffmpeg_path.set(settings.get("ffmpeg_path", ""))
            self.input_option.set(settings.get("input_option", ""))
            self.input_file_path.set(settings.get("input_file_path", ""))
            self.output_option.set(settings.get("output_option", ""))

if __name__ == "__main__":
    # アプリケーションの開始
    root = tk.Tk()
    app = FFmpegConverterGUI(root)
    root.mainloop()
