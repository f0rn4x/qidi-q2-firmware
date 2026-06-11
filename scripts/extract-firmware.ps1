<#
.SYNOPSIS
    Unpack a QIDI Q2 firmware update package (.zip) into a full extract tree.

.DESCRIPTION
    Reproduces the steps documented in <ver>-full/README.md, generically, so the same
    script works for current and future packages:

      1. Find the SOC blob inside the zip (entry name matches *QD_Q2_SOC*, which also
         covers the QD_Update/ nesting used by 1.1.0) and pull it out. The SOC blob is a
         Debian package (an ar archive: debian-binary + control.tar.* + data.tar.*);
         data.tar.* is the rootfs overlay.
      2. Split the .deb into its control.tar.* / data.tar.* members (any compression -
         xz, zstd, gz - is matched by glob, not hard-coded).
      3. Extract control.tar.* -> <ver>-full/control and data.tar.* -> <ver>-full/rootfs.
         Failures from the rootfs extraction (Windows can't create the Linux symlinks)
         are written to <ver>-full/rootfs-extract.log with paths made relative to the
         firmware-extract folder (the Windows root is rewritten to '.').
      4. Copy every non-SOC zip member (QD_Q2_MCU / _THR / _BOX, firmware_manifest.json,
         ...) into <ver>-full/package by leaf name.
      5. Inflate and pretty-print the embedded Klipper data dictionary from each MCU
         blob (fw_dict.py) into package/<blob>.dict.json.

    All output lives under the firmware-extract folder (this script's grandparent by
    default), so the tree is relocatable - no absolute paths are baked into the result.

.PARAMETER Zip
    Path to the firmware .zip. Absolute, or relative to the firmware-extract folder.

.PARAMETER Version
    Label for the output folders (<Version> for intermediates, <Version>-full for the
    extract). If omitted, it is parsed from the zip file name, e.g. Q2_V1.1.0.zip -> 1.1.0.

.PARAMETER Root
    The firmware-extract folder. Defaults to this script's grandparent directory.

.EXAMPLE
    .\extract-firmware.ps1 -Zip 'C:\dl\Q2_V1.1.0.zip'

.EXAMPLE
    .\extract-firmware.ps1 -Zip '..\..\Q2_V1.1.3.zip' -Version 1.1.3

.NOTES
    Requires Windows tar.exe (bsdtar / libarchive) and Python 3 on PATH.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)] [string] $Zip,
    [string] $Version,
    [string] $Root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
)

$ErrorActionPreference = 'Stop'

# --- resolve inputs -------------------------------------------------------------
if (-not [System.IO.Path]::IsPathRooted($Zip)) {
    $Zip = Join-Path $Root $Zip
}
$Zip = (Resolve-Path $Zip).Path

if (-not $Version) {
    $zipName = [System.IO.Path]::GetFileName($Zip)
    $m = [regex]::Match($zipName, '(\d+\.\d+\.\d+)')
    if (-not $m.Success) {
        throw "Could not parse a version from '$zipName'; pass -Version explicitly."
    }
    $Version = $m.Groups[1].Value
}

$work       = Join-Path $Root $Version              # intermediates (.deb, *.tar.*)
$full       = Join-Path $Root "$Version-full"       # the extract
$controlDir = Join-Path $full 'control'
$rootfsDir  = Join-Path $full 'rootfs'
$pkgDir     = Join-Path $full 'package'

foreach ($d in @($work, $controlDir, $rootfsDir, $pkgDir)) {
    New-Item -ItemType Directory -Force -Path $d | Out-Null
}

Write-Host "firmware-extract : $Root"
Write-Host "source zip       : $Zip"
Write-Host "version          : $Version"
Write-Host ""

# --- 1. pull the SOC .deb out of the zip; copy every other member to package\ ---
Add-Type -AssemblyName System.IO.Compression.FileSystem
$archive = [System.IO.Compression.ZipFile]::OpenRead($Zip)
try {
    $soc = $archive.Entries |
        Where-Object { $_.FullName -like '*QD_Q2_SOC*' } |
        Select-Object -First 1
    if (-not $soc) {
        throw "No *QD_Q2_SOC* entry found in $Zip"
    }

    $deb = Join-Path $work 'QD_Q2_SOC.deb'
    [System.IO.Compression.ZipFileExtensions]::ExtractToFile($soc, $deb, $true)
    Write-Host "SOC blob         : $($soc.FullName)"

    foreach ($entry in $archive.Entries) {
        if ([string]::IsNullOrEmpty($entry.Name)) { continue }   # directory entry
        if ($entry.FullName -like '*QD_Q2_SOC*')  { continue }   # the .deb, handled above
        $dest = Join-Path $pkgDir $entry.Name
        [System.IO.Compression.ZipFileExtensions]::ExtractToFile($entry, $dest, $true)
    }
}
finally {
    $archive.Dispose()
}

# --- 2. split the .deb into its control.tar.* / data.tar.* members --------------
$members       = & tar.exe -tf $deb
$controlMember = $members | Where-Object { $_ -like 'control.tar.*' } | Select-Object -First 1
$dataMember    = $members | Where-Object { $_ -like 'data.tar.*' }    | Select-Object -First 1
if (-not $dataMember) {
    throw "No data.tar.* member inside $deb"
}
& tar.exe -xf $deb -C $work $controlMember $dataMember

# --- 3. extract control (metadata) and rootfs (the overlay) ---------------------
if ($controlMember) {
    & tar.exe -xf (Join-Path $work $controlMember) -C $controlDir
}

# Capture the rootfs extraction's stderr and rewrite the Windows root to '.', so the
# log reads .\firmware-extract\<ver>-full\rootfs\...  instead of an absolute path.
$logPath = Join-Path $full 'rootfs-extract.log'
$base    = Split-Path $Root -Parent     # the folder that CONTAINS firmware-extract

$prevEAP = $ErrorActionPreference
$ErrorActionPreference = 'Continue'
$stderr = & tar.exe -xf (Join-Path $work $dataMember) -C $rootfsDir 2>&1 |
    ForEach-Object { $_.ToString() }
$ErrorActionPreference = $prevEAP

$lines = @($stderr) | ForEach-Object {
    $_ -replace [regex]::Escape("\\?\$base"), '.' -replace [regex]::Escape($base), '.'
}
[System.IO.File]::WriteAllLines($logPath, [string[]]$lines)

# --- 4./5. inflate + pretty-print the embedded Klipper dictionaries (MCU blobs) --
& python (Join-Path $PSScriptRoot 'fw_dict.py') $pkgDir

# --- summary --------------------------------------------------------------------
$files = Get-ChildItem -Recurse -File $rootfsDir
$bytes = ($files | Measure-Object Length -Sum).Sum
$gb    = [math]::Round($bytes / 1GB, 2)
Write-Host ""
Write-Host ("rootfs           : {0} files, {1} GB" -f $files.Count, $gb)
Write-Host ("log              : {0}" -f $logPath)
Write-Host ("package          : {0}" -f $pkgDir)
