param(
    [string]$Version = '5.2',
    [string]$BlenderExe = '',
    [Parameter(Mandatory=$true)][string]$Script,
    [string]$Arguments = '',
    [Parameter(Mandatory=$true)][string]$Label
)
$ErrorActionPreference = 'Stop'
$benchRoot = Split-Path -Parent $PSScriptRoot
$taskRoot = Split-Path -Parent $benchRoot
$configuredPaths = Join-Path $taskRoot 'benchmark-local-paths.json'
if (!$BlenderExe -and (Test-Path -LiteralPath $configuredPaths)) {
    $BlenderExe = (Get-Content -LiteralPath $configuredPaths -Raw | ConvertFrom-Json).$Version
}
if (!$BlenderExe) { $BlenderExe = (Get-Command blender.exe -ErrorAction Stop).Source }
$profile = Join-Path $benchRoot ('artifacts\comparator-sandbox\' + $Label + '-' + $Version)
$env:BLENDER_USER_CONFIG = Join-Path $profile 'config'
$env:BLENDER_USER_SCRIPTS = Join-Path $profile 'scripts'
$env:BLENDER_USER_EXTENSIONS = Join-Path $profile 'extensions'
$env:OPENBLAS_NUM_THREADS = '2'
$env:OMP_NUM_THREADS = '2'
$output = Join-Path $benchRoot ('artifacts\' + $Label + '-' + $Version + '-console.txt')
$errorOutput = Join-Path $benchRoot ('artifacts\' + $Label + '-' + $Version + '-stderr.txt')
$launchArgs = @('--background','--factory-startup','--disable-autoexec','-t','2','--python-exit-code','1','--python',(Join-Path $benchRoot $Script))
if ($Arguments) { $launchArgs += '--'; $launchArgs += $Arguments.Split(' ',[System.StringSplitOptions]::RemoveEmptyEntries) }
$quotedArgs = $launchArgs | ForEach-Object { if ($_ -match '\s') { '"' + $_ + '"' } else { $_ } }
$process = Start-Process -FilePath $BlenderExe -ArgumentList $quotedArgs -WorkingDirectory $benchRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput $output -RedirectStandardError $errorOutput
try { $process.PriorityClass = 'BelowNormal' } catch { }
Write-Output ('Benchmark process priority: ' + $process.PriorityClass)
$process.WaitForExit()
Get-Content -LiteralPath $output -Tail 12
Get-Content -LiteralPath $errorOutput -Tail 8
if ($process.ExitCode -ne 0) { throw ('Isolated Blender failed with exit code ' + $process.ExitCode) }
