# Native Visio renderer for the private VDX drawing plan produced by export_visio.py.
# This never passes VDX to Visio's legacy XML importer. Requires desktop Visio COM.
Set-StrictMode -Version Latest

function Release-FlowchartCom {
    param($Value)
    if ($null -ne $Value -and [Runtime.InteropServices.Marshal]::IsComObject($Value)) {
        [void][Runtime.InteropServices.Marshal]::ReleaseComObject($Value)
    }
}

function Set-FlowchartResult {
    param($Cell, [double]$Value)
    try { $Cell.ResultIU = $Value }
    finally { Release-FlowchartCom $Cell }
}

function Set-FlowchartFormula {
    param($Cell, [string]$Formula)
    try { $Cell.FormulaU = $Formula }
    finally { Release-FlowchartCom $Cell }
}

function Get-FlowchartNumber {
    param([string]$Value)
    return [double]::Parse($Value, [Globalization.CultureInfo]::InvariantCulture)
}

function Set-FlowchartCell {
    param($Cell, [System.Xml.XmlElement]$XmlCell, [hashtable]$ShapeIds)
    try {
    if ($XmlCell.HasAttribute('F')) {
        $taskFormula = $XmlCell.GetAttribute('F')
        $taskFormula = [regex]::Replace($taskFormula, 'Sheet\.(\d+)!', {
            param($taskMatch)
            $taskOldId = $taskMatch.Groups[1].Value
            if (-not $ShapeIds.ContainsKey($taskOldId)) { throw "Unknown drawing-plan shape ID: $taskOldId" }
            return 'Sheet.' + $ShapeIds[$taskOldId] + '!'
        })
        $Cell.FormulaU = $taskFormula
    } elseif ($XmlCell.InnerText -match '^#([0-9a-fA-F]{6})$') {
        $taskHex = $Matches[1]
        $Cell.FormulaU = 'RGB(' + [Convert]::ToInt32($taskHex.Substring(0,2),16) + ',' +
            [Convert]::ToInt32($taskHex.Substring(2,2),16) + ',' + [Convert]::ToInt32($taskHex.Substring(4,2),16) + ')'
    } else {
        $Cell.ResultIU = Get-FlowchartNumber $XmlCell.InnerText
    }
    } finally { Release-FlowchartCom $Cell }
}

function Set-FlowchartShapeCells {
    param($Shape, [System.Xml.XmlElement]$XmlShape, [System.Xml.XmlNamespaceManager]$Namespace, [hashtable]$ShapeIds, [switch]$SkipTransform)
    foreach ($taskSectionName in @('XForm', 'Line', 'Fill', 'TextBlock')) {
        if ($SkipTransform -and $taskSectionName -eq 'XForm') { continue }
        $taskSection = $XmlShape.SelectSingleNode('v:' + $taskSectionName, $Namespace)
        if ($null -eq $taskSection) { continue }
        foreach ($taskCell in $taskSection.ChildNodes) {
            if ($taskCell -isnot [System.Xml.XmlElement]) { continue }
            Set-FlowchartCell $Shape.CellsU($taskCell.LocalName) $taskCell $ShapeIds
        }
    }
}

