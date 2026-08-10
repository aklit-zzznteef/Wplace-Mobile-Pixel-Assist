$ErrorActionPreference = "Stop"
$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $ProjectDir

$BundledPython = "$env:USERPROFILE\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"

if (Test-Path -LiteralPath $BundledPython) {
    & $BundledPython pixel_assist.py @args
} elseif (Get-Command py -ErrorAction SilentlyContinue) {
    & py pixel_assist.py @args
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    & python pixel_assist.py @args
} else {
    throw "Python was not found. Install Python 3.11 or newer, then run setup.ps1."
}
