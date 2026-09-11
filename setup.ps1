param(
    [string]$CodexHome = "",
    [switch]$ForceSkill,
    [switch]$ForceAgents,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
$ScriptDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
$Installer = Join-Path $ScriptDirectory "scripts/install_codex.py"
$InstallerArguments = @($Installer)

if ($CodexHome) {
    $InstallerArguments += @("--codex-home", $CodexHome)
}
if ($ForceSkill) {
    $InstallerArguments += "--force-skill"
}
if ($ForceAgents) {
    $InstallerArguments += "--force-agents"
}
if ($DryRun) {
    $InstallerArguments += "--dry-run"
}

if (Get-Command py -ErrorAction SilentlyContinue) {
    & py -3 @InstallerArguments
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    & python @InstallerArguments
} elseif (Get-Command python3 -ErrorAction SilentlyContinue) {
    & python3 @InstallerArguments
} else {
    throw "Python 3 is required to install this plugin."
}

exit $LASTEXITCODE
