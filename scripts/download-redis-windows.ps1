param(
    [Parameter(Mandatory = $true)]
    [string]$OutFile
)

$ErrorActionPreference = 'Stop'
$urls = @(
    'https://ghfast.top/https://github.com/tporadowski/redis/releases/download/v5.0.14.1/Redis-x64-5.0.14.1.zip',
    'https://mirror.ghproxy.com/https://github.com/tporadowski/redis/releases/download/v5.0.14.1/Redis-x64-5.0.14.1.zip',
    'https://gh-proxy.com/https://github.com/tporadowski/redis/releases/download/v5.0.14.1/Redis-x64-5.0.14.1.zip',
    'https://github.com/tporadowski/redis/releases/download/v5.0.14.1/Redis-x64-5.0.14.1.zip'
)

$outDir = Split-Path -Parent $OutFile
if ($outDir -and -not (Test-Path $outDir)) {
    New-Item -ItemType Directory -Path $outDir -Force | Out-Null
}

foreach ($url in $urls) {
    Write-Host "[redis] 尝试: $url"
    try {
        if (Get-Command curl.exe -ErrorAction SilentlyContinue) {
            curl.exe -fsSL --connect-timeout 30 --max-time 300 -o $OutFile $url
        } else {
            Invoke-WebRequest -Uri $url -OutFile $OutFile -UseBasicParsing -TimeoutSec 300
        }
        if ((Test-Path $OutFile) -and ((Get-Item $OutFile).Length -gt 1000000)) {
            Write-Host "[redis] 下载成功"
            exit 0
        }
        Remove-Item $OutFile -Force -ErrorAction SilentlyContinue
    } catch {
        Write-Host "[redis] 失败: $($_.Exception.Message)"
        Remove-Item $OutFile -Force -ErrorAction SilentlyContinue
    }
}

Write-Host '[redis] 所有镜像均下载失败'
exit 1
