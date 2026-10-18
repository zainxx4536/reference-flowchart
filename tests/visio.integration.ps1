<#
.SYNOPSIS
Opt-in integration test for editable desktop Visio output.
.DESCRIPTION
Run this file explicitly on Windows with desktop Visio 2013 or later and Python
3.10 or later. It is deliberately excluded from the normal test runner. No
software is installed. Missing Visio, a noninteractive COM session, or any failed
assertion is a failure, never a skipped or simulated success.
.EXAMPLE
powershell -NoProfile -ExecutionPolicy Bypass -File tests/visio.integration.ps1 -PythonPath 'C:\Python311\python.exe'
.EXAMPLE
$env:FLOWCHART_PYTHON = 'C:\Python311\python.exe'
./tests/visio.integration.ps1
#>
[CmdletBinding()]
param([string]$PythonPath = $env:FLOWCHART_PYTHON)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)

function Assert-True([bool]$Condition, [string]$Message) {
    if (-not $Condition) { throw $Message }
}

function Release-Com($Value) {
    if ($null -ne $Value -and [Runtime.InteropServices.Marshal]::IsComObject($Value)) {
        [void][Runtime.InteropServices.Marshal]::ReleaseComObject($Value)
    }
}

function Normalize-Text([string]$Text) {
    return $Text.Replace("`r`n", "`n").TrimEnd([char[]]"`r`n")
}

function Get-Sha256([string]$FilePath) {
    $algorithm = [Security.Cryptography.SHA256]::Create()
    try { return [Convert]::ToBase64String($algorithm.ComputeHash([IO.File]::ReadAllBytes($FilePath))) }
    finally { $algorithm.Dispose() }
}

function Invoke-Exporter([switch]$Overwrite) {
    # A child process keeps the exporter's documented exit code from terminating
    # this test, and lets the refusal-to-overwrite case be inspected normally.
    $quote = { param([string]$Value) "'" + $Value.Replace("'", "''") + "'" }
    $command = '$ProgressPreference = ''SilentlyContinue''; & ' + (& $quote $exportScript) +
        ' -LayoutPath ' + (& $quote $layoutPath) +
        ' -OutputPath ' + (& $quote $outputPath) +
        ' -PythonPath ' + (& $quote $PythonPath)
    if ($Overwrite) { $command += ' -Overwrite' }
    $encoded = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($command))
    $start = New-Object Diagnostics.ProcessStartInfo
    $start.FileName = $hostExecutable
    $start.Arguments = '-NoProfile -NonInteractive -ExecutionPolicy Bypass -OutputFormat Text -EncodedCommand ' + $encoded
    $start.UseShellExecute = $false
    $start.CreateNoWindow = $true
    $start.RedirectStandardOutput = $true
    $start.RedirectStandardError = $true
    $start.StandardOutputEncoding = New-Object Text.UTF8Encoding($false)
    $start.StandardErrorEncoding = New-Object Text.UTF8Encoding($false)
    $process = New-Object Diagnostics.Process
    $process.StartInfo = $start
    try {
        [void]$process.Start()
        $stdout = $process.StandardOutput.ReadToEndAsync()
        $stderr = $process.StandardError.ReadToEndAsync()
        $process.WaitForExit()
        return [pscustomobject]@{
            ExitCode = $process.ExitCode
            Stdout = $stdout.Result
            Stderr = $stderr.Result
        }
    } finally { $process.Dispose() }
}

function Get-GlueTargets($Shape) {
    $result = @{}
    $connections = $null
    try {
        $connections = $Shape.Connects
        Assert-True ($connections.Count -eq 2) ('Expected two glue connections on ' + $Shape.NameU)
        for ($index = 1; $index -le $connections.Count; $index++) {
            $connection = $null; $fromCell = $null; $toShape = $null
            try {
                $connection = $connections.Item($index)
                $fromCell = $connection.FromCell
                $toShape = $connection.ToSheet
                $result[[string]$fromCell.NameU] = [string]$toShape.NameU
            } finally {
                Release-Com $toShape
                Release-Com $fromCell
                Release-Com $connection
            }
        }
    } finally { Release-Com $connections }
    return $result
}

function Assert-NativeDrawing($Page, $Layout) {
    Assert-True ($Page.Connects.Count -eq (2 * $Layout.edges.Count)) 'Page Connects lost an edge endpoint.'
    foreach ($expected in $Layout.nodes) {
        $shape = $null
        try {
            $shape = $Page.Shapes.ItemU('node-' + $expected.id)
            Assert-True ([int]$shape.Type -eq 3) ('Expected a native Visio shape for ' + $expected.id)
            Assert-True ([int]$shape.OneD -eq 0) ('Expected a 2D node for ' + $expected.id)
            $actualText = Normalize-Text ([string]$shape.Text)
            Assert-True ($actualText -ceq ($expected.lines -join "`n")) ('Native Chinese text did not survive for ' + $expected.id)
        } finally { Release-Com $shape }
    }
    foreach ($expected in $Layout.edges) {
        $shape = $null
        try {
            $shape = $Page.Shapes.ItemU('edge-' + $expected.id)
            Assert-True ([int]$shape.Type -eq 3) ('Expected a native Visio connector for ' + $expected.id)
            Assert-True ([int]$shape.OneD -ne 0) ('Expected a 1D connector for ' + $expected.id)
            $targets = Get-GlueTargets $shape
            Assert-True ($targets.ContainsKey('BeginX') -and $targets['BeginX'] -ceq ('node-' + $expected.from)) ('BeginX is not glued to the source of ' + $expected.id)
            Assert-True ($targets.ContainsKey('EndX') -and $targets['EndX'] -ceq ('node-' + $expected.to)) ('EndX is not glued to the destination of ' + $expected.id)
        } finally { Release-Com $shape }
    }
}

