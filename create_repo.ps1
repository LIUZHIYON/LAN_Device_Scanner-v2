$ErrorActionPreference = "Stop"

function Run-Cmd {
    param($Cmd)
    $p = Start-Process -NoNewWindow -FilePath "openclaw" -ArgumentList $Cmd -PassThru -Wait -RedirectStandardOutput "$env:TEMP\browser_out.txt" -RedirectStandardError "$env:TEMP\browser_err.txt"
    $stdout = (Get-Content "$env:TEMP\browser_out.txt" -Raw).Trim()
    $stderr = (Get-Content "$env:TEMP\browser_err.txt" -Raw).Trim()
    if ($LASTEXITCODE -ne 0) {
        throw "Failed: $Cmd`n$stderr"
    }
    return $stdout, $stderr
}

Write-Host "=== GitHub 自动创建仓库 ==="
Write-Host ""

# Step 1: Focus the repo name textbox by clicking the label above it
Write-Host "1. 定位仓库名输入框..."
openclaw browser click 104 2>$null
if ($LASTEXITCODE -ne 0) {
    # Try to snapshot first
    openclaw browser snapshot | Out-Null
    openclaw browser click 104 2>$null
}
Start-Sleep -Seconds 1

# Step 2: Clear existing text with Ctrl+A then Delete
Write-Host "2. 清空输入框..."
openclaw browser press "Control+a" 2>$null
Start-Sleep -Milliseconds 300
openclaw browser press "Delete" 2>$null
Start-Sleep -Milliseconds 300

# Step 3: Type new name
Write-Host "3. 输入仓库名: lan-scanner"
openclaw browser type 104 "lan-scanner" 2>$null

# Step 4: Click Create
Write-Host "4. 点击创建按钮..."
Start-Sleep -Seconds 1
openclaw browser snapshot | Out-Null
openclaw browser click 189 2>$null

Write-Host ""
Write-Host "✅ 仓库创建请求已发送！"
Write-Host "等待页面跳转..."
Start-Sleep -Seconds 3
openclaw browser snapshot
