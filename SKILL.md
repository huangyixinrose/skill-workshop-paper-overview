---
name: review-workshop
description: >
  给定一个学术 workshop 或会议主页 URL，通读全部论文，产出一份按主线分类的综述报告（单文件 HTML）。
  报告包含：编者整体判断、分类总表、主线综述、议题×论文对照（共性问题/中心论文/研究空白）、逐篇速查卡、少量关键架构图。
  当用户说"帮我通读这个 workshop 的所有论文""出一份综述""梳理这个会议的核心进展与思路"时触发。
---

# review-workshop

把一个 workshop/会议主页变成一份分类综述报告。

## 总览

这条流水线读完一个 workshop 的全部论文，输出单文件 HTML 综述。成品包含六个板块：编者整体判断（卷首）、分类总表、按主线展开的综述、议题×论文对照（共性问题/中心论文/研究空白）、逐篇速查卡（含少量架构图与批判核查提示）、未公开论文。

设计原则：**能用脚本做的不交给模型**。整条流水线只在 5 处调用 LLM——侦察主页提取论文清单、精读每篇论文、撰写主线综述与查漏、议题对照扫描、编者写卷首判断——其余环节（下载、抽文本、分组、抠图、渲染 HTML）全由脚本完成。

## 何时触发

用户给出一个主页 URL（CVPR/NeurIPS workshop、会议 proceedings、论文集页等），希望"通读全部论文并出综述"。

## 全貌：流水线阶段总览

开始前先看一眼整体流程。详细架构图见 `docs/flowchart.svg`。

| 阶段 | 做什么 | 输入 | 产出 | 工具 | 模型 |
|------|--------|------|------|------|------|
| 1. 侦察 | 从主页提取论文清单 | 主页 URL | `manifest.json` | WebFetch + `prompts/recon.md` | 当前主模型 |
| 2. 采集预处理 | 下载 PDF、抽文本 | `manifest.json` | `pdf/`、`txt/`、体量画像 | `scripts/acquire.py` | 无（纯脚本） |
| 3. 标定 | 先跑 3 篇验证成本与质量 | 3 篇 `txt/*.txt` | 3 条 digest + 成本估算 | 同阶段 4 | 便宜模型 |
| 4. 并行精读 | 每篇一个子agent结构化精读 | `txt/*.txt` + 类目 | `data/digests.json` | `workflow/review_workshop.template.js` | 便宜模型 |
| 5. 主题综述 + 查漏 | 按主线写综述、critic 检查 | digests + 类目 | `data/sections.json`、`data/critic.txt` | `prompts/theme_writer.md`、`prompts/critic.md` | 便宜模型 |
| 6. 议题对照 | 跨论文系统性对照扫描 | digests | `data/crosscut.json` | `prompts/crosscut.md` | 便宜模型 |
| 7. 配图 | 为少数论文裁剪关键架构图 | PDF + digests | `figures/fig_<id>.png` | `scripts/extract_figure.py` | 强模型（看图定框） |
| 8. 卷首 + 组装 | 编者写整体判断、渲染 HTML | sections + critic + crosscut + digests | `report.html` | `prompts/preface.md`、`scripts/build_report.py` | 强模型（卷首）/ 无（组装） |

## 人工确认关口

流水线设有 4 个确认点。它们在流程中自然出现（下文各阶段会标注），但在实践中合并为**开跑前一次性确认**：做完侦察后，把 4 项一起呈现给用户拍板，拍板后全自动跑到底。

| 关口 | 确认什么 | 出现在 |
|------|----------|--------|
| 选题范围 | 抓到的论文清单、缺失项、是否排除某些条目 | 侦察之后 |
| 分类方案 | 主线类目名 + 每篇预归类 | 侦察之后（或标定之后微调） |
| 配图策略 | 默认"少而精"，确认上限（建议 4-8 张） | 一并确认 |
| 终稿格式 | 单文件 HTML（默认）/ 视角侧重 | 一并确认 |

用户传 `--yes` 或说"全自动"时，跳过确认，用默认策略。

## 流水线详述

### 阶段 1 · 侦察

用 WebFetch 抓取主页，按 `prompts/recon.md` 的提示词提取全部论文清单。

对每篇提取：完整标题、PDF 直链、赛道（archival / non-archival）。整理成 `manifest.json`，格式为 `[{"id":"p01","title":"...","url":"...","track":"archival"}, ...]`。

