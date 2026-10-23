$ErrorActionPreference = "Stop"
if (-not $env:MT5_PASSWORD) { throw "MT5_PASSWORD is missing; demo login cannot proceed" }
$url = "https://download.mql5.com/cdn/web/deriv.com.limited/mt5/derivmt5setup.exe"
Invoke-WebRequest -Uri $url -OutFile "$env:TEMP\derivmt5setup.exe"
$installer = Start-Process -PassThru "$env:TEMP\derivmt5setup.exe" -ArgumentList "/auto"
if (-not $installer.WaitForExit(600000)) { $installer.Kill(); throw "MT5 installer timed out" }
Start-Sleep -Seconds 20
$terminal = Get-ChildItem "C:\Program Files","C:\Program Files (x86)" -Recurse -Filter terminal64.exe -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $terminal) { throw "MT5 terminal64.exe not found after installation" }
# An explicit portable path prevents initialize() attaching to a different
# first-run terminal/user profile. Passwords are supplied only by the Python API.
$runtime = Join-Path $env:RUNNER_TEMP "sentinel-mt5"
New-Item -ItemType Directory -Force -Path $runtime | Out-Null
Copy-Item (Join-Path $terminal.DirectoryName "*") $runtime -Recurse -Force
$terminalPath = Join-Path $runtime "terminal64.exe"
"MT5_TERMINAL_PATH=$terminalPath" | Out-File -FilePath $env:GITHUB_ENV -Encoding utf8 -Append
# Enable terminal algorithmic trading, but never embed the account password in a file.
$config = Join-Path $env:TEMP "sentinel-mt5.ini"
@"
[Common]
KeepPrivate=1
Server=$env:MT5_DEMO_SERVER
[Experts]
Enabled=1
AllowLiveTrading=1
AllowDllImport=0
"@ | Set-Content $config
Get-Process terminal64 -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Process -FilePath $terminalPath -ArgumentList @("/portable", "/skipupdate", "/config:$config")
Start-Sleep -Seconds 45
Write-Host "Native MT5 terminal launched; Python broker performs authenticated demo login"
