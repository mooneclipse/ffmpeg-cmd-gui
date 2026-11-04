[日本語](#FFmpegコマンドGUIツール)

[English](#FFmpeg-CMD-GUI)

# FFmpegコマンドGUIツール

FFmpeg cmd guiはGUIに記入したオプションでFFmpegコマンドを実行するアプリです。

## 機能

- FFmpeg実行に必要な設定を記入するとコマンドが実行されます。そのため、コマンドプロンプトをたたく必要がありません。
- 実行中の出力はアプリ内のログ欄に表示されます。実行したコマンドもログに残ります。
- 進捗バーと、経過時間／全体の時間で進み具合を表示します。
- 変換を途中で停止できます。
- 実行するコマンドを色分けしてプレビューし、ワンクリックでコピーできます。
- 出力ファイルが既にある場合は、上書きの確認を表示します。
- 前回の設定を自動で保存し、次回起動時に復元します。保存先は Windows が `%APPDATA%\ffmpeg-cmd-gui\`、それ以外は `~/.config/ffmpeg-cmd-gui/` です。
- プリセットとしてjsonファイルに保存ができるので、別のファイルで同じ処理を実行したいときに使いまわすことが可能です。変換前・変換後のファイルもプリセットに保存されます。

## 使用方法

v2.0でUIを刷新しました（スクリーンショットは更新予定です）。

1. アプリケーションを起動します。前回の設定が自動で復元されます。
2. 必要に応じて、画面右上の「プリセット」の「読み込み」から保存済みの設定を読み込みます。
3. 「ffmpeg」欄にffmpegのパスを設定します。未設定の場合はPATHに登録されたffmpegを使います。
4. 「変換前」で、変換前のファイルを選択し、必要に応じてオプションを指定します。
5. 「変換後」で、変換後のファイルを設定し、必要に応じてオプションを指定します。
6. 「実行コマンド」欄で、生成されたFFmpegコマンドを確認します。「コピー」でクリップボードにコピーできます。
7. 「変換」ボタンをクリックして変換処理を開始します。途中で止める場合は「停止」ボタンをクリックします。
8. 「ログ」を開くと、FFmpegの出力を確認できます。変換に失敗した場合はログが自動で開きます。

## プリセットの使用

- 現在の設定をプリセットとして保存するには、「保存」ボタンをクリックします。
- 保存されたプリセットを読み込むには、「読み込み」ボタンをクリックします。

サンプルプリセットを4件同梱しています。

- wavへ変換
- timecodeを削除
- mp3へ変換
- mp4(h264)へ変換

アプリの「読み込み」ボタンから読み込んでください。

## 要件

- Python 3.x
- tkinter（通常はPythonに標準で含まれています）
- FFmpeg（システムにインストールされているか、パスが正しく設定されている必要があります）

### exe版の作り方

PyInstallerを使ってWindows用のexeを作成できます。

1. PythonとPyInstallerをインストールします（`pip install pyinstaller`）。
2. 同梱の `build_exe.bat` を実行します。
3. `dist` フォルダに `ffmpeg-cmd-gui.exe` が作成されます。

## 注意事項

- FFmpegのパスが正しく設定されていることを確認してください。
- 入力ファイルと出力ファイルのパスは、正確に指定する必要があります。
- オプション欄には、パスを含むオプション（スペースを含むパスなど）は書けません。パスは「ファイル」欄で指定してください。
- 複雑なFFmpegオプションを使用する場合は、FFmpegの公式ドキュメントを参照してください。

## 免責事項

このプログラムの使用によって生じたいかなる損害についても、開発者は責任を負いません。以下の点に特に注意してください：

1. データ損失：入力ファイルや出力先のデータが破損または消失する可能性があります。重要なファイルは必ずバックアップを取ってから使用してください。

2. システムへの影響：不適切な設定やオプションの使用により、システムに悪影響を及ぼす可能性があります。

3. 著作権侵害：このツールを使用して著作権で保護されたコンテンツを不正に変換または配布しないでください。

4. リソース消費：大規模なファイルの変換は、システムリソースを大量に消費する可能性があります。

5. セキュリティリスク：信頼できない出所からのプリセットやスクリプトを使用する際は注意してください。

ユーザーは自己責任でこのプログラムを使用し、適切な注意を払ってください。不明な点がある場合は、使用を中止し、専門家に相談することをお勧めします。

## ライセンス

このプロジェクトは[MITライセンス](https://opensource.org/licenses/MIT)の下で公開されています。

## 貢献

バグ報告や機能リクエストは、GitHubのIssueトラッカーを使用してください。プルリクエストも歓迎します。

## 作者

mooneclipse[https://x.com/mooneclipse]

---

# FFmpeg CMD GUI

FFmpeg CMD GUI is an application that executes FFmpeg commands using options entered in a graphical user interface.

## Features

- Executes FFmpeg commands based on settings entered in the GUI, eliminating the need to use the command prompt.
- Output is shown in the log area inside the app. The executed command is also recorded in the log.
- Shows a progress bar with elapsed / total time so you can see how far the conversion has progressed.
- Conversion can be stopped midway.
- Previews the command to be executed with color coding, and lets you copy it with one click.
- Asks for confirmation when the output file already exists.
- Automatically saves the previous settings and restores them on the next launch. They are stored in `%APPDATA%\ffmpeg-cmd-gui\` on Windows and in `~/.config/ffmpeg-cmd-gui/` on other systems.
- Settings can be saved as JSON preset files, enabling reuse of the same process on different files. The input and output files are also saved in the preset.

## How to Use

The UI was redesigned in v2.0 (screenshots will be updated).

1. Launch the application. The previous settings are restored automatically.
2. If needed, click "Load" under "Preset" at the top right to load saved settings.
3. Set the path to FFmpeg in the "ffmpeg" field. If left empty, the ffmpeg registered in your PATH is used.
4. In "Input" (変換前), select the input file and specify input options if necessary.
5. In "Output" (変換後), set the output file and specify output options if necessary.
6. Verify the generated FFmpeg command in the command area. Use "Copy" to copy it to the clipboard.
7. Click the "Convert" button to start the conversion. To stop it midway, click the "Stop" button.
8. Open "Log" to see the FFmpeg output. The log opens automatically if the conversion fails.

## Using Presets

- To save the current settings as a preset, click the "Save" button.
- To load a saved preset, click the "Load" button.

Four sample presets are included:

- Convert to wav
- Remove timecode
- Convert to mp3
- Convert to mp4 (H.264)

Load them with the app's "Load" button.

## Requirements

- Python 3.x
- tkinter (usually included with Python by default)
- FFmpeg (must be installed on your system or have its path correctly set)

### Building the exe

You can build a Windows exe with PyInstaller.

1. Install Python and PyInstaller (`pip install pyinstaller`).
2. Run the bundled `build_exe.bat`.
3. `ffmpeg-cmd-gui.exe` is created in the `dist` folder.

## Precautions

- Ensure that the FFmpeg path is set correctly.
- Input and output file paths must be specified accurately.
- Options that contain a path (for example, a path with spaces) cannot be written in the option fields. Specify paths in the "File" fields.
- For complex FFmpeg options, please refer to the official FFmpeg documentation.

## Disclaimer

The developer bears no responsibility for any damage caused by the use of this program. Please pay special attention to the following points:

1. Data Loss: Input files or output data may become corrupted or lost. Always backup important files before use.

2. System Impact: Improper settings or options may adversely affect your system.

3. Copyright Infringement: Do not use this tool to illegally convert or distribute copyrighted content.

4. Resource Consumption: Converting large files may consume a significant amount of system resources.

5. Security Risk: Exercise caution when using presets or scripts from untrusted sources.

Users should use this program at their own risk and exercise appropriate caution. If you have any doubts, please stop using the program and consult an expert.

## License

This project is released under the [MIT License](https://opensource.org/licenses/MIT).

## Contributions

Please use the GitHub Issue tracker for bug reports and feature requests. Pull requests are also welcome.

## Author

mooneclipse [https://x.com/mooneclipse]
