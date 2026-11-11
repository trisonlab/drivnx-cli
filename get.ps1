# Set up the DrivnX workspace on Windows (PowerShell):
#   irm https://raw.githubusercontent.com/trisonlab/drivnx-cli/main/get.ps1 | iex
# Creates DrivnX\ in the folder you run it from (the folder itself if it's already named DrivnX, or
# $env:DRIVNX_HOME), clones drivnx-cli into it and runs `drivnx install`.
$ErrorActionPreference = 'Stop'

$here = (Get-Location).Path
$ws = if ($env:DRIVNX_HOME) { $env:DRIVNX_HOME }
      elseif ((Split-Path -Leaf $here) -eq 'DrivnX') { $here }
      else { Join-Path $here 'DrivnX' }
# Only an empty folder or an existing workspace, so a run in the wrong place can't mix into another project.
if ((Test-Path $ws) -and (Get-ChildItem -Force $ws | Select-Object -First 1)) {
    $isWs = @('drivnx-cli', 'drivnx-docs', 'drivnx-web', 'drivnx-landing') |
        Where-Object { Test-Path (Join-Path (Join-Path $ws $_) '.git') }
    if (-not $isWs) {
        throw "$ws already has other files and isn't a DrivnX workspace. Run this from another folder, or set DRIVNX_HOME to an empty folder."
    }
}
Write-Host "Installing the DrivnX workspace into $ws"

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    throw 'Install git first: winget install Git.Git (then open a new terminal)'
}
$py = Get-Command py -ErrorAction SilentlyContinue
$pyArgs = @('-3')
if (-not $py) { $py = Get-Command python -ErrorAction SilentlyContinue; $pyArgs = @() }
if (-not $py) { throw 'Install Python 3.10+ first: winget install Python.Python.3.12 (then open a new terminal)' }

New-Item -ItemType Directory -Force -Path $ws | Out-Null
$cli = Join-Path $ws 'drivnx-cli'
if (Test-Path (Join-Path $cli '.git')) {
    git -C $cli pull --ff-only --quiet
} else {
    git clone --quiet https://github.com/trisonlab/drivnx-cli.git $cli
}
& $py.Source @pyArgs (Join-Path $cli 'drivnx') install
