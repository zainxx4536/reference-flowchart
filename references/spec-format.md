# 布局 JSON、来源定位与脚本调用

内置脚本是确定性的绘图工具：调用者负责语义和整体布局，脚本负责规格校验、明确的布局辅助、绘制和部分几何检查。

输入规格见 [../schemas/flowchart.schema.json](../schemas/flowchart.schema.json)。编辑器可在 JSON 顶部写 `"$schema": "../schemas/flowchart.schema.json"` 获得字段提示；相对路径以输入文件为准。Python 校验使用标准库实现该文件中使用的断言关键字，不联网加载远程 Schema，也不依赖 `jsonschema` 包。

## 基础字段

| 字段 | 用途 |
| --- | --- |
| `canvas` | 必需；`width`、`height` 为 100–20000 的有限数；可设标题、字体和字号 |
| `nodes` | 必需且非空；每项含 `id,x,y,width,height,lines`；支持 `parent,shape,font_size,line_height,ellipse_radius,sources` |
| `zones` | 虚线分区，先外后内排列；含 `id,x,y,width,height,title`；可设 `parent,title_y,font_size` |
| `edges` | 连线；含 `id,from,to`，以及互斥的 `points` 或 `route`；可设 `kind,arrow,sources` |
| `junctions` | 显式汇合点；含 `id,x,y`；可设 `parent,radius` |
| `labels` | 图中标注；含 `x,y,text`；可设 `font_size,bold,anchor` |
| `paths` | 需核对的有向路径；含 `name,nodes`，相邻节点必须有对应边 |
| `notes` | HTML 中的说明段落，不进入主图 |
| `layout` | 可选对齐及等距指令，在连线路由前执行 |
| `description` | SVG 可访问性说明 |
| `schema_version` | 可选，当前值为 `"1.0"` |

`id` 使用字母开头以及字母、数字、连字符和下划线。节点、分区、汇合点 ID 互不重复，边 ID 也须唯一。`parent` 必须引用包含该对象的分区，父分区不允许形成循环。

数值字段不接受数字字符串、布尔值或非有限数。未知字段会被拒绝，错误含 JSON 路径。JSON Schema 负责字段类型和范围，Python 另行检查对象引用、包含关系、图路径、路由字段互斥等关系。

## 文字与形状

`lines` 是显式分行的纯文本数组，首行默认加粗，正文默认字号 25。不要把 HTML 放入文字字段；文本会被转义。`S{t+1}` 一类花括号内容会排为下标，不支持通用 LaTeX。正文没有独立式号时，不编造编号。

形状：

- `rect`：默认直角矩形。
- `cylinder`：圆柱；默认 `ellipse_radius: 14`，上下各保留 `2×半径+7` 的文字边距。
- `diamond`：判断菱形；文字必须位于菱形内部，不只满足外接矩形的范围。
- `terminator`：起止节点，用圆角矩形形成胶囊形轮廓。

长文字优先精简或拆行，再扩大模块。字号、行高及下标会共同影响占用空间；跨平台更换字体后必须重新检查。`canvas.font_family` 是 CSS 字体族声明；PNG 导出还可以通过 `--font-path` 临时使用本地字体，此文件不会内嵌进 SVG／HTML。

分区标题通常位于顶部下方 38 单位，可设置 `title_y`。标题与模块、连线分别留白。`labels.anchor` 为 `start`、`middle` 或 `end`，默认 `middle`；分支的“是／否”等标签由调用者明确添加。

## 显式连线

```json
{
  "id": "input-process",
  "from": "input",
  "to": "process",
  "kind": "main",
  "points": [[300, 250], [500, 250]],
  "arrow": true
}
```

`points` 至少含两个点，只支持水平／垂直段，不允许零长度段。首尾点必须位于实际形状边界或汇合点中心。`kind: main` 的线稍粗，其他 `kind` 仅记录连线角色，不自动上色。`arrow: false` 适合汇入黑点的支线。

分区可以作为连线端点，表示参数更新作用于整个网络；业务主线应连到实际处理模块。不要用多个重叠线段表示共享路径，优先拆成汇入显式黑点、再从黑点离开的独立边。

## 对齐、等距与自动路由

