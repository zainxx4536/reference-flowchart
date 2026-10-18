# 坐标化 JSON 与脚本调用

使用内置脚本时读取。它们是小型确定性绘制工具，不提供自动布局或论文语义校验；需要其他形状或复杂交互时可直接编写 SVG／HTML。

## 文件与基本字段

可从 [../assets/example-flowchart.json](../assets/example-flowchart.json) 理解格式，随后为本次材料重新设计布局。示例中的学习支路是可选演示，不要自动移植到每张图。

| 字段 | 用途 |
|---|---|
| `canvas` | 必需；`width`、`height` 为 SVG 单位，`title`、`subtitle` 可选；正文默认 `font_size: 25`，字体可用 `font_family` 修改 |
| `description` | SVG 可访问性说明，简述主要路径 |
| `zones` | 虚线分区，按先外后内顺序排列；对象含 `id,x,y,width,height,title` |
| `nodes` | 模块；含 `id,x,y,width,height,lines`；可选 `parent,shape,font_size,line_height` |
| `edges` | 含 `id,from,to,points`；`points` 是 `[x,y]` 折点数组；可选 `kind,arrow` |
| `junctions` | 明确汇合点，含 `id,x,y`，默认黑点半径 5 |
| `labels` | 连线旁或图注文字；含 `x,y,text`，可选 `font_size,bold,anchor` |
| `paths` | 声明需要核对的路径；每项含 `name,nodes`，其中相邻 id 必须有对应有向边 |
| `notes` | HTML 中的解释段落字符串，不进入主图 |

对象 `id` 使用字母开头及字母、数字、连字符、下划线。节点、分区、汇合点的 id 互不重复。`parent` 只可引用包含它的分区；分区只做分组，不是普通业务处理节点。

`lines` 是显式分行的字符串数组，首行默认加粗。文本按纯文本转义，不执行 HTML。可用 `S{t+1}` 表示下标，不支持通用 LaTeX 排版；仅标式号通常无需数学排版。

节点形状 `rect` 为默认矩形，`cylinder` 表示圆柱存储，默认椭圆半径 14，可用 `ellipse_radius` 修改。圆柱文字需在上下各 `2×半径+7` 的边距以内；增加圆柱高度，而不是让文字压住弧线。

分区标题默认放在其顶部下方 38 单位，可用 `title_y`、`font_size` 修改。节点避开标题区；大框与内部模块分别留白。

`edges.points` 由调用者规划，只支持水平／垂直段。起止点位于 `from`／`to` 对象边界或汇合点中心。`kind: main` 的线稍粗；其他角色由语义、路径和旁注区分，不自动上色。`arrow: false` 适合汇入黑点的支线，离开汇合点的箭头继续指向接收模块。

连接到分区边界可表示参数更新作用于整体网络，但业务主线应连接实际模块。不要把一段没有明确接收者的线止于空白。

`labels.anchor` 为 `start`、`middle` 或 `end`，默认 `middle`。标签与连线保持距离，不能靠白底遮掉关键箭头。

## 运行

先确定当前 Python 和 Node 命令。以下用 `python` 和 `node` 表示它们；若不在 PATH，改用发现的绝对可执行路径。`<skill>`、`<spec>`、`<base>` 是本次真实路径，输出基名不含扩展名。

```text
python "<skill>/scripts/render_flowchart.py" "<spec>.json" --output-base "<base>"
node "<skill>/scripts/export_png.cjs" "<base>.html"
```

在已有工作区运行时中发现 Playwright 和浏览器后，可以显式指定：

```text
node "<skill>/scripts/export_png.cjs" "<base>.html" --playwright-module "<existing-node_modules>/playwright" --browser-path "<existing-browser-executable>" --scale 2
```

也支持环境变量 `FLOWCHART_PLAYWRIGHT_MODULE`、`FLOWCHART_BROWSER_PATH`。脚本优先使用显式值，否则检查已有安装；不自动执行 `npm install` 或下载浏览器。

对已确认是本次图件的文件再次导出时，在对应命令后加 `--overwrite`。脚本默认拒绝覆盖。

## 输出与检查范围

绘制脚本输出同名 `.svg`、`.html`、`.layout.json`。导出脚本追加 `.png`、`.validation.json`；PNG 默认 2 倍尺寸。HTML 支持适应窗口和按原尺寸查看。

- 绘制前检查对象 id、画布范围、分区归属、连线引用、正交路由和声明路径是否连续。
- 浏览器检查节点文字边界、圆柱弧线、图注与节点重叠、画布文字截断、节点互压、连线穿无关节点、接入端口、严格内部交叉、PNG 尺寸及窗口适配。
- 报告 `layout-pass` 仅表示上述自动几何项目通过，不证明论文／程序逻辑正确。端点附近的含糊连接、共线叠线、文字压线、密集阅读负担等仍需视觉检查。
- 发现问题时保留报告和 PNG 便于修正，但不要把失败图当作最终交付。实际打开最终图片，结合来源再核查语义。

测试可在工作区临时输出目录使用示例规格；不要把测试 PNG 等生成物装进技能目录。
