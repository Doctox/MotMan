param(
    [switch]$SkipSync
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot

function Test-JavaHome([string]$Path) {
    return $Path -and (Test-Path (Join-Path $Path 'bin\java.exe')) -and (Test-Path (Join-Path $Path 'lib\jvm.cfg'))
}

if (-not (Test-JavaHome $env:JAVA_HOME)) {
    $androidStudioRoots = @(
        'C:\Program Files\Android\Android Studio1\jbr',
        'C:\Program Files\Android\Android Studio\jbr'
    )
    $detectedJava = $androidStudioRoots | Where-Object { Test-JavaHome $_ } | Select-Object -First 1
    if (-not $detectedJava) {
        throw 'Java 21 introuvable. Ouvrez Android Studio ou définissez JAVA_HOME vers son dossier jbr.'
    }
    $env:JAVA_HOME = $detectedJava
}

if (-not $env:ANDROID_HOME) {
    $env:ANDROID_HOME = Join-Path $env:LOCALAPPDATA 'Android\Sdk'
}

Push-Location $projectRoot
try {
    if (-not $SkipSync) {
        & npm.cmd run mobile:assets
        if ($LASTEXITCODE -ne 0) { throw 'La génération des ressources Android a échoué.' }

        & npm.cmd run mobile:sync
        if ($LASTEXITCODE -ne 0) { throw 'La synchronisation Capacitor a échoué.' }
    }

    Push-Location (Join-Path $projectRoot 'android')
    try {
        & .\gradlew.bat :app:bundleRelease
        if ($LASTEXITCODE -ne 0) { throw 'La création du bundle Android a échoué.' }
    }
    finally {
        Pop-Location
    }

    $bundle = Get-Item (Join-Path $projectRoot 'android\app\build\outputs\bundle\release\app-release.aab')
    Write-Host "Bundle créé : $($bundle.FullName) ($([math]::Round($bundle.Length / 1MB, 2)) Mo)"

    $signingVariables = @(
        $env:MOTMAN_KEYSTORE_PATH,
        $env:MOTMAN_KEYSTORE_PASSWORD,
        $env:MOTMAN_KEY_ALIAS,
        $env:MOTMAN_KEY_PASSWORD
    )
    if ($signingVariables -contains $null -or $signingVariables -contains '') {
        Write-Warning 'Bundle non signé : configurez les quatre variables MOTMAN_* avant un envoi dans Google Play.'
    }
    else {
        Write-Host 'Signature de publication configurée via les variables MOTMAN_*.'
    }
}
finally {
    Pop-Location
}
