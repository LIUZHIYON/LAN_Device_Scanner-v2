# Save credentials temporarily and push
$userName = "LIUZHIYON"
$password = "Liu11480153"

cd "C:\Users\29503\Desktop\局域网设备扫描工具_v2"

# First, let's try to use 'hub' or 'gh' - if not available, use git directly
# Create the repo on GitHub using their new fine-grained token approach
# We'll use the web API with basic auth

$pair = "${userName}:${password}"
$bytes = [System.Text.Encoding]::ASCII.GetBytes($pair)
$base64 = [System.Convert]::ToBase64String($bytes)

$headers = @{
    "Authorization" = "***"
    "Accept" = "application/vnd.github.v3+json"
    "User-Agent" = "PowerShell"
}

$repoBody = @{
    name = "lan-scanner"
    description = "局域网设备扫描工具 v2.0 - Web版，支持配置子网/MAC/SSH参数，实时扫描并显示结果"
    private = $false
    auto_init = $false
} | ConvertTo-Json

Write-Host "正在通过GitHub API创建远程仓库..."
$ErrorActionPreference = "Stop"
try {
    $response = Invoke-RestMethod -Uri "https://api.github.com/user/repos" -Method POST -Headers $headers -Body $repoBody -ContentType "application/json"
    Write-Host "✅ 仓库创建成功: $($response.html_url)"
    
    # Add remote and push
    $remoteUrl = "https://${userName}:${password}@github.com/${userName}/lan-scanner.git"
    git remote remove origin 2>$null
    git remote add origin $remoteUrl
    git push -u origin main
    Write-Host "✅ 推送成功!"
}
catch {
    Write-Host "❌ 通过API创建仓库失败: $($_.Exception.Message)"
    Write-Host "可能是密码认证被废弃(GitHub在2021年后不再接受密码认证)"
    Write-Host ""
    Write-Host "替代方案:"
    Write-Host "1. 去 https://github.com/settings/tokens 生成一个 Personal Access Token"
    Write-Host "   选 repo 权限"
    Write-Host "2. 然后运行:"
    Write-Host "   cd $pwd"
    Write-Host '   git remote add origin https://LIUZHIYON:你的TOKEN@github.com/LIUZHIYON/lan-scanner.git'
    Write-Host "   git push -u origin main"
    Write-Host ""
    Write-Host "或者手动操作:"
    Write-Host "1. 浏览器打开 https://github.com/new"
    Write-Host "2. 仓库名填 lan-scanner，公开库，不初始化"
    Write-Host "3. 创建后在命令行运行:"
    Write-Host "   cd $pwd"
    Write-Host "   git remote add origin https://github.com/LIUZHIYON/lan-scanner.git"
    Write-Host "   git push -u origin main"
}
