param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]] $AppArgs
)

$ErrorActionPreference = "Stop"
if (Get-Variable -Name PSNativeCommandUseErrorActionPreference -Scope Global -ErrorAction SilentlyContinue) {
    $global:PSNativeCommandUseErrorActionPreference = $false
}

$ProjectDir = Split-Path -Parent $PSCommandPath
$VenvDir = Join-Path $ProjectDir ".venv"
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
$PythonBin = if ($env:PYTHON_BIN) { $env:PYTHON_BIN } else { "python" }

Set-Location $ProjectDir

function Test-Venv {
    if (-not (Test-Path $VenvPython)) {
        return $false
    }
    @'
import pathlib
import sys

expected = pathlib.Path(sys.argv[1]).resolve()
actual = pathlib.Path(sys.prefix).resolve()
raise SystemExit(0 if actual == expected and sys.prefix != sys.base_prefix else 1)
'@ | & $VenvPython - $VenvDir *> $null
    return $LASTEXITCODE -eq 0
}

if (-not (Test-Venv)) {
    if (Test-Path $VenvDir) {
        Write-Host "Ambiente virtual invalido ou movido. Recriando .venv..."
        Remove-Item -LiteralPath $VenvDir -Recurse -Force
    }
    & $PythonBin -m venv $VenvDir
}

$env:VIRTUAL_ENV = $VenvDir
$env:PATH = "$(Join-Path $VenvDir 'Scripts');$env:PATH"

@'
import pip
import setuptools
import wheel
'@ | & $VenvPython - *> $null
if ($LASTEXITCODE -ne 0) {
    & $VenvPython -m pip install --upgrade pip setuptools wheel
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}

@'
import importlib.util
import sys

required = ["PySide6", "watchdog", "yaml", "psutil"]
missing = [name for name in required if importlib.util.find_spec(name) is None]
if missing:
    print(", ".join(missing))
    sys.exit(1)
'@ | & $VenvPython -
if ($LASTEXITCODE -ne 0) {
    Write-Host "Dependencias ausentes na venv. Tentando instalar dependencias do projeto..."
    & $VenvPython -m pip install -e . pytest
}

& $VenvPython -m rclone_sync_manager init *> $null

if (-not $AppArgs -or $AppArgs.Count -eq 0) {
    & $VenvPython -m rclone_sync_manager gui
} else {
    & $VenvPython -m rclone_sync_manager @AppArgs
}
exit $LASTEXITCODE
