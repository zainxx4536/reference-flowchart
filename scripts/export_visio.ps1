<#
.SYNOPSIS
Create an editable .vsdx with desktop Visio from a flowchart JSON specification.
.DESCRIPTION
Python validates/resolves the layout and writes native VDX shapes and connectors.
A new invisible Visio instance opens that drawing and saves a real .vsdx. Existing
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
    $scratch = Join-Path $parent ('.flowchart-visio-' + [Guid]::NewGuid().ToString('N'))
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
    $visio.AlertResponse = 7 # No: never accept repair/conversion prompts silently.
    $visio.EventsEnabled = $false
    if ([double]::Parse($visio.Version, [Globalization.CultureInfo]::InvariantCulture) -lt 15) { throw 'VSDX export requires Visio 2013 (version 15) or later.' }
    # visOpenHidden (64) | visOpenDontList (8) | visOpenMacrosDisabled (128).
    $document = $visio.Documents.OpenEx($vdx, [int16]200)
    $document.SaveAs($vsdx)
    $document.Close()
    [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($document)
    $document = $null
    # Reopen the saved result: a successful SaveAs alone does not prove it is usable.
    $document = $visio.Documents.OpenEx($vsdx, [int16]200)
    $page = $document.Pages.Item(1)
    $shapeCount = $page.Shapes.Count
    $connectionCount = $page.Connects.Count
    if ($shapeCount -lt 1) { throw 'Visio reopened an empty drawing.' }
    if ($previewFile) { $page.Export($png) }
    [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($page)
    $page = $null
    $document.Saved = $true
    $document.Close()
    [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($document)
    $document = $null
    if (-not (Test-Path -LiteralPath $vsdx -PathType Leaf) -or (Get-Item -LiteralPath $vsdx).Length -eq 0) { throw 'Visio did not create a nonempty VSDX file.' }
    # Publish only after generation and reopen checks succeed. Recheck no-clobber
    # targets in case another process created them while Visio was working.
    [void](Check-Target $outputFile '.vsdx')
    if ($previewFile) {
        [void](Check-Target $previewFile '.png')
        [void][IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($previewFile))
        [IO.File]::Copy($png, $previewFile, [bool]$Overwrite)
    }
    [IO.File]::Copy($vsdx, $outputFile, [bool]$Overwrite)
    [ordered]@{ status = 'visio-exported'; vsdx = $outputFile; preview = $previewFile; shapes = $shapeCount; connections = $connectionCount; visioVersion = $visio.Version } | ConvertTo-Json -Compress
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
