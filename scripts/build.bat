@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
cd /d "%~dp0.."

REM 版本号取自 src\launchforge.py 的 APP_VERSION，避免手写两处不一致
for /f "tokens=2 delims='" %%v in ('findstr /b "APP_VERSION" src\launchforge.py') do set APPVER=%%v
if "%APPVER%"=="" (
    echo [错误] 未能从 src\launchforge.py 解析 APP_VERSION
    exit /b 1
)
set OUTNAME=一键多启_v%APPVER%
echo 版本 %APPVER%  ^-^>  %OUTNAME%.exe
echo.

echo [1/3] 安装依赖（国内镜像）...
python -m pip install -i https://mirrors.aliyun.com/pypi/simple/ -r requirements.txt pyinstaller
if errorlevel 1 goto :err

echo [2/3] 清理旧产物...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist "%OUTNAME%.spec" del /q "%OUTNAME%.spec"

echo [3/3] 打包...
REM  --onefile        单文件 exe（运行时自解压到临时目录）
REM  --windowed       GUI 程序，不弹控制台
REM  --add-data       把图标放进包内，供 sys._MEIPASS 读取（Windows 分隔符是分号）
REM  --icon           写入 exe 文件图标
REM  --version-file   写入 VERSIONINFO（文件属性里可见）
python -m PyInstaller --noconfirm --onefile --windowed ^
    --icon=assets\logo.ico ^
    --add-data "assets\logo.ico;." ^
    --version-file=version.txt ^
    --name "%OUTNAME%" ^
    src\launchforge.py
if errorlevel 1 goto :err

REM 根目录只保留当前可用版本（git 不管二进制，历史版本走 Release）
copy /y "dist\%OUTNAME%.exe" ".\%OUTNAME%.exe" >nul

echo.
echo 构建完成：dist\%OUTNAME%.exe
echo 已复制到仓库根目录：%OUTNAME%.exe
pause
exit /b 0

:err
echo.
echo 构建失败，请查看上方报错。
pause
exit /b 1
