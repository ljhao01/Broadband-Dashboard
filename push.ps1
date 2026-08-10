# 一键提交并推送项目到 GitHub
# 用法（PowerShell）：
#   cd d:\vscode\家宽
#   Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
#   .\push.ps1
$ErrorActionPreference = "Stop"

# 0. 确保 git 可用（没装则尝试用 winget 安装）
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Write-Host ">>> 未检测到 git，尝试安装 ..." -ForegroundColor Yellow
    winget install --id Git.Git -e --silent --accept-package-agreements --accept-source-agreements
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
}
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Write-Host ">>> git 仍不可用，请手动安装 Git 后重跑本脚本。" -ForegroundColor Red
    Read-Host "按回车退出"
    exit 1
}
Write-Host ">>> git 版本: $(git --version)" -ForegroundColor Green

# 1. 进入项目目录
Set-Location "d:\vscode\家宽"

# 2. 初始化（若尚未初始化）
if (-not (Test-Path ".git")) {
    git init
}

# 3. 全部加入并提交
git add .
$status = git status --porcelain
if ($status) {
    git commit -m "家宽 AI 可视化智能管控平台 - 深色大屏看板 (TDesign)"
} else {
    Write-Host ">>> 没有需要提交的变更。" -ForegroundColor Cyan
}

# 4. 关联远程并推送
$remote = "https://github.com/ljhao01/Broadband-Dashboard.git"
$hasRemote = git remote get-url origin 2>$null
if (-not $hasRemote) {
    git remote add origin $remote
} else {
    git remote set-url origin $remote
}
git branch -M main

# 若远程已有内容，先拉取（允许无关历史）再推
$pull = git pull origin main --allow-unrelated-histories 2>&1
Write-Host ">>> pull 结果: $pull"

git push -u origin main

Write-Host ">>> 完成！" -ForegroundColor Green
Read-Host "按回车退出"
