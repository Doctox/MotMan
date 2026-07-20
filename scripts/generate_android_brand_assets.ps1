param(
    [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing

$resRoot = Join-Path $ProjectRoot 'android\app\src\main\res'
$masterRoot = Join-Path $ProjectRoot 'android\app\src\main\play-assets'
$iconMaster = Join-Path $masterRoot 'motman-icon-master.png'
$splashMaster = Join-Path $masterRoot 'motman-splash-master.png'
$wordmarkMaster = Join-Path $ProjectRoot 'public\assets\motman-logo-v2.png'

if (-not (Test-Path -LiteralPath $iconMaster) -or -not (Test-Path -LiteralPath $splashMaster) -or -not (Test-Path -LiteralPath $wordmarkMaster)) {
    throw 'Les masters MotMan sont absents de android/app/src/main/play-assets.'
}

function New-Canvas([int]$Width, [int]$Height) {
    $bitmap = [System.Drawing.Bitmap]::new($Width, $Height, [System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
    $bitmap.SetResolution(144, 144)
    return $bitmap
}

function Save-Png([System.Drawing.Bitmap]$Bitmap, [string]$Path) {
    $directory = Split-Path -Parent $Path
    New-Item -ItemType Directory -Force -Path $directory | Out-Null
    $Bitmap.Save($Path, [System.Drawing.Imaging.ImageFormat]::Png)
}

function Set-HighQuality([System.Drawing.Graphics]$Graphics) {
    $Graphics.CompositingMode = [System.Drawing.Drawing2D.CompositingMode]::SourceOver
    $Graphics.CompositingQuality = [System.Drawing.Drawing2D.CompositingQuality]::HighQuality
    $Graphics.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
    $Graphics.PixelOffsetMode = [System.Drawing.Drawing2D.PixelOffsetMode]::HighQuality
    $Graphics.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::HighQuality
}

function Export-Icon([System.Drawing.Image]$Source, [int]$Size, [string]$Path) {
    $bitmap = New-Canvas $Size $Size
    $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
    try {
        Set-HighQuality $graphics
        $graphics.Clear([System.Drawing.ColorTranslator]::FromHtml('#FBF7EC'))
        $cropSize = [Math]::Min($Source.Width, $Source.Height) * 0.72
        $crop = [System.Drawing.RectangleF]::new(
            ($Source.Width - $cropSize) / 2,
            ($Source.Height - $cropSize) / 2,
            $cropSize,
            $cropSize
        )
        $destination = [System.Drawing.RectangleF]::new(0, 0, $Size, $Size)
        $graphics.DrawImage($Source, $destination, $crop, [System.Drawing.GraphicsUnit]::Pixel)
        Save-Png $bitmap $Path
    }
    finally {
        $graphics.Dispose()
        $bitmap.Dispose()
    }
}

function Export-Splash([System.Drawing.Image]$Source, [int]$Width, [int]$Height, [string]$Path) {
    $bitmap = New-Canvas $Width $Height
    $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
    try {
        Set-HighQuality $graphics
        $graphics.Clear([System.Drawing.ColorTranslator]::FromHtml('#FBF7EC'))
        $scale = [Math]::Min(($Width * 0.72) / $Source.Width, ($Height * 0.28) / $Source.Height)
        $drawWidth = $Source.Width * $scale
        $drawHeight = $Source.Height * $scale
        $destination = [System.Drawing.RectangleF]::new(
            ($Width - $drawWidth) / 2,
            ($Height - $drawHeight) / 2,
            $drawWidth,
            $drawHeight
        )
        $graphics.DrawImage($Source, $destination)
        Save-Png $bitmap $Path
    }
    finally {
        $graphics.Dispose()
        $bitmap.Dispose()
    }
}

$icon = [System.Drawing.Image]::FromFile($iconMaster)
$splash = [System.Drawing.Image]::FromFile($wordmarkMaster)
try {
    $launcherSizes = @{ mdpi = 48; hdpi = 72; xhdpi = 96; xxhdpi = 144; xxxhdpi = 192 }
    $foregroundSizes = @{ mdpi = 108; hdpi = 162; xhdpi = 216; xxhdpi = 324; xxxhdpi = 432 }

    foreach ($density in $launcherSizes.Keys) {
        $folder = Join-Path $resRoot "mipmap-$density"
        Export-Icon $icon $launcherSizes[$density] (Join-Path $folder 'ic_launcher.png')
        Export-Icon $icon $launcherSizes[$density] (Join-Path $folder 'ic_launcher_round.png')
        Export-Icon $icon $foregroundSizes[$density] (Join-Path $folder 'ic_launcher_foreground.png')
    }

    $splashTargets = @(
        @{ Path = 'drawable\splash.png'; Width = 480; Height = 320 },
        @{ Path = 'drawable-land-mdpi\splash.png'; Width = 480; Height = 320 },
        @{ Path = 'drawable-land-hdpi\splash.png'; Width = 800; Height = 480 },
        @{ Path = 'drawable-land-xhdpi\splash.png'; Width = 1280; Height = 720 },
        @{ Path = 'drawable-land-xxhdpi\splash.png'; Width = 1600; Height = 960 },
        @{ Path = 'drawable-land-xxxhdpi\splash.png'; Width = 1920; Height = 1280 },
        @{ Path = 'drawable-port-mdpi\splash.png'; Width = 320; Height = 480 },
        @{ Path = 'drawable-port-hdpi\splash.png'; Width = 480; Height = 800 },
        @{ Path = 'drawable-port-xhdpi\splash.png'; Width = 720; Height = 1280 },
        @{ Path = 'drawable-port-xxhdpi\splash.png'; Width = 960; Height = 1600 },
        @{ Path = 'drawable-port-xxxhdpi\splash.png'; Width = 1280; Height = 1920 }
    )
    foreach ($target in $splashTargets) {
        Export-Splash $splash $target.Width $target.Height (Join-Path $resRoot $target.Path)
    }
}
finally {
    $icon.Dispose()
    $splash.Dispose()
}

Write-Host 'Icônes adaptatives et splash MotMan générés.'
