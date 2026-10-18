<#
.SYNOPSIS
Create an editable .vsdx with desktop Visio from a flowchart JSON specification.
.DESCRIPTION
Python validates/resolves the layout and prepares native geometry and text.
A new invisible Visio instance creates native objects and saves a real .vsdx. Existing
Visio windows are never attached to. Requires Windows, Python >= 3.10 and Visio >= 2013.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$LayoutPath,
    [Parameter(Mandatory = $true)][string]$OutputPath,
    [string]$PythonPath,
    [string]$PreviewPath,
    [switch]$Overwrite
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)

function Find-Python {
    $selected = $PythonPath
    if (-not $selected) { $selected = $env:FLOWCHART_PYTHON }
    $candidates = @()
    if ($selected) { $candidates += @{ Command = $selected; Prefix = @() } }
    else {
        $candidates += @{ Command = 'python3'; Prefix = @() }
        $candidates += @{ Command = 'python'; Prefix = @() }
        $candidates += @{ Command = 'py'; Prefix = @('-3') }
    }
    foreach ($candidate in $candidates) {
        try {
            $command = $candidate.Command
            $prefix = $candidate.Prefix
            $version = & $command @prefix --version 2>$null
            if ($LASTEXITCODE -eq 0 -and "$version" -match '^Python 3[.]([0-9]+)[.]' -and [int]$Matches[1] -ge 10) { return $candidate }
        } catch { }
    }
    throw 'Python >= 3.10 not found. Pass -PythonPath PATH or set FLOWCHART_PYTHON.'
}

function Check-Target([string]$Path, [string]$Extension) {
    $full = [IO.Path]::GetFullPath($Path)
    if ([IO.Path]::GetExtension($full) -ine $Extension) { throw "Output must use the $Extension extension: $full" }
    if (Test-Path -LiteralPath $full) {
        if (-not (Test-Path -LiteralPath $full -PathType Leaf)) { throw "Output is not a file: $full" }
        if (-not $Overwrite) { throw "Output already exists. Choose another path or pass -Overwrite: $full" }
    }
    return $full
}