链接补全是这一步的主要坑（各家主页格式差异大），`prompts/recon.md` 里列出了 CVF / arXiv / OpenReview / 站内相对链接等常见规则。无全文或撤稿的论文不进 manifest，放入 `data/missing.json`，后续由 recovery 子agent检索。

**这是整条流水线最脆弱的环节。** 主页结构千变万化，侦察有时会漏抓或链接错误。如果解析不了，直接退回让用户手工贴链接清单。

> 确认关口：侦察完成后，把论文清单、缺失项、分类方案草案、配图策略、终稿格式一并呈现给用户确认。

### 阶段 2 · 采集预处理

运行 `scripts/acquire.py`：

```bash
python scripts/acquire.py --workdir <dir> [--jobs 8]
```

脚本并发下载全部 PDF，用 `pdftotext -layout` 抽取纯文本，打印体量画像（字符数、页数、失败项）。产出 `pdf/<id>.pdf`、`txt/<id>.txt`、`data/acquire_report.json`。

下载失败的论文移入 `data/missing.json`，不卡主流程。

**为什么抽文本而不是把 PDF 当图片喂模型：** 这是最大的省钱点。纯文本输入相比整页图片，token 消耗低约 3 倍，且精读质量不受 OCR 噪声影响。

### 阶段 3 · 标定（3 篇试跑）

从 manifest 中挑 3 篇跨主线的代表性论文，走一遍阶段 4 的精读流程，量出真实 token 成本与输出质量，再决定是否全量展开。

**为什么要先标定：** 没有这一步就是闭眼调优。标定能暴露提示词问题（比如 schema 字段不够用、类目划分不合理）、估算全量成本，也为用户微调分类方案提供依据。

### 阶段 4 · 并行精读

用 `workflow/review_workshop.template.js` 编排并行精读。使用前需把模板里的 5 处 `▼FILL▼` 填好（`BASE` 文本目录、`CATS` 类目列表、`PAPERS` 论文清单、`RECOVER` 缺失标题、`AUDIENCE` 目标读者），然后用 Workflow 工具运行。

每篇论文分配一个子agent（便宜模型），读取 `txt/<id>.txt`，按 `prompts/reader.md` 的提示词精读，强制输出符合 `schemas/digest.schema.json` 的结构化数据。schema 不合格时自动重试。

同时启动 1 个 recovery 子agent，用 WebSearch 检索 `data/missing.json` 中缺失论文的预印本。

产出汇总为 `data/digests.json`。recovery 结果写入 `data/recovery.txt`。

digest schema 的核心字段：`id`、`title`、`team`、`track`、`category`、`problem`、`method`、`key_results`、`limitations`、`relevance`、`card_zh`（120-180 字速查卡）、`figure_essential`（是否值得配图）、`figure_ref`、`figure_caption`、`appraisal`、`future_calls`。完整定义见 `schemas/digest.schema.json`。

其中两个新增字段的定义：

- **`appraisal`**（批判核查提示）：按该工作**自身范式**给出的核查线索——证据是否扎实、核心构念/指标是否清晰且与同领域一致、有何隐含前提。这是给人的线索而非定论，无明显问题时写"未见明显问题"。标注"待人核查"。
- **`future_calls`**（局限与未来呼吁）：论文自陈的局限和未来工作呼吁，是现成的研究 gap 候选。无则写"无"。

**为什么强制结构化输出 + 重试：** 多个子agent并行跑，结果必须能拼起来。没有 schema 约束，输出格式漂移会导致后续组装失败。

**断点续跑：** Workflow 支持 `resumeFromRunId`。20 篇跑到一半中断了，可以从断点续跑，不必重头来。

### 阶段 5 · 主题综述 + 查漏

分两步：

**5a. 主线写手。** 按 `data/cats.json` 的类目分组（确定性脚本），每条主线分配一个写手子agent（便宜模型），按 `prompts/theme_writer.md` 撰写 600-1000 字综述。产出写入 `data/sections.json`，顺序与 `cats.json` 对齐。

**5b. 查漏 critic。** 跑一个 critic 子agent（便宜模型），按 `prompts/critic.md` 审查全部 digests + sections 草稿，检查：归错类或遗漏的论文、缺论文支撑的结论、不可比数字并排、绝对值写成相对提升、以偏概全的断言、缺失的跨主线视角。

