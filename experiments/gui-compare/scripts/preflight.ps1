# Read-only prerequisite check. Intentionally does not install software or change Windows settings.
$ErrorActionPreference = 'Stop'
$rows = @(
    @{ name='Python'; command='python'; args=@('--version') },
    @{ name='Node'; command='node'; args=@('--version') },
    @{ name='npm'; command='npm'; args=@('--version') },
    @{ name='.NET SDK'; command='dotnet'; args=@('--list-sdks') },
    @{ name='Rust / cargo'; command='cargo'; args=@('--version') },
    @{ name='WinApp CLI'; command='winapp'; args=@('--version') }
)
Write-Host '=== Aredoko GUI comparison prerequisites (read only) ==='
foreach ($item in $rows) {
    $found = Get-Command $item.command -ErrorAction SilentlyContinue
    if (-not $found) { Write-Host "[MISSING] $($item.name): $($item.command)"; continue }
    try {
        $output = (& $item.command @($item.args) 2>&1) -join '; '
        Write-Host "[FOUND] $($item.name): $output"
    } catch { Write-Host "[ERROR] $($item.name): $_" }
}
$dm = Get-ItemProperty -Path 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\AppModelUnlock' -Name AllowDevelopmentWithoutDevLicense -ErrorAction SilentlyContinue
Write-Host "Developer Mode: $($dm.AllowDevelopmentWithoutDevLicense -eq 1)"
Write-Host 'No components were installed or changed.'
