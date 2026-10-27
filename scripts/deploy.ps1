[CmdletBinding()]
param(
    [switch]$SkipDeploy
)

$ErrorActionPreference = 'Stop'

$projectRoot = Split-Path -Parent $PSScriptRoot
$appRoot = Join-Path $projectRoot 'app'
$configPath = Join-Path $appRoot 'appsail-python\app-config.json'
$backupPath = "$configPath.bak"
$envPath = Join-Path $projectRoot '.env'
$injectedKeys = @(
    'HS_QML_URL',
    'HS_QML_KEY',
    'HS_ORG_ID',
    'HS_ENV_NAME',
    'HS_OAUTH_ID',
    'HS_OAUTH_SECRET',
    'HS_OAUTH_REFRESH',
    'HS_OAUTH_URL'
)
$envKeyMap = [ordered]@{
    'HS_QML_URL' = 'QUICKML_ENDPOINT_URL'
    'HS_QML_KEY' = 'QUICKML_ENDPOINT_KEY'
    'HS_ORG_ID' = 'CATALYST_ORG'
    'HS_ENV_NAME' = 'CATALYST_ENVIRONMENT'
    'HS_OAUTH_ID' = 'ZOHO_CLIENT_ID'
    'HS_OAUTH_SECRET' = 'ZOHO_CLIENT_SECRET'
    'HS_OAUTH_REFRESH' = 'ZOHO_REFRESH_TOKEN'
    'HS_OAUTH_URL' = 'ZOHO_ACCOUNTS_URL'
}

function Read-LocalEnv {
    param([string]$Path)

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "Missing .env file."
    }

    $values = @{}
    foreach ($line in Get-Content -LiteralPath $Path) {
        $trimmed = $line.Trim()
        if ([string]::IsNullOrWhiteSpace($trimmed) -or $trimmed.StartsWith('#')) {
            continue
        }

        $separator = $trimmed.IndexOf('=')
        if ($separator -lt 1) {
            continue
        }

        $key = $trimmed.Substring(0, $separator).Trim()
        $value = $trimmed.Substring($separator + 1).Trim()
        while ($value.Length -ge 2 -and
            (($value.StartsWith('"') -and $value.EndsWith('"')) -or
             ($value.StartsWith("'") -and $value.EndsWith("'")))) {
            $value = $value.Substring(1, $value.Length - 2).Trim()
        }
        $values[$key] = $value
    }
    return $values
}

$backupCreated = $false
try {
    Copy-Item -LiteralPath $configPath -Destination $backupPath -Force
    $backupCreated = $true

    $envValues = Read-LocalEnv -Path $envPath
    $missingKeys = @(
        $envKeyMap.Values | Where-Object {
            -not $envValues.ContainsKey($_) -or
            [string]::IsNullOrWhiteSpace([string]$envValues[$_])
        }
    )
    if ($missingKeys.Count -gt 0) {
        throw "Missing required .env key(s): $($missingKeys -join ', ')"
    }

    $config = Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json
    $environment = [ordered]@{}
    foreach ($key in $injectedKeys) {
        $environment[$key] = [string]$envValues[$envKeyMap[$key]]
    }
    $config.env_variables = $environment

    $json = $config | ConvertTo-Json -Depth 20
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($configPath, $json, $utf8NoBom)

    Write-Output 'Injected environment variable names:'
    foreach ($key in $injectedKeys) {
        Write-Output $key
    }

    if (-not $SkipDeploy) {
        Push-Location $appRoot
        try {
            & catalyst deploy
            if ($LASTEXITCODE -ne 0) {
                throw "catalyst deploy failed with exit code $LASTEXITCODE."
            }
        }
        finally {
            Pop-Location
        }
    }
}
finally {
    if ($backupCreated) {
        Copy-Item -LiteralPath $backupPath -Destination $configPath -Force
        Remove-Item -LiteralPath $backupPath -Force
    }
}
