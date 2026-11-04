@echo off
rem ffmpeg-cmd-gui v2.0 - Windows用 exe ビルドスクリプト
rem 使い方: このファイルをダブルクリックするか、コマンドプロンプトで実行する
rem 前提: Python 3 と PyInstaller がインストールされていること
rem       未導入の場合: pip install pyinstaller
setlocal
cd /d %~dp0

python -m PyInstaller --noconfirm --onefile --windowed --name ffmpeg-cmd-gui ffmpeg-cmdgui.py
if errorlevel 1 (
    echo.
    echo ビルドに失敗しました。Python と PyInstaller が入っているか確認してください。
    pause
    exit /b 1
)

echo.
echo ビルドが完了しました: dist\ffmpeg-cmd-gui.exe
pause
