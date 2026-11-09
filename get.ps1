# Set up the DrivnX workspace on Windows (PowerShell):
#   irm https://raw.githubusercontent.com/trisonlab/drivnx-cli/main/get.ps1 | iex
# Creates ~\DrivnX (or $env:DRIVNX_HOME), clones drivnx-cli into it and runs `drivnx install`.
$ErrorActionPreference = 'Stop'

$ws = if ($env:DRIVNX_HOME) { $env:DRIVNX_HOME } else { Join-Path $HOME 'DrivnX' }
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
