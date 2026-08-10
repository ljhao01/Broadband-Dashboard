@echo off
chcp 65001 >nul 2>&1
setlocal

:: 家宽项目一键提交并推送到 GitHub
:: 仓库：https://github.com/ljhao01/Broadband-Dashboard.git

set "REPO=https://github.com/ljhao01/Broadband-Dashboard.git"
set "PROJ=d:\vscode\家宽"

echo ============================================
echo   家宽 AI 可视化智能管控平台 - Git 推送
echo ============================================

:: 0. 检测 git
where git >nul 2>nul
if errorlevel 1 (
    echo [!] 未检测到 git，尝试用 winget 安装...
    winget install --id Git.Git -e --silent --accept-package-agreements --accept-source-agreements
    if errorlevel 1 (
        echo [!] git 安装失败，请手动安装 Git 后重跑本脚本。
        pause
        exit /b 1
    )
    :: 刷新 PATH（重新打开的 cmd 才生效，这里尝试直接调用常见路径）
    set "PATH=%PATH%;C:\Program Files\Git\bin;C:\Program Files\Git\cmd"
)
git --version

:: 1. 进入项目目录
cd /d "%PROJ%"
if errorlevel 1 (
    echo [!] 无法进入目录 %PROJ%
    pause
    exit /b 1
)

:: 2. 初始化（若需要）
if not exist ".git" (
    git init
)

:: 3. 添加并提交
git add .
git commit -m "家宽 AI 可视化智能管控平台 - 深色大屏看板 (TDesign)"

:: 4. 关联远程
git remote get-url origin >nul 2>nul
if errorlevel 1 (
    git remote add origin %REPO%
) else (
    git remote set-url origin %REPO%
)
git branch -M main

:: 5. 远程若已有内容先拉取（允许无关历史）
git pull origin main --allow-unrelated-histories 2>nul

:: 6. 推送
git push -u origin main

echo.
echo ============================================
echo   完成！按任意键退出。
echo ============================================
pause >nul
