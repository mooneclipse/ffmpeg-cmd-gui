[日本語](#FFmpegコマンドGUIツール)

[English](#FFmpeg-CMD-GUI)

# FFmpegコマンドGUIツール

FFmpeg cmd guiはGUIに記入したオプションでFFmpegコマンドを実行するアプリです。

## 機能

- FFmpeg実行に必要な設定を記入するとコマンドが実行されます。そのため、コマンドプロンプトをたたく必要がありません。
- 実行したものはbatファイルに残るので同じ処理を何度も実行できます。
- プリセットとしてjsonファイルに保存ができるので、別のファイルで同じ処理を実行したいときに使いまわすことが可能です。

## 使用方法

![image](https://github.com/user-attachments/assets/2d9cb231-0dd1-4861-a404-3a5f4b01b52e)

1. アプリケーションを起動します。
2. 環境変数に登録していない方はffmpeg.exeのパスを設定します。
3. 入力ファイルを選択し、必要に応じて入力オプションを指定します。
4. 出力ファイルを設定し、必要に応じて出力オプションを指定します。
5. 生成されたFFmpegコマンドを確認します。
6. 「変換」ボタンをクリックして変換処理を開始します。

## プリセットの使用

- 現在の設定をプリセットとして保存するには、「SAVE」ボタンをクリックします。
- 保存されたプリセットを読み込むには、「LOAD」ボタンをクリックします。

サンプルプリセットを設置しています。  
プリセットを右クリックして「名前を付けてリンク先を保存」をクリックしてダウンロードし、アプリのLOADボタンから読み込んでください。

![image](https://github.com/user-attachments/assets/0ef9c917-0d9d-4e40-ae89-81a8e1c42877)


## 要件

- Python 3.x
- tkinter（通常はPythonに標準で含まれています）
- FFmpeg（システムにインストールされているか、パスが正しく設定されている必要があります）

## 注意事項

- FFmpegのパスが正しく設定されていることを確認してください。
- 入力ファイルと出力ファイルのパスは、正確に指定する必要があります。
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
- Commands are saved as batch files, allowing for repeated execution of the same process.
- Settings can be saved as JSON preset files, enabling reuse of the same process on different files.

## How to Use

![image](https://github.com/user-attachments/assets/2d9cb231-0dd1-4861-a404-3a5f4b01b52e)

1. Launch the application.
2. If FFmpeg is not registered in your environment variables, set the path to ffmpeg.exe.
3. Select the input file and specify input options if necessary.
4. Set the output file and specify output options if necessary.
5. Verify the generated FFmpeg command.
6. Click the "Convert" button to start the conversion process.

## Using Presets

- To save the current settings as a preset, click the "SAVE" button.
- To load a saved preset, click the "LOAD" button.

## Requirements

- Python 3.x
- tkinter (usually included with Python by default)
- FFmpeg (must be installed on your system or have its path correctly set)

## Precautions

- Ensure that the FFmpeg path is set correctly.
- Input and output file paths must be specified accurately.
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
