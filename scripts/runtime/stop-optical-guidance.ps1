# =====================================================================
# 光学引导系统 · 停止（兼容入口）
#   实际编排逻辑已迁到 scripts/runtime/launcher.py。
# =====================================================================
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$Root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$py   = Join-Path $Root '.venv\Scripts\python.exe'

if (-not (Test-Path $py)) {
    $cmd = Get-Command python -ErrorAction SilentlyContinue
    if ($cmd) { $py = $cmd.Source }
}
if (-not $py -or -not (Test-Path $py)) {
    Write-Host ' 找不到 python，请先安装 Python 3.12 (64位) 并加入 PATH' -ForegroundColor Red
    exit 1
}

& $py (Join-Path $PSScriptRoot 'launcher.py') stop
exit $LASTEXITCODE
