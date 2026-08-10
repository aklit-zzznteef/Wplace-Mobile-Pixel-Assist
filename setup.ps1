$ErrorActionPreference = "Stop"
$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $ProjectDir

if (Get-Command py -ErrorAction SilentlyContinue) {
    & py -m pip install -r requirements.txt
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    & python -m pip install -r requirements.txt
} elseif (Test-Path -LiteralPath "$env:USERPROFILE\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe") {
    & "$env:USERPROFILE\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -c "import numpy, PIL; print('Codex bundled Python is ready; no installation is needed.')"
} else {
    throw "Python was not found. Install Python 3.11 or newer first."
}