**关键后续：把 critic 发现的事实硬伤回填修正到 `data/sections.json` 和 `data/digests.json`。** 这是单次摘要给不了的质量来源。critic 发现的跨主线主轴（比如"视觉保真不等于物理可用""效率离实时还有多远"），也是编者写卷首的好素材。

### 阶段 6 · 议题对照（CrossCut）

在主题综述与查漏完成之后、卷首与组装之前，新增一轮**跨论文系统性对照扫描**。用便宜模型（Sonnet）跑一个子agent，读取 `data/digests.json` 中全部论文的精读结果（特别是 `appraisal`、`future_calls`、`limitations`、`method`、`key_results` 等字段），按 `prompts/crosscut.md` 的提示词做结构化对照，产出 `data/crosscut.json`。

`crosscut.json` 包含四个顶层对象：

- **`issues`**（议题×论文矩阵）：提取跨论文的共性议题（如"sim-to-real gap 的量化方式""视频质量评估指标的可比性"），每条议题列出涉及的论文 id 列表。
- **`common_problems`**（共性问题候选）：多篇论文共享的方法局限或评估盲区，每条列出涉及论文 + 为何值得注意。
- **`central_papers`**（建议优先二次深读的论文）：基于议题覆盖度和被引关系推荐的重点论文，每条列出涉及议题 + 推荐理由。
- **`white_space`**（研究空白）：从 `future_calls` 和跨论文对比中提炼的未被覆盖方向。

另有一个 **`human_note`** 字段，固定写入"以上均为系统性对照扫描的候选线索，标注待人核查；真正的深度 critical thinking 请回到原文完成"。

**定位铁律：这一层是"系统性对照扫描 → 给人的核查提示/线索"。** AI 只负责扫描、列候选，一律标注"待人核查"，不下定论。真正的深度 critical thinking 由人读原文完成。正因如此，用便宜模型即可——扫描覆盖面比模型智力更重要。

产出的 `crosscut.json` 有两个用途：（1）直接渲染为报告中的"议题×论文对照"版块；（2）为编者写卷首提供额外的跨论文视角素材。

### 阶段 7 · 配图

从 digests 中挑选 `figure_essential` 为 true 的论文，由编者（强模型）把关，只为少数架构/流程图确有助于理解的论文配图，总数不超过确认关口约定的上限。

每篇配图走三步循环，用 `scripts/extract_figure.py`：

```bash
# 1. 定位：找到图在第几页
python extract_figure.py locate --workdir DIR --id p10 --ref "Figure 2" --caption "Framework of ..."

# 2. 渲染：把该页渲染成整页 PNG，供查看定框
python extract_figure.py render --workdir DIR --id p10 --page 4

# 3. 裁剪：按坐标裁出图（查看整页 PNG 后确定 box），缩到宽 <=1100
python extract_figure.py crop --workdir DIR --id p10 --box 28 52 1248 398
```

产出 `figures/fig_<id>.png`。`build_report.py` 会自动把存在的 `fig_<id>.png` 以 base64 内联到对应卡片。裁完后查看验证，不满意改 box 重裁。

**为什么"少而精"：** `figure_essential` 模型倾向于全标 true，这是已知噪声。不要因为"每篇都有架构图"就每篇配；只配真正帮助理解的。

### 阶段 8 · 卷首 + 组装

**8a. 卷首（强模型亲自写）。** 这是整份综述最高价值的部分，不外包给子agent。通读 `data/sections.json` + `data/critic.txt` + `data/crosscut.json`，按 `prompts/preface.md` 写出编者"整体判断"——核心成果、能力边界、未来趋势，每条判断都挂具体证据（哪篇、什么数字）。优先写 critic 发现的跨主线主轴。产出 `data/preface.html`（HTML 片段）。

填写 `data/meta.json`（标题、副标题、说明）。

**8b. 组装（纯脚本）。**

```bash
python scripts/build_report.py --workdir <dir>
```

`build_report.py` 是确定性渲染器，不调用模型。它读取 `data/` 下的全部结构化数据和 `figures/` 下的图片，组装成单文件 `report.html`（图以 base64 内联，可离线打开）。

**验收：** 起静态服务截图自检——图片渲染、卡片布局、表格对齐，确认无误后交付。

## 工作目录与产物链

每次运行使用一个独立 workdir（如 `./<slug>_review/`），产物按阶段逐步生成：