function Read-Cell($Shape, [string]$CellName) {
    $cell = $null
    try { $cell = $Shape.CellsU($CellName); return [double]$cell.ResultIU }
    finally { Release-Com $cell }
}

function Write-Cell($Shape, [string]$CellName, [double]$Value) {
    $cell = $null
    try { $cell = $Shape.CellsU($CellName); $cell.ResultIU = $Value }
    finally { Release-Com $cell }
}

function Assert-Near([double]$Actual, [double]$Expected, [string]$Message) {
    Assert-True (-not [double]::IsNaN($Actual) -and -not [double]::IsInfinity($Actual) -and [Math]::Abs($Actual - $Expected) -lt 0.00001) $Message
}

function Assert-MovedEndpoints($Page, $Before, [double]$DeltaX, [double]$DeltaY) {
    foreach ($item in @(@('edge-start-process', 'End'), @('edge-process-decision', 'Begin'))) {
        $edge = $null
        try {
            $edge = $Page.Shapes.ItemU($item[0])
            foreach ($axis in @('X', 'Y')) {
                $key = $item[0] + ':' + $item[1] + $axis
                $delta = $DeltaY
                if ($axis -eq 'X') { $delta = $DeltaX }
                Assert-Near (Read-Cell $edge ($item[1] + $axis)) ($Before[$key] + $delta) ('Glued endpoint did not follow the moved node: ' + $key)
            }
        } finally { Release-Com $edge }
    }
}