function Set-FlowchartGeometry {
    param($Shape, [System.Xml.XmlElement]$XmlShape, [System.Xml.XmlNamespaceManager]$Namespace, [hashtable]$ShapeIds)
    # Remove the skeleton's geometry before creating native ShapeSheet rows.
    $taskGeometryCount = [int]$Shape.GeometryCount
    for ($taskSectionIndex = 10 + $taskGeometryCount - 1; $taskSectionIndex -ge 10; $taskSectionIndex--) {
        [void]$Shape.DeleteSection([int16]$taskSectionIndex)
    }
    $taskTags = @{ MoveTo=138; LineTo=139; Ellipse=143; EllipticalArcTo=144 }
    $taskColumns = @{ X=0; Y=1; A=2; B=3; C=4; D=5 }
    $taskFlags = @{ NoFill=0; NoLine=1; NoShow=2; NoSnap=3 }
    foreach ($taskGeometry in $XmlShape.SelectNodes('v:Geom', $Namespace)) {
        $taskSectionIndex = 10 + [int]$taskGeometry.GetAttribute('IX')
        [void]$Shape.AddSection([int16]$taskSectionIndex)
        # Geometry row 0 is the component header; vertices start at row 1.
        [void]$Shape.AddRow([int16]$taskSectionIndex, 0, 137)
        foreach ($taskRow in $taskGeometry.ChildNodes) {
            if ($taskRow -isnot [System.Xml.XmlElement]) { continue }
            if ($taskFlags.ContainsKey($taskRow.LocalName)) {
                Set-FlowchartCell $Shape.CellsSRC([int16]$taskSectionIndex, 0, [int16]$taskFlags[$taskRow.LocalName]) $taskRow $ShapeIds
                continue
            }
            if (-not $taskTags.ContainsKey($taskRow.LocalName)) { throw "Unsupported drawing-plan geometry: $($taskRow.LocalName)" }
            $taskActualRow = [int]$Shape.AddRow([int16]$taskSectionIndex, -1, [int16]$taskTags[$taskRow.LocalName])
            foreach ($taskCell in $taskRow.ChildNodes) {
                if ($taskCell -isnot [System.Xml.XmlElement]) { continue }
                Set-FlowchartCell $Shape.CellsSRC([int16]$taskSectionIndex, [int16]$taskActualRow, [int16]$taskColumns[$taskCell.LocalName]) $taskCell $ShapeIds
            }
        }
    }
}

function Set-FlowchartText {
    param($Shape, [System.Xml.XmlElement]$XmlShape, [System.Xml.XmlNamespaceManager]$Namespace, [string]$FontName, [hashtable]$ShapeIds)
    $taskText = $XmlShape.SelectSingleNode('v:Text', $Namespace)
    if ($null -eq $taskText) { return }
    $Shape.Text = $taskText.InnerText
    $taskDefaultChar = $XmlShape.SelectSingleNode('v:Char[@IX="0"]', $Namespace)
    if ($null -ne $taskDefaultChar) {
        foreach ($taskCell in $taskDefaultChar.ChildNodes) {
            if ($taskCell -isnot [System.Xml.XmlElement]) { continue }
            if ($taskCell.LocalName -in @('Font', 'AsianFont')) { continue }
            Set-FlowchartCell $Shape.CellsU('Char.' + $taskCell.LocalName) $taskCell $ShapeIds
        }
    }
    # Font indices in the drawing plan are private to its FaceNames table.
    # Resolve the requested family by name in the document's own font table.
    $taskQuotedFont = $FontName.Replace('"', '""')
    $taskFontCell = $Shape.CellsU('Char.Font')
    try {
        $taskFontCell.FormulaU = 'FONT("' + $taskQuotedFont + '")'
        $taskFontId = [double]$taskFontCell.ResultIU
        # Store the resolved document font rather than re-evaluating FONT on reopen.
        $taskFontCell.ResultIU = $taskFontId
    } finally { Release-FlowchartCom $taskFontCell }
    Set-FlowchartResult $Shape.CellsU('Char.AsianFont') $taskFontId
    foreach ($taskParagraph in $XmlShape.SelectNodes('v:Para', $Namespace)) {
        foreach ($taskCell in $taskParagraph.ChildNodes) {
            if ($taskCell -isnot [System.Xml.XmlElement]) { continue }
            Set-FlowchartCell $Shape.CellsU('Para.' + $taskCell.LocalName) $taskCell $ShapeIds
        }
    }
    # Preserve mixed-content character runs, including line breaks on cp tails.
    $taskOffset = 0
    $taskCharIndex = '0'
    foreach ($taskPart in $taskText.ChildNodes) {
        if ($taskPart -is [System.Xml.XmlElement]) {
            if ($taskPart.LocalName -eq 'cp') { $taskCharIndex = $taskPart.GetAttribute('IX') }
            continue
        }
        $taskContent = $taskPart.Value
        if ([string]::IsNullOrEmpty($taskContent)) { continue }
        $taskChar = $XmlShape.SelectSingleNode('v:Char[@IX="' + $taskCharIndex + '"]', $Namespace)
        $taskStyle = 0
        $taskPosition = 0
        if ($null -ne $taskChar) {
            $taskStyleCell = $taskChar.SelectSingleNode('v:Style', $Namespace)
            $taskPositionCell = $taskChar.SelectSingleNode('v:Pos', $Namespace)
            if ($null -ne $taskStyleCell) { $taskStyle = [int]$taskStyleCell.InnerText }
            if ($null -ne $taskPositionCell) { $taskPosition = [int]$taskPositionCell.InnerText }
        }
        $taskCharacters = $Shape.Characters
        try {
            $taskCharacters.Begin = $taskOffset
            $taskCharacters.End = $taskOffset + $taskContent.Length
            [void]$taskCharacters.GetType().InvokeMember("CharProps", [Reflection.BindingFlags]::SetProperty, $null, $taskCharacters, @([int16]2, [int16]$taskStyle))
            [void]$taskCharacters.GetType().InvokeMember("CharProps", [Reflection.BindingFlags]::SetProperty, $null, $taskCharacters, @([int16]4, [int16]$taskPosition))
        } finally {
            Release-FlowchartCom $taskCharacters
        }
        $taskOffset += $taskContent.Length
    }
}

