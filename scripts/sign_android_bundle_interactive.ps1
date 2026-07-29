param(
    [string]$KeystorePath = 'C:\Users\peete\MotMan-secrets',
    [string]$KeyAlias = 'motman-upload'
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$resultPath = Join-Path $projectRoot 'output\android-aab-signing-result.json'
$logPath = Join-Path $projectRoot 'output\android-aab-signing.log'

function ConvertTo-PlainText([Security.SecureString]$SecureValue) {
    $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($SecureValue)
    try {
        return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
    }
    finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
    }
}

try {
    if (-not (Test-Path -LiteralPath $KeystorePath)) {
        throw "Clé d'upload introuvable : $KeystorePath"
    }

    Write-Host 'MotMan — signature sécurisée du nouvel Android App Bundle' -ForegroundColor Cyan
    Write-Host "Clé : $KeystorePath"
    Write-Host "Alias : $KeyAlias"
    Write-Host 'Les mots de passe restent uniquement dans cette fenêtre et ne sont enregistrés nulle part.'
    Write-Host ''

    $storeSecure = Read-Host 'Mot de passe de la clé (keystore)' -AsSecureString
    $keySecure = Read-Host "Mot de passe de l'alias (Entrée = même mot de passe)" -AsSecureString
    $storePassword = ConvertTo-PlainText $storeSecure
    $keyPassword = if ($keySecure.Length -eq 0) {
        $storePassword
    }
    else {
        ConvertTo-PlainText $keySecure
    }

    $env:MOTMAN_KEYSTORE_PATH = $KeystorePath
    $env:MOTMAN_KEYSTORE_PASSWORD = $storePassword
    $env:MOTMAN_KEY_PASSWORD = $keyPassword

    $keytool = 'C:\Program Files\Android\Android Studio1\jbr\bin\keytool.exe'
    if (-not (Test-Path -LiteralPath $keytool)) {
        throw 'keytool Android Studio est introuvable.'
    }
    $keytoolOutput = (& $keytool '-J-Duser.language=en' -list -v -keystore $KeystorePath -storepass:env MOTMAN_KEYSTORE_PASSWORD 2>&1) -join [Environment]::NewLine
    if ($LASTEXITCODE -ne 0) {
        throw 'Le mot de passe du keystore est incorrect.'
    }
    $aliases = @([regex]::Matches($keytoolOutput, '(?m)^Alias name:\s*(.+?)\s*$') | ForEach-Object { $_.Groups[1].Value })
    if ($aliases.Count -eq 1 -and $aliases[0] -ne $KeyAlias) {
        $KeyAlias = $aliases[0]
        Write-Host "Alias détecté automatiquement : $KeyAlias" -ForegroundColor Yellow
    }
    elseif ($aliases.Count -gt 0 -and $KeyAlias -notin $aliases) {
        throw "Alias '$KeyAlias' absent du keystore. Alias disponibles : $($aliases -join ', ')."
    }
    $env:MOTMAN_KEY_ALIAS = $KeyAlias

    Push-Location $projectRoot
    try {
        Remove-Item -LiteralPath $logPath -ErrorAction SilentlyContinue
        & powershell -ExecutionPolicy Bypass -File scripts\build_android_bundle.ps1 -SkipSync 2>&1 |
            Tee-Object -FilePath $logPath
        if ($LASTEXITCODE -ne 0) {
            throw "La construction signée a échoué (code $LASTEXITCODE)."
        }
    }
    finally {
        Pop-Location
    }

    $bundle = Get-Item (Join-Path $projectRoot 'android\app\build\outputs\bundle\release\app-release.aab')
    $hash = (Get-FileHash -LiteralPath $bundle.FullName -Algorithm SHA256).Hash
    $result = [ordered]@{
        success = $true
        bundle = $bundle.FullName
        size = $bundle.Length
        sha256 = $hash
        signedAt = (Get-Date).ToString('o')
    }
    $result | ConvertTo-Json | Set-Content -LiteralPath $resultPath -Encoding UTF8

    Write-Host ''
    Write-Host 'AAB signé avec succès.' -ForegroundColor Green
    Write-Host $bundle.FullName
    Write-Host "SHA-256 : $hash"
    Start-Sleep -Seconds 5
}
catch {
    $failure = [ordered]@{
        success = $false
        error = $_.Exception.Message
        failedAt = (Get-Date).ToString('o')
    }
    $failure | ConvertTo-Json | Set-Content -LiteralPath $resultPath -Encoding UTF8
    Write-Host ''
    Write-Host $_.Exception.Message -ForegroundColor Red
    Read-Host 'Appuyez sur Entrée pour fermer'
    exit 1
}
finally {
    $storePassword = $null
    $keyPassword = $null
    Remove-Item Env:MOTMAN_KEYSTORE_PATH -ErrorAction SilentlyContinue
    Remove-Item Env:MOTMAN_KEYSTORE_PASSWORD -ErrorAction SilentlyContinue
    Remove-Item Env:MOTMAN_KEY_ALIAS -ErrorAction SilentlyContinue
    Remove-Item Env:MOTMAN_KEY_PASSWORD -ErrorAction SilentlyContinue
}
