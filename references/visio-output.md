# Visio 可编辑输出

仅在用户选择 Visio／`.vsdx` 时读取。格式选择与会话内复用规则见 [../SKILL.md](../SKILL.md)；用户未明确格式且本会话没有已确认选择时，先询问 PNG（默认推荐）或 Visio，不直接替用户选择。

## 依赖与交付

需要 Windows、PowerShell，以及已安装并可通过 COM 启动的桌面版 Microsoft Visio 2013 或更高版本。仅有 Visio 网页版、查看器或 Office 其他应用不能提供本脚本所需的自动化接口。Visio 导出不依赖 Node、Playwright 或浏览器。Python 标准库校验并解析布局，生成 XML 绘图计划；`scripts/visio_native.ps1` 读取计划，通过独立的桌面 Visio COM 实例逐一创建原生形状、文字与一维连接线，设置胶合关系，再保存 `.vsdx`。主流程不调用 Visio 的 VDX 导入功能。

主交付为 `.vsdx`：模块、分区、文字、汇合点和连接线由 COM 创建的 Visio 原生对象构成，可在 Visio 中单独选择、编辑文字、移动或调整。不能将整张 SVG／PNG 导入后保存，或仅改扩展名，作为本模式的完成条件。保留源 JSON、解析后 `.layout.json` 及同轮次 SVG／HTML，便于核对来源和重新生成。

## 生成

先按 [spec-format.md](spec-format.md) 设计布局并运行生成器。Visio 导出器使用生成器解析后的 `.layout.json`，其中对齐、等距和自动路由已经转为最终坐标与折点；也可传入原始规格，导出器会复用相同的校验、对齐和路由逻辑；为便于比对，推荐使用同轮次 `.layout.json`。

`scripts/export_visio.ps1` 负责准备绘图计划、调用原生建图 helper、保存结果并核对 VSDX 包结构。在仓库根目录执行：

```powershell
python scripts/render_flowchart.py assets/branching-flowchart.json --output-base output/my-flowchart
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/export_visio.ps1 -LayoutPath output/my-flowchart.layout.json -OutputPath output/my-flowchart.vsdx
```

需要可直接查看的 PNG 预览时，由同一次 Visio 导出增加：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/export_visio.ps1 -LayoutPath output/my-flowchart.layout.json -OutputPath output/my-flowchart.vsdx -PreviewPath output/my-flowchart.visio.png
```

预览可选，不改变用户选择的 Visio 主交付。它由 Visio 渲染，不能用浏览器导出的 PNG 替代对最终 Visio 文档的视觉检查。

Python 不在 PATH 时，为 PowerShell 命令添加 `-PythonPath "C:/Python/python.exe"`。

脚本默认拒绝覆盖。确认目标文件属于本次任务后，为 Visio 命令追加 `-Overwrite`；生成器单独使用 `--overwrite`。带空格的路径加双引号。修改源 JSON 后，重新生成解析后布局，再导出 Visio，不能混用不同轮次文件。PowerShell 使用的 XML 绘图计划是临时文件，成功或失败后均会清理。

## 可选：保留旧版 XML 中间源

需要独立保留绘图计划或检查其结构时，可只用 Python 生成 VDX：

```powershell
python scripts/export_visio.py output/my-flowchart.layout.json --output output/my-flowchart.vdx
```

此命令可跨平台运行，只使用 Python 标准库；默认拒绝覆盖，确认后添加 `--overwrite`。VDX 是旧版 Visio XML 中间源，记录形状、文字、连接线与胶合关系，不是 `.vsdx`。部分 Visio 安装的 VDX 导入受限，XML 结构校验通过也不能保证手动导入成功；主导出流程读取其中的绘图计划并通过 COM 建图，不依赖该导入功能。

用户选择 `.vsdx` 时，不能仅交付 VDX 就声称已完成。不能调用桌面 Visio 时，保留原始输入与已有 SVG／HTML 等源文件，说明原因并询问是否切换 PNG。只有用户明确接受 XML 中间源时才另行交付 VDX，并说明兼容性限制；需要保留它时必须单独运行上面的 Python 命令。

## 完成前核对

1. 环境允许时，重新用桌面 Visio 打开保存后的 `.vsdx`，确认文件可正常读取；无法实际重开或编辑验证时，在交付中披露限制。
2. 查看 Visio 导出的预览或应用截图，检查中文字体、上下标、首行强调、圆柱文字边距、分区标题、箭头方向、正交折点、画布边界与原布局；字体度量可能与浏览器不同，发现截断时调整源布局后重新导出。
3. 检查至少一个模块的文字可修改，形状和连接线可单独选中编辑，并核对连接端点。文件可打开或预览看起来相似，均不能单独证明其内容可编辑。
4. 与 PNG 模式共用语义检查：输入输出连续，控制与反馈接收方明确，式号和来源定位正确。Visio 文件不代替来源核对。

XML 结构、形状数量、文字内容和连接关系的单元检查只验证绘图计划，不证明最终 `.vsdx` 能在目标 Visio 版本中正确打开或显示，也不能单独证明其实际编辑效果。导出器核对保存后的 VSDX 包中原生形状数量且无嵌入整图，不自动重开文档；包结构检查不能替代中文排版与实际编辑检查。桌面 Visio 验证需在安装且能够运行 Visio 的 Windows 会话中完成。

具备可用桌面 Visio 时，可单独运行集成检查：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tests/visio.integration.ps1 -PythonPath "C:/Python/python.exe"
```

将 Python 路径替换为已有可执行文件。此检查不属于默认 `npm test`；示例的 `-ExecutionPolicy Bypass` 仅对本次 PowerShell 进程生效，不修改系统执行策略。

只在完成实际检查后说明已验证可编辑。没有桌面 Visio、COM 无法启动、字体不完整或导出失败时，记录具体原因并保留源文件，询问用户是否切换 PNG；未得到同意前不切换，也不声称已完成 Visio 交付。

## 格式差异

Visio 使用本机字体和自己的文字度量，视觉上可能与 SVG／浏览器输出略有不同。SVG 的 CSS 字体族不能视为已在 Visio 中安装；浏览器 `--font-path` 临时加载的字体不会自动安装到 Visio。需要在 Visio 中实际确认中文显示与布局。

原始输入 JSON 是重新生成的来源；用户在 Visio 内的后续人工修改不会自动回写 JSON。若从源文件再次导出，使用新文件名，或确认后覆盖，避免丢失需要保留的人工调整。
