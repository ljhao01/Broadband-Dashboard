# 一键安装 Git 并推送项目到 GitHub
# 用法：右键此文件 -> 用 PowerShell 运行（或在该目录打开 PowerShell 执行 .\setup_and_push.ps1）
$ErrorActionPreference = "Stop"

# 1. 安装 Git（若已安装则跳过）
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Write-Host ">>> 正在安装 Git ..." -ForegroundColor Cyan
    winget install --id Git.Git -e --silent --accept-package-agreements --accept-source-agreements
    # 刷新 PATH
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
}

Write-Host ">>> git 版本: $(git --version)" -ForegroundColor Green

# 2. 进入项目目录
Set-Location "d:\vscode\家宽"

# 3. 初始化并提交
if (-not (Test-Path ".git")) {
    git init
}
git add .
git commit -m "家宽 AI 可视化智能管控平台 - 深色大屏看板 (TDesign)"

# 4. 关联远程并推送
$remote = "https://github.com/ljhao01/Broadband-Dashboard.git"
$hasRemote = git remote get-url origin 2>$null
if (-not $hasRemote) {
    git remote add origin $remote
} else {
    git remote set-url origin $remote
}
git branch -M main
git push -u origin main

Write-Host ">>> 完成！" -ForegroundColor Green
Read-Host "按回车退出"