```
<workdir>/
├── manifest.json                # 阶段 1 → 论文清单
├── pdf/                         # 阶段 2 → 下载的 PDF
├── txt/                         # 阶段 2 → 抽取的纯文本
├── figures/
│   ├── <id>_page.png            # 阶段 7 → 渲染的整页（中间产物）
│   └── fig_<id>.png             # 阶段 7 → 裁剪的成品图
├── data/
│   ├── acquire_report.json      # 阶段 2 → 体量画像
│   ├── missing.json             # 阶段 1/2 → 缺失论文
│   ├── digests.json             # 阶段 4 → 全部精读结果（含 appraisal/future_calls）
│   ├── cats.json                # 确认后 → 主线类目列表
│   ├── sections.json            # 阶段 5 → 各主线综述
│   ├── recovery.txt             # 阶段 4 → 缺失论文检索结果
│   ├── critic.txt               # 阶段 5 → 查漏审查结果
│   ├── crosscut.json            # 阶段 6 → 议题对照（issues/common_problems/central_papers/white_space）
│   ├── preface.html             # 阶段 8 → 编者整体判断
│   └── meta.json                # 阶段 8 → 标题/副标题/说明
└── report.html                  # 阶段 8 → 最终成品
```

## 模型分配

| 角色 | 模型档位 | 说明 |
|------|----------|------|
| 精读子agent（每篇） | 便宜（Sonnet/Haiku） | 并发量大，是 token 消耗大头 |
| recovery 子agent | 便宜（Sonnet） | 检索缺失论文 |
| 主线写手（每条主线） | 便宜（Sonnet） | 600-1000 字综述 |
| 查漏 critic | 便宜（Sonnet） | 审查全部 digests + sections |
| 议题对照子agent | 便宜（Sonnet） | 系统性对照扫描，重覆盖面不重智力 |
| 卷首（编者整体判断） | 强（Opus） | 最高价值部分，需要跨主线洞察 |
| 配图判断 + 定框 | 强（Opus） | 需要看图做判断 |
| 组装 HTML | 无模型 | `build_report.py` 纯脚本渲染 |

经验值：一个约 20 篇的 workshop，总消耗约 100 万 token，耗时约 10-15 分钟。

## 关键工程决策

这些决策在上文各阶段已就地解释了 why，这里汇总备查：

1. **PDF 抽文本，不喂图。** 最大省钱点，token 降约 3 倍。（阶段 2）
2. **先标定 3 篇再全量。** 拿真实成本和质量反馈，避免低估翻车。（阶段 3）
3. **强制结构化输出 + 重试。** 多代理并行结果能拼起来的前提。（阶段 4）
4. **查漏 critic 必跑，且把硬伤回填。** 单次摘要给不了的质量。（阶段 5）
5. **批判性对照层定位为给人的提示而非定论。** 议题对照只做系统性扫描、列候选，标注"待人核查"；人读原文做深度 critical thinking。便宜模型即可。（阶段 6）
6. **配图少而精。** 只配真帮理解的，不因"每篇都有架构图"就每篇配。（阶段 7）
7. **断点续跑。** Workflow 支持 `resumeFromRunId`，跑到一半挂了能续。（阶段 4）
8. **侦察是最脆弱的环节。** 各家主页格式差异大，解析不了就退回让用户贴链接清单。（阶段 1）

## 文件清单

| 文件 | 用途 |
|------|------|
| `scripts/acquire.py` | 下载 PDF + pdftotext 抽文本 + 打印体量画像 |
| `scripts/extract_figure.py` | 关键图的定位（locate）/ 渲染（render）/ 裁剪（crop） |
| `scripts/build_report.py` | 确定性组装单文件 HTML，纯渲染，不调用模型 |
| `schemas/digest.schema.json` | 每篇精读的结构化输出契约 |
| `prompts/recon.md` | 侦察提示词：从主页提取论文清单 |
| `prompts/reader.md` | 精读提示词：单篇结构化摘要 |
| `prompts/theme_writer.md` | 写手提示词：一条主线的综述 |
| `prompts/critic.md` | 查漏提示词：审查归类、事实、跨主线视角 |
| `prompts/crosscut.md` | 议题对照提示词：跨论文系统性对照扫描，产出共性问题/中心论文/研究空白 |
| `prompts/preface.md` | 卷首提示词：编者整体判断 |
| `workflow/review_workshop.template.js` | 并行精读 + 综合的 Workflow 编排模板（填 PAPERS/CATS 后运行） |
| `docs/flowchart.svg` | 流水线架构图 |
| `examples/` | 样例成品 |