$visio = $null
$document = $null
$page = $null
$scratch = $null
try {
    if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) { throw 'VSDX export requires Windows desktop Visio. The Python VDX exporter is available on other platforms.' }
    $inputFile = (Resolve-Path -LiteralPath $LayoutPath).ProviderPath
    $outputFile = Check-Target $OutputPath '.vsdx'
    $previewFile = $null
    if ($PreviewPath) { $previewFile = Check-Target $PreviewPath '.png' }
    $python = Find-Python
    $parent = [IO.Path]::GetDirectoryName($outputFile)
    [void][IO.Directory]::CreateDirectory($parent)
    # Keep Office's working files in the current user's local temporary folder.
    # Publish the VSDX to the requested output path only after saved-package checks.
    $scratch = Join-Path ([IO.Path]::GetTempPath()) ('.flowchart-visio-' + [Guid]::NewGuid().ToString('N'))
    [void][IO.Directory]::CreateDirectory($scratch)
    $vdx = Join-Path $scratch 'drawing.vdx'
    $vsdx = Join-Path $scratch 'drawing.vsdx'
    $png = Join-Path $scratch 'preview.png'
    $command = $python.Command
    $prefix = $python.Prefix
    $result = & $command @prefix -X utf8 (Join-Path $PSScriptRoot 'export_visio.py') $inputFile --output $vdx
    if ($LASTEXITCODE -ne 0) { throw 'Invalid flowchart input or VDX generation failed. No VSDX was written.' }
    try { $visio = New-Object -ComObject Visio.InvisibleApp }
    catch { throw ('Desktop Visio could not start in this session. Install/activate Visio 2013 or later and run from an interactive Windows session. No PNG fallback was performed. Details: ' + $_.Exception.Message) }
    $visio.AlertResponse = 7 # Decline link updates and other Yes/No prompts in our own instance.
    $visio.EventsEnabled = $false
    if ([double]::Parse($visio.Version, [Globalization.CultureInfo]::InvariantCulture) -lt 15) { throw 'VSDX export requires Visio 2013 (version 15) or later.' }
    . (Join-Path $PSScriptRoot 'visio_native.ps1')
    Write-Verbose 'Creating native Visio objects'
    $document = New-NativeVisioDocument -Application $visio -VdxPath $vdx
    Write-Verbose 'Saving native VSDX'
    [void]$document.SaveAs($vsdx)
    $page = $document.Pages.Item(1)
    $shapeCount = $page.Shapes.Count
    $connectionCount = $page.Connects.Count
    if ($shapeCount -lt 1) { throw 'Visio created an empty drawing.' }
    if ($previewFile) { Write-Verbose 'Exporting Visio PNG preview'; [void]$page.Export($png) }
    [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($page)
    $page = $null
    $document.Saved = $true
    [void]$document.Close()
    [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($document)
    $document = $null
    # Verify the actual saved package without a second Office open operation.
    # Desktop reopening/editing is exercised by the opt-in integration test.
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $archive = [IO.Compression.ZipFile]::OpenRead($vsdx)
    try {
        if ($null -eq $archive.GetEntry('visio/document.xml') -or $null -eq $archive.GetEntry('visio/pages/page1.xml')) { throw 'Visio did not save a valid VSDX package.' }
        $entryReader = New-Object IO.StreamReader($archive.GetEntry('visio/pages/page1.xml').Open())
        try { [xml]$savedPage = $entryReader.ReadToEnd() } finally { $entryReader.Dispose() }
        $savedShapes = $savedPage.SelectNodes("//*[local-name()='Shape' and @Type='Shape']")
        if ($savedShapes.Count -ne $shapeCount) { throw 'Saved package shape count does not match the native drawing.' }
        if ($savedPage.SelectNodes("//*[local-name()='Section' and @N='Geometry']/*[local-name()='Row' and @IX='0']").Count -gt 0) { throw 'Saved geometry is missing the native component header.' }
        if ($savedPage.SelectNodes("//*[local-name()='ForeignData']").Count -gt 0) { throw 'Saved drawing unexpectedly contains flattened image data.' }
    } finally { $archive.Dispose() }
    if (-not (Test-Path -LiteralPath $vsdx -PathType Leaf) -or (Get-Item -LiteralPath $vsdx).Length -eq 0) { throw 'Visio did not create a nonempty VSDX file.' }
    # Publish only after native generation and saved-package checks succeed. Recheck no-clobber
    # targets in case another process created them while Visio was working.
    [void](Check-Target $outputFile '.vsdx')
    if ($previewFile) {
        [void](Check-Target $previewFile '.png')
        [void][IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($previewFile))
        [IO.File]::Copy($png, $previewFile, [bool]$Overwrite)
    }
    [IO.File]::Copy($vsdx, $outputFile, [bool]$Overwrite)
    [ordered]@{ status = 'visio-exported'; vsdx = $outputFile; preview = $previewFile; shapes = $shapeCount; connections = $connectionCount; visioVersion = $visio.Version; packageChecked = $true; reopenVerified = $false } | ConvertTo-Json -Compress
} catch {
    [Console]::Error.WriteLine('Error: ' + $_.Exception.Message)
    exit 1
} finally {
    if ($page) { [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($page) }
    if ($document) {
        try { $document.Saved = $true; $document.Close() } catch { }
        [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($document)
    }
    if ($visio) {
        try { $visio.Quit() } catch { }
        [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($visio)
    }
    if ($scratch) {
        # Only remove named files in our own unique temporary directory.
        foreach ($name in @('drawing.vdx', 'drawing.vsdx', 'preview.png')) {
            $tempFile = Join-Path $scratch $name
            if (Test-Path -LiteralPath $tempFile -PathType Leaf) { Remove-Item -LiteralPath $tempFile -Force }
        }
        if (Test-Path -LiteralPath $scratch -PathType Container) { Remove-Item -LiteralPath $scratch }
    }
}