function New-NativeVisioDocument {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory=$true)]$Application,
        [Parameter(Mandatory=$true)][string]$VdxPath
    )
    $taskReaderSettings = New-Object System.Xml.XmlReaderSettings
    $taskReaderSettings.DtdProcessing = [System.Xml.DtdProcessing]::Prohibit
    $taskReaderSettings.XmlResolver = $null
    $taskPlan = New-Object System.Xml.XmlDocument
    $taskPlan.PreserveWhitespace = $true
    $taskPlan.XmlResolver = $null
    $taskReader = [System.Xml.XmlReader]::Create([IO.Path]::GetFullPath($VdxPath), $taskReaderSettings)
    try { $taskPlan.Load($taskReader) } finally { $taskReader.Dispose() }
    $taskNamespace = New-Object System.Xml.XmlNamespaceManager($taskPlan.NameTable)
    $taskNamespace.AddNamespace('v', 'http://schemas.microsoft.com/visio/2003/core')
    $taskPagePlan = $taskPlan.SelectSingleNode('/v:VisioDocument/v:Pages/v:Page', $taskNamespace)
    if ($null -eq $taskPagePlan) { throw 'The drawing plan does not contain a flowchart page.' }
    $taskFont = $taskPlan.SelectSingleNode('/v:VisioDocument/v:FaceNames/v:FaceName', $taskNamespace)
    $taskFontName = 'SimSun'
    if ($null -ne $taskFont) { $taskFontName = $taskFont.GetAttribute('Name') }
    $taskDocument = $null
    $taskDocuments = $null
    $taskPages = $null
    $taskPage = $null
    $taskPageSheet = $null
    $taskShapes = @{}
    $taskShapeIds = @{}
    $taskSucceeded = $false
    try {
        $taskDocuments = $Application.Documents
        $taskDocument = $taskDocuments.Add('')
        $taskPages = $taskDocument.Pages
        $taskPage = $taskPages.Item(1)
        $taskPageSheet = $taskPage.PageSheet
        $taskPage.NameU = 'Flowchart'
        foreach ($taskCell in $taskPagePlan.SelectNodes('v:PageSheet/v:PageProps/*', $taskNamespace)) {
            Set-FlowchartCell $taskPageSheet.CellsU($taskCell.LocalName) $taskCell $taskShapeIds
        }
        $taskShapePlans = @($taskPagePlan.SelectNodes('v:Shapes/v:Shape', $taskNamespace))
        # Create every native shape before assigning cross-shape formulas.
        foreach ($taskShapePlan in $taskShapePlans) {
            $taskOriginalId = $taskShapePlan.GetAttribute('ID')
            $taskEndpoints = $taskShapePlan.SelectSingleNode('v:XForm1D', $taskNamespace)
            if ($null -ne $taskEndpoints) {
                # Restore the plan's cached local coordinates to page inches,
                # then let Visio construct its own complete native 1D object.
                $taskTransform = $taskShapePlan.SelectSingleNode('v:XForm', $taskNamespace)
                $taskPinX = Get-FlowchartNumber $taskTransform.SelectSingleNode('v:PinX', $taskNamespace).InnerText
                $taskPinY = Get-FlowchartNumber $taskTransform.SelectSingleNode('v:PinY', $taskNamespace).InnerText
                $taskLocPinX = Get-FlowchartNumber $taskTransform.SelectSingleNode('v:LocPinX', $taskNamespace).InnerText
                $taskLocPinY = Get-FlowchartNumber $taskTransform.SelectSingleNode('v:LocPinY', $taskNamespace).InnerText
                $taskAngle = Get-FlowchartNumber $taskTransform.SelectSingleNode('v:Angle', $taskNamespace).InnerText
                $taskCos = [Math]::Cos($taskAngle)
                $taskSin = [Math]::Sin($taskAngle)
                [double[]]$taskPolylinePoints = @()
                foreach ($taskVertex in $taskShapePlan.SelectNodes('v:Geom/v:MoveTo | v:Geom/v:LineTo', $taskNamespace)) {
                    $taskLocalX = (Get-FlowchartNumber $taskVertex.SelectSingleNode('v:X', $taskNamespace).InnerText) - $taskLocPinX
                    $taskLocalY = (Get-FlowchartNumber $taskVertex.SelectSingleNode('v:Y', $taskNamespace).InnerText) - $taskLocPinY
                    $taskPolylinePoints += $taskPinX + $taskLocalX*$taskCos - $taskLocalY*$taskSin
                    $taskPolylinePoints += $taskPinY + $taskLocalX*$taskSin + $taskLocalY*$taskCos
                }
                if ($taskPolylinePoints.Length -lt 4) { throw 'A native connector needs at least two points.' }
                $taskShape = $taskPage.DrawPolyline([ref]$taskPolylinePoints, 8)
            } else {
                $taskTransform = $taskShapePlan.SelectSingleNode('v:XForm', $taskNamespace)
                $taskPinX = Get-FlowchartNumber $taskTransform.SelectSingleNode('v:PinX', $taskNamespace).InnerText
                $taskPinY = Get-FlowchartNumber $taskTransform.SelectSingleNode('v:PinY', $taskNamespace).InnerText
                $taskWidth = Get-FlowchartNumber $taskTransform.SelectSingleNode('v:Width', $taskNamespace).InnerText
                $taskHeight = Get-FlowchartNumber $taskTransform.SelectSingleNode('v:Height', $taskNamespace).InnerText
                $taskShape = $taskPage.DrawRectangle($taskPinX-$taskWidth/2, $taskPinY-$taskHeight/2,
                                                     $taskPinX+$taskWidth/2, $taskPinY+$taskHeight/2)
            }
            $taskShapes[$taskOriginalId] = $taskShape
            $taskShape.NameU = $taskShapePlan.GetAttribute('NameU')
            $taskShapeIds[$taskOriginalId] = [int]$taskShape.ID
        }
        foreach ($taskShapePlan in $taskShapePlans) {
            $taskOriginalId = $taskShapePlan.GetAttribute('ID')
            $taskShape = $taskShapes[$taskOriginalId]
            $taskIsConnector = $null -ne $taskShapePlan.SelectSingleNode('v:XForm1D', $taskNamespace)
            Set-FlowchartShapeCells $taskShape $taskShapePlan $taskNamespace $taskShapeIds -SkipTransform:$taskIsConnector
            if (-not $taskIsConnector) { Set-FlowchartGeometry $taskShape $taskShapePlan $taskNamespace $taskShapeIds }
            Set-FlowchartText $taskShape $taskShapePlan $taskNamespace $taskFontName $taskShapeIds
            $taskData = $taskShapePlan.SelectSingleNode('v:Data1', $taskNamespace)
            if ($null -ne $taskData) { $taskShape.Data1 = $taskData.InnerText }
            if ($taskShapePlan.SelectNodes('v:Connection', $taskNamespace).Count -gt 0) {
                if ($taskShape.SectionExists(7, 0) -eq 0) { [void]$taskShape.AddSection(7) }
                foreach ($taskConnection in $taskShapePlan.SelectNodes('v:Connection', $taskNamespace)) {
                    $taskRow = [int]$taskShape.AddRow(7, -1, 153)
                    $taskConnectionColumns = @{ X=0; Y=1; DirX=2; DirY=3; Type=4 }
                    foreach ($taskCell in $taskConnection.ChildNodes) {
                        if ($taskCell -isnot [System.Xml.XmlElement]) { continue }
                        Set-FlowchartCell $taskShape.CellsSRC(7, [int16]$taskRow, [int16]$taskConnectionColumns[$taskCell.LocalName]) $taskCell $taskShapeIds
                    }
                }
            }
        }
        # Use native GlueToPos, which creates references using the actual new IDs.
        foreach ($taskConnect in $taskPagePlan.SelectNodes('v:Connects/v:Connect', $taskNamespace)) {
            $taskSource = $taskShapes[$taskConnect.GetAttribute('FromSheet')]
            $taskTargetId = $taskConnect.GetAttribute('ToSheet')
            $taskTarget = $taskShapes[$taskTargetId]
            $taskTargetPlan = $taskShapePlans | Where-Object { $_.GetAttribute('ID') -eq $taskTargetId } | Select-Object -First 1
            $taskPortIndex = [int]([regex]::Match($taskConnect.GetAttribute('ToCell'), '\d+$').Value)-1
            $taskPort = $taskTargetPlan.SelectSingleNode('v:Connection[@IX="' + $taskPortIndex + '"]', $taskNamespace)
            if ($null -eq $taskPort) { throw "The drawing plan contains an unknown connection point: $taskTargetId/$taskPortIndex" }
            $taskPortX = Get-FlowchartNumber $taskPort.SelectSingleNode('v:X', $taskNamespace).InnerText
            $taskPortY = Get-FlowchartNumber $taskPort.SelectSingleNode('v:Y', $taskNamespace).InnerText
            $taskWidth = Get-FlowchartNumber $taskTargetPlan.SelectSingleNode('v:XForm/v:Width', $taskNamespace).InnerText
            $taskHeight = Get-FlowchartNumber $taskTargetPlan.SelectSingleNode('v:XForm/v:Height', $taskNamespace).InnerText
            $taskGlueCell = $taskSource.CellsU($taskConnect.GetAttribute('FromCell'))
            try { [void]$taskGlueCell.GlueToPos($taskTarget, $taskPortX/$taskWidth, $taskPortY/$taskHeight) }
            finally { Release-FlowchartCom $taskGlueCell }
        }
        foreach ($taskShape in $taskShapes.Values) {
            if ($taskShape.OneD -ne 0) { Set-FlowchartResult $taskShape.CellsU('ConFixedCode') 2 }
        }
        $taskSucceeded = $true
        return $taskDocument
    } finally {
        # Release every child RCW before the caller closes/reopens the document.
        # The document itself is the single COM object transferred to the caller.
        foreach ($taskOwnedShape in $taskShapes.Values) { Release-FlowchartCom $taskOwnedShape }
        $taskShapes.Clear()
        Release-FlowchartCom $taskPageSheet
        Release-FlowchartCom $taskPage
        Release-FlowchartCom $taskPages
        Release-FlowchartCom $taskDocuments
        if (-not $taskSucceeded -and $null -ne $taskDocument) {
            try { $taskDocument.Saved = $true; [void]$taskDocument.Close() } catch { }
            Release-FlowchartCom $taskDocument
        }
    }
}