```json
{
  "layout": {
    "align": [
      {"nodes": ["input", "process"], "axis": "y", "anchor": "center", "value": 300}
    ],
    "distribute": [
      {"nodes": ["input", "process", "result"], "axis": "x", "gap": 80}
    ]
  }
}
```

对齐先执行，等距后执行；仅移动列出的节点，不移动分区、文字标注或手写折点。`axis` 为 `x`／`y`，`anchor` 为 `start`／`center`／`end`。省略 `value` 时取组内第一个节点的对应锚点。等距按给定节点顺序排列，保留首节点的位置，并在相邻外框之间留下 `gap`。

需要移动节点后重新计算连线时，使用 `route`：

```json
{
  "id": "judge-accept",
  "from": "judge",
  "to": "accept",
  "route": {"from_port": "right", "to_port": "left", "clearance": 20}
}
```

`from_port`／`to_port` 为 `left,right,top,bottom,auto`，默认 `auto`；端口位于相应边的中点。`clearance` 为 4–200，默认 20。路由在节点外框扩展的障碍网格上搜索正交路径，优先较短且折点较少的路线。

自动路由避开节点，不自动避开所有标签、分区标题或其他连线；导出检查仍可能要求调整。没有可用路线时会报错，应移动节点、改变端口／间距，或用 `points` 明确设计。父分区需预留足够空间；助手不自动扩大画布或改变主体归属。

生成的 `.layout.json` 保存解析完成的坐标和折点，移除已经执行的 `layout`／`route` 指令。原始 JSON 保留为编辑源。完整示例见 [../assets/branching-flowchart.json](../assets/branching-flowchart.json)。

## 来源记录

节点和边都支持可选的 `sources` 数组，例如：

```json
{
  "sources": [
    {"kind": "paper", "document": "doi:10.xxxx/example", "page": 3, "equation": "5"},
    {"kind": "code", "document": "src/service.py", "symbol": "choose_action", "line_start": 20, "line_end": 45},
    {"kind": "design", "document": "本次建议方案", "note": "材料未实现的建议步骤"}
  ]
}
```

`kind` 与 `document` 必需。其他可选定位字段为 `page,section,figure,equation,symbol,line_start,line_end,note`；页码与行号从 1 开始，结束行不能早于开始行。来源字段按纯文本处理，不打开文献、不执行文件、不自动验证对应关系。

HTML 中可展开来源表；检查报告保留逐对象来源和覆盖数量。覆盖数量表示已填写记录，不能代替对原文或代码的核对。论文案例仅提供 DOI 与定位记录，不分发原论文 PDF。

## 命令与产物

```text
python scripts/render_flowchart.py input.json --output-base output/chart
node scripts/export_png.cjs output/chart.html
```

只验证输入可用 `--validate-only`。生成器输出同名 `.svg`、`.html`、`.layout.json`；导出器追加 `.png`、`.validation.json`。输出基名不含扩展名；默认拒绝覆盖，确认后为对应命令追加 `--overwrite`。

PNG 默认 2 倍，可用 `--scale 1` 至 `--scale 4`。模块、浏览器和字体可通过 `--playwright-module`、`--browser-path`、`--font-path` 指定，也可用 README 中的环境变量。

SVG 内记录布局文件 SHA-256；HTML 中的 SVG 必须与独立 SVG 一致。不要手工混用不同轮次的三种文件。修改输入后重新生成，并重新导出 PNG。输出使用临时文件写入后替换，报告同时记录布局、SVG 和 PNG 哈希。

## 自动检查范围

- 规格：字段类型与范围、ID、父分区循环与包含关系、连线引用、正交性、有向声明路径。
- 几何：节点重叠、连线穿节点、实际形状端口、严格内部交叉、端点／近端点接触及共线叠线。
- 文字：结合 SVG 字符基线位置与 Canvas 字形边界，检查越框、文字重叠和文字压线，并在报告保留 SVG 原始度量供对照。
- 渲染：中文探针实际字体和示例字形、PNG 尺寸、900 像素窗口适配及原尺寸切换。

`layout-pass` 表示自动项目通过；`needs-fix` 会返回非零退出码，保留 PNG 和报告。几何检测包含容差和文字边界估计，不证明没有所有视觉问题。没有包含论文语义、真实模型训练或硬件验证。交付前仍需打开最终 PNG 检查。