$testRoot = $null; $visio = $null; $document = $null; $page = $null
try {
    Assert-True ([Environment]::OSVersion.Platform -eq [PlatformID]::Win32NT) 'This integration test requires Windows desktop Visio; it cannot pass on another platform.'
    Assert-True (-not [string]::IsNullOrWhiteSpace($PythonPath)) 'Pass -PythonPath PATH or set FLOWCHART_PYTHON to a Python 3.10+ executable. This test does not install dependencies.'
    $repoRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
    $exportScript = Join-Path $repoRoot 'scripts/export_visio.ps1'
    Assert-True (Test-Path -LiteralPath $exportScript -PathType Leaf) ('Missing exporter: ' + $exportScript)
    $hostExecutable = Join-Path $PSHOME 'powershell.exe'
    if (-not (Test-Path -LiteralPath $hostExecutable -PathType Leaf)) { $hostExecutable = Join-Path $PSHOME 'pwsh.exe' }
    Assert-True (Test-Path -LiteralPath $hostExecutable -PathType Leaf) 'Could not locate this PowerShell host executable.'
    $tempParent = [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd([char[]]'\/')
    $testName = 'reference-flowchart Visio 中文 ' + [Guid]::NewGuid().ToString('N')
    $testRoot = Join-Path $tempParent $testName
    [void][IO.Directory]::CreateDirectory($testRoot)
    $layoutPath = Join-Path $testRoot '输入 layout 中文.json'
    $outputPath = Join-Path $testRoot '可编辑 flow chart.vsdx'
    $movedPath = Join-Path $testRoot '移动和编辑后 drawing.vsdx'
    $layout = [ordered]@{
        canvas = [ordered]@{ width = 800; height = 850; title = '中文流程图'; font_family = 'Microsoft YaHei' }
        nodes = @(
            [ordered]@{ id = 'start'; x = 100; y = 80; width = 200; height = 70; shape = 'terminator'; lines = @('开始 / Start') },
            [ordered]@{ id = 'process'; x = 100; y = 230; width = 200; height = 80; shape = 'rect'; lines = @('处理 <中文> & 审核') },
            [ordered]@{ id = 'decision'; x = 100; y = 390; width = 200; height = 120; shape = 'diamond'; lines = @('是否通过？') },
            [ordered]@{ id = 'store'; x = 100; y = 590; width = 200; height = 100; shape = 'cylinder'; lines = @('存储结果', '可编辑文本') }
        )
        edges = @(
            [ordered]@{ id = 'start-process'; from = 'start'; to = 'process'; points = @(@(200, 150), @(200, 230)); arrow = $true },
            [ordered]@{ id = 'process-decision'; from = 'process'; to = 'decision'; points = @(@(200, 310), @(200, 390)); arrow = $true },
            [ordered]@{ id = 'decision-store'; from = 'decision'; to = 'store'; points = @(@(200, 510), @(200, 590)); arrow = $true }
        )
    }
    $utf8 = New-Object Text.UTF8Encoding($false)
    [IO.File]::WriteAllText($layoutPath, ($layout | ConvertTo-Json -Depth 12), $utf8)
    $result = Invoke-Exporter
    Assert-True ($result.ExitCode -eq 0) ('Initial Visio export failed. Desktop Visio must be available in this Windows session. ' + $result.Stderr + $result.Stdout)
    Assert-True ((Test-Path -LiteralPath $outputPath -PathType Leaf) -and (Get-Item -LiteralPath $outputPath).Length -gt 0) 'Exporter did not create a nonempty VSDX.'
    $originalHash = Get-Sha256 $outputPath
    try { $visio = New-Object -ComObject Visio.InvisibleApp }
    catch { throw ('Cannot start desktop Visio for native integration checks. This is a test failure, not a skip. ' + $_.Exception.Message) }
    $visio.AlertResponse = 7
    $visio.EventsEnabled = $false
    Assert-True ([double]::Parse($visio.Version, [Globalization.CultureInfo]::InvariantCulture) -ge 15) 'Visio 2013 or later is required.'
    $document = $visio.Documents.OpenEx($outputPath, [int16]200)
    $page = $document.Pages.Item(1)
    Assert-NativeDrawing $page $layout
    $before = @{}
    foreach ($item in @(@('edge-start-process', 'End'), @('edge-process-decision', 'Begin'))) {
        $edge = $null
        try {
            $edge = $page.Shapes.ItemU($item[0])
            foreach ($axis in @('X', 'Y')) { $before[$item[0] + ':' + $item[1] + $axis] = Read-Cell $edge ($item[1] + $axis) }
        } finally { Release-Com $edge }
    }
    $node = $null
    try {
        $node = $page.Shapes.ItemU('node-process')
        Write-Cell $node 'PinX' ((Read-Cell $node 'PinX') + 0.5)
        Write-Cell $node 'PinY' ((Read-Cell $node 'PinY') + 0.25)
        $node.Text = '中文流程：已在 Visio 编辑'
        $layout.nodes[1].lines = @('中文流程：已在 Visio 编辑')
    } finally { Release-Com $node }
    Assert-MovedEndpoints $page $before 0.5 0.25
    $document.SaveAs($movedPath)
    Release-Com $page; $page = $null
    $document.Close(); Release-Com $document; $document = $null
    $document = $visio.Documents.OpenEx($movedPath, [int16]200)
    $page = $document.Pages.Item(1)
    Assert-NativeDrawing $page $layout
    Assert-MovedEndpoints $page $before 0.5 0.25
    Release-Com $page; $page = $null
    $document.Close(); Release-Com $document; $document = $null

    $refused = Invoke-Exporter
    Assert-True ($refused.ExitCode -ne 0) 'Exporter unexpectedly overwrote an existing VSDX without -Overwrite.'
    Assert-True (($refused.Stderr + $refused.Stdout) -match 'already exists') 'Exporter failed for a reason other than refusing to overwrite.'
    Assert-True ((Get-Sha256 $outputPath) -ceq $originalHash) 'Refused export changed the existing VSDX.'
    $layout.nodes[1].lines = @('覆盖成功：新的中文文本')
    [IO.File]::WriteAllText($layoutPath, ($layout | ConvertTo-Json -Depth 12), $utf8)
    $replaced = Invoke-Exporter -Overwrite
    Assert-True ($replaced.ExitCode -eq 0) ('Explicit -Overwrite export failed. ' + $replaced.Stderr + $replaced.Stdout)
    $document = $visio.Documents.OpenEx($outputPath, [int16]200)
    $page = $document.Pages.Item(1)
    Assert-NativeDrawing $page $layout
} catch {
    [Console]::Error.WriteLine('FAIL: ' + $_.Exception.Message)
    exit 1
} finally {
    Release-Com $page
    if ($document) {
        try { $document.Saved = $true; $document.Close() } catch { }
        Release-Com $document
    }
    if ($visio) {
        try { $visio.Quit() } catch { }
        Release-Com $visio
    }
    if ($testRoot -and (Test-Path -LiteralPath $testRoot -PathType Container)) {
        # Verify the absolute generated target before removing our temporary tree.
        $resolvedTestRoot = [IO.Path]::GetFullPath($testRoot)
        $resolvedParent = [IO.Path]::GetDirectoryName($resolvedTestRoot)
        $safeName = [IO.Path]::GetFileName($resolvedTestRoot) -ceq $testName
        if ($safeName -and $resolvedParent.Equals($tempParent, [StringComparison]::OrdinalIgnoreCase)) {
            Remove-Item -LiteralPath $resolvedTestRoot -Recurse -Force
        } else { Write-Warning ('Refusing to remove unexpected temporary path: ' + $resolvedTestRoot) }
    }
}
Write-Output 'PASS: desktop Visio reopened native Chinese shapes and glued 1D connectors; movement, text editing, save/reopen, Unicode paths and overwrite checks passed.'
