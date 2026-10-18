# Reference Flowchart｜科研与程序流程图

一个面向 Codex 的中文流程图技能：依据论文、代码或流程说明梳理完整主线、输入输出与反馈关系，再参照用户提供的图片绘制流程图，交付可编辑 SVG、可浏览 HTML 和高清 PNG。

默认采用白底黑线、宋体类中文字体、虚线分区和直角模块；用户指定的参考样式优先。技能独立工作，不依赖 Diagram Design 插件。

## 示例效果

下面是根据论文 *Anti-Jamming Communications Using Spectrum Waterfall: A Deep Reinforcement Learning Approach* 绘制的案例图，展示从发射端到接收结果的物理主线，以及选频控制和经验回放支路。

![示例：论文主线、选频控制与经验回放流程图](example/示例_论文主线流程图.png)

- [查看原尺寸示例图片（4560 × 2940）](example/示例_论文主线流程图.png)
- [查看示例论文 PDF](example/示例_论文.pdf)
- [论文 DOI：10.1109/LCOMM.2018.2815018](https://doi.org/10.1109/LCOMM.2018.2815018)
- [阅读该论文的来源对应与绘图注意事项](references/paper-case.md)

这张论文案例图与 `assets/example-flowchart.json` 是两个不同的示例。前者用于展示实际图件；后者是通用的脚本演示输入，不会直接生成上面的论文案例图，也不代表任何真实系统。

## 适用场景与能力边界

- 根据论文梳理系统模型、算法主线、模块归属、控制反馈和训练／推理关系，并核对相关式号。
- 根据程序入口、调用关系和数据变化绘制代码真实实现的流程。
- 根据业务或信号处理说明绘制完整的输入、处理、输出和闭环。
- 根据参考图片调整布局、字体、分区和线型，保留可编辑的矢量源文件。

Codex 负责阅读材料、理解语义、设计布局和检查来源；附带脚本只负责把**已经规划好坐标的 JSON** 绘制为图件并检查部分几何问题。脚本不会自动读取论文生成正确流程，也不提供自动布局或通用 LaTeX 排版。

## 目录与阅读顺序

```text
reference-flowchart/
├── README.md                       安装、依赖、运行方法与示例预览
├── LICENSE                         MIT 许可证
├── SKILL.md                        Codex 读取的技能入口与工作规则
├── agents/
│   └── openai.yaml                  技能显示名称、说明和默认提示词
├── scripts/
│   ├── render_flowchart.py          JSON → SVG、HTML、布局副本
│   └── export_png.cjs               HTML → PNG、几何检查报告
├── references/
│   ├── spec-format.md              JSON 字段、坐标约定和脚本参数
│   └── paper-case.md               示例论文的来源核对记录
├── assets/
│   └── example-flowchart.json       可直接运行的通用布局示例
└── example/
    ├── 示例_论文.pdf                 论文案例的输入材料
    └── 示例_论文主线流程图.png        README 中展示的案例图
```

首次使用先看本 README，再看 [SKILL.md](SKILL.md)。需要直接运行脚本或修改 JSON 时阅读 [格式说明](references/spec-format.md)；只有复用该论文案例时才需要阅读 `paper-case.md`。

`scripts/` 下的两个文件是命令行入口，不需要在别的程序中导入。`SKILL.md`、`agents/openai.yaml` 和 `references/` 是由 Codex 读取的指令或资料；`assets/`、`example/` 提供输入示例和效果示例。

## 运行依赖

| 用途 | 依赖 | 说明 |
| --- | --- | --- |
| 让 Codex 使用技能 | 支持本地技能的 Codex 环境 | 需要能够读取提供的论文、代码和参考图片；使用宿主已有的材料读取能力 |
| 生成 SVG／HTML | Python 3 | `render_flowchart.py` 只使用标准库，不需要 `pip install` |
| 导出 PNG、生成检查报告 | Node.js + **Node 版** `playwright` 包 | Python 版 Playwright 不能替代 Node 包；无需安装 `@playwright/test` |
| 浏览器截图 | 可启动的 Chromium、Chrome 或 Edge | 可复用已有浏览器，或自行安装 Playwright 配套的 Chromium |
| 中文文字渲染 | 系统中可用的中文字体 | 默认依次尝试 SimSun、Songti SC、Noto Serif CJK SC、serif；字体会影响字宽和换行，仓库不附带字体文件 |
| 从论文提取文本（按需） | 宿主现有 PDF 工具，例如 `pypdf`、`pdfplumber` | 不是绘图脚本依赖；扫描版 PDF 还需要单独的 OCR 能力 |

本次发布验证使用 Windows、Python **3.14.5**、Node.js **22.22.3**、Playwright **1.62.1**、系统 Chrome 和宋体。这里只列实际验证的组合，不声明其他版本或操作系统已经通过验证。

两个脚本均可在本地处理文件，不需要 OpenAI API Key。让 Codex 分析材料仍使用你已有的 Codex 账户或模型配置。

## 安装到 Codex

按照 [OpenAI 官方技能文档](https://learn.chatgpt.com/docs/build-skills)，可以把技能放在项目的 `.agents/skills/` 或用户目录的 `~/.agents/skills/` 下。下面的命令使用 PowerShell。

### 只在当前项目使用

在目标项目根目录运行：

```powershell
New-Item -ItemType Directory -Force -Path ".agents/skills" | Out-Null
git clone https://github.com/zainxx4536/reference-flowchart.git ".agents/skills/reference-flowchart"
```

### 在多个项目中使用

```powershell
$skillParent = Join-Path $HOME ".agents/skills"
New-Item -ItemType Directory -Force -Path $skillParent | Out-Null
git clone https://github.com/zainxx4536/reference-flowchart.git (Join-Path $skillParent "reference-flowchart")
```

两种安装方式选择一种即可。目录已存在时，先确认其中的内容；不要直接覆盖已有技能。需要更新 Git 克隆的版本时，可在对应技能目录执行 `git pull --ff-only`。

Codex 通常会自动发现新技能；如果未显示，重启 Codex 后再检查技能列表。通过 `$reference-flowchart` 明确指定技能，并给出材料和输出目录。例如：

```text
请使用 $reference-flowchart。
依据 example/示例_论文.pdf，参照 example/示例_论文主线流程图.png 的视觉形式，
绘制论文整体流程图，保留完整输入输出、控制反馈和学习支路。
涉及公式时只标注原论文式号；输出到当前工作区 output/，交付 SVG、HTML 和高清 PNG。
```

如果对话工作区不是技能目录，把示例路径替换为可访问的实际路径，或直接附上材料。用于新论文时，必须替换为新材料，不能沿用示例论文的模块和式号。

## 直接运行脚本

无需通过 Codex，也可以用附带 JSON 检查本地绘图和导出链路。以下命令均在**本仓库根目录**运行；`python`、`node` 不在 PATH 时，替换为对应可执行文件的路径。PowerShell 调用带空格的可执行路径时，在路径前加 `&`。

### 1. 生成可编辑 SVG 和 HTML

```powershell
python scripts/render_flowchart.py assets/example-flowchart.json --output-base output/example-flowchart
```

此步骤只需要 Python 标准库，生成：

```text
output/example-flowchart.svg
output/example-flowchart.html
output/example-flowchart.layout.json
```

HTML 可直接用浏览器打开，支持适应窗口和按原尺寸查看。`.layout.json` 是本次输入的布局副本，PNG 导出脚本会读取它；请将它与同名 HTML 保存在同一目录。

### 2. 准备 PNG 导出依赖

先复用已有的 Node Playwright 包和浏览器。在支持该工具的 Codex 环境中，可通过 `load_workspace_dependencies` 查找现有运行时；普通终端用户无需使用这个工具。

本地没有 Node Playwright 时，可自行执行以下安装命令。它会联网下载 npm 包；脚本本身不会自动安装依赖：

```powershell
npm install --no-save --package-lock=false playwright
```

安装方法见 [Playwright Library 官方文档](https://playwright.dev/docs/library)。如需复用本次验证的包版本，可把包名改为 `playwright@1.62.1`。

已有 Chrome 或 Edge 时，可直接在下一步指定路径。如果希望使用 Playwright 配套的 Chromium，可自行执行以下下载命令：

```powershell
npx playwright install chromium
```

浏览器及 Linux 系统依赖说明见 [Playwright 浏览器文档](https://playwright.dev/docs/browsers)。在无桌面环境的 Linux 中，仍需准备浏览器启动所需的系统库及中文字体。

### 3. 导出高清 PNG

依赖可自动发现时：

```powershell
node scripts/export_png.cjs output/example-flowchart.html
```

需要明确指定模块和浏览器时，下面以 Windows Chrome 为例：

```powershell
node scripts/export_png.cjs output/example-flowchart.html `
  --playwright-module "./node_modules/playwright" `
  --browser-path "C:/Program Files/Google/Chrome/Application/chrome.exe" `
  --scale 2
```

也可以通过以下环境变量指定已有依赖：

```powershell
$env:FLOWCHART_PLAYWRIGHT_MODULE = "C:/your-existing-node_modules/playwright"
$env:FLOWCHART_BROWSER_PATH = "C:/your-browser-location/chrome.exe"
node scripts/export_png.cjs output/example-flowchart.html
```

将路径替换为真实位置。命令行参数优先于环境变量；未指定时，脚本尝试加载可用的 `playwright`，再查找 Playwright Chromium 和常见位置的系统浏览器。

导出后新增：

```text
output/example-flowchart.png
output/example-flowchart.validation.json
```

默认 `--scale 2`，支持 1–4。通用示例画布为 1500 × 1030，默认 PNG 应为 **3000 × 2060**。输出目录已被 `.gitignore` 忽略。

### 4. 检查结果并修改布局

打开最终 PNG，检查阅读顺序、文字、箭头、分区和反馈接收者；再查看 `.validation.json`。修改 JSON 后，重新执行生成和导出两步。

两个脚本默认拒绝覆盖已有结果。确认输出文件属于本次任务后，可以分别为两条命令追加 `--overwrite`：

```powershell
python scripts/render_flowchart.py assets/example-flowchart.json --output-base output/example-flowchart --overwrite
node scripts/export_png.cjs output/example-flowchart.html --overwrite
```

创建新图时，可复制通用 JSON 到工作区，按新材料重新规划节点、分区、连线折点和声明路径。详细字段与限制见 [references/spec-format.md](references/spec-format.md)。

## 检查报告如何解读

- Python 阶段检查对象 ID、基础几何范围、分区归属、连线引用、正交折线以及已声明路径的连续性。
- 浏览器阶段检查部分文字越框、节点重叠、连线穿过无关节点、接入端点、严格内部交叉、PNG 尺寸及窗口适配问题。
- `status: "layout-pass"` 表示当前自动几何检查通过；仍需查看最终图片，并根据论文或代码核对语义。
- `status: "needs-fix"` 时进程返回非零退出码，PNG 和报告会保留，供检查 `issues` 并调整布局。

自动检查不证明算法正确，也不代表模型训练、代码实现或真实硬件运行已经通过验证。端点附近的含糊交叉、共线叠线、文字压线和阅读负担仍需要人工检查。

## 常见问题

| 现象 | 处理方式 |
| --- | --- |
| 找不到 `python`／`node` | 安装所需运行时，或在命令中使用已有运行时的绝对路径 |
| `Existing Playwright module not found` | 安装 **Node 版** `playwright`，或用 `--playwright-module` 指向包含 `package.json` 的 Playwright 包目录 |
| `Existing Chromium browser not found` | 用 `--browser-path` 指定已有 Chrome／Edge，或自行安装 Playwright Chromium |
| 浏览器存在但启动失败 | 确认路径、可执行权限和系统依赖；若由沙箱限制导致，按宿主权限机制处理 |
| 中文变方框或排版变化 | 安装可用中文字体，或修改 `canvas.font_family`；更换字体后重新导出和检查 |
| 找不到 `.layout.json` | 先执行 Python 生成步骤；确认 HTML 与同名布局文件位于同一目录 |
| `Output already exists`／`PNG/report already exists` | 更换输出基名，或确认文件后为对应命令追加 `--overwrite` |
| PNG 导出失败，但已有 SVG／HTML | 保留矢量和浏览器文件，补齐依赖后重试 PNG；此时 PNG 交付尚未完成 |
| 公式显示不符合预期 | 当前仅支持 `S{t+1}` 一类下标写法；优先标原文式号，复杂公式需要另行设计 |

## 许可证

本项目自有的技能说明、脚本、通用布局示例及项目制作的流程图采用 [MIT License](LICENSE)，允许使用、复制、修改、分发及商业使用；分发时应保留许可证要求的版权与许可声明。

**示例论文 `example/示例_论文.pdf` 属于第三方材料，不在本项目 MIT 授权范围内。** 论文著作权归原作者或相应权利人；其使用和再分发应遵守原有授权。仓库中的 MIT 许可证不授予该论文的额外权利。

使用本技能处理你自己的论文、代码或参考图片时，生成结果中涉及的第三方内容仍受其原有权利约束。
