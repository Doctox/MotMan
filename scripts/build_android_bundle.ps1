param(
    [switch]$SkipSync,
    [switch]$AllowUnsigned,
    [switch]$AllowWithoutFirebase,
    [switch]$InteractiveSigning
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

function Read-PlainTextSecret([string]$Prompt) {
    $secureValue = Read-Host $Prompt -AsSecureString
    $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureValue)
    try {
        return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
    }
    finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
        $secureValue.Dispose()
    }
}

if ($InteractiveSigning) {
    if (-not $env:MOTMAN_KEYSTORE_PATH) {
        $env:MOTMAN_KEYSTORE_PATH = 'C:\Users\peete\MotMan-secrets'
    }
    if (-not $env:MOTMAN_KEY_ALIAS) {
        $env:MOTMAN_KEY_ALIAS = 'motman-upload'
    }
    if (-not $env:MOTMAN_KEYSTORE_PASSWORD) {
        $env:MOTMAN_KEYSTORE_PASSWORD = Read-PlainTextSecret 'Mot de passe du keystore MotMan'
    }
    if (-not $env:MOTMAN_KEY_PASSWORD) {
        $env:MOTMAN_KEY_PASSWORD = Read-PlainTextSecret 'Mot de passe de la cle motman-upload'
    }
}

$signingVariables = @{
    MOTMAN_KEYSTORE_PATH = $env:MOTMAN_KEYSTORE_PATH
    MOTMAN_KEYSTORE_PASSWORD = $env:MOTMAN_KEYSTORE_PASSWORD
    MOTMAN_KEY_ALIAS = $env:MOTMAN_KEY_ALIAS
    MOTMAN_KEY_PASSWORD = $env:MOTMAN_KEY_PASSWORD
}
$missingSigningVariables = @($signingVariables.Keys | Where-Object { -not $signingVariables[$_] })
if ($missingSigningVariables.Count -gt 0 -and -not $AllowUnsigned) {
    throw "Bundle Play refusé : variables de signature absentes ($($missingSigningVariables -join ', ')). Utilisez -AllowUnsigned uniquement pour un diagnostic local."
}
if ($missingSigningVariables.Count -eq 0 -and -not (Test-Path -LiteralPath $env:MOTMAN_KEYSTORE_PATH)) {
    throw "Keystore introuvable : $($env:MOTMAN_KEYSTORE_PATH)"
}

$googleServicesPath = Join-Path $projectRoot 'android\app\google-services.json'
if (-not (Test-Path -LiteralPath $googleServicesPath) -and -not $AllowWithoutFirebase) {
    throw 'Bundle Play refusé : android\app\google-services.json est absent. Utilisez -AllowWithoutFirebase uniquement pour un diagnostic local.'
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

    if ($missingSigningVariables.Count -gt 0) {
        Write-Warning 'Bundle non signé : configurez les quatre variables MOTMAN_* avant un envoi dans Google Play.'
    }
    else {
        $jarsigner = Join-Path $env:JAVA_HOME 'bin\jarsigner.exe'
        $signatureOutput = (& $jarsigner -verify $bundle.FullName 2>&1) -join [Environment]::NewLine
        if (
            $LASTEXITCODE -ne 0 -or
            $signatureOutput -match '(?i)jar is unsigned|non signé|non signe'
        ) {
            throw 'La vérification de signature du bundle a échoué : le fichier produit n’est pas signé.'
        }
        Write-Host 'Signature de publication configurée via les variables MOTMAN_*.'
    }
}
finally {
    Pop-Location
}
